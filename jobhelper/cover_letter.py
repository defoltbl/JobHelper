"""Write a cover letter for one job by filling the letter template (.docx).

Follows data/cover_letter_instruction.md: the head block, fonts, spacing and
page setup of data/cover_letter_template.docx stay exactly as they are; only the
title line, the date and the five body paragraphs get new text. We edit
`word/document.xml` inside the template package and copy every other file
unchanged.

The text must sell strengths only: no admission of a gap, and a technology the
master CV cannot back up may be named as the employer's platform or as something
the candidate wants to work with, never as something already done.
"""
from __future__ import annotations

import re
import zipfile
from datetime import date
from typing import Any

from lxml import etree

from . import config, cv_tailor, llm, store
from .cv_tailor import W, _P, _R, _T, _mentions, _set_run_text, _text, clean

BODY_PARAGRAPHS = 5
MIN_WORDS, MAX_WORDS = 320, 410        # instruction: about 330-400 words
MAX_CHARS = 2550                       # keeps the letter on one page (example: 2240)

# Check 3 of the instruction: phrases that admit a gap.
_GAP = re.compile(
    r"\b(not yet|have not|haven't|do not have|don't have|lack(s|ing)?|gaps?|honest(ly)?|limited|"
    r"unfamiliar|despite|although|no experience|little experience|never (used|worked))\b", re.IGNORECASE)
# A forward-looking wish (rule 1, option 2).
_WISH = re.compile(r"\b(would like|would love|keen|look(ing)? forward|want to|eager|hope to|"
                   r"excited to|wish to|aim to|motivated to)\b", re.IGNORECASE)
# Wording that claims hands-on experience.
_CLAIM = re.compile(
    r"\b(I|I've|we)\s+(have\s+|also\s+|regularly\s+|currently\s+)*(work(ed)?|use[ds]?|built|build|"
    r"deploy(ed)?|ran|run|administer(ed)?|manage[ds]?|configure[ds]?|operate[ds]?|maintain(ed)?|"
    r"wrote|written|set up|automate[ds]?|implemented?|develop(ed)?)\b|"
    r"\b(experience(d)? (with|in)|hands-on|proficient|skilled|familiar with|expertise|background in|"
    r"knowledge of|my work with)\b", re.IGNORECASE)

SYSTEM = (
    "You write one candidate's cover letter for a job posting. You sell strengths "
    "only and never mention anything the candidate has not done. You never claim a "
    "technology that is not in the master CV. Write in the first person (I, my): the "
    "candidate is the author, so never refer to them by name or as he/she. Use an en dash (–) with spaces, never "
    "an em dash, and no emojis. You have no tools and no file access here: another "
    "program places your text into the .docx. Reply once, with only the JSON object."
)

PROMPT = """Write the text of a cover letter for the job posting below. The file handling is
done elsewhere; you only supply the wording.

Rules from the candidate (follow them exactly):
---
{rules}
---

Master CV (the only source of truth for experience):
---
{cv_text}
---
{adapted}
Job posting:
- Title: {title}
- Company: {company}
- Location: {location}
- Description: {description}
{feedback}
Return JSON with exactly these keys:
{{
  "title_line": "<the role applied for, without (m/f/d) or location>",
  "paragraphs": ["<hook>", "<strongest evidence>", "<second theme>", "<learning and fit>", "<close>"],
  "role_short": "<the role in 1-3 words, e.g. Middleware Admin>"
}}
Exactly {n} paragraphs, {min_words}-{max_words} words in total. No salutation, no date, no
"Yours sincerely" and no name: those are already in the template."""

GENERIC_RULES = """Sell strengths only. Never mention anything the candidate has not done: no "not
yet", "although", "limited experience", "I lack". A requirement the candidate cannot back up is
left out, or turned into a forward-looking wish ("I would like to bring the same drive to ..."),
or answered with the nearest real evidence. Only technologies in the master CV may appear as
experience.
Five paragraphs, about 330-400 words: (1) hook - role, company, why the work attracts;
(2) strongest evidence for the core requirement - one real project with concrete facts;
(3) a second theme from the posting with one short true story or result; (4) learning and fit,
then the forward-looking wish; (5) close - only the facts listed under "Facts about the candidate"
(location, right to work, start date) and an invitation to talk; a fact that is not stated is left out.
Vary sentence openings, one concrete fact per paragraph, no filler openers, no hedging."""


