"""A free first look at a posting, before any Claude call is spent on it.

Scoring a job costs one model call; most postings a broad search returns are
plainly not for this candidate (another profession, a role that needs a language
the CV does not show). This module drops only those plain cases, from the title and the
keyword overlap with the master CV. Anything in doubt is left for the model:
measured on 143 jobs the model had scored, it must never skip one that scored
30 or more. A skipped job stays in the list with the reason shown, and
can be sent to scoring by hand.
"""
from __future__ import annotations

import re
from typing import Any

from . import keywords

# Professions, grouped into fields. Nothing here belongs to one kind of candidate: which fields
# are "yours" is worked out from the roles you look for (Options, or the CV's analysis), see
# fields_of(). A title from a field that is not yours is skipped; a title that also names one of
# your fields is not ("Sales Engineer" is sales, "Software Engineer - Sales Tools" is software).
# Checked on whole words.
FIELDS: dict[str, re.Pattern] = {name: re.compile(r"\b(?:" + words + r")\b", re.IGNORECASE) for name, words in {
    "software and IT": (
        r"software|developer|vývojář\w*|programmer|programátor\w*|backend|back-end|frontend|front-end|full[- ]?stack|python|kotlin|android|"
        r"machine learning|ml|ai|data (?:scientist|engineer|analyst)|devops|cloud engineer|qa|tester|test engineer"),
    "sales and marketing": r"account (?:executive|manager)|sales|business development|marketing",
    "customer support": r"customer care|customer service|call cent\w*|nightshift|night shift",
    "people and recruiting": r"recruit\w*|hr|hris|payroll",
    "finance": (r"accountant|accounting|účetní|audit\w*|tax|investment|trader|trading|crypto|equities|underwrit\w*|"
                r"risk modell?er|actuar\w*"),
    "law": r"legal|lawyer|paralegal",
    "engineering and manufacturing": (
        r"mechanical|electrical|civil|plc|hardware design|pcb|projektant\w*|konstrukt\w*|cad|functional safety|quality inspector|"
        r"manufactur\w*|(?:machine|production) operator"),
    "logistics": r"shipping operator|forklift operator|warehouse|logistic\w*|forklift|driver",
    "care and health": r"nurse|caregiver",
    "hospitality": r"chef|cook|cleaner",
    "language and teaching": r"annotator|content moderator|translator|copywriter|teacher|lecturer",
}.items()}

_FROM_CV_HITS = 2          # a field counts as yours from the CV alone when it is named at least this often


def _fields_in(text: str) -> dict[str, int]:
    return {name: len(pattern.findall(text or "")) for name, pattern in FIELDS.items()}


def fields_of(roles, cv_text: str = "") -> list[str]:
    """The fields you work in: every field one of your roles names. When no role names any
    (no roles given, or roles in words this list does not know), the field the CV itself names
    most. [] means "not known": then no title is skipped for its profession."""
    names = " | ".join(str(r) for r in (roles or []) if str(r).strip())
    mine = [name for name, hits in _fields_in(names).items() if hits]
    if mine:
        return mine
    counts = _fields_in(cv_text)
    most = max(counts.values(), default=0)
    return [name for name, hits in counts.items() if hits == most] if most >= _FROM_CV_HITS else []


def _phrase(text: str) -> re.Pattern | None:
    words = [re.escape(w) for w in re.findall(r"[^\W_]+(?:[+#.][^\W_]*)*", str(text or ""))]
    return re.compile(r"(?<![^\W_])" + r"[\s\-/]+".join(words) + r"(?![^\W_])", re.IGNORECASE) if words else None


# Levels far above a graduate, when written in the title.
_TOO_HIGH = re.compile(r"\b(?:vp|vice president|l3|level 3|tier 3|iii|director|head of)\b", re.IGNORECASE)

# Another working language asked for in the title: the word found, and the language it means.
_OTHER_LANGUAGE = re.compile(
    r"\b(?:german|deutsch|dutch|french|italian|spanish|polish|hungarian|nordic|swedish|danish|norwegian|finnish|"
    r"portuguese|turkish|hebrew|arabic)(?:[- ]speaking| speaker)?\b|\bwith (?:german|dutch|french)\b|\(m/w/d\)|entwickler",
    re.IGNORECASE)
_LANGUAGE_OF = {"deutsch": "german", "(m/w/d)": "german", "entwickler": "german"}


def _language_named(found: str) -> str:
    word = found.strip().lower()
    word = re.sub(r"^with\s+|[- ]speaking$| speaker$", "", word)
    return _LANGUAGE_OF.get(word, word)


def reason_to_skip(job: dict[str, Any], cv_keywords: set[str], check_level: bool = True,
                   mine=(), unwanted=(), wanted=(), languages=()) -> str:
    """'' when the job should be scored; otherwise a short reason it was skipped.
    mine: your fields (fields_of). unwanted / wanted: the role names from Options.
    languages: the languages your CV shows (lower case)."""
    title = job.get("title") or ""
    description = job.get("description") or ""
    mine = [name for name in mine if name in FIELDS]
    on_profile = any(FIELDS[name].search(title) for name in mine)

    lang = _OTHER_LANGUAGE.search(title)
    if lang and _language_named(lang.group(0)) not in {str(x).lower() for x in languages}:
        return f"The title asks for another language ({lang.group(0).strip()})."
    high = _TOO_HIGH.search(title)
    if high and check_level:
        return f"The title is a senior level ({high.group(0)})."
    # a kind of role you said you do not want, unless the title is also one you named as wanted
    if not any(p and p.search(title) for p in map(_phrase, wanted or [])):
        for role in unwanted or []:
            pattern = _phrase(role)
            if pattern and pattern.search(title):
                return f"You listed this kind of role as not wanted ({str(role).strip()})."
    if mine and not on_profile:
        for name, pattern in FIELDS.items():
            off = pattern.search(title) if name not in mine else None
            if off:
                return f"The title is another profession ({off.group(0).lower()})."
    if description.strip():
        found = keywords.extract(description)
        tech = [k for k in found if k not in ("English", "Czech", "German", "French", "Agile", "Scrum", "Excel", "Jira", "Confluence", "Troubleshooting")]
        have = [k for k in tech if k in cv_keywords]
        if len(tech) >= 3 and not have and not on_profile:
            return "None of the technologies in the posting are in your CV (" + ", ".join(tech[:4]) + ")."
    return ""


def apply(jobs: list[dict[str, Any]], cv_text: str, check_level: bool = True, roles=None, unwanted=None, wanted=None) -> int:
    """Mark unscored leads that are plainly not a fit, so they are not sent to
    the model. Returns how many were marked. Jobs the user sent back to scoring
    (`prefilter_override`) and jobs already scored are left alone.
    check_level=False (no level words in Options: a senior candidate) keeps
    director / head-of titles in. roles: every role you look for (they decide which
    professions are yours); unwanted / wanted: the role names from Options."""
    from . import filters
    mine = fields_of(roles, cv_text)
    languages = filters.cv_languages(cv_text)
    cv_keywords = set(keywords.extract(cv_text))
    marked = 0
    for job in jobs:
        if job.get("prefilter_override"):
            job.pop("prefilter", None)             # the user asked for this one to be scored
            continue
        if job.get("status") != "found" or job.get("match_score") is not None:
            continue
        reason = reason_to_skip(job, cv_keywords, check_level, mine=mine, unwanted=unwanted, wanted=wanted, languages=languages)
        if reason:
            if job.get("prefilter") != reason:
                marked += 1
            job["prefilter"] = reason
        else:
            job.pop("prefilter", None)
    return marked
