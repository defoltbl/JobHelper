"""Adapt the master CV (.docx) to one job posting.

Follows data/cv_adaptation_instruction.md: only the PROFILE paragraph and the
KEY SKILLS rows change. The header, PROJECTS, WORK EXPERIENCE, EDUCATION and
LANGUAGES stay exactly as in the master, because we edit `word/document.xml`
inside the master package and copy every other file in the .docx unchanged.

After building, the result is checked: locked paragraphs identical to the
master, no em dashes or emojis, no technology the master cannot back up, and an
estimate that the text still fits on one page.
"""
from __future__ import annotations

import copy
import math
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from lxml import etree

from .word_document import P, R, Paragraph, WordDocument, set_run_text, text_of
from . import claims, config, llm, pdf, store
from .claims import mentions

# Technologies the master does not contain (instruction, section 4). Used when
# the instruction file is missing or has no "Not in the master" line.
DEFAULT_UNVERIFIED = [
    "Kubernetes", "OpenShift", "Kafka", "A-MQ", "Ansible", "Argo", "GitOps", "Terraform",
    "Helm", "Bash", "PKI", "TLS", "Google Cloud", "GCP", "GitHub Copilot", "AWS", "Jenkins",
]
_INTEREST = re.compile(r"\b(keen|interested|interest in|eager|grow into|looking to learn|"
                       r"motivated to learn|want to learn|excited to learn)\b", re.IGNORECASE)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️]")

CHARS_PER_LINE = 118      # Calibri 9.5 pt on the master's A4 text width (calibrated on the example)
MAX_PAGE_TRIMS = 6        # with LibreOffice: how many items may be dropped to get back to one page
SPARE_LINES = 2           # the master leaves about 3 spare lines; stay inside that
MAX_PROFILE_CHARS = 760
MIN_ROWS, MAX_ROWS = 4, 8

SYSTEM = (
    "You adapt one candidate's CV to a job posting. You rewrite only the PROFILE "
    "paragraph and the KEY SKILLS rows. You never claim a technology, tool or "
    "experience that is not in the master CV. Use an en dash (–), never an em dash, "
    "and no emojis. You have no tools and no file access here: do not try to open, "
    "unzip, edit or convert any file. Another program builds the .docx from your "
    "answer. Reply once, with only the JSON object. " + llm.POSTING_RULE
)

PROMPT = """Write the new PROFILE text and KEY SKILLS rows for the job posting below. The
file handling is done elsewhere; you only supply the wording.

Adaptation rules from the candidate (follow the wording rules exactly):
---
{rules}
---

Master CV (the only source of truth):
---
{cv_text}
---

Current KEY SKILLS rows in the master:
{master_rows}
{rows_shape}

Job posting:
- Title: {title}
- Company: {company}
- Location: {location}
- Description: {description}
{feedback}
Return JSON with exactly these keys:
{{
  "profile": "<one paragraph, at most {max_profile} characters>",
  "skills": [{{"label": "<row label without colon>", "items": "<comma-separated items, no full stop>"}}],
  "role_short": "<the role in 1-3 words, e.g. Middleware Admin>"
}}
Limits: {min_rows}-{max_rows} skill rows; the rows together must not be longer than the
master's rows ({rows_budget} characters in total). Technologies that are not in the master
CV may appear only in PROFILE as an interest ("Keen to grow into ..."), never in KEY SKILLS."""

GENERIC_RULES = """PROFILE (one paragraph, 5-6 lines at most): keep the opening fact about the
candidate's degree, replace the middle with the posting's top 3-4 themes using only things the
CV can back up, keep a sentence about working independently only if the master's PROFILE has one, express anything the candidate
has not done as interest only, and keep the master's closing sentence about languages and the
role sought.
KEY SKILLS (about 7 rows): put the rows the posting cares about first, name the labels with the
posting's vocabulary, use the posting's exact keywords where they are true, merge rows the
posting does not care about into one short line instead of deleting them. Each row is a label
plus comma-separated items, no sentences, no trailing full stop."""


# ── instruction file ─────────────────────────────────────────────────────────
def load_rules(cv_text: str = "") -> str:
    """The adaptation rules to show the model: sections 1, 4 and 5 of the
    instruction file (what may change, how to adapt, the worked example).
    Without a file the built-in general rules are used, so the app works for
    any CV. {{placeholders}} in the file are filled with the person's own facts."""
    return instruction_sections(config.CV_INSTRUCTION, ("1", "4", "5"), cv_text, GENERIC_RULES)


