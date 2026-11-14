"""Whether a text written in the person's voice claims more than their CV shows, and whether it talks
about them instead of as them. One check for the cover letter, the form answers and the interview
preparation (and the adapted CV's "never claim" terms), so the rules cannot drift apart.

A technology the CV cannot back up may be named as the employer's platform, as a wish ("I would like to
work with …") or, in an interview, as an honest bridge ("I have not used X; the closest I have done is …"),
never as something already done.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

from . import keywords

# A sentence that admits a gap (a cover letter sells strengths only).
GAP = re.compile(
    r"\b(not yet|have not|haven't|do not have|don't have|lack(s|ing)?|gaps?|honest(ly)?|limited|"
    r"unfamiliar|despite|although|no experience|little experience|never (used|worked))\b", re.IGNORECASE)
# A forward-looking wish: naming a technology this way is not a claim.
WISH = re.compile(r"\b(would like|would love|keen|look(ing)? forward|want to|eager|hope to|"
                  r"excited to|wish to|aim to|motivated to)\b", re.IGNORECASE)
# A clause that describes a team as it works now ("a team where we use Kafka"), not the candidate's own work: present
# tense only, so "a team where we built Kafka pipelines" is still a claim (#82). It ends at the next "I" or "but" (a
# claim may start there) as well as at a stop.
_TEAM_CLAUSE = re.compile(r"\bwhere\s+we\s+(?:use|run|work|build|deploy|manage|have|are|love|value)\b"
                          r"(?:(?!\b(?:I|but)\b)[^.;,])*", re.IGNORECASE)
# Where a wish ends: the next "I" or "we" (a new claim may start there), "but", a semicolon, or a clause about what was
# done ("eager to learn Spark, having built Kafka pipelines": #82).
_WISH_END = r".*?(?=\b(?:I|I've|I'm|[Ww]e|but)\b|;|,\s*(?:having|after|since|while)\b|$)"
# Wording that claims hands-on experience.
# "lead with" / "lead by" is a manner, not leading a project (#82). A team clause ("a team where we use Kafka") is taken
# out before this is asked (_TEAM_CLAUSE). "I wrote" is read by _work, which knows "I wrote to you" is the letter (#113).
CLAIM = re.compile(
    r"\b(I|I've|we)\s+(have\s+|also\s+|regularly\s+|currently\s+)*(work(ed)?|use[ds]?|built|build|"
    r"deploy(ed)?|ran|run|administer(ed)?|manage[ds]?|configure[ds]?|operate[ds]?|maintain(ed)?|"
    r"written|set up|automate[ds]?|implemented?|develop(ed)?|lead(?!\s+(?:with|by)\b)|led|design(ed)?|create[ds]?|"
    r"deliver(ed)?|migrate[ds]?|own(ed)?)\b|"
    r"\bhaving\s+(?:built|used|worked|deployed|run|written|developed|designed|created|maintained|led|delivered|migrated)\b|"
    r"\b(experience(d)? (with|in)|hands-on|proficient|skilled|familiar with|expertise|background in|"
    r"knowledge of|my work with)\b", re.IGNORECASE)
# Work done, said with any verb in the past tense ("I scheduled", "we reconciled", "I gave CPR"): CLAIM's verbs are a fixed
# list, and a letter can claim a tool with any other (#78). Verbs of seeing, wanting, learning about or joining are no
# claim of the work itself (_NOT_DONE); a few say work or learning by what they act on (_BY_OBJECT, #113). "used" is
# too short for the "-ed" pattern, so it is named (#113).
_PAST = r"[a-z]{3,}ed|used|gave|made|wrote|drew|drove|held|kept|taught|sold|brought|fed|ran|led|built|done|troubleshot|cut|put"
_PAST_WORD = re.compile(_PAST)
_DONE = re.compile(r"\b(?:I|I've|we)\s+(?:have\s+|also\s+|then\s+|once\s+|\w+ly\s+)*(" + _PAST + r")\b"
                   r"|\b(?:I'm|I am|I've been|I have been|we're|we've been|we have been)\s+(?:\w+ly\s+)?([a-z]{2,}ing)\b",
                   re.IGNORECASE)
_NOT_DONE = frozenset({"noticed", "noted", "learned", "wanted", "hoped", "liked", "loved", "enjoyed",
                       "decided", "discovered", "realised", "realized", "followed", "watched", "admired",
                       "appreciated", "considered", "wondered", "mentioned", "attended", "researched", "studied", "started",
                       "joined", "talked", "asked", "believed", "expected", "missed", "lacked", "visited", "needed",
                       "interested", "excited", "impressed", "pleased", "delighted", "inspired", "intrigued", "reached",
                       "discussed", "contacted", "confirmed", "graduated", "explored",
                       "subscribed", "registered", "signed", "presented",
                       # the letter's own frame: "I attached my CV", "Enclosed is …"
                       "attached", "received", "stumbled", "enclosed", "forwarded",
                       "submitting", "attaching", "enclosing", "responding", "addressing", "contacting", "sending",
                       # what someone is doing now that is no work done: "I'm looking forward to", "I'm learning Kafka"
                       "looking", "hoping", "learning", "planning", "applying", "writing", "reaching", "studying", "going",
                       "trying", "wondering", "thinking", "considering", "following", "reading",
                       # a sentence that opens with how someone feels or where something is: "Based in Prague, …" (#113)
                       "fascinated", "based", "located", "thrilled", "motivated", "honoured", "honored", "humbled", "amazed",
                       "convinced", "detailed", "listed", "outlined", "described", "required", "requested", "preferred",
                       # words that only look like a past tense
                       "indeed", "speed", "proceed", "succeed", "exceed", "hundred"})
# Verbs that are work or learning by what they act on: "I trained the team on Terraform" is work, "I trained in
# Terraform", "I completed a course in Kafka" and "I submitted my application" are not (#113).
_BY_OBJECT = frozenset("trained completed reviewed submitted spotted finished passed earned".split())
# Verbs of the letter's own frame by who they go to: "I wrote to you", "I emailed to your team" is the letter, "I wrote
# Kafka consumers" is work (#113). "sent" and "e-mailed" are no past form the walk reads (_PAST), so they are not here.
_TO_THEM = frozenset("wrote emailed".split())
_LEARNING = frozenset("""course courses training trainings webinar webinars certificate certificates certification
    certifications class classes degree degrees bootcamp bootcamps workshop workshops tutorial tutorials exam exams lesson
    lessons lecture lectures diploma""".split())
# the posting the text answers (the reader's own text), and the application itself
_POSTING = frozenset("posting vacancy advert advertisement ad listing description".split())
_APPLYING = _POSTING | frozenset("application cv résumé resume letter form documents opening role".split())
# what someone applies for or to as a candidate: "I applied for the role", "I applied to your company" (#113)
_APPLIED_TO = _APPLYING | frozenset("job jobs position positions company roles your".split())
# where the words a verb acts on end ("a course | in Kafka")
_PREPOSITIONS = frozenset("in on at for with about from to by of into using via during under over through across as like "
                          "before after".split())
_TOKEN = re.compile(r"[A-Za-z][A-Za-z'’-]*|[,;:.!?]")
_SUBJECTS = frozenset("i i've i’ve i'm i’m we we've we’ve we're we’re".split())
_JOINERS = frozenset({"and", ",", "then"})
_STOPS = frozenset(".;:!?")


def _work(verb: str, acts_on: list[str], after: str, then: list[str]) -> bool:
    """Whether a verb said as done is work, by the verb and what it acts on (`acts_on`, up to `after`, the preposition
    or mark that ends it, and `then`, the words after that preposition)."""
    verb = verb.lower()
    if verb in _NOT_DONE:
        return False
    if verb == "applied":   # a method applied to work is work; applying with no object, or for a job, is not (#113)
        return bool(acts_on) and not (after in ("for", "to") and any(w in _APPLIED_TO for w in then))
    if verb in _TO_THEM and not acts_on and after == "to" and then[:1] in (["you"], ["your"]):
        return False
    if verb not in _BY_OBJECT:
        return True
    if not acts_on or acts_on[0] == "that" or "your" in acts_on:   # "I trained in …", "I spotted that …", "your posting"
        return False
    if any(w in _LEARNING or w in _APPLYING for w in acts_on):
        return False
    return not (acts_on[-1] in ("module", "modules") and after in ("on", "in", "about", "of"))   # "a module on Kafka"


def _words(tokens: list[str], i: int) -> tuple[list[str], int]:
    """The words from token `i` up to a preposition, a joiner or a stop, and where they end."""
    words = []
    while i < len(tokens) and tokens[i] not in _JOINERS and tokens[i] not in _STOPS and tokens[i].lower() not in _PREPOSITIONS:
        words.append(tokens[i].lower())
        i += 1
    return words, i


def _acts_on(tokens: list[str], i: int) -> tuple[list[str], str, list[str]]:
    """The words from token `i` up to a preposition, a joiner or a stop, the token that ends them, and the words after
    that token when it is a preposition ("the role" in "applied last week | for | the role")."""
    words, i = _words(tokens, i)
    after = tokens[i].lower() if i < len(tokens) else ""
    return words, after, (_words(tokens, i + 1)[0] if after in _PREPOSITIONS else [])


def _ends_clause(token: str) -> bool:
    """A stop, or "I" or "we", who start a clause of their own."""
    return token in _STOPS or token.lower() in _SUBJECTS


def _clause(tokens: list[str], verb: str, i: int):
    """Each verb of one first-person clause, from `verb` (the first one, '' when it has no past form) and token `i` after
    it, with what it acts on: the verbs joined by "and", "," or "then" ("I sent events and built consumers"). It ends at a
    stop, at "I" or "we" (their own clause), and where a joiner leads to a new subject with its own verb ("and the team
    built"). Each token is read at most four times, so a long text stays linear."""
    while True:
        if verb:
            yield (verb, *_acts_on(tokens, i))
        while i < len(tokens) and tokens[i] not in _JOINERS:
            if _ends_clause(tokens[i]):
                return
            i += 1
        while i < len(tokens) and (tokens[i] in _JOINERS or tokens[i].endswith("ly") or tokens[i] == "also"):
            i += 1
        if i >= len(tokens):
            return
        if _PAST_WORD.fullmatch(tokens[i]):
            verb, i = tokens[i], i + 1
            continue
        verb = ""                                    # more of what the verb acts on, unless a new subject starts here
        while i < len(tokens) and tokens[i] not in _JOINERS:
            if _ends_clause(tokens[i]) or _PAST_WORD.fullmatch(tokens[i]):
                return
            i += 1


# the words that open a clause about the employer or its product after an opening phrase ("…, your team runs …")
_THEIRS = frozenset("your their its".split())
# a year in the opening phrase: "Founded in 1998, the firm …", "Opened in the 1990s, this agency …" (#113)
_YEAR = re.compile(r"\b(?:19|20)\d{2}s?\b")


def _describes_them(tokens: list[str], k: int, sentence: str, starts: list[int]) -> bool:
    """Whether the past participle at token `k` opens a phrase about the employer, its product or its posting, not work
    done (#113): a preposition follows it, and right after that preposition comes "your" or the posting ("Advertised on
    your careers page: …", "Published in the vacancy text: …"), or the clause after the phrase's comma starts with
    "your", "their" or "its" ("Hosted on Kubernetes, its storefront …"), or with "the" or "this" when the phrase holds a
    year ("Founded in 1998, the firm …"). `sentence` and `starts` (where each token starts) give the year, which is no
    token. A "your" later in the phrase is the candidate's work for them ("Worked with Kafka in your field", #113).
    shortcut: an opening phrase about the product before "the" with no year ("Designed for scale, the platform is …")
    reads as a claim; add a rule only if letters show it often."""
    if k + 1 >= len(tokens) or tokens[k + 1].lower() not in _PREPOSITIONS:
        return False
    end = next((i for i in range(k + 1, len(tokens)) if tokens[i] == "," or tokens[i] in _STOPS), len(tokens))
    head = [t.lower() for t in tokens[k + 2:min(end, k + 4)]]          # the first words after the preposition
    if head[:1] in (["the"], ["this"]):
        head = head[1:]
    if head[:1] == ["your"] or (head and head[0] in _POSTING):
        return True
    if tokens[end:end + 1] != [","] or end + 1 >= len(tokens):
        return False
    then = tokens[end + 1].lower()
    return then in _THEIRS or (then in ("the", "this") and bool(_YEAR.search(sentence, starts[k + 1], starts[end])))


def _fragment(tokens: list[str], sentence: str, starts: list[int]) -> int:
    """Where the verb of a sentence that opens with one is ("Built pipelines in Kafka.", "Recently led a team"), or -1. A
    name that only looks like a verb is none when a verb or a possessive follows it ("Ahmed built", "Ahmed's"), or a
    comma without a verb after it ("Alfred, your CTO, …"). A participle that describes the employer is none either
    (_describes_them).
    shortcut: a name ending in "-ed" before another kind of verb ("Ahmed told me") still reads as work; add a list of
    names only if a letter shows one."""
    k = 1 if tokens and tokens[0].lower().endswith("ly") else 0
    if k >= len(tokens) or not _PAST_WORD.fullmatch(tokens[k].lower()):
        return -1
    after = tokens[k + 1:k + 3]
    if after and _PAST_WORD.fullmatch(after[0]):
        return -1
    if after[:1] == [","] and not (len(after) > 1 and _PAST_WORD.fullmatch(after[1])):
        return -1
    return -1 if _describes_them(tokens, k, sentence, starts) else k


def _deeds(sentence: str):
    """Each verb the sentence says as done by the person, with what it acts on: after "I" or "we" (_DONE), joined to one
    of those, or opening a sentence without a subject (the candidate's own: owner's decision on #113)."""
    found = list(_TOKEN.finditer(sentence))
    tokens, starts = [m.group(0) for m in found], [m.start() for m in found]
    done = {m.start(): (m.group(1) or m.group(2), bisect.bisect_left(starts, m.end())) for m in _DONE.finditer(sentence)}
    k = _fragment(tokens, sentence, starts)
    if k >= 0:
        yield from _clause(tokens, tokens[k], k + 1)
    for k, token in enumerate(tokens):
        if token.lower() in _SUBJECTS:
            skip = k + 2 if k + 1 < len(tokens) and tokens[k + 1] not in _JOINERS | _STOPS else k + 1
            yield from _clause(tokens, *done.get(starts[k], ("", skip)))


def _done(sentence: str) -> bool:
    """Whether the sentence says, in the first person or as a fragment, that work was done (see _deeds and _work)."""
    return any(_work(*deed) for deed in _deeds(sentence))


# An honest bridge names the missing thing on purpose (in an interview that is the right answer).
HONEST = re.compile(r"\b(have not|haven't|do not have|don't have|not (?:yet )?(?:used|worked)|"
                    r"no (?:(?:professional|production|hands-on|commercial|prior|direct) )?experience|"
                    r"closest|would (?:get|learn|pick)|new to me|only (?:read|studied))\b", re.IGNORECASE)
FIRST_PERSON = re.compile(r"\b(?:I|my|me|I'm|I've)\b")


def unwished(sentence: str, wish: re.Pattern = WISH) -> str:
    """The sentence without its wishes and without a clause about a team as it works now: from each wish word to where
    the wish ends. "I have used Kafka and would like to learn Spark" keeps "I have used Kafka and"; a wish elsewhere in a
    sentence never hides a claim. The team clause goes first: a wish ends at its "we" and would leave "we use Kafka"
    without its "where" (#109)."""
    kept = _TEAM_CLAUSE.sub(" ", sentence)
    return re.sub(f"(?:{wish.pattern}){_WISH_END}", " ", kept, flags=(wish.flags & re.IGNORECASE) | re.DOTALL)


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def mentions(text: str, term: str) -> bool:
    """Whether `text` names `term` as a whole word (case blind)."""
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text or "", re.IGNORECASE))


