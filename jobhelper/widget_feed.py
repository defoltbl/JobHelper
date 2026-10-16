"""The summary the macOS widget shows.

The widget (widget/JobHelperWidget.swift) runs in macOS's sandbox: it cannot open the app's
encrypted data, and it may read one folder only, ~/Library/Application Support/JobHelper/widget.
The app writes a small summary there: how many new jobs, applications, interviews, offers and
follow-ups there are; the next dates (kind, company, role, day, time); the last run; the Claude
usage left; and the weekly run. Nothing else: no letters, no CV, no mail, no notes. The file is
readable by you only (0600).
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config, schedule, store

FILE_NAME = "snapshot.json"
VERSION = 1
NEXT_DATES = 3


def folder() -> Path:
    """The widget's folder, beside the data folder in the data home."""
    return config.HOME.library / "widget"


class WidgetFeed:
    """Builds the summary from the app's back end (`ui_api.Api`) and writes it for the widget."""

    def __init__(self, app, target: Path) -> None:
        self._app = app
        self._target = Path(target)

    @property
    def file(self) -> Path:
        return self._target / FILE_NAME

    def snapshot(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now()
        counts = self._app.counts()
        jobs = store.load_jobs()
        usage = self._app.usage_info()
        run = self._app.last_run()
        return {
            "version": VERSION,
            "updated": now.isoformat(timespec="seconds"),
            "counts": {"leads": int(counts.get("leads", 0)), "applications": int(counts.get("applications", 0)),
                       "interviews": sum(1 for j in jobs if j.get("status") == "interview"),
                       "offers": sum(1 for j in jobs if j.get("status") == "offer"),
                       "followups": int(counts.get("followups", 0)), "responses": int(counts.get("responses", 0))},
            "next": [{"kind": str(e.get("kind") or ""), "company": str(e.get("company") or ""), "title": str(e.get("title") or ""),
                      "date": str(e.get("date") or ""), "time": str(e.get("time") or "")}
                     for e in self._app.upcoming(NEXT_DATES)],
            "last_run": {"when": str(run.get("when") or ""), "found": _number(run.get("found")),
                         "letters": _number(run.get("letters"))} if run else None,
            "usage": {"five_hour_left": _left(usage.get("five_hour_used")), "week_left": _left(usage.get("seven_day_used"))},
            "weekly": str(schedule.read_schedule().get("label") or "Off"),
        }

    def write(self) -> Path:
        """Write the summary (a draft first, then swapped in, so the widget never reads half a file)."""
        self._target.mkdir(parents=True, exist_ok=True)
        draft = self.file.with_name(FILE_NAME + ".draft")
        draft.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=1), encoding="utf-8")
        os.chmod(draft, 0o600)
        draft.replace(self.file)
        return self.file


def _number(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _left(used) -> int | None:
    """The percent of a Claude limit that is left (None when not known yet)."""
    return None if used is None else max(0, min(100, 100 - int(used)))