def instruction_sections(path: Path, numbers: tuple[str, ...], cv_text: str, fallback: str) -> str:
    """The numbered "## N." sections of an instruction file the model is shown, with {{placeholders}} filled
    from the person's own facts; `fallback` (the built-in general rules) when the file or those sections are missing."""
    if not path.exists():
        return fallback
    parts = re.split(r"(?m)^## ", config.fill_placeholders(path.read_text(encoding="utf-8"), cv_text))
    keep = [p for p in parts if re.match(rf"({'|'.join(map(re.escape, numbers))})\.", p)]
    return ("## " + "\n## ".join(k.strip() for k in keep)) if keep else fallback


def unverified_terms(master_text: str) -> list[str]:
    """Technologies that must not be claimed: the instruction's "never claim"
    list (or the default one), minus anything the master really contains."""
    terms = list(DEFAULT_UNVERIFIED)
    path = config.CV_INSTRUCTION
    if path.exists():
        m = re.search(r"Not in the master[^:]*:\s*(.+?)\.\s", path.read_text(encoding="utf-8"))
        if m:
            for raw in m.group(1).split(","):
                for t in re.split(r"/", raw):
                    t = re.sub(r"\b(administration)\b", "", t).strip()
                    if t and t not in terms:
                        terms.append(t)
    low = master_text.lower()
    return [t for t in terms if not re.search(rf"(?<![a-z0-9]){re.escape(t.lower())}(?![a-z0-9])", low)]


_FILLER = set("""the and for with you your our are will have has this that from into about over under more most very also such than then
    their they them was were been being can could should would may might must not but all any each every other another some many much new
    who what which when where while how why its his her she him out off per via able well good great strong high level based using use used
    work working works role roles team teams job jobs position company companies experience experienced skills skill knowledge ability
    including include includes within across between part time full year years month months day days people person candidate candidates
    looking join offer offers opportunity environment related relevant required requirements preferred plus etc""".split())


# Everyday pairs of words that say how someone works, not what they have done: found in most postings and fair in any CV.
_SOFT = {("attention", "detail"), ("end", "end"), ("self", "motivat"), ("root", "cause"), ("mostly", "remote"), ("fully", "remote"),
         ("version", "control"), ("large", "scale"), ("fast", "paced"), ("cross", "functional"), ("problem", "solving"), ("hands", "on"),
         ("day", "day"), ("best", "practic"), ("real", "world"), ("clear", "written"), ("written", "communicat"), ("plain", "language"),
         ("detail", "orient"), ("continuous", "improvement"), ("quality", "control"), ("time", "management"), ("decision", "mak")}


def _stem(word: str) -> str:
    """A word without its ending, so that "invoices" and "invoice", "reconciling" and "reconciled" compare equal."""
    w = word.lower()
    for ending in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if w.endswith(ending) and len(w) - len(ending) >= 4:
            return w[: -len(ending)]
    return w


def borrowed_phrases(text: str, description: str, backed: str) -> list[str]:
    """Phrases of two words that `text` (a drafted PROFILE) took from the posting although neither word is
    anywhere in what the person wrote (the master CV and their own notes): "cost center", "master data".

    The fixed "never claim" list knows technologies. This finds the same thing for any profession: the
    surest sign that a draft presents the posting's requirements as the person's experience is a term of
    the posting, in the draft, of which the CV knows nothing. One shared word is not enough to count,
    so ordinary wording is left alone."""
    words = lambda t: re.findall(r"[^\W\d_]{3,}", (t or "").lower())      # noqa: E731
    known = {_stem(w) for w in words(backed)}
    posting = words(description)
    wanted = {(_stem(a), _stem(b)) for a, b in zip(posting, posting[1:])
              if a not in _FILLER and b not in _FILLER and _stem(a) not in known and _stem(b) not in known}
    found, drafted = [], re.findall(r"[^\W\d_]{3,}", text or "")
    for a, b in zip(drafted, drafted[1:]):
        pair = (_stem(a), _stem(b))
        if pair in wanted and not any(pair[0].startswith(x) and pair[1].startswith(y) for x, y in _SOFT) \
                and f"{a} {b}".lower() not in [f.lower() for f in found]:
            found.append(f"{a} {b}")
    return found


