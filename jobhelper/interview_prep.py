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
from dataclasses import dataclass
from datetime import date
from typing import Any

from . import claims, config, cover_letter, llm
from .claims import ClaimCheck

# ASD-STE100 Simplified Technical English, as the person asked for: short, clear sentences that a reader
# whose first language is not English reads once and understands. Kept here so the sheet and the answers follow it.
STE_RULES = (
    "Write all text in ASD-STE100 Simplified Technical English: one idea in each sentence; at most 20 words "
    "in a sentence (25 in a description); the active voice; the simple present or the simple past; common English "
    "words with one meaning each; no idioms, no slang, no phrasal verb where one verb does the work; keep 'the' "
    "and 'a'; a list for steps or for several items; at most 6 sentences in a paragraph. Spoken answers follow "
    "the same rules: short, direct sentences."
)
SYSTEM = (
    "You prepare one candidate for one job interview. You only use facts from the "
    "candidate's CV: never invent experience, employers, numbers or technologies. "
    "Answers are in the first person, spoken style, 3-6 sentences. Use an en dash "
    "with spaces, never an em dash, and no emojis. " + STE_RULES + " Reply with only the JSON object."
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
- "hr": about {hr} questions a recruiter or HR person asks. They usually do not know the specialist side of the work, so
  the answers are in plain words: no jargon, and any specialist term that cannot be avoided is explained in
  a few words. They want to hear motivation, how the candidate works with people, reliability, what the
  candidate actually did day to day, and the practical facts.
- "technical": about {tech} questions someone who does this work, or the hiring manager, asks: the specialist
  side of the role, whatever the profession (its tools, methods, rules and standards). Precise answers, with the
  real tools, methods and numbers. They must come from what the posting asks for and the candidate's own work.
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
  "plain" is the same story in 2-3 sentences for an HR person who does not know the specialist side of the work.
  "typical" is 3-5 things people in that kind of position usually do day to day, stated in general ("Someone in
  that position usually …"). This is general knowledge about the role, for the candidate to compare with
  what they really did; it is never written as something this candidate did.
  "if_true" is 3-5 questions TO THE CANDIDATE that turn those usual tasks into reminders, e.g. "Did you write
  the tests for it yourself?". Never statements about the candidate.
- "projects": one entry for EVERY project in the CV (not the jobs), most relevant to this role first. "what" is
  3-5 spoken sentences in the first person: the goal, what the candidate built, with what, and the result, as the
  CV and the candidate's own words give them. "plain" is the same in 1-2 sentences for HR. "tools" are the tools
  the CV names for it. "tech" takes each of those tools in turn, so the candidate can explain it to a specialist:
  "about" is one sentence on what the tool or method is, in general; "use" is one or two sentences on what it did in
  this project; "why" is one sentence on the technical reason it suits that task in the project (what it does
  better there than the usual other choices). "why" is about the project, not about this application: never
  "it shows I can …". Use what the CV and the candidate's own words say; where they only name the tool, explain its usual
  job and its usual reason in general words ("FastAPI serves the answers over HTTP"), never as a detail or a
  decision the candidate claims.
  "result" is the outcome the CV gives ('' when it gives none). "ask" is 2-3 questions a specialist may ask
  about this project. Nothing that is not written in the CV.
- "skills": 5-8 skills this role asks for that the CV shows. "proof" names where the CV shows it (a job, a
  project, a course), in one short sentence. "detail" is 2-3 sentences for a specialist: what the candidate
  did with it, as the CV says, and what they can explain about it. A skill the CV does not show is not in this list.
- "ask_hr" must include: the next steps of the process and when the candidate hears back; and practical details
  of the work that HR can answer (the team and who the role reports to, working hours and office or home days,
  the first weeks and the training, the type of contract).
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
  "projects": [{{"name": "<the project's name as the CV gives it>", "what": "<3-5 sentences, first person>",
                "plain": "<1-2 sentences for HR, no jargon, first person>", "tools": ["<tools the CV names for it>"],
                "tech": [{{"tool": "<one of those tools>", "about": "<1 sentence: what the tool or method is>",
                          "use": "<1-2 sentences: what it did in this project>", "why": "<1 sentence: the technical reason it suits that task in the project>"}}],
                "result": "<the outcome the CV gives, or ''>", "ask": ["<2-3 questions a specialist may ask about it>"]}}],
  "skills": [{{"skill": "<a skill this role asks for>", "proof": "<one sentence: where the CV shows it>",
              "detail": "<2-3 sentences for a specialist: what you did with it and what you can explain>"}}],
  "concepts": [{{"term": "<a term from the posting>", "meaning": "<1-2 plain sentences>"}}],
  "reminders": ["<4-6 practical reminders for this interview: what to lead with, what not to bluff, what to ask at the end>"],
  "questions": [
    {{"audience": "hr | technical", "kind": "<one of the kinds above>", "question": "<the question>",
      "why": "<one short sentence: why they ask it>", "answer": "<the answer, first person>"}}
  ],
  "ask_hr": ["<5-6 questions the candidate can ask HR or a recruiter: the next steps and when they hear back, the team and who the role reports to, working hours and office or home days, the first weeks and the training, the contract; specific to this company and role, nothing a quick look at the posting already answers>"],
  "ask_technical": ["<5 questions the candidate can ask someone who does this work or the hiring manager: the actual work, the tools and methods, how the team works and checks its work, what a newcomer would own first; specific to this posting>"],
  "revise": ["<up to 5 topics from the posting worth revising before the interview>"]
}}"""

AUDIENCE_TITLES = {"hr": "If you speak with HR or a recruiter", "technical": "If you speak with someone who does this work or the hiring manager"}
KINDS = ["about you", "technical", "your projects", "behavioural", "the role and company", "practical"]
AUDIENCES = ("hr", "technical")
QUESTIONS, HR_QUESTIONS = 14, 7


def audience_of(question: dict[str, Any]) -> str:
    """Who asks a question: its "audience", or for an older or careless one, the specialist when it is about the work itself."""
    audience = str(question.get("audience") or "").strip().lower()
    if audience in AUDIENCES:
        return audience
    return "technical" if question.get("kind") in ("technical", "your projects") else "hr"


def unbacked(answer: str, unverified: list[str]) -> str:
    """The first technology an answer in your voice presents as experience though the CV lacks it ('' if none).
    In an interview an honest bridge ("I have not used X; the closest I have done is …") is the right answer, not a claim."""
    return ClaimCheck(unverified).unbacked(answer, honest_ok=True)


# Every HR talk should end with the next steps: asked by the app itself when the model left it out.
NEXT_STEPS_QUESTION = "What are the next steps in the process, and when can I expect to hear from you?"
_ASKS_NEXT = re.compile(r"\b(next steps?|process|timeline|hear (?:back|from you)|decision)\b", re.IGNORECASE)


def with_next_steps(questions: list[str]) -> list[str]:
    """The questions for HR, with one about the next steps first when none asks it."""
    return list(questions) if any(_ASKS_NEXT.search(q) for q in questions) else [NEXT_STEPS_QUESTION] + list(questions)


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
    feedback, prep = "", Preparation({})
    for _attempt in range(2):
        data = llm.ask_json(PROMPT.format(
            cv_text=cv_text[:12000], title=job.get("title", ""), company=job.get("company", ""),
            location=job.get("location", ""),
            description=(job.get("description") or "").strip()[:4000] or "(No posting text was saved; use the title and the CV.)",
            emails=mail_lines, feedback=feedback, n=QUESTIONS, hr=HR_QUESTIONS, tech=QUESTIONS - HR_QUESTIONS,
            facts=config.facts_block(cv_text),
            notes=notes[:config.MAX_EXPERIENCE_NOTES] or "(nothing written yet)"),
            system=SYSTEM, tag="interview_prep")
        prep = Preparation.from_reply(data)
        if not prep.questions:
            raise ValueError("The model returned no questions.")
        # everything said in the candidate's own voice is held to the CV: the answers, the pitch, the stories, the projects
        bad, third = prep.problems(unverified, first_name)
        if not bad and not third:
            break
        feedback = claims.rejected(
            [f"{where} presents '{term}' as experience, but it is not in the CV. Use the honest bridge." for where, term in bad] +
            [f"{where} talks about the candidate by name. Write it in the first person." for where in third])
    # Whatever still claims unbacked experience after the retry is marked, not hidden: the user must see it.
    prep.mark(unverified)
    saved = prep.as_dict()
    facts = config.candidate_facts(cv_text)
    for key in ("ask_hr", "ask_technical", "ask_them"):       # the app's own check, whatever the model wrote
        saved[key] = fit_questions(saved[key], facts)
    saved["ask_hr"] = with_next_steps(saved["ask_hr"])
    saved["made"] = date.today().isoformat()
    return saved


def _items(value: Any, most: int) -> list[str]:
    """A list the model was asked for, as cleaned texts. A model sometimes answers one sentence where a list was asked:
    that is one item (read as a list it would become one item per letter); anything else that is not a list is nothing."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [cover_letter.clean(str(x)).strip() for x in value if isinstance(x, (str, int, float)) and str(x).strip()][:most]


