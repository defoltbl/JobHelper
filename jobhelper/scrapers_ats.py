"""Company career-site scrapers via common ATS public APIs.

Greenhouse, Lever, SmartRecruiters and Recruitee all publish a company's open
roles as public JSON, so we can pull a company's career center directly. You
list the companies you care about in ``data/companies.json``::

    [
      {"name": "Bloomreach", "ats": "greenhouse", "token": "bloomreach"},
      {"name": "GitLab",     "ats": "greenhouse", "token": "gitlab"},
      {"name": "Acme",       "ats": "lever",      "token": "acme"}
    ]

The ``token`` is the slug in the board URL (e.g. boards.greenhouse.io/**gitlab**).

NOT supported (they block scraping or are bespoke): SAP (jobs.sap.com) and
Microsoft careers. For those, set up their own "job agent" email alert — Agent 5
reads the replies into your tracker.
"""
from __future__ import annotations

import html
import json
import re
import time
from typing import Any

import requests

from . import config, filters, store

_H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
      "Accept": "application/json"}
_T = 15
_DELAY = 0.3

# cache a company's roles for the session so repeated queries don't refetch
_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}


def _strip_html(raw: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(raw or ""))).strip()[:6000]


# ── per-ATS fetchers: return a company's open roles as normalized records ──
def _greenhouse(name: str, token: str) -> list[dict[str, Any]]:
    r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                     params={"content": "true"}, headers=_H, timeout=_T)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        posted = (j.get("first_published") or j.get("updated_at") or "")[:10]
        out.append(_norm(f"gh-{token}-{j.get('id')}", j.get("title", ""), name,
                         (j.get("location") or {}).get("name", ""), j.get("absolute_url", ""),
                         _strip_html(j.get("content", "")), posted))
    return out


def _lever(name: str, token: str) -> list[dict[str, Any]]:
    r = requests.get(f"https://api.lever.co/v0/postings/{token}",
                     params={"mode": "json"}, headers=_H, timeout=_T)
    r.raise_for_status()
    out = []
    for j in r.json():
        loc = ((j.get("categories") or {}).get("location")) or ""
        posted = ""
        if j.get("createdAt"):
            import datetime
            posted = datetime.date.fromtimestamp(j["createdAt"] / 1000).isoformat()
        out.append(_norm(f"lever-{token}-{j.get('id')}", j.get("text", ""), name,
                         loc, j.get("hostedUrl", ""),
                         _strip_html(j.get("descriptionPlain") or j.get("description", "")), posted))
    return out


def _smartrecruiters(name: str, token: str) -> list[dict[str, Any]]:
    r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{token}/postings",
                     params={"limit": 100}, headers=_H, timeout=_T)
    r.raise_for_status()
    out = []
    for j in r.json().get("content", []):
        loc = " ".join(str(x) for x in [(j.get("location") or {}).get("city"),
                                        (j.get("location") or {}).get("country")] if x)
        posted = (j.get("releasedDate") or "")[:10]
        url = f"https://jobs.smartrecruiters.com/{token}/{j.get('id')}"
        out.append(_norm(f"sr-{token}-{j.get('id')}", j.get("name", ""), name,
                         loc, url, "", posted))
    return out


def _recruitee(name: str, token: str) -> list[dict[str, Any]]:
    r = requests.get(f"https://{token}.recruitee.com/api/offers/", headers=_H, timeout=_T)
    r.raise_for_status()
    out = []
    for j in r.json().get("offers", []):
        posted = (j.get("published_at") or "")[:10]
        out.append(_norm(f"rc-{token}-{j.get('id')}", j.get("title", ""), name,
                         j.get("location", ""), j.get("careers_url", ""),
                         _strip_html(j.get("description", "")), posted))
    return out


_FETCHERS = {"greenhouse": _greenhouse, "lever": _lever,
             "smartrecruiters": _smartrecruiters, "recruitee": _recruitee}


def _norm(jid: str, title: str, company: str, location: str, url: str,
          description: str, posted: str) -> dict[str, Any]:
    return store.new_job(id=jid, title=(title or "").strip(), company=company,
                         location=(location or "").strip(), url=url,
                         description=description, date_posted=posted, source="careers")


def load_companies() -> list[dict[str, str]]:
    p = config.DATA_DIR / "companies.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [c for c in data if c.get("ats") in _FETCHERS and c.get("token")]
    except Exception:
        return []


def _company_jobs(name: str, ats: str, token: str) -> list[dict[str, Any]]:
    key = (ats, token)
    if key not in _cache:
        try:
            _cache[key] = _FETCHERS[ats](name, token)
        except requests.RequestException:
            _cache[key] = []
        time.sleep(_DELAY)
    return _cache[key]


# words we ignore when matching a query to a job title
_STOP = {"junior", "senior", "medior", "mid", "entry", "graduate", "intern", "trainee",
         "the", "for", "and", "with", "our", "developer", "engineer", "specialist"}


def _loc_ok(loc: str, where: str) -> bool:
    """In the searched city, in its country, or remote without being tied to another part of the world."""
    return filters.location_fits(loc, where)


def careers(keyword: str, where: str, limit: int, with_description: bool = True) -> list[dict[str, Any]]:
    """Search the configured company career centers for a keyword near `where`.

    Signature matches the other providers so it plugs into agent2_search.
    """
    companies = load_companies()
    if not companies:
        return []
    terms = [t for t in re.findall(r"[a-z0-9+#]{3,}", keyword.lower()) if t not in _STOP]
    results: list[dict[str, Any]] = []
    for c in companies:
        for job in _company_jobs(c.get("name", c["token"]), c["ats"], c["token"]):
            if not _loc_ok(job["location"], where):
                continue
            title = job["title"].lower()
            if terms and not any(t in title for t in terms):
                continue
            results.append(job)
            if len(results) >= limit * 3:
                return results
    return results