def load_rules(cv_text: str = "") -> str:
    """Sections 1, 4, 5 and 7 of the instruction (content rules + worked example).
    Without a file the built-in general rules are used. {{placeholders}} in the
    file are filled with the person's own facts (see config.fill_placeholders)."""
    path = config.LETTER_INSTRUCTION
    if not path.exists():
        return GENERIC_RULES
    parts = re.split(r"(?m)^## ", config.fill_placeholders(path.read_text(encoding="utf-8"), cv_text))
    keep = [p for p in parts if re.match(r"(1|4|5|7)\.", p)]
    return ("## " + "\n## ".join(k.strip() for k in keep)) if keep else GENERIC_RULES


def unverified_terms(master_text: str) -> list[str]:
    """The CV's "never claim" list plus the letter instruction's "Anything else (...)" list."""
    terms = cv_tailor.unverified_terms(master_text)
    path = config.LETTER_INSTRUCTION
    if path.exists():
        m = re.search(r"Anything else \(([^)]*)\)", path.read_text(encoding="utf-8"))
        if m:
            low = master_text.lower()
            for raw in m.group(1).split(","):
                t = re.sub(r"\band so on\b", "", raw).strip()
                if t and t not in terms and t.lower() not in low:
                    terms.append(t)
    return terms


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


_FIRST_PERSON = re.compile(r"\b(?:I|my|me|I'm|I've)\b")


def candidate_first_name(cv_text: str) -> str:
    """First word of the CV's first line ("Jane Doe" -> "Jane")."""
    for line in (cv_text or "").splitlines():
        words = re.findall(r"[^\W\d_]+", line)
        if words:
            return words[0]
    return ""


def third_person(paragraphs: list[str], first_name: str = "") -> bool:
    """True if the letter talks about the candidate instead of as the candidate."""
    text = " ".join(paragraphs)
    if first_name and re.search(rf"\b{re.escape(first_name)}\b", text):
        return True
    return bool(text.strip()) and not _FIRST_PERSON.search(text)


def content_problems(paragraphs: list[str], unverified: list[str], first_name: str = "") -> list[str]:
    """Why this draft can't be used as is (empty list = fine)."""
    problems = []
    if third_person(paragraphs, first_name):
        problems.append("The letter is written about the candidate in the third person. Rewrite it in the "
                        "first person (I, my); never use the candidate's name or he/his in the body.")
    if len(paragraphs) != BODY_PARAGRAPHS:
        problems.append(f"The letter has {len(paragraphs)} paragraphs; it must have exactly {BODY_PARAGRAPHS}.")
    words = sum(len(p.split()) for p in paragraphs)
    chars = sum(len(p) for p in paragraphs)
    if words < MIN_WORDS:
        problems.append(f"Too short: {words} words; write {MIN_WORDS}-{MAX_WORDS}.")
    if words > MAX_WORDS or chars > MAX_CHARS:
        problems.append(f"Too long for one page: {words} words; write {MIN_WORDS}-{MAX_WORDS}.")
    for n, para in enumerate(paragraphs, 1):
        for s in _sentences(para):
            gap = _GAP.search(s)
            if gap:
                problems.append(f"Paragraph {n} admits a gap (\"{gap.group(0)}\"): \"{s[:90]}\". "
                                "Remove it or state a forward-looking wish instead.")
            for term in unverified:
                if _mentions(s, term) and _CLAIM.search(s) and not _WISH.search(s):
                    problems.append(f"Paragraph {n} presents '{term}' as experience, but it is not in the "
                                    "master CV. Name it only as something the candidate wants to work with.")
                    break
    return problems


