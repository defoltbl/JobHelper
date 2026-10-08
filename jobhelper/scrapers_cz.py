"""Scrapers for the two biggest Czech job boards: jobs.cz and prace.cz.

Both run on LMC's platform, so job detail pages share the same description
container (``[data-test=jd-body-richtext]``). Search pages differ, so each has
its own card parser. Parsers key off stable ``data-test`` / ``data-testid``
attributes rather than hashed CSS-module class names.

For personal use only. Be polite: modest volumes, a short delay between detail
fetches. If a board changes its markup, the selectors here are what to update.
"""
from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

import requests
from bs4 import BeautifulSoup

from . import store

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "cs,en;q=0.9",
}
_TIMEOUT = 25
_DETAIL_DELAY = 0.3  # seconds between detail-page fetches (politeness)

# English → Czech city names used in board URLs.
_CITY_MAP = {"prague": "praha", "pilsen": "plzen", "budweis": "ceske-budejovice"}


def _slug(text: str) -> str:
    text = text.strip().lower()
    text = _CITY_MAP.get(text, text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "praha"


def _get(url: str, params: dict[str, Any] | None = None) -> requests.Response:
    resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp


def parse_detail(html_text: str) -> tuple[str, str]:
    """(description, company) from a posting's page.

    Company-branded pages (eph.jobs.cz, cdt.jobs.cz …) load the text by script, so
    the page itself holds only a summary in its meta tags and the company after
    the "|" in its title. That is little, but enough to know the company and the
    language of the ad."""
    soup = BeautifulSoup(html_text, "lxml")
    description = ""
    for sel in ("[data-test=jd-body-richtext]", "[data-jobad-body]", ".RichContent", "main"):
        el = soup.select_one(sel)
        if el:
            text = el.get_text(" ", strip=True)
            if len(text) > 80:
                description = re.sub(r"\s+", " ", text)[:6000]
                break

    def meta(*names: str) -> str:
        for name in names:
            el = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if el and (el.get("content") or "").strip():
                return re.sub(r"\s+", " ", el["content"]).strip()
        return ""

    if not description:
        summary = meta("og:description", "description")
        if len(summary) >= 40 and not summary.lower().startswith(("kariéra v", "career at", "careers at")):
            description = summary[:6000]
    company = ""
    title = meta("og:title") or (soup.title.get_text(" ", strip=True) if soup.title else "")
    if " | " in title:
        tail = title.rsplit(" | ", 1)[1].strip()
        if tail and tail.lower() not in ("jobs.cz", "prace.cz", "práce.cz") and re.search(r"[^\W\d_]{2}", tail):
            company = tail
    return description, company


def _fetch_detail(url: str) -> tuple[str, str]:
    try:
        return parse_detail(_get(url).text)
    except requests.RequestException:
        return "", ""


def _fetch_description(url: str) -> str:
    """Pull the plain-text job description from an LMC detail page."""
    return _fetch_detail(url)[0]


def _add_details(jobs: list[dict[str, Any]]) -> None:
    """Fetch each posting's page: its text, and the company when the list did not give one."""
    for job in jobs:
        description, company = _fetch_detail(job["url"])
        job["description"] = description
        if company and not (job.get("company") or "").strip():
            job["company"] = company
        time.sleep(_DETAIL_DELAY)


# ── jobs.cz ─────────────────────────────────────────────────────────────────
def parse_jobs_cz(html_text: str, where: str, limit: int = 1000) -> list[dict[str, Any]]:
    """Pure parser: search-page HTML → job records (no network, no descriptions)."""
    soup = BeautifulSoup(html_text, "lxml")
    out: list[dict[str, Any]] = []
    for card in soup.select("article.SearchResultCard")[:limit]:
        a = card.select_one("a.SearchResultCard__titleLink")
        if not a:
            continue
        jid = a.get("data-jobad-id") or ""
        href = a.get("href", "")
        detail_url = f"https://www.jobs.cz/rpd/{jid}/" if jid else href
        footer = [x.get_text(" ", strip=True) for x in card.select(".SearchResultCard__footerItem")]
        company = footer[0] if footer else ""
        logo = card.select_one(".CompanyLogo img")
        if not company and logo:
            company = logo.get("alt", "")
        loc_el = card.select_one("[data-test=serp-locality]")
        location = loc_el.get_text(strip=True) if loc_el else where
        out.append(store.new_job(
            id=f"jobscz-{jid}" if jid else f"jobscz-{store.url_id(detail_url)}",
            title=a.get_text(strip=True), company=company, location=location,
            source="jobs.cz", url=detail_url, description="",
        ))
    return out


def jobs_cz(keyword: str, where: str, limit: int, with_description: bool = True) -> list[dict[str, Any]]:
    url = f"https://www.jobs.cz/prace/{_slug(where)}/"
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, 6):   # paginate until we reach `limit` (≈30 cards/page)
        if len(jobs) >= limit:
            break
        params = {"q[]": keyword} if page == 1 else {"q[]": keyword, "page": page}
        page_jobs = parse_jobs_cz(_get(url, params=params).text, where, 1000)
        new = [j for j in page_jobs if j["id"] not in seen]
        if not new:
            break   # no more results
        for j in new:
            seen.add(j["id"])
        jobs.extend(new)
        time.sleep(_DETAIL_DELAY)
    jobs = jobs[:limit]
    if with_description:
        _add_details(jobs)
    return jobs


# ── prace.cz ────────────────────────────────────────────────────────────────
def parse_prace_cz(html_text: str, where: str, limit: int = 1000) -> list[dict[str, Any]]:
    """Pure parser: search-page HTML → job records (no network, no descriptions)."""
    soup = BeautifulSoup(html_text, "lxml")
    out: list[dict[str, Any]] = []
    articles = [a for a in soup.select("article[id^=advert-]") if a.select_one("a[data-testid=advert-link]")]
    for card in articles[:limit]:
        a = card.select_one("a[data-testid=advert-link]")
        href = a.get("href", "")
        detail_url = href if href.startswith("http") else f"https://www.prace.cz{href}"
        detail_url = detail_url.split("?")[0]
        m = re.search(r"nabidka/([0-9a-f-]+)", href)
        jid = m.group(1) if m else store.url_id(detail_url)
        logo = card.select_one("img[alt]")
        company = logo.get("alt", "") if logo else ""
        location = where
        for li in card.select("li"):
            txt = li.get_text(" ", strip=True)
            if txt.startswith("Lokalita"):
                location = txt.split(":", 1)[-1].strip() or where
                break
        out.append(store.new_job(
            id=f"pracecz-{jid}", title=a.get_text(strip=True), company=company,
            location=location, source="prace.cz", url=detail_url, description="",
        ))
    return out


def prace_cz(keyword: str, where: str, limit: int, with_description: bool = True) -> list[dict[str, Any]]:
    url = f"https://www.prace.cz/nabidky/{_slug(where)}/"
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(1, 6):
        if len(jobs) >= limit:
            break
        params = {"q": keyword} if page == 1 else {"q": keyword, "page": page}
        page_jobs = parse_prace_cz(_get(url, params=params).text, where, 1000)
        new = [j for j in page_jobs if j["id"] not in seen]
        if not new:
            break
        for j in new:
            seen.add(j["id"])
        jobs.extend(new)
        time.sleep(_DETAIL_DELAY)
    jobs = jobs[:limit]
    if with_description:
        _add_details(jobs)
    return jobs
