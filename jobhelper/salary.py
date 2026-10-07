"""Rough Prague market-rate salary estimates by role, for stating a desired
compensation on applications. Deterministic (no API cost). Figures are gross
CZK per month for a JUNIOR level (2025-2026 Prague averages, approximate), with
multipliers for higher levels. These are ballpark guidance, not exact market data.
"""
from __future__ import annotations

# Junior monthly gross (CZK), matched by the FIRST keyword found in the title.
# Order matters — more specific / higher-paid roles first.
_JUNIOR_MONTHLY: list[tuple[str, int]] = [
    ("genai", 65000), ("machine learning", 62000), ("ml engineer", 62000),
    ("ai engineer", 62000), ("data scien", 60000), (" ai", 60000), ("ai ", 60000),
    ("golang", 62000), ("scala", 62000), ("c++", 60000), ("rust", 62000),
    ("devops", 60000), ("sre", 60000), ("site reliability", 60000),
    ("data engineer", 60000), ("cloud", 58000), ("infrastructure", 58000),
    ("backend", 58000), ("back end", 58000), ("back-end", 58000),
    ("python", 58000), ("java", 55000), (".net", 55000), ("c#", 55000),
    ("full stack", 58000), ("fullstack", 58000), ("full-stack", 58000),
    ("android", 55000), ("ios", 55000), ("mobile", 55000),
    ("frontend", 54000), ("front end", 54000), ("front-end", 54000), ("react", 54000),
    ("data analyst", 52000), ("analytics", 52000), ("analyst", 50000),
    ("qa", 48000), ("tester", 48000), ("test engineer", 48000), ("quality", 48000),
    ("service desk", 40000), ("help desk", 40000), ("helpdesk", 40000),
    ("it support", 42000), ("support", 44000), ("administrator", 46000),
    ("developer", 55000), ("engineer", 55000), ("software", 55000), ("programmer", 55000),
]
_DEFAULT_MONTHLY = 50000

_LEVEL_MULT = {"junior": 1.0, "entry": 1.0, "graduate": 1.0, "mid": 1.3,
               "medior": 1.3, "senior": 1.7, "lead": 2.0}


def estimate(title: str, seniority: str = "junior") -> tuple[int, int]:
    """Return (monthly_czk_gross, annual_czk_gross), rounded to the nearest 1000."""
    t = (title or "").lower()
    base = next((v for kw, v in _JUNIOR_MONTHLY if kw in t), _DEFAULT_MONTHLY)
    mult = _LEVEL_MULT.get((seniority or "junior").strip().lower(), 1.0)
    monthly = int(round(base * mult / 1000.0)) * 1000
    return monthly, monthly * 12


# ── what a posting itself says about pay ────────────────────────────────────
import re  # noqa: E402

_NUM = r"(\d{1,3}(?:[ \u00a0.,]\d{3})+|\d{4,7})"
_CUR = r"(Kč|CZK|EUR|€|USD|\$)"
_STATED = re.compile(
    rf"(?:{_CUR}\s*{_NUM}(?:\s*(?:-|–|to|až)\s*(?:{_CUR}\s*)?{_NUM})?)"       # CZK 65,000 - 80,000
    rf"|(?:{_NUM}(?:\s*(?:-|–|to|až)\s*{_NUM})?\s*{_CUR})"                     # 65 000 - 80 000 Kč
    rf"|(?:(?:from|od)\s+{_NUM})",                                              # from 60 000 (job-board field)
    re.IGNORECASE)
_TO_CZK = {"kč": 1.0, "czk": 1.0, "eur": 25.0, "€": 25.0, "usd": 23.0, "$": 23.0}
_YEARLY = re.compile(r"per\s+(?:year|annum)|/\s*(?:year|yr|rok)|ročně|annual|yearly|p\.?a\.?\b", re.IGNORECASE)


def _number(text: str) -> int:
    return int(re.sub(r"[^0-9]", "", text))


def stated(job: dict) -> dict | None:
    """The pay a posting states, as gross CZK per month: {low, high, text} or None.
    Yearly figures (said to be yearly, or too large to be monthly) are divided by
    twelve; EUR and USD are converted at a rough fixed rate."""
    sources = [str(job.get("salary") or ""), str(job.get("title") or ""), str(job.get("description") or "")]
    for source in sources:
        for m in _STATED.finditer(source):
            groups = [g for g in m.groups() if g]
            currency = next((g for g in groups if g.lower() in _TO_CZK), "CZK")
            numbers = [_number(g) for g in groups if re.fullmatch(_NUM, g)]
            if not numbers:
                continue
            low, high = min(numbers), max(numbers)
            rate = _TO_CZK[currency.lower()]
            low, high = low * rate, high * rate
            around = source[max(0, m.start() - 40): m.end() + 40]
            if _YEARLY.search(around) or low >= 300_000:
                low, high = low / 12, high / 12
            if not 15_000 <= low <= 400_000:
                continue                            # a phone number, a year, a company size
            return {"low": int(round(low / 1000) * 1000), "high": int(round(high / 1000) * 1000),
                    "text": re.sub(r"\s+", " ", m.group(0)).strip()}
    return None
