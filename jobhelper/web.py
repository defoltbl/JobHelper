"""How the app introduces itself when it reads a job site: as a desktop browser does. One place for it,
so every scraper sends the same thing."""
from __future__ import annotations

BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def headers(language: str | None = "en;q=0.9", accept: str | None = None) -> dict[str, str]:
    """The request headers of a browser that reads pages in `language` (None: no preference) and accepts `accept`."""
    out = {"User-Agent": BROWSER}
    if accept:
        out["Accept"] = accept
    if language:
        out["Accept-Language"] = language
    return out
