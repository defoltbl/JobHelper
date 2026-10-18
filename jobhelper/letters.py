"""Import your own pre-written cover letters into the tracker.

Scans your own cover letters (data/my_letters/, or COVER_LETTERS_DIR in .env) named like
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
    found: dict[str, dict[str, str]] = {}
    for p in sorted(letters_dir.iterdir()):
        if p.suffix.lower() not in {".docx", ".pdf"} or not p.is_file():
            continue
        company = parse_company(p.name)
        key = company.lower()
        if key in _GENERIC:
            continue
        # one letter per company: the first Word file, or the first PDF when there is no Word file (whatever sorts first)
        kept = found.get(key)
        if kept is None or (kept["file_name"].lower().endswith(".pdf") and p.suffix.lower() == ".docx"):
            found[key] = {"company": company, "file_name": p.name, "file_path": str(p)}
    return list(found.values())


def _match(company: str, jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The job this letter's company belongs to. The names must be the same company:
    equal once spacing, accents and legal suffixes are ignored ("TDSYNNEX" = "TD SYNNEX"),
    or one name's words all inside the other ("ESET" in "ESET Research"). One shared
    word is not enough: "Good Data" is not "NTT DATA"."""
    key = email_client.norm_company(company)
    toks = email_client.company_tokens(company)
    if not key and not toks:
        return None
    best, best_score = None, 0
    for job in jobs:
        name = job.get("company", "")
        if key and email_client.norm_company(name) == key:
            return job
        jtoks = email_client.company_tokens(name)
        if toks and jtoks and (toks <= jtoks or jtoks <= toks):
            score = len(toks & jtoks)
            if score > best_score:
                best, best_score = job, score
    return best


def _written_for(lead: dict[str, Any], file_path: str) -> bool:
    """True if a letter of your own was written for this lead: the lead has no
    letter yet and the file is newer than the day the job was found. A letter that
    is older was written for an earlier application at that company."""
    if lead.get("cover_letter_file"):
        return False
    try:
        written = date.fromtimestamp(Path(file_path).stat().st_mtime)
        found = date.fromisoformat((lead.get("date_found") or "")[:10])
    except (OSError, ValueError):
        return False
    return written >= found


def import_letters(
    jobs: list[dict[str, Any]],
    letters_dir: Path | None = None,
    mark_applied: bool = True,
) -> dict[str, int]:
    """Link your own cover letters to jobs and seed past applications. Mutates `jobs`.

    A letter belongs to the application it was written for. It is never put on a
    new job at the same company just because the company matches: that job gets a
    fresh letter from the app. Order: the job that already carries the file; an
    application at that company; a lead the letter was clearly written for (see
    _written_for); otherwise a new "(existing application)" record."""
    stats = {"linked": 0, "seeded": 0, "scanned": 0}
    for rec in scan(letters_dir):
        stats["scanned"] += 1
        # a job that already carries this very file is its job, whatever the company is called now
        # (you may have merged or renamed it); never seed a second application for the same letter
        if any(j.get("cover_letter_file") == rec["file_name"] for j in jobs):
            stats["linked"] += 1
            continue
        match = _match(rec["company"], [j for j in jobs if j.get("status") in store.APPLICATION_STATUSES])
        if match is None:
            lead = _match(rec["company"], [j for j in jobs if j.get("status") in store.LEAD_STATUSES])
            if lead is not None and _written_for(lead, rec["file_path"]):
                match = lead
                match["own_letter"] = True              # yours: the app never replaces it
        if match is None:
            match = store.find(jobs, f"letter-{store.slugify(rec['company'])}")     # seeded before, letter name changed
        if match:
            match["cover_letter_file"] = rec["file_name"]
            if match.get("status") in (None, "", "found"):
                match["status"] = "letter_ready"
            stats["linked"] += 1
        else:
            job = store.new_job(
                id=f"letter-{store.slugify(rec['company'])}",
                title=store.EXISTING_APPLICATION,
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
