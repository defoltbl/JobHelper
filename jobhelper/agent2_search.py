"""Agent 2 — search for jobs (multi-provider).

Providers:
  • Jooble  — free API, COVERS THE CZECH REPUBLIC (Prague). Aggregates Czech
              boards such as jobs.cz / prace.cz. Get a key at
              https://jooble.org/api/about  → set JOOBLE_API_KEY in .env
  • Adzuna  — free API, does NOT support Czech; good for pl/de/gb/at/... Set
              ADZUNA_COUNTRY accordingly.

The provider(s) are chosen automatically from what's configured and whether the
country is supported. All results are normalised to job records and de-duped.
Deterministic HTTP — spends no Claude subscription usage.
"""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Any, Callable

import requests

from . import (config, email_client, filters, language, salary, scrapers_ats,
               scrapers_cz, scrapers_intl, scrapers_remote, store)

ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
JOOBLE_URL = "https://jooble.org/api/{key}"


def _clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)  # strip any HTML tags
    return re.sub(r"\s+", " ", text).strip()


# ── Adzuna ──────────────────────────────────────────────────────────────────
def _adzuna_query(what: str, where: str, per_page: int) -> list[dict[str, Any]]:
    params = {
        "app_id": config.ADZUNA_APP_ID,
        "app_key": config.ADZUNA_APP_KEY,
        "what": what,
        "where": where,
        "results_per_page": per_page,
        "content-type": "application/json",
    }
    url = ADZUNA_URL.format(country=config.ADZUNA_COUNTRY, page=1)
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    out = []
    for raw in resp.json().get("results", []):
        smin, smax = raw.get("salary_min"), raw.get("salary_max")
        salary = ""
        if smin or smax:
            salary = f"{int(smin or 0):,} - {int(smax or 0):,}".replace(",", " ")
        out.append(store.new_job(
            id=f"adzuna-{raw.get('id')}",
            title=_clean(raw.get("title", "")),
            company=_clean((raw.get("company") or {}).get("display_name", "")),
            location=_clean((raw.get("location") or {}).get("display_name", "")),
            source="adzuna",
            url=raw.get("redirect_url", ""),
            salary=salary,
            description=_clean(raw.get("description", "")),
            date_posted=(raw.get("created") or "")[:10],
        ))
    return out


# ── Jooble ──────────────────────────────────────────────────────────────────
def _jooble_query(what: str, where: str, per_page: int) -> list[dict[str, Any]]:
    url = JOOBLE_URL.format(key=config.JOOBLE_API_KEY)
    resp = requests.post(url, json={"keywords": what, "location": where}, timeout=30)
    resp.raise_for_status()
    out = []
    for raw in resp.json().get("jobs", [])[:per_page]:
        out.append(store.new_job(
            id=f"jooble-{raw.get('id')}",
            title=_clean(raw.get("title", "")),
            company=_clean(raw.get("company", "")),
            location=_clean(raw.get("location", "")),
            source=f"jooble/{_clean(raw.get('source', ''))}"[:40],
            url=raw.get("link", ""),
            salary=_clean(raw.get("salary", "")),
            description=_clean(raw.get("snippet", "")),
        ))
    return out


def active_providers(source: str = "czech", max_age_days: int = 0) -> list[tuple[str, Callable[[str, str, int], list[dict[str, Any]]]]]:
    """Which providers to use, given the chosen source.

    source:
      "czech"    → jobs.cz + prace.cz + LinkedIn (default; Prague market)
      "linkedin" → LinkedIn only
      "remote"   → RemoteOK + We Work Remotely (English remote roles)
      "careers"  → your companies' career centers (data/companies.json)
      "adzuna"   → Adzuna API (pl/de/gb/... — NOT Czech)
      "jooble"   → Jooble API (needs a key for the target region)
      "all"      → every configured provider

    max_age_days restricts LinkedIn to recent postings (its f_TPR window).
    """
    import functools
    provs: list[tuple[str, Callable]] = []
    if source in ("czech", "all"):
        provs.append(("jobs.cz", scrapers_cz.jobs_cz))
        provs.append(("prace.cz", scrapers_cz.prace_cz))
    if source in ("czech", "linkedin", "all"):
        provs.append(("linkedin", functools.partial(scrapers_intl.linkedin, max_age_days=max_age_days)))
    if source in ("remote", "all"):
        provs.append(("remoteok", scrapers_remote.remoteok))
        provs.append(("weworkremotely", scrapers_remote.weworkremotely))
    if source in ("careers", "czech", "all") and scrapers_ats.load_companies():
        provs.append(("careers", scrapers_ats.careers))
    if source in ("jooble", "all") and config.has_jooble():
        provs.append(("jooble", _jooble_query))
    if source in ("adzuna", "all") and config.adzuna_available():
        provs.append(("adzuna", _adzuna_query))
    return provs


# Words to strip from a title before comparing roles (seniority / gender / noise).
_ROLE_NOISE = {
    "junior", "senior", "medior", "mid", "lead", "jr", "sr", "entry", "graduate",
    "the", "for", "and", "with", "our", "team", "role", "position", "new",
    "m", "f", "d", "n", "x", "mfd", "fmd",
}


