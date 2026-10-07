"""Import your own pre-written cover letters into the tracker.

Scans a folder of cover letters (default ~/Documents/CV/Letter) named like
`<Name>_CoverLetter_<Company>.docx`, links each to a tracked job by
company name, and seeds a job record for companies you applied to that aren't
tracked yet — so their email history and interview progress show up too.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from . import config, email_client, store

_GENERIC = {"cover letter", "letter", "coverletter", ""}


def _decamel(text: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    return text


def parse_company(filename: str) -> str:
    stem = Path(filename).stem
    m = re.search(r"coverletter[_\-\s]+(.+)", stem, re.IGNORECASE)
    raw = m.group(1) if m else stem
    raw = re.sub(r"[_\-\s]+[A-Za-z0-9]$", "", raw)  # drop a trailing variant like _M / _2
    return _decamel(raw.replace("_", " ")).strip()


def scan(letters_dir: Path | None = None) -> list[dict[str, str]]:
    """Return [{company, file_name, file_path}] for each cover letter found."""
    letters_dir = letters_dir or config.COVER_LETTERS_DIR
    if not letters_dir.exists():
        return []
    out: list[dict[str, str]] = []
    seen_companies: dict[str, str] = {}
    for p in sorted(letters_dir.iterdir()):
        if p.suffix.lower() not in {".docx", ".pdf"} or not p.is_file():
            continue
        company = parse_company(p.name)
        if company.lower() in _GENERIC:
            continue
        # Prefer .docx over .pdf when both exist for the same company.
        key = company.lower()
        if key in seen_companies and p.suffix.lower() == ".pdf":
            continue
        seen_companies[key] = p.name
        out.append({"company": company, "file_name": p.name, "file_path": str(p)})
    # De-dup keeping first (docx) per company.
    uniq: dict[str, dict[str, str]] = {}
    for rec in out:
        uniq.setdefault(rec["company"].lower(), rec)
    return list(uniq.values())


def _match(company: str, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    toks = email_client.company_tokens(company)
    if not toks:
        return None
    best, best_score = None, 0
    for job in jobs:
        jtoks = email_client.company_tokens(job.get("company", ""))
        score = len(toks & jtoks)
        if score > best_score:
            best, best_score = job, score
    return best if best_score > 0 else None


def import_letters(
    jobs: list[dict[str, Any]],
    letters_dir: Path | None = None,
    mark_applied: bool = True,
) -> dict[str, int]:
    """Link cover letters to jobs and seed past applications. Mutates `jobs`."""
    stats = {"linked": 0, "seeded": 0, "scanned": 0}
    for rec in scan(letters_dir):
        stats["scanned"] += 1
        match = _match(rec["company"], jobs)
        if match:
            match["cover_letter_file"] = rec["file_name"]
            if match.get("status") in (None, "", "found"):
                match["status"] = "letter_ready"
            stats["linked"] += 1
        else:
            job = store.new_job(
                id=f"letter-{store.slugify(rec['company'])}",
                title="(existing application)",
                company=rec["company"],
                source="manual",
                cover_letter_file=rec["file_name"],
                status="waiting" if mark_applied else "letter_ready",
                date_applied=date.today().isoformat() if mark_applied else "",
                notes="Imported from your cover-letter folder.",
            )
            jobs.append(job)
            stats["seeded"] += 1
    return stats
