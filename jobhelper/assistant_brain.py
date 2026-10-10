"""What the assistant makes of a request that is not one of its fixed ones.

One call to Claude decides one thing: an answer in words, or ONE action for the app to carry
out. Claude is given what the app knows (the jobs, their state, the last few turns of the
talk) and the list of actions; it does nothing itself. What it returns is checked here before
anything happens: an action that is not on the list, a job that does not exist or an argument
of the wrong kind is thrown away, and only the words are kept.

An action that changes your data is never carried out on Claude's word. The app describes it
in its own words ("Mark Junior Analyst at Northwind as applied?") and waits for your yes.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from . import db, llm, planner, store

MAX_TURNS, MAX_TURN, MAX_JOBS, MAX_SHOWN, MAX_ACTIONS = 6, 400, 70, 30, 3
STATUSES = ("waiting", "interview", "offer", "rejected", "on_hold")

# name -> (what it needs, does it change your data)
ACTIONS = {
    "fill_form": ((), False), "my_details": ((), False), "my_answers": ((), False),
    "open": (("job",), False), "company_brief": (("job",), False), "advice": ((), False),
    "practice": (("job",), False), "review_form": ((), False), "judge_page": ((), False), "draft_reply": (("job", "how"), False),
    "remember": (("note",), False), "forget_note": (("number",), False),
    "mark_applied": (("job",), True), "set_status": (("job", "status"), True), "set_date": (("job", "day"), True),
    "not_interested": (("job",), True), "rewrite_letter": (("job", "paragraph", "how"), True),
    "rewrite_answer": (("job", "question", "how"), True),
}

SYSTEM = (
    "You are the assistant inside JobHelper, a desktop app for one person's job search. For each request you decide ONE "
    "thing: an answer in words, or up to three actions for the app to carry out in order. You only use the facts you are given: never "
    "invent a job, a number, a date, a score or a reason, and never say that something was done (the app does it after "
    "you and reports it itself). When the request is not clear, or you cannot tell which job is meant, ask one short "
    "question instead of acting. Answers are at most five short sentences, plain words, no lists, no emojis; use an en "
    "dash, never an em dash. Reply with only the JSON object."
)

PROMPT = """Today is {today}.

What the app can do (up to three actions, only when the person asked for each of them):
- fill_form {{"skip": ["words of fields to leave out"]}} - fill in the application form that is open in the browser
- review_form {{}} - read the form in the browser back and say what looks wrong before it is sent
- my_details {{}} / my_answers {{}} - open those pages
- open {{"job": id, "what": "job" | "posting" | "cv" | "letter"}}
- mark_applied {{"job": id}} - move a lead to Applications
- set_status {{"job": id, "status": "waiting" | "interview" | "offer" | "rejected" | "on_hold"}}
- set_date {{"job": id, "day": "YYYY-MM-DD", "time": "HH:MM" or "", "kind": "interview" | "deadline" | "test task" | "call" | "other", "note": ""}}
- not_interested {{"job": id}} - remove a lead for good
- rewrite_letter {{"job": id, "paragraph": 1-based number, "how": "what to change"}}
- rewrite_answer {{"job": id, "question": "the form question", "how": "what to change"}}
- company_brief {{"job": id}} - what is known about the company, in a few lines
- advice {{}} - what the person's results so far say about their search
- practice {{"job": id}} - practise the interview questions of that job
- judge_page {{}} - read the job posting that is open in the browser, score it against the CV and offer to add it to New Jobs
- draft_reply {{"job": id, "how": "what the person wants to say"}} - draft a reply to the company's last message, for the person to copy and send
- remember {{"note": "a fact or wish of the person, in a few words"}} - keep it for later talks (only when they ask you to remember, or state a lasting wish)
- forget_note {{"number": n}} - remove one of the notes below

About the app:
{about}

The person's numbers: {numbers}

What the person asked you to remember (use it in your answers; it changes nothing in the app by itself):
{notes}

