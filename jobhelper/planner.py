"""Dates to remember and notes per company.

* An application (or a lead) can carry one dated event: an interview, a
  deadline, a test task or anything else. Upcoming events are shown on the main
  screen and a notification goes out the day before and on the day.
* Notes are kept per company, not per job: who you spoke to, the salary they
  mentioned, what they asked. They show again when you apply to the same
  company later. Stored encrypted in data/company_notes.json.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from . import email_client, store, trouble, vault

KINDS = ["interview", "deadline", "test task", "call", "other"]
NOTE_FIELDS = ["contact", "salary", "asked", "notes"]
NOTE_LIMITS = {"contact": 200, "salary": 200, "asked": 400, "notes": 2000}
NOTE_LABELS = {"contact": "Who you spoke to", "salary": "Salary mentioned", "asked": "What they asked", "notes": "Notes"}
MAX_EVENT_NOTE = 200
_OVER = {"rejected", store.NOT_INTERESTED}


# ── events ──────────────────────────────────────────────────────────────────
class EventCheck:
    """What the user typed for a dated event, checked: its ISO day, or the reason it is refused and the field that
    reason is about ("date", "time", "kind" or "note"), so the window marks that field and no other."""

    def __init__(self, day_text: str, time_text: str = "", kind: str = "interview", note: str = "", today: date | None = None) -> None:
        self.day, self.problem, self.field = "", "", ""
        self.time, self.kind, self.note = (time_text or "").strip(), kind, (note or "").strip()
        today = today or date.today()
        try:
            day = date.fromisoformat((day_text or "").strip())
        except ValueError:
            self._refuse("date", "Write the date as YYYY-MM-DD, for example 2026-10-15.")
            return
        if day < today:
            self._refuse("date", "That date has already passed.")
        elif day > today + timedelta(days=730):
            self._refuse("date", "That date is more than two years away. Check the year.")
        elif self.time and not self._is_time(self.time):
            self._refuse("time", "Write the time as HH:MM, for example 14:30, or leave it empty.")
        elif kind not in KINDS:
            self._refuse("kind", "Choose what kind of date this is.")
        elif len(self.note) > MAX_EVENT_NOTE:
            self._refuse("note", f"The note is {len(self.note)} characters long; the most is {MAX_EVENT_NOTE}. Shorten it.")
        else:
            self.day = day.isoformat()

    @staticmethod
    def _is_time(text: str) -> bool:
        try:
            datetime.strptime(text, "%H:%M")
        except ValueError:
            return False
        return True

    def _refuse(self, field: str, problem: str) -> None:
        self.field, self.problem = field, problem

    @property
    def ok(self) -> bool:
        return self.problem == ""

    def put_on(self, job: dict[str, Any]) -> "EventCheck":
        """Save it as the job's date when it is ok (its reminders start again); a refused one changes nothing."""
        if not self.ok:
            return self
        clear_event(job)
        job["event"] = {"date": self.day, "time": self.time, "kind": self.kind, "note": self.note}
        return self

    def answer(self) -> dict[str, Any]:
        """What the window is told: {ok} or {ok, msg, field}."""
        return {"ok": True} if self.ok else {"ok": False, "msg": self.problem, "field": self.field}


def check_event(day_text: str, time_text: str = "", kind: str = "interview", today: date | None = None) -> tuple[str, str]:
    """('', problem) or (ISO day, '') for what the user typed. The time is optional (HH:MM)."""
    check = EventCheck(day_text, time_text, kind, today=today)
    return check.day, check.problem


def set_event(job: dict[str, Any], day_text: str, time_text: str = "", kind: str = "interview", note: str = "") -> str:
    """Put a date on a job. Returns '' or the reason it was refused."""
    return EventCheck(day_text, time_text, kind, note).put_on(job).problem


def clear_event(job: dict[str, Any]) -> None:
    job.pop("event", None)
    job.pop("event_notified", None)
    job.pop("event_marks", None)


