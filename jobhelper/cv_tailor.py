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
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from . import config, llm, pdf, store

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_P, _R, _T = f"{{{W}}}p", f"{{{W}}}r", f"{{{W}}}t"

# Technologies the master does not contain (instruction, section 4). Used when
# the instruction file is missing or has no "Not in the master" line.
DEFAULT_UNVERIFIED = [
    "Kubernetes", "OpenShift", "Kafka", "A-MQ", "Ansible", "Argo", "GitOps", "Terraform",
    "Helm", "Bash", "PKI", "TLS", "Google Cloud", "GCP", "GitHub Copilot", "AWS", "Jenkins",
]
_INTEREST = re.compile(r"\b(keen|interested|interest in|eager|grow into|looking to learn|"
                       r"motivated to learn|want to learn|excited to learn)\b", re.IGNORECASE)
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️]")

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
    "answer. Reply once, with only the JSON object."
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
CV can back up, keep one sentence about working independently, express anything the candidate
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
    path = config.CV_INSTRUCTION
    if not path.exists():
        return GENERIC_RULES
    text = config.fill_placeholders(path.read_text(encoding="utf-8"), cv_text)
    parts = re.split(r"(?m)^## ", text)
    keep = [p for p in parts if re.match(r"(1|4|5)\.", p)]
    return ("## " + "\n## ".join(k.strip() for k in keep)) if keep else GENERIC_RULES


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


def unknown_skill_terms(items: str, master_text: str) -> list[str]:
    """Technology-looking words in a KEY SKILLS row that the master never
    mentions (names with a capital letter, digit or symbol, e.g. "Kafka", "S3")."""
    low = master_text.lower()
    unknown = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.]*", items):
        token = token.strip(".")
        if len(token) < 2 or token.islower():
            continue                                  # ordinary words: "schema design", "monitoring"
        if token.lower() not in low and token not in unknown:
            unknown.append(token)
    return unknown


def _mentions(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.IGNORECASE))


# ── docx (document.xml) helpers ──────────────────────────────────────────────
def _text(p) -> str:
    return "".join(t.text or "" for t in p.iter(_T))


def _norm(s: str) -> str:
    return re.sub(r"[\s ]+", "", s).upper()


def _set_run_text(run, text: str) -> None:
    ts = run.findall(_T)
    if not ts:
        ts = [etree.SubElement(run, _T)]
    ts[0].text = text
    ts[0].set(XML_SPACE, "preserve")
    for extra in ts[1:]:
        run.remove(extra)


def _sections(body) -> dict[str, Any]:
    """Locate the PROFILE paragraph and the KEY SKILLS rows in the body."""
    paras = [p for p in body if p.tag == _P]
    idx = {(_norm(_text(p))): i for i, p in enumerate(paras)}
    out: dict[str, Any] = {"paras": paras, "profile": None, "rows": []}
    if "PROFILE" in idx:
        for p in paras[idx["PROFILE"] + 1:]:
            if _text(p).strip():
                out["profile"] = p
                break
    if "KEYSKILLS" in idx:
        for p in paras[idx["KEYSKILLS"] + 1:]:
            if _norm(_text(p)) in ("PROJECTS", "WORKEXPERIENCE&PRACTICALTRAINING", "EDUCATION", "LANGUAGES"):
                break
            if _text(p).strip():
                out["rows"].append(p)
    return out


def master_rows(master_path) -> list[str]:
    with zipfile.ZipFile(master_path) as z:
        body = etree.fromstring(z.read("word/document.xml")).find(f"{{{W}}}body")
    return [_text(p) for p in _sections(body)["rows"]]