def enforce(paragraphs: list[str], unverified: list[str]) -> list[str]:
    """Last line of defence: drop sentences that admit a gap or claim unbacked experience."""
    out = []
    for para in paragraphs:
        kept = []
        for s in _sentences(para):
            if _GAP.search(s):
                continue
            if any(_mentions(s, t) for t in unverified) and _CLAIM.search(s) and not _WISH.search(s):
                continue
            kept.append(s)
        out.append(" ".join(kept))
    return out


# ── docx ─────────────────────────────────────────────────────────────────────
def _slots(body) -> dict[str, Any]:
    """Paragraphs of the template by role: name, title, 2 contact lines, date,
    salutation, the body paragraphs, closing, signature."""
    filled = [p for p in body if p.tag == _P and _text(p).strip()]
    if len(filled) < 9:      # name, title, 2 contact lines, date, salutation, body, closing, signature
        raise ValueError("The letter template does not have the expected structure.")
    return {"title": filled[1], "date": filled[4], "body": filled[6:-2]}


def _set_para(p, text: str) -> None:
    runs = p.findall(_R)
    _set_run_text(runs[0], text)
    for r in runs[1:]:
        _set_run_text(r, "")


def letter_date(d: date | None = None) -> str:
    d = d or date.today()
    return f"{d.day} {d:%B %Y}"                      # 6 October 2026


def build_docx(template_path, out_path, title_line: str, paragraphs: list[str], when: date | None = None,
               date_text: str = "") -> None:
    with zipfile.ZipFile(template_path) as zin:
        root = etree.fromstring(zin.read("word/document.xml"))
        slots = _slots(root.find(f"{{{W}}}body"))
        if len(slots["body"]) != len(paragraphs):
            raise ValueError(f"The template has {len(slots['body'])} body paragraphs, the letter {len(paragraphs)}.")
        _set_para(slots["title"], title_line)
        _set_para(slots["date"], date_text or letter_date(when))
        for p, text in zip(slots["body"], paragraphs):
            _set_para(p, text)
        new_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(out_path, "w") as zout:
            for item in zin.infolist():
                data = new_xml if item.filename == "word/document.xml" else zin.read(item.filename)
                zout.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED)


def read_letter(path) -> dict[str, Any]:
    """The editable parts of a letter this app built: title line, date, body paragraphs."""
    with zipfile.ZipFile(path) as z:
        slots = _slots(etree.fromstring(z.read("word/document.xml")).find(f"{{{W}}}body"))
    return {"title_line": _text(slots["title"]), "date_text": _text(slots["date"]),
            "paragraphs": [_text(p) for p in slots["body"]]}


REWRITE_PROMPT = """Rewrite ONE paragraph of the candidate's cover letter. Everything else stays as it is.

Rules from the candidate (follow them exactly):
---
{rules}
---

Master CV (the only source of truth for experience):
---
{cv_text}
---

Job posting:
- Title: {title}
- Company: {company}
- Description: {description}

The letter now (paragraphs numbered):
{letter}

Rewrite paragraph {number}. Keep its job in the letter and roughly its length ({words} words, at most {max_words}).
{hint}{feedback}
Return JSON only: {{"paragraph": "<the new paragraph {number}>"}}"""


def rewrite_paragraph(job: dict[str, Any], cv_text: str, paragraphs: list[str], index: int, hint: str = "") -> str:
    """A new version of one paragraph (one model call, one retry if it breaks a rule).
    Nothing is saved here: the caller shows it to the user first."""
    if not 0 <= index < len(paragraphs):
        raise ValueError("That paragraph does not exist.")
    unverified, first_name = unverified_terms(cv_text), candidate_first_name(cv_text)
    letter = "\n".join(f"{n}. {p}" for n, p in enumerate(paragraphs, 1))
    words = len(paragraphs[index].split())
    hint_line = f"What the candidate wants changed: {hint.strip()[:300]}\n" if hint.strip() else ""
    feedback, text = "", ""
    for _attempt in range(2):
        data = llm.ask_json(REWRITE_PROMPT.format(
            rules=load_rules(cv_text) + "\n\nFacts about the candidate (use only these for location, right to work and start date):\n" + config.facts_block(cv_text), cv_text=cv_text[:12000], title=job.get("title", ""), company=job.get("company", ""),
            description=(job.get("description") or "").strip()[:3000] or "(No description was available.)",
            letter=letter, number=index + 1, words=words, max_words=max(words + 25, 60),
            hint=hint_line, feedback=feedback), system=SYSTEM, tag="agent3_letters")
        text = clean(str((data or {}).get("paragraph", ""))).strip() if isinstance(data, dict) else ""
        problems = paragraph_problems(text, unverified, first_name)
        if not problems:
            return text
        feedback = "\nYour previous version was rejected. Fix this:\n" + "\n".join(f"- {p}" for p in problems) + "\n"
    raise ValueError(problems[0] if text else "The model returned no paragraph.")


