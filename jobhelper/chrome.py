"""The tab you have open in your browser: where it is, and a way to run a script in it.

macOS lets one app ask another to do something (Apple events). Google Chrome, Brave, Microsoft
Edge, Opera and Safari answer the requests the assistant needs (Opera GX and Firefox do not): "which page is in front" and "run
this script in it". Both need your consent: macOS asks once whether JobHelper may control the
browser, and the browser has a switch, off by default, called "Allow JavaScript from Apple
Events" (in Chrome, Brave and Edge under View > Developer; in Safari under Develop).

The browser is never started from here and no page is opened, closed or changed by this module
on its own; it only carries what form_fill asks. (The module keeps its first name: Chrome was
the only browser when it was written.)
"""
from __future__ import annotations

import subprocess
import time

# key -> (the app's name for macOS, how it is spoken to, where its switch is)
BROWSERS = {
    "chrome": ("Google Chrome", "chromium", "View > Developer > Allow JavaScript from Apple Events"),
    "brave": ("Brave Browser", "chromium", "View > Developer > Allow JavaScript from Apple Events"),
    "edge": ("Microsoft Edge", "chromium", "Tools > Developer > Allow JavaScript from Apple Events"),
    "opera": ("Opera", "chromium", "Developer > Allow JavaScript from Apple Events (the Developer menu is turned on under View > Show Developer Menu)"),
    "safari": ("Safari", "safari", "Develop > Allow JavaScript from Apple Events (turn on the Develop menu first, under Settings > Advanced)"),
}
SHORT = {"chrome": "Chrome", "brave": "Brave", "edge": "Edge", "opera": "Opera", "safari": "Safari"}
# Browsers people ask for that cannot be reached this way, with the reason: said plainly, not left out without a word.
NOT_POSSIBLE = {"opera_gx": ("Opera GX", "Opera GX tells another app which page is open, but it has switched off the part that lets one fill a page in "
                                         "(tried on 10 October 2026: the request is refused before it is even sent). Open the application form in "
                                         "Google Chrome or Safari; your Opera GX stays as it is."),
                "firefox": ("Firefox", "Firefox does not let another app read or fill in its pages (it has no such switch), so I cannot work in it. "
                                       "Open the application form in one of the other browsers; your Firefox stays as it is.")}
DEFAULT = "chrome"
TIMEOUT = 20
_NOT_RUNNING, _NO_WINDOW = "JOBHELPER_NOT_RUNNING", "JOBHELPER_NO_WINDOW"
_current = [DEFAULT]

_SAID = {
    "not_running": "{app} is not open. Open the application form in {short}, then ask me again.",
    "no_window": "{short} has no window open. Open the application form in a {short} tab, then ask me again.",
    "no_consent": ("macOS did not let JobHelper talk to {short}. Open System Settings > Privacy & Security > Automation, "
                   "turn on {app} for JobHelper (or for Terminal, when the app was started from it), then ask me again."),
    "no_scripts": "{short} does not let other apps fill in pages yet. In {short}'s menu bar choose {switch}, then ask me again.",
    "no_answer": "{short} did not answer in time. Bring the tab with the form to the front, then ask me again.",
    "no_osascript": "This Mac could not run the request to {short} (osascript is missing).",
    "refused": "{short} refused the request. Bring the tab with the form to the front, then ask me again.",
    "cannot": ("{short} does not let another app fill in its pages: it has switched that part off, and there is no setting for it. "
               "Choose another browser on the My details page (Google Chrome and Safari work), and open the form there."),
}


def use(key: str | None) -> str:
    """Choose the browser the assistant works in ("chrome", "brave", "edge", "safari"). Anything else means Chrome."""
    _current[0] = key if key in BROWSERS else DEFAULT
    return _current[0]


def current() -> str:
    return _current[0]


def name(key: str | None = None) -> str:
    """"Google Chrome", "Safari" ..."""
    return BROWSERS[key if key in BROWSERS else _current[0]][0]


def short(key: str | None = None) -> str:
    """"Chrome", "Brave", "Edge", "Safari": the word used in a sentence."""
    return SHORT[key if key in BROWSERS else _current[0]]


def said(kind: str, key: str | None = None) -> str:
    key = key if key in BROWSERS else _current[0]
    return _SAID[kind].format(app=BROWSERS[key][0], short=SHORT[key], switch=BROWSERS[key][2])


