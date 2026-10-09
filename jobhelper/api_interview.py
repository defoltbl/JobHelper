"""The window's back end, part: dates to remember, the thank-you note, answers for a job's
application form and the interview preparation."""
from __future__ import annotations


from . import (agent1_cv, cv_tailor, form_answers, prep_doc, config, db, followup, interview_prep, planner, store,
               vault)
from .api_base import _guarded


class InterviewApi:
    """Mixed into `ui_api.Api`; uses its `_change`, `_cv_text`, `_open` and `live`."""

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

    @_guarded(str)
    def prep_text(self, job_id):
        j = store.find(store.load_jobs(), job_id) or {}
        return interview_prep.as_text(j, j["interview_prep"]) if j.get("interview_prep") else ""
