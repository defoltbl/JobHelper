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


def rejected(problems: list[str], what: str = "version") -> str:
    """The note sent back with the next request when a draft broke a rule."""
    return f"\nYour previous {what} was rejected. Fix these problems:\n" + "\n".join(f"- {p}" for p in problems) + "\n"
