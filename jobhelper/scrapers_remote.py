"""Remote English-language job boards: RemoteOK and We Work Remotely.

Both are English by nature and need no key. Remote roles aren't location-bound,
so the `where` argument is ignored. Results are keyword-filtered client-side and
cached per run to avoid refetching.
"""
from __future__ import annotations

import html
import re
from functools import lru_cache
from typing import Any

import requests

from . import store

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en;q=0.9",
}
_TIMEOUT = 25
_WWR_FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
]


def _clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _keywords(keyword: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9+#]+", keyword.lower()) if len(t) >= 3]


def _matches(keyword: str, *fields: str) -> bool:
    toks = _keywords(keyword)
    if not toks:
        return True
    hay = " ".join(fields).lower()
    return any(t in hay for t in toks)


# ── RemoteOK ────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _remoteok_payload() -> tuple[dict[str, Any], ...]:
    r = requests.get("https://remoteok.com/api", headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return tuple(data[1:])  # [0] is a legal notice


def remoteok(keyword: str, where: str, limit: int, with_description: bool = True) -> list[dict[str, Any]]:
    try:
        payload = _remoteok_payload()
    except requests.RequestException:
        return []
    out: list[dict[str, Any]] = []
    for raw in payload:
        position = raw.get("position") or raw.get("title") or ""
        if not _matches(keyword, position):  # match on title only to reduce noise
            continue
        smin = raw.get("salary_min")
        out.append(store.new_job(
            id=f"remoteok-{raw.get('id')}",
            title=_clean(position),
            company=_clean(raw.get("company", "")),
            location=_clean(raw.get("location") or "Remote"),
            source="remoteok",
            url=raw.get("url") or raw.get("apply_url") or f"https://remoteok.com/remote-jobs/{raw.get('slug','')}",
            salary=f"from {int(smin):,}".replace(",", " ") if smin else "",
            description=_clean(raw.get("description", "")),
            date_posted=(raw.get("date") or "")[:10],   # ISO datetime → YYYY-MM-DD
        ))
        if len(out) >= limit:
            break
    return out


# ── We Work Remotely ────────────────────────────────────────────────────────
@lru_cache(maxsize=4)
def _wwr_feed(url: str) -> str:
    r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.text


def _parse_wwr_items(rss: str) -> list[dict[str, str]]:
    items = []
    for block in re.findall(r"<item>(.*?)</item>", rss, re.DOTALL):
        def tag(name: str) -> str:
            m = re.search(rf"<{name}>(.*?)</{name}>", block, re.DOTALL)
            val = m.group(1) if m else ""
            val = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", val, flags=re.DOTALL)
            return val.strip()
        items.append({"title": tag("title"), "link": tag("link"),
                      "description": tag("description"), "region": tag("region"),
                      "pubDate": tag("pubDate")})
    return items


def _rss_date(pubdate: str) -> str:
    """RFC-822 pubDate → YYYY-MM-DD."""
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(pubdate).date().isoformat()
    except (TypeError, ValueError):
        return ""


def weworkremotely(keyword: str, where: str, limit: int, with_description: bool = True) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for feed in _WWR_FEEDS:
        try:
            rss = _wwr_feed(feed)
        except requests.RequestException:
            continue
        for it in _parse_wwr_items(rss):
            title_raw = _clean(it["title"])
            # WWR titles are usually "Company: Role"
            company, _, role = title_raw.partition(":")
            role = role.strip() or title_raw
            desc = _clean(it["description"])
            if not _matches(keyword, role):  # match on role title only to reduce noise
                continue
            m = re.search(r"/remote-jobs/([\w-]+)", it["link"])
            jid = m.group(1) if m else store.url_id(it["link"])
            out.append(store.new_job(
                id=f"wwr-{jid}",
                title=role,
                company=company.strip(),
                location=_clean(it.get("region") or "Remote"),
                source="weworkremotely",
                url=it["link"],
                description=desc[:6000],
                date_posted=_rss_date(it.get("pubDate", "")),
            ))
            if len(out) >= limit:
                return out
    return out
