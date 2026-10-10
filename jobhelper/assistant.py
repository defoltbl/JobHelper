"""The assistant: what a request means, and how it says what it did.

It understands a few plain requests ("fill in the form in Chrome", "my details", "help");
which one is decided here by words, without asking a model, so that a request costs nothing
and always means the same.
"""
from __future__ import annotations

import re
from typing import Any

MAX_REQUEST = 300
EMPTY = "Write what you need, or press one of the buttons."
TOO_LONG = f"That is longer than {MAX_REQUEST} characters. Say it in a sentence, for example: fill in the form."
GREETING = "Hi! Open an application form in your browser, then ask me to fill it in."
HELP = ("I fill in application forms. Open the form in your browser, bring its tab to the front, and ask me to fill it in. "
        "Your name, contacts and links come from My details; open questions are answered from your CV for the job you choose. "
        "I choose from lists and yes/no questions only when your CV or your details settle the answer. "
        "I choose from lists, menus and yes/no questions only when your CV or your details settle the answer. "
        "I leave files, passwords, tick boxes and personal questions to you, and I never send a form.")
UNKNOWN = "I did not understand that. " + HELP

# What the assistant may say about the app when asked a free question: facts, kept short. It is
# given to Claude with the question, so an answer never comes from anywhere else.
ABOUT = """JobHelper is a desktop app for a job search. It runs on the person's Claude subscription.
- Run search: reads job boards, filters postings without a model call (language, level, years of experience, age, location), scores the rest from 0 to 100 against the CV, and writes an adapted CV and a cover letter for postings at or above the limit set in Options.
- A score has a reason in words (Why this score) and a list of the posting's keywords that are and are not in the CV. A required language the CV does not show caps the score at 25; a posting scored from its title only is capped at 40 and gets no documents.
- New Jobs lists leads; Mark applied moves one to Applications. Statuses of an application: waiting, interview, offer, rejected, on hold.
- Scan email reads replies read-only and files them to applications. Nothing is ever sent, deleted or marked.
- Filtered out (Last run card) lists every posting a search dropped, with the reason.
- Options sets the city, roles, limit, skip words, About you (right to work, start date, more about your work) and the salary you ask for.
- Form answers drafts answers to a form's questions from the CV. The assistant fills in the form that is open in Google Chrome and never sends it.
- Nothing is claimed in a CV, letter or answer that the master CV or the person's own notes do not show.
- When Claude's limit is used up, a run pauses and can be resumed after the reset time shown in the Usage card."""

_FILL = re.compile(r"\b(?:fill|complete|populate|autofill)\w*|\bform\b|chrome|\bapply|\bapplication")
_DETAILS = re.compile(r"detail|my (?:info|data|name|phone|address|email|links?)|contacts?\b|about me")
_ASKS = re.compile(r"^(?:why|when|where|which|who|how (?:many|much|long|often)|is|are|was|were|did|does|do|can|could|should|will|what(?! can you))\b|\?$")
_ABOUT_ME = re.compile(r"^(?:hi|hello|hey)\b|^help$|what can you|who are you|how (?:does this|do you) work")
_HELP = re.compile(r"\b(?:hi|hello|hey|help|how|what can you|who are you)\b")


# questions most forms ask whatever the company, to answer once in your own words
STARTERS = ("When can you start?", "What are your salary expectations?", "Do you need a work permit or visa sponsorship?",
            "Tell us about yourself.", "What are your strengths?", "Why are you looking for a new job?",
            "Describe a project you are proud of.", "Are you willing to relocate?")
MAX_QUESTION, MAX_ANSWER = 300, 3000
ABOUT_ONE_COMPANY = ("This question is about one company, so one answer cannot serve them all. "
                     "I draft it for each job when I fill in that job's form.")
_ONE_COMPANY = re.compile(r"\b(?:work|working|join|apply\w*) (?:here|with us|for us|at (?:our|this)|to (?:our|this))|\b(?:our|this) (?:company|team|role|position|job)\b|\bwhy us\b|about us\b")


