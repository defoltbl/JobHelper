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

    # The countries a source has postings for (as `places.country_of` names them); empty = anywhere.
    countries: tuple[str, ...] = ()

    def __init__(self, name: str, groups: tuple[str, ...]) -> None:
        self.name = name
        self.groups = groups

    def serves(self, country: str) -> bool:
        """Whether it has postings for a search in `country` ('' = a place the app does not know: it may be
        in any country, so a source is not left out for it)."""
        return not self.countries or not country or country in self.countries

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
                 forget: Callable[[], None] | None = None, needs: Callable[[], Any] | None = None,
                 countries: tuple[str, ...] = ()) -> None:
        super().__init__(name, groups)
        self._fetch, self._forget, self._needs = fetch, forget, needs
        self.countries = countries

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
        Board("jobs.cz", scrapers_cz.jobs_cz, ("czech", "boards", "all"), countries=("czechia",)),     # Czech postings only
        Board("prace.cz", scrapers_cz.prace_cz, ("czech", "boards", "all"), countries=("czechia",)),
        LinkedInSource(max_age_days),
        Board("remoteok", scrapers_remote.remoteok, ("remote", "all"), forget=scrapers_remote.forget_remoteok),
        Board("weworkremotely", scrapers_remote.weworkremotely, ("remote", "all"), forget=scrapers_remote.forget_wwr),
        Board("careers", scrapers_ats.careers, ("careers", "czech", "all"), forget=scrapers_ats.forget, needs=scrapers_ats.load_companies),
        JoobleSource(),
        AdzunaSource(),
    ]


class SourceChoice:
    """Which kinds of job source a search reads: any combination of the ones Options offers (the Czech
    boards, LinkedIn, the career sites, the remote boards). The search, the weekly run and the main
    screen's chips all read it from here, so they cannot disagree.

    Older settings had one "Job source" value and an "Include remote jobs" switch; they are read as the
    same choice, so nothing changes until the person changes it."""

    KINDS = (("boards", "Czech boards"), ("linkedin", "LinkedIn"), ("careers", "Career sites"), ("remote", "Remote boards"))
    EXTRA = (("adzuna", "Adzuna"), ("jooble", "Jooble"))          # with a key, from the command line
    _LEGACY = {"czech": ("boards", "linkedin", "careers"), "linkedin": ("linkedin",), "careers": ("careers",),
               "remote": ("remote",), "adzuna": ("adzuna",), "jooble": ("jooble",),
               "all": ("boards", "linkedin", "careers", "remote", "adzuna", "jooble")}

    def __init__(self, kinds) -> None:
        wanted = set(kinds or ())
        self._kinds = tuple(key for key, _name in self.KINDS + self.EXTRA if key in wanted)

    @classmethod
    def offered(cls) -> list[dict[str, str]]:
        """The kinds Options lets you pick, in their order: [{key, name}]."""
        return [{"key": key, "name": name} for key, name in cls.KINDS]

    @classmethod
    def known(cls, key) -> bool:
        return any(key == k for k, _name in cls.KINDS + cls.EXTRA)

    @classmethod
    def from_options(cls, opts: dict[str, Any]) -> "SourceChoice":
        chosen = opts.get("sources")
        if isinstance(chosen, (list, tuple)) and any(cls.known(k) for k in chosen):
            return cls(chosen)
        source = str(opts.get("source") or "czech")
        kinds = cls._LEGACY.get(source, cls._LEGACY["czech"])
        if opts.get("include_remote") is True and source == "czech":   # the old switch added them to the mixed source only
            kinds += ("remote",)
        return cls(kinds)

    @property
    def kinds(self) -> tuple[str, ...]:
        return self._kinds

    def names(self) -> list[str]:
        """The names to show, e.g. ["Czech boards", "LinkedIn"]."""
        return [name for key, name in self.KINDS + self.EXTRA if key in self._kinds]

    def includes(self, source: "JobSource") -> bool:
        return any(kind in source.groups for kind in self._kinds)


def _tags(source) -> set[str]:
    """The groups a setting stands for: one old value ("czech", "all") or a SourceChoice / list of kinds."""
    if isinstance(source, SourceChoice):
        return set(source.kinds)
    if isinstance(source, str):
        return {source}
    return set(source or ())


def sources_for(source="czech", max_age_days: int = 0, country: str = "") -> list[JobSource]:
    """The sources a search uses for Options' "Job source" setting:

      "czech"    jobs.cz + prace.cz + LinkedIn + your companies' career sites (default; the Prague market)
      "linkedin" LinkedIn only
      "remote"   RemoteOK + We Work Remotely (English remote roles)
      "careers"  your companies' career sites (data/companies.json)
      "adzuna"   the Adzuna API (pl/de/gb/..., not Czech)
      "jooble"   the Jooble API (needs a key for the region)
      "all"      every source that is set up

    `max_age_days` limits LinkedIn to recent postings. `country` is where the search is: a board for
    another country only (jobs.cz, prace.cz outside Czechia) is left out, see `left_out`. `source` may
    also be a SourceChoice (or a list of its kinds): then every source of any chosen kind is asked."""
    tags = _tags(source)
    return [s for s in all_sources(max_age_days) if tags & set(s.groups) and s.available() and s.serves(country)]


def left_out(source, country: str) -> list[tuple[list[str], tuple[str, ...]]]:
    """The sources of this setting that a search in `country` does not use, because they are for another
    country: [(their names, the countries they are for)], one entry per set of countries."""
    grouped: dict[tuple[str, ...], list[str]] = {}
    tags = _tags(source)
    for s in all_sources():
        if tags & set(s.groups) and not s.serves(country):
            grouped.setdefault(s.countries, []).append(s.name)
    return [(names, served) for served, names in grouped.items()]