_INTEREST = re.compile(r"\b(?:interests?|passion|curiosity|enthusiasm|wish|goal|plans?|aim|hope)\b", re.IGNORECASE)


def _owned(text: str, term: str) -> bool:
    """Whether `text` speaks of `term` as the person's own: "my Kafka pipelines", "our streaming Kafka cluster". "My
    interest in Kafka" owns an interest, not Kafka (#82)."""
    return any(not _INTEREST.search(found.group(1)) for found in
               re.finditer(rf"\b(?:my|our)\s+((?:[\w-]+\s+){{0,2}}){re.escape(term)}(?![A-Za-z0-9])", text, re.IGNORECASE))


def names_candidate(text: str, first_name: str) -> bool:
    """Whether a text written as the person uses their own first name (it talks about them, not as them)."""
    return bool(first_name) and bool(re.search(rf"\b{re.escape(first_name)}\b", text or ""))


# A spoken language said with a level is a claim of it (owner's decision on #113): "I am fluent in German", "I speak
# English and German", "native German speaker", "German (C1)", "German at B2 level". Named any other way ("German
# clients", "German-speaking customers", "I worked with German clients") it is no claim of the language.
_LANGUAGE = r"[A-Z][a-z]++(?![\w'’-])"                     # any language a list names: "fluent in Spanish and German"
_LANGUAGE_LIST = _LANGUAGE + r"(?:\s*(?:,\s*(?:(?:and|or)\s+)?|(?:and|or|&)\s+)" + _LANGUAGE + r")*"
_LEVEL_BEFORE = (r"(?i:\b(?:fluent(?:ly)?|native|bilingual|speaks?|spoke|speaking|speaker|proficient|business[- ]level|"
                 r"working\s+knowledge|mother\s+tongue))\s+(?:(?i:in|of)\s+)?"
                 r"(?:(?i:fluent|native|good|basic|some|conversational|excellent|business[- ]level)\s+)?")
