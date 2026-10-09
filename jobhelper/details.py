"""Your own details, for filling in application forms: name, contacts, address, links, and the
few facts forms ask again and again (employer, degree, notice period, salary).

They are typed once in the assistant's window and kept encrypted in data/my_details.json.
Nothing here is guessed: a value read from the CV is only offered, and is saved when you
save the page. What a form gets is exactly what is written here.
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import config, vault

# (key, what the window calls it, the most characters)
FIELDS = (("first_name", "First name", 60), ("last_name", "Last name", 60), ("email", "Email", 120),
          ("phone", "Phone", 30), ("street", "Street and number", 120), ("city", "City", 80),
          ("postcode", "Postcode", 16), ("country", "Country", 60), ("linkedin", "LinkedIn", 200),
          ("github", "GitHub", 200), ("website", "Website or portfolio", 200),
          ("current_employer", "Current employer", 100), ("current_title", "Current job title", 100),
          ("university", "University or school", 120), ("degree", "Degree", 120),
          ("notice_period", "Notice period", 60), ("salary", "Salary expectation", 80))
KEYS = tuple(key for key, _label, _most in FIELDS)
LABELS = {key: label for key, label, _most in FIELDS}
LINKS = {"linkedin": "linkedin.com", "github": "github.com", "website": ""}

_EMAIL = re.compile(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+")
_LINK = re.compile(r"https?://[^\s/.]+(?:\.[^\s/.]+)+(?:/\S*)?", re.IGNORECASE)
_WORDS = re.compile(r"[^\W\d_]+(?:[ '.\-]+[^\W\d_]+)*\.?")


def path():
    return config.DATA_DIR / "my_details.json"


def empty() -> dict[str, str]:
    return {key: "" for key in KEYS}


def load() -> dict[str, str]:
    """What was saved, with every key there ('' = not given)."""
    out = empty()
    try:
        if path().exists():
            kept = json.loads(vault.read_text(path()))
            out.update({key: str(kept.get(key) or "").strip() for key in KEYS})
    except vault.VaultError:
        raise
    except Exception:  # noqa: BLE001 - an unreadable file is the same as none: the page shows empty fields
        pass
    return out


def check(values: Any) -> tuple[dict[str, str], dict[str, str]]:
    """(clean values, {}) or ({}, {"field": key, "msg": what is wrong}). The window checks the
    same things as you type; this is the last word."""
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
    return clean, {}


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


def full_name(d: dict[str, str]) -> str:
    return " ".join(part for part in (d.get("first_name", ""), d.get("last_name", "")) if part)
