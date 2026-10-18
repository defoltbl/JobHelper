"""Replies from companies: the list, one reply, filing it under an application, and follow-ups.

Part of the window's back end: the facade `ui_api.Api` hands calls to this service."""
from __future__ import annotations

from datetime import date

from .api_base import _guarded
from . import agent1_cv, agent2_search, agent5_responses, email_client, db, followup, store


class RepliesService:
    """Replies from companies: the list, one reply, filing it under an application, and follow-ups."""

    def __init__(self, app, editor, cv, desktop) -> None:
        """`app` is the facade (`ui_api.Api`): what this service needs from the others is asked through it."""
        self._app, self._editor, self._cv, self._desktop = app, editor, cv, desktop

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
                if current is not self._editor.live:
                    agent5_responses.annotate_progress(current)
                    agent2_search.prune_applied_leads(current)
            self._editor.change(job_id, go)
        return result

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
        result = self._editor.change(job_id, lambda jobs, j: followup.mark_sent(j))
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

    def filing_targets(self, text=""):
        """The applications a reply can be filed under, newest first: [{id, company, title, status, applied}].
        `text` narrows them to those whose company or title contains every word typed."""
        words = [w for w in str(text or "").lower().split() if w][:8]
        rows = [j for j in store.load_jobs() if j.get("status") in store.APPLICATION_STATUSES]
        rows = [j for j in rows if all(w in f"{j.get('company', '')} {j.get('title', '')}".lower() for w in words)]
        rows.sort(key=lambda j: j.get("date_applied") or "", reverse=True)
        return [{"id": j["id"], "company": j.get("company", ""), "title": j.get("title", ""), "status": j.get("status", ""),
                 "applied": j.get("date_applied", "")} for j in rows[:40]]

    def refile_response(self, msg_id, job_id):
        """File a reply under another application, or under none (job_id ''). The reply itself is not
        changed. The application it moves to follows the reply the usual way (an invitation makes it an
        interview, a rejection closes it); the one it leaves keeps its status, which only you can judge."""
        reply = next((x for x in db.all_responses() if x.get("msg_id") == msg_id), None)
        if not reply:
            return {"ok": False, "msg": "That reply is not on file any more."}
        job_id, was = str(job_id or ""), reply.get("job_id") or ""
        if job_id == was:
            return {"ok": False, "msg": "It is already filed there." if job_id else "It is not filed under any application."}
        jobs = store.load_jobs()
        old = store.find(jobs, was) if was else None
        if not job_id:
            db.set_response_job(msg_id, "")
            if old:
                self._editor.change(old["id"], lambda all_jobs, j: agent5_responses.annotate_progress(all_jobs))
            return {"ok": True, "msg": "The reply is not filed under any application now."
                                       + (f" {old['company']} keeps its status ({old['status']}): change it there if this reply had set it." if old else "")}
        target = store.find(jobs, job_id)
        if not target:
            return {"ok": False, "msg": "That application is not in the list any more."}
        if target.get("status") not in store.APPLICATION_STATUSES:
            return {"ok": False, "msg": "A reply is filed under an application. Mark that job as applied first."}
        # you said where it belongs: the reply is listed under that company from now on, if the reader had named another
        named = reply.get("company", "")
        fix = None if named and email_client.same_company(named, target.get("company", "")) else target.get("company", "")
        db.set_response_job(msg_id, job_id, fix)
        moved = {}

        def go(all_jobs, j):
            current = j.get("status", "")
            new_status = email_client.status_after(current, reply.get("stage", ""))
            if new_status and new_status != current:
                moved["from"], moved["to"] = current, new_status
                j["status"], j["last_update"] = new_status, date.today().isoformat()
            agent5_responses.annotate_progress(all_jobs)
        self._editor.change(job_id, go)
        text = f"Filed under {target.get('company', '')} · {target.get('title', '')}."
        if moved:
            text += f" Its status changed from {moved['from']} to {moved['to']}."
        if old and old["id"] != job_id:
            text += f" {old.get('company', '')} keeps its status ({old.get('status', '')}): change it there if this reply had set it."
        return {"ok": True, "msg": text}

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
