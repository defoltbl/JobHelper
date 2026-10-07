"""Dates to remember and notes per company.

* An application (or a lead) can carry one dated event: an interview, a
  deadline, a test task or anything else. Upcoming events are shown on the main
  screen and a notification goes out the day before and on the day.
* Notes are kept per company, not per job: who you spoke to, the salary they
  mentioned, what they asked. They show again when you apply to the same
  company later. Stored encrypted in data/company_notes.json.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from . import config, email_client, vault

KINDS = ["interview", "deadline", "test task", "call", "other"]
NOTE_FIELDS = ["contact", "salary", "asked", "notes"]
_OVER = {"rejected", "not_interested"}


# ── events ──────────────────────────────────────────────────────────────────
def check_event(day_text: str, time_text: str = "", kind: str = "interview", today: date | None = None) -> tuple[str, str]:
    """('', problem) or (ISO day, '') for what the user typed. The time is optional (HH:MM)."""
    try:
        day = date.fromisoformat((day_text or "").strip())
    except ValueError:
        return "", "Write the date as YYYY-MM-DD, for example 2026-10-15."
    if day < (today or date.today()):
        return "", "That date has already passed."
    if day > (today or date.today()) + timedelta(days=730):
        return "", "That date is more than two years away. Check the year."
    t = (time_text or "").strip()
    if t:
        try:
            datetime.strptime(t, "%H:%M")
        except ValueError:
            return "", "Write the time as HH:MM, for example 14:30, or leave it empty."
    if kind not in KINDS:
        return "", "Choose what kind of date this is."
    return day.isoformat(), ""


def set_event(job: dict[str, Any], day_text: str, time_text: str = "", kind: str = "interview", note: str = "") -> str:
    """Put a date on a job. Returns '' or the reason it was refused."""
    day, problem = check_event(day_text, time_text, kind)
    if problem:
        return problem
    job["event"] = {"date": day, "time": (time_text or "").strip(), "kind": kind, "note": (note or "").strip()[:200]}
    job.pop("event_notified", None)
    return ""


def clear_event(job: dict[str, Any]) -> None:
    job.pop("event", None)
    job.pop("event_notified", None)


def _when(job: dict[str, Any]) -> tuple[str, str]:
    e = job.get("event") or {}
    return e.get("date", ""), e.get("time", "") or "99:99"


def upcoming(jobs: list[dict[str, Any]], today: date | None = None, limit: int = 0) -> list[dict[str, Any]]:
    """Events from today on, soonest first: {id, company, title, date, time, kind, note, days, label}."""
    today = today or date.today()
    out = []
    for j in sorted((j for j in jobs if (j.get("event") or {}).get("date")), key=_when):
        e = j["event"]
        try:
            days = (date.fromisoformat(e["date"]) - today).days
        except ValueError:
            continue
        if days < 0 or j.get("status") in _OVER:
            continue                                # passed, or the application is closed
        label = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        out.append({"id": j["id"], "company": j.get("company", ""), "title": j.get("title", ""), "date": e["date"],
                    "time": e.get("time", ""), "kind": e.get("kind", "other"), "note": e.get("note", ""),
                    "days": days, "label": label})
    return out[:limit] if limit else out


def due_reminders(jobs: list[dict[str, Any]], today: date | None = None) -> list[dict[str, Any]]:
    """Events that are tomorrow or today and have not been announced for that day yet.
    Marks them as announced (mutates jobs), so each reminder is given once per day."""
    today = today or date.today()
    due = []
    for item in upcoming(jobs, today):
        if item["days"] > 1:
            continue
        job = next(j for j in jobs if j["id"] == item["id"])
        mark = f"{today.isoformat()}:{item['days']}"
        if job.get("event_notified") == mark:
            continue
        job["event_notified"] = mark
        due.append(item)
    return due


def reminder_text(item: dict[str, Any]) -> str:
    when = item["label"].capitalize() + (f" at {item['time']}" if item.get("time") else "")
    return f"{when}: {item['kind']} · {item['company'] or item['title']}"


# ── notes per company ───────────────────────────────────────────────────────
def _path():
    return config.DATA_DIR / "company_notes.json"


def _load() -> dict[str, dict[str, str]]:
    try:
        data = json.loads(vault.read_text(_path()))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, vault.VaultError):
        return {}


def company_key(company: str) -> str:
    return email_client.norm_company(company)


def company_notes(company: str) -> dict[str, str]:
    """The notes kept for this company (empty strings where nothing was written)."""
    saved = _load().get(company_key(company), {})
    return {f: str(saved.get(f, "")) for f in NOTE_FIELDS} | {"updated": str(saved.get("updated", "")),
                                                              "name": str(saved.get("name", company or ""))}


def save_company_notes(company: str, fields: dict[str, Any]) -> bool:
    key = company_key(company)
    if not key or key == "unknown":
        return False
    data = _load()
    entry = {f: str(fields.get(f, "") or "").strip()[:2000] for f in NOTE_FIELDS}
    if any(entry.values()):
        entry.update(name=company, updated=date.today().isoformat())
        data[key] = entry
    else:
        data.pop(key, None)                        # everything emptied: no entry
    config.ensure_dirs()
    vault.write_text(_path(), json.dumps(data, ensure_ascii=False, indent=2))
    return True
