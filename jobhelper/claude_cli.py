"""The Claude program (the Claude Code CLI) that the app uses to check and to start the sign-in.

The SDK that asks Claude carries its own copy of this program, and uses it for every question.
The app uses the same copy for the sign-in, so the check, the sign-in and the questions always
agree. Only when that copy is missing does the app look for one that is installed: on the PATH,
then in the usual folders. (An app that Finder opens gets a short PATH without those folders.)
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Callable

MISSING = ("The Claude program is not on this Mac, so the app cannot sign in to Claude. "
           "Install the app again, or install Claude Code from claude.com/code.")


class ClaudeCli:
    """Finds the Claude program and runs its sign-in commands."""

    PLACES = ("~/.local/bin/claude", "~/.claude/local/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude")

    def __init__(self, bundled: Path | None, which: Callable[[str], str | None] = shutil.which,
                 places: tuple[str, ...] = PLACES) -> None:
        self._bundled = Path(bundled) if bundled else None
        self._which = which
        self._places = places

    @classmethod
    def of_the_sdk(cls) -> "ClaudeCli":
        """The copy inside the SDK first, as the SDK itself does."""
        try:
            import claude_agent_sdk
            bundled = Path(claude_agent_sdk.__file__).resolve().parent / "_bundled" / "claude"
        except Exception:  # noqa: BLE001 - without the SDK, only an installed program can be used
            bundled = None
        return cls(bundled)

    @staticmethod
    def _runnable(path: Path) -> bool:
        return path.is_file() and os.access(path, os.X_OK)

    def path(self) -> str:
        """The program to use, or '' when there is none."""
        if self._bundled and self._runnable(self._bundled):
            return str(self._bundled)
        found = self._which("claude")
        if found:
            return found
        for place in self._places:
            candidate = Path(place).expanduser()
            if self._runnable(candidate):
                return str(candidate)
        return ""

    def auth_status(self, timeout: float = 8) -> subprocess.CompletedProcess:
        """`claude auth status`; FileNotFoundError (with MISSING) when there is no program."""
        program = self.path()
        if not program:
            raise FileNotFoundError(MISSING)
        from . import config
        return subprocess.run([program, "auth", "status"], capture_output=True, text=True, timeout=timeout,
                              cwd=config.work_dir())               # never in / (see config.work_dir)

    def login_script(self) -> list[str]:
        """The osascript arguments that open Terminal on `claude auth login`, with this program's full path
        (Terminal may not know a program that only the app carries)."""
        program = self.path()
        if not program:
            raise FileNotFoundError(MISSING)
        command = f"{shlex.quote(program)} auth login"
        quoted = command.replace("\\", "\\\\").replace('"', '\\"')          # inside an AppleScript string
        return ["osascript", "-e", 'tell application "Terminal" to activate',
                "-e", f'tell application "Terminal" to do script "{quoted}"']
