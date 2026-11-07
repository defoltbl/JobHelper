"""Bridge between the Qt Quick (QML) front-end and the JobHelper backend.

The read methods delegate to the proven `ui_api.Api`; the long-running
pipeline / email scan run on a worker thread and report progress through Qt
**signals** (QML updates live – no polling needed).

Exposed to QML as the context property `bridge`.

`Bridge` is put together from parts: the runs (search, email scan, scoring again,
pausing on the limit, stopping) are in `bridge_runs`, everything the job windows
ask for is in `bridge_jobs`. Here: the signals, sign-in and connections, Options,
the weekly schedule and the usage card.
"""
from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from PySide6.QtCore import Property, QObject, Signal, Slot

from .ui_api import Api
from .bridge_jobs import JobSlots
from .bridge_runs import RunSlots
from . import trouble  # noqa: I001
from . import (api_system, claude_cli, config, integrity, schedule, store)
from .claude_cli import ClaudeCli


def _address_problem(address: str) -> str:
    """'' or what is wrong with an email address (the window checks the same before it asks)."""
    import re
    text = str(address or "").strip()
    if not text:
        return "Enter the email address."
    if len(text) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", text):
        return "That does not look like an email address."
    return ""


class Bridge(RunSlots, JobSlots, QObject):
    # key in {a1..a5}, status in {running,done}, info text
    agentChanged = Signal(str, str, str)
    logChanged = Signal(str)
    runFinished = Signal(str, str)        # mode, summary
    runningChanged = Signal(bool)
    progressChanged = Signal(str, int, int)   # agent key, done, total (within its stage)
    usageReady = Signal()                 # fresh usage numbers are available
    connectionsReady = Signal("QVariantMap")   # result of checkConnections()
    cvSet = Signal("QVariantMap")              # a chosen master CV was checked and set (or why not)
    letterSaved = Signal("QVariantMap")        # an edited letter was saved, with its PDF (or why not)
    pdfReady = Signal("QVariantMap")           # the single PDF of a letter and a CV was made and opened (or why not)
    limitChanged = Signal("QVariantMap")       # paused on Claude's limit / may resume / resumed
    paragraphReady = Signal("QVariantMap")     # a rewritten letter paragraph (or why it failed)
    prepReady = Signal("QVariantMap")          # interview preparation finished (or why it failed)
    replyReady = Signal("QVariantMap")         # a pasted reply was filed (or why not)
    answersReady = Signal("QVariantMap")       # answers for a job's form were drafted (or why not)
    rescoreReady = Signal("QVariantMap")       # one job was scored again (or why not)
    docsReady = Signal("QVariantMap")          # the CV and letter of one job were written (or why not)
    storageDone = Signal("QVariantMap")        # a backup was made, checked or copied out (or why not)
    emailTested = Signal("QVariantMap")        # a saved mailbox was tried: {box, ok, msg}
    emailSaved = Signal("QVariantMap")         # a mailbox was tried and saved (or why not)
    assistantReady = Signal("QVariantMap")     # the assistant did what was asked (or says why not)
    assistantProgress = Signal("QVariantMap")  # what the assistant is doing right now, in a few words: {text}
    formNoticed = Signal("QVariantMap")        # the tab in front looks like the form of a tracked job (only when that is turned on)
    formWatched = Signal("QVariantMap")        # where the form in Chrome stands now (asked while the assistant's window waits)

    def __init__(self, quiet: bool = False) -> None:
        """`quiet`: asks Claude nothing and gives no reminder (the window check of a built app)."""
        super().__init__()
        self._quiet = quiet
        self._api = Api()
        self._running = False
        self._sign_in = None                    # (when, answer) of the last signed-in connection check, for run starts
        self._sign_ins = 0                      # how many times Sign in was pressed: a check from before one is not kept
        self._cv_choosing = threading.Lock()    # one master CV is read and set at a time
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._paused = False
        self._can_resume = False
        self._partial = None                 # jobs of the run in progress, saved when it pauses
        self._outbox: queue.Queue = queue.Queue()
        self._warming = threading.Lock()     # held while Insights is being prepared in the background
        config.apply_ui_settings()

    # ── running state (QML-bindable) ────────────────────────────
    def _is_running(self) -> bool:
        return self._running

    running = Property(bool, _is_running, notify=runningChanged)

    def _set_running(self, val: bool) -> None:
        if not val:
            self._api.live = None                # the run is over: hand edits go straight to disk again
            if getattr(self, "_holds_jobs", False):
                store.RunLock.release()           # the job list is free for the weekly run again
                self._holds_jobs = False
        self._running = val
        self.runningChanged.emit(val)

    # ── reads (delegate to the shared Api) ──────────────────────
    @Slot(result="QVariantMap")
    def counts(self):
        return self._api.counts()

    @Slot(result="QVariantMap")
    def usageInfo(self):
        return self._api.usage_info()

    @Slot(result="QVariantList")
    def leads(self):
        return self._api.leads()

    @Slot(result="QVariantList")
    def applications(self):
        return self._api.applications()

    @Slot(result="QVariantList")
    def responses(self):
        return self._api.responses()

    @Slot(result="QVariantMap")
    def analytics(self):
        return self._api.analytics()

    @Slot(result="QVariantMap")
    def lastRun(self):
        return self._api.last_run()

    @Slot(result="QVariantMap")
    def options(self):
        return self._api.options()

    @Slot("QVariantList", result="QVariantMap")
    def professionFields(self, wanted):
        try:
            return self._api.profession_fields(list(wanted or []))
        except Exception:  # noqa: BLE001 - a line of explanation must never break Options
            return {"fields": [], "from_cv": False, "all": []}

    @Slot(result="QVariantList")
    def sourceKinds(self):
        """The kinds of job source Options lets you tick: [{key, name}] (job_sources.SourceChoice)."""
        from . import job_sources
        return job_sources.SourceChoice.offered()

    @Slot(str, result=bool)
    def knownRole(self, text):
        """True if a search role names a profession the app knows (any of them, not only software), or shares a word
        with the role words (prefilter.looks_like_role): the one check of a typed role."""
        from . import prefilter
        return bool(prefilter.fields_of([str(text or "")])) or prefilter.looks_like_role(str(text or ""))

    # ── the back end's own checks, asked by the window so it never keeps a copy (#61) ──
    @Slot(str, result=str)
    def addressProblem(self, text):
        """'' or what is wrong with a typed email address."""
        return _address_problem(text)

    @Slot(str, str, str, result=str)
    def passwordProblem(self, address, host, password):
        """'' or what is wrong with a typed mail password, before any server is asked (mailhosts.password_problem)."""
        from . import mailhosts
        return mailhosts.password_problem(address, host, password)

    @Slot(str, result=bool)
    def hasNonLatin(self, text):
        """Whether a text has letters of another alphabet than the Latin one (textfmt.has_non_latin)."""
        from . import textfmt
        return textfmt.has_non_latin(text)

    @Slot(str, result=str)
    def cityShown(self, name):
        """A city as the window shows it, in English where it was saved in its own language (places.city_shown)."""
        from . import places
        return places.city_shown(name)

    @Slot(result="QVariantMap")
    def aboutYou(self):
        """The About you window's values and what the app says about them (OptionsService.about_you)."""
        return self._api.about_you()

    @Slot("QVariantMap", result="QVariantMap")
    def saveAboutYou(self, data):
        result = self._api.save_about_you(dict(data or {}))
        if result.get("ok"):
            config.apply_ui_settings()
        return result

    @Slot(str, result="QVariantMap")
    def startPreview(self, text):
        return self._api.start_preview(text)

    @Slot(str, int, "QVariantList", result="QVariantMap")
    def payFault(self, role, amount, others):
        """{msg, box} for a line of "A different figure for": which box the fault is about (OptionsService.pay_fault)."""
        return self._api.pay_fault(role, int(amount), list(others or []))

    @Slot(str, int, "QVariantList", result=str)
    def payProblem(self, role, amount, others):
        """'' or what is wrong with a line of "A different figure for" (OptionsService.pay_problem)."""
        return self._api.pay_problem(role, int(amount), list(others or []))

    @Slot(str, result=str)
    def payKey(self, role):
        """When two kinds of role are the same line (OptionsService.pay_key)."""
        return self._api.pay_key(role)

    @Slot(float, str, result=int)
    def ownFigure(self, estimate_czk, currency):
        """An estimate in crowns as your own figure in the chosen currency (OptionsService.own_figure)."""
        return self._api.own_figure(estimate_czk, currency)

    @Slot("QVariantList", str, result=int)
    def workNotesSize(self, jobs, general):
        """How long the notes are as the app reads them (WorkNotes.size)."""
        return self._api.work_notes_size([dict(j) for j in (jobs or []) if isinstance(j, dict)], general)

    @Slot("QVariantMap", result="QVariantMap")
    def saveOptions(self, opts):
        result = self._api.save_options(dict(opts or {}))
        if result.get("ok"):
            config.apply_ui_settings()
        return result

    @Slot(result="QVariantList")
    def companies(self):
        return self._api.companies()

    @staticmethod
    def _company_rows(companies):
        """The window's list of career sites as plain dicts; a row that cannot be read is kept as a name, so the check
        names it as not saved instead of dropping it silently."""
        clean = []
        for c in (companies or []):
            try:
                clean.append(c if isinstance(c, dict) else {"name": c["name"], "ats": c["ats"], "token": c["token"]})
            except Exception:  # noqa: BLE001 - a row that cannot be read is named as not saved, never dropped silently
                clean.append({"name": str(c)[:40]})
        return clean

    @Slot("QVariantList", result="QVariantMap")
    def saveCompanies(self, companies):
        return self._api.save_companies(self._company_rows(companies))

    @Slot("QVariantList", result=str)
    def companiesProblem(self, companies):
        """'' or why the career sites would not all be saved, with nothing written (#67: Options asks before it saves)."""
        return self._api.companies_problem(self._company_rows(companies))

    # ── actions ─────────────────────────────────────────────────
    @Slot(str, result=bool)
    def applyJob(self, job_id):
        return bool(self._api.apply_job(job_id).get("ok"))

    @Slot(str, str, result="QVariantMap")
    def openDoc(self, kind, name):
        return self._api.open_doc(kind, name)

    @Slot(str, result="QVariantMap")
    def openExcel(self, which):
        return self._api.open_excel(which)

    @Slot(str, result="QVariantMap")
    def openUrl(self, job_id):
        return self._api.open_url(job_id)

    # ── connection management (write to the right places) ───────
    @Slot(str, result=bool)
    def chooseMasterCV(self, path):
        """Make a chosen file the master CV off the window's thread: reading a large PDF to check it can take seconds
        (#67). The answer arrives as cvSet. False, and nothing started, while a CV chosen before is still being read:
        two at once would leave the master to whichever ends last."""
        if not self._cv_choosing.acquire(blocking=False):
            return False

        def work():                          # an answer always comes, and the lock always goes, whatever happens
            result = {"ok": False, "msg": "Couldn't set that file as your CV."}
            try:
                result = self._set_master_cv(path)
            finally:
                try:
                    self._post("cvSet", result)
                finally:
                    self._cv_choosing.release()
        try:
            threading.Thread(target=work, daemon=True).start()
        except BaseException:
            self._cv_choosing.release()      # no thread: nothing is reading, so the next choice is taken
            raise
        return True

    def _set_master_cv(self, path):
        """Copy a chosen CV file into data/cv/ as the master CV, after checking it can be read ({ok, name} or {ok, msg})."""
        try:
            p = path
            if p.startswith("file://"):
                p = unquote(urlparse(p).path)
            src = Path(p)
            if not src.exists():
                return {"ok": False, "msg": "File not found."}
            from . import agent1_cv, vault
            problem = agent1_cv.cv_file_problem(src)
            if problem:
                return {"ok": False, "msg": problem}
            config.ensure_dirs()
            dest = config.CV_DIR / src.name
            # picking the CV that's already the master → no-op success (avoids
            # a SameFileError leaking its raw PosixPath repr into the UI)
            if src.resolve() != dest.resolve():
                if dest.exists():
                    vault.keep_copy(dest, "cv_versions")      # a CV of the same name is kept, never written over unseen
                shutil.copy2(src, dest)
            agent1_cv.remember_cv(dest.name)      # this one is the master, even if another CV in the folder sorts before it
            integrity.approve(["master_cv"])      # chosen through the app: trusted
            return {"ok": True, "name": src.name}
        except Exception as e:  # noqa: BLE001 - said in words; its kind goes to the log of problems (it runs in a thread)
            trouble.note("choosing the master CV", type(e).__name__)
            return {"ok": False, "msg": "Couldn't set that file as your CV."}

    @Slot(result="QVariantMap")
    def claudeLogin(self):
        """Open a Terminal running the Claude program's `auth login` so the user can complete
        the subscription sign-in (OAuth), then Recheck in the app."""
        if sys.platform != "darwin":
            return {"ok": False, "msg": "Signing in from the app works on a Mac only."}
        try:
            subprocess.Popen(ClaudeCli.of_the_sdk().login_script())
            self._sign_in, self._sign_ins = None, self._sign_ins + 1     # another account may come back: ask again
            return {"ok": True}
        except FileNotFoundError as e:
            return {"ok": False, "msg": str(e) if str(e) == claude_cli.MISSING else "Terminal could not be opened."}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": str(e)}

    def _busy_with_run(self, what):
        """The refusal of an action that asks Claude or changes the job list while a search or scan runs, or None (#79):
        the run would write its copy of the list over it, and both would spend the same Claude limit. The other way round
        (a run started while such an action is still busy) needs no refusal: the action's change goes through
        JobEditor.change, which also applies it to the run's own copy (`live`)."""
        return {"ok": False, "msg": f"A search or scan is running. {what} when it has finished."} if self._running else None

    def _recent_sign_in(self):
        """The last check's signed-in answer while it is younger than api_system.SIGN_IN_FRESH, else None: a run start
        then need not ask the Claude program on the window's thread (#80)."""
        seen = self._sign_in
        return seen[1] if seen and time.monotonic() - seen[0] < api_system.SIGN_IN_FRESH else None

    @Slot()
    def checkConnections(self):
        """Check Claude / email / CV off the UI thread (the Claude check runs
        the CLI), then emit connectionsReady so animations never stall."""
        round_ = self._sign_ins

        def work():
            try:
                info = self._api.connections()
            except Exception as e:  # noqa: BLE001 - nothing could be checked: Claude's sign-in is not known
                trouble.note("the connection check", e)
                info = {"claude_unsure": True, "claude_msg": api_system.UNSURE}
            if round_ == self._sign_ins:       # a sign-in started meanwhile: this answer may be of the old account
                self._sign_in = (time.monotonic(), {k: info.get(k) for k in api_system.SIGN_IN_KEYS}) \
                    if info.get("claude") is True else None
            # The start-up check too: it reads every job, which costs the window a frame or two. As text,
            # because an answer sent from another thread arrives only when its values are plain ones.
            try:
                info["health"] = json.dumps(self.selfCheckFor(info))
            except Exception as e:  # noqa: BLE001 - the window then runs the check itself
                trouble.note("the start-up check", e)
            self.connectionsReady.emit(info)
        threading.Thread(target=work, daemon=True).start()

    @Slot(result="QVariantList")
    def approveChanges(self):
        """Accept the current CV rules / letter rules / template / CV / career-site
        list as trusted, after the user has looked at what changed."""
        try:
            return integrity.approve()
        except Exception:  # noqa: BLE001
            return []

    @Slot(result="QVariantList")
    def whatChanged(self):
        """For each file changed outside the app: what was added and removed since it was approved."""
        try:
            return [integrity.what_changed(f["name"]) for f in integrity.problems() if f["state"] == "changed"]
        except Exception as e:  # noqa: BLE001 - the card then only names the files
            trouble.note("showing what changed in a watched file", e)
            return []

    # ── weekly schedule ─────────────────────────────────────────
    @Slot(result="QVariantMap")
    def weeklySchedule(self):
        return schedule.read_schedule()

    @Slot(bool, int, int, int, result="QVariantMap")
    def setWeeklySchedule(self, enabled, weekday, hour, minute):
        return schedule.write_schedule(bool(enabled), int(weekday), int(hour), int(minute))

    # ── usage refresh (a tiny ping fetches current rate-limit windows) ──
    @Slot()
    def warmUp(self):
        """Read every posting's keywords once, in the background, so the first Insights view opens at once.
        One at a time: a second request while the first is still reading is dropped."""
        if not self._warming.acquire(blocking=False):
            return

        def work():
            try:
                self._api.read_ahead()
            except Exception as e:  # noqa: BLE001 - only a head start; the view computes it itself if this failed
                trouble.note("preparing Insights in the background", e)
            finally:
                self._warming.release()
        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def refreshWidget(self):
        """Write the summary for the macOS widget, in the background (it reads the job list and the replies)."""
        threading.Thread(target=self._api.widget_update, daemon=True).start()

    @Slot()
    def refreshUsage(self):
        threading.Thread(target=self._ping_usage, daemon=True).start()

    def _ping_usage(self):
        from . import llm, usage
        if self._quiet:
            self.usageReady.emit()
            return
        try:
            if self._api.connections().get("claude") and not config.using_paid_api():
                llm.ask("ping", system="Reply with exactly: ok", tag="usage_ping", force=True)
        except llm.LimitReached:
            pass                                   # a used-up limit is what the card then shows, not a problem to note
        except Exception as e:  # noqa: BLE001 - the usage card keeps its last numbers
            trouble.note("asking Claude for the current usage", e)
        finally:
            usage.note_try()                       # an answer without the limits is not asked for again at once
            self.usageReady.emit()
