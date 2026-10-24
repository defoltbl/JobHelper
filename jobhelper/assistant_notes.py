"""What the assistant keeps between sessions: things you told it to remember ("I do not want
consulting firms") and the last turns of the talk, so that a talk can go on the next day.

The notes only shape the assistant's own answers. They change nothing in a search, a score or
a letter: for that there are the Options. Kept encrypted in data/assistant_notes.json.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from . import vault

MAX_NOTES, MAX_NOTE, MAX_TURNS, MAX_TURN = 40, 200, 12, 400


def check(text: Any) -> str:
    """'' or why this cannot be kept."""
    words = " ".join(str(text or "").split())
    if len(words) < 3:
        return "Say in a few words what I should remember."
    if len(words) > MAX_NOTE:
        return f"That is {len(words)} characters; a note takes up to {MAX_NOTE}. Say it shorter."
    return ""


class AssistantNotes:
    """The notes and the last turns, read from their file at each call and written back whole."""

    def __init__(self, file: vault.JsonFile) -> None:
        self._file = file

    @property
    def path(self):
        return self._file.path

    def _read(self, changing: bool = False) -> dict[str, Any]:
        # None when unreadable: the assistant starts fresh; a change first moves a damaged file aside
        data = self._file.load_for_change() if changing else self._file.read()
        if not isinstance(data, dict):
            return {"notes": [], "turns": []}
        notes = [n for n in data.get("notes") or [] if isinstance(n, dict) and isinstance(n.get("text"), str) and n["text"].strip()]
        turns = [(str(t[0]), str(t[1])) for t in data.get("turns") or [] if isinstance(t, (list, tuple)) and len(t) == 2]
        return {"notes": notes[-MAX_NOTES:], "turns": turns[-MAX_TURNS:]}

    def _write(self, data: dict[str, Any]) -> None:
        self._file.write({"notes": data["notes"], "turns": [list(t) for t in data["turns"]]})

    def notes(self) -> list[dict[str, str]]:
        return [{"text": n["text"], "when": str(n.get("when") or "")} for n in self._read()["notes"]]

    def remember(self, text: Any) -> dict[str, Any]:
        problem = check(text)
        if problem:
            return {"ok": False, "msg": problem}
        words = " ".join(str(text).split())
        data = self._read(changing=True)
        if any(n["text"].lower() == words.lower() for n in data["notes"]):
            return {"ok": True, "known": True}
        if len(data["notes"]) >= MAX_NOTES:
            return {"ok": False, "msg": f"I keep up to {MAX_NOTES} notes. Remove one on the My details page first."}
        data["notes"].append({"text": words, "when": date.today().isoformat()})
        self._write(data)
        return {"ok": True, "known": False}

    def forget(self, number: Any) -> dict[str, Any]:
        """Remove a note by its number (1 = the oldest). Returns the text that was removed."""
        data = self._read(changing=True)
        try:
            index = int(number) - 1
        except (TypeError, ValueError):
            index = -1
        if not 0 <= index < len(data["notes"]):
            return {"ok": False, "msg": "There is no note with that number."}
        gone = data["notes"].pop(index)
        self._write(data)
        return {"ok": True, "text": gone["text"]}

    def turns(self) -> list[tuple[str, str]]:
        return self._read()["turns"]

    def keep_turns(self, talk: list[tuple[str, str]]) -> None:
        """Keep the last turns for the next session. Trouble here must never stop an answer."""
        try:
            data = self._read(changing=True)
            data["turns"] = [(who, " ".join(str(text).split())[:MAX_TURN]) for who, text in talk][-MAX_TURNS:]
            self._write(data)
        except Exception:  # noqa: BLE001 - the talk simply starts fresh next time
            pass


NOTES = AssistantNotes(vault.JsonFile("assistant_notes.json"))


def path():
    return NOTES.path


def notes() -> list[dict[str, str]]:
    return NOTES.notes()


def remember(text: Any) -> dict[str, Any]:
    return NOTES.remember(text)


def forget(number: Any) -> dict[str, Any]:
    return NOTES.forget(number)


def turns() -> list[tuple[str, str]]:
    return NOTES.turns()


def keep_turns(talk: list[tuple[str, str]]) -> None:
    NOTES.keep_turns(talk)


def clear_turns() -> None:
    NOTES.keep_turns([])