_LEVEL_AFTER = (r"(?:\s*\(\s*|\s*[:–-]\s*|\s+(?:(?i:is\s+my|at)\s+)?(?:(?i:an?)\s+)?(?:(?i:level)\s+)?)"
                r"(?:[ABC][12]\b|(?i:native|fluent(?:ly)?|bilingual|business[- ]level|proficient|mother\s+tongue|speaker)\b)")
_SPOKEN_LEVEL = re.compile(rf"{_LEVEL_BEFORE}(?P<listed>{_LANGUAGE_LIST})"
                           rf"|(?<![\w-])(?P<named>{'|'.join(map(re.escape, keywords.SPOKEN))})(?![\w'’-])(?=(?P<level>{_LEVEL_AFTER}))")
# What the job needs, right after a level and its language: "Fluent German is a must", "German (C1) is required for the
# role", "German at B2 level or higher is preferred" state the job's need, not the person's skill (#113). Possessive
# repeats, each after a fixed word or mark, so a long run of spaces is read once.
_REQUIRED = re.compile(r"(?:\s*+\))?+(?:\s++(?i:level)\b)?+(?:\s++(?i:or\s++(?:higher|above|better))\b)?+(?:\s*+[,–-])?+"
                       r"\s++(?i:(?:is|are)\s++(?:required|a\s++must|needed|essential|preferred|expected|mandatory|a\s++plus"
                       r"|an\s++advantage))\b")