{context}

{totals}
The jobs (id | company | title | status | score | applied | last reply | date set | documents):
{jobs}

The talk so far:
{turns}

The request: {request}

Return JSON with exactly this shape:
{{"say": "<your answer, or what you are about to ask the app to do>", "actions": [{{"name": "<action>", "args": {{...}}}}],
  "show": [<ids of jobs the answer is about, to list for the person; [] when none>]}}
"actions" is [] when you only answer."""


def job_line(job: dict[str, Any], last_reply: dict[str, Any] | None, today: date) -> str:
    applied = str(job.get("date_applied") or "")
    try:
        ago = f" ({(today - date.fromisoformat(applied)).days} days ago)" if applied else ""
    except ValueError:
        ago = ""
    reply = f"{last_reply.get('stage') or 'reply'} on {db.received_at(last_reply.get('received_date', '')).date().isoformat()}" if last_reply else "none"
    event = job.get("event") or {}
    when = f"{event.get('kind', '')} {event.get('date', '')} {event.get('time', '')}".strip() if event.get("date") else "none"
    score = job.get("match_score")
    docs = "yes" if job.get("cover_letter_file") or job.get("tailored_cv_file") else "no"
    return " | ".join([str(job.get("id", "")), str(job.get("company", ""))[:40], str(job.get("title", ""))[:60], str(job.get("status", "")),
                       "-" if score is None else str(score), (applied + ago) or "-", reply, when, docs])


_ALL = re.compile(r"\b(?:reject\w*|declin\w*|refus\w*|said no|all|every|each|total|history|ever|so far|overall|how many)\b")


def relevant(jobs: list[dict[str, Any]], words: str, context_id: str = "", most: int = MAX_JOBS) -> list[dict[str, Any]]:
    """The jobs worth showing Claude for this request, the likeliest first: the one in front, the ones
    named in the talk, what is open, then the best leads. Closed applications come only when the request
    is about them or about everything. Sending every job with every request would spend the limit for nothing."""
    from . import email_client
    text = " " + " ".join(re.findall(r"[a-z0-9]+", str(words).lower())) + " "
    order = {"interview": 0, "offer": 0, "waiting": 1, "on_hold": 1, "letter_ready": 2, "found": 3, "rejected": 4}
    known = [j for j in jobs if j.get("status") in order]

    def named(job) -> bool:
        own = email_client.company_tokens(job.get("company", "")) - email_client.GENERIC_COMPANY_WORDS
        return any(f" {w} " in text for w in own)
    first = [j for j in known if j.get("id") == context_id] + [j for j in known if j.get("id") != context_id and named(j)]
    rest = [j for j in known if j not in first and (j["status"] != "rejected" or _ALL.search(text))]
    rest.sort(key=lambda j: (order[j["status"]], -(j.get("match_score") or 0)))
    return (first + rest)[:most]


def totals(jobs: list[dict[str, Any]], shown: int) -> str:
    counts: dict[str, int] = {}
    for j in jobs:
        counts[str(j.get("status") or "")] = counts.get(str(j.get("status") or ""), 0) + 1
    said = ", ".join(f"{n} {status.replace('_', ' ')}" for status, n in sorted(counts.items()) if status)
    return f"All jobs by status: {said or 'none'}. Listed below: {shown} of {len(jobs)} (the ones this request is likely about)."


def snapshot(jobs: list[dict[str, Any]], responses: list[dict[str, Any]], today: date | None = None,
             words: str = "", context_id: str = "") -> tuple[str, set[str]]:
    """The jobs as lines for the prompt and the ids that may be named."""
    today = today or date.today()
    last: dict[str, dict[str, Any]] = {}
    for r in responses:                              # newest first: the first one met for a job is its last reply
        if r.get("job_id") and r["job_id"] not in last:
            last[r["job_id"]] = r
    kept = relevant(jobs, words, context_id)
    return "\n".join(job_line(j, last.get(j["id"]), today) for j in kept) or "(no jobs yet)", {j["id"] for j in kept}


def turns_text(turns: list[tuple[str, str]]) -> str:
    kept = turns[-MAX_TURNS:]
    return "\n".join(f"{'Person' if who == 'you' else 'Assistant'}: {' '.join(str(text).split())[:MAX_TURN]}" for who, text in kept) or "(this is the first request)"


def decide(request: str, jobs: list[dict[str, Any]], responses: list[dict[str, Any]], turns: list[tuple[str, str]],
           about: str, numbers: str, context_job: dict[str, Any] | None = None, today: date | None = None,
           notes: list[str] | None = None) -> dict[str, Any]:
    """{"say", "actions": [{"name", "args"}], "show": [ids], "dropped"}: Claude's decision, checked."""
    today = today or date.today()
    talk = " ".join([str(request)] + [text for _who, text in turns[-MAX_TURNS:]])
    lines, ids = snapshot(jobs, responses, today, talk, context_job["id"] if context_job else "")
    context = "No job is open in the app right now."
    if context_job:
        ids.add(context_job["id"])
        context = (f"The job the person is looking at right now (\"this job\", \"it\"): {context_job['id']} - "
                   f"{context_job.get('title', '')} at {context_job.get('company', '')}, status {context_job.get('status', '')}, "
                   f"score {context_job.get('match_score') if context_job.get('match_score') is not None else 'none'}. "
                   f"Why this score: {str(context_job.get('match_reason') or 'no reason stored')[:600]}")
    kept = "\n".join(f"{n}. {text}" for n, text in enumerate(notes or [], 1)) or "(nothing yet)"
    data = llm.ask_json(PROMPT.format(today=f"{today.isoformat()}, a {today.strftime('%A')}", about=about, numbers=numbers, context=context,
                                      notes=kept, totals=totals(jobs, len(ids)), jobs=lines, turns=turns_text(turns),
                                      request=" ".join(str(request).split())),
                        system=SYSTEM, tag="assistant")
    return check(data, ids, len(notes or []))