def role_key(title: str) -> frozenset[str]:
    """Normalise a job title to its core role tokens (drops seniority/gender/noise)."""
    import re
    tokens = re.findall(r"[a-z0-9+#]{2,}", (title or "").lower())
    return frozenset(t for t in tokens if t not in _ROLE_NOISE)


def _same_role(a: frozenset[str], b: frozenset[str]) -> bool:
    """True if two role keys look like the same role (Jaccard >= 0.5 or subset)."""
    if not a or not b:
        return False  # unknown role → don't treat as duplicate (allow the lead)
    if a <= b or b <= a:
        return True
    return len(a & b) / len(a | b) >= 0.5


def drop_known_applications(
    new_jobs: list[dict[str, Any]],
    existing_jobs: list[dict[str, Any]],
    exclude_statuses: set[str] | None = None,
    dropped: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Remove a new lead only if you've already applied to the SAME role at the
    SAME company (any application status, incl. rejected).

    Different roles at the same company are kept — you can apply to a company
    multiple times for different positions.
    """
    # ... and a role you marked "not interested" does not come back as a repost either
    exclude = exclude_statuses or (store.APPLICATION_STATUSES | {store.NOT_INTERESTED})
    known = [(j["company"], role_key(j.get("title", "")))
             for j in existing_jobs if j.get("status") in exclude and j.get("company")]

    kept, n_dropped = [], 0
    for nj in new_jobs:
        company = nj.get("company", "")
        nrole = role_key(nj.get("title", ""))
        # the same company, not merely a name that shares a word with it ("Good Data" is not "NTT DATA")
        if company and any(_same_role(nrole, kr) and email_client.same_company(company, kc) for kc, kr in known):
            n_dropped += 1
            note_dropped(dropped, nj, "already applied", "You already applied for this role at this company.")
            continue
        kept.append(nj)
    return kept, n_dropped


# Backwards-compatible alias (now role-aware).
drop_known_companies = drop_known_applications


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
    apps = [(j["company"], role_key(j.get("title", "")))
            for j in jobs if j.get("status") in store.APPLICATION_STATUSES and j.get("company")]

    removed, kept = [], []
    for j in jobs:
        if j.get("status") in store.LEAD_STATUSES:
            company = j.get("company", "")
            rk = role_key(j.get("title", ""))
            if company and any(_same_role(rk, ar) and email_client.same_company(company, ac) for ac, ar in apps):
                removed.append(j)
                continue
        kept.append(j)
    jobs[:] = kept
    return removed


CLOSED_RECHECK_DAYS = 3        # a posting's page is asked again at most this often
CLOSED_PER_SEARCH = 40         # and at most this many pages per search, the longest unchecked first
CLOSED_REASON = "The posting no longer accepts applications."


def posting_closed(job: dict[str, Any]) -> bool | None:
    """Ask a posting's own page whether it still accepts applications.
    True / False, or None when the board gives no clear answer (or is not one the app can ask)."""
    if not (job.get("id", "").startswith("linkedin-") or "linkedin.com" in (job.get("url") or "")):
        return None
    number = re.search(r"(\d{6,})", job.get("id", "") + " " + (job.get("url") or ""))
    if not number:
        return None
    try:
        text, closed, _posted = scrapers_intl._fetch_detail(number.group(1))
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
        due = [j for j in leads if id(j) not in verdict and str(j.get("closed_checked") or "") <= stale]
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
            from . import scrapers_intl
            digits = re.search(r"(\d{6,})", job.get("id", "") + " " + url)
            return scrapers_intl._fetch_detail(digits.group(1))[0] if digits else ""
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
    """An error's text without the address's query part: API keys travel there
    (…?app_id=…&app_key=…) and must never reach a log file or the screen."""
    return re.sub(r"(https?://[^\s?'\"]+)\?[^\s'\"]*", r"\1", str(error))


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


def _dropped_path():
    return config.DATA_DIR / "filtered_out.json"


# Reasons a later run would apply again at once, so bringing the posting back would not last.
NO_BRING_BACK = {"duplicate", "already applied", "closed"}


def save_dropped(rows: list[dict[str, Any]], when: str = "") -> None:
    """Keep what the latest search filtered out (replaces the previous search's list)."""
    import json
    from datetime import datetime
    from . import vault
    config.ensure_dirs()
    vault.write_text(_dropped_path(), json.dumps(
        {"when": when or datetime.now().strftime("%d %b %H:%M"), "total": len(rows), "rows": rows[:MAX_DROPPED]},
        ensure_ascii=False, indent=1))


def load_dropped() -> dict[str, Any]:
    import json
    from . import vault
    try:
        data = json.loads(vault.read_text(_dropped_path()))
    except (OSError, ValueError, vault.VaultError):
        return {"when": "", "total": 0, "rows": []}
    rows = [r for r in data.get("rows", []) if isinstance(r, dict)] if isinstance(data, dict) else []
    return {"when": str(data.get("when", "")) if isinstance(data, dict) else "", "rows": rows,
            "total": int(data.get("total", len(rows))) if isinstance(data, dict) else len(rows)}


def search(
    queries: list[str],
    where: str = "",
    per_query: int = 15,
    source: str = "czech",
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
        raise RuntimeError("No city to search in. Choose one in the app's Options (or pass --where to run.py).")
    # What the career sites and remote boards answered is remembered while one search asks its queries,
    # not from one search to the next: the app can stay open for days.
    scrapers_ats._cache.clear()
    scrapers_remote._remoteok_payload.cache_clear()
    scrapers_remote._wwr_feed.cache_clear()
    providers = active_providers(source, max_age_days=max_age_days)
    if not providers:
        raise RuntimeError(
            f"No usable job source for source='{source}'.\n"
            "  • czech  → no key needed (jobs.cz + prace.cz)\n"
            "  • adzuna → set ADZUNA_* and a supported ADZUNA_COUNTRY\n"
            "  • jooble → set JOOBLE_API_KEY"
        )

    found: dict[str, dict[str, Any]] = {}
    steps, step = len(providers) * len(queries), 0
    for name, fn in providers:
        got = 0
        for q in queries:
            if progress:
                progress(step, steps)
            step += 1
            try:
                for job in fn(q, where, per_query):
                    if job["id"] and job["id"] not in found:
                        job["query"] = q            # which keyword found it (for the Insights view)
                        found[job["id"]] = job
                        got += 1
            except requests.HTTPError as e:
                print(f"  ! {name} error for '{q}': {safe_error(e)}")
            except requests.RequestException as e:
                print(f"  ! {name} network error for '{q}': {safe_error(e)}")
        print(f"  · {name}: +{got} new listings")

    results = list(found.values())
    for job in results:
        fill_company(job)

    def sift(group: str, why, label: str) -> None:
        """Keep the postings `why` has nothing against; note the others with the reason."""
        nonlocal results
        kept, n = [], 0
        for job in results:
            reason = why(job)
            if reason:
                n += 1
                note_dropped(dropped, job, group, reason)
            else:
                kept.append(job)
        results = kept
        if n:
            print(f"  · filtered out {n} {label}")

    sift("closed", lambda j: "No longer accepts applications."
         if filters.is_closed(f"{j.get('title','')} {j.get('description','')}") else "",
         "closed / no-longer-accepting postings")
    # A "Prague" search can return Prague, Nebraska.
    sift("other country", lambda j: f"Located in the United States ({j.get('location', '')})."
         if filters.is_us_location(j.get("location", "")) else "", "jobs located in the United States")
    # Career sites list a company's openings everywhere; keep the ones here or remote.
    sift("other country", lambda j: f"A career-site job somewhere else ({j.get('location', '') or 'no location given'})."
         if j.get("source") == "careers" and not filters.location_fits(j.get("location", ""), where) else "",
         "career-site jobs in other countries")
    sift("too many years", lambda j: f"Asks for {filters.years_required(j.get('description', ''))}+ years of experience."
         if filters.needs_too_many_years(j.get("description", ""), candidate_seniority, max_years) else "",
         "roles asking for many years of experience")
    if skip_words:
        def skip_reason(j):
            word = filters.skipped_word(j["title"], skip_words, keep_words)
            return f'The title has a word you skip ("{word}").' if word else ""
        sift("skip word", skip_reason, f"roles with a word you skip ({', '.join(skip_words)})")
    if full_time_only:
        sift("part-time", lambda j: "Part-time, and you search for full-time only."
             if filters.is_part_time(j["title"], j.get("description", "")) else "", "part-time roles")

    # The same role posted twice (jobs.cz + prace.cz, or a LinkedIn repost).
    removed = prune_duplicate_leads(results)
    for job in removed:
        note_dropped(dropped, job, "duplicate", "The same role is already listed from another board.")
    if removed:
        print(f"  · filtered out {len(removed)} duplicate postings")

    # Roles above the candidate's level (junior/mid only).
    def level_reason(j):
        word = filters.level_word(j["title"], candidate_seniority, level_words)
        return f'The title has a level you skip ("{word}").' if word else ""
    sift("level", level_reason, f"roles above your level (candidate: {candidate_seniority})")
    # With "English only" on: roles that need another language, and ads not written in English.
    # (Someone who speaks Czech turns "English only" off and keeps them.)
    if english_only:
        sift(LANGUAGE_GROUP, language_reason, "roles that need another language, and ads not written in English")
    if max_age_days and max_age_days > 0:
        sift("too old", lambda j: "" if _is_recent(j, max_age_days) else f"Posted more than {max_age_days} days ago.",
             f"jobs older than {max_age_days} days")

    # Add a Prague market-rate desired-salary estimate to each listing.
    for job in results:
        m, a = salary.estimate(job["title"], candidate_seniority)
        job["desired_monthly_czk"], job["desired_annual_czk"] = m, a
    return results