def borrowed_claims(profile: str, description: str, backed: str) -> list[str]:
    """The borrowed phrases a PROFILE states as experience. One named only as an interest
    ("keen to grow into …") is the honest way to mention it and is left out."""
    phrases = borrowed_phrases(profile, description, backed)
    claimed = []
    for sentence in re.split(r"(?<=[.!?])\s+", profile or ""):
        said = _as_experience(sentence)
        claimed += [p for p in phrases if mentions(said, p) and p not in claimed]
    return claimed


def _as_experience(sentence: str) -> str:
    """The sentence without what an interest names ("keen to grow into Kafka"): the rest is stated as experience."""
    return claims.unwished(sentence, _INTEREST)


POSTING_SHOWN = 5000                   # how much of a posting the CV and letter prompts show (and their figure checks read)


def figure_sources(job: dict[str, Any], cv_text: str, own=(), references=()) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(sources, references) for `claims.unbacked_figures`. Your own: the CV, your notes and About you facts, plus what
    you typed (`own`). References: the posting (as much as the letter prompt shows), the job's title, company and location
    ("3M", "Praha 4"), plus `references` – they may be repeated, never claimed as your amount ("5+ years")."""
    return ((cv_text, config.experience_notes(), config.facts_block(cv_text), *own),
            ((job.get("description") or "")[:POSTING_SHOWN], job.get("title") or "", job.get("company") or "", job.get("location") or "",
             *references))


def profile_problems(profile: str, job: dict[str, Any], cv_text: str) -> tuple[list[str], list[str]]:
    """What a PROFILE claims that the person's own words do not back: (figures, names). A figure ("8 years") must come
    from the CV, the notes or About you; a technology or company name from those or from this job's own company and
    place (not its title: "Rust Developer" does not back "built Rust services"). The first word of a sentence is not taken for a name, and what an interest
    names ("keen to grow into Kafka") is no claim; the rest of its sentence still is."""
    sources, references = figure_sources(job, cv_text)
    figures = claims.unbacked_figures(profile, sources, references, brackets_ok=False)
    own = "\n".join((*sources, job.get("company") or "", job.get("location") or ""))     # not the title: it is the posting's word
    inner = " ".join(_after_first_word(s, _as_experience(s)) for s in claims.sentences(profile))
    return figures, unknown_skill_terms(inner, own)


def _after_first_word(sentence: str, rest: str) -> str:
    """`rest` (the sentence without its interests) without the sentence's first word, which is capital for being first."""
    words = rest.split()
    return " ".join(words[1:] if words and words[0] == sentence.split()[0] else words)


_ABBREVIATION = re.compile(r"\b(?:e\.g|i\.e|approx|etc|vs|incl|no|st|cca)\.$", re.IGNORECASE)   # a split there is no sentence end
_NOT_THE_SAME = {"java": "javascript"}     # a name inside a longer name of another technology: Java is not JavaScript
# a name inside the longer names CVs give it ("GitHub" backs "Git", "PySpark" backs "Spark"); elsewhere a name starts a
# word, and a short one is a whole word or its plural
_INSIDE = {"go": ("golang",), "git": ("github", "gitlab", "gitea", "gitops", "gitflow"), "qt": ("pyqt", "pyside", "qtquick"),
           "vue": ("vuejs", "vuex", "vuetify", "nuxt"), "spark": ("pyspark",), "mac": ("macos",), "ant": ("antd",),
           "torch": ("pytorch",), "test": ("pytest",)}


def unknown_skill_terms(items: str, master_text: str) -> list[str]:
    """Technology-looking words in a KEY SKILLS row that the master never
    mentions (names with a capital letter, digit or symbol, e.g. "Kafka", "S3")."""
    low, unknown = master_text.lower(), []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.]*", items):
        token = token.strip(".")
        if len(token) < 2 or token.islower():
            continue                                  # ordinary words: "schema design", "monitoring"
        seen = low.replace(_NOT_THE_SAME[token.lower()], " ") if token.lower() in _NOT_THE_SAME else low
        if not _named_in(token, seen) and token not in unknown:
            unknown.append(token)
    return unknown


