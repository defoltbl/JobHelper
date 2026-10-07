"""Find and merge application records that are the same application twice.

It happens when one application reaches the tracker by two routes: a cover
letter imported from your folder creates "(existing application)" for "CSOB",
and the company's email creates another record for "ČSOB (KBC)". Their history
is then split over two rows.

Two records are the same application when their company is the same and at
least one of them has no real role title (a placeholder), or both have the same
role. Two different roles at one company are never merged.
"""
from __future__ import annotations

import difflib
from typing import Any

from . import db, email_client, store
from .agent2_search import role_key


_PLACEHOLDER_TITLES = {"(existing application)", "(from email response)", "(unknown role)"}


def is_placeholder(job: dict[str, Any]) -> bool:
    """A record the app made without knowing the role. A real title that merely
    starts with a bracket, like "(Junior) Data Engineer", is not one."""
    title = (job.get("title") or "").strip().lower()
    return not title or title in _PLACEHOLDER_TITLES


def _company(job: dict[str, Any]) -> str:
    return email_client.norm_company(job.get("company", ""))


def _same_role(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ra, rb = role_key(a.get("title", "")), role_key(b.get("title", ""))
    return bool(ra) and ra == rb


def confidence(a: dict[str, Any], b: dict[str, Any]) -> str:
    """'sure' | 'possible' | '' for two application records."""
    ca, cb = _company(a), _company(b)
    if not ca or not cb or ca == "unknown" or cb == "unknown":
        return ""
    if not (is_placeholder(a) or is_placeholder(b) or _same_role(a, b)):
        return ""                                  # two real, different roles at one company
    if ca == cb:
        return "sure"
    short, long = sorted((ca, cb), key=len)
    if len(short) >= 5 and (long.startswith(short) or difflib.SequenceMatcher(None, ca, cb).ratio() >= 0.85):
        return "possible"                          # "gooddata" / "gooddataai", a typo, a longer legal name
    return ""


def find(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pairs of application records that look like one application.
    Each: {keep, drop, confidence}; pairs the user said are different are left out."""
    apps = [j for j in jobs if j.get("status") in store.APPLICATION_STATUSES]
    out, used = [], set()
    for i, a in enumerate(apps):
        for b in apps[i + 1:]:
            if a["id"] in used or b["id"] in used:
                continue
            if b["id"] in (a.get("not_duplicate_of") or []) or a["id"] in (b.get("not_duplicate_of") or []):
                continue
            level = confidence(a, b)
            if level:
                keep, drop = _order(a, b)
                out.append({"keep": keep["id"], "drop": drop["id"], "confidence": level})
                used.update((a["id"], b["id"]))
    return out


def _order(a: dict[str, Any], b: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Which record survives: the one with a real role title, then the one with a posting link."""
    def worth(j):
        return (not is_placeholder(j), bool(j.get("url")), bool(j.get("description")), len(j.get("notes") or ""))
    return (a, b) if worth(a) >= worth(b) else (b, a)


_RANK = {"waiting": 1, "on_hold": 1, "interview": 2, "offer": 3}


def merge(jobs: list[dict[str, Any]], keep_id: str, drop_id: str) -> bool:
    """Fold record `drop_id` into `keep_id`: nothing the dropped record knew is lost."""
    keep, drop = store.find(jobs, keep_id), store.find(jobs, drop_id)
    if not keep or not drop or keep is drop:
        return False
    # status: a rejection is final; otherwise the furthest stage reached
    if "rejected" in (keep.get("status"), drop.get("status")):
        keep["status"] = "rejected"
    elif _RANK.get(drop.get("status"), 0) > _RANK.get(keep.get("status"), 0):
        keep["status"] = drop["status"]
    # your own cover letter stays your own: it is carried over and still never rewritten
    if drop.get("cover_letter_file") and not keep.get("cover_letter_file"):
        keep["cover_letter_file"] = drop["cover_letter_file"]
        if drop.get("source") == "manual" or drop.get("own_letter"):
            keep["own_letter"] = True
    if drop.get("tailored_cv_file") and not keep.get("tailored_cv_file"):
        keep["tailored_cv_file"] = drop["tailored_cv_file"]
    # the earliest real apply date
    dates = [j["date_applied"] for j in (keep, drop) if j.get("date_applied")
             and not (j.get("source") == "manual" and j["date_applied"] == j.get("date_found"))]
    if dates:
        if min(dates) != keep.get("date_applied"):
            keep["date_applied"] = min(dates)
            source = next((j.get("date_applied_source") for j in (keep, drop) if j.get("date_applied") == min(dates)), None)
            keep.pop("date_applied_source", None)
            if source:
                keep["date_applied_source"] = source
    for field in ("url", "description", "location", "followup_date", "next_step", "stages_path", "salary"):
        if drop.get(field) and not keep.get(field):
            keep[field] = drop[field]
    notes = [n for n in (keep.get("notes"), drop.get("notes")) if n]
    keep["notes"] = "\n".join(dict.fromkeys(notes)).strip()
    keep["last_update"] = max(keep.get("last_update") or "", drop.get("last_update") or "")
    db.relink_responses(drop["id"], keep["id"])
    jobs[:] = [j for j in jobs if j is not drop]
    return True


def auto_merge(jobs: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Merge every pair that is certain. Returns what was merged."""
    done = []
    while True:
        pair = next((p for p in find(jobs) if p["confidence"] == "sure"), None)
        if not pair:
            return done
        names = {j["id"]: j.get("company", "") for j in jobs}
        if merge(jobs, pair["keep"], pair["drop"]):
            done.append({"kept": names[pair["keep"]], "dropped": names[pair["drop"]]})
        else:
            return done


def keep_separate(jobs: list[dict[str, Any]], a_id: str, b_id: str) -> bool:
    """Remember that these two are different applications (never suggested again)."""
    a, b = store.find(jobs, a_id), store.find(jobs, b_id)
    if not a or not b:
        return False
    a["not_duplicate_of"] = sorted(set(a.get("not_duplicate_of") or []) | {b_id})
    return True
