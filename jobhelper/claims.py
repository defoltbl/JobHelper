"""Whether a text written in the person's voice claims more than their CV shows, and whether it talks
about them instead of as them. One check for the cover letter, the form answers and the interview
preparation (and the adapted CV's "never claim" terms), so the rules cannot drift apart.

A technology the CV cannot back up may be named as the employer's platform, as a wish ("I would like to
work with …") or, in an interview, as an honest bridge ("I have not used X; the closest I have done is …"),
never as something already done.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

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


_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#]*")
# A position's dates: a range ("2023 – 2024", "Sep 2025 – Apr 2026", "2024 – present") or a year in brackets ("(2021)")
_DATES = re.compile(r"\b(?:19|20)\d{2}\s*[–—-]\s*(?:[A-Za-z]{3,9}\.?\s+)?(?:(?:19|20)\d{2}|present|now|today|current)\b"
                    r"|\([^()]*\b(?:19|20)\d{2}\b[^()]*\)", re.IGNORECASE)
_BULLET = re.compile(r"^[-–—•·*▪◦]")
# Between a job's title and its employer: "Developer – Contoso", "Developer, Contoso", "Developer | Contoso"
_SEPARATOR = re.compile(r"\s[–—|-]\s|,\s")
# Study, not work: a section of it, a place of it, or a degree as the first word ("BSc, Computer Science – …").
# "Research Intern (Pre-Diploma Practice) – Diskret" is a job: a degree word later in the line does not count.
_STUDY_SECTION = re.compile(r"(education|studies|certificat|course|training|language|award|publication|conference)", re.IGNORECASE)
_STUDY_PLACE = re.compile(r"\b(university|college|school|institute|academy|faculty)\b", re.IGNORECASE)
# A job title is short and opens with no action verb ("Head of Sales", "Full-stack Developer", "Data scientist"),
# unlike work done ("Led migration, …", "Built dashboards – …", "Designed APIs for …"). These "-ed" words open real titles.
_TITLE_WORD = re.compile(r"[A-Za-z][\w+#'-]*")
_TITLE_ED = frozenset("applied embedded licensed certified registered qualified chartered accredited advanced".split())
_ACTION = frozenset("led built wrote ran made cut won drove grew taught sold set took gave kept".split())
_DEGREE = re.compile(r"^(bsc|msc|ba|ma|phd|mba|bachelor\w*|master\w*|degree|diploma)\b", re.IGNORECASE)
# Words of a job title, not of an employer: a position is named by its employer, never by "Junior" or "Developer".
_ROLE_WORDS = frozenset("""junior senior lead principal staff chief head intern internship trainee student assistant associate
    developer engineer programmer analyst manager consultant specialist administrator architect designer tester officer
    coordinator technician software web data full stack backend frontend front back end and the for with present
    engineering research practice production development
    jan feb mar apr may jun jul aug sep sept oct nov dec january february march april june july august september october
    november december""".split())


def singular(word: str) -> str:
    """Only the plural goes ("APIs" and "API" are one thing); cv_tailor's longer list of endings is for the posting's
    phrases, where "reconciling" and "reconciled" must meet."""
    w = word.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def _heading(line: str) -> bool:
    letters = "".join(ch for ch in line if ch.isalpha())
    return 3 <= len(letters) and len(line) <= 60 and letters.isupper() and ":" not in line


def _named_work(line: str) -> set[str]:
    """The stems of the words in one line of a CV's description of a job that name a thing, not an action: "REST",
    "API", "Django" (capitals inside the word, or a capital after a word or a comma). "Built" at the start of a line
    or after a bullet, "internal" and "pytest" are left out."""
    out = set()
    for m in _WORD.finditer(line):
        word, before = m.group(0), line[:m.start()].rstrip()
        mid_clause = word[0].isupper() and bool(before) and (before[-1].isalnum() or before[-1] == ",")
        if len(word) >= 2 and (sum(ch.isupper() for ch in word) >= 2 or mid_clause):
            out.add(singular(word))
    return out


def _names(text: str, name: str) -> bool:
    """Whether `text` names an employer's word as it is written (case counts: "engineering" is no "Engineering")."""
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text))


@dataclass(frozen=True)
class _Position:
    names: tuple[str, ...]          # the employer's own words in the position's heading ("Fabrikam", "Labs")
    words: frozenset[str]           # the stems of every word of the position
    named_work: frozenset[str]      # the things its description names (see _named_work)