def _named_in(token: str, low: str) -> bool:
    """Whether the lowercase master names `token` where a word starts ("Docker" in "Dockerized"; "Rust" is not in
    "trust"); a short name only as a whole word ("Go" is not in "good"). An abbreviation in capitals counts anywhere
    ("SQL" in "PostgreSQL", "API" in "APIs")."""
    word = token.lower()
    if token.isupper() and word in low:
        return True
    if any(form in low for form in _INSIDE.get(word, ())):
        return True
    end = r"s?(?![a-z])" if len(word) < 4 else ""          # "Gos", never "goes"
    return bool(re.search(rf"(?<![a-z]){re.escape(word)}{end}", low))


# ── docx (document.xml) helpers ──────────────────────────────────────────────
def _norm(s: str) -> str:
    return re.sub(r"[\s ]+", "", s).upper()



# How CVs head the two parts that are adapted (compared without spaces, so "K E Y  S K I L L S" counts).
PROFILE_HEADINGS = ("PROFILE", "SUMMARY", "PROFESSIONALSUMMARY", "PROFESSIONALPROFILE", "PERSONALPROFILE", "CAREERSUMMARY",
                    "ABOUTME", "ABOUT")
SKILLS_HEADINGS = ("KEYSKILLS", "SKILLS", "TECHNICALSKILLS", "CORESKILLS", "CORECOMPETENCIES", "COMPETENCIES",
                   "SKILLS&TOOLS", "PROFESSIONALSKILLS")
MAX_MASTER_ROWS = 14      # more "skill rows" than this means the end of the section was not found: leave it alone


def _is_heading(text: str) -> bool:
    """A section heading as CVs write them: a short line in capitals, without a colon
    (a skills row is "Label: items"). Whatever the next section is called, it ends the rows."""
    text = (text or "").strip()
    letters = "".join(ch for ch in text if ch.isalpha())
    return 3 <= len(letters) and len(text) <= 60 and letters.isupper() and ":" not in text


def sections(body) -> dict[str, Any]:
    """Locate the PROFILE paragraph and the KEY SKILLS rows in the body.

    The rows run from the skills heading to the next heading of any name. (They used to end
    only at four fixed headings: in a CV whose next section was called anything else, the
    whole of that section counted as skill rows and was replaced.)"""
    paras = [p for p in body if p.tag == P]
    names = [_norm(text_of(p)) for p in paras]
    out: dict[str, Any] = {"paras": paras, "profile": None, "rows": [], "rows_unclear": False}
    at_profile = next((i for i, name in enumerate(names) if name in PROFILE_HEADINGS), None)
    if at_profile is not None:
        for p in paras[at_profile + 1:]:
            if text_of(p).strip():
                if not _is_heading(text_of(p)):
                    out["profile"] = p
                break
    at_skills = next((i for i, name in enumerate(names) if name in SKILLS_HEADINGS), None)
    if at_skills is not None:
        for p in paras[at_skills + 1:]:
            if _is_heading(text_of(p)):
                break
            if text_of(p).strip():
                out["rows"].append(p)
        if len(out["rows"]) > MAX_MASTER_ROWS:
            out["rows"], out["rows_unclear"] = [], True
    return out


def adaptable(master_path) -> bool:
    """True if this Word CV has a profile section the app can find (so a full adapted copy can be made)."""
    try:
        return sections(WordDocument(master_path).body)["profile"] is not None
    except Exception:  # noqa: BLE001 - not a Word file the app can read
        return False


def master_rows(master_path) -> list[str]:
    return [text_of(p) for p in sections(WordDocument(master_path).body)["rows"]]


def build_docx(master_path, out_path, profile: str, skills: list[dict[str, str]]) -> None:
    """Write `out_path`: the master CV with only its profile and its skills rows changed."""
    doc = WordDocument(master_path)
    body = doc.body
    sec = sections(body)
    if sec["profile"] is None:
        raise ValueError("The master CV has no PROFILE section.")
    profile_para = Paragraph(sec["profile"])
    if not profile_para.writable:       # the paragraph's text sits inside a link or a content control: nothing to write into
        raise ValueError("The PROFILE paragraph of the master CV is built in a way the app cannot rewrite "
                         "(its text is inside a link or a form control). Retype that paragraph as plain text in Word.")
    profile_para.write(profile)

    if skills and sec["rows"] and sec["rows"][0].findall(R):       # (a first row without plain text: the rows are left as they are)
        template = sec["rows"][0]
        anchor = body.index(template)
        for p in sec["rows"]:
            body.remove(p)
        for n, row in enumerate(skills):
            p = copy.deepcopy(template)
            rr = p.findall(R)
            if not row["label"]:                              # a plain list, as in the master: the items alone
                set_run_text(rr[0], row["items"])
                for r in rr[1:]:
                    p.remove(r)
                body.insert(anchor + n, p)
                continue
            set_run_text(rr[0], f"{row['label']}: ")       # bold label run
            if len(rr) > 1:
                set_run_text(rr[1], row["items"])         # regular items run
                for r in rr[2:]:
                    p.remove(r)
            else:
                set_run_text(rr[0], f"{row['label']}: {row['items']}")
            body.insert(anchor + n, p)
    doc.save(out_path)                  # every other part of the file byte for byte


