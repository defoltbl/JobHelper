"""The window's back end, part: what a score rests on, documents left from a higher score
(moving them to the backup, putting them back, removing old copies) and "not interested"."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from . import (agent2_search, agent3_letters, config, housekeeping, store, vault)
from .api_base import _guarded, textfmt_clean


class DocumentsApi:
    """Mixed into `ui_api.Api`; uses its `_change`, `_cv_text`, `_open` and `live`."""

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
