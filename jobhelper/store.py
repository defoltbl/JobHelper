"""Job records: the on-disk database (data/jobs.json) and helpers.

Each job is a dict. jobs.json is the source of truth; the Excel table and the
saved cover letters are generated from it. Status updates (manual or from
email) modify this store and then re-render Excel.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from . import config, vault

# Recognised statuses (in rough lifecycle order).
STATUSES = [
    "found",        # discovered by Agent 2 (a lead)
    "letter_ready", # cover letter written by Agent 3 (a lead)
    "not_interested",  # a lead you dismissed: hidden, and never brought back by a later search
    "waiting",      # you applied — awaiting a response
    "interview",    # invited to interview / next stage
    "offer",        # offer received
    "rejected",     # turned down
    "on_hold",      # paused
]

# Leads (not applied yet) go to new_jobs.xlsx; the rest are applications.
NOT_INTERESTED = "not_interested"
LEAD_STATUSES = {"found", "letter_ready"}
# How applications are listed: what needs your attention first, closed ones last.
APPLICATION_ORDER = ["offer", "interview", "waiting", "on_hold", "rejected"]


def application_rank(job: dict[str, Any]) -> int:
    status = job.get("status", "")
    return APPLICATION_ORDER.index(status) if status in APPLICATION_ORDER else len(APPLICATION_ORDER)

APPLICATION_STATUSES = {"waiting", "interview", "offer", "rejected", "on_hold"}


def load_jobs() -> list[dict[str, Any]]:
    if not config.JOBS_JSON.exists():
        return []
    return [normalise(j) for j in json.loads(vault.read_text(config.JOBS_JSON)) if isinstance(j, dict)]


def save_jobs(jobs: list[dict[str, Any]]) -> None:
    config.ensure_dirs()
    vault.write_text(config.JOBS_JSON, json.dumps(jobs, ensure_ascii=False, indent=2))


def upsert(jobs: list[dict[str, Any]], new_jobs: list[dict[str, Any]]) -> tuple[int, int]:
    """Merge new_jobs into jobs by id. Returns (added, skipped_duplicates)."""
    by_id = {j["id"]: j for j in jobs}
    added = skipped = 0
    for nj in new_jobs:
        if nj["id"] in by_id:
            skipped += 1
            continue
        by_id[nj["id"]] = normalise(nj)
        added += 1
    jobs[:] = list(by_id.values())
    return added, skipped


def find(jobs: list[dict[str, Any]], job_id: str) -> dict[str, Any] | None:
    for j in jobs:
        if j["id"] == job_id:
            return j
    return None


def normalise(job: dict[str, Any]) -> dict[str, Any]:
    """Give a record every expected key (a scraper that builds its own dict may
    leave some out - a missing "status" once crashed the app). Extra keys stay."""
    missing = {k: v for k, v in new_job(**job).items() if k not in job}
    if missing:
        job.update(missing)
    return job


def new_job(**fields: Any) -> dict[str, Any]:
    """Create a job record with all expected keys defaulted."""
    job = {
        "id": fields.get("id", ""),
        "title": fields.get("title", ""),
        "company": fields.get("company", ""),
        "location": fields.get("location", ""),
        "source": fields.get("source", ""),
        "url": fields.get("url", ""),
        "date_posted": fields.get("date_posted", ""),   # when the job was posted (YYYY-MM-DD)
        "desired_monthly_czk": fields.get("desired_monthly_czk", ""),  # Prague market estimate
        "desired_annual_czk": fields.get("desired_annual_czk", ""),
        "salary": fields.get("salary", ""),
        "description": fields.get("description", ""),
        "match_score": fields.get("match_score"),      # 0-100, set by Agent 3
        "match_reason": fields.get("match_reason", ""),
        "match_tier": fields.get("match_tier", ""),   # strong (60+) | moderate (50-59)
        "cover_letter_file": fields.get("cover_letter_file", ""),
        "tailored_cv_file": fields.get("tailored_cv_file", ""),
        "status": fields.get("status", "found"),
        "date_found": fields.get("date_found", date.today().isoformat()),
        "date_applied": fields.get("date_applied", ""),
        "last_update": fields.get("last_update", date.today().isoformat()),
        "notes": fields.get("notes", ""),
    }
    return job


def url_id(url: str) -> str:
    """A short id made from an address, the same on every run. (Python's own hash()
    changes with every start, so a posting got a new id on each search and was listed again.)"""
    import hashlib
    return hashlib.sha1((url or "").encode("utf-8")).hexdigest()[:16]


def slugify(text: str, max_len: int = 40) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:max_len].strip("-") or "job"