# ── checks ───────────────────────────────────────────────────────────────────
def _lines(text: str) -> int:
    return max(1, math.ceil(len(text) / CHARS_PER_LINE))


def estimate_lines(profile: str, rows: list[str]) -> int:
    return _lines(profile) + sum(_lines(r) for r in rows)


def _row_text(row: dict[str, str]) -> str:
    return f"{row['label']}: {row['items']}" if row["label"] else row["items"]


def _items(text: str) -> list[str]:
    return [i.strip() for i in re.split(r",(?![^()]*\))", text) if i.strip()]


_LABEL = re.compile(r"^([^,:]{1,40}):\s*(\S.*)$")      # "Label: items" (no comma before the colon)
_TERM_WORD = re.compile(r"[A-Za-z0-9+#]+")


class MasterSkills:
    """The KEY SKILLS rows of the master CV and what an adapted set of rows must keep: the master's shape (rows of
    "Label: items", or plain lists without a label). A plain list is only reordered, so it keeps every skill; labelled
    rows are regrouped and may leave out what the posting does not care about (the approved example does). A one-line
    plain list once came back as five labelled rows; to fit the master's one line, each row was cut to its first item."""

    def __init__(self, rows: list[str]) -> None:
        self.rows = [r.strip() for r in rows if r.strip()]
        labels = [bool(_LABEL.match(r)) for r in self.rows]
        self.labelled = bool(labels) and all(labels)
        self.plain = bool(labels) and not any(labels)    # neither (no rows, or a mix): the general rules alone

    @property
    def limits(self) -> tuple[int, int]:
        """How many rows an adapted CV may have: a plain list keeps its number of rows; labelled rows may be
        regrouped within MIN_ROWS..MAX_ROWS (fewer when the master has fewer)."""
        if self.plain:
            return (len(self.rows), len(self.rows))
        return (min(MIN_ROWS, len(self.rows)), MAX_ROWS) if self.labelled else (MIN_ROWS, MAX_ROWS)

    def items(self) -> list[str]:
        out = []
        for row in self.rows:
            m = _LABEL.match(row) if self.labelled else None
            out += _items(m.group(2) if m else row)
        return list(dict.fromkeys(out))

    def missing(self, skills: list[dict[str, str]]) -> list[str]:
        """The skills of a plain master list that the rows no longer name ("REST APIs" counts as kept by "REST API");
        always empty when the master's rows are not a plain list."""
        if not self.plain:
            return []
        kept = {claims.singular(w) for row in skills for w in _TERM_WORD.findall(row["items"])}
        return [item for item in self.items() if not all(claims.singular(w) in kept for w in _TERM_WORD.findall(item))]

    def shape_rule(self) -> str:
        """What the prompt says about the rows' shape; it wins over the general rules."""
        if not self.plain:
            return ""
        lo = self.limits[0]
        return (f"These rows have no labels. Return exactly {lo} row{'s' if lo > 1 else ''} the same way, each with an empty "
                "label, and put the items the posting cares about first. Keep every item: reorder them, never drop one. "
                "This wins over the rules above.")

    def fit(self, skills: list[dict[str, str]]) -> list[dict[str, str]]:
        """The rows in the master's shape whatever the model sent: a plain list gets its extra rows added, in order, to
        its last row, and the skills the model left out are put back (the master is the truth)."""
        if not self.plain:
            return skills
        if not skills:                                   # nothing usable came back: the master's own list
            return [{"label": "", "items": row} for row in self.rows]
        keep = self.limits[1]
        rows = [dict(r) for r in skills[:keep]]
        rows[-1]["items"] = ", ".join([rows[-1]["items"], *(r["items"] for r in skills[keep:])])
        gone = self.missing(rows)
        if gone:
            rows[-1]["items"] = ", ".join([rows[-1]["items"], *gone])
        return rows

    def row(self, data: Any) -> dict[str, str] | None:
        """One row of the model's answer in the master's shape (None when it holds nothing)."""
        if not isinstance(data, dict) or not data.get("items"):
            return None
        label = "" if self.plain else clean(str(data.get("label", ""))).rstrip(":")
        if not self.plain and not label:
            return None
        return {"label": label, "items": clean(str(data.get("items", ""))).rstrip(".")}


