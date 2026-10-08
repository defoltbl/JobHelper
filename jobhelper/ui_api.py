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
from datetime import date

from . import (agent1_cv, agent2_search, agent3_letters, agent4_tracker, agent5_responses, filters, form_answers, health, summary,
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
        return [{"id": j["id"], "score": j.get("match_score"),
                 "tier": j.get("match_tier", "") or ("skipped" if j.get("prefilter") and j.get("match_score") is None else ""),
                 "title": j["title"], "company": j["company"], "posted": j.get("date_posted", ""),
                 "location": j.get("location", ""), "source": (j.get("source") or "").split("/")[0],
                 "desired": j.get("desired_monthly_czk", ""), "status": j["status"],
                 "url": j.get("url", ""),
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
            "reason": j.get("match_reason", ""), "description": description[:8000],
            "prefilter": j.get("prefilter", "") if j.get("match_score") is None else "",
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
            items = form_answers.generate(j, cv_text, questions)
        except Exception as e:  # noqa: BLE001 - shown to the user as the reason
            return {"ok": False, "msg": str(e)}
        kept = {"made": form_answers.stamp(), "items": items}
        # saved through _change: the call took a while, so re-read instead of writing an old copy back
        saved = self._change(job_id, lambda jobs, job: job.__setitem__("form_answers", kept), render=False)
        return {"ok": bool(saved.get("ok")), "count": len(items), "to_check": sum(1 for i in items if i["check"])}

    def save_form_answers(self, job_id, items):
        """Keep the answers as you edited them."""
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
            prep = interview_prep.generate(j, cv_text, emails)
        except Exception as e:  # noqa: BLE001 - shown to the user as the reason
            return {"ok": False, "msg": str(e)}
        # saved through _change: the call took a while, so re-read instead of writing an old copy back
        return {"ok": bool(self._change(job_id, lambda jobs, job: job.__setitem__("interview_prep", prep),
                                        render=False).get("ok"))}

    @_guarded(str)
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
        except Exception:
            seed_queries, level = [], "junior"
        defaults = {"where": "", "source": "czech", "include_remote": False, "full_time_only": True,
                    "all_languages": False, "max_age_days": config.MAX_JOB_AGE_DAYS,
                    "threshold": config.DEFAULT_THRESHOLD, "min_lead_score": config.MIN_LEAD_SCORE,
                    "model": config.MODEL, "per_query": 15, "queries": list(seed_queries),
                    "followup_days": followup.DEFAULT_DAYS, "scan_days": config.IMAP_LOOKBACK_DAYS,
                    "skip_words": ["intern", "internship"], "keep_words": [],
                    # start from the level in the CV; the user can change both in Options
                    "level_words": filters.default_level_words(level), "max_years": filters.default_max_years(level),
                    "about_right_to_work": "", "about_start": "", "notifications": True, "scan_all_folders": False,
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
