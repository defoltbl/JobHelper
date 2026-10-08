"""Interview preparation for one application: likely questions with answers
built only from the master CV.

One model call (one retry if an answer claims something the CV cannot back).
The answers are in the first person and may only use what the CV shows. For a
requirement the CV does not cover, the answer is an honest bridge ("I have not
used X in a project; the closest I have done is ...") - in an interview that is
the right answer, unlike in a cover letter.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from . import config, cover_letter, llm

SYSTEM = (
    "You prepare one candidate for one job interview. You only use facts from the "
    "candidate's CV: never invent experience, employers, numbers or technologies. "
    "Answers are in the first person, spoken style, 3-6 sentences. Use an en dash "
    "with spaces, never an em dash, and no emojis. Reply with only the JSON object."
)

PROMPT = """Prepare the candidate for an interview for the job below.

Master CV (the only source of truth about the candidate):
---
{cv_text}
---

Job:
- Title: {title}
- Company: {company}
- Location: {location}
- Posting: {description}

What the company has written so far (may be empty):
{emails}
{feedback}
Write {n} questions this interviewer is likely to ask, most likely first, across these kinds:
"about you", "technical", "your projects", "behavioural", "the role and company", "practical".
Technical questions must come from the posting's stack and the candidate's own projects.

For each answer:
- use only what the CV shows; name the real project, tool or result;
- if the question is about something the CV does not show, do NOT claim it. Give the honest
  bridge: say plainly it was not used in a project, name the closest real experience, and how
  the candidate would get up to speed;
- practical questions (location, right to work, start date, languages, salary): use only the
  facts below and the languages in the CV. If a fact is "not stated", say the candidate should
  prepare their own answer. For salary, give a way to answer, not a number.
{facts}

Return JSON with exactly these keys:
{{
  "summary": "<2 sentences: what this interview will probably focus on, written to the candidate as 'you'>",
  "questions": [
    {{"kind": "<one of the kinds above>", "question": "<the question>",
      "why": "<one short sentence: why they ask it>", "answer": "<the answer, first person>"}}
  ],
  "ask_them": ["<5 good questions the candidate can ask the interviewer>"],
  "revise": ["<up to 5 topics from the posting worth revising before the interview>"]
}}"""

KINDS = ["about you", "technical", "your projects", "behavioural", "the role and company", "practical"]
QUESTIONS = 12


# An honest bridge names the missing thing on purpose; that is not a claim.
_HONEST = re.compile(r"\b(have not|haven't|do not have|don't have|not (?:yet )?(?:used|worked)|"
                     r"no (?:(?:professional|production|hands-on|commercial|prior|direct) )?experience|"
                     r"closest|would (?:get|learn|pick)|new to me|only (?:read|studied))\b", re.IGNORECASE)


def _unbacked(answer: str, unverified: list[str]) -> str:
    """The first technology an answer presents as experience though the CV lacks it ('' if none)."""
    for sentence in cover_letter._sentences(answer):
        for term in unverified:
            if cover_letter._mentions(sentence, term) and cover_letter._CLAIM.search(sentence) \
                    and not cover_letter._WISH.search(sentence) and not _HONEST.search(sentence):
                return term
    return ""


def generate(job: dict[str, Any], cv_text: str, emails: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Questions and answers for this job. Raises ValueError if the reply is unusable."""
    unverified = cover_letter.unverified_terms(cv_text)
    first_name = cover_letter.candidate_first_name(cv_text)
    mail_lines = "\n".join(f"- {m.get('stage', '')}: {m.get('summary', '')}" for m in (emails or [])[:6]) or "(nothing yet)"
    feedback, prep = "", {}
    for _attempt in range(2):
        data = llm.ask_json(PROMPT.format(
            cv_text=cv_text[:12000], title=job.get("title", ""), company=job.get("company", ""),
            location=job.get("location", ""),
            description=(job.get("description") or "").strip()[:4000] or "(No posting text was saved; use the title and the CV.)",
            emails=mail_lines, feedback=feedback, n=QUESTIONS, facts=config.facts_block(cv_text)),
            system=SYSTEM, tag="interview_prep")
        prep = _clean(data)
        if not prep["questions"]:
            raise ValueError("The model returned no questions.")
        bad = [(q["question"], _unbacked(q["answer"], unverified)) for q in prep["questions"]]
        bad = [(q, term) for q, term in bad if term]
        third = [q["question"] for q in prep["questions"] if first_name and re.search(rf"\b{re.escape(first_name)}\b", q["answer"])]
        if not bad and not third:
            break
        feedback = "\nYour previous version was rejected. Fix these problems:\n" + "\n".join(
            [f"- The answer to \"{q[:70]}\" presents '{term}' as experience, but it is not in the CV. Use the honest bridge."
             for q, term in bad] +
            [f"- The answer to \"{q[:70]}\" talks about the candidate by name. Write it in the first person." for q in third]) + "\n"
    # Whatever still claims unbacked experience after the retry is marked, not hidden: the user must see it.
    for q in prep["questions"]:
        q["check"] = _unbacked(q["answer"], unverified)
    prep["made"] = date.today().isoformat()
    return prep


def _clean(data: Any) -> dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    questions = []
    for item in data.get("questions") or []:
        if not isinstance(item, dict):
            continue
        question, answer = cover_letter.clean(str(item.get("question", ""))).strip(), cover_letter.clean(str(item.get("answer", ""))).strip()
        if not question or not answer:
            continue
        kind = str(item.get("kind", "")).strip().lower()
        questions.append({"kind": kind if kind in KINDS else "about you", "question": question,
                          "why": cover_letter.clean(str(item.get("why", ""))).strip(), "answer": answer})
    questions.sort(key=lambda q: KINDS.index(q["kind"]))
    texts = lambda key, n: [cover_letter.clean(str(x)).strip() for x in (data.get(key) or []) if str(x).strip()][:n]   # noqa: E731
    return {"summary": cover_letter.clean(str(data.get("summary", ""))).strip(), "questions": questions,
            "ask_them": texts("ask_them", 6), "revise": texts("revise", 6)}


def as_text(job: dict[str, Any], prep: dict[str, Any]) -> str:
    """The whole preparation as plain text (for copying or printing)."""
    lines = [f"Interview preparation: {job.get('title', '')} at {job.get('company', '')}", ""]
    if prep.get("summary"):
        lines += [prep["summary"], ""]
    kind = None
    for n, q in enumerate(prep.get("questions") or [], 1):
        if q["kind"] != kind:
            kind = q["kind"]
            lines += [kind.upper(), ""]
        lines += [f"{n}. {q['question']}", q["answer"], ""]
    if prep.get("ask_them"):
        lines += ["QUESTIONS TO ASK THEM", ""] + [f"- {x}" for x in prep["ask_them"]] + [""]
    if prep.get("revise"):
        lines += ["REVISE BEFORE THE INTERVIEW", ""] + [f"- {x}" for x in prep["revise"]]
    return "\n".join(lines).strip() + "\n"
