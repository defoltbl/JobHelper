"""Remote English-language job boards: RemoteOK and We Work Remotely.

Both are English by nature and need no key. Remote roles aren't location-bound,
so the `where` argument is ignored. Results are keyword-filtered client-side and
cached per run to avoid refetching.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import requests

from . import store, textfmt, web

_HEADERS = web.headers()
_TIMEOUT = 25
_WWR = "https://weworkremotely.com/categories/"
_WWR_FEEDS = [_WWR + "remote-programming-jobs.rss", _WWR + "remote-devops-sysadmin-jobs.rss"]      # software and IT
# The board's other lists, by the profession they hold (the names are those of prefilter.FIELDS).
_WWR_BY_FIELD = {
    "software and IT": _WWR_FEEDS,
    "sales and marketing": [_WWR + "remote-sales-and-marketing-jobs.rss"],
    "customer support": [_WWR + "remote-customer-support-jobs.rss"],
    "design and media": [_WWR + "remote-design-jobs.rss"],
    "finance": [_WWR + "remote-management-and-finance-jobs.rss"],
    "office and public administration": [_WWR + "remote-management-and-finance-jobs.rss"],
}
_WWR_OTHER = [_WWR + "all-other-remote-jobs.rss", "https://weworkremotely.com/remote-jobs.rss"]      # everything else


def wwr_feeds(fields=None) -> list[str]:
    """Which of the board's lists to read for someone who works in `fields`. None means "ask
    Options and the CV profile"; a profession the board has no list for gets its general lists;
    with no profession known, the programming lists as before."""
    if fields is None:
        fields = _my_fields()
    feeds: list[str] = []
    for name in fields or []:
        for url in _WWR_BY_FIELD.get(name, _WWR_OTHER):
            if url not in feeds:
                feeds.append(url)
    return feeds or list(_WWR_FEEDS)


def _my_fields() -> list[str]:
    """The professions picked in Options, else the ones the wanted roles or the search roles name."""
    try:
        from . import config, prefilter
        options = config.ui_settings()
        return prefilter.chosen_fields(options.get("my_fields")) or \
            prefilter.fields_of(list(options.get("wanted_roles") or []) + list(options.get("queries") or []))
    except Exception:  # noqa: BLE001 - a missing profession only means the usual lists
        return []


_clean = textfmt.strip_tags          # text from a board, without its HTML


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
    return tuple(item for item in data[1:] if isinstance(item, dict)) if isinstance(data, list) else ()   # [0] is a legal notice


def forget_remoteok() -> None:
    """Forget RemoteOK's list: each search reads it again."""
    _remoteok_payload.cache_clear()


def remoteok(keyword: str, where: str, limit: int, with_description: bool = True) -> list[dict[str, Any]]:
    try:
        payload = _remoteok_payload()
    except (requests.RequestException, ValueError):      # ValueError: the board answered with something that is not its list
        return []
    out: list[dict[str, Any]] = []
    for raw in payload:
        position = raw.get("position") or raw.get("title") or ""
        if not _matches(keyword, position):  # match on title only to reduce noise
            continue
        smin = raw.get("salary_min")
        smin = smin if isinstance(smin, (int, float)) and not isinstance(smin, bool) else 0      # a board may send words here
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
@lru_cache(maxsize=16)      # more than the board has lists: none is fetched twice in one search
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


def forget_wwr() -> None:
    """Forget the feeds of We Work Remotely: each search reads them again."""
    _wwr_feed.cache_clear()


def weworkremotely(keyword: str, where: str, limit: int, with_description: bool = True) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for feed in wwr_feeds():
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
