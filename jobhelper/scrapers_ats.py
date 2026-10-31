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

import json
import re
import time
from typing import Any

import requests

from . import config, filters, store, textfmt, web

_H = web.headers(language=None, accept="application/json")
_T = 15
_DELAY = 0.3

# cache a company's roles for the session so repeated queries don't refetch
_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}


def _strip_html(raw: str) -> str:
    return textfmt.strip_tags(raw)[:6000]


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
ATS_NAMES = tuple(_FETCHERS)          # the career-site systems a company can use: the Options list offers these


def _norm(jid: str, title: str, company: str, location: str, url: str,
          description: str, posted: str) -> dict[str, Any]:
    return store.new_job(id=jid, title=(title or "").strip(), company=company,
                         location=(location or "").strip(), url=url,
                         description=description, date_posted=posted, source="careers")


def is_token(token: str) -> bool:
    """A career site's own short name as it stands in its address ("gitlab", "Acme-Corp"): letters, digits, - and _ only.
    The token becomes part of an address the app asks, so nothing else is accepted (no dots, slashes or spaces)."""
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", str(token or "")))


def forget() -> None:
    """Forget what the career sites answered: each search asks them again (the app can stay open for days)."""
    _cache.clear()


def load_companies() -> list[dict[str, str]]:
    p = config.DATA_DIR / "companies.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a file that cannot be read lists no company
        return []
    if not isinstance(data, list):
        return []
    # entry by entry: one line that is not a company (a note, a typo) must not hide all the others
    return [c for c in data if isinstance(c, dict) and c.get("ats") in _FETCHERS and isinstance(c.get("token"), str) and is_token(c["token"])]


def _company_jobs(name: str, ats: str, token: str) -> list[dict[str, Any]]:
    key = (ats, token)
    if key not in _cache:
        try:
            _cache[key] = _FETCHERS[ats](name, token)
        except requests.RequestException:
            _cache[key] = []
        except Exception as e:  # noqa: BLE001 - one career site that answers in a shape nobody expects must not stop the others
            from . import trouble
            trouble.note(f"reading the career site of {name}", RuntimeError(type(e).__name__))
            _cache[key] = []
        time.sleep(_DELAY)
    return _cache[key]


# words we ignore when matching a query to a job title
_STOP = {"junior", "senior", "medior", "mid", "entry", "graduate", "intern", "trainee",
         "the", "for", "and", "with", "our", "developer", "engineer", "specialist"}


def _loc_ok(loc: str, where: str) -> bool:
    """In the searched city, in its country, or remote in a way that fits (one location; `careers` makes its Placement once)."""
    return filters.location_fits(loc, where)


def _matches(title: str, terms: list[str], keyword: str) -> bool:
    """Whether a posting's title fits the role searched for: one of its telling words, or, when the role has none
    ("QA Engineer", "Junior Developer": short or common words only), every word of it. An empty filter once let every
    posting of every career site through."""
    if terms:
        return any(t in title for t in terms)
    words = re.findall(r"[a-z0-9+#]+", keyword.lower())
    return bool(words) and all(re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", title) for w in words)


def careers(keyword: str, where: str, limit: int, with_description: bool = True) -> list[dict[str, Any]]:
    """Search the configured company career centers for a keyword near `where`.

    Signature matches the other providers so it plugs into agent2_search.
    """
    companies = load_companies()
    if not companies:
        return []
    terms = [t for t in re.findall(r"[a-z0-9+#]{3,}", keyword.lower()) if t not in _STOP]
    placement = filters.Placement.for_search(where)                 # Options read once, not for every posting
    results: list[dict[str, Any]] = []
    for c in companies:
        for job in _company_jobs(c.get("name", c["token"]), c["ats"], c["token"]):
            if not placement.fits(job["location"]):
                continue
            title = job["title"].lower()
            if not _matches(title, terms, keyword):
                continue
            results.append(job)
            if len(results) >= limit * 3:
                return results
    return results
