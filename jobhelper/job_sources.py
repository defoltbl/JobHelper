"""Where postings come from: each job board, feed or API is one `JobSource`.

A search asks every source that the chosen setting includes and that is available (a key is set,
a company list exists). A source forgets what it read in an earlier search when asked (`reset`),
so the search never reaches into a scraper's own memory. A new board is a new source: the search
itself does not change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

import requests

from . import config, scrapers_ats, scrapers_cz, scrapers_intl, scrapers_remote, store, textfmt

_clean = textfmt.strip_tags          # text from a board, without its HTML

Fetch = Callable[[str, str, int], list[dict[str, Any]]]


class JobSource(ABC):
    """One place to find postings. `groups` are the settings of Options' "Job source" that include it."""

    def __init__(self, name: str, groups: tuple[str, ...]) -> None:
        self.name = name
        self.groups = groups

    def available(self) -> bool:
        """Whether it can be asked now (a key that is set, a list of companies that exists)."""
        return True

    def reset(self) -> None:
        """Forget what an earlier search read. A source that keeps nothing has nothing to forget."""

    @abstractmethod
    def find(self, query: str, where: str, per_query: int) -> list[dict[str, Any]]:
        """The postings for one search role in one place, as job records."""


class Board(JobSource):
    """A board read by a scraper function (jobs.cz, prace.cz, RemoteOK, We Work Remotely, the career sites)."""

    def __init__(self, name: str, fetch: Fetch, groups: tuple[str, ...] = ("all",),
                 forget: Callable[[], None] | None = None, needs: Callable[[], Any] | None = None) -> None:
        super().__init__(name, groups)
        self._fetch, self._forget, self._needs = fetch, forget, needs

    def available(self) -> bool:
        return bool(self._needs()) if self._needs else True

    def reset(self) -> None:
        if self._forget:
            self._forget()

    def find(self, query: str, where: str, per_query: int) -> list[dict[str, Any]]:
        return self._fetch(query, where, per_query)


class LinkedInSource(JobSource):
    """LinkedIn's public job search, limited to recent postings when Options asks for that."""

    def __init__(self, max_age_days: int = 0) -> None:
        super().__init__("linkedin", ("czech", "linkedin", "all"))
        self._max_age_days = max_age_days

    def find(self, query: str, where: str, per_query: int) -> list[dict[str, Any]]:
        return scrapers_intl.linkedin(query, where, per_query, max_age_days=self._max_age_days)


class AdzunaSource(JobSource):
    """The Adzuna API (not for Czechia): needs ADZUNA_* in the settings."""

    URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

    def __init__(self) -> None:
        super().__init__("adzuna", ("adzuna", "all"))

    def available(self) -> bool:
        return bool(config.adzuna_available())

    def find(self, query: str, where: str, per_query: int) -> list[dict[str, Any]]:
        params = {"app_id": config.ADZUNA_APP_ID, "app_key": config.ADZUNA_APP_KEY, "what": query, "where": where,
                  "results_per_page": per_query, "content-type": "application/json"}
        resp = requests.get(self.URL.format(country=config.ADZUNA_COUNTRY, page=1), params=params, timeout=30)
        resp.raise_for_status()
        out = []
        for raw in resp.json().get("results", []):
            smin, smax = raw.get("salary_min"), raw.get("salary_max")
            salary = f"{int(smin or 0):,} - {int(smax or 0):,}".replace(",", " ") if (smin or smax) else ""
            out.append(store.new_job(
                id=f"adzuna-{raw.get('id')}", title=_clean(raw.get("title", "")),
                company=_clean((raw.get("company") or {}).get("display_name", "")),
                location=_clean((raw.get("location") or {}).get("display_name", "")),
                source="adzuna", url=raw.get("redirect_url", ""), salary=salary,
                description=_clean(raw.get("description", "")), date_posted=(raw.get("created") or "")[:10]))
        return out


class JoobleSource(JobSource):
    """The Jooble API: needs JOOBLE_API_KEY for the region."""

    URL = "https://jooble.org/api/{key}"

    def __init__(self) -> None:
        super().__init__("jooble", ("jooble", "all"))

    def available(self) -> bool:
        return bool(config.has_jooble())

    def find(self, query: str, where: str, per_query: int) -> list[dict[str, Any]]:
        resp = requests.post(self.URL.format(key=config.JOOBLE_API_KEY), json={"keywords": query, "location": where}, timeout=30)
        resp.raise_for_status()
        return [store.new_job(
            id=f"jooble-{raw.get('id')}", title=_clean(raw.get("title", "")), company=_clean(raw.get("company", "")),
            location=_clean(raw.get("location", "")), source=f"jooble/{_clean(raw.get('source', ''))}"[:40],
            url=raw.get("link", ""), salary=_clean(raw.get("salary", "")), description=_clean(raw.get("snippet", "")))
            for raw in resp.json().get("jobs", [])[:per_query]]


def all_sources(max_age_days: int = 0) -> list[JobSource]:
    """Every source the app knows, in the order a search asks them."""
    return [
        Board("jobs.cz", scrapers_cz.jobs_cz, ("czech", "all")),
        Board("prace.cz", scrapers_cz.prace_cz, ("czech", "all")),
        LinkedInSource(max_age_days),
        Board("remoteok", scrapers_remote.remoteok, ("remote", "all"), forget=scrapers_remote.forget_remoteok),
        Board("weworkremotely", scrapers_remote.weworkremotely, ("remote", "all"), forget=scrapers_remote.forget_wwr),
        Board("careers", scrapers_ats.careers, ("careers", "czech", "all"), forget=scrapers_ats.forget, needs=scrapers_ats.load_companies),
        JoobleSource(),
        AdzunaSource(),
    ]


def sources_for(source: str = "czech", max_age_days: int = 0) -> list[JobSource]:
    """The sources a search uses for Options' "Job source" setting:

      "czech"    jobs.cz + prace.cz + LinkedIn + your companies' career sites (default; the Prague market)
      "linkedin" LinkedIn only
      "remote"   RemoteOK + We Work Remotely (English remote roles)
      "careers"  your companies' career sites (data/companies.json)
      "adzuna"   the Adzuna API (pl/de/gb/..., not Czech)
      "jooble"   the Jooble API (needs a key for the region)
      "all"      every source that is set up

    `max_age_days` limits LinkedIn to recent postings."""
    return [s for s in all_sources(max_age_days) if source in s.groups and s.available()]
