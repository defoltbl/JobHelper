"""Make a scraped job description readable.

Job boards hand over the posting as one long line: headings, list items and
paragraphs run together. This puts the line breaks back for display. It only
adds line breaks and list marks; no word is changed, added or removed (apart
from the board's own "Show more Show less" buttons).
"""
from __future__ import annotations

import re

# Section headings as postings write them. Longest first, so "Bonus qualifications" wins over "Bonus".
_HEADINGS = sorted([
    "About the role", "About the job", "About the team", "About the company", "About us", "About you",
    "Responsibilities", "Key responsibilities", "Your responsibilities", "What you will do", "What you'll do", "What you’ll do",
    "Your role", "The role", "Your tasks", "Tasks", "Your mission", "Job description", "Role overview", "Overview",
    "Requirements", "Key requirements", "Qualifications", "Minimum qualifications", "Preferred qualifications",
    "Bonus qualifications", "Basic qualifications", "Required skills", "Skills", "Must have", "Must-have", "Nice to have",
    "Nice-to-have", "What we expect", "What we are looking for", "What we're looking for", "What you bring", "Who you are",
    "Your profile", "Your skills", "Experience", "Education",
    "What we offer", "We offer", "Benefits", "Perks", "Bonuses", "Why join us", "Why us", "Our offer", "What's in it for you",
    "How to apply", "Application process", "Hiring process", "Next steps", "Compensation Range", "Compensation", "Salary",
    "Our team", "Who we are", "Equal opportunity",
    "Co budete dělat", "Co nabízíme", "Co očekáváme", "Požadujeme", "Nabízíme", "Náplň práce",
], key=len, reverse=True)
_HEADING_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(h) for h in _HEADINGS) + r")(?=:?\s+[A-Z0-9€$(“\"•\-–]|:)(?![\w-])")
_JUNK = re.compile(r"\s*(?:Show more\s*Show less|Show more|Show less|…?\s*See more)\s*$", re.IGNORECASE)
# "Work That Ships: We capture…" - a short capitalised label followed by a colon starts a list item
_LABEL = re.compile(r"(?:(?<=[.!?a-z0-9)]) +|(?<=\n))((?:[A-Z][\w'’&/-]*)(?: (?:[A-Z][\w'’&/-]*|and|of|for|the|to|in|on|a|&)){0,5}:) +(?=[A-Z0-9€$])")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")


def readable(text: str) -> str:
    """The description with headings on their own lines, list items marked and long blocks split."""
    text = _JUNK.sub("", (text or "").strip())
    if not text:
        return ""
    if text.count("\n") >= 4:                       # already laid out: only tidy the spacing
        return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+\n", "\n", text)).strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*[•·▪●◦]\s*", "\n• ", text)   # list marks the board kept inline

    # a heading only counts when it starts the text or follows the end of a sentence or item
    def heading(m: re.Match) -> str:
        before = text[:m.start()].rstrip()
        if before and before[-1] not in ".!?:)\n" and not before.endswith(("•",)) and len(before) > 0:
            # mid-sentence ("strong experience in …"): leave it alone, unless a run of headings/list follows a lowercase word
            if not re.search(r"[a-z0-9)]$", before) or m.group(1)[0].islower():
                return m.group(0)
            if before.split(" ")[-1][:1].islower() and m.group(1).lower() in ("experience", "skills", "salary", "tasks", "education", "overview"):
                return m.group(0)
        return f"\n\n{m.group(1).upper()}\n"
    text = _HEADING_RE.sub(heading, text)
    text = re.sub(r"\n:\s*", "\n", text)            # "Requirements: …" - the colon went with the heading
    text = re.sub(r"\n +", "\n", text)
    text = _LABEL.sub(lambda m: f"\n• {m.group(1)} ", text)

    blocks = []
    for block in text.split("\n"):
        block = block.strip()
        if len(block) <= 420 or block.startswith("•") or block.isupper():
            blocks.append(block)
            continue
        part, size = [], 0                          # a long paragraph: a break every few sentences
        for sentence in _SENTENCE.split(block):
            if size and size + len(sentence) > 380:
                blocks += [" ".join(part), ""]
                part, size = [], 0
            part.append(sentence)
            size += len(sentence) + 1
        blocks.append(" ".join(part))
    out = "\n".join(blocks)
    out = re.sub(r"\n(?=• )", "\n", out)
    out = re.sub(r"([^\n])\n(?=[A-ZÁ-Ž0-9 '’&/-]{3,}\n)", r"\1\n\n", out)     # an empty line before a heading
    out = re.sub(r"\n{2,}(?=• )", "\n", out)       # list items sit right under their heading
    return re.sub(r"\n{3,}", "\n\n", out).strip()