# Words before a level, in its clause, that give the language to someone else, to the job, to a wish to learn or to a
# "not": "your clients speak German", "the role needs fluent German", "I do not speak German", "with native German speakers".
_NOT_THEIRS = re.compile(r"(?i:\b(?:you|your|yours|they|their|he|she|his|her|who|everyone|someone"
                         r"|(?:the|this|that|a|an|our)\s+(?:role|position|job|posting|vacancy|team|company|office|business)"
                         r"|requires?|required|requirements?|asks?\s+for|asking\s+for|needs?|needed|seeking|looking\s+for|preferred"
                         r"|clients?|customers?|colleagues?|partners?|users?|people|staff|candidates?"
                         r"|not|never|cannot|learn|learning|study|studying|improve|improving|with|for|among)\b|n['’]t\b)")
_CLAUSE_BREAK = re.compile(r"[,;:()]|\s[–—-]\s")


def spoken_claims(said: str) -> set[str]:
    """The languages a sentence (its wishes cut) gives the person with a level (#113): no word of _NOT_THEIRS before the
    level in its clause, and no need of the job right after it (_REQUIRED). Every list name is returned ("Spanish" too);
    the caller keeps the ones it checks.
    shortcut: a need said further away ("Fluent German, as your ad says, is a must") still reads as a claim; add the
    words only if a letter shows one."""
    breaks = [m.end() for m in _CLAUSE_BREAK.finditer(said)]
    others = [m.start() for m in _NOT_THEIRS.finditer(said)]
    out: set[str] = set()
    for m in _SPOKEN_LEVEL.finditer(said):
        i, k = bisect.bisect_right(breaks, m.start()), bisect.bisect_left(others, m.start())
        level_end = m.end("level") if m.group("named") else m.end()      # "German (C1|) is required", "Fluent German| is …"
        if k and others[k - 1] >= (breaks[i - 1] if i else 0) or _REQUIRED.match(said, level_end):
            continue
        out.update(re.findall(r"[A-Z][a-z]+", m.group("listed")) if m.group("listed") else [m.group("named")])
    return out


