#!/usr/bin/env python3
"""Keep the numbers of figures and tables in a document in order.

    python scripts/guide_number.py            # docs/GUIDE.md and docs/CODE.md
    python scripts/guide_number.py --check    # only say what is wrong

Figures and tables are numbered inside their chapter, as in a thesis: the second figure of
chapter 4 is Figure 4.2. A figure's caption is the line `*Figure 4.2 – Text*` under its picture;
a table's caption is the line `*Table 4.2 – Text*` above it. The text refers to them as
"Figure 4.2" and "Table 4.2". After a figure or table is added (give it any number not used yet,
such as 900), this renumbers the captions in the order they appear and changes every reference
to match.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = [ROOT / "docs" / "GUIDE.md", ROOT / "docs" / "CODE.md"]
NUMBER = r"\d+(?:\.\d+)?"
CAPTION = re.compile(rf"^\*(Figure|Table) ({NUMBER})(?: –|\.) (.+)\*$", re.M)     # "Figure 7. Text" is the older way of writing one
CHAPTER = re.compile(r"^## (\d+)\. ")


def captions(text: str, kind: str) -> list[tuple[str, str]]:
    return [(m.group(2), m.group(3)) for m in CAPTION.finditer(text) if m.group(1) == kind]


def expected(text: str) -> dict[str, list[tuple[str, str]]]:
    """For each kind, (the number a caption carries, the number it should carry) in the order of the text."""
    chapter, count = 0, {"Figure": 0, "Table": 0}
    out = {"Figure": [], "Table": []}
    for line in text.split("\n"):
        heading = CHAPTER.match(line)
        if heading:
            chapter, count = int(heading.group(1)), {"Figure": 0, "Table": 0}
            continue
        caption = CAPTION.match(line)
        if caption:
            kind = caption.group(1)
            count[kind] += 1
            out[kind].append((caption.group(2), f"{chapter}.{count[kind]}"))
    return out


def problems(text: str) -> list[str]:
    """What breaks the rules: numbers out of order, a caption written another way, a picture or
    table with no caption, one the text never refers to, one outside every chapter."""
    found = []
    body = CAPTION.sub("", text)
    for kind, pairs in expected(text).items():
        numbers = [old for old, _new in pairs]
        for old, new in pairs:
            if new.startswith("0."):
                found.append(f"{kind} {old} stands before the first numbered chapter")
            elif old != new:
                found.append(f"{kind} {old} should be {kind} {new}: numbers follow the chapter and the order of the text")
        for n in numbers:
            if not re.search(rf"\b{kind} {re.escape(n)}(?![\d.]*\d)", body):
                found.append(f"{kind} {n} is never referred to in the text")
        for m in re.finditer(rf"\b{kind} ({NUMBER})", body):
            if m.group(1) not in numbers:
                found.append(f"the text refers to {kind} {m.group(1)}, which does not exist")
    for m in CAPTION.finditer(text):
        if f"{m.group(1)} {m.group(2)} – " not in m.group(0):
            found.append(f"the caption of {m.group(1)} {m.group(2)} is not written as '{m.group(1)} {m.group(2)} – text'")
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("!["):
            after = next((x for x in lines[i + 1:] if x.strip()), "")
            if not after.startswith("*Figure "):
                found.append(f"the picture on line {i + 1} has no caption under it")
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[-| :]+\|$", lines[i + 1]):
            before = next((x for x in reversed(lines[:i]) if x.strip()), "")
            if not before.startswith("*Table "):
                found.append(f"the table on line {i + 1} has no caption above it")
    return found


def renumber(text: str) -> str:
    for kind, pairs in expected(text).items():
        old = [o for o, _new in pairs]
        if len(set(old)) != len(old):
            raise ValueError(f"two {kind.lower()}s carry the same number: give the new one a number not used yet")
        new = dict(pairs)
        text = re.sub(rf"\b{kind} ({NUMBER})", lambda m: f"{kind} {new.get(m.group(1), m.group(1))}", text)
    return CAPTION.sub(lambda m: f"*{m.group(1)} {m.group(2)} – {m.group(3)}*", text)


def main() -> int:
    check = "--check" in sys.argv
    bad = 0
    for path in DOCUMENTS:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if not check:
            fresh = renumber(text)
            if fresh != text:
                path.write_text(fresh, encoding="utf-8")
                print(f"{path.name}: renumbered")
            text = fresh
        for problem in problems(text):
            bad += 1
            print(f"{path.name}: {problem}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