def _text(value: Any) -> str:
    """One text from the model's reply, cleaned (en dash, no stray marks)."""
    return cover_letter.clean(str(value or "")).strip()


def _listed(value: Any) -> list[dict]:
    """The entries of a list the model was asked for (anything that is not a list: none)."""
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


@dataclass
class Question:
    """A question the interviewer will probably ask, with the answer in the candidate's words."""
    audience: str                       # "hr" or "technical"
    kind: str                           # one of KINDS
    question: str
    why: str
    answer: str

    @classmethod
    def from_reply(cls, item: dict) -> "Question | None":
        question, answer = _text(item.get("question")), _text(item.get("answer"))
        if not question or not answer:
            return None
        kind = str(item.get("kind", "")).strip().lower()
        kind = kind if kind in KINDS else "about you"
        return cls(audience_of({"audience": item.get("audience"), "kind": kind}), kind, question, _text(item.get("why")), answer)

    def order(self) -> tuple[int, int]:
        return AUDIENCES.index(self.audience), KINDS.index(self.kind)

    def to_dict(self) -> dict[str, str]:
        return {"audience": self.audience, "kind": self.kind, "question": self.question, "why": self.why, "answer": self.answer}


@dataclass
class WorkStory:
    """One job of the CV, told for this role."""
    job: str
    story: str
    plain: str
    gained: list[str]
    typical: list[str]
    if_true: list[str]
    thin: str

    @classmethod
    def from_reply(cls, e: dict) -> "WorkStory | None":
        story = cls(_text(e.get("job")), _text(e.get("story")), _text(e.get("plain")), _items(e.get("gained"), 5),
                    _items(e.get("typical"), 6), _items(e.get("if_true"), 6), _text(e.get("thin")))
        return story if story.job and story.story else None

    def to_dict(self) -> dict[str, Any]:
        return {"job": self.job, "story": self.story, "plain": self.plain, "gained": self.gained, "typical": self.typical,
                "if_true": self.if_true, "thin": self.thin}