def check(data: Any, ids: set[str], notes: int = 0) -> dict[str, Any]:
    """Claude's reply made safe: only words, known actions with arguments of the right kind, and ids that exist."""
    if not isinstance(data, dict):
        raise ValueError("Claude's answer could not be read. Ask again in other words.")
    say = " ".join(str(data.get("say") or "").replace("—", "–").split())[:1500]
    shown = [str(i) for i in (data.get("show") if isinstance(data.get("show"), list) else []) if str(i) in ids][:MAX_SHOWN]
    asked = data.get("actions") if isinstance(data.get("actions"), list) else ([data["action"]] if isinstance(data.get("action"), dict) else [])
    clean, dropped = [], False
    for action in asked:
        args = None
        if isinstance(action, dict) and action.get("name") in ACTIONS:
            args = _args(action["name"], action.get("args") if isinstance(action.get("args"), dict) else {}, ids, notes)
        if args is None or len(clean) >= MAX_ACTIONS:
            dropped = True
        else:
            clean.append({"name": action["name"], "args": args})
    if not say and not clean:
        raise ValueError("Claude gave no answer. Ask again in other words.")
    return {"say": say, "actions": clean, "action": clean[0] if clean else None, "show": shown, "dropped": dropped}


def _args(name: str, raw: dict[str, Any], ids: set[str], notes: int = 0) -> dict[str, Any] | None:
    needs, _changes = ACTIONS[name]
    out: dict[str, Any] = {}
    if "job" in needs:
        if str(raw.get("job") or "") not in ids:
            return None
        out["job"] = str(raw["job"])
    if name == "fill_form":
        skip = raw.get("skip") if isinstance(raw.get("skip"), list) else []
        out["skip"] = [" ".join(str(w).lower().split())[:40] for w in skip if str(w).strip()][:8]
    if name == "open":
        out["what"] = raw.get("what") if raw.get("what") in ("job", "posting", "cv", "letter") else "job"
    if name == "set_status":
        if raw.get("status") not in STATUSES:
            return None
        out["status"] = raw["status"]
    if name == "set_date":
        day = str(raw.get("day") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            return None
        out.update(day=day, time=str(raw.get("time") or "").strip()[:5],
                   kind=raw.get("kind") if raw.get("kind") in planner.KINDS else "interview", note=" ".join(str(raw.get("note") or "").split())[:200])
    if name == "rewrite_letter":
        try:
            out["paragraph"] = int(raw.get("paragraph"))
        except (TypeError, ValueError):
            return None
        if not 1 <= out["paragraph"] <= 12:
            return None
    if name == "remember":
        out["note"] = " ".join(str(raw.get("note") or "").split())[:200]
        if len(out["note"]) < 3:
            return None
    if name == "forget_note":
        try:
            out["number"] = int(raw.get("number"))
        except (TypeError, ValueError):
            return None
        if not 1 <= out["number"] <= max(notes, 0):
            return None
    if name in ("rewrite_letter", "rewrite_answer", "draft_reply"):
        out["how"] = " ".join(str(raw.get("how") or "").split())[:300]
        if not out["how"] and name != "draft_reply":
            return None
    if name == "rewrite_answer":
        out["question"] = " ".join(str(raw.get("question") or "").split())[:300]
        if not out["question"]:
            return None
    return out


def changes(name: str) -> bool:
    return ACTIONS[name][1]


def asks(action: dict[str, Any], job: dict[str, Any] | None) -> str:
    """What the app is about to do, in the app's own words: the question you answer with yes or no."""
    name, args = action["name"], action["args"]
    what = f"{job.get('title', '')} at {job.get('company', '')}" if job else "this job"
    if name == "mark_applied":
        return f"Mark {what} as applied? It moves to Applications as waiting."
    if name == "set_status":
        return f"Set {what} to “{args['status'].replace('_', ' ')}”?"
    if name == "set_date":
        when = args["day"] + (f" at {args['time']}" if args.get("time") else "")
        return f"Put this date on {what}: {args['kind']} on {when}" + (f" ({args['note']})" if args.get("note") else "") + "?"
    if name == "not_interested":
        return f"Remove {what} from New Jobs as not interested? Later searches will not bring it back, and its documents go to the backup."
    return ""


# ── skills that are a Claude call of their own ──────────────────────────────
BRIEF_SYSTEM = ("You brief one person before they apply to or talk with a company. You only use the facts given: the posting, the "
                "person's own notes and the company's earlier messages. What they do not say, you do not say. At most six short "
                "sentences, plain words, no lists, no emojis; an en dash, never an em dash.")

BRIEF_PROMPT = """Company: {company}
Role: {title} ({location})
Where the application stands: {status}

The posting:
---
{posting}
---

The person's own notes about the company:
{notes}

Messages from the company so far (newest first):
{replies}

Say what this company does and wants as far as these facts show, what stands out for this person, and what is still not known."""

ADVICE_SYSTEM = ("You read the numbers of one person's job search and say what they show. You only use the numbers given, name them, "
                 "and say so when there are too few to conclude anything. Never invent a cause. At most six short sentences, plain "
                 "words, no lists, no emojis; an en dash, never an em dash.")

ADVICE_PROMPT = """The person's results so far (computed by the app; groups with few applications are weak evidence):
{numbers}

Say what works, what does not, and the one or two changes these numbers suggest. If the numbers are too few, say that instead."""

PRACTICE_SYSTEM = ("You help one person practise for a job interview. You are given a question, the answer they just typed, their CV and "
                   "the posting. Say in at most four short sentences what is good in the answer and what is missing or weak, and name "
                   "one real thing from their CV they could add. Never invent experience for them. Plain words, no lists, no emojis; "
                   "an en dash, never an em dash.")

PRACTICE_PROMPT = """The role: {title} at {company}

The posting:
---
{posting}
---

The person's CV:
---
{cv_text}
---

The interview question: {question}
A good answer would draw on: {basis}

The answer the person typed:
---
{answer}
---"""

REVIEW_SYSTEM = ("You check one job application form before the person sends it. You are given what the form holds, the person's CV and "
                 "facts, and the posting. List only real problems: an answer that contradicts the CV or the facts, a claim the CV does "
                 "not back, an answer that does not answer its question, wording that names another company, a figure outside what the "
                 "posting states. Do not comment on style, and do not list fields that are fine. Reply with only the JSON object.")

REVIEW_PROMPT = """The role: {title} at {company}
The posting says about pay: {pay}

The person's CV:
---
{cv_text}
---

Facts the person gave:
{facts}

What the form holds now (field: value):
{fields}

Return JSON with exactly this shape (an empty list when nothing is wrong):
{{"problems": [{{"field": "<the field's name as given>", "problem": "<what is wrong, one sentence>"}}]}}"""


REPLY_SYSTEM = ("You draft a short email reply for one job applicant to send themselves. First person, polite, plain; at most 110 words; "
                "no subject line. You only use the facts given. Whatever you do not know (a time, a date, a name, a phone number) "
                "is written in square brackets for the person to fill in, like [time that suits you]. Never promise or claim "
                "anything the facts do not show. Use an en dash, never an em dash; no emojis. Reply with only the email text.")

REPLY_PROMPT = """The role: {title} at {company}
The applicant's name: {name}

The company's last message ({when}, {stage}):
Subject: {subject}
What it says: {summary}
What they ask for next: {next_step}

What the applicant wants to say: {how}"""

POSTING_SYSTEM = ("You copy facts out of a web page that may be a job posting. You only copy what the page states: never add or guess. "
                  "Reply with only the JSON object.")

POSTING_PROMPT = """The page's title: {title}
The page's address: {url}

The page's text:
---
{text}
---

Return JSON with exactly this shape:
{{"is_posting": true or false (is this one job posting, with what the job is?),
  "title": "<the job's title, as written>", "company": "<the employer, as written>", "location": "<the place, or ''>"}}"""

RATED_SYSTEM = PRACTICE_SYSTEM + (" Also rate the answer: good (it answers the question with something real from the CV), ok (it answers but is "
                                  "thin or general), weak (it misses the question or says little). Reply with only the JSON object.")

RATED_SHAPE = '\n\nReturn JSON with exactly this shape:\n{"rating": "good" | "ok" | "weak", "feedback": "<what is good and what is missing, at most four short sentences>"}'


def _plain(text: Any, most: int = 1500) -> str:
    return " ".join(str(text or "").replace("—", "–").split())[:most]


def brief(job: dict[str, Any], notes: dict[str, Any], replies: list[dict[str, Any]]) -> str:
    mine = "\n".join(f"- {k}: {v}" for k, v in (notes or {}).items() if str(v).strip()) or "(none)"
    said = "\n".join(f"- {db.received_at(r.get('received_date', '')).date().isoformat()} ({r.get('stage', '')}): {_plain(r.get('summary') or r.get('subject'), 300)}"
                     for r in replies[:6]) or "(none)"
    return _plain(llm.ask(BRIEF_PROMPT.format(company=job.get("company", ""), title=job.get("title", ""), location=job.get("location", "") or "not stated",
                                              status=str(job.get("status", "")).replace("_", " "),
                                              posting=str(job.get("description") or "").strip()[:6000] or "(no posting text was saved)",
                                              notes=mine, replies=said), system=BRIEF_SYSTEM, tag="assistant"))


def advice(numbers: dict[str, Any]) -> str:
    return _plain(llm.ask(ADVICE_PROMPT.format(numbers=json.dumps(numbers, ensure_ascii=False, default=str)[:7000]), system=ADVICE_SYSTEM, tag="assistant"))


def feedback(job: dict[str, Any], cv_text: str, question: str, basis: str, answer: str) -> dict[str, str]:
    """{"feedback", "rating"} for one practice answer (one call). An unknown rating counts as "ok"."""
    data = llm.ask_json(PRACTICE_PROMPT.format(title=job.get("title", ""), company=job.get("company", ""),
                                               posting=str(job.get("description") or "").strip()[:4000] or "(no posting text was saved)",
                                               cv_text=cv_text[:10000], question=_plain(question, 400), basis=_plain(basis, 800) or "(nothing prepared)",
                                               answer=str(answer).strip()[:3000]) + RATED_SHAPE, system=RATED_SYSTEM, tag="assistant")
    said = _plain(data.get("feedback") if isinstance(data, dict) else "", 1200)
    rating = data.get("rating") if isinstance(data, dict) and data.get("rating") in ("good", "ok", "weak") else "ok"
    return {"feedback": said, "rating": rating}


def reply(job: dict[str, Any], message: dict[str, Any], how: str, name: str) -> str:
    """A reply to the company's last message, for the person to copy and send themselves."""
    text = llm.ask(REPLY_PROMPT.format(title=job.get("title", ""), company=job.get("company", ""), name=name or "[your name]",
                                       when=db.received_at(message.get("received_date", "")).date().isoformat(), stage=message.get("stage") or "message",
                                       subject=_plain(message.get("subject"), 200), summary=_plain(message.get("summary"), 800) or "(no summary stored)",
                                       next_step=_plain(message.get("next_step"), 300) or "(nothing stated)",
                                       how=_plain(how, 300) or "a polite, positive answer to what they ask"), system=REPLY_SYSTEM, tag="assistant")
    return str(text or "").replace("—", "–").strip()[:2000]


def posting(title: str, url: str, text: str) -> dict[str, Any]:
    """What a page says about the job it advertises: {is_posting, title, company, location}. A title or a company
    that does not stand on the page is dropped, so nothing is added to the list that the page does not say."""
    data = llm.ask_json(POSTING_PROMPT.format(title=_plain(title, 300), url=_plain(url, 300), text=str(text)[:9000]), system=POSTING_SYSTEM, tag="assistant")
    if not isinstance(data, dict):
        return {"is_posting": False, "title": "", "company": "", "location": ""}
    page = " ".join(f"{title} {text}".lower().split())
    there = lambda value: " ".join(str(value or "").lower().split()) in page      # noqa: E731
    out = {key: _plain(data.get(key), 120) for key in ("title", "company", "location")}
    out = {key: value if value and there(value) else "" for key, value in out.items()}
    return {"is_posting": bool(data.get("is_posting")) and bool(out["title"]), **out}


def review(job: dict[str, Any] | None, cv_text: str, facts: str, fields: list[dict[str, str]], pay: str) -> list[dict[str, str]]:
    """Problems Claude sees in a filled-in form: [{field, problem}], only for fields the form really has."""
    held = [f for f in fields if f.get("value")]
    if not held:
        return []
    listing = "\n".join(f"- {f['label']}: {str(f['value'])[:600]}" for f in held[:60])
    data = llm.ask_json(REVIEW_PROMPT.format(title=(job or {}).get("title", "not known"), company=(job or {}).get("company", "not known"),
                                             pay=pay or "nothing", cv_text=cv_text[:10000], facts=facts, fields=listing),
                        system=REVIEW_SYSTEM, tag="assistant")
    names = {f["label"].lower(): f["label"] for f in held}
    out = []
    for item in (data.get("problems") if isinstance(data, dict) else None) or []:
        if isinstance(item, dict) and str(item.get("field") or "").lower() in names and str(item.get("problem") or "").strip():
            out.append({"field": names[str(item["field"]).lower()], "problem": _plain(item["problem"], 300)})
    return out[:8]


def may_be_shown(job: dict[str, Any]) -> bool:
    return job.get("status") in store.LEAD_STATUSES | store.APPLICATION_STATUSES
