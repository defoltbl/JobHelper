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
from dataclasses import dataclass

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
_NOT_RUNNING, _NO_WINDOW = "JOBHELPER_NOT_RUNNING", "JOBHELPER_NO_WINDOW"


@dataclass(frozen=True)
class Browser:
    """One browser the assistant can work in: its name for macOS, the word used in a sentence, how it is spoken to
    (Chromium's AppleScript or Safari's) and where its "Allow JavaScript from Apple Events" switch is. It words its
    own messages and builds its own AppleScript."""
    key: str
    app: str
    short: str
    kind: str                                     # "chromium" or "safari"
    switch: str

    @property
    def safari(self) -> bool:
        return self.kind == "safari"

    @property
    def tab(self) -> str:
        """How this browser calls the tab in front."""
        return "current tab of front window" if self.safari else "active tab of front window"

    def said(self, kind: str) -> str:
        return _SAID[kind].format(app=self.app, short=self.short, switch=self.switch)

    def wrap(self, action: str) -> list[str]:
        """An AppleScript that first makes sure the browser runs and has a window; values travel as arguments."""
        return ["on run argv",
                f'if application "{self.app}" is not running then return "{_NOT_RUNNING}"',
                f'tell application "{self.app}"',
                f'if (count of windows) is 0 then return "{_NO_WINDOW}"',
                action,
                "end tell",
                "end run"]

    def front_tab_action(self) -> str:
        return f"return (URL of {self.tab}) & linefeed & ({'name' if self.safari else 'title'} of {self.tab})"

    def run_action(self) -> str:
        if self.safari:
            return f"return (do JavaScript (item 1 of argv) in {self.tab}) as text"
        return f"return (execute {self.tab} javascript (item 1 of argv)) as text"

    def open_tab_action(self) -> str:
        if self.safari:
            return "tell front window to set current tab to (make new tab with properties {URL:(item 1 of argv)})"
        return "make new tab at end of tabs of front window with properties {URL:(item 1 of argv)}"


_DEVELOP = "View > Developer > Allow JavaScript from Apple Events"
BROWSERS: dict[str, Browser] = {b.key: b for b in (
    Browser("chrome", "Google Chrome", "Chrome", "chromium", _DEVELOP),
    Browser("brave", "Brave Browser", "Brave", "chromium", _DEVELOP),
    Browser("edge", "Microsoft Edge", "Edge", "chromium", "Tools > Developer > Allow JavaScript from Apple Events"),
    Browser("opera", "Opera", "Opera", "chromium",
            "Developer > Allow JavaScript from Apple Events (the Developer menu is turned on under View > Show Developer Menu)"),
    Browser("safari", "Safari", "Safari", "safari",
            "Develop > Allow JavaScript from Apple Events (turn on the Develop menu first, under Settings > Advanced)"))}
# Browsers people ask for that cannot be reached this way, with the reason: said plainly, not left out without a word.
NOT_POSSIBLE = {"opera_gx": ("Opera GX", "Opera GX tells another app which page is open, but it has switched off the part that lets one fill a page in "
                                         "(tried on 10 October 2026: the request is refused before it is even sent). Open the application form in "
                                         "Google Chrome or Safari; your Opera GX stays as it is."),
                "firefox": ("Firefox", "Firefox does not let another app read or fill in its pages (it has no such switch), so I cannot work in it. "
                                       "Open the application form in one of the other browsers; your Firefox stays as it is.")}
DEFAULT = "chrome"
TIMEOUT = 20


class _Choice:
    """The browser the assistant works in now (one for the app; My details sets it)."""
    def __init__(self) -> None:
        self.browser = BROWSERS[DEFAULT]


_chosen = _Choice()


def browser(key: str | None = None) -> Browser:
    """That browser, or the one in use."""
    return BROWSERS[key] if key in BROWSERS else _chosen.browser


def use(key: str | None) -> str:
    """Choose the browser the assistant works in ("chrome", "brave", "edge", "safari"). Anything else means Chrome."""
    _chosen.browser = BROWSERS[key if key in BROWSERS else DEFAULT]
    return _chosen.browser.key


def current() -> str:
    return _chosen.browser.key


def name(key: str | None = None) -> str:
    """"Google Chrome", "Safari" ..."""
    return browser(key).app


def short(key: str | None = None) -> str:
    """"Chrome", "Brave", "Edge", "Safari": the word used in a sentence."""
    return browser(key).short


def said(kind: str, key: str | None = None) -> str:
    return browser(key).said(kind)


# the messages for Chrome, the browser the assistant uses unless another one is chosen
NOT_RUNNING, NO_WINDOW, NO_CONSENT = said("not_running", DEFAULT), said("no_window", DEFAULT), said("no_consent", DEFAULT)
NO_SCRIPTS, NO_ANSWER, NO_OSASCRIPT = said("no_scripts", DEFAULT), said("no_answer", DEFAULT), said("no_osascript", DEFAULT)


class ChromeError(Exception):
    """The browser could not be reached; the text is written for the person, `kind` says which trouble it is."""

    def __init__(self, text: str, kind: str = ""):
        super().__init__(text)
        self.kind = kind or next((k for k in _SAID if text in (b.said(k) for b in BROWSERS.values())), "refused")


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


def active_tab() -> dict[str, str]:
    """{"url", "title"} of the tab in front. Raises ChromeError with the reason."""
    b = browser()
    answer = _checked(_osascript(b.wrap(b.front_tab_action())))
    url, _sep, words = answer.partition("\n")
    return {"url": url.strip(), "title": words.strip()}


def run(script: str) -> str:
    """Run a script in the tab in front and return what it gives back as text ('' for nothing)."""
    b = browser()
    answer = _checked(_osascript(b.wrap(b.run_action()), script))
    return "" if answer == "missing value" else answer


def open_tab(url: str) -> None:
    """Open an address in a new tab of the window in front (the person asked for it by a button)."""
    b = browser()
    _checked(_osascript(b.wrap(b.open_tab_action()), url))


def pause(seconds: float) -> None:
    """Give the page a moment (a menu that was just opened draws its entries a little later)."""
    time.sleep(seconds)
