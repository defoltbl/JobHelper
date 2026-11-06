"""Job records: the on-disk database (data/jobs.json) and helpers.

Each job is a dict. jobs.json is the source of truth; the Excel table and the
saved cover letters are generated from it. Status updates (manual or from
email) modify this store and then re-render Excel.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import threading
import time
from contextlib import contextmanager
from datetime import date
from typing import Any, Callable

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
OPEN_STATUSES = LEAD_STATUSES | {"waiting", "interview", "on_hold"}      # a job you may still fill in a form for


def applied_on_import(job: dict[str, Any]) -> bool:
    """Whether a job's apply date is only the day it was imported from your letters folder, not a day you applied."""
    return job.get("source") == "manual" and bool(job.get("date_applied")) and job.get("date_applied") == job.get("date_found")


class JobsBusy(RuntimeError):
    """Another process is working on the job list: writing now would put an older copy over its changes."""


class RunLock:
    """One lock on the job list between processes – the open window and the weekly run (#72). A process that works on
    the list for minutes (a search, a scan, the weekly run) holds it, so another process never writes an older copy of
    the list over its changes. It is held per process: the window's own hand edits during its own search go on, as
    `JobEditor.live` keeps them; another process's writes wait or are refused with BUSY."""

    BUSY = "The weekly run is working on your jobs right now. Try again when it has finished."
    COMMAND_BUSY = ("✗ The app is working on your jobs right now (a search, a scan or the weekly run). Nothing was "
                    "changed. Run this again when it has finished.")
    _held = 0                        # how many holders in this process
    _file = None
    _guard = threading.Lock()

    @staticmethod
    def path():
        return config.DATA_DIR / ".jobs.lock"

    @classmethod
    def take(cls, wait: float = 0.0) -> bool:
        """Hold the lock (waiting up to `wait` seconds for another process to let it go). False when it stays busy."""
        deadline = time.monotonic() + max(0.0, wait)
        while not cls._try_once():
            left = deadline - time.monotonic()
            if left <= 0:
                return False
            time.sleep(min(2.0, max(0.05, left)))           # never while holding _guard: the window's threads go on
        return True

    @classmethod
    def _try_once(cls) -> bool:
        with cls._guard:
            if cls._held:
                cls._held += 1
                return True
            config.ensure_dirs()
            f = os.fdopen(os.open(cls.path(), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "r+")   # never through a link
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close()
                return False
            except OSError:          # a disk without file locks (ENOLCK, ENOTSUP): no other process can share the list there
                f.close()
                f = None
            cls._file, cls._held = f, 1
            return True

    @classmethod
    def release(cls) -> None:
        with cls._guard:
            if not cls._held:
                return
            cls._held -= 1
            if not cls._held and cls._file is not None:
                fcntl.flock(cls._file, fcntl.LOCK_UN)
                cls._file.close()
                cls._file = None

    @classmethod
    def command(cls, fn: Callable[[], int]) -> int:
        """A command (run.py, status.py) that holds the lock for its whole run, so a save half-way through is never
        refused and the work lost. In the weekly run the lock is already held by the same process. 1 while busy."""
        if not cls.take():
            print(cls.COMMAND_BUSY)
            return 1
        try:
            return fn()
        finally:
            cls.release()

    @classmethod
    @contextmanager
    def holding(cls):
        """Hold the lock for one change of the list (read, change, write), so another process never starts in between.
        Raises JobsBusy while another process holds it."""
        if not cls.take():
            raise JobsBusy(cls.BUSY)
        try:
            yield
        finally:
            cls.release()


def load_jobs() -> list[dict[str, Any]]:
    if not config.JOBS_JSON.exists():
        return []
    return [normalise(j) for j in json.loads(vault.read_text(config.JOBS_JSON)) if isinstance(j, dict)]


def save_jobs(jobs: list[dict[str, Any]]) -> None:
    """Write the job list, holding RunLock. Refused (JobsBusy) while another process works on it, never written over it."""
    with RunLock.holding():
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


def add_note(job: dict[str, Any], text: str, day: str = "") -> None:
    """Put a dated line at the top of a job's notes ("[2026-10-18] Followed up by email."): the newest first."""
    stamp = day or date.today().isoformat()
    job["notes"] = (f"[{stamp}] {text}\n" + (job.get("notes") or "")).strip()


# Titles the app gives a job it knows only by its company: an application imported from your letters, or one a
# reply named. They are no role (Insights groups them apart, a real title from a reply replaces them).
EXISTING_APPLICATION, FROM_EMAIL = "(existing application)", "(from email response)"
PLACEHOLDER_TITLES = frozenset({EXISTING_APPLICATION, FROM_EMAIL, "(unknown role)"})


def has_real_title(job: dict[str, Any]) -> bool:
    title = str(job.get("title") or "").strip()
    return bool(title) and title.lower() not in PLACEHOLDER_TITLES


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


def repair_statuses(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give every job with a status the app does not know one it does: an application (it has an apply date, or came
    from an email) becomes "waiting", anything else a new job again. Each one gets a note. Returns the jobs that were
    changed. Changes `jobs`."""
    fixed = []
    for j in jobs:
        if j.get("status") in STATUSES:
            continue
        applied = bool(j.get("date_applied")) or j.get("source") in ("email", "manual")
        add_note(j, f"Status was \"{j.get('status')}\", which the app does not know; set to {'waiting' if applied else 'found'}.")
        j["status"] = "waiting" if applied else "found"
        fixed.append(j)
    return fixed