# the messages for Chrome, the browser the assistant uses unless another one is chosen
NOT_RUNNING, NO_WINDOW, NO_CONSENT = said("not_running", DEFAULT), said("no_window", DEFAULT), said("no_consent", DEFAULT)
NO_SCRIPTS, NO_ANSWER, NO_OSASCRIPT = said("no_scripts", DEFAULT), said("no_answer", DEFAULT), said("no_osascript", DEFAULT)


class ChromeError(Exception):
    """The browser could not be reached; the text is written for the person, `kind` says which trouble it is."""

    def __init__(self, text: str, kind: str = ""):
        super().__init__(text)
        self.kind = kind or next((k for k in _SAID if text in (said(k, b) for b in BROWSERS)), "refused")


def _fail(kind: str) -> ChromeError:
    return ChromeError(said(kind), kind)


def _osascript(lines: list[str], *args: str) -> str:
    """Run an AppleScript; values travel as arguments, never inside the script text."""
    command = ["osascript"]
    for line in lines:
        command += ["-e", line]
    try:
        done = subprocess.run(command + list(args), capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired as e:
        raise _fail("no_answer") from e
    except OSError as e:
        raise _fail("no_osascript") from e
    if done.returncode != 0:
        kind = _reason(done.stderr or "")
        if kind == "refused":                       # a reason this does not know: kept, so that it can be found out later
            from . import trouble
            trouble.note(f"asking {short()} about the page in front", RuntimeError(" ".join((done.stderr or "").split())[:300]))
        raise _fail(kind)
    return (done.stdout or "").rstrip("\n")


def _reason(error: str) -> str:
    low = error.lower()
    if "-2741" in low or "-2740" in low or "syntax error" in low:
        return "cannot"                             # the browser does not know the command at all (Opera GX has it switched off)
    if "-1743" in low or "not authorized" in low or "not authorised" in low or "not allowed to send" in low:
        return "no_consent"
    if "javascript" in low and ("turned off" in low or "apple events" in low or "allow javascript" in low):
        return "no_scripts"
    if "-600" in low or "isn't running" in low or "is not running" in low:
        return "not_running"
    if "-1728" in low or "-1719" in low or "invalid index" in low or "can't get" in low or "can’t get" in low:
        return "no_window"
    return "refused"


def _checked(answer: str) -> str:
    if answer == _NOT_RUNNING:
        raise _fail("not_running")
    if answer == _NO_WINDOW:
        raise _fail("no_window")
    return answer


def _wrap(action: str) -> list[str]:
    app = name()
    return ["on run argv",
            f'if application "{app}" is not running then return "{_NOT_RUNNING}"',
            f'tell application "{app}"',
            f'if (count of windows) is 0 then return "{_NO_WINDOW}"',
            action,
            "end tell",
            "end run"]


def _safari() -> bool:
    return BROWSERS[_current[0]][1] == "safari"


def _tab() -> str:
    """How this browser calls the tab in front."""
    return "current tab of front window" if _safari() else "active tab of front window"


def active_tab() -> dict[str, str]:
    """{"url", "title"} of the tab in front. Raises ChromeError with the reason."""
    answer = _checked(_osascript(_wrap(f"return (URL of {_tab()}) & linefeed & ({'name' if _safari() else 'title'} of {_tab()})")))
    url, _sep, words = answer.partition("\n")
    return {"url": url.strip(), "title": words.strip()}


def run(script: str) -> str:
    """Run a script in the tab in front and return what it gives back as text ('' for nothing)."""
    if _safari():
        action = f"return (do JavaScript (item 1 of argv) in {_tab()}) as text"
    else:
        action = f"return (execute {_tab()} javascript (item 1 of argv)) as text"
    answer = _checked(_osascript(_wrap(action), script))
    return "" if answer == "missing value" else answer


def open_tab(url: str) -> None:
    """Open an address in a new tab of the window in front (the person asked for it by a button)."""
    if _safari():
        action = "tell front window to set current tab to (make new tab with properties {URL:(item 1 of argv)})"
    else:
        action = "make new tab at end of tabs of front window with properties {URL:(item 1 of argv)}"
    _checked(_osascript(_wrap(action), url))


def pause(seconds: float) -> None:
    """Give the page a moment (a menu that was just opened draws its entries a little later)."""
    time.sleep(seconds)
