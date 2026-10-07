"""A free first look at a posting, before any Claude call is spent on it.

Scoring a job costs one model call; most postings a broad search returns are
plainly not for this candidate (sales, mechanical design, a role that needs
German). This module drops only those plain cases, from the title and the
keyword overlap with the master CV. Anything in doubt is left for the model:
measured on 143 jobs the model had scored, it must never skip one that scored
30 or more. A skipped job stays in the list with the reason shown, and
can be sent to scoring by hand.
"""
from __future__ import annotations

import re
from typing import Any

from . import keywords

# Titles from another profession. Checked on whole words.
_OFF_PROFILE = re.compile(
    r"\b(?:account (?:executive|manager)|sales|business development|marketing|recruit\w*|hr\b|hris|payroll|"
    r"accountant|accounting|účetní|audit\w*|tax\b|legal|lawyer|paralegal|"
    r"investment|trader|trading|crypto|equities|underwrit\w*|risk modell?er|actuar\w*|"
    r"mechanical|electrical|civil|plc|hardware design|pcb|projektant\w*|konstrukt\w*|cad\b|"
    r"functional safety|quality inspector|manufactur\w*|(?:machine|production|shipping|forklift) operator|warehouse|logistic\w*|forklift|"
    r"driver|nurse|caregiver|chef|cook|cleaner|"
    r"customer care|customer service|call cent\w*|nightshift|night shift|"
    r"annotator|content moderator|translator|copywriter|teacher|lecturer)\b", re.IGNORECASE)

# Titles that are this profile even if an off-profile word is next to them
# ("Sales Engineer" is not, "Software Engineer - Sales Tools" is).
_ON_PROFILE = re.compile(
    r"\b(?:software|developer|vývojář\w*|programmer|programátor\w*|backend|back-end|frontend|full[- ]?stack|python|kotlin|android|"
    r"machine learning|\bml\b|\bai\b|data (?:scientist|engineer|analyst)|devops|cloud engineer|qa|tester|test engineer)\b",
    re.IGNORECASE)

# Levels far above a graduate, when written in the title.
_TOO_HIGH = re.compile(r"\b(?:vp|vice president|l3|level 3|tier 3|iii|director|head of)\b", re.IGNORECASE)

# Another working language asked for in the title.
_OTHER_LANGUAGE = re.compile(
    r"\b(?:german|deutsch|dutch|french|italian|spanish|polish|hungarian|nordic|swedish|danish|norwegian|finnish|"
    r"portuguese|turkish|hebrew|arabic)(?:[- ]speaking| speaker)?\b|\bwith (?:german|dutch|french)\b|\(m/w/d\)|entwickler",
    re.IGNORECASE)


def reason_to_skip(job: dict[str, Any], cv_keywords: set[str], check_level: bool = True) -> str:
    """'' when the job should be scored; otherwise a short reason it was skipped."""
    title = job.get("title") or ""
    description = job.get("description") or ""
    on_profile = bool(_ON_PROFILE.search(title))

    lang = _OTHER_LANGUAGE.search(title)
    if lang:
        return f"The title asks for another language ({lang.group(0).strip()})."
    high = _TOO_HIGH.search(title)
    if high and check_level:
        return f"The title is a senior level ({high.group(0)})."
    off = _OFF_PROFILE.search(title)
    if off and not on_profile:
        return f"The title is another profession ({off.group(0).lower()})."
    if description.strip():
        wanted = keywords.extract(description)
        tech = [k for k in wanted if k not in ("English", "Czech", "German", "French", "Agile", "Scrum", "Excel", "Jira", "Confluence", "Troubleshooting")]
        have = [k for k in tech if k in cv_keywords]
        if len(tech) >= 3 and not have and not on_profile:
            return "None of the technologies in the posting are in your CV (" + ", ".join(tech[:4]) + ")."
    return ""


def apply(jobs: list[dict[str, Any]], cv_text: str, check_level: bool = True) -> int:
    """Mark unscored leads that are plainly not a fit, so they are not sent to
    the model. Returns how many were marked. Jobs the user sent back to scoring
    (`prefilter_override`) and jobs already scored are left alone.
    check_level=False (no level words in Options: a senior candidate) keeps
    director / head-of titles in."""
    cv_keywords = set(keywords.extract(cv_text))
    marked = 0
    for job in jobs:
        if job.get("prefilter_override"):
            job.pop("prefilter", None)             # the user asked for this one to be scored
            continue
        if job.get("status") != "found" or job.get("match_score") is not None:
            continue
        reason = reason_to_skip(job, cv_keywords, check_level)
        if reason:
            if job.get("prefilter") != reason:
                marked += 1
            job["prefilter"] = reason
        else:
            job.pop("prefilter", None)
    return marked
