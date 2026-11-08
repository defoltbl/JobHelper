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
from pathlib import Path
from typing import Any, Callable

from . import agent1_cv, agent4_tracker, followup, store, trouble
from .api_base import _holding_jobs


class Desktop:
    """Opens what the person asked to see. A failure is noted, never raised: the window says it."""

    def open(self, path) -> bool:
        """Open a file, folder or page in its own app; whether it opened (#79: a failure was swallowed and the window
        said nothing). On a Mac `open` hands the file over and ends at once, with an exit code when no app takes it."""
        try:
            if sys.platform == "darwin":
                return subprocess.run(["open", str(path)], capture_output=True, timeout=15).returncode == 0
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
                return True
            subprocess.Popen(["xdg-open", str(path)])
            return True
        except Exception as e:  # noqa: BLE001 - the window says "couldn't open"; the reason is kept, without the folder
            trouble.note("opening a file or folder", f"{type(e).__name__} for {Path(str(path)).name}")
            return False

    POSTING_FAILED = "The browser could not open the posting. Open it from the job's link yourself."

    def opened(self, target, failed: str = "") -> dict:
        """{ok} of opening `target`, with what to say when nothing opened (#104): `failed`, or a plain line for a folder or
        a file. Every opener of the window answers with this, so none ignores a failure."""
        if self.open(target):
            return {"ok": True}
        name = Path(str(target)).name
        return {"ok": False, "msg": failed or (f"The folder {name} could not be opened in Finder." if Path(str(target)).is_dir()
                                               else f"{name} could not be opened. Check that an app for this kind of file is installed.")}

    def open_posting(self, url) -> dict:
        """Open a job posting's link: only a web page, and never a site the app refuses (form_fill.PageAddress), for a job
        of the list and a filtered-out one alike (#104). {ok: False} without a word when there is no such link; the
        window then says there is none."""
        from .form_fill import PageAddress      # here: form_fill depends on much of the app
        address = PageAddress(str(url or ""))
        if not address.is_web or address.refused:
            return {"ok": False}
        return {**self.opened(address.url, self.POSTING_FAILED), "url": address.url}

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

    @_holding_jobs()
    def change(self, job_id: str, fn: Callable[[list, dict], Any], render: bool = True) -> dict[str, Any]:
        """Apply `fn(jobs, job)` to the saved job and save. `fn` returns a result dict or None (= ok).
        `render` also writes the Excel files, for edits that change what they show. Refused while the weekly run works
        on the list (store.RunLock): the edit would be lost under the run's copy."""
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
