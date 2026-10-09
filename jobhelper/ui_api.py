"""Data access for the desktop app.

Plain read/write helpers over the JobHelper data (jobs, responses, options,
career-site list) plus small actions (mark applied, open a file or link). The Qt
bridge (`qt_bridge.Bridge`) exposes these to the QML window and runs the long
jobs itself.
"""
from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta

from . import (agent1_cv, agent2_search, agent3_letters, agent4_tracker, agent5_responses, cv_tailor, filters, form_answers, health, prep_doc, summary, textfmt,
               compare, config, cover_letter, db, followup, housekeeping, insights, integrity, interview_prep, keywords, merge, pdf,
               planner, salary, store, usage, vault)


def _guarded(default):
    """A read that returns `default` instead of raising while the data is locked
    (encrypted with a key that is not in the Keychain)."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except vault.VaultError:
                return default() if callable(default) else default
        return inner
    return wrap


def _stem(name: str) -> str:
    """A stored document name without its extension."""
    return os.path.splitext(os.path.basename(name))[0]


def textfmt_clean(text) -> str:
    """Pasted text with its line ends tidied (the words are left as they are)."""
    lines = [ln.rstrip() for ln in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out = "\n".join(lines).strip()
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out


def _claude_auth_status():
    """Ask the Claude CLI who is signed in (tests replace this, so they never run the real CLI)."""
    return subprocess.run(["claude", "auth", "status"], capture_output=True, text=True, timeout=8)


class Api:
    # ── small helpers ───────────────────────────────────────────
    def _open(self, path):
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass

    def _reveal(self, path):
        """Show a file in its folder (selected in Finder), so it is easy to drag into a form."""
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            else:
                self._open(os.path.dirname(str(path)))
        except Exception:
            pass

    def show_in_folder(self, kind, job_id):
        """Reveal a job's CV, letter or single PDF in its folder. The PDF copy when there is one."""
        j = store.find(store.load_jobs(), job_id)
        if not j:
            return {"ok": False, "msg": "That job is not in the list any more."}
        if kind == "combined":
            name = _stem(j.get("tailored_cv_file", "")).replace("_CV_", "_Application_")
            target = config.DATA_DIR / "combined" / f"{name if '_Application_' in name else name + '_application'}.pdf"
        else:
            base = {"cv": config.TAILORED_CV_DIR, "letter": config.LETTERS_DIR}.get(kind)
            name = j.get("tailored_cv_file" if kind == "cv" else "cover_letter_file", "")
            if base is None or not name:
                return {"ok": False, "msg": "There is no such document for this job yet."}
            docx = (base / name).with_suffix(".docx")
            target = pdf.pdf_for(docx) or (docx if docx.is_file() else base / name)
            if not target.is_file() and kind == "letter":
                target = config.COVER_LETTERS_DIR / os.path.basename(name)      # a letter of your own
        if not target.is_file():
            return {"ok": False, "msg": "That file is not on the disk any more." if kind != "combined"
                    else "Make the single PDF first, then it can be shown in its folder."}
        self._reveal(target)
        return {"ok": True, "file": target.name}

    # ── read: status / data ─────────────────────────────────────
    def connections(self):
        claude, plan, claude_email = False, "", ""
        try:
            out = _claude_auth_status()
            try:
                info = json.loads(out.stdout)
                claude = info.get("loggedIn") is True
                plan = str(info.get("subscriptionType") or "")
                claude_email = str(info.get("email") or "")
            except ValueError:
                claude = '"loggedIn": true' in out.stdout
        except Exception:
            claude = False
        cv = agent1_cv.find_cv()
        changed = []
        try:
            changed = [f["title"] for f in integrity.problems()]
        except vault.VaultError:
            pass
        return {"vault": vault.state(), "changed_files": changed, "pdf": pdf.available(),
                "claude": claude, "plan": plan if claude else "",
                "claude_email": claude_email if claude else "",
                "paid_api": config.using_paid_api(),
                "email": config.has_imap(), "email_addr": config.IMAP_USER,
                "email2": bool(config.IMAP_USER_2 and config.IMAP_PASSWORD_2), "email2_addr": config.IMAP_USER_2,
                "cv": cv.name if cv else ""}

    @_guarded(lambda: {"leads": 0, "applications": 0, "responses": 0, "followups": 0, "duplicates": 0})
    def counts(self):
        jobs = store.load_jobs()
        return {"leads": sum(1 for j in jobs if j["status"] in store.LEAD_STATUSES),
                "applications": sum(1 for j in jobs if j["status"] in store.APPLICATION_STATUSES),
                "responses": db.total(),
                "followups": len(followup.due_jobs(jobs, db.all_responses(), self._followup_days())),
                "duplicates": len(merge.find(jobs))}

    def usage_info(self):
        st = usage._load()
        totals = st.get("totals", {})
        rl = (st.get("last_rate_limit") or {}).get("info")
        five = seven = None
        if isinstance(rl, dict):
            w = rl.get("unifiedWindows") or {}
            def pct(k):
                x = (w.get(k) or {}).get("utilization")
                return round(x * 100) if isinstance(x, (int, float)) else None
            five, seven = pct("five_hour"), pct("seven_day")
        return {"five_hour_used": five, "seven_day_used": seven, "model": config.MODEL,
                "calls": totals.get("calls", 0), "cost": round(totals.get("cost_usd", 0.0), 2)}

    @_guarded(list)
    def leads(self):
        jobs = store.load_jobs()
        rows = [j for j in jobs if j["status"] in store.LEAD_STATUSES
                and (j.get("match_score") is None or j["match_score"] >= config.MIN_LEAD_SCORE)]
        rows.sort(key=lambda j: (-(j.get("match_score") or 0), j.get("date_posted", "")))
        rows.sort(key=lambda j: bool(j.get("prefilter")) and j.get("match_score") is None)     # skipped ones last
        threshold = self._threshold()
        return [{"id": j["id"], "score": j.get("match_score"),
                 "tier": j.get("match_tier", "") or ("skipped" if j.get("prefilter") and j.get("match_score") is None else ""),
                 "title": j["title"], "company": j["company"], "posted": j.get("date_posted", ""),
                 "location": j.get("location", ""), "source": (j.get("source") or "").split("/")[0],
                 "desired": j.get("desired_monthly_czk", ""), "status": j["status"],
                 "url": j.get("url", ""),
                 "basis": agent3_letters.text_basis(j) if j.get("match_score") is not None else "",
                 "stale_docs": self._stale_docs(j, threshold),
                 "before": self._score_before(j),
                 "letter": j.get("cover_letter_file", ""), "cv": j.get("tailored_cv_file", "")}
                for j in rows]

    @_guarded(list)
    def applications(self):
        jobs = store.load_jobs()
        rows = [j for j in jobs if j["status"] in store.APPLICATION_STATUSES]
        days, replies = self._followup_days(), followup.last_reply_by_job(db.all_responses())
        state = {j["id"]: followup.info(j, days, replies.get(j["id"])) for j in rows}
        doubles = {i for pair in merge.find(jobs) for i in (pair["keep"], pair["drop"])}
        # grouped by status (interview, waiting, rejected); inside a group the ones
        # due for a follow-up first, then the most recently updated
        rows.sort(key=lambda j: j.get("last_update", ""), reverse=True)
        rows.sort(key=lambda j: not state[j["id"]]["due"])
        rows.sort(key=store.application_rank)
        return [{"id": j["id"], "company": j["company"], "title": j["title"], "status": j["status"],
                 "stages": j.get("stages_path", ""), "next_step": j.get("next_step", ""),
                 "letter": j.get("cover_letter_file", ""), "cv": j.get("tailored_cv_file", ""),
                 "applied": j.get("date_applied", ""), "updated": j.get("last_update", ""),
                 "followup": state[j["id"]]["due"], "days_waiting": state[j["id"]]["days_waiting"],
                 "had_reply": state[j["id"]]["had_reply"], "duplicate": j["id"] in doubles}
                for j in rows]

    # ── one job in full ─────────────────────────────────────────
    def _followup_days(self) -> int:
        try:
            return max(0, int(config.ui_settings().get("followup_days", followup.DEFAULT_DAYS)))
        except (TypeError, ValueError):
            return followup.DEFAULT_DAYS

    _cv_cache: tuple = ("", 0.0, "")

    def _cv_text(self) -> str:
        """Master CV text, re-read only when the file changes."""
        try:
            path = agent1_cv.find_cv()
            if not path:
                return ""
            stamp = path.stat().st_mtime
            if Api._cv_cache[:2] != (str(path), stamp):
                Api._cv_cache = (str(path), stamp, agent1_cv.read_cv_text(path))
            return Api._cv_cache[2]
        except Exception:  # noqa: BLE001
            return ""

    def _doc(self, base, name: str) -> dict:
        """Which files exist for a stored document name."""
        if not name:
            return {"name": "", "pdf": False}
        return {"name": name, "pdf": pdf.pdf_for((base / name).with_suffix(".docx")) is not None}

    @_guarded(dict)
    def job_detail(self, job_id):
        """Everything the detail view shows for one job."""
        jobs = store.load_jobs()
        j = store.find(jobs, job_id)
        if not j:
            return {}
        description = (j.get("description") or "").strip()
        words = keywords.compare(description, self._cv_text()) if description else {"matched": [], "missing": []}
        replies = followup.last_reply_by_job(db.all_responses())
        letter = self._doc(config.LETTERS_DIR, j.get("cover_letter_file", ""))
        cv = self._doc(config.TAILORED_CV_DIR, j.get("tailored_cv_file", ""))
        return {
            "id": j["id"], "title": j["title"], "company": j["company"], "location": j.get("location", ""),
            "source": j.get("source", ""), "url": j.get("url", ""), "posted": j.get("date_posted", ""),
            "status": j["status"], "is_lead": j["status"] in store.LEAD_STATUSES,
            "score": j.get("match_score"), "tier": j.get("match_tier", ""),
            "score_before": self._score_before(j),
            "can_rescore": j["status"] in store.LEAD_STATUSES and j.get("match_score") is not None,
            # what the score rests on matters while you decide whether to apply; an application is past that
            "basis": agent3_letters.text_basis(j) if j["status"] in store.LEAD_STATUSES and j.get("match_score") is not None else "",
            "can_paste_text": j["status"] in store.LEAD_STATUSES and agent3_letters.text_basis(j) != "",
            "docs_stale": self._stale_docs(j), "threshold": self._threshold(),
            "can_unshelve": bool(self._shelved(j)), "shelved_when": (self._shelved(j) or {}).get("when", ""),
            "reason": j.get("match_reason", ""), "description": description[:8000],
            "description_text": textfmt.readable(description[:8000]),
            "prefilter": j.get("prefilter", "") if j.get("match_score") is None else "",
            "hold": j.get("hold", "") if not j.get("cover_letter_file") else "",
            "score_queued": bool(j.get("prefilter_override")) and j.get("match_score") is None,
            "is_application": j["status"] in store.APPLICATION_STATUSES,
            "is_dismissed": j["status"] == store.NOT_INTERESTED,
            "letter_editable": self._editable_letter(j),
            "letter_old_format": self._old_format_letter(j),
            "event": dict(j.get("event") or {}),
            "thanks_due": planner.thanks_due(j),
            "apply_steps": list(j.get("apply_steps") or []),
            "has_answers": bool((j.get("form_answers") or {}).get("items")),
            "can_combine": self._can_combine(j),
            "company_notes": planner.company_notes(j.get("company", "")),
            "pay": salary.stated(j) or {},
            "can_compare": self._comparable(j),
            "has_prep": bool((j.get("interview_prep") or {}).get("questions")),
            "prep_edited": bool((j.get("interview_prep") or {}).get("edited")),
            "prep_made": (j.get("interview_prep") or {}).get("made", ""),
            "duplicate": self._duplicate_of(jobs, j),
            "matched": words["matched"], "missing": words["missing"],
            "desired": j.get("desired_monthly_czk", ""), "applied": j.get("date_applied", ""),
            "applied_from_email": j.get("date_applied_source") == "first email",
            "notes": j.get("notes", ""), "next_step": j.get("next_step", ""),
            "letter": letter["name"], "letter_pdf": letter["pdf"], "cv": cv["name"], "cv_pdf": cv["pdf"],
            "followup": followup.info(j, self._followup_days(), replies.get(j["id"])),
        }

    def _duplicate_of(self, jobs, job) -> dict:
        """The other record that looks like the same application, if any."""
        for pair in merge.find(jobs):
            if job["id"] in (pair["keep"], pair["drop"]):
                other = store.find(jobs, pair["drop"] if pair["keep"] == job["id"] else pair["keep"])
                return {"id": other["id"], "company": other["company"], "title": other["title"],
                        "status": other["status"], "keep": pair["keep"], "drop": pair["drop"]}
        return {}

    # ── changing a job by hand ──────────────────────────────────
    live = None      # the jobs list a run in progress is working on (set by the bridge)

    def _change(self, job_id, fn, render: bool = True):
        """Apply one hand edit to the saved jobs - and, while a search or scan is
        running, to that run's own list too. Without the second step the run
        would write its older copy over your edit when it finishes."""
        jobs = store.load_jobs()
        j = store.find(jobs, job_id)
        if not j:
            return {"ok": False, "msg": "That job is not in the list any more."}
        result = fn(jobs, j) or {"ok": True}
        if result.get("ok"):
            store.save_jobs(jobs)
            if render:                               # the Excel files only when what they show has changed
                agent4_tracker.render_all(jobs)
            running = self.live
            twin = store.find(running, job_id) if running is not None else None
            if twin is not None:
                try:
                    fn(running, twin)
                except Exception:  # noqa: BLE001 - the saved copy is already right
                    pass
        return result

    def set_status(self, job_id, status):
        """Mark an application rejected / interview / offer / waiting by hand
        (for news that did not come through the scanned mailbox)."""
        def go(jobs, j):
            if status not in store.APPLICATION_STATUSES:
                return {"ok": False, "msg": "Unknown status."}
            if j["status"] == status:
                return {"ok": True}
            today = date.today().isoformat()
            if j["status"] in store.LEAD_STATUSES and not j.get("date_applied"):
                j["date_applied"] = today
            j["status"], j["last_update"] = status, today
            j["notes"] = (f"[{today}] Marked {status.replace('_', ' ')} by you.\n" + (j.get("notes") or "")).strip()
            agent2_search.prune_applied_leads(jobs)
        return self._change(job_id, go)

    def set_apply_date(self, job_id, text):
        """Set the day you applied (YYYY-MM-DD). This date is yours: emails never change it."""
        def go(jobs, j):
            try:
                day = date.fromisoformat((text or "").strip())
            except ValueError:
                return {"ok": False, "msg": "Write the date as YYYY-MM-DD, for example 2026-10-07."}
            if day > date.today():
                return {"ok": False, "msg": "That date is in the future."}
            if day.year < 2020:
                return {"ok": False, "msg": "That date is too far in the past. Check the year."}
            j["date_applied"] = day.isoformat()
            j.pop("date_applied_source", None)
            if j.get("source") == "manual" and j.get("date_found") == j["date_applied"]:
                j["date_found"] = ""               # so it is not mistaken for an import day
            j["last_update"] = date.today().isoformat()
        return self._change(job_id, go)

    # ── what a score rests on, and documents left over from a higher score ──
    MIN_PASTED, MAX_PASTED = 200, 20000

    def _threshold(self) -> int:
        try:
            return int(self.options().get("threshold") or config.DEFAULT_THRESHOLD)
        except (TypeError, ValueError):
            return config.DEFAULT_THRESHOLD

    def _stale_docs(self, j, threshold=None) -> bool:
        """A new job whose letter or CV was written by the app when the score was higher than your limit is now."""
        if j.get("status") not in store.LEAD_STATUSES or not isinstance(j.get("match_score"), int):
            return False
        threshold = self._threshold() if threshold is None else threshold
        return j["match_score"] < threshold and (agent3_letters._generated_letter(j) or bool(j.get("tailored_cv_file")))

    def profession_fields(self, wanted=None):
        """Which professions the free first look treats as yours, for the roles given (the ones
        typed in Options, before they are saved): {fields: [...], from_cv: bool}."""
        from . import prefilter
        try:
            profile = agent1_cv.load_profile() or {}
        except Exception:  # noqa: BLE001 - no CV analysis yet
            profile = {}
        wanted = [str(w).strip() for w in (wanted or []) if str(w).strip()] or list(profile.get("target_roles") or [])
        roles = wanted + list(profile.get("adjacent_roles") or [])
        from_roles = prefilter.fields_of(roles)
        return {"fields": from_roles or prefilter.fields_of([], self._cv_text()), "from_cv": not from_roles, "all": list(prefilter.FIELDS)}

    @staticmethod
    def _score_before(j):
        """The score a job had before it was scored again (None if it never changed)."""
        before = j.get("score_before")
        return before if isinstance(before, int) and not isinstance(before, bool) and before != j.get("match_score") else None

    @_guarded(list)
    def stale_docs_list(self):
        """New jobs that still have a letter or CV from a score that was above your limit: [{id, title, company, score}]."""
        threshold = self._threshold()
        return [{"id": j["id"], "title": j["title"], "company": j["company"], "score": j["match_score"]}
                for j in store.load_jobs() if self._stale_docs(j, threshold)]

    def shelve_all_docs(self, expected=-1):
        """Move the documents of every job in stale_docs_list() to the backup. `expected` is how many
        jobs the confirmation named; if the list changed since, nothing moves and the question is asked again."""
        rows = self.stale_docs_list()
        if not rows:
            return {"ok": False, "msg": "No new job has documents from a higher score."}
        if isinstance(expected, int) and expected >= 0 and expected != len(rows):
            return {"ok": False, "changed": True, "msg": f"The list changed: it is now {len(rows)} "
                    f"{'job' if len(rows) == 1 else 'jobs'}. Check the names and confirm again."}
        done, files, failed = 0, 0, []
        batch = datetime.now().strftime("%Y%m%d_%H%M%S_%f")          # one name for all of them, so they can be put back together
        for row in rows:
            got = self.shelve_docs(row["id"], batch)
            if got.get("ok"):
                done, files = done + 1, files + int(got.get("moved") or 0)
            else:
                failed.append({"title": row["title"], "company": row["company"], "why": got.get("msg") or "Couldn't move the documents."})
        if not done:
            return {"ok": False, "msg": "Couldn't move the documents.", "failed": failed}
        return {"ok": True, "jobs": done, "files": files, "failed": failed}

    def set_description(self, job_id, text):
        """Keep the posting's text you pasted for a job the app could not read. Score it again afterwards."""
        text = textfmt_clean(text)
        if len(text) < self.MIN_PASTED:
            return {"ok": False, "msg": f"That is only {len(text)} characters. Paste the whole posting (at least {self.MIN_PASTED})."}
        if len(text) > self.MAX_PASTED:
            return {"ok": False, "msg": f"That is {len(text)} characters; the most is {self.MAX_PASTED}. Paste only the posting itself."}

        def go(jobs, j):
            if j["status"] not in store.LEAD_STATUSES:
                return {"ok": False, "msg": "The text can only be added to a new job."}
            j["description"], j["description_by_hand"] = text, True
            if j.get("hold") == agent3_letters.NO_TEXT:
                j.pop("hold", None)
            j["doc_attempts"] = 0
        return self._change(job_id, go, render=False)

    def reread_posting(self, job_id):
        """Try to read a posting's text from its board again (no Claude). Score it again afterwards."""
        j = store.find(store.load_jobs(), job_id)
        if not j or j["status"] not in store.LEAD_STATUSES:
            return {"ok": False, "msg": "Only a new job's posting can be read again."}
        if not j.get("url"):
            return {"ok": False, "msg": "This job has no link, so there is nothing to read. Paste the posting's text instead."}
        text = agent2_search.refetch_description(j)
        if len(text.strip()) <= len((j.get("description") or "").strip()):
            return {"ok": False, "msg": "The posting still cannot be read from its site. Open it and paste its text instead."}

        def go(jobs, job):
            job["description"] = text
            if job.get("hold") == agent3_letters.NO_TEXT:
                job.pop("hold", None)
            job["doc_attempts"] = 0
        saved = self._change(job_id, go, render=False)
        return {"ok": bool(saved.get("ok")), "chars": len(text)}

    SHELF = "below_your_limit"        # the folder in backups/ that documents below your limit go to
    UNDO_DAYS = 7                     # how long New Jobs offers to put the last moved batch back

    def shelve_docs(self, job_id, batch=""):
        """Move the letter and CV the app wrote for a new job into an encrypted backup (never a letter of your own).
        The job stays in the list; documents are written again only if its score reaches your limit.
        What was moved is noted on the job (`shelved`), so unshelve_docs can put it back."""
        moved = {}
        now = datetime.now()

        def go(jobs, j):
            if "record" in moved:                 # the same edit on a running search's own list: the files are already moved
                record, app_wrote_it = dict(moved["record"]), moved["app_wrote_it"]
                return note(j, record, app_wrote_it)
            if j["status"] not in store.LEAD_STATUSES:
                return {"ok": False, "msg": "Documents are only put away for a new job, not for an application you sent."}
            files = self._generated_docs(j)
            if not files:
                return {"ok": False, "msg": "This job has no documents written by the app."}
            app_wrote_it = agent3_letters._generated_letter(j)
            record = {"when": now.isoformat(timespec="seconds"), "batch": batch or now.strftime("%Y%m%d_%H%M%S_%f"), "files": [],
                      "cover_letter_file": j.get("cover_letter_file", "") if app_wrote_it else "",
                      "tailored_cv_file": j.get("tailored_cv_file", ""), "match_tier": j.get("match_tier", ""),
                      "status": j["status"], "apply_steps": list(j.get("apply_steps") or [])}
            for path in files:
                copy = vault.keep_copy(path, self.SHELF)
                if copy:
                    record["files"].append({"backup": copy.name, "name": path.name,
                                            "folder": "cv" if path.parent == config.TAILORED_CV_DIR else "letter"})
                    path.unlink()
            moved["n"] = len(record["files"])
            moved["record"], moved["app_wrote_it"] = record, app_wrote_it
            return note(j, dict(record), app_wrote_it)

        def note(j, record, app_wrote_it):
            j["shelved"] = record
            if app_wrote_it:
                j["cover_letter_file"] = ""
            j["tailored_cv_file"], j["match_tier"] = "", ""
            if not j.get("cover_letter_file"):
                j["status"] = "found"
            j["apply_steps"] = []
            j["last_update"] = date.today().isoformat()
        result = self._change(job_id, go)
        return {"ok": True, "moved": moved.get("n", 0)} if result.get("ok") else {"ok": False, "msg": result.get("msg") or "Couldn't move the documents."}

    @staticmethod
    def _shelved(j):
        """The note of documents moved to the backup for a new job, while they can still be put back
        (the job is still a new job and no other documents were written for it since)."""
        record = j.get("shelved")
        if not isinstance(record, dict) or not isinstance(record.get("files"), list) or not record["files"]:
            return None
        if j.get("status") not in store.LEAD_STATUSES or j.get("tailored_cv_file"):
            return None
        if record.get("cover_letter_file") and j.get("cover_letter_file"):
            return None
        return record

    def unshelve_docs(self, job_id):
        """Put the documents moved by shelve_docs back where they were. Nothing is changed unless all of it can be."""
        done = {}

        def go(jobs, j):
            if "record" in done:                  # the same edit on a running search's own list: the files are already back
                return back(j, done["record"])
            record = self._shelved(j)
            if not record:
                if isinstance(j.get("shelved"), dict) and j.get("status") in store.LEAD_STATUSES:
                    return {"ok": False, "msg": "Other documents were written for this job since. The earlier ones stay in the backup."}
                return {"ok": False, "msg": "No documents of this job are in the backup to put back."}
            plan = []
            for item in record["files"]:
                if not isinstance(item, dict):
                    return {"ok": False, "msg": "The note of what was moved is damaged. The files are still in the backup."}
                name, backup = os.path.basename(str(item.get("name") or "")), os.path.basename(str(item.get("backup") or ""))
                source = vault.backups_dir() / self.SHELF / backup
                target = (config.TAILORED_CV_DIR if item.get("folder") == "cv" else config.LETTERS_DIR) / name
                if not name or not backup or not source.is_file():
                    return {"ok": False, "msg": f"The backup copy of {name or 'a document'} is missing, so nothing was put back."}
                if target.exists():
                    return {"ok": False, "msg": f"A file named {name} is already in its folder, so nothing was put back."}
                plan.append((source, target))
            try:
                contents = [(source, target, vault.read_bytes(source)) for source, target in plan]
            except Exception as e:  # noqa: BLE001 - a damaged backup: say so, change nothing
                return {"ok": False, "msg": f"A backup copy could not be read ({e}), so nothing was put back."}
            for source, target, data in contents:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                source.unlink()
            done["record"], done["n"] = record, len(contents)
            return back(j, record)

        def back(j, record):
            if record.get("cover_letter_file"):
                j["cover_letter_file"] = record["cover_letter_file"]
            j["tailored_cv_file"], j["match_tier"] = record.get("tailored_cv_file", ""), record.get("match_tier", "")
            if record.get("status") in store.LEAD_STATUSES:
                j["status"] = record["status"]
            j["apply_steps"] = list(record.get("apply_steps") or [])
            j["last_update"] = date.today().isoformat()
            j.pop("shelved", None)
        result = self._change(job_id, go)
        return {"ok": True, "restored": done.get("n", 0)} if result.get("ok") else {"ok": False, "msg": result.get("msg") or "Couldn't put the documents back."}

    # ── moved documents that have grown old ─────────────────────
    SHELF_DAYS = 30                   # the age Options suggests
    SHELF_MAX_DAYS = 3650

    def _shelf_days(self, days):
        """A usable number of days, or the reason it is not one."""
        if isinstance(days, bool) or not isinstance(days, (int, float)) or days != int(days):
            return None, "Give the age as a whole number of days."
        days = int(days)
        if days < housekeeping.SHELF_MIN_DAYS:
            return None, f"Copies younger than {housekeeping.SHELF_MIN_DAYS} days are kept: New Jobs still offers to put them back."
        if days > self.SHELF_MAX_DAYS:
            return None, f"The most is {self.SHELF_MAX_DAYS} days."
        return days, ""

    def shelf_status(self, days=None):
        """How many moved documents are in the backup, and how many are older than `days`:
        {ok, files, bytes, old, old_bytes, days} or {ok: False, msg}."""
        days, why = self._shelf_days(self.SHELF_DAYS if days is None else days)
        if days is None:
            return {"ok": False, "msg": why}
        files, old = housekeeping.shelf_files(), housekeeping.shelf_files(days)
        return {"ok": True, "files": len(files), "bytes": sum(p.stat().st_size for p in files),
                "old": len(old), "old_bytes": sum(p.stat().st_size for p in old), "days": days}

    def tidy_shelf(self, days=None, expected=-1):
        """Move the moved documents older than `days` to the Trash. `expected` is the count the
        question named; if it is no longer right nothing is moved. Jobs whose copies are gone
        lose their note, so no window offers to put back what is no longer in the backup."""
        state = self.shelf_status(days)
        if not state.get("ok"):
            return state
        if not state["old"]:
            return {"ok": False, "msg": f"No moved documents are older than {state['days']} days."}
        if isinstance(expected, int) and not isinstance(expected, bool) and expected >= 0 and expected != state["old"]:
            return {"ok": False, "changed": True, "msg": f"The number changed: it is now {state['old']}. Check and confirm again."}
        done = housekeeping.tidy_shelf(state["days"])
        gone = set(done["removed"])
        if gone:
            jobs, touched = store.load_jobs(), False
            for j in jobs:
                record = j.get("shelved")
                if isinstance(record, dict) and any(isinstance(f, dict) and f.get("backup") in gone for f in record.get("files") or []):
                    j.pop("shelved", None)
                    touched = True
            if touched:
                store.save_jobs(jobs)
        if not gone:
            return {"ok": False, "msg": "The Trash of this disk cannot be used, so nothing was removed." if done.get("no_trash")
                    else "The old copies could not be moved to the Trash."}
        return {"ok": True, "removed": len(gone), "bytes": done["bytes"]}

    @_guarded(dict)
    def last_shelved(self):
        """The most recent batch of documents moved to the backup that can still be put back, for
        UNDO_DAYS: {when, batch, jobs: [{id, title, company}]} ({} when there is none)."""
        oldest = (datetime.now() - timedelta(days=self.UNDO_DAYS)).isoformat(timespec="seconds")
        rows = [(r, j) for j in store.load_jobs() for r in [self._shelved(j)]
                if r and isinstance(r.get("when"), str) and r["when"] >= oldest and isinstance(r.get("batch"), str)]
        if not rows:
            return {}
        newest = max(rows, key=lambda pair: pair[0]["when"])[0]
        return {"when": newest["when"], "batch": newest["batch"],
                "jobs": [{"id": j["id"], "title": j["title"], "company": j["company"]} for r, j in rows if r["batch"] == newest["batch"]]}

    def unshelve_last(self, batch=""):
        """Put back every job's documents of the batch last_shelved() names (`batch` is the one the button showed)."""
        last = self.last_shelved()
        if not last:
            return {"ok": False, "msg": "No moved documents are left to put back."}
        if batch and batch != last["batch"]:
            return {"ok": False, "changed": True, "msg": "The list changed. Look at it again and press once more."}
        done, files, failed = 0, 0, []
        for row in last["jobs"]:
            got = self.unshelve_docs(row["id"])
            if got.get("ok"):
                done, files = done + 1, files + int(got.get("restored") or 0)
            else:
                failed.append({"title": row["title"], "company": row["company"], "why": got.get("msg") or "Couldn't put the documents back."})
        if not done:
            return {"ok": False, "msg": "Couldn't put the documents back.", "failed": failed}
        return {"ok": True, "jobs": done, "files": files, "failed": failed}

    def rescore_ids(self, job_id=""):
        """Which jobs "Score again" covers: the one given, or every new job that has a score."""
        jobs = store.load_jobs()
        if job_id:
            j = store.find(jobs, job_id)
            return [j["id"]] if j and j.get("status") in store.LEAD_STATUSES and j.get("match_score") is not None else []
        return [j["id"] for j in jobs if j.get("status") in store.LEAD_STATUSES and j.get("match_score") is not None]

    def rescore_plan(self):
        """How much "Score all again" would ask: {jobs, calls}."""
        n = len(self.rescore_ids())
        return {"jobs": n, "calls": -(-n // max(1, int(config.SCORE_BATCH)))}

    def rescore_one(self, job_id):
        """Score one new job again now (one Claude call). Only the score and its reason change."""
        ids = self.rescore_ids(job_id)
        if not ids:
            return {"ok": False, "msg": "Only a new job that already has a score can be scored again."}
        profile = agent1_cv.load_profile() or {}
        jobs = store.load_jobs()
        try:
            stats = agent3_letters.rescore(jobs, ids, profile, self._cv_text())
        except Exception as e:  # noqa: BLE001 - shown to the user as the reason (the limit, no connection)
            return {"ok": False, "msg": str(e)}
        if not stats["scored"]:
            return {"ok": False, "msg": "Claude gave no usable score. Try again in a moment."}
        fresh = store.find(jobs, job_id)
        keys = ("match_score", "match_reason", "score_before", "score_capped", "match_tier", "last_update")

        def go(current, j):          # put on a fresh copy: the call took a few seconds
            for k in keys:
                if k in fresh:
                    j[k] = fresh[k]
                else:
                    j.pop(k, None)
        self._change(job_id, go)
        change = stats["changed"][0] if stats["changed"] else None
        return {"ok": True, "score": fresh["match_score"], "before": change["before"] if change else fresh["match_score"]}

    def score_anyway(self, job_id):
        """Send a job the free pre-filter skipped to scoring on the next run."""
        def go(jobs, j):
            j["prefilter_override"] = True
            j.pop("prefilter", None)
        return self._change(job_id, go)

    # ── dates to remember ───────────────────────────────────────
    def set_event(self, job_id, day, time_text="", kind="interview", note=""):
        def go(jobs, j):
            problem = planner.set_event(j, day, time_text, kind, note)
            return {"ok": False, "msg": problem} if problem else {"ok": True}
        return self._change(job_id, go, render=False)

    def clear_event(self, job_id):
        return self._change(job_id, lambda jobs, j: planner.clear_event(j), render=False)

    @_guarded(list)
    def upcoming(self, limit=0):
        return planner.upcoming(store.load_jobs(), limit=int(limit or 0))

    def due_reminders(self):
        """Events that are tomorrow or today and were not announced yet (marks them announced)."""
        try:
            jobs = store.load_jobs()
        except vault.VaultError:
            return []
        due = planner.due_reminders(jobs)
        if due:
            store.save_jobs(jobs)
            live = self.live
            for item in due:                         # a run in progress must not lose the mark
                twin = store.find(live, item["id"]) if live is not None else None
                saved = store.find(jobs, item["id"])
                if twin is not None and saved is not None:
                    twin["event_notified"] = saved.get("event_notified")
                    twin["event_marks"] = list(saved.get("event_marks") or [])
        return due

    def export_event(self, job_id):
        """Write the job's date as a calendar file and open it (Calendar adds it; it syncs to the phone)."""
        j = store.find(store.load_jobs(), job_id)
        text = planner.ics(j) if j else ""
        if not text:
            return {"ok": False, "msg": "Save a date first."}
        folder = config.DATA_DIR / "calendar"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (store.slugify(f"{j.get('company', '')} {j['event'].get('kind', '')} {j['event']['date']}") + ".ics")
        path.write_text(text, encoding="utf-8", newline="")
        self._open(path)
        return {"ok": True, "file": path.name}

    # ── a thank-you note after an interview ─────────────────────
    def _my_name(self) -> str:
        try:
            profile = agent1_cv.load_profile()
        except Exception:  # noqa: BLE001
            profile = None
        cv = agent1_cv.find_cv()
        return followup.candidate_name(profile, cv.name if cv else "")

    def thanks_draft(self, job_id):
        j = store.find(store.load_jobs(), job_id)
        if not j:
            return {}
        return planner.thanks_draft(j, self._my_name(), planner.company_notes(j.get("company", "")).get("contact", ""))

    def mark_thanked(self, job_id):
        return bool(self._change(job_id, lambda jobs, j: planner.mark_thanked(j), render=False).get("ok"))

    # ── answers for one job's application form ──────────────────
    @_guarded(dict)
    def form_answers(self, job_id):
        """What is stored for this job's form, plus the questions forms ask most often to start from."""
        j = store.find(store.load_jobs(), job_id)
        if not j:
            return {}
        kept = j.get("form_answers") or {}
        return {"id": j["id"], "company": j.get("company", ""), "title": j.get("title", ""),
                "items": form_answers.tidy(kept.get("items")), "made": str(kept.get("made", "")),
                "common": form_answers.common_questions(j)}

    def check_questions(self, questions_text):
        """What the pasted text holds, before anything is asked: {count, problem, note}."""
        checked = form_answers.check_questions(questions_text)
        return {"count": len(checked["questions"]), "problem": checked["problem"], "note": checked["note"]}

    def make_form_answers(self, job_id, questions_text):
        """Draft answers to the pasted questions with Claude (one call, one retry) and keep them with the job."""
        j = store.find(store.load_jobs(), job_id)
        if not j:
            return {"ok": False, "msg": "That job is not in the list any more."}
        checked = form_answers.check_questions(questions_text)
        if checked["problem"]:
            return {"ok": False, "msg": checked["problem"]}
        questions = checked["questions"]
        cv_text = self._cv_text()
        if not cv_text.strip():
            return {"ok": False, "msg": "Your master CV could not be read, so answers cannot be built from it."}
        try:
            items = form_answers.generate(j, cv_text, questions, config.experience_notes())
        except Exception as e:  # noqa: BLE001 - shown to the user as the reason
            return {"ok": False, "msg": str(e)}
        kept = {"made": form_answers.stamp(), "items": items}
        # saved through _change: the call took a while, so re-read instead of writing an old copy back
        saved = self._change(job_id, lambda jobs, job: job.__setitem__("form_answers", kept), render=False)
        return {"ok": bool(saved.get("ok")), "count": len(items), "to_check": sum(1 for i in items if i["check"])}

    def save_form_answers(self, job_id, items):
        """Keep the answers as you edited them. An answer over the limit is refused, not cut."""
        for item in items or []:
            answer = str((item or {}).get("answer", "") or "").strip() if isinstance(item, dict) else ""
            if len(answer) > form_answers.MAX_ANSWER:
                question = str(item.get("question", ""))[:60]
                return {"ok": False, "msg": f"The answer to “{question}” is {len(answer)} characters long; "
                                            f"the most is {form_answers.MAX_ANSWER}. Shorten it."}
        clean = form_answers.tidy(list(items or []))

        def go(jobs, j):
            made = (j.get("form_answers") or {}).get("made") or form_answers.stamp()
            if clean:
                j["form_answers"] = {"made": made, "items": clean}
            else:
                j.pop("form_answers", None)
        saved = self._change(job_id, go, render=False)
        return {"ok": bool(saved.get("ok")), "count": len(clean)}

    # ── the last seven days ─────────────────────────────────────
    @_guarded(dict)
    def week_summary(self):
        w = summary.week(store.load_jobs(), db.all_responses(), int(self.options().get("followup_days") or 0))
        return {"from": w["from"], "to": w["to"], "lines": summary.lines(w), "headline": summary.headline(w)}

    # ── notes per company ───────────────────────────────────────
    def save_company_notes(self, company, fields):
        problem = planner.check_company_notes(dict(fields or {}))
        if problem:
            return {"ok": False, "msg": problem}
        ok = planner.save_company_notes(company, dict(fields or {}))
        return {"ok": ok} if ok else {"ok": False, "msg": "Notes need a company name."}

    # ── a reply that did not come by email ──────────────────────
    def add_reply(self, job_id, text):
        """File a pasted message (LinkedIn, a portal) under an application."""
        jobs = store.load_jobs()
        result = agent5_responses.add_pasted_reply(jobs, job_id, text)      # may take seconds: Claude reads it
        if result.get("ok"):
            filed = store.find(jobs, job_id) or {}
            moved = {k: filed[k] for k in ("status", "notes", "last_update", "date_applied", "date_applied_source", "next_step") if k in filed}

            def go(current, j):
                # applied to a fresh copy, not the one read before the call: other edits made meanwhile are kept
                j.update(moved)
                if current is not self.live:
                    agent5_responses.annotate_progress(current)
                    agent2_search.prune_applied_leads(current)
            self._change(job_id, go)
        return result

    # ── the check made when the app starts ──────────────────────
    def self_check(self, claude_signed_in=None):
        return health.run(claude_signed_in)

    # ── what changed (CHANGELOG.md, shown in Help) ──────────────
    @_guarded(list)
    def changelog(self):
        """[{date, items}] from CHANGELOG.md, newest first; **words** become <b>words</b>."""
        import html
        import re
        try:
            text = (config.ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        except OSError:
            return []
        out = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("## "):
                out.append({"date": line[3:].strip(), "items": []})
            elif line.startswith("- ") and out:
                out[-1]["items"].append(re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(line[2:].strip(), quote=False)))
        return [entry for entry in out if entry["items"]]

    # ── what the last search filtered out ───────────────────────
    @_guarded(dict)
    def filtered_out(self):
        """Postings the last search removed before scoring, each with its reason.
        The stored posting itself is left out: the window only needs to know whether it can come back."""
        data = agent2_search.load_dropped()
        rows = [{**{k: v for k, v in r.items() if k != "job"},
                 "can_return": isinstance(r.get("job"), dict) and bool(r["job"].get("id"))
                               and r.get("group") not in agent2_search.NO_BRING_BACK}
                for r in data["rows"]]
        return {"when": data["when"], "total": data["total"], "rows": rows}

    def bring_back(self, index):
        """Put a filtered-out posting into New Jobs; the next search run scores it like any other."""
        data = agent2_search.load_dropped()
        rows = data["rows"]
        if not 0 <= int(index) < len(rows):
            return {"ok": False, "msg": "That posting is not in the list any more."}
        row = rows[int(index)]
        posting = row.get("job")
        if not isinstance(posting, dict) or not posting.get("id"):
            return {"ok": False, "msg": "This posting was saved without its details. Run a search, then bring it back."}
        if row.get("group") in agent2_search.NO_BRING_BACK:
            return {"ok": False, "msg": "The next search would remove it again for the same reason."}
        jobs = store.load_jobs()
        if store.find(jobs, posting["id"]):
            return {"ok": False, "msg": "This posting is already in your lists."}
        job = store.normalise(dict(posting))
        job["status"] = "found"
        job["brought_back"] = row.get("reason", "")       # why it was filtered, for the record
        job["prefilter_override"] = True                  # you chose it: the free pre-filter must not skip it
        if not job.get("desired_monthly_czk"):
            level = (agent1_cv.load_profile() or {}).get("seniority", "junior")
            job["desired_monthly_czk"], job["desired_annual_czk"] = salary.estimate(job.get("title", ""), level)
        store.upsert(jobs, [job])
        store.save_jobs(jobs)
        agent4_tracker.render_all(jobs)
        live = self.live
        if live is not None and not store.find(live, job["id"]):
            live.append(dict(job))                        # a run in progress must not lose it
        del rows[int(index)]
        agent2_search.save_dropped(rows, when=data["when"])
        return {"ok": True, "title": job.get("title", "")}

    def open_filtered(self, index):
        rows = agent2_search.load_dropped()["rows"]
        url = rows[index].get("url", "") if 0 <= int(index) < len(rows) else ""
        if not url.startswith(("http://", "https://")):
            return {"ok": False}
        self._open(url)
        return {"ok": True}

    # ── master CV next to an adapted one ────────────────────────
    def _comparable(self, j) -> bool:
        name = j.get("tailored_cv_file", "")
        master = agent1_cv.find_cv()
        return bool(name) and name.endswith(".docx") and (config.TAILORED_CV_DIR / name).is_file() \
            and master is not None and str(master).lower().endswith(".docx")

    @_guarded(dict)
    def cv_compare(self, job_id):
        j = store.find(store.load_jobs(), job_id)
        if not j or not self._comparable(j):
            return {"ok": False, "msg": "There is no adapted Word CV for this job to compare."}
        try:
            result = compare.compare(agent1_cv.find_cv(), config.TAILORED_CV_DIR / j["tailored_cv_file"])
        except Exception:  # noqa: BLE001
            return {"ok": False, "msg": "The two CV files could not be read."}
        # adapted before the master CV was last changed: differences outside the adapted parts come from the older master
        adapted = config.TAILORED_CV_DIR / j["tailored_cv_file"]
        older = os.path.getmtime(adapted) < os.path.getmtime(agent1_cv.find_cv())
        return {"ok": True, "company": j["company"], "title": j["title"], "file": j["tailored_cv_file"],
                "older_master": older, **result}

    # ── interview preparation ───────────────────────────────────
    @_guarded(dict)
    def interview_prep(self, job_id):
        j = store.find(store.load_jobs(), job_id) or {}
        prep = j.get("interview_prep") or {}
        return dict(prep, id=j.get("id", ""), company=j.get("company", ""), title=j.get("title", "")) if prep else {}

    def make_interview_prep(self, job_id):
        """Ask Claude for likely questions and CV-based answers (one or two calls) and keep them with the job."""
        jobs = store.load_jobs()
        j = store.find(jobs, job_id)
        if not j:
            return {"ok": False, "msg": "That job is not in the list any more."}
        if j["status"] not in store.APPLICATION_STATUSES:
            return {"ok": False, "msg": "Interview preparation is for jobs you have applied to."}
        cv_text = self._cv_text()
        if not cv_text.strip():
            return {"ok": False, "msg": "Your master CV could not be read, so answers cannot be built from it."}
        emails = [r for r in db.all_responses() if r.get("job_id") == job_id]
        try:
            prep = interview_prep.generate(j, cv_text, emails, config.experience_notes())
        except Exception as e:  # noqa: BLE001 - shown to the user as the reason
            return {"ok": False, "msg": str(e)}
        # saved through _change: the call took a while, so re-read instead of writing an old copy back
        return {"ok": bool(self._change(job_id, lambda jobs, job: job.__setitem__("interview_prep", prep),
                                        render=False).get("ok"))}

    @_guarded(str)
    @_guarded(dict)
    def prep_parts(self, job_id):
        """The saved preparation as a list of parts to edit (see interview_prep.parts)."""
        j = store.find(store.load_jobs(), job_id)
        prep = (j or {}).get("interview_prep") or {}
        if not prep.get("questions"):
            return {"ok": False, "msg": "Prepare the interview first, then it can be edited."}
        return {"ok": True, "id": j["id"], "company": j.get("company", ""), "title": j.get("title", ""),
                "parts": interview_prep.parts(prep), "edited": str(prep.get("edited", "")),
                "max_part": interview_prep.MAX_PART}

    def save_prep_parts(self, job_id, edited):
        """Put the user's edits into the saved preparation. Refused with the reason when a part is empty or too long."""
        cv_text, notes = self._cv_text(), config.experience_notes()
        outcome = {}

        def go(jobs, j):
            prep = j.get("interview_prep") or {}
            if not prep.get("questions"):
                return {"ok": False, "msg": "There is no saved preparation for this job any more."}
            new, problem = interview_prep.apply_parts(prep, list(edited or []), cv_text, notes)
            if problem:
                return {"ok": False, "msg": problem}
            j["interview_prep"] = new
            outcome["to_check"] = len(new.get("checks") or []) + sum(1 for q in new["questions"] if q.get("check"))
        result = self._change(job_id, go, render=False)
        return {"ok": True, **outcome} if result.get("ok") else {"ok": False, "msg": result.get("msg") or "The changes could not be saved."}

    def _prep_file(self, j):
        cv = agent1_cv.find_cv()
        prefix = cv_tailor.name_prefix(cv) if cv else "Candidate"
        return config.DATA_DIR / "interview_prep" / prep_doc.file_name(prefix, j.get("company", ""))

    def prep_document(self, job_id, reveal=False):
        """Write the saved preparation as a Word document and open it (or show it in its folder)."""
        j = store.find(store.load_jobs(), job_id)
        if not j or not (j.get("interview_prep") or {}).get("questions"):
            return {"ok": False, "msg": "Prepare the interview first, then it can be opened as a document."}
        try:
            contact = planner.company_notes(j.get("company", "")).get("contact", "")
            path = prep_doc.build(j, j["interview_prep"], self._prep_file(j), contact)
        except Exception as e:  # noqa: BLE001 - shown to the user as the reason
            return {"ok": False, "msg": f"The document could not be written ({e})."}
        (self._reveal if reveal else self._open)(path)
        return {"ok": True, "file": path.name}

    def prep_text(self, job_id):
        j = store.find(store.load_jobs(), job_id) or {}
        return interview_prep.as_text(j, j["interview_prep"]) if j.get("interview_prep") else ""

    # ── insights (worked out locally, no model call) ────────────
    @_guarded(dict)
    def insights(self):
        jobs, opts = store.load_jobs(), self.options()
        threshold = int(opts.get("threshold") or 30)
        return {"works": insights.what_works(jobs, db.all_responses()),
                "keywords": insights.keyword_stats(jobs, list(opts.get("queries") or []), threshold),
                "gaps": insights.skill_gaps(jobs, self._cv_text()),
                "salaries": insights.salaries(jobs),
                "trends": insights.trends(jobs, db.all_responses()),
                "reply_times": insights.reply_times(jobs, db.all_responses()),
                "low_scores": insights.low_score_reasons(jobs, self._cv_text(), threshold),
                "threshold": threshold, "min_group": insights.MIN_GROUP}

    # ── not interested ──────────────────────────────────────────
    def _generated_docs(self, j):
        """The files this app wrote for a job (never a letter of your own)."""
        files = []
        if j.get("tailored_cv_file"):
            base = config.TAILORED_CV_DIR / j["tailored_cv_file"]
            files += [base, base.with_suffix(".pdf")]
        if agent3_letters._generated_letter(j):
            base = config.LETTERS_DIR / j["cover_letter_file"]
            files += [base, base.with_suffix(".docx"), base.with_suffix(".pdf")]
        return [p for p in dict.fromkeys(files) if p.exists()]

    def dismiss_job(self, job_id):
        """"Not interested": the lead leaves the list and later searches do not bring it back.
        The documents the app wrote for it go to an encrypted backup."""
        def go(jobs, j):
            if j["status"] not in store.LEAD_STATUSES:
                return {"ok": False, "msg": "Only a lead can be marked not interested."}
            app_wrote_it = agent3_letters._generated_letter(j)      # ask before the file is moved away
            vault.stash(self._generated_docs(j), "not_interested")
            if app_wrote_it:
                j["cover_letter_file"] = ""
            j["tailored_cv_file"], j["match_tier"] = "", ""
            j["status"], j["last_update"] = store.NOT_INTERESTED, date.today().isoformat()
        return self._change(job_id, go)

    def restore_job(self, job_id):
        """Undo "not interested": the job is a lead again (documents are written on the next run)."""
        def go(jobs, j):
            if j["status"] != store.NOT_INTERESTED:
                return {"ok": False, "msg": "That job is not in the not-interested list."}
            j["status"], j["last_update"] = "found", date.today().isoformat()
            j["doc_attempts"] = 0
        return self._change(job_id, go)

    @_guarded(list)
    def dismissed(self):
        rows = [j for j in store.load_jobs() if j["status"] == store.NOT_INTERESTED]
        rows.sort(key=lambda j: j.get("last_update", ""), reverse=True)
        return [{"id": j["id"], "score": j.get("match_score"), "title": j["title"], "company": j["company"],
                 "posted": j.get("date_posted", ""), "location": j.get("location", ""),
                 "source": (j.get("source") or "").split("/")[0], "url": j.get("url", "")} for j in rows]

    # ── editing a letter the app wrote ──────────────────────────
    def _letter_path(self, j):
        return (config.LETTERS_DIR / j.get("cover_letter_file", "")).with_suffix(".docx")

    def _editable_letter(self, j) -> bool:
        if not (bool(j) and agent3_letters._generated_letter(j) and self._letter_path(j).is_file()
                and config.LETTER_TEMPLATE.exists()):
            return False
        try:        # letters from an early version have fewer paragraphs than the template: Word only
            return len(cover_letter.read_letter(self._letter_path(j))["paragraphs"]) \
                == len(cover_letter.read_letter(config.LETTER_TEMPLATE)["paragraphs"])
        except Exception:  # noqa: BLE001 - not a letter built from the template
            return False

    def _old_format_letter(self, j) -> bool:
        """A Word letter the app wrote, but in an earlier layout: it opens in Word, not in the editor here."""
        return bool(j) and agent3_letters._generated_letter(j) and self._letter_path(j).is_file() \
            and config.LETTER_TEMPLATE.exists() and not self._editable_letter(j)

    @_guarded(dict)
    def letter_for_edit(self, job_id):
        j = store.find(store.load_jobs(), job_id)
        if not j:
            return {"ok": False, "msg": "That job is not in the list any more."}
        if not self._editable_letter(j):
            if self._old_format_letter(j):
                return {"ok": False, "msg": "This letter was made in an older format. Open it in Word to change it."}
            return {"ok": False, "msg": "This letter is your own, or was not made from the current letter template. "
                                        "Open it in Word to change it."}
        try:
            parts = cover_letter.read_letter(self._letter_path(j))
        except Exception:  # noqa: BLE001
            return {"ok": False, "msg": "The letter file could not be read. Open it in Word instead."}
        return {"ok": True, "id": j["id"], "company": j["company"], "title": j["title"], **parts,
                "min_words": cover_letter.MIN_WORDS, "max_words": cover_letter.MAX_WORDS}

    def save_letter(self, job_id, paragraphs):
        """Write the edited paragraphs back into the letter (same head, date, fonts and layout).
        The previous version is kept in an encrypted backup. Rule breaks are returned as warnings."""
        jobs = store.load_jobs()
        j = store.find(jobs, job_id)
        if not self._editable_letter(j):
            return {"ok": False, "msg": "This letter cannot be edited here."}
        texts = [cover_letter.clean(str(p)).strip() for p in (paragraphs or [])]
        if len(texts) != cover_letter.BODY_PARAGRAPHS or any(not t for t in texts):
            return {"ok": False, "msg": f"The letter needs all {cover_letter.BODY_PARAGRAPHS} paragraphs; none may be empty."}
        path = self._letter_path(j)
        parts = cover_letter.read_letter(path)
        draft = path.with_name(path.stem + ".editing.docx")
        try:
            cover_letter.build_docx(config.LETTER_TEMPLATE, draft, parts["title_line"], texts, date_text=parts["date_text"])
            # Only a damaged file stops the save. Wording that breaks a letter rule is
            # your call in a hand edit: it comes back as a warning below.
            problems = [x for x in cover_letter.verify(config.LETTER_TEMPLATE, draft, []) if "admits a gap" not in x]
            if problems:
                return {"ok": False, "msg": "The letter could not be saved: " + "; ".join(problems)}
            vault.keep_copy(path, "letter_versions")
            draft.replace(path)
        finally:
            draft.unlink(missing_ok=True)
        warnings = cover_letter.letter_warnings(texts, self._cv_text())
        made = pdf.to_pdf(path)
        if made and pdf.page_count(made) > 1:
            warnings.append("The letter is now longer than one page.")
        self._change(job_id, lambda all_jobs, job: job.__setitem__("last_update", date.today().isoformat()), render=False)
        return {"ok": True, "warnings": warnings, "words": sum(len(t.split()) for t in texts)}

    def rewrite_paragraph(self, job_id, paragraphs, index, hint=""):
        """Ask Claude for a new version of one paragraph (not saved). One or two calls."""
        j = store.find(store.load_jobs(), job_id)
        if not self._editable_letter(j):
            return {"ok": False, "msg": "Only letters the app wrote can be rewritten here."}
        texts = [str(p) for p in (paragraphs or [])]
        cv_text = self._cv_text()
        if not cv_text.strip():
            return {"ok": False, "msg": "Your master CV could not be read, so the paragraph cannot be checked against it."}
        try:
            return {"ok": True, "index": int(index),
                    "paragraph": cover_letter.rewrite_paragraph(j, cv_text, texts, int(index), hint or "")}
        except Exception as e:  # noqa: BLE001 - shown to the user as the reason
            return {"ok": False, "msg": str(e)}

    def merge_jobs(self, keep_id, drop_id):
        def go(jobs, j):
            return {"ok": merge.merge(jobs, keep_id, drop_id)}
        return self._change(keep_id, go)

    def keep_separate(self, a_id, b_id):
        def go(jobs, j):
            return {"ok": merge.keep_separate(jobs, a_id, b_id)}
        return self._change(a_id, go)

    @_guarded(dict)
    def followup_draft(self, job_id):
        j = store.find(store.load_jobs(), job_id)
        if not j:
            return {}
        try:
            profile = agent1_cv.load_profile()
        except Exception:  # noqa: BLE001
            profile = None
        cv = agent1_cv.find_cv()
        return followup.draft(j, followup.candidate_name(profile, cv.name if cv else ""))

    def mark_followed_up(self, job_id):
        result = self._change(job_id, lambda jobs, j: followup.mark_sent(j))
        return {"ok": bool(result.get("ok"))}

    @_guarded(list)
    def responses(self):
        # grouped like Applications (interviews first, rejections last), newest first inside a group
        rows = sorted(db.all_responses(), key=lambda r: db.stage_rank(r.get("stage", "")))
        out = []
        for r in rows:
            when = db.received_at(r.get("received_date", ""))
            out.append({"id": r.get("msg_id", ""), "date": when.strftime("%Y-%m-%d") if when.year > 1 else "",
                        "company": r.get("company", ""),
                        "stage": r.get("stage", ""), "summary": r.get("summary", "")})
        return out

    @_guarded(dict)
    def response_detail(self, msg_id):
        """One reply in full, with the application it belongs to."""
        r = next((x for x in db.all_responses() if x.get("msg_id") == msg_id), None)
        if not r:
            return {}
        when = db.received_at(r.get("received_date", ""))
        job = store.find(store.load_jobs(), r.get("job_id") or "") or {}
        return {"id": msg_id, "company": r.get("company", ""), "role": r.get("role", ""), "stage": r.get("stage", ""),
                "date": when.strftime("%Y-%m-%d %H:%M") if when.year > 1 else "",
                "subject": r.get("subject", ""), "sender": r.get("from_addr", ""), "summary": r.get("summary", ""),
                "next_step": r.get("next_step", ""), "sentiment": r.get("sentiment", ""),
                "reason": r.get("rejection_reason", ""),
                "category": (r.get("rejection_category") or "").replace("_", " ") if r.get("stage") == "rejection" else "",
                "job_id": job.get("id", ""), "job_title": job.get("title", ""), "job_company": job.get("company", ""),
                "job_status": job.get("status", "")}

    @_guarded(dict)
    def analytics(self):
        return agent5_responses.analytics(store.load_jobs())

    # ── the last run (shown on the Last run card, also after a restart) ──
    def last_run(self):
        try:
            data = json.loads(vault.read_text(config.DATA_DIR / "last_run.json"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, vault.VaultError):
            return {}

    def note_run(self, **fields):
        """Merge the given facts into the saved last-run summary."""
        data = self.last_run()
        data.update({k: v for k, v in fields.items() if v is not None})
        config.ensure_dirs()
        vault.write_text(config.DATA_DIR / "last_run.json", json.dumps(data, ensure_ascii=False, indent=2))
        return data

    # ── read / write: options ───────────────────────────────────
    def options(self):
        p = config.DATA_DIR / "ui_settings.json"
        # Seed the search keywords from the CV profile so the user sees (and can
        # edit) what's actually being searched.
        try:
            profile = agent1_cv.load_profile() or {}
            seed_queries = profile.get("search_queries") or profile.get("target_roles") or []
            level = profile.get("seniority", "junior")
            target_roles = [str(r) for r in (profile.get("target_roles") or [])]
        except Exception:
            seed_queries, level, target_roles = [], "junior", []
        defaults = {"where": "", "source": "czech", "include_remote": False, "full_time_only": True,
                    "all_languages": False, "max_age_days": config.MAX_JOB_AGE_DAYS,
                    "threshold": config.DEFAULT_THRESHOLD, "min_lead_score": config.MIN_LEAD_SCORE,
                    "model": config.MODEL, "per_query": 15, "queries": list(seed_queries),
                    "followup_days": followup.DEFAULT_DAYS, "scan_days": config.IMAP_LOOKBACK_DAYS,
                    "skip_words": ["intern", "internship"], "keep_words": [],
                    # what the scorer treats as your direction: starts from the roles read from your CV
                    "wanted_roles": list(target_roles), "unwanted_roles": [], "my_fields": [],
                    # start from the level in the CV; the user can change both in Options
                    "level_words": filters.default_level_words(level), "max_years": filters.default_max_years(level),
                    "about_right_to_work": "", "about_start": "", "about_experience": "", "notifications": True, "scan_all_folders": False,
                    "keep_backups": housekeeping.DEFAULT_KEEP}
        try:
            if p.exists():
                defaults.update(json.loads(vault.read_text(p)))
        except Exception:
            pass
        return defaults

    def save_options(self, opts):
        config.ensure_dirs()
        vault.write_text(config.DATA_DIR / "ui_settings.json",
                         json.dumps(opts or {}, ensure_ascii=False, indent=2))
        return {"ok": True}

    # ── career-site companies (data/companies.json) ─────────────
    def companies(self):
        p = config.DATA_DIR / "companies.json"
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                return [{"name": c.get("name", ""), "ats": c.get("ats", ""), "token": c.get("token", "")}
                        for c in data if isinstance(c, dict) and c.get("ats") and c.get("token")]
        except Exception:
            pass
        return []

    def save_companies(self, companies):
        config.ensure_dirs()
        clean = [{"name": (c.get("name") or c.get("token")), "ats": c.get("ats"), "token": c.get("token")}
                 for c in (companies or []) if c.get("ats") and c.get("token")]
        (config.DATA_DIR / "companies.json").write_text(
            json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        integrity.approve(["companies"])          # changed through the app: trusted
        return {"ok": True, "count": len(clean)}

    # ── actions ─────────────────────────────────────────────────
    def apply_job(self, job_id):
        def go(jobs, j):
            j["status"] = "waiting"
            j["last_update"] = date.today().isoformat()
            if not j.get("date_applied"):
                j["date_applied"] = date.today().isoformat()
                j.pop("date_applied_source", None)          # you pressed "mark applied": this is the real day
            agent2_search.prune_applied_leads(jobs)
        result = self._change(job_id, go)
        return {"ok": bool(result.get("ok"))}

    # ── the steps before "Mark applied" ─────────────────────────
    APPLY_STEPS = ("posting", "cv", "letter", "answers", "combined")

    def apply_step(self, job_id, step):
        """Tick one step of the apply checklist (kept with the job, so it survives closing the window)."""
        if step not in self.APPLY_STEPS:
            return {"ok": False}

        def go(jobs, j):
            done = [s for s in (j.get("apply_steps") or []) if s in self.APPLY_STEPS]
            if step not in done:
                j["apply_steps"] = done + [step]
        result = self._change(job_id, go, render=False)
        return {"ok": bool(result.get("ok"))}

    # ── letter and CV in one PDF ────────────────────────────────
    def _pdf_parts(self, j, make: bool = False):
        """[letter.pdf, cv.pdf] for a job, or None when a single PDF is not possible.
        A missing PDF copy is made from the Word file when make=True; with make=False
        it is enough that it could be made (LibreOffice is installed)."""
        parts = []
        for base, name in ((config.LETTERS_DIR, (j or {}).get("cover_letter_file", "")),
                           (config.TAILORED_CV_DIR, (j or {}).get("tailored_cv_file", ""))):
            if not name:
                return None
            docx = (base / name).with_suffix(".docx")
            found = pdf.pdf_for(docx)
            if found is None and docx.is_file():
                if make:
                    found = pdf.to_pdf(docx)
                elif pdf.available():
                    found = docx                       # can be made when asked for
            if found is None:
                return None
            parts.append(found)
        return parts

    def _can_combine(self, j) -> bool:
        return self._pdf_parts(j) is not None

    def combined_pdf(self, job_id):
        """Write the letter followed by the CV as one PDF (data/combined/) and open it."""
        j = store.find(store.load_jobs(), job_id)
        parts = self._pdf_parts(j, make=True) if j else None
        if not parts:
            return {"ok": False, "msg": "A single PDF needs both a letter and an adapted CV as PDF. "
                                        "Install LibreOffice so the app can make the PDF copies."}
        stem = _stem(j["tailored_cv_file"]).replace("_CV_", "_Application_")
        if "_Application_" not in stem:
            stem += "_application"
        out = pdf.combine(parts, config.DATA_DIR / "combined" / f"{stem}.pdf")
        if out is None:
            return {"ok": False, "msg": "The two PDF files could not be joined."}
        self._open(out)
        return {"ok": True, "file": out.name, "pages": pdf.page_count(out)}

    def open_doc(self, kind, name):
        want_pdf = kind.endswith("_pdf")
        base = {"letter": config.LETTERS_DIR, "cv": config.TAILORED_CV_DIR}.get(kind.replace("_pdf", ""))
        if not base or not name:
            return {"ok": False}
        p = base / name
        docx = p.with_suffix(".pdf" if want_pdf else ".docx")
        target = docx if docx.exists() or want_pdf else p
        if target.exists():
            self._open(target)
            return {"ok": True}
        own = config.COVER_LETTERS_DIR / os.path.basename(name)   # a letter you wrote yourself
        if kind == "letter" and own.is_file():
            self._open(own)
            return {"ok": True}
        return {"ok": False}

    def my_letters(self):
        """Where your own letters go, and how many are there."""
        folder = config.COVER_LETTERS_DIR
        try:
            count = sum(1 for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".docx", ".pdf"))
        except OSError:
            count = 0
        return {"folder": str(folder), "name": folder.name, "count": count, "inside_app": folder == config.MY_LETTERS_DIR}

    def open_my_letters(self):
        folder = config.COVER_LETTERS_DIR
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return {"ok": False}
        self._open(folder)
        return {"ok": True}

    def open_excel(self, which):
        p = {"leads": config.NEW_JOBS_EXCEL, "apps": config.EXCEL_PATH,
             "report": config.RESPONSES_REPORT}.get(which)
        if p and p.exists():
            self._open(p)
            return {"ok": True}
        return {"ok": False}

    def open_url(self, job_id):
        """Open a lead's job posting in the default browser (to go apply)."""
        job = store.find(store.load_jobs(), job_id)
        url = (job or {}).get("url", "")
        if not url:
            return {"ok": False}
        self._open(url)
        return {"ok": True, "url": url}
