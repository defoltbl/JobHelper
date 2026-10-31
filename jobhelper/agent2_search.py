"""Agent 2: search for jobs on several sources, and filter what comes back.

Sources (each one a `job_sources.JobSource`; see `job_sources.sources_for`):
  • jobs.cz, prace.cz   read from their search pages (scrapers_cz); no key needed
  • LinkedIn            its public job search (scrapers_intl)
  • RemoteOK, We Work Remotely   remote roles (scrapers_remote)
  • career sites        the companies in data/companies.json (scrapers_ats)
  • Jooble, Adzuna      search APIs, used only when their keys are in .env
                        (Adzuna does not cover Czechia; set ADZUNA_COUNTRY)

All results become job records and are de-duplicated; every posting a filter removes is
kept with its reason for the "Filtered out" list. Plain HTTP: no Claude usage is spent here.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

import requests

from . import config, email_client, filters, job_sources, language, salary, scrapers_intl, store, textfmt, trouble

_clean = textfmt.strip_tags          # text from a board, without its HTML


# Words to strip from a title before comparing roles (seniority / gender / noise).
_ROLE_NOISE = {
    "junior", "senior", "medior", "mid", "lead", "jr", "sr", "entry", "graduate",
    "the", "for", "and", "with", "our", "team", "role", "position", "new",
    "m", "f", "d", "n", "x", "mfd", "fmd",
}


def role_key(title: str) -> frozenset[str]:
    """Normalise a job title to its core role tokens (drops seniority/gender/noise)."""
    tokens = re.findall(r"[a-z0-9+#]{2,}", (title or "").lower())
    return frozenset(t for t in tokens if t not in _ROLE_NOISE)


def _same_role(a: frozenset[str], b: frozenset[str]) -> bool:
    """True if two role keys look like the same role (Jaccard >= 0.5 or subset)."""
    if not a or not b:
        return False  # unknown role → don't treat as duplicate (allow the lead)
    if a <= b or b <= a:
        return True
    return len(a & b) / len(a | b) >= 0.5


class AppliedRoles:
    """The roles you already applied for (or marked "not interested"), company by company. A lead for one of
    them is not shown again; a different role at the same company is (you can apply there more than once)."""

    def __init__(self, jobs: list[dict[str, Any]], statuses: set[str]) -> None:
        self._known = [(j["company"], role_key(j.get("title", ""))) for j in jobs if j.get("status") in statuses and j.get("company")]

    def covers(self, job: dict[str, Any]) -> bool:
        """The same role at the same company: not merely a name that shares a word ("Good Data" is not "NTT DATA")."""
        company = job.get("company", "")
        role = role_key(job.get("title", ""))
        return bool(company) and any(_same_role(role, known_role) and email_client.same_company(company, known_company)
                                     for known_company, known_role in self._known)


def drop_known_applications(
    new_jobs: list[dict[str, Any]],
    existing_jobs: list[dict[str, Any]],
    exclude_statuses: set[str] | None = None,
    dropped: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Remove a new lead only if you've already applied to the SAME role at the
    SAME company (any application status, incl. rejected), or marked it "not interested"."""
    applied = AppliedRoles(existing_jobs, exclude_statuses or (store.APPLICATION_STATUSES | {store.NOT_INTERESTED}))
    kept, n_dropped = [], 0
    for nj in new_jobs:
        if applied.covers(nj):
            n_dropped += 1
            note_dropped(dropped, nj, "already applied", "You already applied for this role at this company.")
            continue
        kept.append(nj)
    return kept, n_dropped


def _lead_key(job: dict[str, Any]) -> tuple[str, str]:
    title = re.sub(r"\([^)]*\)", " ", (job.get("title") or "").lower())
    title = re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()).strip()
    return email_client.norm_company(job.get("company", "")), title


