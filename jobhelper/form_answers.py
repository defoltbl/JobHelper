"""Answers for one job's application form.

Every form asks something different, so the answers are made per job: you paste
the form's questions, one model call drafts the answers from your master CV, the
posting and the facts you gave in Options, and you check them before copying.

The same rules as everywhere else: nothing that the CV does not show is claimed.
Where the app cannot know the answer (a salary figure, a reference, a date), the
draft says what to fill in and the answer is marked for you.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from . import config, cover_letter, interview_prep, llm, salary

MAX_QUESTIONS, MAX_QUESTION, MAX_ANSWER = 15, 300, 3000

SYSTEM = (
    "You fill in one job application form for one candidate. You only use facts from the "
    "candidate's CV and the facts given: never invent experience, employers, numbers, dates or "
    "technologies. Answers are in the first person, written style, short: one to four sentences "
    "unless the question asks for more. Use an en dash with spaces, never an em dash, and no "
    "emojis. Reply with only the JSON object."
)

PROMPT = """Answer the questions of this job's application form for the candidate.

Master CV (the only source of truth about the candidate):
---
{cv_text}
---

Job:
- Title: {title}
- Company: {company}
- Location: {location}
- Posting: {description}

Facts the candidate gave (use them as they are; "not stated" means you do not know):
{facts}
{salary}

The form's questions:
{questions}
{feedback}
For each question:
- answer what is asked, for THIS job and company; for "why us / why this role" connect one real
  project or skill from the CV with something the posting says;
- use only what the CV and the facts show. If the question is about a technology or experience
  the CV does not show, say so plainly and name the closest real experience;
- if you cannot know the answer (a salary figure with no target given, a reference, a date, a
  link, a yes/no the facts do not settle), do not guess: write the answer with the missing part
  in square brackets, like "[your notice period]", and say in "needs_you" what must be filled in;
- a yes/no question starts with Yes or No only when the CV or the facts settle it.

