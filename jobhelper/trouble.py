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


def _safe(text: str) -> str:
    """No query part of an address (keys travel there) and no line breaks."""
    return re.sub(r"\s+", " ", without_query(text)).strip()[:_MAX_LINE]


def _folder():
    from . import config
    return config.DATA_DIR


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