def prune_duplicate_leads(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove leads that are the same role at the same company as another lead
    (posted on two boards, or reposted). Keeps the copy that already has a
    letter or score, else the one with the longer description. Applications are
    never touched. Mutates `jobs`; returns the removed records."""
    def worth(j):
        return (bool(j.get("cover_letter_file")), j.get("match_score") is not None, len(j.get("description") or ""))

    best: dict[tuple[str, str], dict[str, Any]] = {}
    for j in jobs:
        if j.get("status", "found") not in store.LEAD_STATUSES:
            continue
        key = _lead_key(j)
        if not key[0] or not key[1]:
            continue                                   # unknown company: cannot tell duplicates apart
        if key not in best or worth(j) > worth(best[key]):
            best[key] = j
    keep = {id(j) for j in best.values()}
    removed = [j for j in jobs if j.get("status", "found") in store.LEAD_STATUSES
               and all(_lead_key(j)) and id(j) not in keep]
    # A lead without a company name whose title equals a lead that has one
    # (prace.cz sometimes omits the company) is the same posting.
    titled = {key[1] for key in best}
    removed += [j for j in jobs if j.get("status", "found") in store.LEAD_STATUSES
                and not _lead_key(j)[0] and len(_lead_key(j)[1]) >= 12 and _lead_key(j)[1] in titled]
    gone = {id(j) for j in removed}
    # The same link twice is the same posting, whatever its id says (ids made from an
    # address used to change on every run, so such a posting was listed again each time).
    by_url: dict[str, dict[str, Any]] = {}
    for j in jobs:
        url = (j.get("url") or "").strip().rstrip("/")
        if not url or id(j) in gone:
            continue
        if j.get("status", "found") not in store.LEAD_STATUSES:
            by_url[url] = j                             # an application always stays
            continue
        other = by_url.get(url)
        if other is None:
            by_url[url] = j
        elif other.get("status", "found") not in store.LEAD_STATUSES or worth(other) >= worth(j):
            removed.append(j); gone.add(id(j))
        else:
            removed.append(other); gone.add(id(other)); by_url[url] = j
    jobs[:] = [j for j in jobs if id(j) not in gone]
    return removed


def prune_applied_leads(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove leads (found/letter_ready) from new_jobs when you've already applied
    to that SAME role at that SAME company (an application-status job exists).
    Mutates `jobs` in place; returns the removed lead records.

    Different roles at an applied company are kept (multi-role applications).
    """
    applied = AppliedRoles(jobs, store.APPLICATION_STATUSES)
    removed, kept = [], []
    for j in jobs:
        if j.get("status") in store.LEAD_STATUSES and applied.covers(j):
            removed.append(j)
            continue
        kept.append(j)
    jobs[:] = kept
    return removed


CLOSED_RECHECK_DAYS = 3        # a posting's page is asked again at most this often
CLOSED_PER_SEARCH = 40         # and at most this many pages per search, the longest unchecked first
CLOSED_REASON = "The posting no longer accepts applications."


def can_ask_if_closed(job: dict[str, Any]) -> bool:
    """Whether this posting's board is one whose page says if it still accepts applications (LinkedIn)."""
    return scrapers_intl.is_linkedin(job)


def posting_closed(job: dict[str, Any]) -> bool | None:
    """Ask a posting's own page whether it still accepts applications.
    True / False, or None when the board gives no clear answer (or is not one the app can ask)."""
    if not scrapers_intl.posting_number(job):
        return None
    try:
        text, closed, _posted = scrapers_intl.read_posting(job)
    except Exception:  # noqa: BLE001 - no answer is not "closed"
        return None
    return True if closed else (False if text else None)


def check_closed(jobs: list[dict[str, Any]], dropped: list | None = None, network: bool = True,
                 today: str = "", pause: float = 0.4) -> dict[str, int]:
    """Find new jobs whose posting no longer accepts applications: by what their saved text
    says, and (network=True) by asking the pages of those not asked for CLOSED_RECHECK_DAYS.
    A closed job without documents leaves the list (noted in `dropped` with the reason);
    one that has a letter or CV stays and is marked `closed`, so nothing written is lost.
    A job found open again loses the mark. Mutates `jobs`. {asked, removed, marked}"""
    import time
    from datetime import date, timedelta
    today = today or date.today().isoformat()
    stale = (date.fromisoformat(today) - timedelta(days=CLOSED_RECHECK_DAYS)).isoformat()
    leads = [j for j in jobs if j.get("status") in store.LEAD_STATUSES]
    verdict: dict[int, bool] = {}
    for j in leads:
        if filters.is_closed(f"{j.get('title', '')} {j.get('description', '')}"):
            verdict[id(j)] = True
    stats = {"asked": 0, "removed": 0, "marked": 0}
    if network:
        # only postings whose board can be asked stand in line: the others used to take the places at its head on
        # every search (they are never marked as asked), so most of the ones that can be asked never were
        due = [j for j in leads if id(j) not in verdict and can_ask_if_closed(j) and str(j.get("closed_checked") or "") <= stale]
        due.sort(key=lambda j: str(j.get("closed_checked") or ""))
        for j in due[:CLOSED_PER_SEARCH]:
            answer = posting_closed(j)
            if answer is None:
                continue                       # nothing learned: ask again next time
            stats["asked"] += 1
            j["closed_checked"] = today
            verdict[id(j)] = answer
            if pause:
                time.sleep(pause)
    gone = set()
    for j in leads:
        closed = verdict.get(id(j))
        if closed is None:
            continue
        if not closed:
            j.pop("closed", None)
        elif j.get("cover_letter_file") or j.get("tailored_cv_file"):
            if not j.get("closed"):
                stats["marked"] += 1
            j["closed"] = True
        else:
            note_dropped(dropped, j, "closed", CLOSED_REASON)
            gone.add(id(j))
    if gone:
        jobs[:] = [j for j in jobs if id(j) not in gone]
        stats["removed"] = len(gone)
    return stats


LANGUAGE_GROUP = "other language"       # the name of the reason in the Filtered out list


def is_english_job(job: dict[str, Any]) -> bool:
    """Is the ad written in English? Judged on the description when present, otherwise the title."""
    return other_language(job) == ""


def other_language(job: dict[str, Any]) -> str:
    """The language an ad is written in when that is not English ("Czech", "German" …), else ''."""
    text = (job.get("description") or "").strip() or job.get("title", "")
    return language.detect(text)


def language_reason(job: dict[str, Any]) -> str:
    """Why a posting does not fit someone who works in English only: '' or one sentence."""
    description = job.get("description", "")
    if filters.requires_czech(description):
        return "Requires Czech at a working level."
    for group in filters.required_languages(description):
        if "english" not in group:
            return "Requires %s at a working level." % " or ".join(name.capitalize() for name in group)
    name = other_language(job)
    if name:
        return "The ad is not written in English." if name == "another language" else f"The ad is written in {name}."
    return ""


def _is_recent(job: dict[str, Any], max_age_days: int) -> bool:
    """True if the job was posted within max_age_days. Unknown dates are kept
    (jobs.cz/prace.cz don't expose a date)."""
    from datetime import date, timedelta
    posted = (job.get("date_posted") or "").strip()[:10]
    if not posted:
        return True
    try:
        return date.fromisoformat(posted) >= date.today() - timedelta(days=max_age_days)
    except ValueError:
        return True


# Sites that answer a program with a "prove you are a person" page. That is a no, and the app
# takes it as one: their postings keep the summary, and the job window offers pasting the text.
_NO_SECOND_READ = ("jooble.org",)


def refetch_description(job: dict[str, Any]) -> str:
    """Read one posting's text again from its board ('' if it still cannot be read).
    A first read can fail for a moment (the board answers too many requests with nothing)."""
    url, source = job.get("url") or "", (job.get("source") or "").split("/")[0]
    try:
        if source == "linkedin" or "linkedin.com" in url:
            return scrapers_intl.read_posting(job)[0]
        if "jobs.cz" in url or "prace.cz" in url:
            from . import scrapers_cz
            return scrapers_cz._fetch_detail(url)[0]
        if not url or any(host in url for host in _NO_SECOND_READ):
            return ""
        # any other board or company page: the copy of the posting the page itself publishes
        from . import scrapers_page
        return scrapers_page.posting_text(url)
    except Exception:  # noqa: BLE001 - no text is an answer too
        return ""


REREAD_TRIES = 3          # how many searches try to get more of a posting's text before leaving it be


def reread_missing(jobs: list[dict[str, Any]], english_only: bool = True, dropped: list | None = None, pause: float = 0.5) -> dict[str, int]:
    """Try once more to read every new job that has no posting text or only a short summary
    of it (REREAD_TRIES times at most per job, counted in `text_tries`). With english_only, a
    posting that turns out to be written in another language leaves the list (noted in
    `dropped`, like any filtered posting). A job scored earlier on less text loses that
    score (kept as score_before) so this run scores it from the text; one that already has
    documents keeps its score until "Score again". Mutates `jobs`. {read, removed}"""
    import time
    from . import agent3_letters
    stats, gone = {"read": 0, "removed": 0}, []
    for job in jobs:
        had = len((job.get("description") or "").strip())
        tries = job.get("text_tries") if isinstance(job.get("text_tries"), int) else 0
        if (job.get("status") not in store.LEAD_STATUSES or had >= agent3_letters.SHORT_TEXT or not job.get("url")
                or tries >= REREAD_TRIES):
            continue
        text = (refetch_description(job) or "").strip()
        if pause:
            time.sleep(pause)
        if len(text) <= had:
            job["text_tries"] = tries + 1
            continue
        job.pop("text_tries", None)
        job["description"] = text
        stats["read"] += 1
        fill_company(job)
        if job.get("hold") == agent3_letters.NO_TEXT:
            job.pop("hold", None)
            job["doc_attempts"] = 0
        if job.get("match_score") is not None and not job.get("cover_letter_file"):
            job["score_before"], job["match_score"] = job["match_score"], None
        if english_only and not job.get("cover_letter_file") and not is_english_job(job):
            note_dropped(dropped, job, LANGUAGE_GROUP, language_reason(job) or "The ad is not written in English.")
            gone.append(id(job))
    if gone:
        jobs[:] = [j for j in jobs if id(j) not in gone]
        stats["removed"] = len(gone)
    return stats


def safe_error(error) -> str:
    """An error's text without the address's query part (`trouble.without_query`)."""
    return trouble.without_query(error)


_COMPANY_IN_TEXT = re.compile(r"\b(?:Firma|Společnost|Zaměstnavatel|Company|Employer)\s*:\s*(.{2,80}?)\s*(?:\(|Místo pracoviště|Adresa|Location|\||\n|$)")


def fill_company(job: dict[str, Any]) -> None:
    """Some board pages give the company only inside the posting text ("Firma: X ( zaměstnavatel )").
    Take it from there when the listing itself had none."""
    if (job.get("company") or "").strip():
        return
    m = _COMPANY_IN_TEXT.search(job.get("description") or "")
    if m and re.search(r"[^\W\d_]{2}", m.group(1)):
        job["company"] = m.group(1).strip(" .,;:-")


# ── what the filters removed, and why ───────────────────────────────────────
MAX_DROPPED = 600


def note_dropped(dropped: list | None, job: dict[str, Any], group: str, reason: str) -> None:
    if dropped is not None:
        dropped.append({"title": job.get("title", ""), "company": job.get("company", ""),
                        "location": job.get("location", ""), "source": job.get("source", ""),
                        "url": job.get("url", ""), "group": group, "reason": reason,
                        "job": dict(job)})          # the whole posting, so it can be brought back


# Reasons a later run would apply again at once, so bringing the posting back would not last.
NO_BRING_BACK = {"duplicate", "already applied", "closed"}


def save_dropped(rows: list[dict[str, Any]], when: str = "") -> None:
    """Keep what the latest search filtered out (replaces the previous search's list)."""
    from datetime import datetime
    config.FILTERED_OUT.write({"when": when or datetime.now().strftime("%d %b %H:%M"), "total": len(rows), "rows": rows[:MAX_DROPPED]},
                          indent=1)


def load_dropped() -> dict[str, Any]:
    """What the latest search filtered out; nothing when it cannot be read (it is only shown, never saved back)."""
    from . import vault
    try:
        data = config.FILTERED_OUT.read()
    except vault.VaultError:
        data = None
    if not isinstance(data, dict):
        return {"when": "", "total": 0, "rows": []}
    rows = [r for r in data["rows"] if isinstance(r, dict)] if isinstance(data.get("rows"), list) else []
    total = data.get("total")
    return {"when": str(data.get("when", "")), "rows": rows,
            "total": total if isinstance(total, int) and not isinstance(total, bool) and total >= len(rows) else len(rows)}



def _collect(sources: list, queries: list[str], where: str, per_query: int, progress=None) -> list[dict[str, Any]]:
    """Every posting the sources find for the queries, once each (the first source to find it keeps it).
    A source that fails is noted and the others go on."""
    found: dict[str, dict[str, Any]] = {}
    steps, step = len(sources) * len(queries), 0
    for src in sources:
        name, got = src.name, 0
        for q in queries:
            if progress:
                progress(step, steps)
            step += 1
            try:
                for job in src.find(q, where, per_query):
                    if job["id"] and job["id"] not in found:
                        job["query"] = q            # which keyword found it (for the Insights view)
                        found[job["id"]] = job
                        got += 1
            except requests.HTTPError as e:
                print(f"  ! {name} error for '{q}': {safe_error(e)}")
            except requests.RequestException as e:
                print(f"  ! {name} network error for '{q}': {safe_error(e)}")
            except Exception as e:  # noqa: BLE001 - a board that changed its pages must not end the whole search
                trouble.note(f"reading {name} for a search", RuntimeError(safe_error(f"{type(e).__name__}: {e}")))
                print(f"  ! {name} could not be read for '{q}' ({type(e).__name__}); the other sources go on")
        print(f"  · {name}: +{got} new listings")
    return list(found.values())


@dataclass(frozen=True)
class Sift:
    """One rule a posting must pass: its group in the Filtered out list, the words for the run's log, and
    `reason`, which says why a posting fails ('' = it passes)."""
    group: str
    label: str
    reason: Callable[[dict[str, Any]], str]


class SearchFilters:
    """The rules one search's postings pass, made once from its settings and applied in order. Each posting that a
    rule drops is noted with its reason. The duplicate check comes last, so that a copy is dropped as a duplicate
    only when another copy is kept: the copies of one role can differ in language or date, and a filter must not
    remove the one that was kept and hide the other."""

    def __init__(self, placement: filters.Placement, candidate_seniority: str = "junior", english_only: bool = True,
                 max_age_days: int = 0, full_time_only: bool = True, skip_words=(), keep_words=(),
                 level_words=None, max_years: int | None = None) -> None:
        self.placement = placement
        self.seniority = candidate_seniority
        self.english_only, self.full_time_only = english_only, full_time_only
        self.max_age_days = max_age_days if max_age_days and max_age_days > 0 else 0
        self.skip_words, self.keep_words = list(skip_words or ()), list(keep_words or ())
        self.level_words, self.max_years = level_words, max_years

    def sifts(self) -> list[Sift]:
        """The rules this search uses, in the order they run."""
        out = [Sift("closed", "closed / no-longer-accepting postings", self._closed),
               Sift("other country", "jobs located in the United States", self._in_the_us),
               Sift("other country", "jobs in other countries, and remote jobs not open to yours", self._elsewhere),
               Sift("too many years", "roles asking for many years of experience", self._years)]
        if self.skip_words:
            out.append(Sift("skip word", f"roles with a word you skip ({', '.join(self.skip_words)})", self._skip_word))
        if self.full_time_only:
            out.append(Sift("part-time", "part-time roles", self._part_time))
        out.append(Sift("level", f"roles above your level (candidate: {self.seniority})", self._level))
        # With "English only" on: roles that need another language, and ads not written in English.
        # (Someone who speaks Czech turns "English only" off and keeps them.)
        if self.english_only:
            out.append(Sift(LANGUAGE_GROUP, "roles that need another language, and ads not written in English", language_reason))
        if self.max_age_days:
            out.append(Sift("too old", f"jobs older than {self.max_age_days} days", self._too_old))
        return out

    def apply(self, jobs: list[dict[str, Any]], dropped: list | None = None) -> list[dict[str, Any]]:
        """The postings every rule keeps, without duplicates; each one dropped goes to `dropped` with its reason."""
        for sift in self.sifts():
            kept = []
            for job in jobs:
                reason = sift.reason(job)
                if reason:
                    note_dropped(dropped, job, sift.group, reason)
                else:
                    kept.append(job)
            if len(kept) < len(jobs):
                print(f"  · filtered out {len(jobs) - len(kept)} {sift.label}")
            jobs = kept
        removed = prune_duplicate_leads(jobs)       # the same role posted twice (jobs.cz + prace.cz, or a LinkedIn repost)
        for job in removed:
            note_dropped(dropped, job, "duplicate", "The same role is already listed from another board.")
        if removed:
            print(f"  · filtered out {len(removed)} duplicate postings")
        return jobs

    # ── the reasons ─────────────────────────────────────────────────────────
    @staticmethod
    def _closed(job: dict[str, Any]) -> str:
        return CLOSED_REASON if filters.is_closed(f"{job.get('title', '')} {job.get('description', '')}") else ""

    def _in_the_us(self, job: dict[str, Any]) -> str:
        return self.placement.us_reason(job.get("location", ""), job_sources.is_remote_board(job.get("source", "")))

    def _elsewhere(self, job: dict[str, Any]) -> str:
        return self.placement.place_reason(job.get("location", ""), job.get("source", ""),
                                           job_sources.is_remote_board(job.get("source", "")))

    def _years(self, job: dict[str, Any]) -> str:
        if not filters.needs_too_many_years(job.get("description", ""), self.seniority, self.max_years):
            return ""
        return f"Asks for {filters.years_required(job.get('description', ''))}+ years of experience."

    def _skip_word(self, job: dict[str, Any]) -> str:
        word = filters.skipped_word(job["title"], self.skip_words, self.keep_words)
        return f'The title has a word you skip ("{word}").' if word else ""

    @staticmethod
    def _part_time(job: dict[str, Any]) -> str:
        return "Part-time, and you search for full-time only." if filters.is_part_time(job["title"], job.get("description", "")) else ""

    def _level(self, job: dict[str, Any]) -> str:
        word = filters.level_word(job["title"], self.seniority, self.level_words)
        return f'The title has a level you skip ("{word}").' if word else ""

    def _too_old(self, job: dict[str, Any]) -> str:
        return "" if _is_recent(job, self.max_age_days) else f"Posted more than {self.max_age_days} days ago."


@dataclass(frozen=True)
class SearchSettings:
    """How one search is run, from the Options: the city, how many results per keyword, and what the filters skip.
    The window and the command line (the weekly run) make it the same way, so both search alike."""
    where: str
    per_query: int = 15
    english_only: bool = True
    seniority: str = "junior"
    max_age_days: int = 0
    full_time_only: bool = True
    skip_words: tuple[str, ...] = ()
    keep_words: tuple[str, ...] = ()
    level_words: tuple[str, ...] | None = None      # None: decide from the level in the CV
    max_years: int | None = None                    # None: the usual limit for that level; 0: never

    @classmethod
    def from_options(cls, options: dict[str, Any], seniority: str = "junior") -> "SearchSettings":
        """From the Options as `ui_api.Api().options()` gives them (saved values over the defaults)."""
        o = options or {}
        level = o.get("level_words")
        return cls(where=str(o.get("where") or ""), per_query=int(o.get("per_query") or 15),
                   english_only=not o.get("all_languages"), seniority=seniority or "junior",
                   max_age_days=int(o.get("max_age_days") or 0), full_time_only=o.get("full_time_only", True) is not False,
                   skip_words=tuple(o.get("skip_words") or ()), keep_words=tuple(o.get("keep_words") or ()),
                   level_words=tuple(level) if isinstance(level, (list, tuple)) else None,
                   max_years=None if o.get("max_years") is None else int(o["max_years"]))

    def run(self, queries: list[str], source, dropped: list | None = None, progress=None) -> list[dict[str, Any]]:
        """The search itself (see `search`)."""
        return search(queries, where=self.where, per_query=self.per_query, source=source, english_only=self.english_only,
                      candidate_seniority=self.seniority, max_age_days=self.max_age_days, progress=progress,
                      full_time_only=self.full_time_only, skip_words=list(self.skip_words), keep_words=list(self.keep_words),
                      dropped=dropped, level_words=None if self.level_words is None else list(self.level_words),
                      max_years=self.max_years)


def take_in(jobs: list[dict[str, Any]], found: list[dict[str, Any]], english_only: bool = True,
            dropped: list | None = None) -> dict[str, int]:
    """Add what a search found to the job list, the same way after every search: roles you already applied to are
    left out, a role already listed from another board is kept once, an empty posting is read once more, and
    postings that stopped taking applications are noted. The Filtered out list is saved. Mutates `jobs`.
    Returns {found, added, skipped, known, closed}."""
    dropped = dropped if dropped is not None else []
    found, known = drop_known_applications(found, jobs, dropped=dropped)
    added, skipped = store.upsert(jobs, found)
    added -= len(prune_duplicate_leads(jobs))                       # same role already listed from another board
    added -= reread_missing(jobs, english_only=english_only, dropped=dropped)["removed"]
    closed = check_closed(jobs, dropped=dropped)                    # postings that stopped accepting applications
    save_dropped(dropped)
    return {"found": len(found), "added": added, "skipped": skipped, "known": known,
            "closed": closed["removed"] + closed["marked"]}


def search(
    queries: list[str],
    where: str = "",
    per_query: int = 15,
    source="czech",
    english_only: bool = True,
    candidate_seniority: str = "junior",
    max_age_days: int = 0,
    progress=None,
    full_time_only: bool = True,
    skip_words=(),
    keep_words=(),
    dropped: list[dict[str, Any]] | None = None,
    level_words=None,
    max_years: int | None = None,
) -> list[dict[str, Any]]:
    """Run each query against every active provider; return de-duped records.

    progress(done, total), if given, is called before each provider/query request.

    With english_only (default), ads in another language and roles that need one are dropped. Roles above the
    candidate's level are dropped for junior/mid. With max_age_days>0, jobs with a
    known posting date older than that are dropped (undated jobs are kept).

    Every posting a filter removes is added to `dropped` (if given) with the reason.

    level_words / max_years come from Options ("Skip levels above yours", "Skip jobs
    asking for … years"). None means: decide from the level in the CV.
    """
    if not str(where or "").strip():
        raise RuntimeError("No city to search in. Choose one in the app's Options.")
    placement = filters.Placement.for_search(where)                  # where this search is, read from Options once
    sources = job_sources.sources_for(source, max_age_days=max_age_days, country=placement.home)
    for names, served in job_sources.left_out(source, placement.home):
        print(f"  · {' and '.join(names)}: only for places in {' and '.join(c.title() for c in served)}, so not used for {where}")
    # What a source read is remembered while one search asks its roles, not from one search to the next:
    # the app can stay open for days.
    for src in sources:
        src.reset()
    if not sources:
        raise RuntimeError(
            f"No usable job source for source='{source}'.\n"
            "  • czech  → no key needed (jobs.cz + prace.cz)\n"
            "  • adzuna → set ADZUNA_* and a supported ADZUNA_COUNTRY\n"
            "  • jooble → set JOOBLE_API_KEY"
        )

    results = _collect(sources, queries, where, per_query, progress)
    for job in results:
        fill_company(job)
    results = SearchFilters(placement, candidate_seniority, english_only=english_only, max_age_days=max_age_days,
                            full_time_only=full_time_only, skip_words=skip_words, keep_words=keep_words,
                            level_words=level_words, max_years=max_years).apply(results, dropped)

    # Add a Prague market-rate desired-salary estimate to each listing.
    for job in results:
        m, a = salary.estimate(job["title"], candidate_seniority)
        job["desired_monthly_czk"], job["desired_annual_czk"] = m or "", a or ""
    return results
