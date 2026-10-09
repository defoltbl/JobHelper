"""Cheap, deterministic language heuristic — no LLM, no network.

Used to keep only English-language job ads when "English only" is on: an ad
written in English is a strong signal that the role works in English, an ad in
the local language usually expects that language. `detect` names the language,
so that the reason shown for a dropped posting is true whatever it was.
"""
from __future__ import annotations

import re

# Characters that essentially only appear in Czech/Slovak text.
_CZECH_CHARS = set("ěščřžýáíéúůňťďĚŠČŘŽÝÁÍÉÚŮŇŤĎ")

# Non-Latin scripts: Japanese (hiragana/katakana), CJK ideographs, Korean,
# Cyrillic, Greek, Arabic, Hebrew, Thai, Devanagari. Text in these isn't English.
_NON_LATIN = re.compile(
    r"[぀-ヿ㐀-鿿가-힯Ѐ-ӿͰ-Ͽ"
    r"؀-ۿ֐-׿฀-๿ऀ-ॿ＀-￯]"
)

# Common Czech function words (job-ad vocabulary included).
_CZECH_WORDS = {
    "a", "se", "na", "v", "pro", "je", "že", "práce", "nabízíme", "požadujeme",
    "znalost", "zkušenosti", "měsíc", "možnost", "hledáme", "místo", "úvazek",
    "vzdělání", "jazyk", "dovednosti", "náplň", "benefity", "mzda", "plat",
}
# Common English function + job-ad words (all unambiguously English — note "a"
# and "to" are skipped because they collide with Czech words).
_ENGLISH_WORDS = {
    "the", "and", "for", "with", "you", "we", "our", "your", "are", "will",
    "experience", "skills", "team", "work", "role", "requirements", "join",
    "developer", "engineer", "looking", "seeking", "position", "opportunity",
    "opportunities", "responsibilities", "offer", "candidate", "knowledge",
    "ability", "development", "company", "we're", "you'll", "who", "what",
    "strong", "years", "including", "environment", "please", "apply",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-ZěščřžýáíéúůňťďĚŠČŘŽÝÁÍÉÚŮŇŤĎ]+", text.lower())


# The most common words of other languages an ad may be written in. Words that are also
# ordinary English ("in", "a", "per", "to") are left out, so English text scores nothing here.
_OTHER_WORDS = {
    "German": {"und", "der", "das", "mit", "für", "wir", "sie", "ist", "nicht", "eine", "einen", "oder", "bei", "auf", "sind",
               "werden", "ihre", "unser", "unsere", "aufgaben", "kenntnisse", "erfahrung", "bieten", "suchen", "sowie", "zum", "zur"},
    "French": {"le", "les", "des", "et", "pour", "vous", "nous", "une", "dans", "avec", "votre", "notre", "est", "sur", "aux",
               "poste", "expérience", "équipe", "recherchons", "vos", "nos", "du", "au", "qui"},
    "Spanish": {"el", "los", "las", "y", "para", "con", "una", "del", "que", "nuestro", "nuestra", "experiencia", "equipo",
                "buscamos", "trabajo", "por", "tus", "como", "más", "ofrecemos"},
    "Italian": {"il", "gli", "con", "una", "di", "che", "della", "delle", "nostro", "esperienza", "lavoro", "cerchiamo",
                "sono", "nel", "alla", "siamo", "anche", "più", "offriamo", "ricerca"},
    "Polish": {"w", "z", "na", "się", "oraz", "jest", "dla", "nie", "praca", "pracy", "doświadczenie", "oferujemy", "szukamy",
               "wymagania", "znajomość", "zespół", "lub", "od", "przy", "naszym"},
    "Dutch": {"en", "het", "een", "van", "voor", "met", "je", "wij", "zijn", "onze", "ervaring", "jij", "bij", "naar",
              "functie", "werken", "zoeken", "niet", "ook", "als", "ons", "jouw"},
    "Portuguese": {"os", "para", "com", "uma", "em", "que", "não", "nossa", "nosso", "experiência", "equipe", "equipa",
                   "trabalho", "você", "da", "ao", "dos", "das", "mais", "procuramos"},
    "Slovak": {"sme", "ste", "ponúkame", "hľadáme", "požadujeme", "práca", "skúsenosti", "znalosť", "alebo", "pre", "pri",
               "ktorý", "ktorá", "ako", "aj", "náplň", "výhody", "mzda", "pracovné"},
}
_SCRIPTS = [("Ukrainian", re.compile(r"[іїєґІЇЄҐ]")), ("Russian", re.compile(r"[Ѐ-ӿ]")), ("Japanese", re.compile(r"[぀-ヿ]")),
            ("Korean", re.compile(r"[가-힯]")), ("Chinese", re.compile(r"[㐀-鿿]")), ("Greek", re.compile(r"[Ͱ-Ͽ]")),
            ("Arabic", re.compile(r"[؀-ۿ]")), ("Hebrew", re.compile(r"[֐-׿]")), ("Thai", re.compile(r"[฀-๿]")),
            ("Hindi", re.compile(r"[ऀ-ॿ]"))]
_SLOVAK_CHARS = set("ľĺŕôĽĹŔÔ")
# Letters of Czech and Slovak that French, Spanish, Portuguese, German and Polish do not have
# ("é", "á", "í" are shared with them and say nothing).
_CZECH_ONLY = set("ěščřžůťďňýľĺŕĚŠČŘŽŮŤĎŇÝĽĹŔ")


def detect(text: str) -> str:
    """The language a text is written in when it is plainly not English: "Czech", "German",
    "Russian" …, or "another language" when it cannot be named. "" for English, and for text
    too short to tell (it is then kept, not dropped)."""
    text = (text or "").strip()
    if len(text) < 15:
        return ""

    # Text in a non-Latin script (Japanese, Chinese, Korean, Russian, etc.): stray English
    # tech terms ("3D", "AI") don't make it English.
    non_latin = len(_NON_LATIN.findall(text))
    latin = len(re.findall(r"[a-zA-Z]", text))
    if non_latin >= 8 and non_latin > (latin + non_latin) * 0.2:
        return next((name for name, script in _SCRIPTS if script.search(text)), "another language")

    words = re.findall(r"[^\W\d_]+", text.lower())
    if not words:
        return ""
    en = sum(1 for w in words if w in _ENGLISH_WORDS)

    name, hits = max(((name, sum(1 for w in words if w in vocabulary)) for name, vocabulary in _OTHER_WORDS.items()),
                     key=lambda pair: pair[1])

    # Czech text has an accented letter every few words. A long English ad with a
    # few of them (a company or city name: "ČSOB", "Plzeň") is still English, so
    # the letters must also be a real share of the text, not just three of them.
    # At least one must be a letter only Czech and Slovak have: "é" and "á" are French and Spanish too.
    accents = sum(1 for ch in text if ch in _CZECH_CHARS)
    own = sum(1 for ch in text if ch in _CZECH_ONLY)
    cz = sum(1 for w in words if w in _CZECH_WORDS)
    if (own >= 1 and accents >= 3 and accents >= len(text) * 0.01) or (cz > en and cz >= hits):
        slovak = sum(1 for ch in text if ch in _SLOVAK_CHARS) + sum(1 for w in words if w in _OTHER_WORDS["Slovak"])
        return "Slovak" if slovak > cz and slovak >= 3 else "Czech"

    # Another European language: its everyday words clearly outnumber the English ones.
    if hits >= 4 and hits > en * 2 and hits >= len(words) * 0.08:
        return name
    return ""