@dataclass
class Tool:
    """A tool or a method of a project: what it is, what it did there, and why it suits that task."""
    tool: str
    about: str
    use: str
    why: str

    @classmethod
    def from_reply(cls, t: dict) -> "Tool | None":
        tool = cls(*(_text(t.get(key)) for key in ("tool", "about", "use", "why")))
        return tool if tool.tool and tool.use else None

    def to_dict(self) -> dict[str, str]:
        return {"tool": self.tool, "about": self.about, "use": self.use, "why": self.why}


@dataclass
class Project:
    """A project of the CV, told for a specialist ("what") and for HR ("plain")."""
    name: str
    what: str
    plain: str
    tools: list[str]
    tech: list[Tool]
    result: str
    ask: list[str]

    @classmethod
    def from_reply(cls, pr: dict) -> "Project | None":
        tech = [t for t in (Tool.from_reply(x) for x in _listed(pr.get("tech"))) if t][:10]
        project = cls(_text(pr.get("name")), _text(pr.get("what")), _text(pr.get("plain")), _items(pr.get("tools"), 10),
                      tech, _text(pr.get("result")), _items(pr.get("ask"), 4))
        return project if project.name and project.what else None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "what": self.what, "plain": self.plain, "tools": self.tools,
                "tech": [t.to_dict() for t in self.tech], "result": self.result, "ask": self.ask}


@dataclass
class Skill:
    """A skill the role asks for, with where the CV shows it."""
    skill: str
    proof: str
    detail: str

    @classmethod
    def from_reply(cls, sk: dict) -> "Skill | None":
        skill = cls(_text(sk.get("skill")), _text(sk.get("proof")), _text(sk.get("detail")))
        return skill if skill.skill and skill.proof else None

    def to_dict(self) -> dict[str, str]:
        return {"skill": self.skill, "proof": self.proof, "detail": self.detail}