def build_docx(master_path, out_path, profile: str, skills: list[dict[str, str]]) -> None:
    """Write `out_path`: the master package with only document.xml changed."""
    with zipfile.ZipFile(master_path) as zin:
        root = etree.fromstring(zin.read("word/document.xml"))
        body = root.find(f"{{{W}}}body")
        sec = _sections(body)
        if sec["profile"] is None:
            raise ValueError("The master CV has no PROFILE section.")

        runs = sec["profile"].findall(_R)
        _set_run_text(runs[0], profile)
        for r in runs[1:]:
            _set_run_text(r, "")

        if skills and sec["rows"]:
            template = sec["rows"][0]
            anchor = body.index(template)
            for p in sec["rows"]:
                body.remove(p)
            for n, row in enumerate(skills):
                p = copy.deepcopy(template)
                rr = p.findall(_R)
                _set_run_text(rr[0], f"{row['label']}: ")       # bold label run
                if len(rr) > 1:
                    _set_run_text(rr[1], row["items"])         # regular items run
                    for r in rr[2:]:
                        p.remove(r)
                else:
                    _set_run_text(rr[0], f"{row['label']}: {row['items']}")
                body.insert(anchor + n, p)

        new_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(out_path, "w") as zout:
            for item in zin.infolist():                         # every other file byte-for-byte
                data = new_xml if item.filename == "word/document.xml" else zin.read(item.filename)
                zout.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED)


# ── checks ───────────────────────────────────────────────────────────────────
def _lines(text: str) -> int:
    return max(1, math.ceil(len(text) / CHARS_PER_LINE))


def estimate_lines(profile: str, rows: list[str]) -> int:
    return _lines(profile) + sum(_lines(r) for r in rows)


def _row_text(row: dict[str, str]) -> str:
    return f"{row['label']}: {row['items']}"


def content_problems(profile: str, skills: list[dict[str, str]], master_profile: str,
                     master_rows_: list[str], unverified: list[str], master_text: str = "") -> list[str]:
    """Why this draft can't be used as is (empty list = fine)."""
    problems = []
    rows = [_row_text(r) for r in skills]
    if len(profile) > MAX_PROFILE_CHARS:
        problems.append(f"PROFILE is {len(profile)} characters; the limit is {MAX_PROFILE_CHARS}.")
    if not MIN_ROWS <= len(skills) <= MAX_ROWS:
        problems.append(f"KEY SKILLS has {len(skills)} rows; use {MIN_ROWS}-{MAX_ROWS}.")
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
                problems.append(f"'{term}' (row '{row['label']}') is not in the master CV; remove it from KEY SKILLS.")
    for term in unverified:
        if any(_mentions(r, term) for r in rows):
            problems.append(f"'{term}' is not in the master CV, so it must not be in KEY SKILLS.")
        for sentence in re.split(r"(?<=[.!?])\s+", profile):
            if _mentions(sentence, term) and not _INTEREST.search(sentence):
                problems.append(f"'{term}' is not in the master CV; mention it in PROFILE only as an interest.")
                break
    return problems


def enforce(profile: str, skills: list[dict[str, str]], unverified: list[str],
            master_text: str = "") -> tuple[str, list[dict[str, str]]]:
    """Last line of defence: strip anything the master cannot back up."""
    kept_sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+", profile):
        if any(_mentions(sentence, t) for t in unverified) and not _INTEREST.search(sentence):
            continue
        kept_sentences.append(sentence)
    out_rows = []
    for row in skills:
        items = [i.strip() for i in re.split(r",(?![^()]*\))", row["items"]) if i.strip()]
        items = [i for i in items if not any(_mentions(i, t) for t in unverified)]
        if master_text:
            items = [i for i in items if not unknown_skill_terms(i, master_text)]
        if items:
            out_rows.append({"label": row["label"], "items": ", ".join(items)})
    return " ".join(kept_sentences), out_rows