class EmployerCheck:
    """The positions of a CV and whether a text gives one employer work that the CV names only under another ("at
    Fabrikam Labs I built REST APIs" when the CV built the REST API at Northwind Parcel).

    The layout it reads: one line per position with its dates ("Junior Developer – Northwind Parcel (2024 – present)"),
    its work on the same line after the dates or on the lines below, up to the next position or heading. A CV that
    names its employers some other way (on a line of their own, in the profile too) gives no names, and nothing is
    judged: the check stays quiet rather than guess."""

    def __init__(self, cv_text: str) -> None:
        raw = self._read(cv_text or "")
        heads = " ".join(head for head, _body in raw)
        self._positions = self._merged([self._position(head, body, cv_text or "", heads) for head, body in raw])

    @staticmethod
    def _head_end(line: str) -> int:
        """Where the heading of a position ends (after its dates), or 0 when the line heads no position. A heading is
        a title and an employer with a separator between them, then the dates ("Applied Scientist – Contoso Research
        (2022 – 2024)"). A bullet, a line of work with a year in it ("Built a dashboard (Tableau, 2023)") and a degree
        ("BSc Computer Science – Charles University") head none."""
        dates = _DATES.search(line[:160])
        before = line[:dates.start()] if dates else ""
        if not dates or _BULLET.match(line) or not _SEPARATOR.search(before) or _STUDY_PLACE.search(before) or _DEGREE.match(line):
            return 0
        return dates.end() if EmployerCheck._title(_SEPARATOR.split(before, maxsplit=1)[0]) else 0

    @staticmethod
    def _title(text: str) -> bool:
        """Whether the text before the separator reads like a job title, not like a piece of work (see _TITLE_ED)."""
        words = _TITLE_WORD.findall(re.sub(r"\([^()]*\)", " ", text))      # "(Pre-Diploma Practice)" says what kind of job
        if not words or len(words) > 6:
            return False
        first = words[0].lower()
        return first not in _ACTION and not (first.endswith("ed") and first not in _TITLE_ED)

    @classmethod
    def _read(cls, cv_text: str) -> list[tuple[str, list[str]]]:
        raw: list[tuple[str, list[str]]] = []
        studies = False                        # under EDUCATION, CERTIFICATES … a dated line is no job
        for line in cv_text.splitlines():
            line = line.strip()
            end = 0 if studies else cls._head_end(line)
            if end:
                raw.append((line[:end], [line[end:]]))
            elif _heading(line):
                studies = bool(_STUDY_SECTION.search(re.sub(r"\s+", "", line)))     # also "E D U C A T I O N"
                raw.append(("", []))           # a new section ends the position before it
            elif line and raw and raw[-1][0]:
                raw[-1][1].append(line)
        return [(head, body) for head, body in raw if head]

    @staticmethod
    def _position(head: str, body: list[str], cv_text: str, heads: str) -> _Position:
        # an employer's name is a word the CV uses only in the headings of positions: "Fabrikam", never "Machine
        # Learning" or "Engineering", which the CV also uses for skills, titles or other places
        def count(text: str, word: str) -> int:
            return sum(1 for w in _WORD.findall(text) if singular(w) == singular(word))
        employer = _SEPARATOR.split(_DATES.sub(" ", head), maxsplit=1)[-1]     # after the title: "Freelance" names no one
        candidates = [w for w in _WORD.findall(employer) if len(w) >= 3 and w[0].isupper() and w.lower() not in _ROLE_WORDS]
        names = tuple(dict.fromkeys(w for w in candidates if count(cv_text, w) == count(heads, w)))
        return _Position(names, frozenset(singular(w) for w in _WORD.findall(" ".join([head, *body]))),
                         frozenset().union(*map(_named_work, body)))

    @staticmethod
    def _merged(positions: list[_Position]) -> list[_Position]:
        """Two roles at one employer (headings sharing two name words, or one's names inside the other's) are one."""
        out: list[_Position] = []
        for p in positions:
            same = next((q for q in out if p.names and q.names and (len(set(p.names) & set(q.names)) >= 2
                                                                    or set(p.names) <= set(q.names) or set(q.names) <= set(p.names))), None)
            if same is None:
                out.append(p)
            else:
                out[out.index(same)] = _Position(tuple(dict.fromkeys(same.names + p.names)), same.words | p.words,
                                                 same.named_work | p.named_work)
        # a word in the headings of two employers ("Brno", "Labs") names neither of them
        shared = {n for p in out for q in out if q is not p for n in p.names if n in q.names}
        return [_Position(tuple(n for n in p.names if n not in shared), p.words, p.named_work) for p in out]

    def misplaced(self, text: str, company: str = "") -> list[str]:
        """For each sentence that names one employer and the work the CV names under another one, a note such as
        "'REST', 'APIs' at Fabrikam Labs" (empty: nothing is out of place). Words of `company` (the employer the text
        is written to) name no former employer: "join Contoso Labs" is no "Fabrikam Labs"."""
        target = {singular(w) for w in _WORD.findall(company or "")}
        out = []
        for sentence in sentences(text):
            named = [p for p in self._positions
                     if any(_names(sentence, n) for n in p.names if singular(n) not in target)]
            if len(named) != 1:
                continue                        # no employer, or several: the sentence ties nothing to one of them
            here = named[0]
            others = set().union(*(p.named_work for p in self._positions if p is not here))
            words = [w for w in dict.fromkeys(_WORD.findall(sentence))
                     if singular(w) in others and singular(w) not in here.words and singular(w) in _named_work(sentence)]
            if words:
                out.append(", ".join(f"'{w}'" for w in words) + " at " + " ".join(here.names))
        return out


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
