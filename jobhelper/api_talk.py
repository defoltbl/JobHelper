"""Talking with the assistant: a request in free words, the action it leads to, and your yes
before anything of yours is changed."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from . import answer_memory, assistant, assistant_brain, chrome, config, db, details, form_answers, form_choices, form_fill, insights, mailhosts, planner, salary, store

_PLAIN = re.compile(r"\b(?:but|skip|except|without|only|not|don't|do not|leave|and)\b")
NO_JOB = "That job is not in the list any more."


class TalkApi:
    # ── what the talk remembers ─────────────────────────────────
    def _turn(self, who: str, text: str) -> None:
        turns = getattr(self, "_turns", [])
        turns.append((who, " ".join(str(text or "").split())[:assistant_brain.MAX_TURN]))
        self._turns = turns[-2 * assistant_brain.MAX_TURNS:]

    def assistant_new_talk(self):
        self._turns = []
        return {"ok": True}

    def _numbers(self) -> str:
        c = self.counts()
        return (f"{c.get('leads', 0)} leads in New Jobs, {c.get('applications', 0)} applications, "
                f"{c.get('responses', 0)} replies read, {c.get('followups', 0)} follow-ups due")

    # ── one request ─────────────────────────────────────────────
    def assistant_talk(self, text, context_job="", chosen_job=""):
        """What the assistant does with a request. The fixed requests ("fill in the form", "my details",
        "help") cost nothing; anything else is one call to Claude, which answers or names one action.
        `context_job` is the job whose window is open, `chosen_job` the one picked in the assistant's list."""
        problem = assistant.check(text)
        if problem:
            return {"ok": False, "action": "none", "msg": problem}
        words = " ".join(str(text).split())
        job_id = context_job or chosen_job
        what = assistant.intent(words)
        if what in ("fill", "details", "help") and len(words.split()) <= 6 and not _PLAIN.search(words.lower()):
            out = self.assistant_ask(words, job_id)
            self._turn("you", words)
            self._turn("bot", out.get("say") or out.get("msg") or "")
            return out
        if what == "unknown":
            return {"ok": True, "action": "help", "say": assistant.UNKNOWN}
        jobs = store.load_jobs()
        try:
            decided = assistant_brain.decide(words, jobs, db.all_responses(), getattr(self, "_turns", []), assistant.ABOUT, self._numbers(),
                                             store.find(jobs, job_id) if job_id else None)
        except Exception as e:  # noqa: BLE001 - said to the person as the reason
            return {"ok": False, "action": "say", "msg": f"I could not ask Claude: {str(e) or type(e).__name__}"}
        self._turn("you", words)
        rows = [{"id": j["id"], "label": f"{j.get('company', '')} · {j.get('title', '')}",
                 "sub": str(j.get("status", "")).replace("_", " ") + (f" · score {j['match_score']}" if j.get("match_score") is not None else "")}
                for j in (store.find(jobs, i) for i in decided["show"]) if j]
        action = decided["action"]
        if action is None:
            say = decided["say"] + (" (I could not carry that out as an action: say which job you mean, or use the job's own window.)" if decided["dropped"] else "")
            self._turn("bot", say)
            return {"ok": True, "action": "say", "say": say, "rows": rows}
        out = self._act(action, decided["say"], jobs, job_id)
        out.setdefault("rows", rows)
        self._turn("bot", out.get("say") or out.get("ask") or out.get("msg") or "")
        return out

    def _act(self, action: dict[str, Any], say: str, jobs: list[dict[str, Any]], job_id: str) -> dict[str, Any]:
        name, args = action["name"], action["args"]
        job = store.find(jobs, args["job"]) if args.get("job") else None
        if "job" in args and not job:
            return {"ok": False, "action": "say", "msg": NO_JOB}
        if name == "fill_form":
            return self.assistant_fill(job_id, skip=args.get("skip") or [])
        if name == "review_form":
            return self.assistant_review(job_id)
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
        if name == "rewrite_letter":
            return self._rewrite_letter(job, args)
        if name == "rewrite_answer":
            return self._rewrite_answer(job, args)
        # what is left changes your data: described in the app's own words, done only after your yes
        if name == "mark_applied" and job["status"] not in store.LEAD_STATUSES:
            return {"ok": False, "action": "say", "msg": f"{job.get('title', '')} at {job.get('company', '')} is already among your applications."}
        if name == "not_interested" and job["status"] not in store.LEAD_STATUSES:
            return {"ok": False, "action": "say", "msg": "Only a lead in New Jobs can be marked not interested. For an application, set its status instead."}
        if name == "set_date":
            _day, problem = planner.check_event(args["day"], args.get("time", ""), args.get("kind", "interview"))
            if problem:
                return {"ok": False, "action": "say", "msg": problem}
        return {"ok": True, "action": "confirm", "ask": assistant_brain.asks(action, job), "pending": action, "say": ""}

    def _said(self, make) -> dict[str, Any]:
        try:
            said = make()
        except Exception as e:  # noqa: BLE001 - said to the person as the reason
            return {"ok": False, "action": "say", "msg": f"I could not ask Claude: {str(e) or type(e).__name__}"}
        return {"ok": True, "action": "say", "say": said} if said else {"ok": False, "action": "say", "msg": "Claude gave no answer. Ask again in other words."}

    def _results(self) -> dict[str, Any]:
        """The numbers of the Insights view, as the advice is built from them."""
        jobs, responses = store.load_jobs(), db.all_responses()
        threshold = int(self.options().get("threshold") or 30)
        return {"what_works": insights.what_works(jobs, responses), "skill_gaps": insights.skill_gaps(jobs, self._cv_text()),
                "reply_times": insights.reply_times(jobs, responses), "low_scores": insights.low_score_reasons(jobs, self._cv_text(), threshold),
                "smallest_group_that_counts": insights.MIN_GROUP}

    # ── edits by instruction: shown first, saved after your yes ──
    def _rewrite_letter(self, job, args) -> dict[str, Any]:
        letter = self.letter_for_edit(job["id"])
        if not letter.get("ok"):
            return {"ok": False, "action": "say", "msg": letter.get("msg") or "This letter cannot be changed here."}
        paragraphs = list(letter["paragraphs"])
        index = args["paragraph"] - 1
        if not 0 <= index < len(paragraphs):
            return {"ok": False, "action": "say", "msg": f"The letter has {len(paragraphs)} paragraphs; there is no paragraph {args['paragraph']}."}
        new = self.rewrite_paragraph(job["id"], paragraphs, index, args["how"])
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
        cv_text = self._cv_text()
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
        """Carry out an action you agreed to. It is checked again here: only the actions the app itself offered are accepted."""
        if not isinstance(pending, dict) or not isinstance(pending.get("args"), dict):
            return {"ok": False, "action": "say", "msg": "There is nothing waiting for your yes."}
        name, args = pending.get("name"), pending["args"]
        job = store.find(store.load_jobs(), str(args.get("job") or ""))
        if not job:
            return {"ok": False, "action": "say", "msg": NO_JOB}
        what = f"{job.get('title', '')} at {job.get('company', '')}"
        if name == "mark_applied":
            done, said = self.apply_job(job["id"]), f"Moved {what} to Applications, as waiting."
        elif name == "set_status" and args.get("status") in assistant_brain.STATUSES:
            done, said = self.set_status(job["id"], args["status"]), f"{what} is now “{args['status'].replace('_', ' ')}”."
        elif name == "set_date":
            done = self.set_event(job["id"], str(args.get("day") or ""), str(args.get("time") or ""), str(args.get("kind") or "interview"), str(args.get("note") or ""))
            said = f"The date is set for {what}: {args.get('kind', 'interview')} on {args.get('day', '')}" + (f" at {args['time']}." if args.get("time") else ".")
        elif name == "not_interested":
            done, said = self.dismiss_job(job["id"]), f"Removed {what} from New Jobs. Its documents are in the backup."
        elif name == "save_letter" and isinstance(args.get("paragraphs"), list):
            done, said = self.save_letter(job["id"], [str(p) for p in args["paragraphs"]]), f"The letter for {job.get('company', '')} is changed."
            if done.get("ok") and done.get("warnings"):
                said += " Look at it once: " + "; ".join(str(w) for w in done["warnings"][:3])
        elif name == "save_answer" and str(args.get("answer") or "").strip():
            question, answer = str(args.get("question") or ""), str(args["answer"]).strip()

            def keep(jobs, j):          # may run twice (the running search's copy): the result is the same
                items = form_answers.tidy((j.get("form_answers") or {}).get("items"))
                for it in items:
                    if it["question"].lower() == question.lower():
                        it["answer"], it["check"] = answer, ""
                j["form_answers"] = {"made": (j.get("form_answers") or {}).get("made") or form_answers.stamp(), "items": items}
            done, said = self._change(job["id"], keep, render=False), "The answer is changed and kept with the job."
            if done.get("ok"):
                answer_memory.remember(question, answer, job.get("company", ""))
        else:
            return {"ok": False, "action": "say", "msg": "That is not something I can do on a yes."}
        if not done.get("ok"):
            return {"ok": False, "action": "say", "msg": done.get("msg") or "That did not work. The job may have changed in the meantime."}
        self._turn("bot", said)
        return {"ok": True, "action": "done", "say": said, "job_id": job["id"], "changed": True}

    # ── practising an interview ─────────────────────────────────
    def assistant_practice(self, job_id):
        """Start practising: the questions of the job's interview preparation, one at a time."""
        job = store.find(store.load_jobs(), job_id)
        if not job:
            return {"ok": False, "action": "say", "msg": NO_JOB}
        prep = job.get("interview_prep") or {}
        questions = [{"question": str(q.get("question") or ""), "basis": str(q.get("answer") or "")} for q in (prep.get("questions") or []) if q.get("question")]
        key = prep.get("key_question") or {}
        if key.get("question"):
            questions.insert(0, {"question": str(key["question"]), "basis": str(key.get("answer") or "")})
        if not questions:
            return {"ok": False, "action": "say", "msg": f"There is no interview preparation for {job.get('title', '')} at {job.get('company', '')} yet. "
                                                         "Open the application and build it first; the practice uses its questions."}
        return {"ok": True, "action": "practice", "job_id": job["id"], "job": f"{job.get('title', '')} at {job.get('company', '')}",
                "questions": [q["question"] for q in questions[:20]],
                "say": f"Let us practise for {job.get('title', '')} at {job.get('company', '')}: {min(len(questions), 20)} questions. "
                       "Type your answer as you would say it; I tell you what is good and what is missing. Say stop to end."}

    def assistant_practice_answer(self, job_id, question, answer):
        """What Claude makes of one practice answer (one call). Nothing is saved."""
        job = store.find(store.load_jobs(), job_id)
        if not job:
            return {"ok": False, "action": "say", "msg": NO_JOB}
        answer = str(answer or "").strip()
        if len(answer.split()) < 3:
            return {"ok": False, "action": "practice_feedback", "msg": "Answer in a sentence or two, as you would in the interview."}
        if len(answer) > 3000:
            return {"ok": False, "action": "practice_feedback", "msg": f"That is {len(answer)} characters; an answer you would say aloud fits in 3000."}
        cv_text = self._cv_text()
        if not cv_text.strip():
            return {"ok": False, "action": "practice_feedback", "msg": "Your master CV could not be read, so I cannot compare your answer with it."}
        prep = job.get("interview_prep") or {}
        known = {str(q.get("question") or ""): str(q.get("answer") or "") for q in (prep.get("questions") or []) + [prep.get("key_question") or {}]}
        out = self._said(lambda: assistant_brain.feedback(job, cv_text, question, known.get(str(question), ""), answer))
        out["action"] = "practice_feedback"
        return out

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
        week = summary.week(jobs, responses, int(self.options().get("followup_days") or 0), now)
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
        return {"ok": bool(self._change(job_id, go, render=False).get("ok"))}

    def assistant_watching(self):
        return bool(self.options().get("assistant_watch"))

    def assistant_set_watch(self, on):
        """Turn noticing a form in Chrome on or off. It is off until you turn it on: it means looking at the
        address of the tab in front every little while."""
        if not isinstance(on, bool):
            return {"ok": False, "msg": "Noticing a form is on or off."}
        saved = self.save_options({"assistant_watch": on})
        self._noticed = set()
        return {"ok": bool(saved.get("ok")), "on": on, "msg": saved.get("msg", "")}

    def assistant_notice(self):
        """Is the tab in front the application form of a job you track? Only when you turned this on, and each
        page is offered once. Looks at the tab's address and title and counts its empty fields; reads nothing else."""
        if not self.assistant_watching():
            return {"ok": False, "off": True}
        try:
            tab = chrome.active_tab()
        except chrome.ChromeError as e:
            quiet = str(e) in (chrome.NOT_RUNNING, chrome.NO_WINDOW)      # Chrome simply not in use is nothing to report
            return {"ok": False, "problem": "" if quiet else str(e)}
        url = tab["url"]
        seen = getattr(self, "_noticed", set())
        if not url.lower().startswith(("http://", "https://")) or url in seen or mailhosts.never_used(form_fill.host_of(url)):
            return {"ok": False}
        jobs = [j for j in store.load_jobs() if j.get("status") in store.LEAD_STATUSES | {"waiting", "interview", "on_hold"}]
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
    def _facts(self, job) -> str:
        return form_choices.facts_block(self._cv_text(), details.load(), job)

    @staticmethod
    def _pay(job) -> str:
        stated = salary.stated(job, salary.asked(job)[1]) if job else None
        return str((stated or {}).get("text") or "") if isinstance(stated, dict) else ""

