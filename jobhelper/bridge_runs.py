"""The Qt bridge, part: the long runs. Starting a search, an email scan or a scoring-again run,
stopping one, pausing on Claude's limit and resuming, and the workers themselves, which report
through signals."""
from __future__ import annotations

import imaplib
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMetaObject, Qt, Slot

from . import (agent1_cv, agent2_search, agent3_letters, agent4_tracker, agent5_responses, config, letters, notify, store, trouble, usage)


class RunCancelled(BaseException):
    """The user pressed Stop; raised at the next safe point between two steps.

    Not an ordinary error: the agents catch `Exception` around each job or email ("could not score this one, go on"), and a
    Stop pressed while a run waits on Claude's limit is raised from inside such a step. As an ordinary error it was taken
    for a failed job (and cost that job one of its two tries at documents) and the run went on to the next one."""


class RunSlots:
    """Mixed into `qt_bridge.Bridge`; uses its signals, `_api`, `_set_running` and the run's own state."""

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
        return self._start_scan(None)

    @Slot(int, result="QVariantMap")
    def scanEmailBack(self, days):
        """One scan over a longer period than Options says; the saved setting stays as it is."""
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
            return {"ok": False, "msg": "Choose between 1 and 365 days to look back."}
        return self._start_scan(days)

    def _start_scan(self, days):
        if self._running:
            return {"ok": False, "msg": "A search or scan is running. Start this one when it has finished."}
        if not config.has_imap():
            return {"ok": False, "msg": "Set up your job email first (open Account).", "fix": "email"}
        self._stop.clear()
        self._resume.clear()
        self._partial = None
        self._set_running(True)
        threading.Thread(target=self._scan, args=(days,), daemon=True).start()
        return {"ok": True}

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

    @Slot(str)
    def writeDocuments(self, job_id):
        """Write the CV and the letter of one job in the background; the answer arrives as docsReady."""
        def work():
            try:
                result = self._api.write_documents(job_id)
            except Exception as e:  # noqa: BLE001 - the window must always get an answer
                trouble.note("writing the documents of one job", e)
                result = {"ok": False, "msg": str(e) or type(e).__name__}
            result["job_id"] = job_id
            self._post("docsReady", result)
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
            stale = sum(1 for j in jobs if self._api._stale_docs(j))
            if stale:
                text += " %d now below your limit still %s documents (marked in New Jobs)." % (stale, "has" if stale == 1 else "have")
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

    @staticmethod
    def _spent(before: float) -> float:
        """What the run that started at `before` would have cost through the paid API."""
        return round(max(0.0, usage.total_cost() - before), 2)

    def _checkpoint(self) -> None:
        if self._stop.is_set():
            raise RunCancelled()

    # ── pausing on Claude's limit ───────────────────────────────
    def _limit_state(self, message: str = "") -> dict:
        from . import llm
        status = usage.limit_status()
        resets = status.get("resets_at") or 0
        return {"paused": self._paused, "can_resume": self._can_resume,
                "window": {"five_hour": "5-hour", "seven_day": "7-day"}.get(status.get("window", ""), "usage"),
                "used": round(status.get("used", 0) * 100),
                "resets_at": datetime.fromtimestamp(resets).strftime("%H:%M") if resets else "",
                "resets_day": datetime.fromtimestamp(resets).strftime("%d %b") if resets else "",
                "message": message or llm.limit_message(status)}

    def _notify(self, message: str, subtitle: str = "") -> None:
        """A desktop notification, but only while the app is in the background -
        in front of you the status bar already says it."""
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QGuiApplication
            if QGuiApplication.instance() is not None and QGuiApplication.applicationState() == Qt.ApplicationActive:
                return
        except Exception:  # noqa: BLE001 - cannot tell whether the window is in front: send it
            pass
        notify.send(message, subtitle)

    def _on_limit(self, error) -> None:
        """Called by an agent when Claude's limit is used up. Saves what is done,
        tells the window, and waits here until the limit is back AND the user
        presses Resume (or Stop). The agent then repeats the step it was on."""
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
        except Exception as e:  # noqa: BLE001 - a sound is never worth stopping for
            trouble.note("playing the finished sound", e)

    def _tick(self, key: str, done: int, total: int) -> None:
        """Progress from an agent; also where a run can be stopped."""
        self._checkpoint()
        self.progressChanged.emit(key, int(done), int(total))

    # ── workers (emit signals; QML animates the robots live) ────
    def _pipeline(self, opts):
        jobs = None
        before = usage.total_cost()
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
            added, _ = store.upsert(jobs, found)
            added -= len(agent2_search.prune_duplicate_leads(jobs))     # same role already listed from another board
            # a posting whose text could not be read gets one more try before it is scored from its title
            added -= agent2_search.reread_missing(jobs, english_only=not o["all_languages"], dropped=dropped)["removed"]
            # postings that stopped accepting applications since they were found
            agent2_search.check_closed(jobs, dropped=dropped)
            agent2_search.save_dropped(dropped)
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
                               scored=stats.get("scored", 0), prefiltered=stats.get("prefiltered", 0),
                               cost=self._spent(before), cost_of="search")

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
            self._save_partial(jobs)                             # what was scored and written before the error is kept
            trouble.note("the search", e)
            self.runFinished.emit("search", "Error: %s" % agent2_search.safe_error(e))
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
        except Exception as e:  # noqa: BLE001 - Stop must still end the run
            trouble.note("saving what was finished before Stop", e)

    def _scan(self, days=None):
        jobs = None
        before = usage.total_cost()
        try:
            self.agentChanged.emit("a5", "running", "")
            self.logChanged.emit("Reading inbox (read-only)…")
            jobs = store.load_jobs()
            days = int(days or self._api.options().get("scan_days") or config.IMAP_LOOKBACK_DAYS)
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
            self._api.note_run(scan="%s · %d new" % (datetime.now().strftime("%d %b"), stats["new_responses"]),
                               scan_detail=agent5_responses.scan_detail(stats), cost=self._spent(before), cost_of="email scan")
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
            self.runFinished.emit("scan", "Couldn't sign in to your email — check its password in the Account card.")
        except RuntimeError as e:
            self._save_partial(jobs)
            self.runFinished.emit("scan", str(e))
        except Exception as e:  # noqa: BLE001
            self._save_partial(jobs)                             # statuses changed by the replies read so far are kept
            trouble.note("the email scan", e)
            self.runFinished.emit("scan", "Email scan failed — check your connection and try again.")
        finally:
            self._set_running(False)
