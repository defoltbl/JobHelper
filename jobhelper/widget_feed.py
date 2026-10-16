"""The summary the macOS widget shows.

The widget (widget/JobHelperWidget.swift) runs in macOS's sandbox: it cannot open the app's
encrypted data, and it may read one folder only, ~/Library/Application Support/JobHelper/widget.
The app writes a small summary there: how many new jobs, applications, interviews, offers and
follow-ups there are; the next five dates (kind, company, role, day, time); the last run; the Claude
usage left; and the weekly run. Nothing else: no letters, no CV, no mail, no notes. The file is
readable by you only (0600).

After writing, the app asks macOS to redraw the widget at once (WidgetReloader); otherwise the widget
would show the new summary only at its next scheduled read, up to 15 minutes later.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import app_info, config, schedule, store, trouble

FILE_NAME = "snapshot.json"
VERSION = 1
NEXT_DATES = 5          # the large widget shows three, the extra large five


def folder() -> Path:
    """The widget's folder, beside the data folder in the data home."""
    return config.HOME.library / "widget"


class WidgetReloader:
    """Asks macOS to redraw the widget at once after the app wrote a new summary.

    Only the app that holds a widget may ask WidgetKit for that, from its own process: the built app
    loads a small library for it (widget/WidgetReload.swift, in Contents/Frameworks). macOS allows each
    app a limited number of such reloads a day, so it asks only when something the widget shows changed:
    always for the numbers, the dates, the last run and the weekly run; for the Claude usage alone at most
    every USAGE_EVERY seconds. Outside the built app (tests, `python app_qt.py`) it asks nothing."""

    USAGE_EVERY = 30 * 60

    def __init__(self, reload: Callable[[], Any] | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._reload, self._clock = reload, clock
        self._asked: tuple[dict[str, Any], float] | None = None      # the summary it last asked for, and when

    @classmethod
    def of_the_app(cls) -> "WidgetReloader":
        """The reloader of the running app: the library is in the built app's Frameworks folder."""
        if not getattr(sys, "frozen", False):
            return cls(None)
        library = Path(sys.executable).resolve().parent.parent / "Frameworks" / app_info.WIDGET_RELOAD
        return cls(_LibraryCall(library, "jobhelper_reload_widgets") if library.is_file() else None)

    @staticmethod
    def _shown(summary: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in summary.items() if k != "updated"}

    def needed(self, summary: dict[str, Any]) -> bool:
        if self._asked is None:
            return True
        before, at = self._asked
        now = self._shown(summary)
        if {k: v for k, v in now.items() if k != "usage"} != {k: v for k, v in before.items() if k != "usage"}:
            return True
        return now.get("usage") != before.get("usage") and self._clock() - at >= self.USAGE_EVERY

    def after_write(self, summary: dict[str, Any]) -> bool:
        """Ask for a redraw when it is needed. True when it asked."""
        if self._reload is None or not self.needed(summary):
            return False
        try:
            self._reload()
        except (OSError, AttributeError) as e:
            trouble.note("asking macOS to redraw the widget", e)
            return False
        self._asked = (self._shown(summary), self._clock())
        return True


class _LibraryCall:
    """A function without arguments in a library, loaded the first time it is called."""

    def __init__(self, path: Path, name: str) -> None:
        self._path, self._name = path, name
        self._function = None

    def __call__(self) -> None:
        if self._function is None:
            self._function = getattr(ctypes.CDLL(str(self._path)), self._name)
            self._function.restype = None
        self._function()


class WidgetFeed:
    """Builds the summary from the app's back end (`ui_api.Api`) and writes it for the widget."""

    def __init__(self, app, target: Path, reloader: WidgetReloader | None = None) -> None:
        self._app = app
        self._target = Path(target)
        self._reloader = reloader

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
        summary = self.snapshot()
        draft = self.file.with_name(FILE_NAME + ".draft")
        draft.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        os.chmod(draft, 0o600)
        draft.replace(self.file)
        if self._reloader is not None:
            self._reloader.after_write(summary)
        return self.file


def _number(value) -> int:
    """A count, also from the way the last run writes it ("+27 new" is 27)."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    found = re.search(r"\d+", str(value or ""))
    return int(found.group()) if found else 0


def _left(used) -> int | None:
    """The percent of a Claude limit that is left (None when not known yet)."""
    return None if used is None else max(0, min(100, 100 - int(used)))