Return JSON with exactly this shape, one entry per question, in the same order:
{{"answers": [{{"n": <question number>, "answer": "<the answer>", "needs_you": "<'' or what the candidate must fill in or check>"}}]}}"""


def _lines(text: str) -> list[str]:
    """Pasted lines with list marks and numbering removed (empty lines dropped)."""
    out = []
    for line in (text or "").splitlines():
        q = re.sub(r"^\s*(?:[-*•·]+|\(?\d{1,2}[.)])\s*", "", line).strip().rstrip("*").strip()
        if q:
            out.append(q)
    return out


def check_questions(text: str) -> dict[str, Any]:
    """What was pasted, judged before anything is sent to Claude:
    {questions, problem, note}. `problem` says what to change (nothing is drafted
    while it is set); `note` only tells what was left out."""
    lines = _lines(text)
    if not lines:
        return {"questions": [], "note": "", "problem": "Paste the questions from the form first, one per line."}
    for n, line in enumerate(lines, 1):
        if len(line) > MAX_QUESTION:
            return {"questions": [], "note": "",
                    "problem": f"Line {n} is {len(line)} characters long. Paste only the questions, one per line, "
                               f"not the whole page (a question can be up to {MAX_QUESTION} characters)."}
    real = [q for q in lines if len(q) >= 3 and re.search(r"[^\W\d_]{2}", q)]
    if not real:
        return {"questions": [], "note": "", "problem": "No question found in that text. Write each question as a line of words."}
    out, seen, repeats = [], set(), 0
    for q in real:
        if q.lower() in seen:
            repeats += 1
            continue
        seen.add(q.lower())
        out.append(q)
    if len(out) > MAX_QUESTIONS:
        return {"questions": [], "note": "",
                "problem": f"That is {len(out)} questions; one draft takes up to {MAX_QUESTIONS}. Remove some and draft the rest afterwards."}
    notes = []
    if repeats:
        notes.append(f"{repeats} repeated line{'s were' if repeats != 1 else ' was'} left out")
    if len(lines) - len(real):
        skipped = len(lines) - len(real)
        notes.append(f"{skipped} line{'s' if skipped != 1 else ''} with no words {'were' if skipped != 1 else 'was'} left out")
    return {"questions": out, "problem": "", "note": "; ".join(notes)}


def common_questions(job: dict[str, Any]) -> list[str]:
    """What forms ask most often, to start from when you have not opened the form yet."""
    company = (job.get("company") or "this company").strip()
    return ["What are your salary expectations?", "When can you start?", f"Why do you want to work at {company}?",
            "Why are you a good fit for this role?", "Do you need a work permit or visa sponsorship?"]


def _salary_line(job: dict[str, Any]) -> str:
    target, currency, yours = salary.asked(job)
    if target <= 0:
        return "- Salary target: not stated"
    source = "the candidate's own figure" if yours else "an estimate for this kind of role"
    return (f"- Salary target: about {salary.money(target, currency)} gross per month ({source}; "
            "give it as the expectation and add that it is open to discussion)")


def generate(job: dict[str, Any], cv_text: str, questions: list[str], notes: str = "") -> list[dict[str, str]]:
    """[{question, answer, check}] for the given questions. `check` is '' or what you must look at.
    Raises ValueError if there is nothing to answer or the reply is unusable."""
    questions = [q.strip()[:MAX_QUESTION] for q in questions if q and q.strip()][:MAX_QUESTIONS]
    if not questions:
        raise ValueError("Paste at least one question from the form.")
    notes = (notes or "").strip()
    unverified = cover_letter.unverified_terms(cv_text + "\n" + notes)
    first_name = cover_letter.candidate_first_name(cv_text)
    numbered = "\n".join(f"{n}. {q}" for n, q in enumerate(questions, 1))
    feedback, items = "", []
    for _attempt in range(2):
        data = llm.ask_json(PROMPT.format(
            cv_text=cv_text[:12000] + (f"\n\nMore about the candidate's work, in their own words (true; use it like the CV):\n{notes}" if notes else ""),
            title=job.get("title", ""), company=job.get("company", ""),
            location=job.get("location", ""),
            description=(job.get("description") or "").strip()[:4000] or "(No posting text was saved; use the title and the CV.)",
            facts=config.facts_block(cv_text), salary=_salary_line(job), questions=numbered, feedback=feedback),
            system=SYSTEM, tag="form_answers")
        items = _clean(data, questions)
        if not any(i["answer"] for i in items):
            raise ValueError("The model returned no answers.")
        bad = [(i["question"], interview_prep._unbacked(i["answer"], unverified)) for i in items]
        bad = [(q, term) for q, term in bad if term]
        third = [i["question"] for i in items if first_name and re.search(rf"\b{re.escape(first_name)}\b", i["answer"])]
        if not bad and not third:
            break
        feedback = "\nYour previous version was rejected. Fix these problems:\n" + "\n".join(
            [f"- The answer to \"{q[:70]}\" presents '{term}' as experience, but it is not in the CV. Say so plainly instead."
             for q, term in bad] +
            [f"- The answer to \"{q[:70]}\" talks about the candidate by name. Write it in the first person." for q in third]) + "\n"
    for item in items:
        term = interview_prep._unbacked(item["answer"], unverified)
        if term:                                            # still there after the retry: shown, never hidden
            item["check"] = f"Mentions {term} as experience, which is not in your CV."
        elif not item["answer"]:
            item["check"] = "No answer was drafted. Write this one yourself."
        elif "[" in item["answer"] and "]" in item["answer"] and not item["check"]:
            item["check"] = "Fill in the part in square brackets."
    return items


def _clean(data: Any, questions: list[str]) -> list[dict[str, str]]:
    """One entry per question, in order, whatever order or shape the reply came in."""
    rows = (data.get("answers") if isinstance(data, dict) else data) or []
    by_number: dict[int, dict[str, Any]] = {}
    for position, row in enumerate(rows if isinstance(rows, list) else [], 1):
        if isinstance(row, dict):
            try:
                n = int(row.get("n") or position)
            except (TypeError, ValueError):
                n = position
            by_number.setdefault(n, row)
    out = []
    for n, question in enumerate(questions, 1):
        row = by_number.get(n, {})
        out.append({"question": question,
                    "answer": cover_letter.clean(str(row.get("answer", "") or "")).strip()[:MAX_ANSWER],
                    "check": cover_letter.clean(str(row.get("needs_you", "") or "")).strip()[:200]})
    return out


def tidy(items: Any) -> list[dict[str, str]]:
    """What the user edited, made safe to store: only question/answer/check, with sane lengths."""
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "") or "").strip()[:MAX_QUESTION]
        if question:
            out.append({"question": question, "answer": str(item.get("answer", "") or "").strip()[:MAX_ANSWER],
                        "check": str(item.get("check", "") or "").strip()[:200]})
    return out[:MAX_QUESTIONS]


def stamp() -> str:
    return date.today().isoformat()