def paragraph_problems(text: str, unverified: list[str], first_name: str = "") -> list[str]:
    """The letter rules, applied to a single paragraph."""
    if not text.strip():
        return ["The paragraph is empty."]
    problems = []
    if first_name and re.search(rf"\b{re.escape(first_name)}\b", text):
        problems.append("Write in the first person (I, my); never use the candidate's name.")
    for s in _sentences(text):
        gap = _GAP.search(s)
        if gap:
            problems.append(f"It admits a gap (\"{gap.group(0)}\"). Remove it or state a forward-looking wish instead.")
        for term in unverified:
            if _mentions(s, term) and _CLAIM.search(s) and not _WISH.search(s):
                problems.append(f"It presents '{term}' as experience, but it is not in the master CV.")
                break
    return problems


def letter_warnings(paragraphs: list[str], cv_text: str) -> list[str]:
    """What a hand-edited letter no longer follows (shown to the user, never blocking)."""
    out = []
    words = sum(len(p.split()) for p in paragraphs)
    if words < MIN_WORDS:
        out.append(f"The letter is short: {words} words (the usual range is {MIN_WORDS}-{MAX_WORDS}).")
    if words > MAX_WORDS:
        out.append(f"The letter is long: {words} words (the usual range is {MIN_WORDS}-{MAX_WORDS}); it may not fit on one page.")
    unverified, first_name = unverified_terms(cv_text), candidate_first_name(cv_text)
    for n, p in enumerate(paragraphs, 1):
        out += [f"Paragraph {n}: {x}" for x in paragraph_problems(p, unverified, first_name)]
    return out


def _formatting_only(xml: bytes) -> bytes:
    """document.xml with every piece of text removed (check 2 of the instruction)."""
    root = etree.fromstring(xml)
    for t in root.iter(_T):
        t.text = ""
        t.attrib.pop(cv_tailor.XML_SPACE, None)      # whitespace handling of the text, not formatting
    return etree.tostring(root)


def verify(template_path, out_path, unverified: list[str] | None = None) -> list[str]:
    problems = []
    with zipfile.ZipFile(template_path) as zt, zipfile.ZipFile(out_path) as zo:
        for name in zt.namelist():
            if name != "word/document.xml" and zt.read(name) != zo.read(name):
                problems.append(f"{name} differs from the template.")
        if _formatting_only(zt.read("word/document.xml")) != _formatting_only(zo.read("word/document.xml")):
            problems.append("The formatting differs from the template.")
        body = etree.fromstring(zo.read("word/document.xml")).find(f"{{{W}}}body")
    paragraphs = [_text(p) for p in _slots(body)["body"]]
    full = "\n".join(_text(p) for p in body if p.tag == _P)
    if "—" in full:
        problems.append("The letter contains an em dash.")
    if cv_tailor._EMOJI.search(full):
        problems.append("The letter contains an emoji.")
    for para in paragraphs:
        gap = _GAP.search(para)
        if gap:
            problems.append(f"The letter admits a gap (\"{gap.group(0)}\").")
    return problems


