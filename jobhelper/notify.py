"""Desktop notifications (macOS Notification Centre).

Short, and never with anything private beyond a company name or a count. Does
nothing on other systems, or when notifications are switched off in Options.

The installed app shows them itself (`AppNotifier`), so macOS asks once and lists JobHelper in
System Settings → Notifications. Run from Python (`python app_qt.py`), they go the plain way
(`ScriptNotifier`), which macOS shows under Script Editor.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from . import app_info, config

TITLE = "JobHelper"


def enabled() -> bool:
    return config.ui_settings().get("notifications", True) is not False


def _quote(text: str) -> str:
    return '"' + (text or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")[:240] + '"'


def _run(cmd: list[str]) -> None:
    """The one place a plain notification leaves the app (tests replace it, so they never show one)."""
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _one_line(text: str, limit: int = 240) -> str:
    return " ".join((text or "").split())[:limit]


class Notifier(ABC):
    """Shows one notification: a headline ("Search finished") and the detail."""

    @abstractmethod
    def show(self, headline: str, message: str) -> bool:
        """True when it was handed to macOS."""

    def permission(self) -> str:
        """"allowed", "off" (turned off in System Settings), "not asked" or "unknown"."""
        return "unknown"


class ScriptNotifier(Notifier):
    """The plain way, through osascript: for `python app_qt.py`, where there is no app of our own."""

    def show(self, headline: str, message: str) -> bool:
        script = f"display notification {_quote(message)} with title {_quote(TITLE)}"
        if headline and headline != TITLE:
            script += f" subtitle {_quote(headline)}"
        try:
            _run(["osascript", "-e", script])
        except OSError:
            return False
        return True


class AppNotifier(Notifier):
    """The installed app's own notifications (macos/Notify.swift, in Contents/Frameworks). They carry
    JobHelper's name and icon, and macOS asks the person once whether to show them."""

    _PERMISSION = {1: "allowed", 0: "off", 2: "not asked"}

    def __init__(self, show: Callable[[bytes, bytes], int], permission: Callable[[], int]) -> None:
        self._show, self._permission = show, permission

    @classmethod
    def of_the_app(cls) -> "AppNotifier | None":
        """The notifier of the running app, or None outside the built app (tests, `python app_qt.py`)."""
        if not getattr(sys, "frozen", False):
            return None
        library = Path(sys.executable).resolve().parent.parent / "Frameworks" / app_info.NOTIFY_LIBRARY
        if not library.is_file():
            return None
        try:
            loaded = ctypes.CDLL(str(library))
        except OSError:
            return None
        show, permission = loaded.jobhelper_notify, loaded.jobhelper_notify_permission
        show.argtypes, show.restype = [ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int32
        permission.argtypes, permission.restype = [], ctypes.c_int32
        return cls(show, permission)

    def show(self, headline: str, message: str) -> bool:
        # 1 shown, 2 waiting for the person's first answer (shown once they allow it); 0 turned off, -1 refused
        return self._show(headline.encode("utf-8"), message.encode("utf-8")) in (1, 2)

    def permission(self) -> str:
        return self._PERMISSION.get(self._permission(), "unknown")


def notifier() -> Notifier:
    """The app's own notifier when it runs as the installed app, else the plain way."""
    return AppNotifier.of_the_app() or ScriptNotifier()


TEST_HEADLINE = "Test notification"
TEST_MESSAGE = "This is how JobHelper tells you that a search finished or an interview invitation came."


def send_test(patience: float = 0.0, sleep: Callable[[float], None] = time.sleep) -> dict:
    """Send one test notification, whatever the switch in Options says, and say in words what macOS did.
    The first time, macOS asks the person; `patience` is how many seconds to wait for that answer (the
    command line waits, because its program would end and take the question with it; the window does not)."""
    if sys.platform != "darwin":
        return {"ok": False, "msg": "Notifications are shown on macOS only."}
    way = notifier()
    handed = way.show(TEST_HEADLINE, TEST_MESSAGE)
    allowed, waited = way.permission(), 0.0
    while allowed == "not asked" and waited < patience:
        sleep(1.0)
        waited += 1.0
        allowed = way.permission()
    if allowed == "off" or not handed:
        return {"ok": False, "msg": "macOS did not show it: JobHelper's notifications are turned off in System Settings."}
    if allowed == "not asked":
        return {"ok": True, "msg": "macOS asks whether to allow JobHelper's notifications. Choose Allow."}
    return {"ok": True, "msg": "Sent. It shows at the top right of the screen."}


def send(message: str, subtitle: str = "") -> bool:
    """Show one notification: `subtitle` is its headline ("Search finished"), `message` the detail.
    True if it was handed to the system."""
    if not message or not enabled() or sys.platform != "darwin":
        return False
    return notifier().show(_one_line(subtitle) or TITLE, _one_line(message))


def search_text(new_jobs: int, ready: int) -> str:
    """What a finished search found, in one plain sentence."""
    if new_jobs <= 0:
        return "Nothing new this time. Your list is up to date."
    jobs = "1 new job" if new_jobs == 1 else f"{new_jobs} new jobs"
    if ready <= 0:
        return f"{jobs} found. None scored high enough for a CV and letter."
    return f"{jobs} found. {ready} {'is' if ready == 1 else 'are'} ready to send, with a CV and letter."


PAUSED = "Claude's limit is used up. Everything done so far is saved."
RESUME = "Claude's limit is back. Open JobHelper and press Resume to continue."
FAILED = "The search stopped on an error. Open JobHelper to see what happened."


def invites_text(companies: list[str]) -> str:
    """"Interview invitation from SAP" / "... from SAP and 2 others"."""
    names = [c for c in dict.fromkeys(companies) if c]
    if not names:
        return ""
    if len(names) == 1:
        return f"Interview invitation from {names[0]}"
    return f"Interview invitations from {names[0]} and {len(names) - 1} other" + ("s" if len(names) > 2 else "")
