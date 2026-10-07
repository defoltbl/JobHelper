"""Desktop notifications (macOS Notification Centre).

Short, and never with anything private beyond a company name or a count. Does
nothing on other systems, or when notifications are switched off in Options.
"""
from __future__ import annotations

import subprocess
import sys

from . import config

TITLE = "JobHelper"


def enabled() -> bool:
    return config.ui_settings().get("notifications", True) is not False


def _quote(text: str) -> str:
    return '"' + (text or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")[:240] + '"'


def _run(cmd: list[str]) -> None:
    """The one place a notification leaves the app (tests replace it, so they never show one)."""
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def send(message: str, subtitle: str = "") -> bool:
    """Show one notification. True if it was handed to the system."""
    if not message or not enabled() or sys.platform != "darwin":
        return False
    script = f"display notification {_quote(message)} with title {_quote(TITLE)}"
    if subtitle:
        script += f" subtitle {_quote(subtitle)}"
    try:
        _run(["osascript", "-e", script])
        return True
    except OSError:
        return False


def invites_text(companies: list[str]) -> str:
    """"Interview invitation from SAP" / "... from SAP and 2 others"."""
    names = [c for c in dict.fromkeys(companies) if c]
    if not names:
        return ""
    if len(names) == 1:
        return f"Interview invitation from {names[0]}"
    return f"Interview invitations from {names[0]} and {len(names) - 1} other" + ("s" if len(names) > 2 else "")