def content_problems(profile: str, skills: list[dict[str, str]], master_profile: str,
                     master_rows_: list[str], unverified: list[str], master_text: str = "") -> list[str]:
    """Why this draft can't be used as is (empty list = fine)."""
    problems = []
    rows = [_row_text(r) for r in skills]
    shape = MasterSkills(master_rows_)
    lo, hi = shape.limits
    if len(profile) > MAX_PROFILE_CHARS:
        problems.append(f"PROFILE is {len(profile)} characters; the limit is {MAX_PROFILE_CHARS}.")
    if not lo <= len(skills) <= hi:
        problems.append(f"KEY SKILLS has {len(skills)} rows; use {lo}-{hi}." if lo < hi else
                        f"KEY SKILLS has {len(skills)} rows; use exactly {lo}, as the master does.")
    gone = shape.missing(skills)
    if gone:
        problems.append("KEY SKILLS no longer names " + ", ".join(f"'{g}'" for g in gone) + " from the master; keep every skill.")
    budget = estimate_lines(master_profile, master_rows_) + SPARE_LINES
    used = estimate_lines(profile, rows)
    if used > budget:
        problems.append(f"Too long for one page: about {used} lines, the page has room for {budget}. Shorten.")
    for r in rows:
        tail = len(r) % CHARS_PER_LINE
        if len(r) > CHARS_PER_LINE and 0 < tail < 12:
            problems.append(f"Row '{r[:40]}…' wraps with an orphan word; shorten it to fit one line.")
    if master_text:
        for row in skills:
            for term in unknown_skill_terms(row["items"], master_text):
                where = f" (row '{row['label']}')" if row["label"] else ""
                problems.append(f"'{term}'{where} is not in the master CV; remove it from KEY SKILLS.")
    for term in unverified:
        if any(mentions(r, term) for r in rows):
            problems.append(f"'{term}' is not in the master CV, so it must not be in KEY SKILLS.")
        for sentence in re.split(r"(?<=[.!?])\s+", profile):
            if mentions(_as_experience(sentence), term):
                problems.append(f"'{term}' is not in the master CV; mention it in PROFILE only as an interest.")
                break
    return problems


def enforce(profile: str, skills: list[dict[str, str]], unverified: list[str],
            master_text: str = "") -> tuple[str, list[dict[str, str]]]:
    """Last line of defence: strip anything the master cannot back up."""
    kept_sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+", profile):
        if any(mentions(_as_experience(sentence), t) for t in unverified):
            continue
        kept_sentences.append(sentence)
    out_rows = []
    for row in skills:
        items = [i.strip() for i in re.split(r",(?![^()]*\))", row["items"]) if i.strip()]
        items = [i for i in items if not any(mentions(i, t) for t in unverified)]
        if master_text:
            items = [i for i in items if not unknown_skill_terms(i, master_text)]
        if items:
            out_rows.append({"label": row["label"], "items": ", ".join(items)})
    return " ".join(kept_sentences), out_rows


def en_dashes(text: str) -> str:
    """The en dash "–" wherever the model wrote the long em dash "—" (the person's documents never use it)."""
    return text.replace("—", "–")


def clean(text: str) -> str:
    """En dash instead of em dash, no emojis, single spaces."""
    text = EMOJI.sub("", en_dashes(text))
    return re.sub(r"[ \t]+", " ", text).strip()


def verify(master_path, out_path) -> list[str]:
    """Checks 2-4 of the instruction on the finished file."""
    problems = []
    master, out = WordDocument(master_path), WordDocument(out_path)
    for name in master.names():
        if name != WordDocument.TEXT and master.part(name) != out.part(name):
            problems.append(f"{name} differs from the master.")
    ms, os_ = sections(master.body), sections(out.body)

    def locked(sec):
        skip = {id(sec["profile"])} | {id(p) for p in sec["rows"]}
        return [etree.tostring(p) for p in sec["paras"] if id(p) not in skip]

    if locked(ms) != locked(os_):
        problems.append("A locked paragraph (header, projects, experience, education, languages) changed.")
    # every heading of the master must still be there, in the same order: a section must never go missing
    heads = lambda sec: [_norm(text_of(p)) for p in sec["paras"] if _is_heading(text_of(p))]     # noqa: E731
    if heads(ms) != heads(os_):
        problems.append("A section of the master CV is missing from the adapted one.")
    full = "\n".join(text_of(p) for p in os_["paras"])
    if "—" in full:
        problems.append("The CV contains an em dash.")
    if EMOJI.search(full):
        problems.append("The CV contains an emoji.")
    return problems


