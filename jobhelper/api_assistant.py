"""The assistant's part of the window's back end: your details, and filling in the form that is open in Chrome."""
from __future__ import annotations

import os

from . import (answer_memory, assistant, assistant_brain, chrome, config, details, form_answers, form_fill, form_run,
               mailhosts, salary, store)
from .api_base import _guarded


class AssistantService:
    """Your details, your answers, and the assistant's work on the form in the browser."""

    def __init__(self, app, editor, cv, desktop) -> None:
        """`app` is the facade (`ui_api.Api`): what this service needs from the others is asked through it."""
        self._app, self._editor, self._cv, self._desktop = app, editor, cv, desktop
        self._last_fill = None      # what the last fill found, for the buttons under the answer
    # ── My details ──────────────────────────────────────────────
    @_guarded(dict)
    def my_details(self):
        """What the page shows: the saved details, and in empty fields what the CV plainly states (offered, not saved)."""
        kept = details.load()
        offered = details.from_cv(self._cv.text(), self._cv.name())
        from_cv = [key for key in details.KEYS if not kept[key] and offered.get(key)]
        return {"details": {key: kept[key] or offered.get(key, "") for key in details.KEYS}, "from_cv": from_cv,
                "saved": details.any_given(kept),
                "fields": [{"key": key, "label": label, "most": most} for key, label, most in details.FIELDS],
                "columns": {name: [{"key": key, "label": label, "most": most, "long": key in details.LONG} for key, label, most in cols]
                            for name, cols in details.ROWS.items()},
                "experience": kept["experience"], "education": kept["education"], "languages": kept["languages"],
                "levels": list(details.LEVELS),
                "files": [{**f, "name": os.path.basename(f["path"])} for f in kept["files"]],
                "salary_amount": kept["salary_amount"], "salary_currency": kept["salary_currency"], "salary_period": kept["salary_period"],
                "currencies": list(salary.CURRENCIES), "periods": list(details.PERIODS), "max_rows": details.MAX_ROWS}

    def assistant_cv_lists(self):
        """The jobs and degrees your CV states, read by Claude in one call, to offer in the page (nothing is saved)."""
        try:
            found = details.lists_from_cv(self._cv.text())
        except Exception as e:  # noqa: BLE001 - said to the person as the reason
            return {"ok": False, "msg": f"I could not read them from your CV: {str(e) or type(e).__name__}"}
        if not found["experience"] and not found["education"] and not found.get("languages"):
            return {"ok": False, "msg": "I found no jobs or degrees written in your CV in a way I can copy. Add them by hand."}
        spoken = len(found.get("languages") or [])
        return {"ok": True, **found, "say": f"I read {len(found['experience'])} jobs and {len(found['education'])} degrees"
                                              f"{f' and {spoken} languages' if spoken else ''} from your CV. "
                                              "They are on the My details page, not saved yet: check them, then save."}

    # ── answers of your own, for questions every form asks ──────
    @_guarded(dict)
    def my_answers(self):
        kept = answer_memory.entries()
        have = {answer_memory.key(i["question"]) for i in kept}
        return {"items": kept, "starters": [q for q in assistant.STARTERS if answer_memory.key(q) not in have]}

    def save_my_answer(self, question, answer, was=""):
        """Keep an answer in your own words (a changed question replaces the old entry)."""
        problem = assistant.check_answer(question, answer)
        if problem:
            return {"ok": False, **problem}
        question = " ".join(str(question).split())
        if was and answer_memory.key(was) != answer_memory.key(question):
            answer_memory.forget(was)
        if not answer_memory.remember(question, str(answer).strip()):
            return {"ok": False, "field": "answer", "msg": "That answer could not be kept."}
        return {"ok": True}

    def delete_my_answer(self, question):
        return {"ok": answer_memory.forget(str(question or ""))}

    def draft_my_answer(self, question):
        """A first draft of an answer from your CV (one Claude call). It is yours only once you read it and save it."""
        question = " ".join(str(question or "").split())
        problem = assistant.check_answer(question, "x")
        if problem:
            return {"ok": False, **problem}
        if assistant.about_one_company(question):
            return {"ok": False, "field": "question", "msg": assistant.ABOUT_ONE_COMPANY}
        cv_text = self._cv.text()
        if not cv_text.strip():
            return {"ok": False, "field": "answer", "msg": "Your master CV could not be read, so no answer can be built from it."}
        mine = details.load()
        general = {"title": "any role this candidate applies for (do not name a role)", "company": "not known (do not name a company)",
                   "location": "", "description": "", "desired_monthly_czk": ""}
        notes = "\n".join([config.experience_notes()] + details.facts(mine)).strip()
        try:
            item = form_answers.generate(general, cv_text, [question], notes)[0]
        except Exception as e:  # noqa: BLE001 - said to the person as the reason
            return {"ok": False, "field": "answer", "msg": f"The answer could not be drafted: {str(e) or type(e).__name__}"}
        return {"ok": True, "question": question, "answer": item["answer"], "check": item["check"],
                "say": "Drafted from your CV. Read it, make it yours, then save."}

    def check_my_details(self, values):
        """{} or {"field", "msg"}: what is wrong with what is typed, before anything is saved."""
        return details.check(dict(values) if isinstance(values, dict) else values)[1]

    def save_my_details(self, values):
        return details.save(dict(values) if isinstance(values, dict) else values)

    # ── the jobs a form can be for ──────────────────────────────
    @_guarded(list)
    def assistant_jobs(self):
        """Leads and open applications, newest first, to choose the job a form belongs to."""
        open_ones = [j for j in store.load_jobs() if j.get("status") in store.OPEN_STATUSES]
        open_ones.sort(key=lambda j: str(j.get("found_date") or j.get("date") or ""), reverse=True)
        return [{"id": j["id"], "label": f"{j.get('company', '')} · {j.get('title', '')}"} for j in open_ones[:300]]

    # ── a request typed to the assistant ────────────────────────
    def assistant_ask(self, text, job_id=""):
        """What the assistant does with a typed request: {"ok", "action", "say" or "msg", ...}."""
        problem = assistant.check(text)
        if problem:
            return {"ok": False, "action": "none", "msg": problem}
        what = assistant.intent(text)
        if what == "fill":
            return self.assistant_fill(job_id)
        if what == "details":
            return {"ok": True, "action": "details", "say": "Here are your details. Change what is wrong and save."}
        return {"ok": True, "action": "help", "say": assistant.HELP if what == "help" else assistant.UNKNOWN}

    # ── small helpers the window offers after a fill ────────────
    def assistant_open_form(self, url, job_id=""):
        """Open a form that sits in a frame in a tab of its own (the address comes from the page that was read), and fill
        it in there once it has loaded: one press for what used to be a press and a second request."""
        url = str(url or "").strip()
        host = form_fill.host_of(url)
        if not url.lower().startswith(("http://", "https://")) or not host or len(url) > 2000:
            return {"ok": False, "msg": "That is not a web address I can open."}
        if mailhosts.never_used(host):
            return {"ok": False, "msg": "This app does not work with Russian services, so I do not open this site."}
        self._app.browser()
        try:
            chrome.open_tab(url)
        except chrome.ChromeError as e:
            return {"ok": False, "msg": str(e)}
        ready = False
        for wait in (1.0, 1.0, 1.5, 2.0, 2.5):          # the page gets time to load; a slow one is left to a second request
            chrome.pause(wait)
            try:
                tab = chrome.active_tab()
                ready = form_fill.host_of(tab["url"]) == host and bool(form_fill.read_answer(chrome.run(form_fill.READ))["fields"])
            except (chrome.ChromeError, ValueError):
                ready = False
            if ready:
                break
        if not ready:
            return {"ok": True, "action": "open_form", "say": f"I opened the form from {host} in a new tab. It is still loading: ask me to fill it in when you see it."}
        result = self.assistant_fill(job_id)
        if result.get("ok"):
            result["say"] = f"I opened the form from {host} in a tab of its own. " + result["say"]
        return result

    def assistant_files(self, job_id):
        """Show the CV and the letter of a job, and your own files (certificates, diplomas), in Finder,
        ready to be dragged into the form."""
        j = store.find(store.load_jobs(), job_id) if job_id else {}
        if j is None:
            return {"ok": False, "msg": "That job is not in the list any more."}
        shown = []
        for extra in details.load()["files"]:
            if os.path.isfile(extra["path"]):
                self._desktop.reveal(extra["path"])
                shown.append(f"{extra['label']} ({os.path.basename(extra['path'])})")
        for what, base, name in (("CV", config.TAILORED_CV_DIR, j.get("tailored_cv_file", "")), ("letter", config.LETTERS_DIR, j.get("cover_letter_file", ""))):
            if not name or os.path.basename(str(name)) != str(name):       # a file name, never a path out of the folder
                continue
            docx = (base / name).with_suffix(".docx")
            for path in (docx.with_suffix(".pdf"), docx, config.COVER_LETTERS_DIR / name):
                if path.is_file():
                    self._desktop.reveal(path)
                    shown.append(f"{what} ({path.name})")
                    break
        if not shown:
            return {"ok": False, "msg": "There is no CV or letter from the app for this job, and no file of your own under My details. Attach your files yourself."}
        return {"ok": True, "say": f"Shown in Finder: {', '.join(shown)}. Drag {'it' if len(shown) == 1 else 'them'} onto the form's file {'field' if len(shown) == 1 else 'fields'}."}

    def assistant_watch(self):
        """Where the form in front stands now: quiet on any trouble (it is asked every few seconds while the window waits)."""
        try:
            self._app.browser()
            return {"ok": True, **form_fill.watch_answer(chrome.run(form_fill.WATCH))}
        except Exception:  # noqa: BLE001 - not being able to look is not something to report
            return {"ok": False, "url": "", "sign": "", "empty": 0}

    def assistant_learn(self):
        """Take over what the person changed on the page in the answers the assistant wrote: kept with the job and
        remembered for the same question elsewhere. Only those fields are read back, nothing else on the page."""
        last = self._last_fill
        if not last or not last.get("items"):
            return {"ok": False, "msg": "There is nothing to compare with yet. Ask me to fill in a form first."}
        self._app.browser()
        try:
            now = form_fill.values_answer(chrome.run(form_fill.values_script([i["n"] for i in last["items"]], last["url"])))
        except chrome.ChromeError as e:
            return {"ok": False, "msg": str(e)}
        if not now:
            return {"ok": False, "msg": "The form is not in front any more, so I cannot see what you changed. Go back to it and ask again."}
        learned = []
        for item in last["items"]:
            value = now.get(item["n"], "").strip()
            if value and answer_memory.changed(item["value"], value) and answer_memory.remember(item["label"], value, last.get("company", "")):
                learned.append({"question": item["label"], "answer": value})
                item["value"] = value
        if learned and last.get("job_id"):
            new = {i["question"].lower(): i for i in learned}

            def keep(jobs, j):          # may run twice (the running search's copy): the result is the same
                items = form_answers.tidy((j.get("form_answers") or {}).get("items"))
                for it in items:
                    if it["question"].lower() in new:
                        it["answer"], it["check"] = new[it["question"].lower()]["answer"], ""
                have = {it["question"].lower() for it in items}
                items += [{"question": i["question"], "answer": i["answer"], "check": ""} for i in learned if i["question"].lower() not in have]
                j["form_answers"] = {"made": (j.get("form_answers") or {}).get("made") or form_answers.stamp(), "items": items}
            self._editor.change(last["job_id"], keep, render=False)
        if not learned:
            return {"ok": True, "learned": 0, "say": "You changed none of the answers I wrote, so there is nothing new to remember."}
        return {"ok": True, "learned": len(learned),
                "say": f"I will use your wording for {len(learned)} {'question' if len(learned) == 1 else 'questions'} from now on: "
                       + "; ".join(i["question"][:60] for i in learned[:4]) + ("…" if len(learned) > 4 else ".")}

    def assistant_memory(self):
        try:
            return {"count": answer_memory.count()}
        except Exception:  # noqa: BLE001
            return {"count": 0}

    def assistant_forget(self):
        return {"ok": True, "say": f"Forgotten: {answer_memory.forget_all()} remembered answers. New ones are drafted from your CV again."}

    # ── filling in the form in Chrome ───────────────────────────
    def assistant_review(self, job_id=""):
        """Read the whole form back and say what looks wrong before it is sent: what a plain check finds (a required
        field left empty, a part still in square brackets) and, in one call, what Claude sees against your CV.
        The values of personal and payment fields are not looked at."""
        def no(msg):
            return {"ok": False, "action": "review", "msg": msg}
        self._app.browser()
        try:
            tab = chrome.active_tab()
            host = form_fill.host_of(tab["url"])
            if not tab["url"].lower().startswith(("http://", "https://")) or not host:
                return no("The tab in front is not a web page with a form. Bring the form to the front and ask me again.")
            if mailhosts.never_used(host):
                return no("This app does not work with Russian services, so I do not read forms on this site.")
            page = form_fill.review_answer(chrome.run(form_fill.REVIEW))
        except (chrome.ChromeError, ValueError) as e:
            return no(str(e))
        fields = page["fields"]
        if not fields:
            return no("I found no form fields on this page. Bring the form to the front and ask me again.")
        jobs = store.load_jobs()
        job = store.find(jobs, job_id) if job_id else store.find(jobs, form_fill.match_job(
            [j for j in jobs if j.get("status") in store.OPEN_STATUSES], page["url"], page["title"]))
        mine = details.load()
        problems = []
        for f in fields:
            if f["required"] and not f["filled"]:
                problems.append({"field": f["label"], "problem": "It is required and still empty."})
            elif "[" in f["value"] and "]" in f["value"]:
                problems.append({"field": f["label"], "problem": "It still has a part in [square brackets] to fill in."})
            elif f["kind"] == "email" and mine.get("email") and f["value"].strip() and f["value"].strip().lower() != mine["email"].lower():
                problems.append({"field": f["label"], "problem": f"It is not the address in My details ({mine['email']})."})
        note = ""
        cv_text = self._cv.text()
        if cv_text.strip():
            try:
                seen = {p["field"] for p in problems}
                problems += [p for p in assistant_brain.review(job, cv_text, self._app.facts(job), [f for f in fields if not f["private"]], self._app.pay(job))
                             if p["field"] not in seen]
            except Exception as e:  # noqa: BLE001 - the plain checks are still reported
                note = f" Claude could not read it against your CV ({str(e) or type(e).__name__}), so only the plain checks were made."
        else:
            note = " Your master CV could not be read, so only the plain checks were made."
        filled = sum(1 for f in fields if f["filled"])
        if problems:
            say = f"I read the form on {host}: {filled} of {len(fields)} fields are filled in, and {len(problems)} {'thing looks' if len(problems) == 1 else 'things look'} wrong."
        else:
            say = f"I read the form on {host}: {filled} of {len(fields)} fields are filled in, and I see nothing wrong."
        return {"ok": True, "action": "review", "host": host, "problems": problems[:12], "job_id": job["id"] if job else "",
                "say": say + note + " Tick boxes, files and personal questions are yours to check. I did not send anything."}

    def assistant_fill(self, job_id="", skip=None):
        """Fill in the form in the browser tab in front. Only empty fields are written; the only things
        pressed are a menu, an entry of a menu and a radio button; file fields get the CV and the letter
        of the job; the form is not sent. Returns what was filled, what was left and why (see `form_run`)."""
        run = form_run.FormFillRun(self._app, self._editor, self._cv, job_id, skip)
        out = run.result()
        if out["ok"]:
            self._last_fill = run.learned()
        return out
