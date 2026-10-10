"""Your own details, for filling in application forms.

- the plain ones: name, contacts, address, links, notice period;
- the jobs you have had (any number, each may be marked as a current one) and your degrees;
- the salary you ask for, as a figure with its currency;
- files a form may ask for besides the CV: certificates, diplomas, references.

They are typed once in the assistant's window and kept encrypted in data/my_details.json.
Nothing here is guessed: what is read from the CV is only offered and is saved when you save
the page. What a form gets is exactly what is written here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import config, llm, salary, vault

# (key, what the window calls it, the most characters)
FIELDS = (("first_name", "First name", 60), ("last_name", "Last name", 60), ("email", "Email", 120),
          ("phone", "Phone", 30), ("street", "Street and number", 120), ("city", "City", 80),
          ("postcode", "Postcode", 16), ("country", "Country", 60), ("linkedin", "LinkedIn", 200),
          ("github", "GitHub", 200), ("website", "Website or portfolio", 200), ("notice_period", "Notice period", 60))
KEYS = tuple(key for key, _label, _most in FIELDS)
LABELS = {key: label for key, label, _most in FIELDS}
LINKS = {"linkedin": "linkedin.com", "github": "github.com", "website": ""}

# the lists: one row per job, one per degree. `start` and `end` are a year, or a month and a year.
# A job also has where it was and what you did there: forms ask for both inside each job ("Location", "Role description").
ROWS = {"experience": (("employer", "Employer", 100), ("title", "Job title", 100), ("start", "From", 10), ("end", "To", 10),
                       ("location", "Where it was", 80), ("description", "What you did there", 2000)),
        "education": (("school", "University or school", 120), ("degree", "Degree", 120), ("field", "Field of study", 120),
                      ("start", "From", 10), ("end", "To", 10)),
        "languages": (("language", "Language", 40), ("level", "Level", 20))}
NEEDED = {"experience": ("employer", "title"), "education": ("school",), "languages": ("language",)}
# How well you speak a language, in the words forms use. What you choose here is what forms are told: it is your own statement.
LEVELS = ("Native", "Fluent", "Advanced", "Intermediate", "Basic")
LONG = ("description",)         # row fields that hold several lines
WORD = {"experience": "job", "education": "degree", "languages": "language"}
MAX_ROWS, MAX_FILES, MAX_FILE_LABEL = 15, 20, 60
PERIODS = ("month", "year")
MAX_SALARY = 100_000_000

_EMAIL = re.compile(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+")
_LINK = re.compile(r"https?://[^\s/.]+(?:\.[^\s/.]+)+(?:/\S*)?", re.IGNORECASE)
_WORDS = re.compile(r"[^\W\d_]+(?:[ '.\-]+[^\W\d_]+)*\.?")
_WHEN = re.compile(r"(?:(?:0?[1-9]|1[0-2])[./\-])?(?:19|20)\d{2}")


def path():
    return config.DATA_DIR / "my_details.json"


def empty() -> dict[str, Any]:
    return {**{key: "" for key in KEYS}, "experience": [], "education": [], "languages": [], "files": [],
            "salary_amount": 0, "salary_currency": "CZK", "salary_period": "month"}


def load() -> dict[str, Any]:
    """What was saved, with every key there ('' or an empty list = not given)."""
    out = empty()
    try:
        if path().exists():
            kept = json.loads(vault.read_text(path()))
            clean, problem = check(kept)
            if not problem:
                out = clean
            elif isinstance(kept, dict):
                # One saved value no longer passes a check (a rule that became stricter, a file edited by hand): that
                # one is left out and everything else is kept. Reading it all as empty would show a blank page, and the
                # next Save would then write the blank page over what was there.
                for key in list(out):
                    part, wrong = check({key: kept.get(key)} if key not in ("salary_amount", "salary_currency", "salary_period")
                                        else {k: kept.get(k) for k in ("salary_amount", "salary_currency", "salary_period")})
                    if not wrong:
                        out[key] = part[key]
                for name in ROWS:                   # a list with one bad row keeps its good rows
                    if not out[name] and isinstance(kept.get(name), list):
                        out[name] = [rows[0] for rows, wrong in (_rows(name, [row]) for row in kept[name][:MAX_ROWS]) if not wrong and rows]
    except vault.VaultError:
        raise
    except Exception:  # noqa: BLE001 - an unreadable file is the same as none: the page shows empty fields
        pass
    return out


def any_given(d: dict[str, Any]) -> bool:
    """Is there anything to fill a form with?"""
    return any(d.get(key) for key in KEYS) or bool(d.get("experience") or d.get("education") or d.get("languages"))


def check(values: Any) -> tuple[dict[str, Any], dict[str, str]]:
    """(clean values, {}) or ({}, {"field": where, "msg": what is wrong}). `field` is a key
    ("email"), a place in a list ("experience.1.title"), "salary" or "files.0". The window
    checks the same things as you type; this is the last word."""
    if not isinstance(values, dict):
        return {}, {"field": "", "msg": "The details did not arrive as fields. Close the page and open it again."}
    clean = empty()
    for key, label, most in FIELDS:
        raw = values.get(key)
        if raw is not None and not isinstance(raw, str):
            return {}, {"field": key, "msg": f"“{label}” must be text."}
        value = " ".join(str(raw or "").split())
        if len(value) > most:
            return {}, {"field": key, "msg": f"“{label}” is {len(value)} characters long; the most is {most}."}
        problem = _problem(key, label, value) if value else ""
        if problem:
            return {}, {"field": key, "msg": problem}
        clean[key] = _link(value) if key in LINKS and value else value
    for name in ROWS:
        rows, problem = _rows(name, values.get(name))
        if problem:
            return {}, problem
        clean[name] = rows
    files, problem = _files(values.get("files"))
    if problem:
        return {}, problem
    clean["files"] = files
    pay, problem = _salary(values)
    if problem:
        return {}, problem
    clean.update(pay)
    return clean, {}


def _rows(name: str, raw: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if raw is None:
        return [], {}
    if not isinstance(raw, (list, tuple)):
        return [], {"field": name, "msg": f"The list of {WORD[name]}s did not arrive as a list. Close the page and open it again."}
    out = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            return [], {"field": f"{name}.{i}", "msg": f"Line {i + 1} of the {WORD[name]}s is not a row of fields."}
        clean: dict[str, Any] = {}
        for key, label, most in ROWS[name]:
            if key in LONG:                         # several lines: each tidied, the line breaks kept
                value = "\n".join(line for line in (" ".join(part.split()) for part in str(row.get(key) or "").splitlines()) if line)
            else:
                value = " ".join(str(row.get(key) or "").split())
            if len(value) > most:
                return [], {"field": f"{name}.{i}.{key}", "msg": f"“{label}” is {len(value)} characters long; the most is {most}."}
            if key in ("start", "end") and value and not _WHEN.fullmatch(value):
                return [], {"field": f"{name}.{i}.{key}", "msg": "Write a year, or a month and a year: 2023 or 03/2023."}
            if key == "level" and value:
                known = next((level for level in LEVELS if level.lower() == value.lower()), "")
                if not known:
                    return [], {"field": f"{name}.{i}.{key}", "msg": "Write one of: " + ", ".join(LEVELS) + "."}
                value = known
            if key == "language" and value and not re.fullmatch(r"[^\W\d_]+(?:[ '\-][^\W\d_]+)*", value):
                return [], {"field": f"{name}.{i}.{key}", "msg": "Write the language's name in letters, for example English."}
            clean[key] = value
        if name == "experience":
            clean["current"] = bool(row.get("current"))
            if clean["current"] and clean["end"]:
                return [], {"field": f"{name}.{i}.end", "msg": "A current job has no end date. Clear “To”, or turn off “current”."}
        if not any(clean.get(key) for key, _label, _most in ROWS[name]):
            continue                                # a line left empty is not a job
        for key in NEEDED[name]:
            if not clean[key]:
                label = next(lab for k, lab, _most in ROWS[name] if k == key)
                return [], {"field": f"{name}.{i}.{key}", "msg": f"“{label}” is missing in this {WORD[name]}. Fill it in, or remove the line."}
        if name == "languages" and any(clean["language"].lower() == other["language"].lower() for other in out):
            return [], {"field": f"{name}.{i}.language", "msg": f"{clean['language']} is in the list twice. Remove one line."}
        if clean.get("start") and clean.get("end") and _year(clean["end"]) < _year(clean["start"]):
            return [], {"field": f"{name}.{i}.end", "msg": "“To” is earlier than “From”."}
        out.append(clean)
    if len(out) > MAX_ROWS:
        return [], {"field": name, "msg": f"That is {len(out)} {WORD[name]}s; the most is {MAX_ROWS}. Remove the oldest ones."}
    return out, {}


def _year(when: str) -> tuple[int, int]:
    parts = re.split(r"[./\-]", when)
    return (int(parts[-1]), int(parts[0]) if len(parts) == 2 else 0)


def _files(raw: Any) -> tuple[list[dict[str, str]], dict[str, str]]:
    if raw is None:
        return [], {}
    if not isinstance(raw, (list, tuple)):
        return [], {"field": "files", "msg": "The list of files did not arrive as a list. Close the page and open it again."}
    out, seen = [], set()
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            return [], {"field": f"files.{i}", "msg": f"Line {i + 1} of the files is not a file."}
        where = str(row.get("path") or "").strip()
        label = " ".join(str(row.get("label") or "").split())
        if not where and not label:
            continue
        if not where or not Path(where).is_absolute() or not Path(where).is_file():
            return [], {"field": f"files.{i}", "msg": f"The file “{Path(where).name or label}” is not there any more. Choose it again, or remove the line."}
        if len(label) > MAX_FILE_LABEL:
            return [], {"field": f"files.{i}", "msg": f"The name of a file is {len(label)} characters long; the most is {MAX_FILE_LABEL}."}
        if where in seen:
            return [], {"field": f"files.{i}", "msg": f"“{Path(where).name}” is in the list twice. Remove one of them."}
        seen.add(where)
        out.append({"label": label or Path(where).stem, "path": where})
    if len(out) > MAX_FILES:
        return [], {"field": "files", "msg": f"That is {len(out)} files; the most is {MAX_FILES}."}
    return out, {}


def _salary(values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    raw = values.get("salary_amount", 0)
    try:
        amount = int(str(raw if raw not in (None, "") else 0).replace(" ", "").replace(" ", ""))
    except ValueError:
        return {}, {"field": "salary", "msg": "The salary must be a whole number, like 60000."}
    if not 0 <= amount <= MAX_SALARY:
        return {}, {"field": "salary", "msg": f"The salary must be between 0 (not given) and {MAX_SALARY:,}.".replace(",", " ")}
    currency = str(values.get("salary_currency") or "CZK").strip().upper()
    if currency not in salary.CURRENCIES:
        return {}, {"field": "salary", "msg": f"“{currency}” is not a currency the app knows. Choose one from the list."}
    period = str(values.get("salary_period") or "month").strip().lower()
    if period not in PERIODS:
        return {}, {"field": "salary", "msg": "A salary is per month or per year."}
    return {"salary_amount": amount, "salary_currency": currency, "salary_period": period}, {}


def _link(value: str) -> str:
    return value if re.match(r"https?://", value, re.IGNORECASE) else "https://" + value


def _problem(key: str, label: str, value: str) -> str:
    if key in ("first_name", "last_name", "city", "country") and not _WORDS.fullmatch(value):
        return f"“{label}” must be written in letters."
    if key == "email" and not _EMAIL.fullmatch(value):
        return "That does not look like an email address. It needs a name, an @ and a domain, like name@example.com."
    if key == "phone":
        digits = re.sub(r"\D", "", value)
        if not re.fullmatch(r"\+?[\d ()./\-]+", value) or value.count("+") > 1:
            return "A phone number is made of digits, spaces and + at the start, like +420 123 456 789."
        if not 6 <= len(digits) <= 15:
            return f"A phone number has 6 to 15 digits; this one has {len(digits)}."
    if key == "postcode" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 \-]*", value):
        return "A postcode is made of letters, digits, spaces and dashes."
    if key in LINKS:
        link = _link(value)
        if not _LINK.fullmatch(link):
            return f"“{label}” must be a web address with no spaces, like https://example.com/you."
        if LINKS[key] and LINKS[key] not in link.lower():
            return f"“{label}” must be an address at {LINKS[key]}."
    return ""


def save(values: Any) -> dict[str, Any]:
    clean, problem = check(values)
    if problem:
        return {"ok": False, **problem}
    config.ensure_dirs()
    vault.write_text(path(), json.dumps(clean, ensure_ascii=False, indent=2))
    return {"ok": True, "details": clean}


# ── what a form is given ────────────────────────────────────────────────────
def full_name(d: dict[str, Any]) -> str:
    return " ".join(part for part in (d.get("first_name", ""), d.get("last_name", "")) if part)


def jobs(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Your jobs in the order forms ask for them: the current ones first, then as you listed them."""
    rows = list(d.get("experience") or [])
    return [r for r in rows if r.get("current")] + [r for r in rows if not r.get("current")]


