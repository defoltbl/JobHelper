"""Whether a text written in the person's voice claims more than their CV shows, and whether it talks
about them instead of as them. One check for the cover letter, the form answers and the interview
preparation (and the adapted CV's "never claim" terms), so the rules cannot drift apart.

A technology the CV cannot back up may be named as the employer's platform, as a wish ("I would like to
work with …") or, in an interview, as an honest bridge ("I have not used X; the closest I have done is …"),
never as something already done.
"""
from __future__ import annotations

import re

# A sentence that admits a gap (a cover letter sells strengths only).
GAP = re.compile(
    r"\b(not yet|have not|haven't|do not have|don't have|lack(s|ing)?|gaps?|honest(ly)?|limited|"
    r"unfamiliar|despite|although|no experience|little experience|never (used|worked))\b", re.IGNORECASE)
# A forward-looking wish: naming a technology this way is not a claim.
WISH = re.compile(r"\b(would like|would love|keen|look(ing)? forward|want to|eager|hope to|"
                  r"excited to|wish to|aim to|motivated to)\b", re.IGNORECASE)
# Wording that claims hands-on experience.
CLAIM = re.compile(
    r"\b(I|I've|we)\s+(have\s+|also\s+|regularly\s+|currently\s+)*(work(ed)?|use[ds]?|built|build|"
    r"deploy(ed)?|ran|run|administer(ed)?|manage[ds]?|configure[ds]?|operate[ds]?|maintain(ed)?|"
    r"wrote|written|set up|automate[ds]?|implemented?|develop(ed)?)\b|"
    r"\b(experience(d)? (with|in)|hands-on|proficient|skilled|familiar with|expertise|background in|"
    r"knowledge of|my work with)\b", re.IGNORECASE)
# An honest bridge names the missing thing on purpose (in an interview that is the right answer).
HONEST = re.compile(r"\b(have not|haven't|do not have|don't have|not (?:yet )?(?:used|worked)|"
                    r"no (?:(?:professional|production|hands-on|commercial|prior|direct) )?experience|"
                    r"closest|would (?:get|learn|pick)|new to me|only (?:read|studied))\b", re.IGNORECASE)
FIRST_PERSON = re.compile(r"\b(?:I|my|me|I'm|I've)\b")


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def mentions(text: str, term: str) -> bool:
    """Whether `text` names `term` as a whole word (case blind)."""
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text or "", re.IGNORECASE))


def names_candidate(text: str, first_name: str) -> bool:
    """Whether a text written as the person uses their own first name (it talks about them, not as them)."""
    return bool(first_name) and bool(re.search(rf"\b{re.escape(first_name)}\b", text or ""))


class ClaimCheck:
    """The technologies the CV cannot back up (`cover_letter.unverified_terms`), and whether a text claims one."""

    def __init__(self, unverified: list[str]) -> None:
        self.terms = list(unverified or [])

    def claimed_in(self, sentence: str, honest_ok: bool = False) -> str:
        """The first technology this sentence presents as experience ('' if none). A wish is never a claim;
        with `honest_ok` an honest bridge is not one either."""
        if not CLAIM.search(sentence) or WISH.search(sentence) or (honest_ok and HONEST.search(sentence)):
            return ""
        return next((term for term in self.terms if mentions(sentence, term)), "")

    def unbacked(self, text: str, honest_ok: bool = False) -> str:
        """The first technology a text presents as experience though the CV lacks it ('' if none)."""
        return next((term for term in (self.claimed_in(s, honest_ok) for s in sentences(text)) if term), "")


# A figure, with its thousands groups ("60 000", "60,000", "60.000") read as one number.
FIGURE = re.compile(r"(?<![\d.,])\d{1,3}(?:[ \u00a0\u202f,.]\d{3})+(?!\d)(?:[.,]\d{1,2}(?!\d))?|\d+(?:[.,]\d+)*")
# A figure used as an amount of something: "5 years", "40%", "1,200 users", "3x" – a claim, not a reference ("situation 3").
_UNIT = (r"\s*\+?\s*(?:years?|yrs|months?|weeks?|days?|hours?|%|per ?cent|users|customers|clients|people|persons?|developers|"
         r"engineers|employees|members|teams?|projects|countries|languages|times|million|thousand|k\b|x\b)")
