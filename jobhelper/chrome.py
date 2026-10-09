"""The tab you have open in Google Chrome: where it is, and a way to run a script in it.

macOS lets one app ask another to do something (Apple events). Chrome answers two such
requests that the assistant needs: "which page is in front" and "run this script in it".
Both need your consent: macOS asks once whether JobHelper may control Chrome, and Chrome has
a switch, off by default, under View > Developer > Allow JavaScript from Apple Events.

Chrome is never started from here and no page is opened, closed or changed by this module on
its own; it only carries what form_fill asks.
"""
from __future__ import annotations

import subprocess
import time

APP = "Google Chrome"
TIMEOUT = 20
_NOT_RUNNING, _NO_WINDOW = "JOBHELPER_NOT_RUNNING", "JOBHELPER_NO_WINDOW"

NOT_RUNNING = "Google Chrome is not open. Open the application form in Chrome, then ask me again."
NO_WINDOW = "Chrome has no window open. Open the application form in a Chrome tab, then ask me again."
NO_CONSENT = ("macOS did not let JobHelper talk to Chrome. Open System Settings > Privacy & Security > Automation, "
              "turn on Google Chrome for JobHelper (or for Terminal, when the app was started from it), then ask me again.")
NO_SCRIPTS = ("Chrome does not let other apps fill in pages yet. In Chrome's menu bar choose "
              "View > Developer > Allow JavaScript from Apple Events, then ask me again.")
NO_ANSWER = "Chrome did not answer in time. Bring the tab with the form to the front, then ask me again."
NO_OSASCRIPT = "This Mac could not run the request to Chrome (osascript is missing)."


class ChromeError(Exception):
    """Chrome could not be reached; the text is written for the person."""


def _osascript(lines: list[str], *args: str) -> str:
    """Run an AppleScript; values travel as arguments, never inside the script text."""
    command = ["osascript"]
    for line in lines:
        command += ["-e", line]
    try:
        done = subprocess.run(command + list(args), capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired as e:
        raise ChromeError(NO_ANSWER) from e
    except OSError as e:
        raise ChromeError(NO_OSASCRIPT) from e
    if done.returncode != 0:
        raise ChromeError(_reason(done.stderr or ""))
    return (done.stdout or "").rstrip("\n")


def _reason(error: str) -> str:
    low = error.lower()
    if "-1743" in low or "not authorized" in low or "not authorised" in low or "not allowed to send" in low:
        return NO_CONSENT
    if "javascript" in low and ("turned off" in low or "apple events" in low):
        return NO_SCRIPTS
    if "-600" in low or "isn't running" in low or "is not running" in low:
        return NOT_RUNNING
    if "-1728" in low or "-1719" in low or "invalid index" in low or "can't get" in low or "can’t get" in low:
        return NO_WINDOW
    return "Chrome refused the request. Bring the tab with the form to the front, then ask me again."


def _checked(answer: str) -> str:
    if answer == _NOT_RUNNING:
        raise ChromeError(NOT_RUNNING)
    if answer == _NO_WINDOW:
        raise ChromeError(NO_WINDOW)
    return answer


def _wrap(action: str) -> list[str]:
    return ["on run argv",
            f'if application "{APP}" is not running then return "{_NOT_RUNNING}"',
            f'tell application "{APP}"',
            f'if (count of windows) is 0 then return "{_NO_WINDOW}"',
            action,
            "end tell",
            "end run"]


def active_tab() -> dict[str, str]:
    """{"url", "title"} of the tab in front. Raises ChromeError with the reason."""
    answer = _checked(_osascript(_wrap('return (URL of active tab of front window) & linefeed & (title of active tab of front window)')))
    url, _sep, title = answer.partition("\n")
    return {"url": url.strip(), "title": title.strip()}


def run(script: str) -> str:
    """Run a script in the tab in front and return what it gives back as text ('' for nothing)."""
    answer = _checked(_osascript(_wrap("return (execute active tab of front window javascript (item 1 of argv)) as text"), script))
    return "" if answer == "missing value" else answer


def pause(seconds: float) -> None:
    """Give the page a moment (a menu that was just opened draws its entries a little later)."""
    time.sleep(seconds)
