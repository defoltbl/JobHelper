"""Bridge between the Qt Quick (QML) front-end and the JobHelper backend.

The read methods delegate to the proven `ui_api.Api`; the long-running
pipeline / email scan run on a worker thread and report progress through Qt
**signals** (QML updates live — no polling needed).

Exposed to QML as the context property `bridge`.

`Bridge` is put together from parts: the runs (search, email scan, scoring again,
pausing on the limit, stopping) are in `bridge_runs`, everything the job windows
ask for is in `bridge_jobs`. Here: the signals, sign-in and connections, Options,
the weekly schedule and the usage card.
"""
from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

from PySide6.QtCore import Property, QObject, Signal, Slot

from .ui_api import Api
from .bridge_jobs import JobSlots
from .bridge_runs import RunSlots
from . import trouble  # noqa: I001
from . import (config, integrity, schedule)


class Bridge(RunSlots, JobSlots, QObject):
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

    @Slot("QVariantList", result="QVariantMap")
    def professionFields(self, wanted):
        try:
            return self._api.profession_fields(list(wanted or []))
        except Exception:  # noqa: BLE001 - a line of explanation must never break Options
            return {"fields": [], "from_cv": False, "all": []}

    @Slot(str, result=bool)
    def knownRole(self, text):
        """True if a search role names a profession the app knows (any of them, not only software)."""
        from . import prefilter
        return bool(prefilter.fields_of([str(text or "")]))

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
        except Exception as e:  # noqa: BLE001 - what could be read is saved
            trouble.note("reading the career-site list from the window", e)
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
            except Exception as e:  # noqa: BLE001 - only a head start; the view computes it itself if this failed
                trouble.note("preparing Insights in the background", e)
        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def refreshUsage(self):
        threading.Thread(target=self._ping_usage, daemon=True).start()

    def _ping_usage(self):
        try:
            from . import llm
            if self._api.connections().get("claude") and not config.using_paid_api():
                llm.ask("ping", system="Reply with exactly: ok", tag="usage_ping", force=True)
        except Exception as e:  # noqa: BLE001 - the usage card keeps its last numbers
            trouble.note("asking Claude for the current usage", e)
        finally:
            self.usageReady.emit()
