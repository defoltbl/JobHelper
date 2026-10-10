"""What the assistant keeps between sessions: things you told it to remember ("I do not want
consulting firms") and the last turns of the talk, so that a talk can go on the next day.

The notes only shape the assistant's own answers. They change nothing in a search, a score or
a letter: for that there are the Options. Kept encrypted in data/assistant_notes.json.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from . import config, vault

MAX_NOTES, MAX_NOTE, MAX_TURNS, MAX_TURN = 40, 200, 12, 400


def path():
    return config.DATA_DIR / "assistant_notes.json"


def _load() -> dict[str, Any]:
    try:
        if path().exists():
            data = json.loads(vault.read_text(path()))
            if isinstance(data, dict):
                notes = [n for n in data.get("notes") or [] if isinstance(n, dict) and isinstance(n.get("text"), str) and n["text"].strip()]
                turns = [(str(t[0]), str(t[1])) for t in data.get("turns") or [] if isinstance(t, (list, tuple)) and len(t) == 2]
                return {"notes": notes[-MAX_NOTES:], "turns": turns[-MAX_TURNS:]}
    except vault.VaultError:
        raise
    except Exception:  # noqa: BLE001 - unreadable notes are no notes: the assistant starts fresh
        pass
    return {"notes": [], "turns": []}


def _save(data: dict[str, Any]) -> None:
    config.ensure_dirs()
    vault.write_text(path(), json.dumps({"notes": data["notes"], "turns": [list(t) for t in data["turns"]]}, ensure_ascii=False, indent=2))


def notes() -> list[dict[str, str]]:
    return [{"text": n["text"], "when": str(n.get("when") or "")} for n in _load()["notes"]]


def check(text: Any) -> str:
    """'' or why this cannot be kept."""
    words = " ".join(str(text or "").split())
    if len(words) < 3:
        return "Say in a few words what I should remember."
    if len(words) > MAX_NOTE:
        return f"That is {len(words)} characters; a note takes up to {MAX_NOTE}. Say it shorter."
    return ""


def remember(text: Any) -> dict[str, Any]:
    problem = check(text)
    if problem:
        return {"ok": False, "msg": problem}
    words = " ".join(str(text).split())
    data = _load()
    if any(n["text"].lower() == words.lower() for n in data["notes"]):
        return {"ok": True, "known": True}
    if len(data["notes"]) >= MAX_NOTES:
        return {"ok": False, "msg": f"I keep up to {MAX_NOTES} notes. Remove one on the My details page first."}
    data["notes"].append({"text": words, "when": date.today().isoformat()})
    _save(data)
    return {"ok": True, "known": False}


def forget(number: Any) -> dict[str, Any]:
    """Remove a note by its number (1 = the oldest). Returns the text that was removed."""
    data = _load()
    try:
        index = int(number) - 1
    except (TypeError, ValueError):
        index = -1
    if not 0 <= index < len(data["notes"]):
        return {"ok": False, "msg": "There is no note with that number."}
    gone = data["notes"].pop(index)
    _save(data)
    return {"ok": True, "text": gone["text"]}


def turns() -> list[tuple[str, str]]:
    return _load()["turns"]


def keep_turns(talk: list[tuple[str, str]]) -> None:
    """Keep the last turns for the next session. Trouble here must never stop an answer."""
    try:
        data = _load()
        data["turns"] = [(who, " ".join(str(text).split())[:MAX_TURN]) for who, text in talk][-MAX_TURNS:]
        _save(data)
    except Exception:  # noqa: BLE001 - the talk simply starts fresh next time
        pass


def clear_turns() -> None:
    keep_turns([])
