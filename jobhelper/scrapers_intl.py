"""International source: LinkedIn public "guest" job search (no login).

Uses LinkedIn's unauthenticated jobs-guest endpoints, which return plain HTML
job cards and descriptions. Great for English-language Prague roles. Be polite:
modest volumes and a short delay. LinkedIn may rate-limit (HTTP 429); the
provider degrades gracefully when that happens.

Note: Indeed and Glassdoor are intentionally NOT here — both hard-block
scraping (Cloudflare / no public API), so a scraper for them would be
unreliable. LinkedIn's guest endpoint is the one that works.
"""
from __future__ import annotations

import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from . import store

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en;q=0.9",
}
_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"
_TIMEOUT = 20
_DELAY = 0.4


_CZECH_CITIES = {"praha": "Prague", "prague": "Prague", "brno": "Brno", "ostrava": "Ostrava", "plzeň": "Pilsen",
                 "plzen": "Pilsen", "pilsen": "Pilsen", "olomouc": "Olomouc", "liberec": "Liberec",
                 "české budějovice": "České Budějovice", "ceske budejovice": "České Budějovice", "budweis": "České Budějovice",
                 "hradec králové": "Hradec Králové", "hradec kralove": "Hradec Králové", "pardubice": "Pardubice", "zlín": "Zlín", "zlin": "Zlín"}


def _location(where: str) -> str:
    """The place as LinkedIn wants it. A Czech city gets its country; any other city
    (the Options offer Vienna, Berlin, Warsaw …) or a "City, Country" is passed as written."""
    w = (where or "").strip()
    known = _CZECH_CITIES.get(w.lower())
    return f"{known}, Czechia" if known else w


def parse_linkedin(html_text: str, where: str, limit: int = 1000) -> list[dict[str, Any]]:
    """Pure parser: guest search HTML → job records (no network, no descriptions)."""
    soup = BeautifulSoup(html_text, "lxml")
    out: list[dict[str, Any]] = []
    for li in soup.select("li")[:limit]:
        a = li.select_one('a[href*="/jobs/view/"]')
        title = li.select_one("h3")
        company = li.select_one("h4")
        loc = li.select_one(".job-search-card__location")
        if not (a and title):
            continue
        href = a.get("href", "").split("?")[0]
        m = re.search(r"(\d{6,})", href)
        jid = m.group(1) if m else store.url_id(href)
        t = li.select_one("time")
        date_posted = (t.get("datetime") or "").strip()[:10] if t else ""
        out.append(store.new_job(
            id=f"linkedin-{jid}",
            title=title.get_text(strip=True),
            company=company.get_text(strip=True) if company else "",
            location=loc.get_text(strip=True) if loc else where,
            source="linkedin",
            url=href,
            description="",
            date_posted=date_posted,
        ))
    return out


# Text LinkedIn shows when a posting is closed / expired.
_CLOSED_MARKERS = (
    "no longer accepting applications",
    "no longer available",
    "this job is no longer",
    "not currently accepting applications",
)


_RELATIVE = re.compile(r"(\d+)\s+(hour|day|week|month|year)s?\s+ago", re.IGNORECASE)


def _relative_to_date(text: str) -> str:
    """Turn a '3 weeks ago' / '2 years ago' / 'Reposted 2 days ago' phrase into
    an ISO date (approximate). Returns '' if none found."""
    import datetime
    low = (text or "").lower()
    if "yesterday" in low:
        return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if "today" in low or "just now" in low or "hours ago" in low:
        return datetime.date.today().isoformat()
    m = _RELATIVE.search(low)
    if not m:
        return ""
    n, unit = int(m.group(1)), m.group(2)
    days = {"hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}.get(unit, 0) * n
    return (datetime.date.today() - datetime.timedelta(days=days)).isoformat()


def _fetch_detail(job_id: str) -> tuple[str, bool, str]:
    """Return (description, is_closed, posted_date_iso) for a LinkedIn posting."""
    try:
        r = requests.get(_DETAIL.format(id=job_id), headers=_HEADERS, timeout=_TIMEOUT)
        if r.status_code != 200:
            return "", r.status_code in (404, 410), ""
        low = r.text.lower()
        closed = any(m in low for m in _CLOSED_MARKERS)
        soup = BeautifulSoup(r.text, "lxml")
        el = soup.select_one(".show-more-less-html__markup, .description__text")
        desc = re.sub(r"\s+", " ", el.get_text(" ", strip=True))[:6000] if el else ""
        # posted date: machine <time> first, else a 'N weeks ago' phrase
        posted = ""
        t = soup.select_one("time[datetime], .posted-time-ago__text")
        if t and t.get("datetime"):
            posted = t["datetime"].strip()[:10]
        if not posted:
            posted = _relative_to_date(r.text)
        return desc, closed, posted
    except requests.RequestException:
        return "", False, ""


def _fetch_description(job_id: str) -> str:  # back-compat
    return _fetch_detail(job_id)[0]


def linkedin(keyword: str, where: str, limit: int, with_description: bool = True,
             max_age_days: int = 0) -> list[dict[str, Any]]:
    """Search LinkedIn's public guest endpoint, newest first, paginating to reach
    `limit`. When max_age_days>0, restrict to postings from that window (f_TPR)."""
    base_params = {"keywords": keyword, "location": _location(where), "sortBy": "DD"}
    if max_age_days and max_age_days > 0:
        base_params["f_TPR"] = f"r{max_age_days * 86400}"   # seconds window

    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for start in range(0, max(limit, 10) * 2, 10):   # 10 cards/page; paginate to reach limit
        if len(jobs) >= limit:
            break
        try:
            r = requests.get(_SEARCH, params={**base_params, "start": start},
                             headers=_HEADERS, timeout=_TIMEOUT)
            if r.status_code != 200:
                break
        except requests.RequestException:
            break
        page = parse_linkedin(r.text, where, 1000)
        if not page:
            break
        for job in page:
            if job["id"] not in seen:
                seen.add(job["id"])
                jobs.append(job)
        time.sleep(_DELAY)
    jobs = jobs[:limit]

    if with_description:
        open_jobs = []
        for job in jobs:
            desc, closed, posted = _fetch_detail(job["id"].replace("linkedin-", ""))
            if closed:
                continue  # skip postings that no longer accept applications
            job["description"] = desc
            if posted and not job.get("date_posted"):
                job["date_posted"] = posted   # backfill missing dates so recency works
            open_jobs.append(job)
            time.sleep(_DELAY)
        jobs = open_jobs
    return jobs
