"""What to ask for, and what a posting says it pays.

The figure to ask for is yours: Options, "Salary you ask for", in the currency you choose.
Only when you gave none, and only for a search in Czechia, the app offers its own estimate:
a table of gross monthly pay in CZK for JUNIOR software roles in Prague (2025-2026 averages,
approximate), with multipliers for higher levels. It knows nothing about other professions
or other countries, and says nothing there. Deterministic (no API cost).
"""
from __future__ import annotations

import re

# Junior monthly gross (CZK), matched by the FIRST keyword found in the title.
# Order matters — more specific / higher-paid roles first.
_JUNIOR_MONTHLY: list[tuple[str, int]] = [
    ("genai", 65000), ("machine learning", 62000), ("ml engineer", 62000),
    ("ai engineer", 62000), ("data scien", 60000), ("ai", 60000),
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

# As whole words: "ios" is not in "kiosk", "ai" not in "Thai", "qa" not in "Qatar", "sre" not in "pressroom".
# ("java" still finds "javascript", and "data scien" finds "scientist" and "science": those are meant.)
_OPEN_END = ("data scien", "java")
_WORD = {kw: re.compile(r"(?<![a-z0-9])" + re.escape(kw) + ("" if kw in _OPEN_END or not kw[-1].isalnum() else r"(?![a-z0-9])"))
         for kw, _pay in _JUNIOR_MONTHLY}

_LEVEL_MULT = {"junior": 1.0, "entry": 1.0, "graduate": 1.0, "mid": 1.3,
               "medior": 1.3, "senior": 1.7, "lead": 2.0}


def estimate(title: str, seniority: str = "junior") -> tuple[int, int]:
    """(monthly, annual) gross CZK for a software role in Prague, rounded to the nearest 1000.
    (0, 0) for a title the table does not know: no figure is better than one from another profession."""
    t = (title or "").lower()
    base = next((v for kw, v in _JUNIOR_MONTHLY if _WORD[kw].search(t)), 0)
    if not base:
        return 0, 0
    mult = _LEVEL_MULT.get((seniority or "junior").strip().lower(), 1.0)
    monthly = int(round(base * mult / 1000.0)) * 1000
    return monthly, monthly * 12


# ── what a posting itself says about pay ────────────────────────────────────
# How many crowns one unit is worth, roughly: enough to compare a posting's pay with what you ask.
CURRENCIES = {"CZK": 1.0, "EUR": 25.0, "USD": 23.0, "GBP": 29.0, "CHF": 26.0, "PLN": 5.8, "HUF": 0.063, "RON": 5.0,
              "SEK": 2.2, "NOK": 2.1, "DKK": 3.35, "CAD": 17.0, "AUD": 15.0}

_NUM = r"(\d{1,3}(?:[ \u00a0.,]\d{3})+|\d{4,7})"
_CUR = r"(Kč|CZK|EUR|€|USD|\$|GBP|£|CHF|PLN|zł|HUF|Ft|RON|SEK|NOK|DKK|CAD|AUD)"
_STATED = re.compile(
    rf"(?:{_CUR}\s*{_NUM}(?:\s*(?:-|–|to|až)\s*(?:{_CUR}\s*)?{_NUM})?)"       # CZK 65,000 - 80,000
    rf"|(?:{_NUM}(?:\s*(?:-|–|to|až)\s*{_NUM})?\s*{_CUR})"                     # 65 000 - 80 000 Kč
    rf"|(?:(?:from|od)\s+{_NUM})",                                              # from 60 000 (job-board field)
    re.IGNORECASE)
_TO_CZK = {**{code.lower(): rate for code, rate in CURRENCIES.items()},
           "kč": 1.0, "€": CURRENCIES["EUR"], "$": CURRENCIES["USD"], "£": CURRENCIES["GBP"], "zł": CURRENCIES["PLN"], "ft": CURRENCIES["HUF"]}
_YEARLY = re.compile(r"per\s+(?:year|annum)|/\s*(?:year|yr|rok)|ročně|annual|yearly|p\.?a\.?\b", re.IGNORECASE)


def _number(text: str) -> int:
    return int(re.sub(r"[^0-9]", "", text))


def tidy(amount: float, currency: str = "CZK") -> int:
    """Rounded as people say it: to the thousand for large figures (crowns), to the hundred for small ones (euros)."""
    step = 1000 if amount >= 20_000 else 100
    return int(round(amount / step) * step)


def money(amount: int, currency: str = "CZK") -> str:
    """"60 000 CZK"."""
    return f"{int(amount):,}".replace(",", " ") + " " + currency


def brief(amount: int) -> str:
    """"65k" for a large figure, "2 600" for a small one."""
    return f"{round(amount / 1000)}k" if amount >= 10_000 else f"{int(amount):,}".replace(",", " ")


def span(low: int, high: int, currency: str = "CZK") -> str:
    """"55–65k CZK", "2 600–3 200 EUR", or one figure when both ends are the same."""
    if low == high:
        return f"{brief(low)} {currency}"
    if low >= 10_000:
        return f"{round(low / 1000)}–{round(high / 1000)}k {currency}"
    return f"{brief(low)}–{brief(high)} {currency}"


def currency_of(options: dict | None = None) -> str:
    from . import config
    code = str((config.ui_settings() if options is None else options).get("salary_currency") or "CZK").upper()
    return code if code in CURRENCIES else "CZK"


def estimate_available(options: dict) -> bool:
    """Whether the app's own estimate counts for this search: it exists only for Czechia, so only while the search is
    there (or no city or country is set yet). The salary of a job, the line in About you and its estimates ask here."""
    from . import filters
    where, country = str(options.get("where") or ""), str(options.get("country") or "")
    return not (where.strip() or country.strip()) or filters.Placement(where, country).home == "czechia"


def asked(job: dict, options: dict | None = None) -> tuple[int, str, bool]:
    """What to ask for in this job: (gross per month, currency, True when it is your own figure).

    Your figure from Options when you gave one: the one for this kind of role when its words are
    in the title ("support" for "IT Support Specialist"), else the general one. Otherwise the app's estimate for the job, which
    exists only for software roles and only while the search is in Czechia (or no city is set
    yet). (0, currency, False) when there is nothing to say."""
    from . import config
    opts = config.ui_settings() if options is None else options
    currency = currency_of(opts)
    try:
        own = int(opts.get("salary_target") or 0)
    except (TypeError, ValueError):
        own = 0
    for entry in opts.get("salary_by_role") or []:              # a figure of your own for this kind of role comes first
        try:
            role, amount = str(entry.get("role") or ""), int(entry.get("amount") or 0)
        except (AttributeError, TypeError, ValueError):
            continue
        from . import prefilter
        phrase = prefilter.role_phrase(role)
        if amount > 0 and phrase is not None and phrase.search(str(job.get("title") or "")):
            return amount, currency, True
    if own > 0:
        return own, currency, True
    if not estimate_available(opts):
        return 0, currency, False
    try:
        estimate_czk = int(job.get("desired_monthly_czk") or 0)
    except (TypeError, ValueError):
        estimate_czk = 0
    return (estimate_czk, "CZK", False) if estimate_czk > 0 else (0, currency, False)


def stated(job: dict, currency: str = "CZK") -> dict | None:
    """The pay a posting states, gross per month in `currency`: {low, high, text, currency} or None.
    Yearly figures (said to be yearly, or too large to be monthly) are divided by
    twelve; other currencies are converted at a rough fixed rate."""
    out_rate = CURRENCIES.get(currency, 1.0)
    sources = [str(job.get("salary") or ""), str(job.get("title") or ""), str(job.get("description") or "")]
    for source in sources:
        for m in _STATED.finditer(source):
            groups = [g for g in m.groups() if g]
            written = next((g for g in groups if g.lower() in _TO_CZK), "CZK")
            numbers = [_number(g) for g in groups if re.fullmatch(_NUM, g)]
            if not numbers:
                continue
            low, high = min(numbers), max(numbers)
            rate = _TO_CZK[written.lower()]
            low, high = low * rate, high * rate
            around = source[max(0, m.start() - 40): m.end() + 40]
            if _YEARLY.search(around) or low >= 300_000:
                low, high = low / 12, high / 12
            if not 15_000 <= low <= 400_000:
                continue                            # a phone number, a year, a company size
            return {"low": tidy(low / out_rate, currency), "high": tidy(high / out_rate, currency), "currency": currency,
                    "text": re.sub(r"\s+", " ", m.group(0)).strip()}
    return None
