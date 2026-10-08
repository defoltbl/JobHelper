"""Bridge between the Qt Quick (QML) front-end and the JobHelper backend.

The read methods delegate to the proven `ui_api.Api`; the long-running
pipeline / email scan run on a worker thread and report progress through Qt
**signals** (QML updates live — no polling needed).

Exposed to QML as the context property `bridge`.
"""
from __future__ import annotations

import imaplib
import queue
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from PySide6.QtCore import Property, QMetaObject, QObject, Qt, Signal, Slot

from .ui_api import Api
from . import (agent1_cv, agent2_search, agent3_letters, agent4_tracker,
               agent5_responses, config, integrity, letters, notify, planner, schedule, store)


class RunCancelled(Exception):
    """The user pressed Stop; raised at the next safe point between two steps."""


class Bridge(QObject):
    # key in {a1..a5}, status in {running,done}, info text
    agentChanged = Signal(str, str, str)
    logChanged = Signal(str)
    runFinished = Signal(str, str)        # mode, summary
    runningChanged = Signal(bool)
    progressChanged = Signal(str, int, int)   # agent key, done, total (within its stage)
    usageReady = Signal()                 # fresh usage numbers are available
    connectionsReady = Signal("QVariantMap")   # result of checkConnections()
    limitChanged = Signal("QVariantMap")       # paused on Claude's limit / may resume / resumed
    paragraphReady = Signal("QVariantMap")     # a rewritten letter paragraph (or why it failed)
    prepReady = Signal("QVariantMap")          # interview preparation finished (or why it failed)
    replyReady = Signal("QVariantMap")         # a pasted reply was filed (or why not)
    answersReady = Signal("QVariantMap")       # answers for a job's form were drafted (or why not)
    rescoreReady = Signal("QVariantMap")       # one job was scored again (or why not)

    def __init__(self) -> None:
        super().__init__()
        self._api = Api()
        self._running = False
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._paused = False
        self._can_resume = False
        self._partial = None                 # jobs of the run in progress, saved when it pauses
        self._outbox: queue.Queue = queue.Queue()
        config.apply_ui_settings()

    # ── running state (QML-bindable) ────────────────────────────
    def _is_running(self) -> bool:
        return self._running

    running = Property(bool, _is_running, notify=runningChanged)

    def _set_running(self, val: bool) -> None:
        if not val:
            self._api.live = None                # the run is over: hand edits go straight to disk again
        self._running = val
        self.runningChanged.emit(val)

    # ── reads (delegate to the shared Api) ──────────────────────
    @Slot(result="QVariantMap")
    def connections(self):
        return self._api.connections()

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

    @Slot("QVariantMap")
    def saveOptions(self, opts):
        self._api.save_options(dict(opts or {}))
        config.apply_ui_settings()

    @Slot(result="QVariantList")
    def companies(self):
        return self._api.companies()

    @Slot("QVariantList")
    def saveCompanies(self, companies):
        clean = []
        try:
            for c in (companies or []):
                if isinstance(c, dict):
                    clean.append(c)
                else:  # tolerate odd item types from the bridge
                    clean.append({"name": c["name"], "ats": c["ats"], "token": c["token"]})
        except Exception:
            pass
        self._api.save_companies(clean)

    # ── actions ─────────────────────────────────────────────────
    @Slot(str, result=bool)
    def applyJob(self, job_id):
        return bool(self._api.apply_job(job_id).get("ok"))

    @Slot(str, str)
    def openDoc(self, kind, name):
        self._api.open_doc(kind, name)

    @Slot(str)
    def openExcel(self, which):
        self._api.open_excel(which)

    @Slot(str, result="QVariantMap")
    def openUrl(self, job_id):
        return self._api.open_url(job_id)

    # ── connection management (write to the right places) ───────
    @Slot(str, str, result="QVariantMap")
    def saveEmail(self, user, password):
        """Save Gmail IMAP email + app password to .env (password optional:
        blank keeps the current one)."""
        try:
            pwd = password.strip() or config.IMAP_PASSWORD
            config.set_imap(user.strip(), pwd)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": str(e)}

    @Slot(str, result="QVariantMap")
    def setMasterCV(self, path):
        """Copy a chosen CV file into data/cv/ as the master CV."""
        try:
            p = path
            if p.startswith("file://"):
                p = unquote(urlparse(p).path)
            src = Path(p)
            if not src.exists():
                return {"ok": False, "msg": "File not found."}
            if src.suffix.lower() not in (".docx", ".pdf", ".txt"):
                return {"ok": False, "msg": "Use a Word (.docx), PDF (.pdf) or .txt file."}
            config.ensure_dirs()
            dest = config.CV_DIR / src.name
            # picking the CV that's already the master → no-op success (avoids
            # a SameFileError leaking its raw PosixPath repr into the UI)
            if src.resolve() == dest.resolve():
                return {"ok": True, "name": src.name}
            shutil.copy2(src, dest)
            integrity.approve(["master_cv"])      # chosen through the app: trusted
            return {"ok": True, "name": src.name}
        except Exception:  # noqa: BLE001
            return {"ok": False, "msg": "Couldn't set that file as your CV."}

    @Slot(result="QVariantMap")
    def claudeLogin(self):
        """Open a Terminal running `claude auth login` so the user can complete
        the subscription sign-in (OAuth), then Recheck in the app."""
        try:
            if sys.platform == "darwin":
                subprocess.Popen([
                    "osascript",
                    "-e", 'tell application "Terminal" to activate',
                    "-e", 'tell application "Terminal" to do script "claude auth login"',
                ])
                return {"ok": True}
            return {"ok": False, "msg": "Run: claude auth login"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": str(e)}

    @Slot()
    def checkConnections(self):
        """Check Claude / email / CV off the UI thread (the Claude check runs
        the CLI), then emit connectionsReady so animations never stall."""
        def work():
            try:
                info = self._api.connections()
            except Exception:  # noqa: BLE001
                info = {}
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
        """Read every posting's keywords once, in the background, so the first Insights view opens at once."""
        def work():
            try:
                self._api.insights()
            except Exception:  # noqa: BLE001 - only a head start; the view computes it itself if this failed
                pass
        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def refreshUsage(self):
        threading.Thread(target=self._ping_usage, daemon=True).start()

    def _ping_usage(self):
        try:
            from . import llm
            if self._api.connections().get("claude") and not config.using_paid_api():
                llm.ask("ping", system="Reply with exactly: ok", tag="usage_ping", force=True)
        except Exception:
            pass
        finally:
            self.usageReady.emit()

    @Slot("QVariantMap", result="QVariantMap")
    def runSearch(self, opts):
        if self._running:
            return {"ok": False, "msg": "A run is already in progress."}
        conn = self._api.connections()
        if conn.get("paid_api"):
            return {"ok": False, "msg": "Unset ANTHROPIC_API_KEY to use your subscription."}
        if not conn.get("claude"):
            return {"ok": False, "msg": "Log in to Claude first (open Account).", "fix": "claude"}
        if not conn.get("cv"):
            return {"ok": False, "msg": "Add your CV first (open Account).", "fix": "cv"}
        if conn.get("vault") == "locked":
            return {"ok": False, "msg": "Your data is encrypted and its key is missing (open Account).", "fix": "vault"}
        if conn.get("changed_files"):
            return {"ok": False, "fix": "integrity",
                    "msg": "Changed outside the app: %s. Review and approve in Account." % ", ".join(conn["changed_files"])}
        chosen = dict(self._api.options(), **dict(opts or {}))
        if not str(chosen.get("where") or "").strip():
            return {"ok": False, "fix": "city", "msg": "Choose the city to search in first (Options)."}
        self._stop.clear()
        self._resume.clear()
        self._partial = None
        self._set_running(True)
        threading.Thread(target=self._pipeline, args=(dict(opts or {}),), daemon=True).start()
        return {"ok": True}

    @Slot(result="QVariantMap")
    def scanEmail(self):
        if self._running:
            return {"ok": False, "msg": "A run is already in progress."}
        if not config.has_imap():
            return {"ok": False, "msg": "Set up your job email first (open Account).", "fix": "email"}
        self._stop.clear()
        self._resume.clear()
        self._partial = None
        self._set_running(True)
        threading.Thread(target=self._scan, daemon=True).start()
        return {"ok": True}

    @Slot(result="QVariantMap")
    def rescorePlan(self):
        return self._api.rescore_plan()

    @Slot(str)
    def rescoreJob(self, job_id):
        """Score one job again in the background (one Claude call); the answer arrives as rescoreReady."""
        def work():
            try:
                result = self._api.rescore_one(job_id)
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                result = {"ok": False, "msg": str(e) or type(e).__name__}
            result["job_id"] = job_id
            self._post("rescoreReady", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot(result="QVariantMap")
    def rescoreAll(self):
        """Score every new job that has a score again, as a run: it shows progress, can be stopped,
        and pauses on the limit like a search."""
        if self._running:
            return {"ok": False, "msg": "A run is already in progress."}
        conn = self._api.connections()
        if conn.get("paid_api"):
            return {"ok": False, "msg": "Unset ANTHROPIC_API_KEY to use your subscription."}
        if not conn.get("claude"):
            return {"ok": False, "msg": "Log in to Claude first (open Account).", "fix": "claude"}
        if not self._api.rescore_ids():
            return {"ok": False, "msg": "There are no scored new jobs to score again."}
        self._stop.clear()
        self._resume.clear()
        self._partial = None
        self._set_running(True)
        threading.Thread(target=self._rescore, daemon=True).start()
        return {"ok": True}

    def _rescore(self):
        jobs = None
        try:
            self.agentChanged.emit("a3", "running", "")
            profile = agent1_cv.load_profile() or {}
            jobs = self._partial = self._api.live = store.load_jobs()
            ids = [j["id"] for j in jobs if j.get("status") in store.LEAD_STATUSES and j.get("match_score") is not None]
            self.logChanged.emit("Scoring %d new jobs again…" % len(ids))

            def tick(done, total):
                self._checkpoint()                              # Stop is honoured between calls
                self._tick("a3", done, total)
            stats = agent3_letters.rescore(jobs, ids, profile, self._api._cv_text(), progress=tick,
                                           on_limit=self._on_limit, status=self.logChanged.emit)
            store.save_jobs(jobs)
            agent4_tracker.render_all(jobs)
            changed = stats["changed"]
            lower = sum(1 for c in changed if (c["before"] or 0) > c["after"])
            self.agentChanged.emit("a3", "done", "%d rescored" % stats["scored"])
            text = "Scored %d jobs again: %d changed (%d lower, %d higher)." % (stats["scored"], len(changed), lower, len(changed) - lower)
            if stats["failed"]:
                text += " %d could not be scored and keep their old score." % stats["failed"]
            self.runFinished.emit("rescore", text)
            self._notify(text, "Scoring finished")
        except RunCancelled:
            self._save_partial(jobs)
            self.runFinished.emit("rescore", "Stopped. The jobs scored before that keep their new score.")
        except Exception as e:  # noqa: BLE001
            self._save_partial(jobs)
            self.runFinished.emit("rescore", "Couldn't finish scoring again: %s" % (str(e) or type(e).__name__))
        finally:
            self._api.live = None
            self._set_running(False)

    # ── answers from short background jobs ──────────────────────
    def _post(self, signal_name: str, payload: dict) -> None:
        """Hand a result from a worker thread to the window. The signal is emitted
        on the UI thread (the worker only queues it), which is the one way that
        is reliable for a short-lived thread."""
        self._outbox.put((signal_name, payload))
        QMetaObject.invokeMethod(self, "_drain", Qt.QueuedConnection)

    @Slot()
    def _drain(self):
        while True:
            try:
                signal_name, payload = self._outbox.get_nowait()
            except queue.Empty:
                return
            getattr(self, signal_name).emit(payload)

    # ── stopping a run ──────────────────────────────────────────
    @Slot(result=bool)
    def stopRun(self):
        """Ask the running job to stop. It ends after the step it is on (one
        search request, one job, one email), and what is finished is saved."""
        if not self._running:
            return False
        self._stop.set()
        self._resume.set()                   # wake a paused run so it can end
        self.logChanged.emit("Stopping after the current step…")
        return True

    def _checkpoint(self) -> None:
        if self._stop.is_set():
            raise RunCancelled()

    # ── pausing on Claude's limit ───────────────────────────────
    def _limit_state(self, message: str = "") -> dict:
        from . import llm, usage
        status = usage.limit_status()
        resets = status.get("resets_at") or 0
        return {"paused": self._paused, "can_resume": self._can_resume,
                "window": {"five_hour": "5-hour", "seven_day": "7-day"}.get(status.get("window", ""), "usage"),
                "used": round(status.get("used", 0) * 100),
                "resets_at": datetime.fromtimestamp(resets).strftime("%H:%M") if resets else "",
                "resets_day": datetime.fromtimestamp(resets).strftime("%d %b") if resets else "",
                "message": message or llm.limit_message(status)}

    @Slot(result="QVariantMap")
    def limitInfo(self):
        return self._limit_state()

    def _notify(self, message: str, subtitle: str = "") -> None:
        """A desktop notification, but only while the app is in the background -
        in front of you the status bar already says it."""
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QGuiApplication
            if QGuiApplication.instance() is not None and QGuiApplication.applicationState() == Qt.ApplicationActive:
                return
        except Exception:  # noqa: BLE001
            pass
        notify.send(message, subtitle)

    def _on_limit(self, error) -> None:
        """Called by an agent when Claude's limit is used up. Saves what is done,
        tells the window, and waits here until the limit is back AND the user
        presses Resume (or Stop). The agent then repeats the step it was on."""
        from . import usage
        self._save_partial(self._partial)
        self._paused, self._can_resume = True, False
        self._resume.clear()
        self.logChanged.emit("Paused: %s Everything done so far is saved." % error)
        self._notify(notify.PAUSED + " The run continues when you press Resume.", "Run paused")
        self.limitChanged.emit(self._limit_state(str(error)))
        try:
            while True:
                woke = self._resume.wait(timeout=self.LIMIT_POLL_SECONDS)
                self._checkpoint()                               # Stop pressed while paused
                free = not usage.limit_status()["blocked"]
                if free and not self._can_resume:
                    self._can_resume = True
                    self.logChanged.emit("The limit is back. Press Resume to continue.")
                    self._notify(notify.RESUME, "Ready to resume")
                    self.limitChanged.emit(self._limit_state(str(error)))
                elif not free and self._can_resume:
                    self._can_resume = False
                    self.limitChanged.emit(self._limit_state(str(error)))
                if woke:
                    self._resume.clear()
                    if free:
                        break
        finally:
            self._paused = self._can_resume = False
            self.limitChanged.emit(self._limit_state())
        self.logChanged.emit("Resumed.")

    LIMIT_POLL_SECONDS = 20.0

    @Slot(result=bool)
    def resumeRun(self):
        """Continue a paused run. Only works once the limit has reset."""
        if not (self._running and self._paused and self._can_resume):
            return False
        self._resume.set()
        return True

    def _with_limit(self, call):
        """Run a step that asks Claude outside the agents' own loops."""
        from . import llm
        while True:
            try:
                return call()
            except llm.LimitReached as e:
                self._on_limit(e)

    @Slot()
    def playAlert(self):
        """The limit warning sound (the app's own short three-tone alert)."""
        sound = Path(__file__).resolve().parent.parent / "ui_qt" / "sounds" / "limit.wav"
        try:
            if sys.platform == "darwin" and sound.is_file():
                subprocess.Popen(["afplay", str(sound)])
            else:
                from PySide6.QtGui import QGuiApplication
                QGuiApplication.beep()
        except Exception:  # noqa: BLE001
            pass

    def _tick(self, key: str, done: int, total: int) -> None:
        """Progress from an agent; also where a run can be stopped."""
        self._checkpoint()
        self.progressChanged.emit(key, int(done), int(total))

    # ── job detail and follow-ups ───────────────────────────────
    @Slot(str, result="QVariantMap")
    def jobDetail(self, job_id):
        return self._api.job_detail(job_id)

    @Slot(str, result="QVariantMap")
    def followupDraft(self, job_id):
        return self._api.followup_draft(job_id)

    @Slot(str, str, result="QVariantMap")
    def setStatus(self, job_id, status):
        return self._api.set_status(job_id, status)

    @Slot(str, str, result="QVariantMap")
    def setApplyDate(self, job_id, text):
        return self._api.set_apply_date(job_id, text)

    @Slot(str, result="QVariantMap")
    def scoreAnyway(self, job_id):
        return self._api.score_anyway(job_id)

    @Slot(str, str, result="QVariantMap")
    def mergeJobs(self, keep_id, drop_id):
        return self._api.merge_jobs(keep_id, drop_id)

    @Slot(str, str, result="QVariantMap")
    def keepSeparate(self, a_id, b_id):
        return self._api.keep_separate(a_id, b_id)

    @Slot(str, str, result="QVariantMap")
    def saveEmail2(self, user, password):
        """Add or change the optional second mailbox (blank password keeps the current one)."""
        try:
            if user.strip().lower() == config.IMAP_USER.lower():
                return {"ok": False, "msg": "That is already your main job email."}
            config.set_imap2(user.strip(), password.strip() or config.IMAP_PASSWORD_2)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": str(e)}

    @Slot(result="QVariantMap")
    def removeEmail2(self):
        try:
            config.remove_imap2()
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": str(e)}

    @Slot(str, str, str, str, str, result="QVariantMap")
    def setEvent(self, job_id, day, time_text, kind, note):
        return self._api.set_event(job_id, day, time_text, kind, note)

    @Slot(str, result="QVariantMap")
    def clearEvent(self, job_id):
        return self._api.clear_event(job_id)

    @Slot(result="QVariantList")
    def upcoming(self):
        return self._api.upcoming(4)

    @Slot(result=int)
    def remind(self):
        """Announce dates that are tomorrow or today (once per day each). Returns how many."""
        due = self._api.due_reminders()
        for item in due:
            notify.send(planner.reminder_text(item), "Reminder")
        return len(due)

    @Slot(str, "QVariantMap", result="QVariantMap")
    def saveCompanyNotes(self, company, fields):
        return self._api.save_company_notes(company, dict(fields or {}))

    @Slot(str, str)
    def addReply(self, job_id, text):
        """Runs in the background (it may ask Claude); the answer arrives as replyReady."""
        def work():
            try:
                result = self._api.add_reply(job_id, text)
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                result = {"ok": False, "msg": str(e) or type(e).__name__}
            result["job_id"] = job_id
            self._post("replyReady", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot(result="QVariantMap")
    def myLetters(self):
        return self._api.my_letters()

    @Slot(result="QVariantMap")
    def openMyLetters(self):
        return self._api.open_my_letters()

    @Slot(str, str, result="QVariantMap")
    def showInFolder(self, kind, job_id):
        return self._api.show_in_folder(kind, job_id)

    @Slot(str, str, result="QVariantMap")
    def applyStep(self, job_id, step):
        return self._api.apply_step(job_id, step)

    @Slot(str, result="QVariantMap")
    def combinedPdf(self, job_id):
        return self._api.combined_pdf(job_id)

    @Slot(str, result="QVariantMap")
    def exportEvent(self, job_id):
        return self._api.export_event(job_id)

    @Slot(str, result="QVariantMap")
    def thanksDraft(self, job_id):
        return self._api.thanks_draft(job_id)

    @Slot(str, result=bool)
    def markThanked(self, job_id):
        return self._api.mark_thanked(job_id)

    @Slot(str, result="QVariantMap")
    def formAnswers(self, job_id):
        return self._api.form_answers(job_id)

    @Slot(str, result="QVariantMap")
    def checkQuestions(self, questions_text):
        return self._api.check_questions(questions_text)

    @Slot(str, str)
    def draftAnswers(self, job_id, questions_text):
        """Runs in the background (it asks Claude); the answer arrives as answersReady."""
        def work():
            try:
                result = self._api.make_form_answers(job_id, questions_text)
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                result = {"ok": False, "msg": str(e) or type(e).__name__}
            result["job_id"] = job_id
            self._post("answersReady", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, "QVariantList", result="QVariantMap")
    def saveFormAnswers(self, job_id, items):
        return self._api.save_form_answers(job_id, [dict(i) for i in (items or [])])

    @Slot(result="QVariantMap")
    def weekSummary(self):
        return self._api.week_summary()

    @Slot(bool, result="QVariantMap")
    def selfCheck(self, claude_signed_in):
        """The start-up check; the window passes what its connection check found about Claude."""
        return self._api.self_check(bool(claude_signed_in))

    @Slot(result="QVariantList")
    def changelog(self):
        return self._api.changelog()

    @Slot(result="QVariantMap")
    def filteredOut(self):
        return self._api.filtered_out()

    @Slot(int, result="QVariantMap")
    def bringBack(self, index):
        return self._api.bring_back(index)

    @Slot(int, result="QVariantMap")
    def openFiltered(self, index):
        return self._api.open_filtered(index)

    @Slot(str, result="QVariantMap")
    def cvCompare(self, job_id):
        return self._api.cv_compare(job_id)

    @Slot(str, result="QVariantMap")
    def interviewPrep(self, job_id):
        return self._api.interview_prep(job_id)

    @Slot(str)
    def prepareInterview(self, job_id):
        """Runs in the background (it asks Claude); the answer arrives as prepReady."""
        def work():
            try:
                result = self._api.make_interview_prep(job_id)
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                result = {"ok": False, "msg": str(e) or type(e).__name__}
            result["job_id"] = job_id
            self._post("prepReady", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, result="QVariantMap")
    def prepParts(self, job_id):
        return self._api.prep_parts(job_id)

    @Slot(str, "QVariantList", result="QVariantMap")
    def savePrepParts(self, job_id, parts):
        return self._api.save_prep_parts(job_id, [dict(p) for p in (parts or [])])

    @Slot(str, bool, result="QVariantMap")
    def prepDocument(self, job_id, reveal):
        return self._api.prep_document(job_id, bool(reveal))

    @Slot(str, result=str)
    def prepText(self, job_id):
        return self._api.prep_text(job_id)

    @Slot(result="QVariantMap")
    def insights(self):
        return self._api.insights()

    @Slot(str, result="QVariantMap")
    def dismissJob(self, job_id):
        return self._api.dismiss_job(job_id)

    @Slot(str, result="QVariantMap")
    def restoreJob(self, job_id):
        return self._api.restore_job(job_id)

    @Slot(result="QVariantList")
    def dismissedLeads(self):
        return self._api.dismissed()

    @Slot(str, result="QVariantMap")
    def letterForEdit(self, job_id):
        return self._api.letter_for_edit(job_id)

    @Slot(str, "QVariantList", result="QVariantMap")
    def saveLetter(self, job_id, paragraphs):
        return self._api.save_letter(job_id, [str(p) for p in (paragraphs or [])])

    @Slot(str, "QVariantList", int, str)
    def rewriteParagraph(self, job_id, paragraphs, index, hint):
        """Runs in the background (it asks Claude); the answer arrives as paragraphReady."""
        texts = [str(p) for p in (paragraphs or [])]

        def work():
            try:
                result = self._api.rewrite_paragraph(job_id, texts, index, hint)
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                result = {"ok": False, "msg": str(e) or type(e).__name__}
            result.setdefault("index", int(index))
            result["job_id"] = job_id
            self._post("paragraphReady", result)
        threading.Thread(target=work, daemon=True).start()

    @Slot(str, result="QVariantMap")
    def responseDetail(self, msg_id):
        return self._api.response_detail(msg_id)

    @Slot(str, result=bool)
    def markFollowedUp(self, job_id):
        return bool(self._api.mark_followed_up(job_id).get("ok"))

    @Slot(str, result=bool)
    def copyText(self, text):
        """Put text on the clipboard (the follow-up draft). Nothing is sent anywhere."""
        from PySide6.QtGui import QGuiApplication
        board = QGuiApplication.clipboard()
        if board is None:
            return False
        board.setText(text or "")
        return True

    # ── workers (emit signals; QML animates the robots live) ────
    def _pipeline(self, opts):
        jobs = None
        try:
            o = self._api.options()
            o.update(opts or {})

            self.agentChanged.emit("a1", "running", "")
            self.logChanged.emit("Reading your CV…")
            profile = agent1_cv.load_profile(current_only=True)     # re-read after the CV was changed
            if profile is None:
                profile = self._with_limit(agent1_cv.analyze)
            seniority = profile.get("seniority", "junior")
            self.agentChanged.emit("a1", "done", seniority)

            jobs = self._partial = self._api.live = store.load_jobs()
            agent2_search.prune_applied_leads(jobs)
            self._checkpoint()

            self.agentChanged.emit("a2", "running", "")
            self.logChanged.emit("Searching jobs in " + str(o["where"]) + "…")
            # User-defined keywords (from Options) take priority over the CV-derived ones.
            queries = (o.get("queries") or profile.get("search_queries")
                       or profile.get("target_roles") or [])
            kw = dict(where=o["where"], per_query=int(o["per_query"]),
                      english_only=not o["all_languages"], candidate_seniority=seniority,
                      max_age_days=int(o["max_age_days"]),
                      full_time_only=o.get("full_time_only", True) is not False,
                      skip_words=list(o.get("skip_words") or []), keep_words=list(o.get("keep_words") or []),
                      level_words=list(o.get("level_words") or []), max_years=int(o.get("max_years") or 0))
            remote_too = bool(o.get("include_remote")) and o["source"] not in ("remote", "all")
            # two passes share one bar: the main sources fill most of it, remote the rest
            share = 0.85 if remote_too else 1.0
            dropped = []                                     # what the filters remove, with the reason
            kw["dropped"] = dropped
            found = agent2_search.search(
                queries, source=o["source"],
                progress=lambda d, t: self._tick("a2", int(d * share * 100), max(1, t * 100)), **kw)
            if remote_too:
                found += agent2_search.search(
                    queries, source="remote",
                    progress=lambda d, t: self._tick(
                        "a2", int((share + (1 - share) * d / max(1, t)) * 1000), 1000), **kw)
            found, _ = agent2_search.drop_known_applications(found, jobs, dropped=dropped)
            agent2_search.save_dropped(dropped)
            added, _ = store.upsert(jobs, found)
            added -= len(agent2_search.prune_duplicate_leads(jobs))     # same role already listed from another board
            store.save_jobs(jobs)
            self.agentChanged.emit("a2", "done", "+%d new" % added)

            letters.import_letters(jobs)
            store.save_jobs(jobs)

            self._checkpoint()
            self.agentChanged.emit("a3", "running", "")
            self.logChanged.emit("Scoring jobs and writing letters + CVs…")
            cv_path = agent1_cv.find_cv()
            cv_text = agent1_cv.read_cv_text(cv_path) if cv_path else ""
            stats = agent3_letters.process(jobs, profile, threshold=int(o["threshold"]),
                                           cv_text=cv_text, cv_path=cv_path,
                                           progress=lambda d, t: self._tick("a3", d, t),
                                           on_limit=self._on_limit, status=self.logChanged.emit)
            store.save_jobs(jobs)
            documents = "%d letters · %d CVs" % (stats["letters"], stats.get("tailored_cvs", 0))
            self.agentChanged.emit("a3", "done", documents)
            self._api.note_run(when=datetime.now().strftime("%d %b %H:%M"), found="+%d new" % added, filtered=len(dropped),
                               letters=stats["letters"], cvs=stats.get("tailored_cvs", 0),
                               scored=stats.get("scored", 0), prefiltered=stats.get("prefiltered", 0))

            self.agentChanged.emit("a4", "running", "")
            self.logChanged.emit("Building the tracker…")
            agent5_responses.annotate_progress(jobs)
            agent4_tracker.render_all(jobs)
            leads = sum(1 for j in jobs if j["status"] in store.LEAD_STATUSES)
            self.agentChanged.emit("a4", "done", "%d leads" % leads)

            self.runFinished.emit("search",
                                  "Done · +%d new jobs, %d letters + CVs ready." % (added, stats["letters"]))
            self._notify(notify.search_text(added, stats["letters"]), "Search finished")
        except RunCancelled:
            self._save_partial(jobs)
            self.runFinished.emit("search", "Stopped. Everything finished before that is saved.")
        except Exception as e:  # noqa: BLE001
            self.runFinished.emit("search", "Error: %s" % e)
            self._notify(notify.FAILED, "Search stopped")
        finally:
            self._set_running(False)

    def _save_partial(self, jobs) -> None:
        """After Stop: keep what the agents already finished."""
        if jobs is None:
            return
        try:
            store.save_jobs(jobs)
            agent4_tracker.render_all(jobs)
        except Exception:  # noqa: BLE001
            pass

    def _scan(self):
        jobs = None
        try:
            self.agentChanged.emit("a5", "running", "")
            self.logChanged.emit("Reading inbox (read-only)…")
            jobs = store.load_jobs()
            days = int(self._api.options().get("scan_days") or config.IMAP_LOOKBACK_DAYS)
            self.logChanged.emit("Reading inbox (read-only), last %d days…" % days)
            self._partial = self._api.live = jobs
            stats = agent5_responses.process_inbox(jobs, lookback_days=days,
                                                   progress=lambda d, t: self._tick("a5", d, t),
                                                   on_limit=self._on_limit)
            agent5_responses.backfill_roles(jobs)
            agent5_responses.annotate_progress(jobs)
            agent2_search.prune_applied_leads(jobs)
            store.save_jobs(jobs)
            agent4_tracker.render_all(jobs)
            agent5_responses.build_report(jobs)
            self.agentChanged.emit("a5", "done", "%d new" % stats["new_responses"])
            self._api.note_run(scan="%s · %d new" % (datetime.now().strftime("%d %b"), stats["new_responses"]))
            from . import email_client
            warning = (" " + " ".join(email_client.last_warnings)) if email_client.last_warnings else ""
            self.runFinished.emit("scan", agent5_responses.scan_summary(stats) + warning)
            invites = notify.invites_text(stats.get("invites") or [])
            if invites:
                notify.send(invites + ". Open JobHelper to prepare for it.", "Interview invitation")   # worth an alert even with the app in front
            else:
                self._notify(agent5_responses.replies_text(stats), "Email scan finished")
        except RunCancelled:
            self._save_partial(jobs)
            self.runFinished.emit("scan", "Stopped. Emails read before that are saved.")
        except imaplib.IMAP4.error:
            self.runFinished.emit("scan", "Couldn't sign in to your email — check the Gmail App Password in the Account card.")
        except RuntimeError as e:
            self.runFinished.emit("scan", str(e))
        except Exception:  # noqa: BLE001
            self.runFinished.emit("scan", "Email scan failed — check your connection and try again.")
        finally:
            self._set_running(False)
