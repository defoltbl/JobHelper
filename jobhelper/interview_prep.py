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

More about the candidate's work, in their own words (true; use it exactly like the CV; may be empty):
---
{notes}
---

Job:
- Title: {title}
- Company: {company}
- Location: {location}
- Posting: {description}

What the company has written so far (may be empty):
{emails}
{feedback}
Write {n} questions, most likely first, across these kinds:
"about you", "technical", "your projects", "behavioural", "the role and company", "practical".
The candidate may meet two different people, so write for both and mark each question with its "audience":
- "hr": about {hr} questions a recruiter or HR person asks. They usually do not know the technology, so
  the answers are in plain words: no jargon, and any technical term that cannot be avoided is explained in
  a few words. They want to hear motivation, how the candidate works with people, reliability, what the
  candidate actually did day to day, and the practical facts.
- "technical": about {tech} questions an engineer or the hiring manager asks. Precise answers, with the
  real tools, methods and numbers. They must come from the posting's stack and the candidate's own work.
A question both may ask ("Tell me about your last project") appears once for each, answered differently.

For each answer:
- use only what the CV shows; name the real project, tool or result;
- if the question is about something the CV does not show, do NOT claim it. Give the honest
  bridge: say plainly it was not used in a project, name the closest real experience, and how
  the candidate would get up to speed;
- practical questions (location, right to work, start date, languages, salary): use only the
  facts below and the languages in the CV. If a fact is "not stated", say the candidate should
  prepare their own answer. For salary, give a way to answer, not a number.
{facts}

Besides the questions, write the sheet the candidate reads before the call:
- "company": only what the posting and the emails above say about the company. Do NOT add facts from
  memory (founding year, size, clients, people): they may be wrong and the candidate would repeat them.