class ClaimCheck:
    """The technologies and spoken languages the CV cannot back up (`cover_letter.unverified_terms`), and whether a text
    claims one. A language is claimed only when it is said with a level (spoken_claims): "I worked with German clients"
    claims no German (#113)."""

    def __init__(self, unverified: list[str]) -> None:
        self.terms = list(unverified or [])
        self._spoken = frozenset(t for t in self.terms if t in keywords.SPOKEN)

    def claimed_in(self, sentence: str, honest_ok: bool = False) -> str:
        """The first technology this sentence presents as experience ('' if none): claiming wording, or "my"/"our" up
        to two words before it ("my Kafka pipelines"); a language said with a level. What a wish names is never a claim;
        with `honest_ok` an honest bridge is not one either."""
        if honest_ok and HONEST.search(sentence):
            return ""
        said = unwished(sentence)
        spoken = spoken_claims(said) if self._spoken else set()
        claims_any = bool(CLAIM.search(said)) or _done(said)
        return next((term for term in self.terms if (term in spoken if term in self._spoken else
                                                     mentions(said, term) and (claims_any or _owned(said, term)))), "")

    def unbacked(self, text: str, honest_ok: bool = False) -> str:
        """The first technology a text presents as experience though the CV lacks it ('' if none)."""
        return next((term for term in (self.claimed_in(s, honest_ok) for s in sentences(text)) if term), "")


_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#]*")
# A position's dates: a range ("2023 – 2024", "Sep 2025 – Apr 2026", "2024 – present") or a year in brackets ("(2021)")
_DATES = re.compile(r"\b(?:19|20)\d{2}\s*[–—-]\s*(?:[A-Za-z]{3,9}\.?\s+)?(?:(?:19|20)\d{2}|present|now|today|current)\b"
                    r"|\([^()]*\b(?:19|20)\d{2}\b[^()]*\)", re.IGNORECASE)
_BULLET = re.compile(r"^[-–—•·*▪◦]")
# a month just before the dates' year ("…, Jan 2022 – Mar 2023"): part of the dates, never of the job's name
_MONTH_END = re.compile(r"[\s,(]*\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|"
                        r"august|september|october|november|december)\.?\s*$", re.IGNORECASE)
# Between a job's title and its employer: "Developer – Contoso", "Developer, Contoso", "Developer | Contoso"
_SEPARATOR = re.compile(r"\s[–—|-]\s|,\s")
# Study, not work: a section of it, a place of it, or a degree as the first word ("BSc, Computer Science – …").
# "Research Intern (Pre-Diploma Practice) – Diskret" is a job: a degree word later in the line does not count.
_STUDY_SECTION = re.compile(r"(education|studies|certificat|course|training|language|award|publication|conference)", re.IGNORECASE)
# a course, whatever job it trains for: "Teacher Training Course, …", "Data Analyst Bootcamp, …"
_COURSE = re.compile(r"\b(training|course|bootcamp|diploma|degree|programme|program|certificate|studies)\b", re.IGNORECASE)
_STUDY_PLACE = re.compile(r"\b(university|college|school|institute|academy|faculty|polytechnic|gymnasium|lyceum|conservatory)\b",
                          re.IGNORECASE)
# A job title is short and opens with no action verb ("Head of Sales", "Full-stack Developer", "Data scientist"),
# unlike work done ("Led migration, …", "Built dashboards – …", "Designed APIs for …"). These "-ed" words open real titles.
_TITLE_WORD = re.compile(r"[A-Za-z][\w+#'’-]*")
_TITLE_ED = frozenset("applied embedded licensed certified registered qualified chartered accredited advanced "
                      "self-employed".split())
_ACTION = frozenset("led built wrote ran made cut won drove grew taught sold set took gave kept rebuilt rewrote oversaw "
                    "began brought held spent got".split())
# a degree as the first words: "Master of Science", "Master's in …", "BSc" – never "Master Data Engineer"
_DEGREE = re.compile(r"^(?:(?:bsc|msc|ba|ma|phd|mba|bachelor\w*|degree|diploma)\b|"
                     r"master(?:[’']?s)?(?:\s+(?:of|in|degree|programme|program|\d)\b|[’']s\b))", re.IGNORECASE)
# The nouns of a job in the title part: with one of them, a school or an academy is an employer ("Teacher – International
# School"); a field of study ("Software Engineering", "Data Science") has none. A closed list on purpose.
# shortcut: a job whose noun is not here is read as study; add the noun when one is seen (#66 added the ones at places
# of study: pianist, postdoc, fellow, dean, … and "working student", a phrase, since "student" alone is study)
_JOB_WORDS = frozenset("""intern trainee assistant developer engineer programmer analyst manager consultant specialist
    administrator architect designer tester coordinator technician head lead teacher tutor lecturer professor instructor
    trainer coach researcher scientist librarian nurse counsellor counselor officer clerk receptionist bookkeeper accountant
    pianist musician accompanist organist singer postdoc postdoctoral fellow dean director curator secretary""".split())