# ── file name ────────────────────────────────────────────────────────────────
def _camel(text: str, max_words: int = 3) -> str:
    ascii_ = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z0-9]+", ascii_)[:max_words]
    return "".join(w if w.isupper() else w[:1].upper() + w[1:] for w in words)


_COMPANY_NOISE = re.compile(r"\b(s\.?r\.?o\.?|a\.?s\.?|inc\.?|ltd\.?|gmbh|group|czech republic|cz)\b", re.IGNORECASE)


def file_stem(master_path, job: dict[str, Any], role_short: str = "") -> str:
    """<Name>_CV_<Company>_<RoleShort>, where <Name> comes from the master CV's
    file name ("FirstnameLastname_CV_EN.docx" -> "FirstnameLastname")."""
    company = _camel(_COMPANY_NOISE.sub(" ", job.get("company", "")) or job.get("company", "")) or "Company"
    role = _camel(role_short or re.sub(r"\(.*?\)", "", job.get("title", ""))) or "Role"
    return f"{name_prefix(master_path)}_CV_{company}_{role}"


def name_prefix(master_path) -> str:
    """The person's part of the master CV file name, without language or "CV" endings."""
    stem = re.sub(r"[_\- ](EN|CZ|ENG|CS|DE)$", "", Path(master_path).stem, flags=re.IGNORECASE)
    stem = re.sub(r"[_\- ]?(CV|Resume|Curriculum[_\- ]?Vitae)$", "", stem, flags=re.IGNORECASE)
    return re.sub(r"[^A-Za-z0-9]+", "", stem) or "Candidate"


# ── entry point ──────────────────────────────────────────────────────────────
def _drop_last_item(skills: list[dict[str, str]]) -> str:
    """Shorten the longest KEY SKILLS row by its last item; the item that went ('' if nothing can go)."""
    if not skills:
        return ""
    longest = max(skills, key=lambda r: len(r["items"]))
    parts = _items(longest["items"])
    if len(parts) <= 1:
        return ""
    longest["items"] = ", ".join(parts[:-1])
    return parts[-1]


_master_pages: dict[tuple[str, float], int] = {}


def master_pages(master_path) -> int:
    """Pages of the master CV as LibreOffice renders it (0 = unknown). Only when
    the master itself is one page does trimming an adapted CV to one page make sense."""
    master_path = Path(master_path)
    key = (str(master_path), master_path.stat().st_mtime)
    if key not in _master_pages:
        pages = 0
        if pdf.available():
            with tempfile.TemporaryDirectory(prefix="jobhelper-master-") as tmp:   # never write into data/cv
                dup = Path(tmp) / "master.docx"
                shutil.copy2(master_path, dup)
                made = pdf.to_pdf(dup)
                pages = pdf.page_count(made) if made else 0
        _master_pages[key] = pages
    return _master_pages[key]


