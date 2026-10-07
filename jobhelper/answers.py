"""Your answers to the questions application forms keep asking.

Written once, copied from the job window. {company} and {role} in an answer are
replaced with the job's when you copy it. Stored encrypted in data/answers.json.
"""
from __future__ import annotations

import json
from typing import Any

from . import config, vault

# What the list starts with: only questions, the answers are yours to write.
STARTERS = ["Salary expectation", "Notice period / when you can start", "Why do you want to work at {company}?",
            "Why are you looking for a new job?", "Your strengths", "Do you need a work permit or visa?"]
MAX_ENTRIES, MAX_QUESTION, MAX_ANSWER = 60, 200, 4000


def _path():
    return config.DATA_DIR / "answers.json"


def load() -> list[dict[str, str]]:
    """[{question, answer}]. Before anything is saved: the starter questions with empty answers."""
    try:
        data = json.loads(vault.read_text(_path()))
    except (OSError, ValueError, vault.VaultError):
        return [{"question": q, "answer": ""} for q in STARTERS]
    return _clean(data)


def _clean(entries: Any) -> list[dict[str, str]]:
    out = []
    for e in entries if isinstance(entries, list) else []:
        if not isinstance(e, dict):
            continue
        question = str(e.get("question", "") or "").strip()[:MAX_QUESTION]
        answer = str(e.get("answer", "") or "").strip()[:MAX_ANSWER]
        if question:
            out.append({"question": question, "answer": answer})
    return out[:MAX_ENTRIES]


def save(entries: Any) -> list[dict[str, str]]:
    clean = _clean(entries)
    config.ensure_dirs()
    vault.write_text(_path(), json.dumps(clean, ensure_ascii=False, indent=2))
    return clean


def fill(text: str, job: dict[str, Any] | None) -> str:
    """The text with {company} and {role} replaced by this job's (left as they are without a job)."""
    job = job or {}
    for key, value in (("{company}", job.get("company")), ("{role}", job.get("title"))):
        if value:
            text = text.replace(key, str(value).strip())
    return text
