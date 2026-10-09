"""Seniority filtering — keep listings realistic for the candidate's level.

A junior/mid candidate shouldn't be shown (or spend scoring calls on) senior,
lead, principal, manager, or architect roles. Applied to every source.
"""
from __future__ import annotations

import re

# Title markers that indicate a role above junior/mid level.
_SENIOR_PATTERNS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bteam\s*lead\b", r"\bprincipal\b",
    r"\bhead\s+of\b", r"\bchief\b", r"\barchitects?\b", r"\bmanagers?\b",
    r"\bstaff\b", r"\bexpert\b", r"\bdirectors?\b", r"\bvedoucí\b", r"\bhead\b",
]
_SENIOR_RE = re.compile("|".join(_SENIOR_PATTERNS), re.IGNORECASE)
# "management" is not in the list: it names a field ("Risk Management", "Repository Management"), not a level
_JUNIOR_RE = re.compile(r"\b(junior|jr\.?|entry[- ]level|graduate|absolvent)\b", re.IGNORECASE)

# Levels for which we filter out senior titles.
_FILTERS_SENIOR = {"junior", "mid", "medior", "entry", "graduate"}


# The words shown in Options ("Skip levels above yours") for a junior or mid candidate.
LEVEL_WORDS = ["senior", "sr", "lead", "team lead", "principal", "head of", "head", "chief", "architect",
               "manager", "staff", "expert", "director", "vedoucí"]


def default_level_words(candidate_seniority: str) -> list[str]:
    """What Options starts with: the level words for a junior/mid CV, nothing for a senior one."""
    return list(LEVEL_WORDS) if (candidate_seniority or "junior").strip().lower() in _FILTERS_SENIOR else []


def default_max_years(candidate_seniority: str) -> int:
    """Postings asking for this many years or more are skipped (0 = never)."""
    return _YEARS_LIMIT.get((candidate_seniority or "junior").strip().lower(), 0)


def level_word(title: str, candidate_seniority: str, words=None) -> str:
    """The word that puts this title above the candidate's level, or ''.

    `words` is the list from Options; None means "decide from the CV's level"
    (the built-in list for junior/mid, nothing for senior). A title that itself
    says junior or graduate is never above the level."""
    if _JUNIOR_RE.search(title or ""):
        return ""  # "Junior Project Manager", "Analyst (Junior+)": the title itself says the level
    if words is None:
        if (candidate_seniority or "junior").strip().lower() not in _FILTERS_SENIOR:
            return ""  # senior/lead candidates: don't filter anything out
        m = _SENIOR_RE.search(title or "")
        return m.group(0).lower() if m else ""
    return next((str(w) for w in words if _word_in(title or "", str(w))), "")


# Detects a real Czech-language *requirement* (not "Czech Republic", not "Czech
# is a plus"). Matches phrasings like "Czech language", "fluent Czech",
# "native Czech", "knowledge of Czech", "Czech B2", "čeština".
_CZECH_LANG = re.compile(
    r"(czech\s+(?:language|native|speaker|speaking|proficiency|fluency|skills)"
    r"|(?:fluent|native|speak|spoken|written|knowledge of|command of|proficient in)\s+czech"
    r"|czech\s+[abc][12]|[abc][12]\s+(?:level\s+)?czech"
    r"|čeština|český jazyk|znalost češtiny|česky)",
    re.IGNORECASE,
)
_LANG_OPTIONAL = re.compile(
    r"(advantage|plus|nice to have|benefit|welcome|optional|preferred|would be|is a plus)",
    re.IGNORECASE,
)


def requires_czech(text: str) -> bool:
    """True if the posting requires Czech at a working level (excludes 'a plus')."""
    for sentence in re.split(r"[.\n;•|]", text or ""):
        if _CZECH_LANG.search(sentence) and not _LANG_OPTIONAL.search(sentence):
            return True
    return False


# Phrases that mean the posting is closed / filled and shouldn't be shown (EN + CZ).
_CLOSED = re.compile(
    r"no longer accepting applications|no longer available|this (job|position) is no longer|"
    r"not currently accepting applications|position has been filled|vacancy is closed|"
    r"applications are closed|pozice (byla )?obsazena|nábor (byl )?ukončen|inzerát .*ukončen",
    re.IGNORECASE,
)


