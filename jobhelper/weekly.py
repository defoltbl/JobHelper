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


class WeeklyRun:
    """The steps of the weekly run, and the log they write into."""

    def __init__(self, log: Path, steps: list[tuple[str, Callable[[], int]]] | None = None,
                 now: Callable[[], datetime] = datetime.now) -> None:
        self._log = Path(log)
        self._steps = steps if steps is not None else [
            ("job search", command_step("run", ["--reuse-profile"])),
            ("email analysis", command_step("status", ["sync", "--summary"])),
        ]
        self._now = now

    @property
    def log(self) -> Path:
        return self._log

    def run(self) -> int:
        """Run every step; 0 when all of them ended well, else the code of the last one that did not."""
        self._log.parent.mkdir(parents=True, exist_ok=True)
        worst = 0
        with self._log.open("a", encoding="utf-8") as out, redirect_stdout(out), redirect_stderr(out):
            print(f"===== weekly JobHelper {self._now():%Y-%m-%d %H:%M} =====", flush=True)
            for title, step in self._steps:
                print(f"--- {title} ---", flush=True)
                try:
                    code = step()
                except Exception:  # noqa: BLE001 - the log says what went wrong; the next step still runs
                    traceback.print_exc(file=out)
                    code = 1
                if code:
                    print(f"({title} ended with code {code})", flush=True)
                    worst = code
            print("", flush=True)
        return worst


def main() -> int:
    from . import config
    code = WeeklyRun(config.DATA_DIR / LOG_NAME).run()
    from . import ui_api
    ui_api.Api().widget_update()                     # the widget shows what the run found
    return code
