"""About you: the few facts about the person that the app may state besides the CV.

The salary they ask for, their right to work, when they can start, and what they really did in
each job beyond what the CV says. They are kept with the Options and edited in their own window.
This module owns what that window shows beyond plain fields: what a start date will turn into,
the usual answers about the right to work, the app's own salary estimate, and the work notes
per job, which become one text that interviews, form answers and the claim checks read.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from . import config, details, filters, places, salary

KEYS = ("salary_target", "salary_currency", "salary_by_role", "about_right_to_work", "about_start", "about_experience",
        "about_jobs")


class WorkNotes:
    """What the person wrote about their work: a note for each job of My details ({job, notes}) and a general one.
    A note keeps its job's name, so it is not lost when the job is renamed or removed in My details."""

    MAX_TOTAL = config.MAX_EXPERIENCE_NOTES          # all notes together, as text() gives them: the room they get in a request
    # a box is named "title, employer" from My details, so its name can be as long as those two fields together
    MAX_JOB_NAME = sum(most for key, _label, most in details.ROWS["experience"] if key in ("title", "employer")) + 2

    def __init__(self, per_job: list[dict[str, str]] | None = None, general: str = "") -> None:
        self.per_job = [{"job": str(n.get("job") or "").strip(), "notes": str(n.get("notes") or "").strip()}
                        for n in per_job or [] if isinstance(n, dict)]
        self.general = str(general or "").strip()

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> "WorkNotes":
        jobs = options.get("about_jobs")
        return cls(jobs if isinstance(jobs, list) else [], str(options.get("about_experience") or ""))

    @staticmethod
    def job_name(row: dict[str, Any]) -> str:
        """How a job of My details is named here: "Junior analyst, Northwind"."""
        return ", ".join(p for p in (str(row.get("title") or "").strip(), str(row.get("employer") or "").strip()) if p)

    def boxes(self, my_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """One box per job of My details, in its order, then a box for each note of a job no longer there
        ({job, notes, earlier}). The window shows these; nothing written is dropped."""
        written = {n["job"]: n["notes"] for n in self.per_job if n["job"]}
        names = [self.job_name(r) for r in my_jobs if self.job_name(r)]
        out = [{"job": name, "notes": written.get(name, ""), "earlier": False} for name in dict.fromkeys(names)]
        out += [{"job": job, "notes": text, "earlier": True} for job, text in written.items() if job not in names and text]
        return out

    def size(self) -> int:
        """How long the notes are as everything reads them (text()): each job's name and the gaps between them count too."""
        return len(self._joined())

    def problem(self) -> str:
        """'' or why these notes cannot be saved."""
        if any(n["notes"] and not n["job"] for n in self.per_job):
            return "A note on a job needs the job's name."
        if any(len(n["job"]) > self.MAX_JOB_NAME for n in self.per_job):
            return f"A job's name takes up to {self.MAX_JOB_NAME} characters."
        if self.size() > self.MAX_TOTAL:
            return (f"The notes about your work are {self.size()} characters together; the most is {self.MAX_TOTAL}. "
                    "Shorten some of them.")
        return ""

    def as_options(self) -> dict[str, Any]:
        return {"about_jobs": [n for n in self.per_job if n["job"] and n["notes"]], "about_experience": self.general}

    def _joined(self) -> str:
        parts = [f"At {n['job']}: {n['notes']}" for n in self.per_job if n["job"] and n["notes"]]
        if self.general:
            parts.append(self.general)
        return "\n\n".join(parts)

    def text(self) -> str:
        """The notes as one text, each job's under its name: what interviews, form answers and the claim checks read.
        Never cut: notes longer than MAX_TOTAL are refused when they are saved (problem)."""
        return self._joined()


class AboutYou:
    """The About you facts as saved with the Options, and what the window says about them."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self._o = dict(options if options is not None else config.ui_settings())
        self.notes = WorkNotes.from_options(self._o)

    @property
    def home(self) -> str:
        """The country of the search ('' when not known): Placement's one rule."""
        return filters.Placement(str(self._o.get("where") or ""), str(self._o.get("country") or "")).home

    def right_to_work_choices(self) -> list[str]:
        """The usual answers, worded for this person's country; a press fills the field, which they can still change."""
        country = places.shown(self.home) if self.home else "the country of the job"
        return [f"Full right to work in {country}", "EU/EEA citizen: no work permit needed",
                f"Work permit for {country}", "Need visa sponsorship"]

    @staticmethod
    def start_preview(text: str, today: date | None = None) -> dict[str, Any]:
        """What forms will get for "You can start": {ok, text}. The date is worked out by the same rule the assistant uses."""
        from . import form_fill
        words = " ".join(str(text or "").split())
        if not words:
            return {"ok": True, "text": ""}
        day, worked = form_fill.start_day(words, today)
        if day is None and form_fill.start_day(words, date.min)[0] is not None:      # a day the rule reads, but it has passed
            return {"ok": False, "text": f"“{words}” has passed. Write a date from today on, or a time from now (two weeks, "
                                         "one month)."}
        if day is None:
            return {"ok": False, "text": f"Forms cannot get a date from “{words}”. Write a date (2026-11-01) or a time "
                                         "from now (two weeks, one month), or leave it to forms to ask."}
        when = f"{day.day} {day:%B %Y}"
        return {"ok": True, "text": f"Forms get: {when}" + (" (worked out from your words: check it in each form)" if worked else "")}

    def roles(self) -> list[str]:
        """The kinds of role an estimate is shown for: the roles you want, else the ones you search for (Options)."""
        return [str(r) for r in (self._o.get("wanted_roles") or self._o.get("queries") or [])]

    def salary_estimates(self, roles: list[str], seniority: str = "junior") -> dict[str, Any]:
        """The app's own monthly estimate for each kind of role ({available, note, rows: [{role, amount, text}]}), used when
        you give no figure. It exists only for software roles while the search is in Czechia (salary.estimate_available)."""
        if not salary.estimate_available(self._o):
            return {"available": False, "rows": [],
                    "note": "The app has no estimate for this country. With 0, forms leave the salary for you to fill in."}
        rows = []
        for role in dict.fromkeys(str(r).strip() for r in roles or [] if str(r).strip()):
            monthly, _year = salary.estimate(role, seniority)
            if monthly:
                rows.append({"role": role, "amount": monthly, "text": salary.money(monthly, "CZK")})
        note = ("With 0, forms give the app's estimate for the job's kind of role. The roles are your kinds of role in Options; "
                "Change makes one your own figure, in the currency you chose." if rows else
                "The app has an estimate only for software roles, and none of your roles is one. With 0, forms leave it to you.")
        return {"available": True, "rows": rows[:6], "note": note}

    def page(self, my_details: dict[str, Any], seniority: str = "junior") -> dict[str, Any]:
        """Everything the window needs besides the plain values."""
        return {"right_choices": self.right_to_work_choices(), "start": self.start_preview(str(self._o.get("about_start") or "")),
                "estimates": self.salary_estimates(self.roles(), seniority),
                "boxes": self.notes.boxes(details.jobs(my_details)), "general": self.notes.general,
                "max_notes": WorkNotes.MAX_TOTAL}


def work_notes_text(options: dict[str, Any] | None = None) -> str:
    """The person's own words about their work, as one text (see WorkNotes.text)."""
    return WorkNotes.from_options(config.ui_settings() if options is None else options).text()