_JOB_PHRASES = re.compile(r"\bworking\s+student\b", re.IGNORECASE)
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
        self._cv = cv_text or ""
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
        title = _SEPARATOR.split(before, maxsplit=1)[0] if dates else ""
        job = (any(w.lower() in _JOB_WORDS for w in _TITLE_WORD.findall(title)) or bool(_JOB_PHRASES.search(title))) \
            and not _COURSE.search(title)
        if (not dates or _BULLET.match(line) or not _SEPARATOR.search(before)
                or (_STUDY_PLACE.search(before) and not job) or _DEGREE.match(line)):
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

    @classmethod
    def job_names(cls, cv_text: str) -> list[str]:
        """The jobs a CV names, in its order, as "title, employer" ("Junior Developer, Northwind Parcel"): the headings of
        its positions without their dates. None when the CV names its jobs some other way (see the class)."""
        names = []
        for head, _body in cls._read(cv_text or ""):
            dates = _DATES.search(head)
            before = (_MONTH_END.sub("", head[:dates.start()]) if dates else head).strip(" ,–—|-(")   # only before real dates
            name = ", ".join(p.strip(" ,–—|-") for p in _SEPARATOR.split(before, maxsplit=1) if p.strip(" ,–—|-"))
            if name and name not in names:
                names.append(name)
        return names

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

    # "I built the API at Contoso Labs", "I worked for Contoso": a name after "at", after "for" only right after a word of
    # employment (so "a tool for Slack" is no employer), after "with" only with a legal ending ("with Contoso Ltd"). It is
    # followed by punctuation or a word that ends the name, so "for Kubernetes clusters" is none either.
    _INTRO = r"(?:\b[Aa]t|\b(?:work(?:ed|ing)?|interned|intern|internship|consulted|freelanced|contracted)\s+for|\b[Ww]ith)\s+"
    # capitalised words; "At" or "With" starts the next name and never continues this one (so a run of them stays linear)
    _CAPITALS = r"(?:(?!(?:At|With)\b)[A-Z][\w&'’.-]*)(?:\s+(?:(?!(?:At|With)\b)[A-Z][\w&'’.-]*|&|of))*"
    _ENDS = ("as on in at where from until during and to for with since before after while last this next every each over "
             "that which who when because but so I we")
    # a place of work after a possessive: "at Fabrikam’s office" is Fabrikam, "at Contoso's event" names no one (#113)
    _PREMISES = "office offices site headquarters plant factory warehouse store branch"
    _END = (rf"\s*(?:[,.;:)]|$)|\s+(?:{'|'.join(_ENDS.split())})\b|\s+\d"      # "… at Wingtip Toys last year", "… in 2023"
            rf"|['’]s\s+(?:{'|'.join(_PREMISES.split())})\b")
    # a lowercase name ("at contoso labs") has no capital to start it: lowercase words up to a word that ends a name or a
    # determiner, so "at a startup" and "at the weekend" give none
    _LOWER = rf"(?!(?:{'|'.join((_ENDS + ' of or a an the my our your his her their its').split())})\b)[a-z][\w&'’-]*"
    _NAME = rf"(?:(?P<capital>{_CAPITALS})(?={_END})|(?P<lower>{_LOWER}(?:\s+{_LOWER})*))"
    _AT_NAME = re.compile(_INTRO + _NAME)
    _AND_NAME = re.compile(r"\s+and\s+" + _NAME)                                # "at Contoso Labs and Globex Labs"
    # "My work at Contoso Labs taught me …": the phrase itself says the candidate worked there, and a verb may follow the
    # name. The nouns are the ones that mean a time employed; "my talk at PyCon" is no job.
    _MY_TIME_AT = re.compile(rf"\b[Mm]y\s+(?:[a-z]+\s+)?(?:work|time|years?|months?|role|job|internship|placement|stint|experience)"
                             rf"\s+at\s+(?P<capital>{_CAPITALS})(?={_END}|\s+[a-z])")
    # "I joined Contoso Labs in 2022", "Joined Globex in 2021", "I was employed by Contoso Labs": the verb says the job, so
    # the name right after it counts; "joined the team" or "joined your webinar" names no one (#113)
    _JOINED = re.compile(r"\b(?:(?P<joined>[Jj]oined)|[Ee]mployed\s+by)\s+" + _NAME)
    # a role noun of the code's job words before "for": "as a tester for Globex", "Developer for Contoso Labs" (#113)
    _ROLE_FOR = re.compile(r"(?i:\b(?:" + "|".join(sorted(_JOB_WORDS)) + r")s?)\s+for\s+" + _NAME)
    _OPENERS = frozenset("as was were am been".split())
    # being somewhere, said without a verb of work: "I was at Wingtip Toys", "I spent two years at …", "I trained at …"
    _THERE = re.compile(r"\b(?:was|were|interned|trained|spent)\b")
    # a visit, not work: "I interviewed at Globex", "I spoke at PyCon" – the verb right before "at", so "I presented the
    # results at Contoso Labs" is still work. A place after a visit is never read as an employer; the rest of the sentence
    # is ("I interviewed at Globex, and I tested apps at Contoso Labs" names Contoso Labs).
    _VISITED = re.compile(r"\b(?:interviewed|visited|spoke|presented|applied|exhibited|competed)\s+$")
    _LEGAL = frozenset("ltd limited inc corp corporation llc plc gmbh ag sa s.r.o a.s".split())
    # words of a name that say nothing about which company it is: they never clear a name by themselves
    _GENERIC = frozenset("""software data cloud systems system solutions services service technologies technology tech digital
        group labs lab consulting global international company partners studio studios""".split())
    # A lowercase name counts only when it ends in a word for a firm or a place of work: a closed list on purpose, as a
    # field of work ("good at corporate finance", "at personal care") also follows "at" without a capital. So
    # "at globex audit" is not caught.
    _WORKPLACE = frozenset("labs lab works industries holdings partners associates hospital clinic hospice centre center "
                           "pharmacy agency bank".split())
    _NOT_A_NAME = frozenset("""i the a an my our your this that these mr mrs ms miss dr prof sir madam hiring team monday tuesday
        wednesday thursday friday saturday sunday january february march april may june july august september october
        november december christmas easter""".split())
    # "at" with a bare noun is an English idiom, not a place ("at scale", "at home"): a closed set of phrases. A one-word
    # name is also ordinary when the text, the CV, the company or the posting writes it in lowercase.
    _AT_IDIOMS = frozenset("""home work school night scale least last first once times heart hand risk length large ease best
        worst most all random sea speed pace present noon midnight dawn dusk lunch weekends""".split())
    # a name with one of these names an event: being at one is no job ("I was at Contoso Expo last year")
    _EVENTS = frozenset("expo fair conference summit meetup hackathon festival congress convention forum".split())

    def invented(self, text: str, company: str = "", posting: str = "") -> list[str]:
        """Employers a first-person sentence places the candidate at or works for ("I built the API at Contoso Labs", "my
        time at Globex Partners") that neither the CV, the company written to nor the posting names (#63): a name the model
        made up. [] when none. A name counts as known when the whole of it is in one of them, or its first telling word is,
        written there with a capital as a name ("Initech Software" is not cleared by "software", "Present Labs" not by "2024 –
        present": #113). What a wish names is no claim. Not caught: a lowercase name that
        ends in a field of work, not a firm or a place ("at globex audit"); the middle names of a list of three ("at A, B and
        C" names A only); a lowercase name after "my work at"; "we built … at X" (first person only). A false alarm left:
        "my time at" an event without an event word ("My time at PyCon Prague was fun")."""
        known = " ".join((self._cv.lower(), (company or "").lower(), (posting or "").lower()))
        # the sources' words only: the model's own text never clears a name it made up ("quality … at Quality")
        lowercase = {w for w in _WORD.findall(" ".join((self._cv, company or "", posting or ""))) if w.islower()}

        known_words = set(re.findall(r"[a-z0-9]+", known))
        sources = _DATES.sub(" ", " ".join((self._cv, company or "", posting or "")))     # "2024 – Present" names no one
        capitalised: dict[str, bool] = {}

        def as_name(word: str) -> bool:     # the sources write it with a capital somewhere ("Northwind", "NORTHWIND")
            if word not in capitalised:
                capitalised[word] = any(m.group(0)[0].isupper() for m in re.finditer(
                    rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", sources, re.IGNORECASE))
            return capitalised[word]

        def named(words: str) -> bool:      # each piece of the name a word of the sources first: one search per name is slow
            phrase = words.lower()
            return set(re.findall(r"[a-z0-9]+", phrase)) <= known_words and \
                bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", known))
        out: dict[str, None] = {}
        seen: set[str] = set()
        for sentence in sentences(text):
            for name in self._names_in(unwished(sentence)):
                name = re.sub(r"['’]s$", "", name)          # "at Contoso's" is Contoso
                if name in seen:
                    continue
                seen.add(name)
                words = [w for w in re.findall(r"[A-Za-z0-9][\w&'’.-]*", name) if w.lower().strip(".") not in self._LEGAL]
                if self._ordinary(words, lowercase):
                    continue
                telling = [w for w in words if w.lower() not in self._GENERIC and len(w) >= 3]
                if named(" ".join(words)) or (telling and named(telling[0]) and as_name(telling[0])):
                    continue                    # the whole name, or its first telling word, is in a source ("EY", "Northwind")
                out[name] = None
        return list(out)

    def _names_in(self, said: str):
        """The names a sentence (its wishes cut) places the candidate at: after "at" or "worked for" only where it says
        they did something ("I built", "I was"), each name of "at A and B", after "my work at" ("My" opens a sentence too),
        after the candidate's role and "for", and after "joined" or "employed by" (#113)."""
        yield from (m.group("capital").rstrip(".") for m in self._MY_TIME_AT.finditer(said))
        yield from self._roles_for(said)
        deeds = list(_deeds(said))
        verbs = {verb.lower() for verb, *_rest in deeds}
        works = bool(FIRST_PERSON.search(said)) and bool(CLAIM.search(said) or any(_work(*deed) for deed in deeds)
                                                         or self._THERE.search(said))
        for found in self._JOINED.finditer(said):     # "I joined" or a fragment ("Joined Globex"), never "Contoso joined"
            if ("joined" in verbs if found.group("joined") else works or "employed" in verbs):
                yield from filter(None, [self._name(found)])
        if not works:
            return
        for found in self._AT_NAME.finditer(said):
            if self._VISITED.search(said[max(0, found.start() - 20):found.start()]):
                continue                                             # "I interviewed at Globex": a visit
            legal_only = found.group(0).lower().startswith("with")   # "with Docker": a tool, unless "with Contoso Ltd"
            more = found
            while more:
                name = self._name(more)
                if name and not (legal_only and not any(w.lower().strip(".") in self._LEGAL for w in name.split())):
                    yield name
                more = self._AND_NAME.match(said, more.end())

    def _roles_for(self, said: str):
        """The names after a role noun and "for" that is the candidate's own job: after "as" ("as a tester for Globex", not
        "applied as …"), after "I was", "I am", "I have been" ("I was a junior developer for Contoso Labs"), or a title that
        opens the sentence ("Senior Developer for Fabrikam since 2021"). "I built a password manager for Slack" makes a
        thing, so a verb, a preposition, a subject or a stop before the role ends the search.
        Not caught: a role said of another person with "as" ("Ms Novak works as lead developer for Globex") is read as
        the candidate's."""
        found = list(_TOKEN.finditer(said)) if self._ROLE_FOR.search(said) else []
        tokens, starts = [m.group(0).lower() for m in found], [m.start() for m in found]
        for match in self._ROLE_FOR.finditer(said):
            if self._own_role(said, found, tokens, bisect.bisect_left(starts, match.start())):
                yield from filter(None, [self._name(match)])

    def _own_role(self, said: str, found: list[re.Match], tokens: list[str], k: int) -> bool:
        """Whether the role at token `k` is the candidate's (see _roles_for). The walk back ends at the "for" of the role
        before, so a sentence is read once."""
        for j in range(k - 1, -1, -1):
            word = tokens[j]
            if word == "as":
                return not self._VISITED.search(said[max(0, found[j].start() - 20):found[j].start()])
            if word in self._OPENERS:                               # "I was", "I am", "I have been", "I've been"
                return j > 0 and (tokens[j - 1] in _SUBJECTS or tokens[j - 1] in ("have", "had"))
            if word in ("i'm", "i’m"):
                return True
            if word in _PREPOSITIONS or word in _STOPS or word in _SUBJECTS or word == "," or \
                    (_PAST_WORD.fullmatch(word) and word not in _TITLE_ED):           # "as an applied scientist" goes on
                return False
        return found[k].group(0)[0].isupper() and tokens[0].strip(".") not in self._NOT_A_NAME   # "The Lead Developer for …"

    def _name(self, found: re.Match) -> str:
        """The name a match holds: its capitalised words, or lowercase words that end in a legal or workplace word."""
        if found.group("capital"):
            return found.group("capital").rstrip(".")
        words = found.group("lower").split()
        return " ".join(words) if len(words) >= 2 and (words[-1] in self._LEGAL or words[-1] in self._WORKPLACE) else ""

    def _ordinary(self, words: list[str], lowercase: set[str]) -> bool:
        """Whether a name's words are no employer's: a title, a day, an idiom ("at Scale"), a word the sources write in
        lowercase (`lowercase`: the words of the CV, the company and the posting written so), or an event."""
        if not words or words[0].lower().strip(".") in self._NOT_A_NAME or any(w.lower() in self._EVENTS for w in words):
            return True
        return len(words) == 1 and (words[0].lower() in self._AT_IDIOMS or words[0].lower() in lowercase)

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
# In the text checked, a digit right after a letter is part of a name ("k8s", "S3", "EC2", "Python3"), not a figure it
# states (#78); "10x" stays one. The name takes its dotted parts too ("Python3.12", "v2.1", group `name`), so "12" is no
# figure, and nor are "Q4" and "H2" (#113). Sources are read with FIGURE as before: whatever digit they hold backs that figure.
STATED = re.compile(r"(?P<name>[A-Za-z]\d+(?:\.\d+)*)"
                    r"|(?<![\d.,A-Za-z])\d{1,3}(?:[ \u00a0\u202f,.]\d{3})+(?!\d)(?:[.,]\d{1,2}(?!\d))?|(?<![A-Za-z\d])\d+(?:[.,]\d+)*")
# A figure used as an amount of something: "5 years", "40%", "1,200 users", "3x" – a claim, not a reference ("situation 3").
_UNIT = (r"\s*(?:\+\s*)?(?:years?|yrs|months?|weeks?|days?|hours?|%|per ?cent|users|customers|clients|people|persons?|developers|"
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
    stated = [m.group(0) for m in STATED.finditer(body) if not m.group("name") and not _version(body, m)]
    return [f for f in dict.fromkeys(stated) if not backed(f)]


# a tool's names, as keywords knows them ("Python", "Java", "Node", ".NET"): a dotted number after one is its version
_TOOLS = frozenset(n for name, spellings in keywords.VOCABULARY.items() for n in (name, *spellings))
_UNIT_AFTER = re.compile(_UNIT, re.IGNORECASE)


def _version(body: str, found: re.Match) -> bool:
    """Whether a figure is a version: a dotted number right after a tool's name ("Python 3.12", "Java 1.8"), with no
    unit after it ("Python 2.5 years" is an amount). "Java 17" stays a figure: without a dot it may count something (#113)."""
    if not re.fullmatch(r"\d+(?:\.\d+)+", found.group(0)) or _UNIT_AFTER.match(body, found.end()):
        return False
    before = body[max(0, found.start() - 30):found.start()]
    words = before.split()
    return before.endswith((" ", "\u00a0")) and bool(words) and words[-1].lstrip("(\"'“‘") in _TOOLS


def rejected(problems: list[str], what: str = "version") -> str:
    """The note sent back with the next request when a draft broke a rule."""
    return f"\nYour previous {what} was rejected. Fix these problems:\n" + "\n".join(f"- {p}" for p in problems) + "\n"
