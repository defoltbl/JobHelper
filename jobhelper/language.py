"""Cheap, deterministic language heuristic — no LLM, no network.

Used to keep only English-language job ads, since the user does not speak Czech.
An ad written in English is a strong signal the role welcomes non-Czech
speakers; an ad written in Czech usually expects Czech.
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


def is_english(text: str) -> bool:
    """Return True if the text looks like English rather than Czech.

    Empty/very short text defaults to True (we can't tell, so don't drop it).
    """
    text = (text or "").strip()
    if len(text) < 15:
        return True

    # Reject text written in a non-Latin script (Japanese, Chinese, Korean,
    # Russian, etc.) — stray English tech terms ("3D", "AI") don't make it English.
    non_latin = len(_NON_LATIN.findall(text))
    latin = len(re.findall(r"[a-zA-Z]", text))
    if non_latin >= 8 and non_latin > (latin + non_latin) * 0.2:
        return False

    czech_char_hits = sum(1 for ch in text if ch in _CZECH_CHARS)
    if czech_char_hits >= 3:
        return False

    words = _words(text)
    if not words:
        return True
    cz = sum(1 for w in words if w in _CZECH_WORDS)
    en = sum(1 for w in words if w in _ENGLISH_WORDS)
    # Require English signal to at least match Czech signal.
    return en >= cz
