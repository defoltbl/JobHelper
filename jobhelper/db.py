"""SQLite database for application responses (Agent 5).

One row per response email, keyed by the email Message-ID so re-scanning never
duplicates. Stores the extracted stage, categorised rejection reason, and links
back to the tracked job where possible.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from . import config, vault

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    msg_id TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS responses (
    msg_id             TEXT PRIMARY KEY,
    received_date      TEXT,
    from_addr          TEXT,
    subject            TEXT,
    job_id             TEXT,
    company            TEXT,
    role               TEXT,
    stage              TEXT,       -- rejection | interview | offer | assessment | acknowledged | other
    rejection_reason   TEXT,       -- free-text reason if stated
    rejection_category TEXT,       -- normalised bucket
    sentiment          TEXT,       -- positive | neutral | negative
    next_step          TEXT,
    summary            TEXT
);
"""

REJECTION_CATEGORIES = [
    "experience_insufficient", "skills_mismatch", "position_filled",
    "overqualified", "language_required", "location_or_visa",
    "went_with_other_candidate", "no_reason_given", "other",
]


@contextmanager
def _connect(write: bool = False):
    """Open the database in memory; the file on disk only ever holds the
    encrypted image. With write=True the image is saved back on success."""
    config.ensure_dirs()
    path = config.RESPONSES_DB
    conn = sqlite3.connect(":memory:")
    try:
        if path.exists() and path.stat().st_size:
            conn.deserialize(vault.read_bytes(path))
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)  # multiple statements
        yield conn
        if write:
            conn.commit()
            vault.write_bytes(path, conn.serialize())
    finally:
        conn.close()


def is_seen(msg_id: str) -> bool:
    with _connect() as conn:
        return conn.execute("SELECT 1 FROM seen WHERE msg_id = ?", (msg_id,)).fetchone() is not None


def mark_seen(msg_id: str) -> None:
    with _connect(write=True) as conn:
        conn.execute("INSERT OR IGNORE INTO seen (msg_id) VALUES (?)", (msg_id,))


def unmark_seen(msg_ids: list[str]) -> int:
    """Let the next scan read these messages again. Returns how many were queued."""
    if not msg_ids:
        return 0
    with _connect(write=True) as conn:
        before = conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
        conn.executemany("DELETE FROM seen WHERE msg_id = ?", [(m,) for m in msg_ids])
        return before - conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0]


def has_response(msg_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("SELECT 1 FROM responses WHERE msg_id = ?", (msg_id,))
        return cur.fetchone() is not None


def set_response_job(msg_id: str, job_id: str) -> bool:
    """File a stored reply under another application ('' = under none). True if the reply exists."""
    with _connect(write=True) as conn:
        cur = conn.execute("UPDATE responses SET job_id = ? WHERE msg_id = ?", (job_id or "", msg_id))
        return cur.rowcount > 0


def upsert_response(rec: dict[str, Any]) -> None:
    cols = ["msg_id", "received_date", "from_addr", "subject", "job_id", "company",
            "role", "stage", "rejection_reason", "rejection_category", "sentiment",
            "next_step", "summary"]
    values = [rec.get(c, "") for c in cols]
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "msg_id")
    with _connect(write=True) as conn:
        conn.execute(
            f"INSERT INTO responses ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(msg_id) DO UPDATE SET {updates}",
            values,
        )


def received_at(text: str) -> datetime:
    """When a reply arrived, from the email's Date header ("Mon, 5 Oct 2026 10:15:00
    +0200") or an ISO date. Unreadable dates sort as the oldest."""
    text = (text or "").strip()
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            when = datetime.fromisoformat(text)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


# How replies are listed: what needs an answer first, closed ones last.
STAGE_ORDER = ["offer", "interview", "assessment", "acknowledged", "other", "rejection"]


def stage_rank(stage: str) -> int:
    return STAGE_ORDER.index(stage) if stage in STAGE_ORDER else len(STAGE_ORDER) - 1


def all_responses() -> list[dict[str, Any]]:
    """Every stored reply, newest first by its real date (the header text itself
    starts with the weekday, so it cannot be sorted as text)."""
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM responses")]
    rows.sort(key=lambda r: received_at(r.get("received_date", "")), reverse=True)
    return rows


def relink_responses(old_job_id: str, new_job_id: str) -> int:
    """Point every reply stored for one job at another (two records merged into one)."""
    if not old_job_id or old_job_id == new_job_id:
        return 0
    with _connect(write=True) as conn:
        cur = conn.execute("UPDATE responses SET job_id = ? WHERE job_id = ?", (new_job_id, old_job_id))
        return cur.rowcount


def counts_by(column: str) -> dict[str, int]:
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT COALESCE(NULLIF({column}, ''), '(none)') AS k, COUNT(*) AS n "
            f"FROM responses GROUP BY k ORDER BY n DESC"
        ).fetchall()
        return {r["k"]: r["n"] for r in rows}


def rejection_reason_counts() -> dict[str, int]:
    """Category counts among rejections only."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT COALESCE(NULLIF(rejection_category, ''), 'no_reason_given') AS k, "
            "COUNT(*) AS n FROM responses WHERE stage = 'rejection' GROUP BY k ORDER BY n DESC"
        ).fetchall()
        return {r["k"]: r["n"] for r in rows}


def total() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
