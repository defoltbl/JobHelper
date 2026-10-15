"""Sentences in a Markdown document that break the ASD-STE100 length rules.

ASD-STE100 Simplified Technical English: at most 20 words in a sentence that tells the reader
to do something (a numbered step), at most 25 words in a sentence that describes. Code, headings,
figure and table captions and links are not prose and are not counted.

    python scripts/ste_check.py docs/GUIDE.md docs/CODE.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

STEP_MOST, TEXT_MOST = 20, 25
_SPLIT = re.compile(r"(?<=[.!?])[”\"')]?\s+(?=[A-Z“\"(*`\[])")


def _words(sentence: str) -> int:
    plain = re.sub(r"`[^`]*`", "x", sentence)                        # a file name or a command is one word
    plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", plain)            # a link counts by its words
    plain = re.sub(r"[*_>|]", " ", plain)
    return len([w for w in plain.split() if re.search(r"\w", w)])


def paragraphs(text: str):
    """(first line number, is a step, text) for each piece of prose."""
    lines, out, buf, start, step, in_code = text.splitlines(), [], [], 0, False, False

    def flush():
        nonlocal buf
        if buf:
            out.append((start, step, " ".join(buf)))
        buf = []

    for n, raw in enumerate(lines, 1):
        line = raw.strip()
        if line.startswith("```"):
            flush(); in_code = not in_code; continue
        if in_code or not line or line.startswith(("#", "![", "*Figure", "*Table", "---", "|---", "<")):
            flush(); continue
        if line.startswith("|"):
            flush()
            for cell in line.strip("|").split("|"):
                if cell.strip():
                    out.append((n, False, cell.strip()))
            continue
        item = re.match(r"^(\d+\.|[-*]|>)\s+(.*)", line)
        if item:
            flush()
            start, step = n, item.group(1)[0].isdigit()
            line = item.group(2)
            if re.fullmatch(r"\*\*(Note|Tip|Important|Warning)\*\*", line):
                continue
        elif not buf:
            start, step = n, False
        buf.append(line.lstrip("> "))
    flush()
    return out


def problems(path: Path) -> list[tuple[int, int, str]]:
    """(line, words, sentence) for each sentence that is too long."""
    found = []
    for line, step, text in paragraphs(path.read_text(encoding="utf-8")):
        for sentence in _SPLIT.split(text):
            n = _words(sentence)
            if n > (STEP_MOST if step else TEXT_MOST):
                found.append((line, n, sentence))
    return found


if __name__ == "__main__":
    total = 0
    for name in sys.argv[1:] or ["docs/GUIDE.md", "docs/CODE.md"]:
        found = problems(Path(name))
        total += len(found)
        for line, n, sentence in found:
            print(f"{name}:{line}: {n} words: {sentence[:160]}")
    print(f"{total} sentences too long")
    sys.exit(1 if total else 0)
