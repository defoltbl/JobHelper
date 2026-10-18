"""Follow-up reminders for applications that got no reply.

An application is due when it is still 'waiting' and nothing has happened for
N days - counted from a date that is really known: the day you applied, the last
email from the company, or your last follow-up. Applications whose date is not
known are never flagged, and after STALE_DAYS of silence an application is
treated as gone quiet rather than nagged about. The draft email is built
from a fixed template (no model call) and is only shown for the user to copy -
the app never sends mail.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from . import store

DEFAULT_DAYS = 10
STALE_DAYS = 45          # longer silence than this: a follow-up no longer makes sense


def _day(text: str) -> date | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).date()
    except (TypeError, ValueError):
        return None


def saved_days() -> int:
    """After how many days of silence a follow-up is due, as set in Options (0 = never); DEFAULT_DAYS when unset."""
    from . import config
    try:
        return max(0, int(config.ui_settings().get("followup_days", DEFAULT_DAYS)))
    except (TypeError, ValueError):
        return DEFAULT_DAYS


def last_reply_by_job(responses: list[dict[str, Any]]) -> dict[str, date]:
    """job id -> day of the latest stored reply."""
    out: dict[str, date] = {}
    for r in responses:
        day, jid = _day(r.get("received_date", "")), r.get("job_id") or ""
        if jid and day and (jid not in out or day > out[jid]):
            out[jid] = day
    return out


def info(job: dict[str, Any], days: int = DEFAULT_DAYS, last_reply: date | None = None,
         today: date | None = None) -> dict[str, Any]:
    """Follow-up state of one job:
    {due, stale, days_waiting, since, had_reply, followed_up}."""
    today = today or date.today()
    # Only real events count. "date_found" / "last_update" are when the app saw
    # the record (for imported applications: the import day), not when you applied.
    applied = _day(job.get("date_applied", ""))
    if store.applied_on_import(job):
        applied = None          # imported from your letters folder: that date is the import day
    marks = [d for d in (applied, last_reply, _day(job.get("followup_date", ""))) if d]
    since = max(marks) if marks else None
    waiting = max(0, (today - since).days) if since else 0
    open_wait = job.get("status") == "waiting" and since is not None and days > 0
    stale = open_wait and waiting > max(STALE_DAYS, days)
    due = open_wait and not stale and waiting >= days
    return {"due": due, "stale": stale, "days_waiting": waiting, "since": since.isoformat() if since else "",
            "had_reply": last_reply is not None, "followed_up": job.get("followup_date", "")}


def due_jobs(jobs: list[dict[str, Any]], responses: list[dict[str, Any]], days: int = DEFAULT_DAYS,
             today: date | None = None) -> list[dict[str, Any]]:
    replies = last_reply_by_job(responses)
    return [j for j in jobs if info(j, days, replies.get(j.get("id", "")), today)["due"]]


def candidate_name(profile: dict[str, Any] | None, cv_file: str = "") -> str:
    """The name to sign with: from the profile, else from a CV file name like
    'FirstnameLastname_CV_EN.docx'."""
    name = str((profile or {}).get("name") or "").strip()
    if name:
        return name
    stem = re.split(r"[_\-. ]", cv_file or (profile or {}).get("_cv_file", "") or "")[0]
    words = re.findall(r"[A-Z][a-z]+", stem)
    return " ".join(words) if len(words) >= 2 else ""


def draft(job: dict[str, Any], name: str = "", today: date | None = None) -> dict[str, str]:
    """A short, polite follow-up for the user to send themselves."""
    role = (job.get("title") or "the role").strip()
    company = (job.get("company") or "your company").strip().rstrip(".")      # "s.r.o." must not end a sentence twice
    applied = _day(job.get("date_applied", ""))
    when = f" on {applied.day} {applied.strftime('%B %Y')}" if applied else " recently"
    body = (
        f"Dear {company} hiring team,\n\n"
        f"I applied for the {role} position{when} and wanted to follow up on my application. "
        f"I am still very interested in the role and in joining {company}.\n\n"
        "Could you let me know whether there is an update on the process, or if I can provide "
        "any further information? I am available for a call at a time that suits you.\n\n"
        "Thank you for your time.\n\n"
        "Kind regards,\n"
        f"{name or '[Your name]'}"
    )
    return {"subject": f"Follow-up on my application: {role}", "body": body}


def mark_sent(job: dict[str, Any], today: date | None = None) -> None:
    """Note that the user followed up today; the reminder clock starts again."""
    day = (today or date.today()).isoformat()
    job["followup_date"] = day
    job["last_update"] = day
    job["notes"] = (f"[{day}] Followed up by email.\n" + (job.get("notes") or "")).strip()


def timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")