class Preparation:
    """One interview preparation. It is saved with the job as a plain dictionary (`as_dict`), the shape the
    documents and the window read. It knows what in it is said in the candidate's voice, so that all of it is
    held to the CV in one place."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @classmethod
    def from_reply(cls, reply: Any) -> "Preparation":
        """The model's reply, cleaned: parts that are not usable are left out; lists keep their limits."""
        data = reply if isinstance(reply, dict) else {}
        keep = lambda kind, key, most: [x.to_dict() for x in (kind.from_reply(i) for i in _listed(data.get(key))) if x][:most]  # noqa: E731
        questions = sorted((q for q in (Question.from_reply(i) for i in _listed(data.get("questions"))) if q), key=Question.order)
        texts = lambda key, n: _items(data.get(key), n)                                                                   # noqa: E731
        key_q = data.get("key_question") if isinstance(data.get("key_question"), dict) else {}
        concepts = [{"term": _text(c.get("term")), "meaning": _text(c.get("meaning"))} for c in _listed(data.get("concepts"))]
        return cls({"summary": _text(data.get("summary")), "questions": [q.to_dict() for q in questions],
                    "experience": keep(WorkStory, "experience", 6), "projects": keep(Project, "projects", 6), "skills": keep(Skill, "skills", 8),
                    "ask_hr": texts("ask_hr", 6), "ask_technical": texts("ask_technical", 6),
                    "ask_them": texts("ask_them", 6),          # one mixed list: what older saved preparations have
                    "revise": texts("revise", 6),
                    "company": texts("company", 7), "company_say": _text(data.get("company_say")),
                    "role": texts("role", 8), "role_plain": _text(data.get("role_plain")),
                    "fit": texts("fit", 8), "gap": _text(data.get("gap")), "pitch": _text(data.get("pitch")),
                    "key_question": {"question": _text(key_q.get("question")), "answer": _text(key_q.get("answer"))},
                    "concepts": [c for c in concepts if c["term"] and c["meaning"]][:10], "reminders": texts("reminders", 7)})

    def as_dict(self) -> dict[str, Any]:
        return self._data

    @property
    def questions(self) -> list[dict]:
        return self._data.get("questions") or []

    def _parts(self, key: str) -> list[dict]:
        return self._data.get(key) or []

    def _sheet_voice(self) -> list[tuple[str, str]]:
        """(label, text) for everything outside the questions that the sheet says in the candidate's own voice."""
        d = self._data
        return [("The opening pitch", d.get("pitch", "")), ("The answer to the key question", (d.get("key_question") or {}).get("answer", "")),
                ("What to say about the company", d.get("company_say", ""))] \
            + [("A point under your fit", point) for point in self._parts("fit")] \
            + [(f"The story about {e['job'][:50]}", e.get("story", "")) for e in self._parts("experience")] \
            + [(f"The plain story about {e['job'][:50]}", e.get("plain", "")) for e in self._parts("experience")] \
            + [(f"The project {pr['name'][:50]}", pr.get("what", "")) for pr in self._parts("projects")] \
            + [(f"The project {pr['name'][:50]} for HR", pr.get("plain", "")) for pr in self._parts("projects")] \
            + [(f"The result of {pr['name'][:50]}", pr.get("result", "")) for pr in self._parts("projects")] \
            + [(f"What {t['tool'][:30]} did in {pr['name'][:40]}", t.get("use", "") + " " + t.get("why", ""))
               for pr in self._parts("projects") for t in pr.get("tech") or []] \
            + [(f"The skill {sk['skill'][:40]}", sk.get("proof", "") + " " + sk.get("detail", "")) for sk in self._parts("skills")]

    def voice(self) -> list[tuple[str, str]]:
        """(where, text) for everything said in the candidate's own voice: what must not claim more than the CV.
        The same list is sent back to the model and marked for the user, so nothing is checked in one place only."""
        return [(f'The answer to "{q["question"][:70]}"', q["answer"]) for q in self.questions] + self._sheet_voice()

    def problems(self, unverified: list[str], first_name: str = "") -> tuple[list[tuple[str, str]], list[str]]:
        """What to send back to the model: (where, a technology claimed without the CV) and where it names the candidate."""
        said = [(where, text) for where, text in self.voice() if text.strip()]
        bad = [(where, term) for where, term in ((w, unbacked(t, unverified)) for w, t in said) if term]
        third = [where for where, text in said if claims.names_candidate(text, first_name)]
        return bad, third

    def mark(self, unverified: list[str]) -> None:
        """Mark, in the saved preparation, what still claims more than the CV: each answer, and a list of checks."""
        for q in self.questions:
            q["check"] = unbacked(q.get("answer", ""), unverified)
        self._data["checks"] = [f"{label} mentions {term} as experience, which is not in your CV."
                                for label, term in ((label, unbacked(text, unverified)) for label, text in self._sheet_voice()) if term]