def is_closed(text: str) -> bool:
    """True if a posting's text says it no longer accepts applications."""
    return bool(_CLOSED.search(text or ""))


# US state codes after a comma ("Fremont, NE", "Prague, NE" - there is a Prague in
# Nebraska). Some sources answer a Prague search with these. "DE" is left out:
# in a European search it means Germany, not Delaware.
_US_STATES = ("AL AK AZ AR CA CO CT FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ "
              "NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC").split()
_US_LOCATION = re.compile(r",\s*(?:%s)\b(?!\w)|\bUnited States\b|\bUSA\b" % "|".join(_US_STATES))


def is_us_location(location: str) -> bool:
    """True for a location in the United States (never wanted in a Prague/EU search)."""
    return bool(_US_LOCATION.search(location or ""))


_NEAR = re.compile(r"prag|praha|czech|česk|cesk|remote|anywhere|emea|europe|worldwide|\bcz\b", re.IGNORECASE)


def location_fits(location: str, where: str) -> bool:
    """For sources that list a company's jobs worldwide (career sites): is this
    one in the searched city, in Czechia, or remote? Unknown locations pass."""
    loc = (location or "").strip()
    if not loc:
        return True
    return bool(_NEAR.search(loc)) or (where or "").strip().lower() in loc.lower()


_PART_TIME = re.compile(r"part[\s-]?time|teilzeit|částečný úvazek|zkrácený úvazek|poloviční úvazek|\bbrigáda\b", re.IGNORECASE)
_FULL_TIME = re.compile(r"full[\s-]?time|vollzeit|plný úvazek", re.IGNORECASE)


def is_part_time(title: str, description: str = "") -> bool:
    """True for a part-time role: the title says so, or the description mentions
    part-time and never full-time ("full-time or part-time" stays in)."""
    if _PART_TIME.search(title or ""):
        return True
    text = description or ""
    return bool(_PART_TIME.search(text)) and not _FULL_TIME.search(text)


_YEARS = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?(?:years?|yrs?)\b[^.\n]{0,60}?\b(?:experience|exp\b|background|track record)",
    re.IGNORECASE)
_YEARS_LIMIT = {"junior": 4, "entry": 4, "graduate": 4, "mid": 7, "medior": 7}


def years_required(text: str) -> int:
    """The largest 'N years of experience' the posting asks for (0 if none)."""
    found = []
    for m in _YEARS.finditer(text or ""):
        # "5 years of experience is an advantage" is a wish, not a requirement
        sentence = re.split(r"[.\n;•|]", (text or "")[m.start():])[0]
        if not _LANG_OPTIONAL.search(sentence):
            found.append(int(m.group(1)))
    return max([n for n in found if n <= 30], default=0)


def needs_too_many_years(text: str, candidate_seniority: str, limit: int | None = None) -> bool:
    """True if the posting asks for `limit` years or more. None = the usual limit
    for the candidate's level; 0 = never."""
    if limit is None:
        limit = _YEARS_LIMIT.get((candidate_seniority or "junior").strip().lower())
    return bool(limit) and years_required(text) >= limit


def _fold(text: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def _word_in(title: str, word: str) -> bool:
    """Whole word or phrase, case and accent blind, with a simple plural:
    "intern" matches "Intern" and "Interns", never "Internal" or "International"."""
    w = _fold(word).strip()
    if not w:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(w)}s?(?![a-z0-9])", _fold(title)))


def skipped_word(title: str, skip_words, keep_words=()) -> str:
    """The skip word that rules this title out, or '' if it stays.
    A title that also contains one of the exception words is always kept."""
    if any(_word_in(title, k) for k in (keep_words or ())):
        return ""
    return next((w for w in (skip_words or ()) if _word_in(title, w)), "")


# ── a required language the CV does not show ────────────────────────────────
# Checked in plain code after the model has scored a posting: the model sometimes lets a
# required language slide ("excellent communication skills in Czech or Slovak" got 55).
_LANGUAGES = ["english", "czech", "slovak", "german", "french", "dutch", "polish", "italian", "spanish", "portuguese",
              "hungarian", "russian", "ukrainian", "swedish", "danish", "norwegian", "finnish", "turkish", "romanian"]