def tailor(job: dict[str, Any], cv_text: str, master_path) -> str:
    """Create the adapted CV for `job`; returns the file name in TAILORED_CV_DIR."""
    master_path = Path(master_path)
    sec = sections(WordDocument(master_path).body)
    master_profile = text_of(sec["profile"]) if sec["profile"] is not None else ""
    m_rows = [text_of(p) for p in sec["rows"]]
    shape = MasterSkills(m_rows)
    unverified = unverified_terms(cv_text)
    backed = cv_text + "\n" + config.experience_notes()          # everything the person wrote about their own work

    description = (job.get("description") or "").strip()[:POSTING_SHOWN] or "(No description was available.)"
    profile, skills, role_short, feedback = "", [], "", ""
    for _attempt in range(2):
        data = llm.ask_json(PROMPT.format(
            rules=load_rules(cv_text), cv_text=cv_text[:12000],
            master_rows="\n".join(f"- {r}" for r in m_rows) or "(none)",
            title=job["title"], company=job["company"], location=job.get("location", ""),
            description=llm.untrusted("posting", description), feedback=feedback, max_profile=MAX_PROFILE_CHARS,
            min_rows=shape.limits[0], max_rows=shape.limits[1], rows_budget=sum(len(r) for r in m_rows) + 60,
            rows_shape=shape.shape_rule(),
        ), system=SYSTEM, tag="agent3_cv")
        if not isinstance(data, dict):
            raise ValueError("The model's answer was not an adapted CV.")
        profile = clean(str(data.get("profile", "")))
        skills = [row for row in map(shape.row, data.get("skills") or []) if row]
        role_short = str(data.get("role_short", ""))
        problems = content_problems(profile, skills, master_profile, m_rows, unverified, cv_text)
        problems += [f"PROFILE presents '{phrase}' as the candidate's experience, but those are the posting's words: nothing in the "
                     "master CV speaks of it. Leave it out, or name it only as something the candidate is keen to grow into."
                     for phrase in borrowed_claims(profile, description, backed)]
        problems += [f"PROFILE states the figure {f}, which none of the candidate's sources gives. Use only the figures the CV "
                     "or the notes give." for f in profile_problems(profile, job, cv_text)[0]]     # names are only noted, below
        if not problems:
            break
        feedback = "\nYour previous draft was rejected. Fix these problems:\n" + \
                   "\n".join(f"- {p}" for p in problems) + "\n"

    profile, skills = enforce(profile, skills, unverified, cv_text)
    skills = shape.fit(skills)
    figures = profile_problems(profile, job, cv_text)[0]
    pieces = claims.sentences(profile)
    if figures and not any(_ABBREVIATION.search(p) for p in pieces):     # "e.g. 12 years" is not a sentence of its own
        kept = " ".join(s for s in pieces if not profile_problems(s, job, cv_text)[0])
        profile = kept or profile                     # nothing would be left: the profile stays, and the figure is noted
        figures = [] if kept else figures             # an invented figure is cut out with its sentence: a CV is sent as is
    if not profile:
        raise ValueError("The model returned no usable PROFILE.")
    # What is still stated as experience in the posting's words after the retry is not cut out by the app (a phrase
    # such as "version control" can be fair wording for what the CV does show): it is put in front of the person,
    # with any name the CV and the notes do not give.
    # a kept figure first, so the cap of eight hides a figure last; then the posting's words, then names
    left = list(dict.fromkeys([f"the figure {f}" for f in figures] + borrowed_claims(profile, description, backed)
                              + profile_problems(profile, job, cv_text)[1]))
    if left:
        job["cv_check"] = left[:8]
    else:
        job.pop("cv_check", None)
    # Still too long after the retry: drop trailing items from the longest rows.
    budget = estimate_lines(master_profile, m_rows) + SPARE_LINES
    left_out = []                                        # never silent: the person is told what went
    while skills and estimate_lines(profile, [_row_text(r) for r in skills]) > budget:
        dropped = _drop_last_item(skills)
        if not dropped:
            break
        left_out.append(dropped)

    config.ensure_dirs()
    stem = file_stem(master_path, job, role_short)
    out = config.TAILORED_CV_DIR / f"{stem}.docx"
    if out.exists() and job.get("tailored_cv_file") != out.name:
        out = config.TAILORED_CV_DIR / f"{stem}_{store.slugify(job['id'])[-6:]}.docx"
    build_docx(master_path, out, profile, skills if sec["rows"] else [])
    # With LibreOffice the one-page rule is checked on the rendered PDF, not estimated.
    made = pdf.to_pdf(out)
    if made and sec["rows"] and master_pages(master_path) == 1:
        for _ in range(MAX_PAGE_TRIMS):
            dropped = "" if pdf.page_count(made) <= 1 else _drop_last_item(skills)
            if not dropped:
                break
            left_out.append(dropped)
            build_docx(master_path, out, profile, skills)
            made = pdf.to_pdf(out)
            if not made:
                break
    if left_out:
        job["cv_left_out"] = left_out            # shown in the job window: a skill is never cut without a word
    else:
        job.pop("cv_left_out", None)
    problems = verify(master_path, out)
    if problems:
        out.unlink(missing_ok=True)
        out.with_suffix(".pdf").unlink(missing_ok=True)
        raise ValueError("Adapted CV failed its checks: " + "; ".join(problems))
    return out.name
