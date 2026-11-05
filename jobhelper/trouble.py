"""A place for errors the app decides to carry on after.

Some failures must not stop anything: a sound that does not play, a folder that
does not open, a head start that did not happen. Swallowing them without a
trace makes the day something really is wrong much harder. `note()` writes one
line to data/app_trouble.log (kept short by the housekeeping, like the other
logs) and never raises itself.
"""
from __future__ import annotations

import re
from datetime import datetime

LOG_NAME = "app_trouble.log"
_MAX_LINE = 400


def without_query(text) -> str:
    """An error's text without the query part of any address in it, with or without "https://": API keys travel
    there (…?app_id=…&app_key=…) and must never reach a log file or the screen."""
    def cut(m: re.Match) -> str:
        token = m.group(0)
        scheme = token.find("://")
        if scheme >= 0:                                  # an address: everything from its "?" on
            at = token.find("?", scheme)
            return token if at < 0 else token[:at]
        at = token.find("?")                             # no scheme ("url: /v1/…?app_key=…"): only a real query
        return token[:at] if 0 < at < len(token) - 1 and ("/" in token[:at] or "." in token[:at]) and "=" in token[at:] else token
    return re.sub(r"[^\s'\"]+", cut, str(text))


def _secrets() -> list[str]:
    """The keys and passwords the app holds (in the settings): a value of 6 or more characters, longest first."""
    from . import config
    held = [config.JOOBLE_API_KEY, config.ADZUNA_APP_KEY, config.ADZUNA_APP_ID, config.IMAP_PASSWORD, config.IMAP_PASSWORD_2]
    return sorted({str(v) for v in held if v and len(str(v)) >= 6}, key=len, reverse=True)


def scrub(text) -> str:
    """An error's text fit for the screen and the log: no query part of an address, and no key or password the app
    holds wherever it stands (Jooble's key is in the address's path, #87)."""
    text = without_query(text)
    for secret in _secrets():
        text = text.replace(secret, "[hidden]")
    return text


def _safe(text: str) -> str:
    """Scrubbed (`scrub`) and on one line."""
    return re.sub(r"\s+", " ", scrub(text)).strip()[:_MAX_LINE]


def _folder():
    from . import config
    return config.DATA_DIR


def kind_of(error: BaseException) -> str:
    """What the person is told about an unexpected fault: its kind only. Its text may hold a path or words of a page,
    so that goes to the log of problems (`note`), never to the screen."""
    return f"{type(error).__name__}. The details are in Help > Usage and problems."


def note(where: str, error: BaseException | str) -> None:
    """Remember that `where` failed with `error`, and carry on."""
    try:
        what = f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else str(error)
        line = f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  {_safe(where)}: {_safe(what)}\n"
        folder = _folder()
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / LOG_NAME, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:  # noqa: BLE001 - the last line of defence must not fail loudly
        return
