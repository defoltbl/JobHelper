"""The weekly run: a job search, then a scan of the mailbox, without the window.

The LaunchAgent that the Weekly run card sets up starts the app with `--weekly` (a packaged
app: `JobHelper --weekly`; from the source: `python app_qt.py --weekly`). Both steps use the
Options saved in the app, and everything they print goes into weekly_jobhelper.log in the data
folder. A step that fails is written in the log, and the next step still runs.
"""
from __future__ import annotations

import importlib
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import trouble

FLAG = "--weekly"
LOG_NAME = "weekly_jobhelper.log"


def command_step(module_name: str, args: list[str]) -> Callable[[], int]:
    """One of the app's commands (run.py, status.py) as a step: its main() with these arguments."""
    def step() -> int:
        module = importlib.import_module(module_name)
        saved, sys.argv = sys.argv, [f"{module_name}.py", *args]
        try:
            return int(module.main() or 0)
        except SystemExit as e:                      # argparse and the commands end with sys.exit
            return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        finally:
            sys.argv = saved
    return step


class ScrubbedLog:
    """The weekly run's log as a file: every line a step prints or raises passes `trouble.scrub` first, so the log never
    keeps a key or an address's query (#93)."""

    def __init__(self, raw) -> None:
        self._raw = raw

    def write(self, text: str) -> int:
        self._raw.write(trouble.scrub(text))
        return len(text)

    def flush(self) -> None:
        self._raw.flush()


class WeeklyRun:
    """The steps of the weekly run, and the log they write into."""

    WAIT = 60 * 60                  # how long the run waits for the window to finish a search or a scan (seconds)
    BUSY_CODE = 75                  # "try again later": the window kept the job list for the whole wait

    def __init__(self, log: Path, steps: list[tuple[str, Callable[[], int]]] | None = None,
                 now: Callable[[], datetime] = datetime.now, wait: float | None = None) -> None:
        self._log = Path(log)
        self._steps = steps if steps is not None else [
            ("job search", command_step("run", ["--reuse-profile"])),
            ("email analysis", command_step("status", ["sync", "--summary"])),
        ]
        self._now = now
        self._wait = self.WAIT if wait is None else wait

    @property
    def log(self) -> Path:
        return self._log

    def run(self) -> int:
        """Run every step; 0 when all of them ended well, else the code of the last one that did not. The steps hold the
        job list's lock (store.RunLock): the run waits while the window works on the list, and never writes over it."""
        self._log.parent.mkdir(parents=True, exist_ok=True)
        with self._log.open("a", encoding="utf-8") as raw:
            return self._logged(ScrubbedLog(raw))

    def _logged(self, out) -> int:
        from . import store
        with redirect_stdout(out), redirect_stderr(out):
            print(f"===== weekly JobHelper {self._now():%Y-%m-%d %H:%M} =====", flush=True)
            if not store.RunLock.take(self._wait):
                print("The app was working on your jobs for the whole wait, so this week's run did not start. "
                      "It runs again next week, or start a search in the app.", flush=True)
                return self.BUSY_CODE
            try:
                worst = self._steps_run(out)
            finally:
                store.RunLock.release()
            print("", flush=True)
        return worst

    def _steps_run(self, out) -> int:
        worst = 0
        for title, step in self._steps:
            print(f"--- {title} ---", flush=True)
            try:
                code = step()
            except Exception:  # noqa: BLE001 - the log says what went wrong; the next step still runs
                out.write(traceback.format_exc())
                code = 1
            if code:
                print(f"({title} ended with code {code})", flush=True)
                worst = code
        return worst


def main() -> int:
    from . import config
    code = WeeklyRun(config.DATA_DIR / LOG_NAME).run()
    from . import ui_api
    ui_api.Api().widget_update()                     # the widget shows what the run found
    return code