def degrees(d: dict[str, Any]) -> list[dict[str, Any]]:
    return list(d.get("education") or [])


def languages(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Your languages in the order you listed them: {language, level}."""
    return list(d.get("languages") or [])


def salary_text(d: dict[str, Any]) -> str:
    """"60 000 CZK gross per month", or '' when no figure is given."""
    amount = int(d.get("salary_amount") or 0)
    return f"{salary.money(amount, d.get('salary_currency') or 'CZK')} gross per {d.get('salary_period') or 'month'}" if amount > 0 else ""


def facts(d: dict[str, Any]) -> list[str]:
    """The jobs, degrees and salary as lines for a prompt (nothing for what is not given)."""
    lines = []
    for job in jobs(d):
        span = f"{job.get('start') or '?'} to {'now' if job.get('current') else (job.get('end') or '?')}"
        lines.append(f"- Job: {job['title']} at {job['employer']} ({span}){' - a current job' if job.get('current') else ''}")
    for row in degrees(d):
        what = ", ".join(part for part in (row.get("degree"), row.get("field")) if part) or "studies"
        lines.append(f"- Education: {what} at {row['school']} ({row.get('start') or '?'} to {row.get('end') or '?'})")
    for row in languages(d):
        lines.append(f"- Language: {row['language']}" + (f" ({row['level']})" if row.get("level") else ""))
    if salary_text(d):
        lines.append(f"- Salary expectation: {salary_text(d)}")
    return lines


# ── what the CV offers ──────────────────────────────────────────────────────
def from_cv(cv_text: str, name: str = "") -> dict[str, str]:
    """What the head of the CV shows, to offer in fields that are still empty. Only what is
    plainly written there: an email, a phone number, the two links, the name the app already uses."""
    head = str(cv_text or "")[:1500]
    out = {}
    words = str(name or "").split()
    if len(words) >= 2:
        out["first_name"], out["last_name"] = words[0], " ".join(words[1:])
    email = _EMAIL.search(head)
    if email:
        out["email"] = email.group(0).strip(".,;")
    phone = re.search(r"(?<![\w/])\+?\d[\d ()\-]{7,18}\d(?!\w)", head)
    if phone and 9 <= len(re.sub(r"\D", "", phone.group(0))) <= 15:
        out["phone"] = " ".join(phone.group(0).split())
    for key, host in (("linkedin", r"linkedin\.com/in/[\w\-%.]+"), ("github", r"github\.com/[\w\-.]+")):
        link = re.search(rf"(?:https?://)?(?:www\.)?{host}", head, re.IGNORECASE)
        if link:
            out[key] = _link(link.group(0).rstrip("."))
    return {key: value for key, value in out.items() if not _problem(key, LABELS[key], value)}


LISTS_SYSTEM = ("You copy facts out of a CV into fields. You only copy what the CV states: never add, guess, translate "
                "or improve anything. A fact the CV does not state stays an empty string. Reply with only the JSON object.")

LISTS_PROMPT = """Copy the jobs and the education out of this CV.

CV:
---
{cv_text}
---

Rules:
- one entry per job and one per degree or school, in the order of the CV;
- "start" and "end" as the CV gives them, written as YYYY or MM/YYYY; "" when the CV does not say;
- "current" is true only when the CV says the job goes on (present, now, current, no end date beside a start date);
- names of employers, titles, schools and degrees exactly as the CV writes them;
- "location" is the place the CV gives for that job (a city, a country, "Remote"); "" when it gives none;
- "description" is what the CV writes under that job: its lines or bullet points copied word for word, one per line,
  without the bullet signs; "" when the CV writes nothing under it. Never a summary, and nothing from the profile at the top;
- personal projects, courses and certificates are not jobs and not degrees: leave them out;
- "languages": every language the CV lists for the person, in the CV's order. "level" is one of Native, Fluent, Advanced,
  Intermediate, Basic, taken from what the CV says (native or mother tongue: Native; fluent, proficient, C1 or C2: Fluent;
  advanced, upper-intermediate or B2: Advanced; intermediate or B1: Intermediate; basic, beginner, A1 or A2: Basic);
  "" when the CV gives no level. Programming languages are not languages.

Return JSON with exactly this shape:
{{"experience": [{{"employer": "", "title": "", "start": "", "end": "", "current": false, "location": "", "description": ""}}],
  "education": [{{"school": "", "degree": "", "field": "", "start": "", "end": ""}}],
  "languages": [{{"language": "", "level": ""}}]}}"""


def lists_from_cv(cv_text: str) -> dict[str, list]:
    """The jobs and degrees the CV states, read by Claude in one call, to offer in the page (not saved).
    A row that would not pass the page's own checks is dropped, and so is one whose employer or
    school is not written in the CV."""
    text = str(cv_text or "")
    if not text.strip():
        raise ValueError("Your master CV could not be read.")
    data = llm.ask_json(LISTS_PROMPT.format(cv_text=text[:14000]), system=LISTS_SYSTEM, tag="assistant")
    plain = " ".join(text.lower().split())
    out: dict[str, list] = {"experience": [], "education": [], "languages": []}
    for name, key in (("experience", "employer"), ("education", "school"), ("languages", "language")):
        for row in (data.get(name) if isinstance(data, dict) else None) or []:
            if not isinstance(row, dict):
                continue
            if row.get("current"):
                row = {**row, "end": ""}
            if name == "experience":                # only what the CV itself says: a place or a line it does not have is dropped
                place = " ".join(str(row.get("location") or "").lower().split())
                lines = [" ".join(line.split()).lstrip("•-–* ").strip() for line in str(row.get("description") or "").splitlines()]
                kept = [line for line in lines if len(line) >= 8 and " ".join(line.lower().split()) in plain]
                row = {**row, "location": str(row.get("location") or "") if place and place in plain else "",
                       "description": "\n".join(kept)[:2000]}
            if name == "languages" and str(row.get("level") or "").strip().lower() not in [level.lower() for level in LEVELS]:
                row = {**row, "level": ""}          # a level in words of its own: left for the person to choose
            rows, problem = _rows(name, [row])
            if problem or not rows or " ".join(rows[0][key].lower().split()) not in plain:
                continue
            if name == "languages" and any(rows[0]["language"].lower() == kept["language"].lower() for kept in out[name]):
                continue
            out[name].append(rows[0])
    out["experience"], out["education"], out["languages"] = out["experience"][:MAX_ROWS], out["education"][:MAX_ROWS], out["languages"][:MAX_ROWS]
    return out
