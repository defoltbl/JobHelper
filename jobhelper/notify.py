"""Desktop notifications (macOS Notification Centre).

Short, and never with anything private beyond a company name or a count. Does
nothing on other systems, or when notifications are switched off in Options.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import config

TITLE = "JobHelper"


def enabled() -> bool:
    return config.ui_settings().get("notifications", True) is not False


def _quote(text: str) -> str:
    return '"' + (text or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")[:240] + '"'


def _run(cmd: list[str]) -> None:
    """The one place a notification leaves the app (tests replace it, so they never show one)."""
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ── the app's own notifier, so notifications carry its name and icon ────────
# A notification sent through plain `osascript` shows the Script Editor icon. macOS takes the
# icon from the app that posts it, so the first time one is needed a tiny helper app is built
# in the data folder (an AppleScript applet with the JobHelper icon). It reads what to show from
# a queue folder, shows it and quits.
APP_NAME = "JobHelper"
_APPLET = """on run
	set q to "%s/"
	try
		set names to paragraphs of (do shell script "ls " & quoted form of q & " 2>/dev/null")
	on error
		set names to {}
	end try
	repeat with f in names
		if (f as text) is not "" then
			try
				set body to do shell script "cat " & quoted form of (q & f)
				do shell script "rm -f " & quoted form of (q & f)
				set parts to paragraphs of body
				if (count of parts) > 1 then
					display notification (item 2 of parts) with title (item 1 of parts)
				else
					display notification body with title "JobHelper"
				end if
				delay 0.3
			end try
		end if
	end repeat
end run
"""


def _folder() -> Path:
    return config.DATA_DIR / "notifier"


def app_path() -> Path:
    return _folder() / f"{APP_NAME}.app"


def _build(cmd: list[str]) -> bool:
    """Run one build tool (osacompile, codesign). Tests replace this."""
    return subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0


def ensure_app() -> Path | None:
    """The helper app, built on first use. None when it cannot be made (not macOS, no
    icon, a build tool failed): notifications then go out the plain way."""
    if sys.platform != "darwin":
        return None
    app, queue = app_path(), _folder() / "queue"
    marker = _folder() / "built_for.txt"
    icon = config.ROOT / "ui_qt" / "icon.icns"
    try:
        if app.is_dir() and marker.is_file() and marker.read_text(encoding="utf-8") == str(queue):
            return app
        if not icon.is_file():
            return None
        import plistlib
        import shutil
        queue.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(app, ignore_errors=True)
        source = _folder() / "notifier.applescript"
        source.write_text(_APPLET % str(queue).replace("\\", "\\\\").replace('"', '\\"'), encoding="utf-8")
        if not _build(["osacompile", "-o", str(app), str(source)]) or not app.is_dir():
            return None
        shutil.copyfile(icon, app / "Contents" / "Resources" / "applet.icns")
        plist = app / "Contents" / "Info.plist"
        info = plistlib.loads(plist.read_bytes())
        info.update(CFBundleName=APP_NAME, CFBundleDisplayName=APP_NAME, CFBundleIdentifier="local.jobhelper.notifier",
                    LSUIElement=True)                       # no Dock icon while it shows a message
        plist.write_bytes(plistlib.dumps(info))
        _build(["codesign", "--force", "--deep", "--sign", "-", str(app)])     # changed after building: sign it again
        marker.write_text(str(queue), encoding="utf-8")
        return app
    except Exception:  # noqa: BLE001 - never let a notification problem break a run
        return None


def _one_line(text: str, limit: int = 240) -> str:
    return " ".join((text or "").split())[:limit]


def send(message: str, subtitle: str = "") -> bool:
    """Show one notification: `subtitle` is its headline ("Search finished"), `message` the detail.
    True if it was handed to the system."""
    if not message or not enabled() or sys.platform != "darwin":
        return False
    try:
        app = ensure_app()
        if app is not None:
            import time
            queue = _folder() / "queue"
            queue.mkdir(parents=True, exist_ok=True)
            (queue / f"{time.time_ns()}.txt").write_text(f"{_one_line(subtitle) or TITLE}\n{_one_line(message)}", encoding="utf-8")
            _run(["open", "-g", "-n", str(app)])
            return True
        script = f"display notification {_quote(message)} with title {_quote(TITLE)}"
        if subtitle:
            script += f" subtitle {_quote(subtitle)}"
        _run(["osascript", "-e", script])
        return True
    except OSError:
        return False


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