def _clean(data: Any) -> dict[str, Any]:
    """The model's reply as a saved preparation (see `Preparation.from_reply`)."""
    return Preparation.from_reply(data).as_dict()


def as_text(job: dict[str, Any], prep: dict[str, Any]) -> str:
    """The whole preparation as plain text (for copying or printing)."""
    lines = [f"Interview preparation: {job.get('title', '')} at {job.get('company', '')}", ""]
    if prep.get("summary"):
        lines += [prep["summary"], ""]
    if prep.get("projects"):
        lines += ["YOUR PROJECTS", ""]
        for pr in prep["projects"]:
            lines += [pr["name"], pr["what"]] + ([f"Tools: {', '.join(pr['tools'])}"] if pr.get("tools") else []) \
                + [f"- {t['tool']}: " + " ".join(x for x in (t.get("about", ""), t.get("use", ""), t.get("why", "")) if x) for t in pr.get("tech") or []] + ([f"Result: {pr['result']}"] if pr.get("result") else []) + [""]
    if prep.get("skills"):
        lines += ["YOUR SKILLS FOR THIS ROLE", ""] + [f"- {sk['skill']}: {sk['proof']}" for sk in prep["skills"]] + [""]
    who = None
    for n, q in enumerate(prep.get("questions") or [], 1):
        audience = audience_of(q)
        if audience != who:
            who = audience
            lines += [AUDIENCE_TITLES.get(who, str(who)).upper(), ""]
        lines += [f"{n}. {q['question']}", q["answer"], ""]
    for key, title in (("ask_hr", "QUESTIONS TO ASK HR OR THE RECRUITER"), ("ask_technical", "QUESTIONS TO ASK THE PEOPLE YOU WOULD WORK WITH OR THE MANAGER"),
                       ("ask_them", "QUESTIONS TO ASK THEM")):
        if prep.get(key):
            lines += [title, ""] + [f"- {x}" for x in prep[key]] + [""]
    if prep.get("revise"):
        lines += ["REVISE BEFORE THE INTERVIEW", ""] + [f"- {x}" for x in prep["revise"]]
    return "\n".join(lines).strip() + "\n"


# ── editing the saved preparation by hand ───────────────────────────────────
MAX_PART, MAX_ITEMS, MAX_ITEM = 3000, 12, 400
_LISTS = {"company": "About the company", "role": "The role: what the work is", "fit": "Your fit: lead with these",
          "ask_hr": "What you can ask HR or the recruiter", "ask_technical": "What you can ask the people you would work with or the hiring manager",
          "revise": "Worth revising before the call", "reminders": "Practical reminders"}
_TEXTS = {"summary": "What to expect", "company_say": "What you can say about the company", "role_plain": "The role in plain terms",
          "gap": "The honest gap", "pitch": "Your opening pitch"}
_ORDER = ["summary", "company", "company_say", "role", "role_plain", "fit", "experience", "projects", "skills", "gap", "key_question",
          "pitch", "questions", "ask_hr", "ask_technical", "revise", "reminders"]


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
        elif name == "projects":
            for i, pr in enumerate(prep.get("projects") or []):
                add(f"projects.{i}.what", f"Your project: {pr['name']}", pr.get("what", ""))
                if pr.get("plain"):
                    add(f"projects.{i}.plain", f"The same for HR, in plain words: {pr['name']}", pr["plain"])
        elif name == "skills":
            for i, sk in enumerate(prep.get("skills") or []):
                add(f"skills.{i}.proof", f"Where your CV shows it: {sk['skill']}", sk.get("proof", ""))
                if sk.get("detail"):
                    add(f"skills.{i}.detail", f"More about it, for a specialist: {sk['skill']}", sk["detail"])
        elif name == "key_question" and (prep.get("key_question") or {}).get("question"):
            add("key_question.question", "The key question", prep["key_question"]["question"])
            add("key_question.answer", "Your answer to the key question", prep["key_question"].get("answer", ""))
        elif name == "questions":
            for i, q in enumerate(prep.get("questions") or []):
                who = "HR asks" if audience_of(q) == "hr" else "A specialist asks"
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
            if not text and field in ("answer", "story", "what", "proof"):
                return prep, f"“{label[:70]}” is empty. Write it, or leave the draft as it was."
            new[section][int(index)][field] = text
    unverified = cover_letter.unverified_terms(cv_text + "\n" + (notes or "")) if cv_text.strip() else []
    Preparation(new).mark(unverified)
    new["edited"] = date.today().isoformat()
    return new, ""
