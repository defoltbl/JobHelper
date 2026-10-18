"""The last seven days in a few lines: new jobs, replies, what needs you.

Plain counting, no Claude. Shown at the top of Analytics and sent as one
notification after the weekly run.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import db, followup, planner, store


def _recent(text: str, since: date) -> bool:
    try:
        return date.fromisoformat((text or "")[:10]) >= since
    except ValueError:
        return False


def week(jobs: list[dict[str, Any]], responses: list[dict[str, Any]], followup_days: int = followup.DEFAULT_DAYS,
         today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    since = today - timedelta(days=7)
    leads = [j for j in jobs if j.get("status") in store.LEAD_STATUSES]
    new = [j for j in leads if _recent(j.get("date_found", ""), since)]
    applied = [j for j in jobs if j.get("status") in store.APPLICATION_STATUSES and _recent(j.get("date_applied", ""), since)]
    recent = [r for r in responses if db.received_at(r.get("received_date", "")).date() >= since]
    stage = lambda *names: sum(1 for r in recent if r.get("stage") in names)      # noqa: E731
    due = followup.due_jobs(jobs, responses, followup_days, today) if followup_days else []
    coming = [u for u in planner.upcoming(jobs, today) if u["days"] <= 7]
    thanks = [j for j in jobs if planner.thanks_due(j, today)]
    return {
        "from": since.isoformat(), "to": today.isoformat(),
        "new_jobs": len(new), "new_ready": sum(1 for j in new if j.get("status") == "letter_ready"),
        "ready_total": sum(1 for j in leads if j.get("status") == "letter_ready"),
        "applied": len(applied), "replies": len(recent),
        "invites": stage("interview", "assessment", "offer"), "rejections": stage("rejection"),
        "followups": len(due), "thanks": len(thanks),
        "coming": [{"id": u["id"], "text": planner.reminder_text(u)} for u in coming],
    }


def lines(w: dict[str, Any]) -> list[dict[str, str]]:
    """[{label, value, note}] for the window, in the order you would act on them."""
    plural = lambda n, one, many: f"{n} {one if n == 1 else many}"                  # noqa: E731
    out = [
        {"label": "New jobs found", "value": str(w["new_jobs"]),
         "note": f"{w['new_ready']} of them with a CV and letter ready" if w["new_jobs"] else "run a search to look for more"},
        {"label": "Ready to send", "value": str(w["ready_total"]), "note": "jobs in New Jobs with a CV and letter, waiting for you"},
        {"label": "Applications sent", "value": str(w["applied"]), "note": "marked as applied in the last 7 days"},
        {"label": "Replies received", "value": str(w["replies"]),
         "note": f"{plural(w['invites'], 'invitation', 'invitations')}, {plural(w['rejections'], 'rejection', 'rejections')}"
                 if w["replies"] else "none in the last 7 days"},
        {"label": "Follow-ups due", "value": str(w["followups"]), "note": "applications with no reply for a while"},
    ]
    if w["thanks"]:
        out.append({"label": "Thank-you notes to send", "value": str(w["thanks"]), "note": "after an interview or call"})
    for item in w["coming"]:
        out.append({"label": "Coming up", "value": "", "note": item["text"]})
    return out


def headline(w: dict[str, Any]) -> str:
    """One line for a notification."""
    parts = [f"{w['new_jobs']} new jobs ({w['ready_total']} ready to send)", f"{w['replies']} replies"]
    if w["invites"]:
        parts.append(f"{w['invites']} invitation" + ("" if w["invites"] == 1 else "s"))
    if w["followups"]:
        parts.append(f"{w['followups']} follow-up" + ("" if w["followups"] == 1 else "s") + " due")
    if w["coming"]:
        parts.append(f"{len(w['coming'])} date" + ("" if len(w["coming"]) == 1 else "s") + " coming up")
    return ", ".join(parts) + "."


def briefing_lines(w: dict[str, Any]) -> list[str]:
    """The assistant's lines when the app opens, from `week`: what is ready to send, invitations, follow-ups due, and
    the next three dates."""
    lines = []
    if w["ready_total"]:
        lines.append(f"{w['ready_total']} {'job is' if w['ready_total'] == 1 else 'jobs are'} ready to send" + (f" ({w['new_ready']} new this week)" if w["new_ready"] else ""))
    if w["invites"]:
        lines.append(f"{w['invites']} {'reply' if w['invites'] == 1 else 'replies'} this week that {'looks' if w['invites'] == 1 else 'look'} like an invitation")
    if w["followups"]:
        lines.append(f"{w['followups']} follow-up{'' if w['followups'] == 1 else 's'} due")
    return lines + [c["text"] for c in w["coming"][:3]]


MAX_NUDGES = 6


def nudges(jobs: list[dict[str, Any]], responses: list[dict[str, Any]], today: date) -> list[dict[str, str]]:
    """What the assistant reminds you of, at most MAX_NUDGES, each until you act on it (a job's "nudged" list): a form
    filled in but not marked applied, an interview within two days without preparation, an invitation in the last
    14 days without a date. [{kind, job_id, text}]"""
    out = []
    last: dict[str, dict[str, Any]] = {}
    for r in responses:
        if r.get("job_id") and r["job_id"] not in last:
            last[r["job_id"]] = r
    for j in jobs:
        what, done = f"{j.get('title', '')} at {j.get('company', '')}", set(j.get("nudged") or [])
        filled = str(j.get("form_filled") or "")
        if j.get("status") in store.LEAD_STATUSES and filled and filled < today.isoformat() and "apply" not in done:
            out.append({"kind": "apply", "job_id": j["id"], "text": f"You filled in the form for {what} on {filled} but did not mark it applied."})
        event = j.get("event") or {}
        if event.get("kind") == "interview" and event.get("date") and "prep" not in done and not (j.get("interview_prep") or {}).get("questions"):
            try:
                away = (date.fromisoformat(event["date"]) - today).days
            except ValueError:
                away = -1
            if 0 <= away <= 2:
                when = ("today", "tomorrow", "in two days")[away]
                out.append({"kind": "prep", "job_id": j["id"], "text": f"The interview for {what} is {when} and there is no preparation yet."})
        reply = last.get(j["id"])
        if reply and reply.get("stage") in ("interview", "assessment") and j.get("status") in store.APPLICATION_STATUSES - {"rejected"} \
                and not event.get("date") and "date" not in done:
            when = db.received_at(reply.get("received_date", "")).date()
            if 0 <= (today - when).days <= 14:
                out.append({"kind": "date", "job_id": j["id"], "text": f"{j.get('company', '')} invited you on {when.isoformat()} and no date is set for it."})
    return out[:MAX_NUDGES]