def about_one_company(question: Any) -> bool:
    return bool(_ONE_COMPANY.search(" ".join(str(question or "").lower().split())))


def check_answer(question: Any, answer: Any) -> dict[str, str]:
    """{} or {"field": "question" | "answer", "msg": ...} for an answer of your own that is to be kept."""
    q, a = " ".join(str(question or "").split()), str(answer or "").strip()
    if len(q) < 4 or not re.search(r"[^\W\d_]{2}", q):
        return {"field": "question", "msg": "Write the question as a form asks it, in words."}
    if len(q) > MAX_QUESTION:
        return {"field": "question", "msg": f"The question is {len(q)} characters long; the most is {MAX_QUESTION}."}
    if not a:
        return {"field": "answer", "msg": "The answer is empty. Write it, or let Claude draft it first."}
    if len(a) > MAX_ANSWER:
        return {"field": "answer", "msg": f"The answer is {len(a)} characters long; the most is {MAX_ANSWER}."}
    if re.search(r"\[[^\]]+\]", a):
        return {"field": "answer", "msg": "The answer still has a part in [square brackets]. Replace it with your own words."}
    return {}


def check(text: Any) -> str:
    """'' or why the request cannot be taken."""
    words = str(text or "").strip()
    if not words:
        return EMPTY
    return TOO_LONG if len(words) > MAX_REQUEST else ""


def intent(text: Any) -> str:
    """"fill", "details", "help", "question" (something to answer with Claude) or "unknown"."""
    words = " ".join(str(text or "").lower().split())
    about_form = bool(re.search(r"\bfill|\bform\b|chrome", words))
    if _DETAILS.search(words) and not about_form:
        return "details"
    if _ABOUT_ME.search(words):
        return "help"
    if _ASKS.search(words) and len(words.split()) >= 3 and not about_form:
        return "question"                           # "why did this score 62?", "how many applications are waiting?"
    if _FILL.search(words):
        return "fill"
    if _DETAILS.search(words):
        return "details"
    if _HELP.search(words):
        return "help"
    return "question" if len(words.split()) >= 3 else "unknown"


def _count(n: int, one: str, many: str = "") -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def summary(host: str, filled: list[dict[str, Any]], left: list[dict[str, Any]], kept: int, boxes: int, job: str, guessed: bool) -> str:
    """What was done on the page, in sentences."""
    mine = sum(1 for f in filled if f.get("kind") == "detail")
    answers = sum(1 for f in filled if f.get("kind") == "answer")
    letters = sum(1 for f in filled if f.get("kind") == "letter")
    choices = sum(1 for f in filled if f.get("kind") == "choice")
    to_check = sum(1 for f in filled if f.get("check"))
    parts = []
    if filled:
        made = [_count(mine, "from My details", "from My details")] if mine else []
        made += [_count(answers, "answer drafted from your CV", "answers drafted from your CV")] if answers else []
        made += ["your cover letter"] if letters else []
        made += [_count(choices, "choice made for you", "choices made for you")] if choices else []
        parts.append(f"I filled in {_count(len(filled), 'field')} on {host}: {', '.join(made)}.")
    else:
        parts.append(f"I filled in nothing on {host}.")
    if job:
        parts.append(f"I took this to be the form for {job}." if guessed else f"The answers are for {job}.")
    if to_check:
        parts.append(f"{_count(to_check, 'of them needs', 'of them need')} your attention (outlined in amber on the page).")
    if left:
        parts.append(f"{_count(len(left), 'field is', 'fields are')} left for you, listed below with the reason.")
    if kept:
        parts.append(f"{_count(kept, 'field', 'fields')} already held something and I did not touch {'it' if kept == 1 else 'them'}.")
    if boxes:
        parts.append(f"The page also has {_count(boxes, 'tick box', 'tick boxes')}: those are yours.")
    parts.append("Read everything on the page, then send the form yourself. I never press Submit.")
    return " ".join(parts)
