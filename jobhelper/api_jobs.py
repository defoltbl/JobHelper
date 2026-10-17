"""The lists of jobs, one job in full, and the hand edits and small actions on a job.

Part of the window's back end: the facade `ui_api.Api` hands calls to this service."""
from __future__ import annotations

import os
import time
from datetime import date, datetime

from .api_base import _guarded, _stem
from . import (agent2_search, agent3_letters, textfmt, config, db, followup, keywords, merge, pdf, planner, salary, store)


class JobsService:
    """The lists of jobs, one job in full, and the hand edits and small actions on a job."""

    def __init__(self, app, editor, cv, desktop) -> None:
        """`app` is the facade (`ui_api.Api`): what this service needs from the others is asked through it."""
        self._app, self._editor, self._cv, self._desktop = app, editor, cv, desktop
        self._opened = ("", 0.0)    # the posting last opened from the app, and when

    # ── small actions ───────────────────────────────────────────
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
        self._desktop.reveal(target)
        return {"ok": True, "file": target.name}

    @_guarded(lambda: {"leads": 0, "applications": 0, "interviews": 0, "offers": 0, "responses": 0, "followups": 0, "duplicates": 0})
    def counts(self):
        jobs = store.load_jobs()
        return {"leads": sum(1 for j in jobs if j["status"] in store.LEAD_STATUSES),
                "applications": sum(1 for j in jobs if j["status"] in store.APPLICATION_STATUSES),
                "interviews": sum(1 for j in jobs if j["status"] == "interview"),
                "offers": sum(1 for j in jobs if j["status"] == "offer"),
                "responses": db.total(),
                "followups": len(followup.due_jobs(jobs, db.all_responses(), self._app.followup_days())),
                "duplicates": len(merge.find(jobs))}

    @_guarded(list)
    def leads(self):
        jobs = store.load_jobs()
        rows = [j for j in jobs if j["status"] in store.LEAD_STATUSES
                and (j.get("match_score") is None or j["match_score"] >= config.MIN_LEAD_SCORE)]
        rows.sort(key=lambda j: (-(j.get("match_score") or 0), j.get("date_posted", "")))
        rows.sort(key=lambda j: bool(j.get("prefilter")) and j.get("match_score") is None)     # skipped ones last
        threshold = self._app.threshold()
        return [{"id": j["id"], "score": j.get("match_score"),
                 "tier": j.get("match_tier", "") or ("skipped" if j.get("prefilter") and j.get("match_score") is None else ""),
                 "title": j["title"], "company": j["company"], "posted": j.get("date_posted", ""),
                 "location": j.get("location", ""), "source": (j.get("source") or "").split("/")[0],
                 "desired": self._asked_text(j), "status": j["status"],
                 "url": j.get("url", ""),
                 "basis": agent3_letters.text_basis(j) if j.get("match_score") is not None else "",
                 "stale_docs": self._app.stale_docs(j, threshold),
                 "before": self._app.score_before(j), "closed": j.get("closed") is True,
                 "letter": j.get("cover_letter_file", ""), "cv": j.get("tailored_cv_file", "")}
                for j in rows]

    @_guarded(list)
    def applications(self):
        jobs = store.load_jobs()
        rows = [j for j in jobs if j["status"] in store.APPLICATION_STATUSES]
        days, replies = self._app.followup_days(), followup.last_reply_by_job(db.all_responses())
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
        words = keywords.compare(description, self._cv.text()) if description else {"matched": [], "missing": []}
        replies = followup.last_reply_by_job(db.all_responses())
        letter = self._doc(config.LETTERS_DIR, j.get("cover_letter_file", ""))
        cv = self._doc(config.TAILORED_CV_DIR, j.get("tailored_cv_file", ""))
        return {
            "id": j["id"], "title": j["title"], "company": j["company"], "location": j.get("location", ""),
            "source": j.get("source", ""), "url": j.get("url", ""), "posted": j.get("date_posted", ""),
            "status": j["status"], "is_lead": j["status"] in store.LEAD_STATUSES,
            "score": j.get("match_score"), "tier": j.get("match_tier", ""),
            "score_before": self._app.score_before(j),
            "can_rescore": j["status"] in store.LEAD_STATUSES and j.get("match_score") is not None,
            # what the score rests on matters while you decide whether to apply; an application is past that
            "basis": agent3_letters.text_basis(j) if j["status"] in store.LEAD_STATUSES and j.get("match_score") is not None else "",
            "can_paste_text": j["status"] in store.LEAD_STATUSES and agent3_letters.text_basis(j) != "",
            "docs_stale": self._app.stale_docs(j), "threshold": self._app.threshold(),
            "closed": j.get("closed") is True and j["status"] in store.LEAD_STATUSES,
            "can_unshelve": bool(self._app.shelved(j)), "shelved_when": (self._app.shelved(j) or {}).get("when", ""),
            "reason": j.get("match_reason", ""), "description": description[:8000],
            "description_text": textfmt.readable(description[:8000]),
            "prefilter": j.get("prefilter", "") if j.get("match_score") is None else "",
            "hold": j.get("hold", "") if not j.get("cover_letter_file") else "",
            "score_queued": bool(j.get("prefilter_override")) and j.get("match_score") is None,
            "is_application": j["status"] in store.APPLICATION_STATUSES,
            "is_dismissed": j["status"] == store.NOT_INTERESTED,
            "letter_editable": self._app.editable_letter(j),
            "letter_old_format": self._app.old_format_letter(j),
            "event": dict(j.get("event") or {}),
            "thanks_due": planner.thanks_due(j),
            "apply_steps": list(j.get("apply_steps") or []),
            "has_answers": bool((j.get("form_answers") or {}).get("items")),
            "can_combine": self._app.can_combine(j),
            "company_notes": planner.company_notes(j.get("company", "")),
            "pay": salary.stated(j, salary.asked(j)[1]) or {}, "pay_text": self._pay_text(j),
            "desired_text": self._asked_text(j, " target"),
            "can_compare": self._app.comparable(j),
            "can_write_docs": self._app.can_write_documents(j) == "",
            "cv_check": [str(x) for x in (j.get("cv_check") or [])][:8] if j.get("tailored_cv_file") else [],
            "letter_check": [str(x) for x in (j.get("letter_check") or [])][:8] if j.get("cover_letter_file") else [],
            "has_prep": bool((j.get("interview_prep") or {}).get("questions")),
            "prep_edited": bool((j.get("interview_prep") or {}).get("edited")),
            "prep_made": (j.get("interview_prep") or {}).get("made", ""),
            "duplicate": self._duplicate_of(jobs, j),
            "matched": words["matched"], "missing": words["missing"],
            "desired": j.get("desired_monthly_czk", ""), "applied": j.get("date_applied", ""),
            "applied_from_email": j.get("date_applied_source") == "first email",
            "notes": j.get("notes", ""), "next_step": j.get("next_step", ""),
            "letter": letter["name"], "letter_pdf": letter["pdf"], "cv": cv["name"], "cv_pdf": cv["pdf"],
            "followup": followup.info(j, self._app.followup_days(), replies.get(j["id"])),
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
            j["status_by_hand"] = datetime.now().isoformat(timespec="seconds")      # emails older than this do not change it back
            j["notes"] = (f"[{today}] Marked {status.replace('_', ' ')} by you.\n" + (j.get("notes") or "")).strip()
            agent2_search.prune_applied_leads(jobs)
        return self._editor.change(job_id, go)

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
        return self._editor.change(job_id, go)

    # ── notes per company ───────────────────────────────────────
    def save_company_notes(self, company, fields):
        problem = planner.check_company_notes(dict(fields or {}))
        if problem:
            return {"ok": False, "msg": problem}
        ok = planner.save_company_notes(company, dict(fields or {}))
        return {"ok": ok} if ok else {"ok": False, "msg": "Notes need a company name."}

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

    def merge_jobs(self, keep_id, drop_id):
        def go(jobs, j):
            return {"ok": merge.merge(jobs, keep_id, drop_id)}
        return self._editor.change(keep_id, go)

    def keep_separate(self, a_id, b_id):
        def go(jobs, j):
            return {"ok": merge.keep_separate(jobs, a_id, b_id)}
        return self._editor.change(a_id, go)

    # ── actions ─────────────────────────────────────────────────
    def apply_job(self, job_id):
        def go(jobs, j):
            if j.get("status") not in store.LEAD_STATUSES and j.get("status") != "waiting":
                # "mark applied" is for a new job: an application that was answered is not set back to waiting by a stray press
                return {"ok": False, "msg": "This job is already among your applications. Change its status there."}
            j["status"] = "waiting"
            j["last_update"] = date.today().isoformat()
            j["status_by_hand"] = datetime.now().isoformat(timespec="seconds")      # emails older than this do not change it back
            if not j.get("date_applied"):
                j["date_applied"] = date.today().isoformat()
                j.pop("date_applied_source", None)          # you pressed "mark applied": this is the real day
            agent2_search.prune_applied_leads(jobs)
        result = self._editor.change(job_id, go)
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
        result = self._editor.change(job_id, go, render=False)
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
            self._desktop.open(target)
            return {"ok": True}
        own = config.COVER_LETTERS_DIR / os.path.basename(name)   # a letter you wrote yourself
        if kind == "letter" and own.is_file():
            self._desktop.open(own)
            return {"ok": True}
        return {"ok": False}

    def open_excel(self, which):
        p = {"leads": config.NEW_JOBS_EXCEL, "apps": config.EXCEL_PATH,
             "report": config.RESPONSES_REPORT}.get(which)
        if p and p.exists():
            self._desktop.open(p)
            return {"ok": True}
        return {"ok": False}

    def open_url(self, job_id):
        """Open a lead's job posting in the default browser (to go apply)."""
        job = store.find(store.load_jobs(), job_id)
        url = str((job or {}).get("url", "") or "").strip()
        if not url.startswith(("http://", "https://")):         # a job board hands this over: only a web page is opened
            return {"ok": False}
        self._desktop.open(url)
        self.note_opened(job_id)                                # the form you fill in next is most likely this job's
        return {"ok": True, "url": url}

    OPENED_FOR = 2 * 3600       # how long an opened posting says which form is in front (seconds)

    def note_opened(self, job_id: str, when: float | None = None) -> None:
        """Remember that the posting of this job was opened from the app (now, or at `when`)."""
        self._opened = (job_id, time.time() if when is None else when)

    def recently_opened(self) -> str:
        """The job whose posting was opened from the app within the last two hours ('' = none)."""
        job_id, when = self._opened
        return job_id if job_id and time.time() - when < self.OPENED_FOR else ""