def clean(text: str) -> str:
    """En dash instead of em dash, no emojis, single spaces."""
    text = text.replace(" — ", " – ").replace("—", "–")
    text = _EMOJI.sub("", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def verify(master_path, out_path) -> list[str]:
    """Checks 2-4 of the instruction on the finished file."""
    problems = []
    with zipfile.ZipFile(master_path) as zm, zipfile.ZipFile(out_path) as zo:
        for name in zm.namelist():
            if name != "word/document.xml" and zm.read(name) != zo.read(name):
                problems.append(f"{name} differs from the master.")
        mb = etree.fromstring(zm.read("word/document.xml")).find(f"{{{W}}}body")
        ob = etree.fromstring(zo.read("word/document.xml")).find(f"{{{W}}}body")
    ms, os_ = _sections(mb), _sections(ob)

    def locked(sec):
        skip = {id(sec["profile"])} | {id(p) for p in sec["rows"]}
        return [etree.tostring(p) for p in sec["paras"] if id(p) not in skip]

    if locked(ms) != locked(os_):
        problems.append("A locked paragraph (header, projects, experience, education, languages) changed.")
    full = "\n".join(_text(p) for p in os_["paras"])
    if "—" in full:
        problems.append("The CV contains an em dash.")
    if _EMOJI.search(full):
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
def _drop_last_item(skills: list[dict[str, str]]) -> bool:
    """Shorten the longest KEY SKILLS row by its last item. False if nothing can go."""
    if not skills:
        return False
    longest = max(skills, key=lambda r: len(r["items"]))
    parts = [i.strip() for i in re.split(r",(?![^()]*\))", longest["items"])]
    if len(parts) <= 1:
        return False
    longest["items"] = ", ".join(parts[:-1])
    return True


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
    with zipfile.ZipFile(master_path) as z:
        body = etree.fromstring(z.read("word/document.xml")).find(f"{{{W}}}body")
    sec = _sections(body)
    master_profile = _text(sec["profile"]) if sec["profile"] is not None else ""
    m_rows = [_text(p) for p in sec["rows"]]
    unverified = unverified_terms(cv_text)

    description = (job.get("description") or "").strip()[:5000] or "(No description was available.)"
    profile, skills, role_short, feedback = "", [], "", ""
    for _attempt in range(2):
        data = llm.ask_json(PROMPT.format(
            rules=load_rules(cv_text), cv_text=cv_text[:12000],
            master_rows="\n".join(f"- {r}" for r in m_rows) or "(none)",
            title=job["title"], company=job["company"], location=job.get("location", ""),
            description=description, feedback=feedback, max_profile=MAX_PROFILE_CHARS,
            min_rows=MIN_ROWS, max_rows=MAX_ROWS, rows_budget=sum(len(r) for r in m_rows) + 60,
        ), system=SYSTEM, tag="agent3_cv")
        profile = clean(str(data.get("profile", "")))
        skills = [{"label": clean(str(r.get("label", ""))).rstrip(":"),
                   "items": clean(str(r.get("items", ""))).rstrip(".")}
                  for r in (data.get("skills") or []) if r.get("label") and r.get("items")]
        role_short = str(data.get("role_short", ""))
        problems = content_problems(profile, skills, master_profile, m_rows, unverified, cv_text)
        if not problems:
            break
        feedback = "\nYour previous draft was rejected. Fix these problems:\n" + \
                   "\n".join(f"- {p}" for p in problems) + "\n"

    profile, skills = enforce(profile, skills, unverified, cv_text)
    if not profile:
        raise ValueError("The model returned no usable PROFILE.")
    # Still too long after the retry: drop trailing items from the longest rows.
    budget = estimate_lines(master_profile, m_rows) + SPARE_LINES
    while skills and estimate_lines(profile, [_row_text(r) for r in skills]) > budget:
        if not _drop_last_item(skills):
            break

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
            if pdf.page_count(made) <= 1 or not _drop_last_item(skills):
                break
            build_docx(master_path, out, profile, skills)
            made = pdf.to_pdf(out)
            if not made:
                break
    problems = verify(master_path, out)
    if problems:
        out.unlink(missing_ok=True)
        out.with_suffix(".pdf").unlink(missing_ok=True)
        raise ValueError("Adapted CV failed its checks: " + "; ".join(problems))
    return out.name