_LANG_WORD = re.compile(r"\b(" + "|".join(_LANGUAGES) + r")\b(?!\s+(?:republic|market|office|team|company|customers?|clients?|branch|"
                        r"law|legislation|crown|koruna|entity|subsidiar\w*|bank|government|citizens?|nationals?|border|economy|"
                        r"region|capital|culture|cuisine|beer))", re.IGNORECASE)
_LANG_CUE = re.compile(r"\b(fluen\w+|native|proficien\w+|require[sd]?|requirement|must|mandatory|essential|necessary|excellent|advanced|"
                       r"business[- ]level|professional[- ]level|working[- ]level|[bc][12]|speak\w*|communicat\w+|written and spoken|"
                       r"spoken and written|command of|knowledge of)\b", re.IGNORECASE)
_LANG_NOT = re.compile(r"\b(not|no|isn't|is not|without)\b[^.]{0,30}\b(require[sd]?|needed|necessary|mandatory)\b", re.IGNORECASE)
_LANG_WEAK = re.compile(r"\b(basic|beginner|elementary|a1|a2|learning|improving|limited)\b", re.IGNORECASE)


def required_languages(text: str) -> list[list[str]]:
    """The languages a posting requires. Each entry is a group of alternatives:
    "German and English" gives [["german"], ["english"]], "Czech or Slovak" gives [["czech", "slovak"]].
    A language named as a plus, or said not to be required, is left out."""
    groups: list[list[str]] = []
    for sentence in re.split(r"[.\n;•|!?]", text or ""):
        if not _LANG_CUE.search(sentence) or _LANG_OPTIONAL.search(sentence) or _LANG_NOT.search(sentence) \
                or re.search(r"\bif you (?:are|speak|have|know)\b|\bmultilingual\b|\bother languages?\b", sentence, re.IGNORECASE):
            continue                                    # a wish, a negation or an "if you also speak …" offer
        found = list(_LANG_WORD.finditer(sentence))
        current: list[str] = []
        for i, m in enumerate(found):
            name = m.group(1).lower()
            joined = i > 0 and re.search(r"\bor\b|/", sentence[found[i - 1].end():m.start()])
            if current and not joined:
                groups.append(current)
                current = []
            if name not in current:
                current.append(name)
        if current:
            groups.append(current)
    unique = []
    for group in groups:
        if sorted(group) not in [sorted(g) for g in unique]:
            unique.append(group)
    return unique


_LANG_LEVEL = re.compile(r"\b(native|fluent|fluency|proficient|advanced|intermediate|upper[- ]intermediate|professional|"
                         r"working|[bc][12]|speaker|speaking|mother tongue)\b", re.IGNORECASE)


def cv_languages(cv_text: str) -> set[str]:
    """The languages a CV shows at a working level. English is assumed for a CV written in
    English. A language counts when the CV states a level for it ("German – B2", "native
    Ukrainian speaker"); "Czech Master's degree" is not a language, and a language marked
    basic, beginner, A1 or A2 does not count."""
    text = cv_text or ""
    strong, weak = set(), set()
    for m in _LANG_WORD.finditer(text):
        name = m.group(1).lower()
        after = text[m.end(): m.end() + 28].split("\n")[0]
        before = text[max(0, m.start() - 28): m.start()].split("\n")[-1]
        # only the nearest words count: "Russian – Native · English – B2" must not give English "native"
        after_own = re.split(r"[·•|;,]", after)[0]
        before_own = re.split(r"[·•|;,]", before)[-1]
        if _LANG_WEAK.search(after_own):
            weak.add(name)
        elif _LANG_LEVEL.search(after_own) or _LANG_LEVEL.search(before_own) or re.search(r"\band\s*$", before_own):
            strong.add(name)
    return {"english"} | (strong - weak)


def unmet_language(description: str, cv_text: str) -> str:
    """"Czech or Slovak" if the posting requires a language the CV does not show, else ''."""
    known = cv_languages(cv_text)
    for group in required_languages(description):
        if not known & set(group):
            return " or ".join(name.capitalize() for name in group)
    return ""