# ── file name ────────────────────────────────────────────────────────────────
def file_stem(master_path, job: dict[str, Any], role_short: str = "") -> str:
    """<Name>_CoverLetter_<Company>_<RoleShort>, matching the adapted CV's name."""
    cv_stem = cv_tailor.file_stem(master_path, job, role_short)       # ..._CV_<Company>_<Role>
    m = re.match(r"(.+?)_CV_(.+)\.docx$", job.get("tailored_cv_file", "") or "")
    if m:
        return f"{m.group(1)}_CoverLetter_{m.group(2)}"
    return cv_stem.replace("_CV_", "_CoverLetter_", 1)


def _adapted_cv_text(job: dict[str, Any]) -> str:
    name = job.get("tailored_cv_file", "")
    path = config.TAILORED_CV_DIR / name if name else None
    if not path or path.suffix.lower() != ".docx" or not path.exists():
        return ""
    with zipfile.ZipFile(path) as z:
        body = etree.fromstring(z.read("word/document.xml")).find(f"{{{W}}}body")
    sec = cv_tailor._sections(body)
    lines = ([_text(sec["profile"])] if sec["profile"] is not None else []) + [_text(p) for p in sec["rows"]]
    return "\n".join(lines)


# ── entry point ──────────────────────────────────────────────────────────────
def write(job: dict[str, Any], cv_text: str, master_path=None) -> str:
    """Create the cover letter for `job`; returns the file name in LETTERS_DIR."""
    template = config.LETTER_TEMPLATE
    unverified = unverified_terms(cv_text)
    first_name = candidate_first_name(cv_text)
    adapted = _adapted_cv_text(job)
    adapted_block = (f"\nPROFILE and KEY SKILLS of the CV adapted for this same application "
                     f"(stay consistent with it):\n---\n{adapted}\n---\n") if adapted else ""
    description = (job.get("description") or "").strip()[:5000] or "(No description was available.)"

    title_line, paragraphs, role_short, feedback = "", [], "", ""
    for _attempt in range(2):
        data = llm.ask_json(PROMPT.format(
            rules=load_rules(cv_text) + "\n\nFacts about the candidate (use only these for location, right to work and start date):\n" + config.facts_block(cv_text), cv_text=cv_text[:12000], adapted=adapted_block,
            title=job["title"], company=job["company"], location=job.get("location", ""),
            description=description, feedback=feedback, n=BODY_PARAGRAPHS,
            min_words=MIN_WORDS + 10, max_words=MAX_WORDS - 10,
        ), system=SYSTEM, tag="agent3_letters")
        paragraphs = [clean(str(p)) for p in (data.get("paragraphs") or []) if str(p).strip()]
        title_line = clean(str(data.get("title_line", "")))
        role_short = str(data.get("role_short", ""))
        problems = content_problems(paragraphs, unverified, first_name)
        if not problems:
            break
        feedback = "\nYour previous draft was rejected. Fix these problems:\n" + \
                   "\n".join(f"- {p}" for p in problems) + "\n"

    if len(paragraphs) != BODY_PARAGRAPHS:
        raise ValueError(f"The model returned {len(paragraphs)} paragraphs instead of {BODY_PARAGRAPHS}.")
    if third_person(paragraphs, first_name):
        raise ValueError("The letter was written in the third person twice; nothing was saved.")
    paragraphs = enforce(paragraphs, unverified)
    if any(not p for p in paragraphs):
        raise ValueError("A paragraph was empty after removing unbacked claims.")
    if not title_line:
        title_line = re.sub(r"\s*\(.*?\)", "", job["title"]).strip()

    config.ensure_dirs()
    stem = file_stem(master_path or "Candidate_CV_EN.docx", job, role_short)
    out = config.LETTERS_DIR / f"{stem}.docx"
    if out.exists() and job.get("cover_letter_file") != out.name:
        out = config.LETTERS_DIR / f"{stem}_{store.slugify(job['id'])[-6:]}.docx"
    build_docx(template, out, title_line, paragraphs)
    problems = verify(template, out, unverified)
    if problems:
        out.unlink(missing_ok=True)
        raise ValueError("Cover letter failed its checks: " + "; ".join(problems))
    return out.name
