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
        r"machine learning|ml|ai|data (?:scientist|engineer|analyst)|datov\w+ analyti\w+|devops|cloud engineer|qa|tester|test engineer"),
    "sales and marketing": (r"account (?:executive|manager)|sales|business development|marketing|brand manager|public relations|"
                            r"obchodní zástupce"),
    "customer support": r"customer care|customer service|call cent\w*|nightshift|night shift",
    "people and recruiting": r"recruit\w*|hr|hris|payroll|talent acquisition|personalist\w*",
    "finance": (r"accountant|accounting|účetní|bookkeeper|audit\w*|tax|investment|trader|trading|crypto|equities|underwrit\w*|"
                r"risk modell?er|actuar\w*"),
    "law": r"legal|lawyer|paralegal|attorney|solicitor|notary|právník\w*",
    "engineering and manufacturing": (
        r"mechanical|electrical|civil|plc|hardware design|pcb|projektant\w*|konstrukt\w*|cad|functional safety|quality inspector|"
        r"manufactur\w*|(?:machine|production) operator"),
    "logistics": r"shipping operator|forklift operator|warehouse|logistic\w*|forklift|driver|courier|skladník\w*|řidič\w*",
    "care and health": r"nurse|caregiver|physician|dentist|paramedic|physiotherapist|midwife|pharmacist|zdravotní sestra|pečovatel\w*",
    "hospitality": r"chef|cook|cleaner|waiter|waitress|bartender|barista|housekeeper|kuchař\w*|číšník\w*",
    "language and teaching": r"annotator|content moderator|translator|copywriter|teacher|lecturer|tutor|učitel\w*|lektor\w*",
    "design and media": (r"graphic design\w*|interior design\w*|fashion design\w*|illustrator|art director|photographer|video editor|"
                         r"journalist"),
    "science and laboratory": r"lab technician|laboratory technician|chemist|biologist|microbiolog\w*|clinical research\w*",
    "construction and trades": (r"construction|site manager|site supervisor|quantity surveyor|bricklayer|plumber|electrician|carpenter|"
                                r"welder|roofer|stavbyvedoucí|zedník\w*"),
    "office and public administration": (r"receptionist|office manager|secretary|administrative assistant|personal assistant|"
                                         r"civil servant|public administration|úředník\w*"),
    "retail": r"cashier|store manager|shop assistant|merchandiser|retail",
    "security and facilities": r"security guard|janitor|caretaker|facility manager",
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


def chosen_fields(names) -> list[str]:
    """The fields picked by hand in Options, in the order of FIELDS; names this list does not have are dropped."""
    picked = {str(n) for n in names} if isinstance(names, (list, tuple, set)) else set()
    return [name for name in FIELDS if name in picked]


def role_phrase(text: str) -> re.Pattern | None:
    """A role's words as one phrase to find in a title ("support" in "IT Support Specialist"); None for no words."""
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


# Named in postings of every profession: they say nothing about which profession a posting is.
_EVERYWHERE = {*keywords.SPOKEN, "Agile", "Scrum", "Excel", "Jira", "Confluence", "Troubleshooting",
               "Project management", "MS Office", "PowerPoint", "B2B", "UX", "GDPR", "Driving licence"}


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
    if not any(p and p.search(title) for p in map(role_phrase, wanted or [])):
        for role in unwanted or []:
            pattern = role_phrase(role)
            if pattern and pattern.search(title):
                return f"You listed this kind of role as not wanted ({str(role).strip()})."
    if mine and not on_profile:
        for name, pattern in FIELDS.items():
            off = pattern.search(title) if name not in mine else None
            if off:
                return f"The title is another profession ({off.group(0).lower()})."
    if description.strip():
        found = keywords.extract(description)
        tech = [k for k in found if k not in _EVERYWHERE]
        have = [k for k in tech if k in cv_keywords]
        if len(tech) >= 3 and not have and not on_profile:
            return "None of the skills and tools the posting names are in your CV (" + ", ".join(tech[:4]) + ")."
    return ""


def apply(jobs: list[dict[str, Any]], cv_text: str, check_level: bool = True, roles=None, unwanted=None, wanted=None, fields=None) -> int:
    """Mark unscored leads that are plainly not a fit, so they are not sent to
    the model. Returns how many were marked. Jobs the user sent back to scoring
    (`prefilter_override`) and jobs already scored are left alone.
    check_level=False (no level words in Options: a senior candidate) keeps
    director / head-of titles in. roles: every role you look for (they decide which
    professions are yours); unwanted / wanted: the role names from Options.
    fields: the professions picked by hand in Options; when given they are used as they are."""
    from . import filters
    mine = chosen_fields(fields) or fields_of(roles, cv_text)
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


# the kinds of role Options suggests as you type, and the words a typed search role is checked against: a role must
# share one of them (or name a profession of FIELDS), which refuses gibberish and most typos (#61: the window kept these)
ROLE_SUGGESTIONS = (
    "junior", "medior", "middle", "senior", "entry level", "graduate", "intern", "trainee",
    "software developer", "software engineer", "backend developer", "frontend developer",
    "full stack developer", "python developer", "java developer", "javascript developer",
    "c# developer", "golang developer", "web developer", "mobile developer", "android developer",
    "ios developer", "data scientist", "data analyst", "data engineer", "machine learning engineer",
    "ai engineer", "qa engineer", "test engineer", "automation engineer", "devops engineer",
    "site reliability engineer", "cloud engineer", "it support", "help desk", "service desk",
    "system administrator", "business analyst", "product manager", "ux designer")
_ROLE_WORD = re.compile(r"[a-z0-9+#]+")
ROLE_WORDS = frozenset(w for r in ROLE_SUGGESTIONS for w in _ROLE_WORD.findall(r)) | frozenset("""
    react node typescript php ruby rust kotlin swift sql database db security network networking infrastructure platform
    sre scrum project program manager consultant specialist architect lead apprentice helpdesk admin administrator
    fullstack ml llm nlp genai api rest microservices embedded firmware hardware linux windows aws azure gcp kubernetes
    docker spring django flask fastapi analytics analyst bi etl warehouse quant developer engineer programmer coder
    tester sdet support desk service it ai qa qe ux ui web mobile cloud data prague praha czech czechia republic english
    speaking remote hybrid onsite junior senior medior middle entry graduate intern trainee level scientist machine
    learning frontend backend software android ios golang go java javascript python csharp automation devops
    reliability designer business product system systems""".split())


def looks_like_role(text: str) -> bool:
    """Whether a typed search role shares a word with the role words (ROLE_WORDS)."""
    return any(w in ROLE_WORDS for w in _ROLE_WORD.findall(str(text or "").lower()))
