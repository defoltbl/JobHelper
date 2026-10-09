#!/usr/bin/env python3
"""Keep the numbers of figures and tables in a document in order.

    python scripts/guide_number.py            # docs/GUIDE.md and docs/CODE.md
    python scripts/guide_number.py --check    # only say what is wrong

A figure's caption is the line `*Figure 7. Text*` under its picture; a table's caption is the
line `*Table 7. Text*` above it. The text refers to them as "Figure 7" and "Table 7". After a
figure or table is added (give it any number not used yet, such as 900), this renumbers the
captions in the order they appear and changes every reference to match.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = [ROOT / "docs" / "GUIDE.md", ROOT / "docs" / "CODE.md"]
CAPTION = re.compile(r"^\*(Figure|Table) (\d+)\. (.+)\*$", re.M)


def captions(text: str, kind: str) -> list[tuple[int, str]]:
    return [(int(m.group(2)), m.group(3)) for m in CAPTION.finditer(text) if m.group(1) == kind]


def problems(text: str) -> list[str]:
    """What breaks the rules: numbers out of order, a picture or table with no caption, one the text never refers to."""
    found = []
    for kind in ("Figure", "Table"):
        numbers = [n for n, _title in captions(text, kind)]
        if numbers != list(range(1, len(numbers) + 1)):
            found.append(f"{kind} numbers are not 1 to {len(numbers)} in order: {numbers}")
        body = CAPTION.sub("", text)
        for n in numbers:
            if not re.search(rf"\b{kind} {n}\b", body):
                found.append(f"{kind} {n} is never referred to in the text")
        for m in re.finditer(rf"\b{kind} (\d+)\b", body):
            if int(m.group(1)) not in numbers:
                found.append(f"the text refers to {kind} {m.group(1)}, which does not exist")
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
    for kind in ("Figure", "Table"):
        old = [n for n, _title in captions(text, kind)]
        if len(set(old)) != len(old):
            raise ValueError(f"two {kind.lower()}s carry the same number: give the new one a number not used yet")
        new = {n: i for i, n in enumerate(old, 1)}
        text = re.sub(rf"\b{kind} (\d+)\b", lambda m: f"{kind} {new.get(int(m.group(1)), int(m.group(1)))}", text)
    return text


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