class Event:
    """One dated event of a job as it is saved ({date, time, kind, note}): its day, and its start when it has a time.
    The one place that reads them, for "Coming up", the reminders, the calendar file and the thank-you note."""

    def __init__(self, saved: dict[str, Any] | None) -> None:
        saved = saved or {}
        try:
            self.day: date | None = date.fromisoformat(str(saved.get("date") or ""))
        except ValueError:
            self.day = None
        try:
            clock = datetime.strptime(str(saved.get("time") or ""), "%H:%M").time()
        except ValueError:
            clock = None
        self.start: datetime | None = datetime.combine(self.day, clock) if self.day and clock else None

    def leaves_at(self) -> datetime | None:
        """When it leaves "Coming up": PASSED_AFTER after its start, or at the end of its day without a time (None: no date)."""
        if self.day is None:
            return None
        return self.start + PASSED_AFTER if self.start else datetime.combine(self.day + timedelta(days=1), datetime.min.time())

    def minutes_left(self, now: datetime) -> int | None:
        """Minutes until it starts; None without a time."""
        return int((self.start - now).total_seconds() // 60) if self.start else None

    def started(self, now: datetime) -> bool:
        return self.start is not None and now >= self.start


def _when(job: dict[str, Any]) -> tuple[str, str]:
    e = job.get("event") or {}
    return e.get("date", ""), e.get("time", "") or "99:99"


PASSED_AFTER = timedelta(hours=1)    # an event with a time stays for its first hour (it may be going on), then it has passed


def leaves_at(event: dict[str, Any]) -> datetime | None:
    """When an event leaves "Coming up": PASSED_AFTER after its time, or at the end of its day when it has
    no time. The window, the reminders and the widget all use this moment (None: no date)."""
    return Event(event).leaves_at()


def has_passed(event: dict[str, Any], now: datetime) -> bool:
    """True when an event with a time started more than PASSED_AFTER ago. An event without a time
    lasts the whole day (the date check covers it)."""
    e = Event(event)
    return e.start is not None and now >= e.leaves_at()


def upcoming(jobs: list[dict[str, Any]], today: date | None = None, limit: int = 0,
             now: datetime | None = None) -> list[dict[str, Any]]:
    """Events from today on, soonest first: {id, company, title, date, time, kind, note, days, label}.
    `now` (the clock when neither is given) also drops today's events whose time has passed;
    a caller that gives only `today` asks about the whole day."""
    if now is None and today is None:
        now = datetime.now()
    today = today or now.date()
    out = []
    for j in sorted((j for j in jobs if (j.get("event") or {}).get("date")), key=_when):
        e = j["event"]
        try:
            days = (date.fromisoformat(e["date"]) - today).days
        except ValueError:
            continue
        if days < 0 or j.get("status") in _OVER:
            continue                                # passed, or the application is closed
        if days == 0 and now is not None and has_passed(e, now):
            continue                                # today, but its time is over
        label = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        out.append({"id": j["id"], "company": j.get("company", ""), "title": j.get("title", ""), "date": e["date"],
                    "time": e.get("time", ""), "kind": e.get("kind", "other"), "note": e.get("note", ""),
                    "days": days, "label": label})
    return out[:limit] if limit else out


HOUR_STEPS = (180, 60)       # with a time set: also about three hours and one hour before


def _minutes_left(item: dict[str, Any], now: datetime) -> int | None:
    """Minutes until an event that has a time; None without one."""
    return Event(item).minutes_left(now)


def due_reminders(jobs: list[dict[str, Any]], today: date | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
    """Reminders that are due and were not given yet: once the day before, once on
    the day, and for an event with a time also about three hours and one hour
    before it. Marks them as given (mutates jobs). Each item carries `minutes`
    when it is one of the hour reminders."""
    now = now or (datetime.combine(today, datetime.min.time()) if today else datetime.now())
    today = today or now.date()
    due = []
    for item in upcoming(jobs, today, now=now):          # no "today" reminder for an interview that is already over
        if item["days"] > 1:
            continue
        job = next(j for j in jobs if j["id"] == item["id"])
        given = job.get("event_marks")
        if not isinstance(given, list):                       # the earlier single mark
            given = [job["event_notified"]] if job.get("event_notified") else []
        marks = [f"{today.isoformat()}:{item['days']}"]
        left = _minutes_left(item, now)
        hour_mark = None
        if left is not None and left > 0:
            step = next((s for s in sorted(HOUR_STEPS) if left <= s), None)
            if step:
                hour_mark = f"{item['date']}T{item['time']}:{step}m"
                marks.append(hour_mark)
        new = [m for m in marks if m not in given]
        if not new:
            continue
        job["event_marks"] = (given + new)[-12:]
        job["event_notified"] = marks[0]
        due.append(dict(item, minutes=left) if hour_mark in new else item)
    return due


def _in(minutes: int) -> str:
    if minutes < 60:
        return f"In {minutes} minutes" if minutes != 1 else "In 1 minute"
    hours, rest = divmod(minutes, 60)
    return ("In 1 hour" if hours == 1 else f"In {hours} hours") + (f" {rest} min" if rest >= 5 else "")


def reminder_text(item: dict[str, Any]) -> str:
    if item.get("minutes"):
        return f"{_in(item['minutes'])} ({item['time']}): {item['kind']} · {item['company'] or item['title']}"
    when = item["label"].capitalize() + (f" at {item['time']}" if item.get("time") else "")
    return f"{when}: {item['kind']} · {item['company'] or item['title']}"


# ── notes per company ───────────────────────────────────────────────────────
def company_key(company: str) -> str:
    return email_client.norm_company(company)


def check_company_notes(fields: dict[str, Any]) -> str:
    """'' or which field is too long (nothing is cut silently)."""
    for field, limit in NOTE_LIMITS.items():
        length = len(str((fields or {}).get(field, "") or "").strip())
        if length > limit:
            return f"“{NOTE_LABELS[field]}” is {length} characters long; the most is {limit}. Shorten it."
    return ""


class CompanyNotes:
    """The notes of every company, by company key; read from their file at each call.

    A file the data key cannot open shows as no notes, but a save stops with VaultError: it must not
    write the one company's notes over every other company's."""

    UNREADABLE = "The notes for companies cannot be read, so nothing was saved. The file is left as it is."

    def __init__(self, file: vault.JsonFile) -> None:
        self._file = file

    @property
    def path(self):
        return self._file.path

    def _read(self) -> dict[str, dict[str, str]]:
        data = self._file.read()
        return data if isinstance(data, dict) else {}

    def of(self, company: str) -> dict[str, str]:
        """The notes kept for this company (empty strings where nothing was written)."""
        try:
            saved = self._read().get(company_key(company), {})
        except vault.VaultError as e:
            trouble.note("company notes", e)
            saved = {}
        return {f: str(saved.get(f, "")) for f in NOTE_FIELDS} | {"updated": str(saved.get("updated", "")),
                                                                  "name": str(saved.get("name", company or ""))}

    def save(self, company: str, fields: dict[str, Any]) -> bool:
        key = company_key(company)
        if not key or key == "unknown" or check_company_notes(fields):
            return False
        data = self._read()
        entry = {f: str(fields.get(f, "") or "").strip() for f in NOTE_FIELDS}
        if any(entry.values()):
            entry.update(name=company, updated=date.today().isoformat())
            data[key] = entry
        else:
            data.pop(key, None)                        # everything emptied: no entry
        self._file.write(data)
        return True


COMPANY_NOTES = CompanyNotes(vault.JsonFile("company_notes.json"))


def company_notes(company: str) -> dict[str, str]:
    return COMPANY_NOTES.of(company)


def save_company_notes(company: str, fields: dict[str, Any]) -> bool:
    return COMPANY_NOTES.save(company, fields)


# ── a calendar file for a date, so the phone reminds you too ────────────────
def _ics_text(text: str) -> str:
    out = (text or "").replace("\r", "")
    for ch in ("\\", ";", ","):
        out = out.replace(ch, "\\" + ch)
    return out.replace("\n", "\\n")


def ics(job: dict[str, Any], now: datetime | None = None) -> str:
    """The job's date as an iCalendar event (opens in Calendar, which syncs to the phone).
    With a time: one hour, reminders a day and an hour before. Without: an all-day
    event, reminders at 9:00 the day before and at 9:00 on the day. '' if there is no date."""
    e = job.get("event") or {}
    event = Event(e)
    day = event.day
    if day is None:
        return ""
    title = f"{(e.get('kind') or 'other').capitalize()}: {job.get('company') or job.get('title') or 'JobHelper'}"
    details = "\n".join(x for x in (job.get("title", ""), e.get("note", ""), job.get("url", "")) if x)
    stamp = (now or datetime.now()).strftime("%Y%m%dT%H%M%S")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//JobHelper//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "BEGIN:VEVENT", f"UID:jobhelper-{job.get('id', '')}@jobhelper.local", f"DTSTAMP:{stamp}",
             f"SUMMARY:{_ics_text(title)}", f"DESCRIPTION:{_ics_text(details)}"]
    if event.start:
        start = event.start
        lines += [f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{start + timedelta(hours=1):%Y%m%dT%H%M%S}"]
        alarms = ["-P1D", "-PT1H"]
    else:                                               # no time: an all-day event
        lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
        alarms = ["-PT15H", "PT9H"]
    for trigger in alarms:
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_text(title)}", f"TRIGGER:{trigger}", "END:VALARM"]
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


# ── a thank-you note after an interview ─────────────────────────────────────
def thanks_due(job: dict[str, Any], today: date | None = None, now: datetime | None = None) -> bool:
    """An interview or call that has taken place (its day has come and, when a time is
    set, that time has passed), for an application still open, not thanked yet."""
    e = job.get("event") or {}
    if e.get("kind") not in ("interview", "call") or job.get("status") in _OVER:
        return False
    event = Event(e)
    if event.day is None:
        return False
    today = today or date.today()
    if event.day > today or job.get("thanked_for") == e.get("date"):
        return False
    if event.day == today and event.start:              # today, with a time: only once it has started
        return event.started(datetime.combine(today, (now or datetime.now()).time()))
    return True


def thanks_draft(job: dict[str, Any], name: str = "", contact: str = "") -> dict[str, str]:
    """A short thank-you for the user to send themselves (plain code, no Claude)."""
    role = (job.get("title") or "the role").strip()
    company = (job.get("company") or "your company").strip().rstrip(".")
    e = job.get("event") or {}
    first = re.split(r"[,(\-–]", contact or "")[0].strip().split(" ")[0] if (contact or "").strip() else ""
    what = "call" if e.get("kind") == "call" else "interview"
    body = (
        f"Dear {first or company + ' team'},\n\n"
        f"Thank you for the {what} about the {role} position. I enjoyed our conversation and learning more "
        f"about the team and the work at {company}.\n\n"
        "The role sounds like a very good match for what I want to do next, and I would be glad to continue "
        "in the process. If you need anything else from me, please let me know.\n\n"
        "Kind regards,\n"
        f"{name or '[Your name]'}"
    )
    return {"subject": f"Thank you: {role}", "body": body}


def mark_thanked(job: dict[str, Any], today: date | None = None) -> None:
    day = (today or date.today()).isoformat()
    job["thanked_for"] = (job.get("event") or {}).get("date", day)
    job["last_update"] = day
    store.add_note(job, "Sent a thank-you note.", day)
