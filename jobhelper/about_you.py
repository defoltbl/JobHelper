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

from . import claims, config, details, filters, places, salary

KEYS = ("salary_target", "salary_currency", "salary_by_role", "about_right_to_work", "about_start", "about_experience",
        "about_jobs")


class WorkNotes:
    """What the person wrote about their work: a note for each job ({job, notes}) and a general one.

    The jobs are the ones the master CV names (`claims.EmployerCheck.job_names`), else the jobs of My details. A box can
    be renamed or removed: a saved note keeps the name the CV gave its job (`from`), so it stays with that job; a
    removed job is kept as `removed` so it does not come back, and can be brought back. A note keeps its job's name,
    so it is not lost when the job leaves the CV or My details."""

    MAX_TOTAL = config.MAX_EXPERIENCE_NOTES          # all notes together, as text() gives them: the room they get in a request
    # a box is named "title, employer": from those two fields of My details, or from a CV's heading (read only in its
    # first 160 characters, so never longer)
    MAX_JOB_NAME = sum(most for key, _label, most in details.ROWS["experience"] if key in ("title", "employer")) + 2

    def __init__(self, per_job: list[dict[str, str]] | None = None, general: str = "") -> None:
        self.per_job = [{"job": str(n.get("job") or "").strip(), "notes": str(n.get("notes") or "").strip(),
                         "from": str(n.get("from") or "").strip(), "removed": n.get("removed") is True}
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

    def boxes(self, names: list[str]) -> list[dict[str, Any]]:
        """One box per job named (the CV's, else My details'), in its order, with your name for it and whether you removed
        it, then a box for each note of a job no longer named ({job, from, notes, earlier, removed}). The window shows
        these; nothing written is dropped."""
        out, used = [], set()
        for name in dict.fromkeys(n for n in names if n):
            at = next((i for i, n in enumerate(self.per_job) if i not in used and n["from"] == name), -1)
            if at < 0:                                # a note from before this change: its job's name, written as My details had it
                at = next((i for i, n in enumerate(self.per_job)
                           if i not in used and not n["from"] and self.same_job(n["job"], name)), -1)
            saved = self.per_job[at] if at >= 0 else None
            if at >= 0:
                used.add(at)
            out.append({"job": saved["job"] if saved and saved["job"] else name, "from": name,
                        "notes": saved["notes"] if saved else "", "earlier": False, "removed": bool(saved and saved["removed"])})
        out += [{"job": n["job"], "from": n["from"], "notes": n["notes"], "earlier": True, "removed": False}
                for i, n in enumerate(self.per_job) if i not in used and n["job"] and n["notes"] and not n["removed"]]
        return out

    @staticmethod
    def same_job(saved: str, named: str) -> bool:
        """Whether a note saved under one name is about the job named the other way: the same words in any case
        ("Junior analyst, Northwind" and "Junior Analyst, Northwind"), or the same title at an employer whose name one of
        them gives in full ("… , Northwind" and "… , Northwind Traders")."""
        a, b = (" ".join(x.casefold().split()) for x in (saved, named))
        if a == b:
            return True
        (ta, _, ea), (tb, _, eb) = a.partition(", "), b.partition(", ")
        return bool(ta and ea and eb) and ta == tb and (ea.startswith(eb + " ") or eb.startswith(ea + " "))   # "Acme" ≠ "Acmeville"

    def size(self) -> int:
        """How long the notes are as everything reads them (text()): each job's name and the gaps between them count too."""
        return len(self._joined())

    def problem(self) -> str:
        """'' or why these notes cannot be saved."""
        if any((n["notes"] or n["from"]) and not n["job"] and not n["removed"] for n in self.per_job):
            return "A job needs a name. Write one, or remove the job."
        named = [n["job"].casefold() for n in self.per_job if n["job"] and not n["removed"]]
        if len(named) != len(set(named)):
            return "Two jobs have the same name. Give each its own name, so each note stays with its job."
        if any(len(n["from"]) > self.MAX_JOB_NAME for n in self.per_job):
            return "A job's name from the CV is too long to keep."
        if any(len(n["job"]) > self.MAX_JOB_NAME for n in self.per_job):
            return f"A job's name takes up to {self.MAX_JOB_NAME} characters."
        if self.size() > self.MAX_TOTAL:
            return (f"The notes about your work are {self.size()} characters together; the most is {self.MAX_TOTAL}. "
                    "Shorten some of them.")
        return ""

    def as_options(self) -> dict[str, Any]:
        """What is saved: notes, and a job you renamed or removed (so it stays so); a plain empty box is not kept."""
        kept = [n for n in self.per_job if (n["job"] and n["notes"] and not n["removed"]) or (n["from"] and n["removed"])
                or (n["from"] and n["job"] and n["job"] != n["from"])]
        return {"about_jobs": [{k: v for k, v in n.items() if v} for n in kept], "about_experience": self.general}

    def _joined(self) -> str:
        parts = [f"At {n['job']}: {n['notes']}" for n in self.per_job if n["job"] and n["notes"] and not n["removed"]]
        if self.general:
            parts.append(self.general)
        return "\n\n".join(parts)

    def text(self) -> str:
        """The notes as one text, each job's under its name: what interviews, form answers and the claim checks read.
        Never cut: notes longer than MAX_TOTAL are refused when they are saved (problem)."""
        return self._joined()


class AboutYou:
    """The About you facts as saved with the Options, and what the window says about them."""

    # why each part is worth filling in, and where the app uses it: the window shows these words as they stand
    USES = {
        "salary": "Why: many application forms ask what salary you expect. Used in: the salary field of forms, form answers, "
                  "and Insights, which compares what postings pay with it. 0 = the app's estimate below, where it has one.",
        "right": "Why: forms and recruiters ask whether you may work here. Used in: cover letters and form answers. "
                 "Empty = never mentioned.",
        "start": "Why: forms ask when you can start. Used in: cover letters say it as you write it, form answers, and forms "
                 "get a date. Empty = never mentioned.",
        "work": "Why: the app states only what your CV or these notes say, so your real work here lets letters and answers use "
                "more of it. Used in: cover letters and the adapted CV (a claim these notes back is allowed), form answers, "
                "interview preparation and the assistant's answers. In English; write only what is true.",
    }

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

    def page(self, my_details: dict[str, Any], seniority: str = "junior", cv_text: str = "") -> dict[str, Any]:
        """Everything the window needs besides the plain values."""
        return {"right_choices": self.right_to_work_choices(), "start": self.start_preview(str(self._o.get("about_start") or "")),
                "estimates": self.salary_estimates(self.roles(), seniority),
                **self.job_boxes(my_details, cv_text), "general": self.notes.general,
                "max_notes": WorkNotes.MAX_TOTAL, "max_job_name": WorkNotes.MAX_JOB_NAME, "uses": dict(self.USES),
                "jobs_from_text": dict(self.JOBS_FROM)}

    def job_boxes(self, my_details: dict[str, Any], cv_text: str = "") -> dict[str, Any]:
        """The work-note boxes and where their jobs came from: the master CV's positions, else My details ({boxes, jobs_from})."""
        from_cv = claims.EmployerCheck.job_names(cv_text)
        names = from_cv or [WorkNotes.job_name(r) for r in details.jobs(my_details)]
        return {"boxes": self.notes.boxes(names), "jobs_from": "cv" if from_cv else ("details" if names else "")}

    JOBS_FROM = {   # what the window says about where the boxes came from (job_boxes' jobs_from)
        "cv": "The jobs are the ones the app could read in your master CV (a line with a title, an employer and dates). Rename "
              "a box to name a job your way, or remove a job you do not want notes for. A job written another way is not "
              "listed: write about it under Other work.",
        "details": "The app could read no jobs in your master CV, so the jobs are the ones in My details. Rename or remove a "
                   "box as you need.",
    }


def work_notes_text(options: dict[str, Any] | None = None) -> str:
    """The person's own words about their work, as one text (see WorkNotes.text)."""
    return WorkNotes.from_options(config.ui_settings() if options is None else options).text()
