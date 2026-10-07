"""Master CV against an adapted CV, paragraph by paragraph.

Only the paragraphs that differ are returned, with the changed words marked, so
checking an adapted CV before sending it takes seconds. Works on .docx files.
"""
from __future__ import annotations

import difflib
import html
import re
from pathlib import Path
from typing import Any


def _paragraphs(path: Path) -> list[str]:
    import docx
    return [p.text.strip() for p in docx.Document(str(path)).paragraphs if p.text.strip()]


def _words(text: str) -> list[str]:
    # punctuation is its own piece, so "Python," and "Python" count as the same word
    return re.findall(r"\s+|[\w+#]+(?:[.\-/'’][\w+#]+)*|[^\w\s]", text)


def _mark(old: str, new: str) -> tuple[str, str]:
    """Both texts as simple HTML: words only in the old one struck through, words only in the new one bold."""
    a, b = _words(old), _words(new)
    left, right = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        old_part, new_part = html.escape("".join(a[i1:i2])), html.escape("".join(b[j1:j2]))
        if op == "equal":
            left.append(old_part); right.append(new_part)
        else:
            if old_part.strip():
                left.append(f"<s>{old_part}</s>")
            elif old_part:
                left.append(old_part)
            if new_part.strip():
                right.append(f"<b>{new_part}</b>")
            elif new_part:
                right.append(new_part)
    return "".join(left), "".join(right)


def _heading(text: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", text)
    return bool(letters) and len(text) < 110 and letters.isupper()


def _section_name(text: str) -> str:
    """"W O R K   E X P E R I E N C E" -> "Work Experience" (letter-spaced headings)."""
    if re.fullmatch(r"(?:\S ?)+(?: {2,}(?:\S ?)+)*", text.strip()) and re.search(r"\b\w \w \w\b", text):
        text = " ".join(part.replace(" ", "") for part in re.split(r" {2,}", text.strip()))
    return re.sub(r"\s+", " ", text).strip().title()


def compare(master_path, adapted_path) -> dict[str, Any]:
    """{'rows': [{section, state, master, adapted}], 'same', 'changed', 'added', 'removed'}.
    state: changed | added (only in the adapted CV) | removed (only in the master)."""
    master, adapted = _paragraphs(Path(master_path)), _paragraphs(Path(adapted_path))
    rows, same, section = [], 0, ""
    sections_at = {}
    for i, text in enumerate(master):
        if _heading(text):
            section = _section_name(text)
        sections_at[i] = section
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, master, adapted, autojunk=False).get_opcodes():
        if op == "equal":
            same += i2 - i1
            continue
        olds, news = master[i1:i2], adapted[j1:j2]
        where = sections_at.get(i1, sections_at.get(max(0, i1 - 1), "")) if master else ""
        for k in range(max(len(olds), len(news))):
            old = olds[k] if k < len(olds) else ""
            new = news[k] if k < len(news) else ""
            if old and new:
                left, right = _mark(old, new)
                rows.append({"section": where, "state": "changed", "master": left, "adapted": right})
            elif new:
                rows.append({"section": where, "state": "added", "master": "", "adapted": f"<b>{html.escape(new)}</b>"})
            else:
                rows.append({"section": where, "state": "removed", "master": f"<s>{html.escape(old)}</s>", "adapted": ""})
    count = lambda state: sum(1 for r in rows if r["state"] == state)     # noqa: E731
    return {"rows": rows, "same": same, "changed": count("changed"), "added": count("added"), "removed": count("removed")}
