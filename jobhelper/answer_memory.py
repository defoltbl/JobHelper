"""Your own wording for questions that forms ask again: kept once, used at the next company.

Only what you wrote or corrected yourself is remembered (an answer saved under Form answers, or
changed on the page after the assistant filled it in), never a draft nobody read. A question is
recognised whatever company asks it ("Why do you want to work at X?" is one question). An answer
that names the company it was written for is not offered to another company.
Kept encrypted in data/answer_memory.json.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from . import config, vault
from .form_answers import MAX_ANSWER, MAX_QUESTION, unfilled

MAX_ENTRIES = 300
CHECK = "Your own earlier answer: check that it fits this job."
_SLOT = "{company}"


def path():
    return config.DATA_DIR / "answer_memory.json"


def key(question: str, company: str = "") -> str:
    """A question as it is compared: lower case, no punctuation, the company's name replaced by a mark."""
    text = str(question or "")
    name = " ".join(str(company or "").split())
    if len(name) >= 3:
        text = re.sub(re.escape(name), _SLOT, text, flags=re.IGNORECASE)
    words = re.sub(r"[^\w{} ]+", " ", text.lower()).split()
    return " ".join(words)


def _load() -> dict[str, dict[str, str]]:
    try:
        if path().exists():
            data = json.loads(vault.read_text(path()))
            if isinstance(data, dict):
                return {str(k): v for k, v in data.items() if isinstance(v, dict) and isinstance(v.get("answer"), str)}
    except vault.VaultError:
        raise
    except Exception:  # noqa: BLE001 - an unreadable memory is an empty one: answers are drafted as before
        pass
    return {}


def _names(answer: str, company: str) -> bool:
    name = " ".join(str(company or "").split())
    return len(name) >= 3 and bool(re.search(rf"(?<!\w){re.escape(name)}(?!\w)", answer, re.IGNORECASE))


def remember(question: str, answer: str, company: str = "") -> bool:
    """Keep the person's wording for a question. False when there is nothing worth keeping
    (no answer, a part still in [square brackets], no real question)."""
    answer = str(answer or "").strip()
    k = key(question, company)
    if not answer or len(answer) > MAX_ANSWER or unfilled(answer) or len(k) < 4:
        return False
    data = _load()
    data.pop(k, None)                               # the newest wording goes to the end
    data[k] = {"question": " ".join(str(question).split())[:MAX_QUESTION], "answer": answer,
               "company": " ".join(str(company or "").split()), "when": date.today().isoformat()}
    while len(data) > MAX_ENTRIES:
        data.pop(next(iter(data)))                  # the oldest one makes room
    config.ensure_dirs()
    vault.write_text(path(), json.dumps(data, ensure_ascii=False, indent=2))
    return True


def recall(question: str, company: str = "", options: list[str] | None = None) -> dict[str, str] | None:
    """Your earlier answer to this question, or None. For a choice (`options` given) only when it
    is one of the options. An answer that names another company is not offered."""
    kept = _load().get(key(question, company))
    if not kept:
        return None
    answer = kept["answer"]
    other = kept.get("company", "")
    if other and other.lower() != " ".join(str(company or "").split()).lower() and _names(answer, other):
        return None
    if options is not None:
        same = [o for o in options if " ".join(str(o).lower().split()) == " ".join(answer.lower().split())]
        if not same:
            return None
        answer = same[0]
    return {"answer": answer, "company": other, "when": kept.get("when", "")}


def entries() -> list[dict[str, str]]:
    """Everything remembered, the newest first: [{question, answer, company, when}]."""
    return [{"question": v.get("question", ""), "answer": v["answer"], "company": v.get("company", ""), "when": v.get("when", "")}
            for v in reversed(list(_load().values()))]


def forget(question: str, company: str = "") -> bool:
    """Remove one remembered answer."""
    data = _load()
    if data.pop(key(question, company), None) is None:
        return False
    vault.write_text(path(), json.dumps(data, ensure_ascii=False, indent=2))
    return True


def count() -> int:
    return len(_load())


def forget_all() -> int:
    """Remove everything remembered (the file goes; a backup made earlier still holds it). Returns how many there were."""
    n = count()
    if path().exists():
        vault.write_text(path(), json.dumps({}, indent=2))
    return n


def changed(before: Any, after: Any) -> bool:
    """Did the person change the text (more than spaces)?"""
    return " ".join(str(before or "").split()) != " ".join(str(after or "").split())
