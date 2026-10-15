"""The small objects every part of the window's back end shares.

Each one has one job and keeps its own state:

- `Desktop` opens a file, a folder or a web page, or shows a file in Finder.
- `CvSource` reads the master CV (kept until the file changes) and the person's name.
- `JobEditor` changes one saved job by hand, and the same job in the list of a run in progress.

The services of `ui_api` receive these in their constructor, so a test replaces one class
(`Desktop.open`, `CvSource.text`) instead of reaching into the services.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Callable

from . import agent1_cv, agent4_tracker, followup, store, trouble


class Desktop:
    """Opens what the person asked to see. A failure is noted, never raised: the window says it."""

    def open(self, path) -> None:
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:  # noqa: BLE001 - the window says "couldn't open"; the reason is kept
            trouble.note("opening a file or folder", e)

    def reveal(self, path) -> None:
        """Show a file in its folder (selected in Finder), so it is easy to drag into a form."""
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            else:
                self.open(os.path.dirname(str(path)))
        except Exception as e:  # noqa: BLE001
            trouble.note("showing a file in its folder", e)


class CvSource:
    """The master CV as text, read again only when the file changes."""

    def __init__(self) -> None:
        self._cache: tuple[str, float, str] = ("", 0.0, "")

    def text(self) -> str:
        try:
            path = agent1_cv.find_cv()
            if not path:
                return ""
            stamp = path.stat().st_mtime
            if self._cache[:2] != (str(path), stamp):
                self._cache = (str(path), stamp, agent1_cv.read_cv_text(path))
            return self._cache[2]
        except Exception:  # noqa: BLE001 - no CV is an empty CV
            return ""

    def name(self) -> str:
        """The person's name, as the profile or the CV's file name gives it."""
        try:
            profile = agent1_cv.load_profile()
        except Exception:  # noqa: BLE001
            profile = None
        cv = agent1_cv.find_cv()
        return followup.candidate_name(profile, cv.name if cv else "")


class JobEditor:
    """Hand edits to the saved jobs.

    While a search or a scan runs, it works on its own copy of the list and writes it back at the
    end. `live` is that copy (set by the bridge, None between runs): an edit is made on both, or
    the run would write its older copy over the edit when it finishes.
    """

    def __init__(self) -> None:
        self.live: list[dict[str, Any]] | None = None

    def change(self, job_id: str, fn: Callable[[list, dict], Any], render: bool = True) -> dict[str, Any]:
        """Apply `fn(jobs, job)` to the saved job and save. `fn` returns a result dict or None (= ok).
        `render` also writes the Excel files, for edits that change what they show."""
        jobs = store.load_jobs()
        j = store.find(jobs, job_id)
        if not j:
            return {"ok": False, "msg": "That job is not in the list any more."}
        result = fn(jobs, j) or {"ok": True}
        if result.get("ok"):
            store.save_jobs(jobs)
            if render:
                agent4_tracker.render_all(jobs)
            running = self.live
            twin = store.find(running, job_id) if running is not None else None
            if twin is not None:
                try:
                    fn(running, twin)
                except Exception as e:  # noqa: BLE001 - the saved copy is already right
                    trouble.note(f"repeating a hand edit on the running search's list ({job_id})", e)
        return result
