"""Talking with the assistant: a request in free words, the action it leads to, and your yes
before anything of yours is changed."""
from __future__ import annotations



import copy
import re
from datetime import date
from typing import Any

from . import (agent1_cv, agent3_letters, agent4_tracker, answer_memory, assistant, assistant_brain, assistant_notes, chrome,
    config, db, details, form_answers, form_choices, form_fill, insights, planner, salary, store)

_PLAIN = re.compile(r"\b(?:but|skip|except|without|only|not|don't|do not|leave|and)\b")
NO_JOB = "That job is not in the list any more."


class TalkService:
    """"""

    def __init__(self, app, editor, cv, desktop) -> None:
        """`app` is the facade (`ui_api.Api`): what this service needs from the others is asked through it."""
        self._app, self._editor, self._cv, self._desktop = app, editor, cv, desktop
        self._turns = None          # the last turns of the talk, read from disk on first use
        self._undo = None           # how to take back the last yes
        self._noticed = set()       # forms already said once
    # ── what the talk remembers ─────────────────────────────────
    def _talk(self) -> list[tuple[str, str]]:
        if self._turns is None:
            try:
                self._turns = assistant_notes.turns()         # the talk goes on where it stopped, also after a restart
            except Exception:  # noqa: BLE001 - locked or unreadable: a fresh talk
                self._turns = []
        return self._turns

    def _turn(self, who: str, text: str) -> None:
        turns = self._talk()
        turns.append((who, " ".join(str(text or "").split())[:assistant_brain.MAX_TURN]))
        self._turns = turns[-2 * assistant_brain.MAX_TURNS:]
        assistant_notes.keep_turns(self._turns)

    def assistant_new_talk(self):
        self._turns = []
        assistant_notes.clear_turns()
        return {"ok": True}

    def _numbers(self) -> str:
        c = self._app.counts()
        return (f"{c.get('leads', 0)} leads in New Jobs, {c.get('applications', 0)} applications, "
                f"{c.get('responses', 0)} replies read, {c.get('followups', 0)} follow-ups due")

    # ── one request ─────────────────────────────────────────────
    def assistant_talk(self, text, context_job="", chosen_job="", progress=None):
        """What the assistant does with a request. The fixed requests ("fill in the form", "my details",
        "help") cost nothing; anything else is one call to Claude, which answers or names up to three actions.
        `context_job` is the job whose window is open, `chosen_job` the one picked in the assistant's list;
        `progress` is told in a few words what is being done."""
        tell = progress or (lambda words: None)
        problem = assistant.check(text)
        if problem:
            return {"ok": False, "action": "none", "msg": problem}
        words = " ".join(str(text).split())
        job_id = context_job or chosen_job
        what = assistant.intent(words)
        if what in ("fill", "details", "help") and len(words.split()) <= 6 and not _PLAIN.search(words.lower()):
            if what == "fill":
                tell("Reading the form in the browser…")
            out = self._app.assistant_ask(words, job_id)
            self._turn("you", words)
            self._turn("bot", out.get("say") or out.get("msg") or "")
            return out
        if what == "unknown":
            return {"ok": True, "action": "help", "say": assistant.UNKNOWN}
        tell("Looking at your jobs…")
        jobs = store.load_jobs()
        try:
            kept = [n["text"] for n in assistant_notes.notes()]
        except Exception:  # noqa: BLE001 - no notes is not a reason to refuse an answer
            kept = []
        tell("Asking Claude…")
        try:
            decided = assistant_brain.decide(words, jobs, db.all_responses(), self._talk(), assistant.ABOUT, self._numbers(),
                                             store.find(jobs, job_id) if job_id else None, notes=kept)
        except Exception as e:  # noqa: BLE001 - said to the person as the reason
            return {"ok": False, "action": "say", "msg": f"I could not ask Claude: {str(e) or type(e).__name__}"}
        tell("Checking the answer…")
        self._turn("you", words)
        rows = [{"id": j["id"], "label": f"{j.get('company', '')} · {j.get('title', '')}",
                 "sub": str(j.get("status", "")).replace("_", " ") + (f" · score {j['match_score']}" if j.get("match_score") is not None else "")}
                for j in (store.find(jobs, i) for i in decided["show"]) if j]
        dropped = " (One thing I could not carry out as an action: say which job you mean, or use the job's own window.)" if decided["dropped"] else ""
        if not decided["actions"]:
            say = decided["say"] + dropped
            self._turn("bot", say)
            return {"ok": True, "action": "say", "say": say, "rows": rows}
        now = [a for a in decided["actions"] if not assistant_brain.changes(a["name"])]
        later = [a for a in decided["actions"] if assistant_brain.changes(a["name"])]
        done = []
        for action in now:                              # what only shows or drafts something is done at once, in order
            tell({"company_brief": "Writing the brief…", "advice": "Reading your results…", "draft_reply": "Drafting the reply…",
                  "judge_page": "Reading the page…", "fill_form": "Reading the form in the browser…", "review_form": "Reading the form back…"}.get(action["name"], "Working…"))
            done.append(self._act(action, decided["say"] if len(decided["actions"]) == 1 else "", jobs, job_id))
        asked = self._ask(later, jobs) if later else None
        # one answer goes back to the window: the one that needs it to do something, with the others' words before it
        results = done + ([asked] if asked else [])
        chosen = asked if asked and asked.get("action") == "confirm" else next((r for r in results if r.get("action") not in ("say", None)), results[-1])
        special = dict(chosen)
        special["also"] = [(r.get("say") or r.get("msg") or "") for r in results if r is not chosen and (r.get("say") or r.get("msg"))]
        special["then"] = [{"action": r["action"], "job_id": r.get("job_id", ""), "what": r.get("what", ""), "page": r.get("page", "")}
                           for r in results if r is not chosen and r.get("ok") and r.get("action") in ("open", "page")]     # also to be shown by the window
        if dropped:
            special["also"].append(dropped.strip(" ()"))
        special.setdefault("rows", rows)
        self._turn("bot", " ".join(special["also"] + [special.get("say") or special.get("ask") or special.get("msg") or ""]))
        return special

    def _ready(self, action: dict[str, Any], job) -> str:
        """'' or why this change cannot be made, said before you are asked about it."""
        name, args = action["name"], action["args"]
        if name == "mark_applied" and job["status"] not in store.LEAD_STATUSES:
            return f"{job.get('title', '')} at {job.get('company', '')} is already among your applications."
        if name == "not_interested" and job["status"] not in store.LEAD_STATUSES:
            return "Only a lead in New Jobs can be marked not interested. For an application, set its status instead."
        if name == "set_date":
            return planner.check_event(args["day"], args.get("time", ""), args.get("kind", "interview"))[1]
        return ""

    def _ask(self, actions: list[dict[str, Any]], jobs: list[dict[str, Any]]) -> dict[str, Any]:
        """The question for what would change your data: described in the app's own words, done only after your yes."""
        if len(actions) == 1 and actions[0]["name"] in ("rewrite_letter", "rewrite_answer"):
            job = store.find(jobs, actions[0]["args"]["job"])
            if not job:
                return {"ok": False, "action": "say", "msg": NO_JOB}
            return self._rewrite_letter(job, actions[0]["args"]) if actions[0]["name"] == "rewrite_letter" else self._rewrite_answer(job, actions[0]["args"])
        plain, asks = [], []
        for action in actions:
            if action["name"] in ("rewrite_letter", "rewrite_answer"):
                return {"ok": False, "action": "say", "msg": "A rewrite is shown to you before it is saved, so ask for it on its own, not together with other changes."}
            job = store.find(jobs, action["args"]["job"])
            if not job:
                return {"ok": False, "action": "say", "msg": NO_JOB}
            problem = self._ready(action, job)
            if problem:
                return {"ok": False, "action": "say", "msg": problem}
            plain.append(action)
            asks.append(assistant_brain.asks(action, job))
        ask = asks[0] if len(asks) == 1 else "Shall I do these " + str(len(asks)) + " things?\n" + "\n".join(f"{n}. {a}" for n, a in enumerate(asks, 1))
        pending = plain[0] if len(plain) == 1 else {"name": "many", "args": {"actions": plain}}
        return {"ok": True, "action": "confirm", "ask": ask, "pending": pending, "say": ""}

    def _act(self, action: dict[str, Any], say: str, jobs: list[dict[str, Any]], job_id: str) -> dict[str, Any]:
        """Carry out an action that changes nothing of yours."""
        name, args = action["name"], action["args"]
        job = store.find(jobs, args["job"]) if args.get("job") else None
        if "job" in args and not job:
            return {"ok": False, "action": "say", "msg": NO_JOB}
        if name == "fill_form":
            return self._app.assistant_fill(job_id, skip=args.get("skip") or [])
        if name == "review_form":
            return self._app.assistant_review(job_id)
        if name == "judge_page":
            return self.assistant_judge_page()
        if name in ("my_details", "my_answers"):
            return {"ok": True, "action": "page", "page": "details" if name == "my_details" else "answers", "say": say or "Here it is."}
        if name == "open":
            return {"ok": True, "action": "open", "job_id": job["id"], "what": args["what"],
                    "say": say or f"Opening {job.get('title', '')} at {job.get('company', '')}."}
        if name == "practice":
            return self.assistant_practice(job["id"])
        if name == "company_brief":
            return self._said(lambda: assistant_brain.brief(job, planner.company_notes(job.get("company", "")),
                                                            [r for r in db.all_responses() if r.get("job_id") == job["id"]]))
        if name == "advice":
            return self._said(lambda: assistant_brain.advice(self._results()))
        if name == "remember":
            kept = assistant_notes.remember(args["note"])
            if not kept.get("ok"):
                return {"ok": False, "action": "say", "msg": kept.get("msg") or "That could not be kept."}
            return {"ok": True, "action": "say", "notes_changed": True,
                    "say": f"I {'already knew' if kept.get('known') else 'will remember'}: {args['note']}. It shapes my answers; to change what a search finds, use Options."}
        if name == "forget_note":
            gone = assistant_notes.forget(args["number"])
            return {"ok": True, "action": "say", "notes_changed": True, "say": f"Forgotten: {gone['text']}."} if gone.get("ok") \
                else {"ok": False, "action": "say", "msg": gone.get("msg") or "That note is not there."}
        if name == "draft_reply":
            return self._draft_reply(job, args.get("how", ""))
        return {"ok": False, "action": "say", "msg": "That is not something I can do."}

    def _draft_reply(self, job, how: str) -> dict[str, Any]:
        message = next((r for r in db.all_responses() if r.get("job_id") == job["id"]), None)
        if not message:
            return {"ok": False, "action": "say", "msg": f"No message from {job.get('company', '')} is filed under this application, so there is nothing to reply to. Scan your email first."}
        try:
            text = assistant_brain.reply(job, message, how, self._cv.name())
        except Exception as e:  # noqa: BLE001 - said to the person as the reason
            return {"ok": False, "action": "say", "msg": f"I could not ask Claude: {str(e) or type(e).__name__}"}
        if not text:
            return {"ok": False, "action": "say", "msg": "Claude gave no draft. Ask again in other words."}
        return {"ok": True, "action": "draft", "copy": text, "preview": text,
                "say": f"A reply to {job.get('company', '')} for you to copy. Fill in what stands in [square brackets], then send it yourself: I never send mail."}

    def assistant_judge_page(self):
        """Read the job posting that is open in the browser, score it with the app's own scorer, and offer to add it.
        One call to Claude (the scoring) when the page states its job in the form search engines read, as most
        job pages do; one more to read the title and the employer off the page when it does not."""
        def no(msg):
            return {"ok": False, "action": "say", "msg": msg}
        self.browser()
        try:
            tab = chrome.active_tab()
            address = form_fill.PageAddress(tab["url"])
            host = address.host
            if not address.is_web:
                return no("The tab in front is not a web page. Bring the job posting to the front and ask me again.")
            if address.refused:
                return no(address.refusal("read this site"))
            page = form_fill.page_answer(chrome.run(form_fill.PAGE))
        except (chrome.ChromeError, ValueError) as e:
            return no(str(e))
        jobs = store.load_jobs()
        known = store.find(jobs, form_fill.match_job([j for j in jobs if assistant_brain.may_be_shown(j)], page["url"], ""))
        if known:
            score = f"it scored {known['match_score']}" if known.get("match_score") is not None else "it has no score yet"
            return {"ok": True, "action": "say", "rows": [{"id": known["id"], "label": f"{known.get('company', '')} · {known.get('title', '')}",
                                                          "sub": str(known.get("status", "")).replace("_", " ")}],
                    "say": f"This posting is in your list already: {known.get('title', '')} at {known.get('company', '')}, {score}. {str(known.get('match_reason') or '')[:400]}".strip()}
        if len(page["text"].split()) < 60:
            return no("There is too little text on this page to judge a job from. Open the posting itself and ask me again.")
        cv_text = self._cv.text()
        if not cv_text.strip():
            return no("Your master CV could not be read, so I cannot compare the posting with it.")
        try:
            if page["stated"]["title"]:          # the page states the job for search engines: no call is needed to read it
                facts = {"is_posting": True, **page["stated"]}
            else:
                facts = assistant_brain.posting(page["title"], page["url"], page["text"])
            if not facts["is_posting"]:
                return no("This page does not read like one job posting. Open the posting itself and ask me again.")
            job = store.new_job(id="assistant-" + store.url_id(page["url"]), title=facts["title"], company=facts["company"] or host,
                                location=facts["location"], source="assistant", url=page["url"], description=page["text"])
            stats = agent3_letters.rescore([job], [job["id"]], agent1_cv.load_profile() or {}, cv_text)
        except Exception as e:  # noqa: BLE001 - said to the person as the reason
            return no(f"I could not ask Claude: {str(e) or type(e).__name__}")
        if not stats["scored"]:
            return no("Claude gave no usable score for this posting. Try again in a moment.")
        job.pop("score_before", None)
        limit = self._app.threshold()
        verdict = "above" if job["match_score"] >= limit else "below"
        return {"ok": True, "action": "confirm", "say": "",
                "ask": f"{job['title']} at {job['company']} scores {job['match_score']}, {verdict} your limit of {limit}. {str(job.get('match_reason') or '')[:500]} "
                       "Add it to New Jobs? The next search then writes its documents if it is above the limit.",
                "pending": {"name": "add_job", "args": {"job": job["id"], "record": job}}}

    def _said(self, make) -> dict[str, Any]:
        try:
            said = make()
        except Exception as e:  # noqa: BLE001 - said to the person as the reason
            return {"ok": False, "action": "say", "msg": f"I could not ask Claude: {str(e) or type(e).__name__}"}
        return {"ok": True, "action": "say", "say": said} if said else {"ok": False, "action": "say", "msg": "Claude gave no answer. Ask again in other words."}

    def _results(self) -> dict[str, Any]:
        """The numbers of the Insights view, as the advice is built from them."""
        jobs, responses = store.load_jobs(), db.all_responses()
        threshold = int(self._app.options().get("threshold") or 30)
        return {"what_works": insights.what_works(jobs, responses), "skill_gaps": insights.skill_gaps(jobs, self._cv.text()),
                "reply_times": insights.reply_times(jobs, responses), "low_scores": insights.low_score_reasons(jobs, self._cv.text(), threshold),
                "smallest_group_that_counts": insights.MIN_GROUP}

    # ── edits by instruction: shown first, saved after your yes ──
    def _rewrite_letter(self, job, args) -> dict[str, Any]:
        letter = self._app.letter_for_edit(job["id"])
        if not letter.get("ok"):
            return {"ok": False, "action": "say", "msg": letter.get("msg") or "This letter cannot be changed here."}
        paragraphs = list(letter["paragraphs"])
        index = args["paragraph"] - 1
        if not 0 <= index < len(paragraphs):
            return {"ok": False, "action": "say", "msg": f"The letter has {len(paragraphs)} paragraphs; there is no paragraph {args['paragraph']}."}
        new = self._app.rewrite_paragraph(job["id"], paragraphs, index, args["how"])
        if not new.get("ok"):
            return {"ok": False, "action": "say", "msg": new.get("msg") or "The paragraph could not be rewritten."}
        paragraphs[index] = new["paragraph"]
        return {"ok": True, "action": "confirm", "say": "", "preview": new["paragraph"],
                "ask": f"Replace paragraph {args['paragraph']} of the letter for {job.get('company', '')} with this version? The old version is kept in the backup.",
                "pending": {"name": "save_letter", "args": {"job": job["id"], "paragraphs": paragraphs}}}

    def _rewrite_answer(self, job, args) -> dict[str, Any]:
        items = form_answers.tidy((job.get("form_answers") or {}).get("items"))
        wanted = " ".join(args["question"].lower().split())
        found = [i for i in items if wanted in i["question"].lower() or i["question"].lower() in wanted]
        if len(found) != 1:
            return {"ok": False, "action": "say", "msg": "I could not tell which answer you mean. Open Form answers for this job and name the question."
                    if items else "This job has no form answers yet. Draft them first."}
        cv_text = self._cv.text()
        if not cv_text.strip():
            return {"ok": False, "action": "say", "msg": "Your master CV could not be read, so the answer cannot be checked against it."}
        try:
            new = form_answers.rewrite(job, cv_text, found[0]["question"], found[0]["answer"], args["how"], config.experience_notes())
        except Exception as e:  # noqa: BLE001 - said to the person as the reason
            return {"ok": False, "action": "say", "msg": f"The answer could not be rewritten: {str(e) or type(e).__name__}"}
        return {"ok": True, "action": "confirm", "say": "", "preview": new["answer"] + (f"\n\nCheck: {new['check']}" if new["check"] else ""),
                "ask": f"Replace the answer to “{found[0]['question'][:80]}” with this version?",
                "pending": {"name": "save_answer", "args": {"job": job["id"], "question": found[0]["question"], "answer": new["answer"]}}}

    # ── your yes ────────────────────────────────────────────────
    def assistant_confirm(self, pending):
        """Carry out what you agreed to. It is checked again here: only the actions the app itself offered are
        accepted. What was done can be taken back once with assistant_undo."""
        if not isinstance(pending, dict) or not isinstance(pending.get("args"), dict):
            return {"ok": False, "action": "say", "msg": "There is nothing waiting for your yes."}
        if self._editor.live is not None and pending.get("name") in ("many", "add_job"):
            return {"ok": False, "action": "say", "msg": "A search or scan is running. Ask me again when it has finished."}
        steps = pending["args"].get("actions") if pending.get("name") == "many" else [pending]
        if not isinstance(steps, list) or not 1 <= len(steps) <= assistant_brain.MAX_ACTIONS:
            return {"ok": False, "action": "say", "msg": "That is not something I can do on a yes."}
        said, undo, last_job = [], [], ""
        for step in steps:
            ok, words, back = self._do(step if isinstance(step, dict) else {})
            if not ok:
                if undo:                            # nothing done this time: what could be taken back before still can
                    self._undo = undo
                done = (" Before that: " + " ".join(said)) if said else ""
                return {"ok": False, "action": "say", "msg": words + done, "changed": bool(said), "can_undo": bool(undo)}
            said.append(words)
            last_job = str((step.get("args") or {}).get("job") or last_job)
            if back:
                undo.append(back)
        self._undo = undo
        text = " ".join(said)
        self._turn("bot", text)
        return {"ok": True, "action": "done", "say": text, "job_id": last_job, "changed": True, "can_undo": bool(undo)}

    def _do(self, step: dict[str, Any]) -> tuple[bool, str, dict[str, Any] | None]:
        """One agreed step: (did it work, what to say, how to take it back)."""
        name, args = step.get("name"), step.get("args") if isinstance(step.get("args"), dict) else {}
        if name == "add_job":
            return self._add_job(args.get("record"))
        jobs = store.load_jobs()
        job = store.find(jobs, str(args.get("job") or ""))
        if not job:
            return False, NO_JOB, None
        what = f"{job.get('title', '')} at {job.get('company', '')}"
        before = {j["id"]: copy.deepcopy(j) for j in jobs}

        def back() -> dict[str, Any]:           # the job as it was, and any lead that marking it applied folded away
            now = {j["id"] for j in store.load_jobs()}
            return {"kind": "job", "job": copy.deepcopy(before[job["id"]]), "gone": [before[i] for i in before if i not in now], "what": what}
        if name == "mark_applied":
            done, said = self._app.apply_job(job["id"]), f"Moved {what} to Applications, as waiting."
        elif name == "set_status" and args.get("status") in assistant_brain.STATUSES:
            done, said = self._app.set_status(job["id"], args["status"]), f"{what} is now “{args['status'].replace('_', ' ')}”."
        elif name == "set_date":
            done = self._app.set_event(job["id"], str(args.get("day") or ""), str(args.get("time") or ""), str(args.get("kind") or "interview"), str(args.get("note") or ""))
            said = f"The date is set for {what}: {args.get('kind', 'interview')} on {args.get('day', '')}" + (f" at {args['time']}." if args.get("time") else ".")
        elif name == "not_interested":
            done, said = self._app.dismiss_job(job["id"]), f"Removed {what} from New Jobs. Its documents are in the backup."
            return (True, said, {"kind": "dismissed", "id": job["id"], "what": what}) if done.get("ok") else (False, done.get("msg") or "That did not work.", None)
        elif name == "save_letter" and isinstance(args.get("paragraphs"), list):
            old = self._app.letter_for_edit(job["id"])
            done, said = self._app.save_letter(job["id"], [str(p) for p in args["paragraphs"]]), f"The letter for {job.get('company', '')} is changed."
            if done.get("ok") and done.get("warnings"):
                said += " Look at it once: " + "; ".join(str(w) for w in done["warnings"][:3])
            return (True, said, {"kind": "letter", "id": job["id"], "paragraphs": list(old.get("paragraphs") or []), "what": what} if old.get("ok") else None) \
                if done.get("ok") else (False, done.get("msg") or "That did not work.", None)
        elif name == "save_answer" and str(args.get("answer") or "").strip():
            question, answer = str(args.get("question") or ""), str(args["answer"]).strip()

            def keep(current, j):       # may run twice (the running search's copy): the result is the same
                items = form_answers.tidy((j.get("form_answers") or {}).get("items"))
                for it in items:
                    if it["question"].lower() == question.lower():
                        it["answer"], it["check"] = answer, ""
                j["form_answers"] = {"made": (j.get("form_answers") or {}).get("made") or form_answers.stamp(), "items": items}
            done, said = self._editor.change(job["id"], keep, render=False), "The answer is changed and kept with the job."
            if done.get("ok"):
                answer_memory.remember(question, answer, job.get("company", ""))
        else:
            return False, "That is not something I can do on a yes.", None
        if not done.get("ok"):
            return False, done.get("msg") or "That did not work. The job may have changed in the meantime.", None
        return True, said, back()

    def _add_job(self, record) -> tuple[bool, str, dict[str, Any] | None]:
        """Put a posting that was read from the browser into New Jobs, as the lead the app scored."""
        if not isinstance(record, dict) or not str(record.get("title") or "").strip() or not str(record.get("url") or "").lower().startswith(("http://", "https://")):
            return False, "That posting cannot be added: it has no title or no address.", None
        if not isinstance(record.get("match_score"), int) or not 0 <= record["match_score"] <= 100:
            return False, "That posting cannot be added: it has no score.", None
        jobs = store.load_jobs()
        job = store.new_job(**{k: (v if k == "match_score" else str(v or "")[:20000]) for k, v in record.items() if k in store.new_job()})
        job.update(id="assistant-" + store.url_id(job["url"]), source="assistant", status="found", date_applied="",
                   cover_letter_file="", tailored_cv_file="", date_found=date.today().isoformat(), last_update=date.today().isoformat())
        for extra in ("score_capped",):
            if extra in record:
                job[extra] = record[extra]
        if store.find(jobs, job["id"]) or any(j.get("url") == job["url"] for j in jobs):
            return False, "That posting is in your list already.", None
        jobs.append(job)
        store.save_jobs(jobs)
        agent4_tracker.render_all(jobs)
        return True, f"Added {job['title']} at {job['company']} to New Jobs with a score of {job['match_score']}.", {"kind": "added", "id": job["id"], "what": f"{job['title']} at {job['company']}"}

    def assistant_undo(self):
        """Take back what the last yes did: the job as it was before, a removed lead restored, a letter's old text, an added posting removed."""
        steps = self._undo
        if not steps:
            return {"ok": False, "action": "say", "msg": "There is nothing to take back."}
        if self._editor.live is not None:
            return {"ok": False, "action": "say", "msg": "A search or scan is running. Take it back in the job's own window, or ask me again when it has finished."}
        said = []
        for step in reversed(steps):
            if step["kind"] == "dismissed":
                ok = bool(self._app.restore_job(step["id"]).get("ok"))
            elif step["kind"] == "letter":
                ok = bool(self._app.save_letter(step["id"], step["paragraphs"]).get("ok"))
            else:
                jobs = store.load_jobs()
                if step["kind"] == "added":
                    kept = [j for j in jobs if j["id"] != step["id"] or j.get("status") != "found" or j.get("cover_letter_file") or j.get("tailored_cv_file")]
                    ok = len(kept) < len(jobs)       # only while it is still the bare lead that was added
                    jobs = kept
                else:
                    index = next((i for i, j in enumerate(jobs) if j["id"] == step["job"]["id"]), -1)
                    ok = index >= 0
                    if ok:
                        jobs[index] = step["job"]
                        have = {j["id"] for j in jobs}
                        jobs += [j for j in step["gone"] if j["id"] not in have]
                if ok:
                    store.save_jobs(jobs)
                    agent4_tracker.render_all(jobs)
            said.append(f"{step['what']} is as it was before." if ok else f"{step['what']} could not be put back: it changed in the meantime.")
        self._undo = []
        text = " ".join(said)
        self._turn("bot", text)
        return {"ok": True, "action": "done", "say": text, "changed": True, "can_undo": False}

    # ── practising an interview ─────────────────────────────────
    def assistant_practice(self, job_id):
        """Start practising: the questions of the job's interview preparation, one at a time. The ones that went
        badly before come first, then the ones never practised."""
        job = store.find(store.load_jobs(), job_id)
        if not job:
            return {"ok": False, "action": "say", "msg": NO_JOB}
        prep = job.get("interview_prep") or {}
        questions = [str(q.get("question") or "") for q in [prep.get("key_question") or {}] + list(prep.get("questions") or []) if q.get("question")]
        if not questions:
            return {"ok": False, "action": "say", "msg": f"There is no interview preparation for {job.get('title', '')} at {job.get('company', '')} yet. "
                                                         "Open the application and build it first; the practice uses its questions."}
        past = job.get("practice") or {}
        rank = {"weak": 0, None: 1, "ok": 2, "good": 3}
        ordered = sorted(dict.fromkeys(questions), key=lambda q: rank.get((past.get(q) or {}).get("rating"), 1))[:20]
        weak = sum(1 for q in ordered if (past.get(q) or {}).get("rating") == "weak")
        return {"ok": True, "action": "practice", "job_id": job["id"], "job": f"{job.get('title', '')} at {job.get('company', '')}",
                "questions": ordered, "last": [(past.get(q) or {}).get("rating") or "" for q in ordered],
                "say": f"Let us practise for {job.get('title', '')} at {job.get('company', '')}: {len(ordered)} questions"
                       + (f", starting with the {weak} that went badly last time" if weak else "")
                       + ". Type your answer as you would say it; I tell you what is good and what is missing. Say stop to end."}

    def assistant_practice_answer(self, job_id, question, answer):
        """What Claude makes of one practice answer (one call). Only how it went is kept (good, ok, weak), not what you typed."""
        job = store.find(store.load_jobs(), job_id)
        if not job:
            return {"ok": False, "action": "say", "msg": NO_JOB}
        answer = str(answer or "").strip()
        if len(answer.split()) < 3:
            return {"ok": False, "action": "practice_feedback", "msg": "Answer in a sentence or two, as you would in the interview."}
        if len(answer) > 3000:
            return {"ok": False, "action": "practice_feedback", "msg": f"That is {len(answer)} characters; an answer you would say aloud fits in 3000."}
        cv_text = self._cv.text()
        if not cv_text.strip():
            return {"ok": False, "action": "practice_feedback", "msg": "Your master CV could not be read, so I cannot compare your answer with it."}
        prep = job.get("interview_prep") or {}
        known = {str(q.get("question") or ""): str(q.get("answer") or "") for q in (prep.get("questions") or []) + [prep.get("key_question") or {}]}
        try:
            made = assistant_brain.feedback(job, cv_text, question, known.get(str(question), ""), answer)
        except Exception as e:  # noqa: BLE001 - said to the person as the reason
            return {"ok": False, "action": "practice_feedback", "msg": f"I could not ask Claude: {str(e) or type(e).__name__}"}
        if not made["feedback"]:
            return {"ok": False, "action": "practice_feedback", "msg": "Claude gave no answer. Try that one again."}
        today, asked = date.today().isoformat(), str(question)[:300]

        def keep(jobs, j):          # may run twice (the running search's copy): the result is the same
            notes = dict(j.get("practice") or {})
            notes[asked] = {"rating": made["rating"], "when": today}
            j["practice"] = dict(list(notes.items())[-40:])
        if asked in known:
            self._editor.change(job_id, keep, render=False)
        return {"ok": True, "action": "practice_feedback", "say": made["feedback"], "rating": made["rating"]}

    def assistant_notes_list(self):
        try:
            return {"notes": assistant_notes.notes()}
        except Exception:  # noqa: BLE001
            return {"notes": []}

    def assistant_forget_note(self, number):
        return assistant_notes.forget(number)

    # ── what the assistant says without being asked ─────────────
    def assistant_briefing(self):
        """What is worth your attention when the app opens, worked out from your data without Claude:
        {"headline" (for the robot's bubble, '' when there is nothing), "lines", "nudges": [{text, job_id, kind}]}."""
        from . import summary
        try:
            jobs, responses = store.load_jobs(), db.all_responses()
        except Exception:  # noqa: BLE001 - locked data: nothing to say yet
            return {"headline": "", "lines": [], "nudges": []}
        now = date.today()
        week = summary.week(jobs, responses, int(self._app.options().get("followup_days") or 0), now)
        lines = []
        if week["ready_total"]:
            lines.append(f"{week['ready_total']} {'job is' if week['ready_total'] == 1 else 'jobs are'} ready to send" + (f" ({week['new_ready']} new this week)" if week["new_ready"] else ""))
        if week["invites"]:
            lines.append(f"{week['invites']} {'reply' if week['invites'] == 1 else 'replies'} this week that {'looks' if week['invites'] == 1 else 'look'} like an invitation")
        if week["followups"]:
            lines.append(f"{week['followups']} follow-up{'' if week['followups'] == 1 else 's'} due")
        lines += [c["text"] for c in week["coming"][:3]]
        nudges = []
        last: dict[str, dict[str, Any]] = {}
        for r in responses:
            if r.get("job_id") and r["job_id"] not in last:
                last[r["job_id"]] = r
        for j in jobs:
            what, done = f"{j.get('title', '')} at {j.get('company', '')}", set(j.get("nudged") or [])
            filled = str(j.get("form_filled") or "")
            if j.get("status") in store.LEAD_STATUSES and filled and filled < now.isoformat() and "apply" not in done:
                nudges.append({"kind": "apply", "job_id": j["id"], "text": f"You filled in the form for {what} on {filled} but did not mark it applied."})
            event = j.get("event") or {}
            if event.get("kind") == "interview" and event.get("date") and "prep" not in done and not (j.get("interview_prep") or {}).get("questions"):
                try:
                    away = (date.fromisoformat(event["date"]) - now).days
                except ValueError:
                    away = -1
                if 0 <= away <= 2:
                    when = ("today", "tomorrow", "in two days")[away]
                    nudges.append({"kind": "prep", "job_id": j["id"], "text": f"The interview for {what} is {when} and there is no preparation yet."})
            reply = last.get(j["id"])
            if reply and reply.get("stage") in ("interview", "assessment") and j.get("status") in store.APPLICATION_STATUSES - {"rejected"} \
                    and not event.get("date") and "date" not in done:
                when = db.received_at(reply.get("received_date", "")).date()
                if 0 <= (now - when).days <= 14:
                    nudges.append({"kind": "date", "job_id": j["id"], "text": f"{j.get('company', '')} invited you on {when.isoformat()} and no date is set for it."})
        nudges = nudges[:6]
        headline = nudges[0]["text"] if nudges else ("; ".join(lines[:3]) + "." if lines else "")
        return {"headline": headline[:220], "lines": lines, "nudges": nudges}

    def assistant_nudge_done(self, job_id, kind):
        """Stop reminding about this (you looked at it, or it does not apply)."""
        if kind not in ("apply", "prep", "date"):
            return {"ok": False}

        def go(jobs, j):            # may run twice (the running search's copy): the result is the same
            j["nudged"] = sorted(set(j.get("nudged") or []) | {kind})
        return {"ok": bool(self._editor.change(job_id, go, render=False).get("ok"))}

    def browser(self) -> str:
        """Speak to the browser chosen in the assistant's settings (Chrome unless another one was chosen)."""
        try:
            return chrome.use(self._app.options().get("assistant_browser"))
        except Exception:  # noqa: BLE001 - unreadable settings: Chrome
            return chrome.use(None)

    def assistant_browser(self):
        key = self.browser()
        return {"key": key, "name": chrome.name(key), "short": chrome.short(key), "switch": chrome.browser(key).switch,
                "all": [{"key": b.key, "name": b.app} for b in chrome.BROWSERS.values()]
                       + [{"key": k, "name": f"{u.name} (not possible)"} for k, u in chrome.NOT_POSSIBLE.items()]}

    def assistant_set_browser(self, key):
        """Choose the browser forms are filled in: Chrome, Brave, Edge, Opera or Safari."""
        if key in chrome.NOT_POSSIBLE:
            return {"ok": False, "msg": chrome.NOT_POSSIBLE[key].reason, **self.assistant_browser()}
        if key not in chrome.BROWSERS:
            return {"ok": False, "msg": "Choose one of: " + ", ".join(b.app for b in chrome.BROWSERS.values()) + "."}
        saved = self._app.save_options({"assistant_browser": key})
        self._noticed = set()
        return {"ok": bool(saved.get("ok")), "msg": saved.get("msg", ""), **self.assistant_browser()}

    def assistant_watching(self):
        return bool(self._app.options().get("assistant_watch"))

    def assistant_set_watch(self, on):
        """Turn noticing a form in Chrome on or off. It is off until you turn it on: it means looking at the
        address of the tab in front every little while."""
        if not isinstance(on, bool):
            return {"ok": False, "msg": "Noticing a form is on or off."}
        saved = self._app.save_options({"assistant_watch": on})
        self._noticed = set()
        return {"ok": bool(saved.get("ok")), "on": on, "msg": saved.get("msg", "")}

    def assistant_notice(self):
        """Is the tab in front the application form of a job you track? Only when you turned this on, and each
        page is offered once. Looks at the tab's address and title and counts its empty fields; reads nothing else."""
        if not self.assistant_watching():
            return {"ok": False, "off": True}
        self.browser()
        try:
            tab = chrome.active_tab()
        except chrome.ChromeError as e:
            quiet = e.kind in ("not_running", "no_window")      # the browser simply not in use is nothing to report
            return {"ok": False, "problem": "" if quiet else str(e)}
        url = tab["url"]
        seen = self._noticed
        address = form_fill.PageAddress(url)
        if not address.is_web or address.refused or url in seen:
            return {"ok": False}
        jobs = [j for j in store.load_jobs() if j.get("status") in store.OPEN_STATUSES]
        job = store.find(jobs, form_fill.match_job(jobs, url, tab["title"]))
        if not job:
            return {"ok": False}
        try:
            page = form_fill.watch_answer(chrome.run(form_fill.WATCH))
        except chrome.ChromeError as e:
            return {"ok": False, "problem": str(e)}
        if page["empty"] < 3:
            return {"ok": False}                    # the posting itself, or a form that is filled in already
        seen.add(url)
        self._noticed = seen
        return {"ok": True, "job_id": job["id"], "job": f"{job.get('title', '')} at {job.get('company', '')}", "url": url,
                "say": f"This looks like the form for {job.get('title', '')} at {job.get('company', '')}. Tap me and I fill it in."}

    # ── the facts a review or a choice is checked against ───────
    def facts(self, job) -> str:
        return form_choices.facts_block(self._cv.text(), details.load(), job)

    @staticmethod
    def pay(job) -> str:
        stated = salary.stated(job, salary.asked(job)[1]) if job else None
        return str((stated or {}).get("text") or "") if isinstance(stated, dict) else ""