- "fit", "pitch" and "key_question": only what the CV shows, like the answers.
- "experience": one entry for EVERY job and internship in the CV (not the projects), newest first. This is how
  the candidate talks about their work history in this interview, so write it in full, for THIS role:
  "story" is 5-8 spoken sentences in the first person: what the place was, what they were there to do, what they
  actually did, with what, and what came of it, told so that it leads towards this role. Use everything the CV and
  the candidate's own words above give you, and nothing else: do not add duties, tools, team sizes or results that
  are not written there. Where they say little, the story is shorter; say so in "thin".
  "gained" is what that work gave them that matters for this role.
  "plain" is the same story in 2-3 sentences for an HR person who does not know the technology.
  "typical" is 3-5 things people in that kind of position usually do day to day, stated in general ("An ML
  research intern usually …"). This is general knowledge about the role, for the candidate to compare with
  what they really did; it is never written as something this candidate did.
  "if_true" is 3-5 questions TO THE CANDIDATE that turn those usual tasks into reminders, e.g. "Did you write
  the tests for it yourself?". Never statements about the candidate.
- "ask_hr" and "ask_technical": questions for the candidate to ask. Never one that the facts above already
  answer (no visa, sponsorship or relocation question when the right to work or the location is stated), and
  never one that points at the candidate's own weak spot (their years of experience, a skill they lack):
  the interviewer may raise those; the candidate does not.
- "concepts": terms from the posting worth being able to explain. Explain each in plain words; where the
  CV has related experience, say how it connects. Never say the candidate has used something the CV lacks.

Return JSON with exactly these keys:
{{
  "summary": "<2-3 sentences: what this interview will probably focus on, written to the candidate as 'you'>",
  "company": ["<4-6 short facts about the company itself (what it does, where, how it works), from the posting and emails only; nothing about this application or its dates>"],
  "company_say": "<1-2 sentences the candidate can say about the company in their own words, first person, from those facts>",
  "role": ["<4-7 points: what the work actually is, from the posting>"],
  "role_plain": "<1-2 sentences: the role in plain terms, to the candidate as 'you'>",
  "fit": ["<5-7 points: the candidate's real strengths for THIS role, each naming the project, tool or result from the CV>"],
  "gap": "<the honest gap between this posting and the CV, and how to frame it, to the candidate as 'you'>",
  "key_question": {{"question": "<the hardest question this interviewer will almost certainly ask THIS candidate>", "answer": "<the answer, first person>"}},
  "pitch": "<the opening pitch, about 45 seconds spoken, first person, from the CV only>",
  "experience": [{{"job": "<title, employer and dates as the CV gives them>", "story": "<5-8 sentences, first person>",
                  "plain": "<2-3 sentences for HR, no jargon, first person>",
                  "gained": ["<2-4 things it gave them for this role>"],
                  "typical": ["<3-5 usual tasks in that kind of position, stated in general>"],
                  "if_true": ["<3-5 questions to the candidate>"],
                  "thin": "<'' or one sentence: what the CV does not say about this job that would help here>"}}],
  "concepts": [{{"term": "<a term from the posting>", "meaning": "<1-2 plain sentences>"}}],
  "reminders": ["<4-6 practical reminders for this interview: what to lead with, what not to bluff, what to ask at the end>"],
  "questions": [
    {{"audience": "hr | technical", "kind": "<one of the kinds above>", "question": "<the question>",
      "why": "<one short sentence: why they ask it>", "answer": "<the answer, first person>"}}
  ],
  "ask_hr": ["<5 questions the candidate can ask HR or a recruiter: the process and next steps, the team, how the first months look, working arrangements; specific to this company and role, nothing a quick look at the posting already answers>"],
  "ask_technical": ["<5 questions the candidate can ask an engineer or the hiring manager: the actual work, stack, how the team builds and reviews, what a junior would own first; specific to this posting>"],
  "revise": ["<up to 5 topics from the posting worth revising before the interview>"]
}}"""

AUDIENCE_TITLES = {"hr": "If you speak with HR or a recruiter", "technical": "If you speak with an engineer or the hiring manager"}
KINDS = ["about you", "technical", "your projects", "behavioural", "the role and company", "practical"]
AUDIENCES = ["hr", "technical"]
QUESTIONS, HR_QUESTIONS = 14, 7


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


_ASK_VISA = re.compile(r"\b(visa|sponsor\w*|work permit|right to work|relocat\w+)\b", re.IGNORECASE)
_ASK_WEAK = re.compile(
    r"\b(given|despite|although|even though|considering|since|as someone)\b[^?]*\b(\d+\s*\+?\s*years?|requirement|junior|"
    r"limited experience|lack\w*|gap|not having|don't have|do not have|haven't|no (?:professional|prior|production) experience)\b"
    r"|\b\d+\s*\+\s*years?\b[^?]*\b(requirement|required)\b|\bmy (?:lack|limited|missing)\b", re.IGNORECASE)


def fit_questions(questions: list[str], facts: dict[str, str]) -> list[str]:
    """The questions to ask, without the ones this candidate should not ask: what their own facts
    already answer, and anything that puts their own weak spot on the table."""
    kept = []
    for q in questions:
        if _ASK_WEAK.search(q):
            continue
        if _ASK_VISA.search(q) and (facts.get("right_to_work") or facts.get("location")):
            continue
        kept.append(q)
    return kept


def generate(job: dict[str, Any], cv_text: str, emails: list[dict[str, Any]] | None = None, notes: str = "") -> dict[str, Any]:
    """Questions and answers for this job. `notes` is what the person wrote about their work
    beyond the CV: true, so it counts like the CV. Raises ValueError if the reply is unusable."""
    notes = (notes or "").strip()
    unverified = cover_letter.unverified_terms(cv_text + "\n" + notes)
    first_name = cover_letter.candidate_first_name(cv_text)
    mail_lines = "\n".join(f"- {m.get('stage', '')}: {m.get('summary', '')}" for m in (emails or [])[:6]) or "(nothing yet)"
    feedback, prep = "", {}
    for _attempt in range(2):
        data = llm.ask_json(PROMPT.format(
            cv_text=cv_text[:12000], title=job.get("title", ""), company=job.get("company", ""),
            location=job.get("location", ""),
            description=(job.get("description") or "").strip()[:4000] or "(No posting text was saved; use the title and the CV.)",
            emails=mail_lines, feedback=feedback, n=QUESTIONS, hr=HR_QUESTIONS, tech=QUESTIONS - HR_QUESTIONS,
            facts=config.facts_block(cv_text),
            notes=notes[:config.MAX_EXPERIENCE_NOTES] or "(nothing written yet)"),
            system=SYSTEM, tag="interview_prep")
        prep = _clean(data)
        if not prep["questions"]:
            raise ValueError("The model returned no questions.")
        # everything said in the candidate's own voice is held to the CV: the answers, the pitch, the fit list
        spoken = [(q["question"], q["answer"]) for q in prep["questions"]] + [
            ("the opening pitch", prep["pitch"]), ("the key question", prep["key_question"]["answer"]),
            ("what to say about the company", prep["company_say"])] + [("your fit", point) for point in prep["fit"]] + [
            (f"the story about {e['job'][:50]}", e["story"]) for e in prep["experience"]] + [
            (f"the plain story about {e['job'][:50]}", e["plain"]) for e in prep["experience"]]
        bad = [(label, _unbacked(said, unverified)) for label, said in spoken if said]
        bad = [(q, term) for q, term in bad if term]
        third = [label for label, said in spoken if said and first_name and re.search(rf"\b{re.escape(first_name)}\b", said)]
        if not bad and not third:
            break
        feedback = "\nYour previous version was rejected. Fix these problems:\n" + "\n".join(
            [f"- The answer to \"{q[:70]}\" presents '{term}' as experience, but it is not in the CV. Use the honest bridge."
             for q, term in bad] +
            [f"- The answer to \"{q[:70]}\" talks about the candidate by name. Write it in the first person." for q in third]) + "\n"
    # Whatever still claims unbacked experience after the retry is marked, not hidden: the user must see it.
    for q in prep["questions"]:
        q["check"] = _unbacked(q["answer"], unverified)
    facts = config.candidate_facts(cv_text)
    for key in ("ask_hr", "ask_technical", "ask_them"):       # the app's own check, whatever the model wrote
        prep[key] = fit_questions(prep[key], facts)
    checks = []
    for label, said in [("The opening pitch", prep["pitch"]), ("The answer to the key question", prep["key_question"]["answer"])] \
            + [("A point under your fit", point) for point in prep["fit"]] \
            + [(f"The story about {e['job'][:50]}", e["story"]) for e in prep["experience"]]:
        term = _unbacked(said, unverified)
        if term:
            checks.append(f"{label} mentions {term} as experience, which is not in your CV.")
    prep["checks"] = checks
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
        kind = kind if kind in KINDS else "about you"
        audience = str(item.get("audience", "")).strip().lower()
        if audience not in AUDIENCES:               # an older or careless reply: technical kinds go to the engineer
            audience = "technical" if kind in ("technical", "your projects") else "hr"
        questions.append({"audience": audience, "kind": kind, "question": question,
                          "why": cover_letter.clean(str(item.get("why", ""))).strip(), "answer": answer})
    questions.sort(key=lambda q: (AUDIENCES.index(q["audience"]), KINDS.index(q["kind"])))
    texts = lambda key, n: [cover_letter.clean(str(x)).strip() for x in (data.get(key) or []) if str(x).strip()][:n]   # noqa: E731
    text = lambda key: cover_letter.clean(str(data.get(key, "") or "")).strip()                                        # noqa: E731
    key_q = data.get("key_question") if isinstance(data.get("key_question"), dict) else {}
    concepts = [{"term": cover_letter.clean(str(c.get("term", ""))).strip(), "meaning": cover_letter.clean(str(c.get("meaning", ""))).strip()}
                for c in (data.get("concepts") or []) if isinstance(c, dict)]
    experience = []
    for e in data.get("experience") or []:
        if not isinstance(e, dict):
            continue
        entry = {"job": cover_letter.clean(str(e.get("job", "") or "")).strip(), "story": cover_letter.clean(str(e.get("story", "") or "")).strip(),
                 "plain": cover_letter.clean(str(e.get("plain", "") or "")).strip(),
                 "gained": [cover_letter.clean(str(x)).strip() for x in (e.get("gained") or []) if str(x).strip()][:5],
                 "typical": [cover_letter.clean(str(x)).strip() for x in (e.get("typical") or []) if str(x).strip()][:6],
                 "if_true": [cover_letter.clean(str(x)).strip() for x in (e.get("if_true") or []) if str(x).strip()][:6],
                 "thin": cover_letter.clean(str(e.get("thin", "") or "")).strip()}
        if entry["job"] and entry["story"]:
            experience.append(entry)
    return {"summary": text("summary"), "questions": questions, "experience": experience[:6],
            "ask_hr": texts("ask_hr", 6), "ask_technical": texts("ask_technical", 6),
            "ask_them": texts("ask_them", 6),          # one mixed list: what older saved preparations have
            "revise": texts("revise", 6),
            "company": texts("company", 7), "company_say": text("company_say"),
            "role": texts("role", 8), "role_plain": text("role_plain"),
            "fit": texts("fit", 8), "gap": text("gap"), "pitch": text("pitch"),
            "key_question": {"question": cover_letter.clean(str(key_q.get("question", "") or "")).strip(),
                             "answer": cover_letter.clean(str(key_q.get("answer", "") or "")).strip()},
            "concepts": [c for c in concepts if c["term"] and c["meaning"]][:10], "reminders": texts("reminders", 7)}


def as_text(job: dict[str, Any], prep: dict[str, Any]) -> str:
    """The whole preparation as plain text (for copying or printing)."""
    lines = [f"Interview preparation: {job.get('title', '')} at {job.get('company', '')}", ""]
    if prep.get("summary"):
        lines += [prep["summary"], ""]
    who = None
    for n, q in enumerate(prep.get("questions") or [], 1):
        audience = q.get("audience") or ("technical" if q["kind"] in ("technical", "your projects") else "hr")
        if audience != who:
            who = audience
            lines += [AUDIENCE_TITLES[who].upper(), ""]
        lines += [f"{n}. {q['question']}", q["answer"], ""]
    for key, title in (("ask_hr", "QUESTIONS TO ASK HR OR THE RECRUITER"), ("ask_technical", "QUESTIONS TO ASK THE ENGINEER OR MANAGER"),
                       ("ask_them", "QUESTIONS TO ASK THEM")):
        if prep.get(key):
            lines += [title, ""] + [f"- {x}" for x in prep[key]] + [""]
    if prep.get("revise"):
        lines += ["REVISE BEFORE THE INTERVIEW", ""] + [f"- {x}" for x in prep["revise"]]
    return "\n".join(lines).strip() + "\n"


# ── editing the saved preparation by hand ───────────────────────────────────
MAX_PART, MAX_ITEMS, MAX_ITEM = 3000, 12, 400
_LISTS = {"company": "About the company", "role": "The role: what the work is", "fit": "Your fit: lead with these",
          "ask_hr": "What you can ask HR or the recruiter", "ask_technical": "What you can ask the engineer or the hiring manager",
          "revise": "Worth revising before the call", "reminders": "Practical reminders"}
_TEXTS = {"summary": "What to expect", "company_say": "What you can say about the company", "role_plain": "The role in plain terms",
          "gap": "The honest gap", "pitch": "Your opening pitch"}
_ORDER = ["summary", "company", "company_say", "role", "role_plain", "fit", "experience", "gap", "key_question", "pitch",
          "questions", "ask_hr", "ask_technical", "revise", "reminders"]


def parts(prep: dict[str, Any]) -> list[dict[str, str]]:
    """The saved preparation as a flat list of things to edit, in the order of the sheet:
    {key, label, text, kind}. kind 'list' is one item per line."""
    out: list[dict[str, str]] = []

    def add(key: str, label: str, text: str, kind: str = "text") -> None:
        out.append({"key": key, "label": label, "text": text, "kind": kind})

    for name in _ORDER:
        if name in _TEXTS and prep.get(name):
            add(name, _TEXTS[name], prep[name])
        elif name in _LISTS and prep.get(name):
            add(name, _LISTS[name], "\n".join(prep[name]), "list")
        elif name == "experience":
            for i, e in enumerate(prep.get("experience") or []):
                add(f"experience.{i}.story", f"Your work: {e['job']}", e.get("story", ""))
                if e.get("plain"):
                    add(f"experience.{i}.plain", f"The same for HR, in plain words: {e['job']}", e["plain"])
        elif name == "key_question" and (prep.get("key_question") or {}).get("question"):
            add("key_question.question", "The key question", prep["key_question"]["question"])
            add("key_question.answer", "Your answer to the key question", prep["key_question"].get("answer", ""))
        elif name == "questions":
            for i, q in enumerate(prep.get("questions") or []):
                who = "HR asks" if (q.get("audience") or ("technical" if q.get("kind") in ("technical", "your projects") else "hr")) == "hr" \
                    else "The engineer asks"
                add(f"questions.{i}.answer", f"{who}: {q['question']}", q.get("answer", ""))
    return out


def apply_parts(prep: dict[str, Any], edited: list[dict[str, Any]], cv_text: str = "", notes: str = "") -> tuple[dict[str, Any], str]:
    """The preparation with the user's edits put in. Returns (new preparation, '') or
    (the old one untouched, what is wrong). Nothing is cut silently: text that is too long is refused."""
    import copy
    new = copy.deepcopy(prep)
    labels = {p["key"]: p["label"] for p in parts(prep)}
    for item in edited if isinstance(edited, list) else []:
        if not isinstance(item, dict) or item.get("key") not in labels:
            continue                                         # not a part of this preparation
        key, text = item["key"], cover_letter.clean(str(item.get("text", "") or "")).strip()
        label = labels[key]
        if key in _LISTS:
            lines = [ln.strip().lstrip("•-– ").strip() for ln in text.split("\n") if ln.strip().lstrip("•-– ").strip()]
            if len(lines) > MAX_ITEMS:
                return prep, f"“{label}” has {len(lines)} lines; the most is {MAX_ITEMS}. Remove some."
            long = next((ln for ln in lines if len(ln) > MAX_ITEM), None)
            if long:
                return prep, f"A line under “{label}” is {len(long)} characters long; the most is {MAX_ITEM}. Shorten it."
            new[key] = lines
            continue
        if len(text) > MAX_PART:
            return prep, f"“{label[:60]}” is {len(text)} characters long; the most is {MAX_PART}. Shorten it."
        if key in _TEXTS:
            new[key] = text
        elif key.startswith("key_question."):
            if not text:
                return prep, f"“{label}” is empty. Write it, or leave the draft as it was."
            new["key_question"][key.split(".")[1]] = text
        else:
            section, index, field = key.split(".")
            if not text and field in ("answer", "story"):
                return prep, f"“{label[:70]}” is empty. Write it, or leave the draft as it was."
            new[section][int(index)][field] = text
    unverified = cover_letter.unverified_terms(cv_text + "\n" + (notes or "")) if cv_text.strip() else []
    for q in new.get("questions") or []:
        q["check"] = _unbacked(q.get("answer", ""), unverified)
    checks = []
    for label, said in [("The opening pitch", new.get("pitch", "")), ("The answer to the key question", (new.get("key_question") or {}).get("answer", ""))] \
            + [("A point under your fit", point) for point in new.get("fit") or []] \
            + [(f"The story about {e['job'][:50]}", e.get("story", "")) for e in new.get("experience") or []]:
        term = _unbacked(said, unverified)
        if term:
            checks.append(f"{label} mentions {term} as experience, which is not in your CV.")
    new["checks"] = checks
    new["edited"] = date.today().isoformat()
    return new, ""
