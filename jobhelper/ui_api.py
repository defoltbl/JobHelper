"""Data access for the desktop app.

Plain read/write helpers over the JobHelper data (jobs, responses, options,
career-site list) plus small actions (mark applied, open a file or link). The Qt
bridge (`qt_bridge.Bridge`) exposes these to the QML window and runs the long
jobs itself.

`Api` is put together from parts, one file per area: documents and scores
(`api_documents`), interviews, dates and form answers (`api_interview`), letters
and PDFs (`api_letters`). What is left here is the lists, one job in full,
hand edits, Options and the small actions.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime

from . import trouble  # noqa: I001
from .api_base import _guarded, _stem
from .api_documents import DocumentsApi
from .api_interview import InterviewApi
from .api_letters import LettersApi
from . import (agent1_cv, agent2_search, agent3_letters, agent4_tracker, agent5_responses, filters, health, summary,
               textfmt, compare, config, db, followup, housekeeping, insights, integrity, keywords, merge, pdf, places,
               planner, salary, store, usage, vault)


def _claude_auth_status():
    """Ask the Claude CLI who is signed in (tests replace this, so they never run the real CLI)."""
    return subprocess.run(["claude", "auth", "status"], capture_output=True, text=True, timeout=8)


class Api(DocumentsApi, InterviewApi, LettersApi):
    # ── small helpers ───────────────────────────────────────────
    def _open(self, path):
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:  # noqa: BLE001 - the window says "couldn't open"; the reason is kept
            trouble.note("opening a file or folder", e)

    def _reveal(self, path):
        """Show a file in its folder (selected in Finder), so it is easy to drag into a form."""
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            else:
                self._open(os.path.dirname(str(path)))
        except Exception as e:  # noqa: BLE001
            trouble.note("showing a file in its folder", e)

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
                "email_host": config.IMAP_HOST, "email2_host": config.IMAP_HOST_2,       # a server typed by hand ('' = read from the address)
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
        """The usage card: how much of each limit is used now, and when a used one frees."""
        st = usage._load()
        totals = st.get("totals", {})
        now = datetime.now()
        out = {"model": config.MODEL, "calls": totals.get("calls", 0), "cost": round(totals.get("cost_usd", 0.0), 2)}
        for name, w in usage.windows(now.timestamp()).items():
            out[name + "_used"] = None if w["used"] is None else min(100, max(0, round(w["used"] * 100)))
            resets = ""
            if w["resets_at"]:
                when = datetime.fromtimestamp(w["resets_at"])
                resets = when.strftime("%H:%M") if when.date() == now.date() else when.strftime("%d %b %H:%M")
            out[name + "_resets"] = resets
        # seconds until the next limit comes back, so the card can correct itself then (0 = none is counting down)
        coming = [w["resets_at"] - now.timestamp() for w in usage.windows(now.timestamp()).values() if w["resets_at"] and w["used"]]
        out["next_reset_in"] = int(min(coming)) + 1 if coming else 0
        return out

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
                 "desired": self._asked_text(j), "status": j["status"],
                 "url": j.get("url", ""),
                 "basis": agent3_letters.text_basis(j) if j.get("match_score") is not None else "",
                 "stale_docs": self._stale_docs(j, threshold),
                 "before": self._score_before(j), "closed": j.get("closed") is True,
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
            "closed": j.get("closed") is True and j["status"] in store.LEAD_STATUSES,
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
            "pay": salary.stated(j, salary.asked(j)[1]) or {}, "pay_text": self._pay_text(j),
            "desired_text": self._asked_text(j, " target"),
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
                except Exception as e:  # noqa: BLE001 - the saved copy is already right
                    trouble.note(f"repeating a hand edit on the running search's list ({job_id})", e)
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
            monthly, annual = salary.estimate(job.get("title", ""), level)
            job["desired_monthly_czk"], job["desired_annual_czk"] = monthly or "", annual or ""
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

    def read_ahead(self):
        """Prepare what the Insights view needs (the keywords of every posting and of the CV), gently:
        for a background thread, so the first Insights view opens at once. Returns how many texts were read."""
        return keywords.read_ahead([j.get("description") or "" for j in store.load_jobs()] + [self._cv_text()])

    @staticmethod
    def _asked_text(j, suffix=""):
        """"60 000 CZK/mo target": what to ask for in this job, or '' when there is no figure."""
        amount, currency, _yours = salary.asked(j)
        return f"{salary.money(amount, currency)}/mo{suffix}" if amount else ""

    @staticmethod
    def _pay_text(j):
        """"posting says 55–65k CZK/mo", in the currency you ask in; '' when the posting names no pay."""
        currency = salary.asked(j)[1]
        pay = salary.stated(j, currency)
        return f"posting says {salary.span(pay['low'], pay['high'], currency)}/mo" if pay else ""

    def currencies(self):
        return list(salary.CURRENCIES)

    def salary_hint(self, where, country):
        """What the app does when no figure is given, for the line under the field in Options."""
        home = places.country_of(str(country or "")) or places.country_of(str(where or ""))
        if home == "czechia" or not (str(where or "").strip() or str(country or "").strip()):
            return "With 0 the app uses its own estimate, which it has for software roles in Czechia only."
        return "With 0 no figure is given: the app has no estimate for this country. Answers then leave the salary for you to fill in."

    def country_of(self, city):
        """The country the app takes a city to be in ("Czechia"), or '' when it does not know the city."""
        name = places.country_of(str(city or ""))
        return " ".join(part.capitalize() for part in name.split())

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
        defaults = {"where": "", "country": "", "salary_target": 0, "salary_currency": "CZK", "source": "czech", "include_remote": False, "full_time_only": True,
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
        except Exception as e:  # noqa: BLE001 - the defaults are used; the start-up check tells the user
            trouble.note("reading the saved Options", e)
        return defaults

    OPTION_NUMBERS = {"salary_target": (0, 100_000_000), "threshold": (0, 100), "min_lead_score": (0, 100), "max_age_days": (0, 3650), "per_query": (1, 100),
                      "max_years": (0, 60), "keep_backups": (0, 1000), "followup_days": (0, 365), "scan_days": (1, 3650)}
    OPTION_LISTS = ("queries", "skip_words", "keep_words", "level_words", "wanted_roles", "unwanted_roles", "my_fields")
    OPTION_TEXTS = {"where": 80, "country": 60, "about_right_to_work": 300, "about_start": 300, "about_experience": config.MAX_EXPERIENCE_NOTES}
    MAX_LIST, MAX_WORD = 60, 100

    def check_options(self, opts):
        """(clean options, '') or ({}, what is wrong). The window checks the same things as you type;
        this is the last word, so nothing unusable is saved whatever sent it."""
        if not isinstance(opts, dict):
            return {}, "Those are not Options."
        clean = dict(opts)
        for key, (low, high) in self.OPTION_NUMBERS.items():
            if key in clean:
                value = clean[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not low <= value <= high:
                    return {}, f"“{key.replace('_', ' ')}” must be a whole number from {low} to {high}."
                clean[key] = int(value)
        for key in self.OPTION_LISTS:
            if key in clean:
                if not isinstance(clean[key], (list, tuple)):
                    return {}, f"“{key.replace('_', ' ')}” must be a list of words."
                words = [str(w).strip() for w in clean[key] if isinstance(w, str) and str(w).strip()]
                if len(words) > self.MAX_LIST:
                    return {}, f"“{key.replace('_', ' ')}” has {len(words)} entries; the most is {self.MAX_LIST}."
                long = next((w for w in words if len(w) > self.MAX_WORD), None)
                if long:
                    return {}, f"An entry under “{key.replace('_', ' ')}” is {len(long)} characters long; the most is {self.MAX_WORD}."
                clean[key] = list(dict.fromkeys(words))
        for key, limit in self.OPTION_TEXTS.items():
            if key in clean:
                text = str(clean[key] or "").strip() if isinstance(clean[key], (str, type(None))) else None
                if text is None:
                    return {}, f"“{key.replace('_', ' ')}” must be text."
                if len(text) > limit:
                    return {}, f"“{key.replace('_', ' ')}” is {len(text)} characters long; the most is {limit}. Shorten it."
                clean[key] = text
        if "salary_currency" in clean:
            code = str(clean["salary_currency"] or "").strip().upper()
            if code not in salary.CURRENCIES:
                return {}, "“salary currency” must be one of: " + ", ".join(salary.CURRENCIES) + "."
            clean["salary_currency"] = code
        if clean.get("country") and not re.fullmatch(r"[^\W\d_]+(?:[ '.\-]+[^\W\d_]+)*\.?", clean["country"]):
            return {}, "“country” must be a country's name in letters, for example Germany."
        for key in ("include_remote", "all_languages", "full_time_only", "notifications", "scan_all_folders"):
            if key in clean and not isinstance(clean[key], bool):
                return {}, f"“{key.replace('_', ' ')}” must be on or off."
        return clean, ""

    def save_options(self, opts):
        """Save the Options. What the window does not send (the chosen master CV) is kept."""
        clean, problem = self.check_options(opts or {})
        if problem:
            return {"ok": False, "msg": problem}
        kept = {k: v for k, v in config.ui_settings().items() if k not in clean}
        config.ensure_dirs()
        vault.write_text(config.DATA_DIR / "ui_settings.json",
                         json.dumps({**kept, **clean}, ensure_ascii=False, indent=2))
        return {"ok": True}

    # ── career-site companies (data/companies.json) ─────────────
    def companies(self):
        p = config.DATA_DIR / "companies.json"
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                return [{"name": c.get("name", ""), "ats": c.get("ats", ""), "token": c.get("token", "")}
                        for c in data if isinstance(c, dict) and c.get("ats") and c.get("token")]
        except Exception as e:  # noqa: BLE001 - an unreadable list is shown as empty
            trouble.note("reading the career-site list", e)
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

    def open_doc(self, kind, name):
        want_pdf = kind.endswith("_pdf")
        base = {"letter": config.LETTERS_DIR, "cv": config.TAILORED_CV_DIR}.get(kind.replace("_pdf", ""))
        if not base or not name or os.path.basename(str(name)) != str(name):     # a file of that folder, never a path
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
        url = str((job or {}).get("url", "") or "").strip()
        if not url.startswith(("http://", "https://")):         # a job board hands this over: only a web page is opened
            return {"ok": False}
        self._open(url)
        return {"ok": True, "url": url}