_NUMBER_WORDS = {w: str(n) for n, w in enumerate(("two three four five six seven eight nine ten eleven twelve").split(), 2)}  # not "one": "one team"
_WORDED_AMOUNT = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b(?=" + _UNIT + r")", re.IGNORECASE)


def _figure(text: str) -> str:
    """One way to write a figure: thousands groups joined, a decimal comma as a point, no leading zeros ("01" is "1")."""
    t = re.sub(r"[ \u00a0\u202f]", "", text)
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", t):
        t = re.sub(r"[,.]", "", t)
    t = re.sub(r",(\d{1,2})$", r".\1", t)
    return ".".join(part.lstrip("0") or "0" for part in re.split(r"[.,]", t))


_SCALED = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s?(k|K|M|million)\b")


def _digits(text: str) -> str:
    """Number words used as an amount ("five years") and scaled figures ("60k", "1.5M") written as plain digits, so they
    are checked like "5 years" and "60000"."""
    from decimal import Decimal

    def scaled(m: re.Match) -> str:              # the unit stays: "40k" is still an amount, now 40000 k
        value = Decimal(m.group(1).replace(",", ".")) * (1000 if m.group(2) in ("k", "K") else 1_000_000)
        return f"{value.normalize():f} {m.group(2)}"
    return _SCALED.sub(scaled, _WORDED_AMOUNT.sub(lambda m: _NUMBER_WORDS[m.group(1).lower()], text or ""))


def _amount(plain: str, figure: str) -> bool:
    return bool(re.search(r"(?<![\d.,])" + re.escape(figure) + _UNIT, plain, re.IGNORECASE))


def as_quantity(text: str, figure: str) -> bool:
    """Whether a text uses this figure as an amount ("5 years", "40%"), not as a name or reference ("situation 3")."""
    return _amount(_digits(text), figure)


# A date in a source ("05/2019", "2026-10-01", "1.10.2026"): its numbers back a date, never an amount like "5 years".
_DATE = re.compile(r"(?<![\d.,/])(?:(?:19|20)\d\d[-/.](?:0?[1-9]|1[0-2])(?:[-/.]\d{1,2})?|\d{1,2}[-/.](?:0?[1-9]|1[0-2])[-/.]\d{2,4}"
                   r"|(?:0?[1-9]|1[0-2])[-/.](?:19|20)\d\d)(?![\d/])")


def _known(texts) -> tuple[set[str], set[str]]:
    """(whole figures, all figures and their parts). The parts of a date or a version back a date or a reference only."""
    plain = [_digits(text) for text in texts]
    dates = {part.lstrip("0") or "0" for text in plain for d in _DATE.findall(text) for part in re.split(r"[-/.]", d)}
    whole = {_figure(f) for text in plain for f in FIGURE.findall(_DATE.sub(" ", text))}
    return whole, whole | dates | {part for f in whole for part in f.split(".")}


def unbacked_figures(text: str, sources=(), references=(), brackets_ok: bool = True) -> list[str]:
    """The figures a text states that its sources do not give: a model may invent them (years, users, per cent …).
    `sources` are the person's own (CV, notes, facts, what they typed): they back any figure. `references` (the posting,
    the question) may be repeated as a reference – "your team of 50" – but never back an amount the text claims, such
    as "my 5 years". A part in [square brackets] is the person's to fill in and is skipped where `brackets_ok`.
    A date or a version is known when each of its parts is. Limit: figures are compared, not claims, so a "3" in the
    person's sources backs every "3"."""
    (own, own_parts), (_, quoted_parts) = _known(sources), _known(references)
    body = _digits(re.sub(r"\[[^\]]*\]", "", text or "") if brackets_ok else text or "")

    def backed(figure: str) -> bool:
        whole, parts = _figure(figure), _figure(figure).split(".")
        if _amount(body, figure):                         # an amount you claim: only a whole figure of your own backs it
            return whole in own
        return whole in own_parts or whole in quoted_parts or (len(parts) > 2 and all(p in own_parts | quoted_parts for p in parts))
    return [f for f in dict.fromkeys(FIGURE.findall(body)) if not backed(f)]


def rejected(problems: list[str], what: str = "version") -> str:
    """The note sent back with the next request when a draft broke a rule."""
    return f"\nYour previous {what} was rejected. Fix these problems:\n" + "\n".join(f"- {p}" for p in problems) + "\n"
