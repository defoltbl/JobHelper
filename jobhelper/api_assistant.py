"""The assistant's part of the window's back end: your details, and filling in the form that is open in Chrome."""
from __future__ import annotations

import os
import secrets
import time
from datetime import date
from typing import Any

from . import agent1_cv, answer_memory, assistant, assistant_brain, chrome, config, cover_letter, details, form_answers, form_choices, form_fill, mailhosts, salary, store
from .api_base import _guarded

SHOWN = 90      # characters of a filled-in value shown in the report


class AssistantApi:
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
        open_ones = [j for j in store.load_jobs() if j.get("status") in store.LEAD_STATUSES | {"waiting", "interview", "on_hold"}]
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
        self._browser()
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
            self._browser()
            return {"ok": True, **form_fill.watch_answer(chrome.run(form_fill.WATCH))}
        except Exception:  # noqa: BLE001 - not being able to look is not something to report
            return {"ok": False, "url": "", "sign": "", "empty": 0}

    def assistant_learn(self):
        """Take over what the person changed on the page in the answers the assistant wrote: kept with the job and
        remembered for the same question elsewhere. Only those fields are read back, nothing else on the page."""
        last = getattr(self, "_last_fill", None)
        if not last or not last.get("items"):
            return {"ok": False, "msg": "There is nothing to compare with yet. Ask me to fill in a form first."}
        self._browser()
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
            self._jobs.change(last["job_id"], keep, render=False)
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
    def _letter_text(self, j) -> str:
        """The body of the letter the app wrote for this job ('' when there is none it can read)."""
        try:
            if j and self._editable_letter(j):
                return "\n\n".join(p for p in cover_letter.read_letter(self._letter_path(j))["paragraphs"] if p.strip())
        except Exception:  # noqa: BLE001 - no letter is not a failure: the field is left to the person
            pass
        return ""

    def _answers(self, job, asked: list[dict[str, Any]]) -> tuple[dict[str, dict], str]:
        """Answers for the open questions of a form: those kept with the job are used again, the
        rest are drafted in one call and kept. Returns ({question: item}, why some are missing)."""
        kept = {i["question"].lower(): i for i in form_answers.tidy((job.get("form_answers") or {}).get("items")) if i["answer"]}
        for q in asked:                      # your own wording for the same question elsewhere comes before a new draft
            if q["label"].lower() not in kept:
                mine = answer_memory.recall(q["label"], job.get("company", ""))
                if mine:
                    kept[q["label"].lower()] = {"question": q["label"], "answer": mine["answer"], "check": answer_memory.CHECK}
        fresh = [q["label"] for q in asked if q["label"].lower() not in kept]
        if not fresh:
            return kept, ""
        cv_text = self._cv.text()
        if not cv_text.strip():
            return kept, "Your master CV could not be read, so no answer could be built from it."
        try:
            drafted = form_answers.generate(job, cv_text, fresh, config.experience_notes())
        except Exception as e:  # noqa: BLE001 - said to the person as the reason; the details are still filled in
            return kept, f"The answers could not be drafted: {str(e) or type(e).__name__}"
        new = {i["question"].lower(): i for i in drafted}

        def keep(jobs, j):          # may run twice (the running search's copy): the result is the same
            items = [i for i in form_answers.tidy((j.get("form_answers") or {}).get("items")) if i["question"].lower() not in new]
            j["form_answers"] = {"made": form_answers.stamp(), "items": items + list(new.values())}
        self._jobs.change(job["id"], keep, render=False)
        return {**kept, **{k: v for k, v in new.items() if v["answer"]}}, ""

    def _menu(self, n: int, url: str, typed: str = "") -> list[str]:
        """Open a menu the page draws itself and read its entries (they are numbered on the page for the pick that follows)."""
        chrome.run(form_fill.choose_script("open", n, typed, url))
        options: list[str] = []
        for wait in (0.35, 0.7, 1.2):
            chrome.pause(wait)
            options = form_fill.choose_answer(chrome.run(form_fill.choose_script("options", n, "", url)))["options"]
            if options:
                break
        if not options:                     # some lists open on the arrow-down key, not on a press
            chrome.run(form_fill.choose_script("key", n, "", url))
            for wait in (0.4, 1.0):
                chrome.pause(wait)
                options = form_fill.choose_answer(chrome.run(form_fill.choose_script("options", n, "", url)))["options"]
                if options:
                    break
        return options

    def _choose(self, choices: list[dict[str, Any]], url: str, mine: dict[str, str], job) -> tuple[list[dict], list[dict], list[dict]]:
        """Decide and make the choices of a form. Returns (values for plain lists and number fields, to be
        written with the rest; what was chosen by pressing; what is left, with the reason)."""
        to_fill, chosen, left = [], [], []
        for extra in choices[form_choices.MAX_CHOICES + 8:]:
            left.append({"label": extra["label"], "why": form_choices.TOO_MANY})
        choices = choices[:form_choices.MAX_CHOICES + 8]
        for c in choices:                            # a menu shows its entries only once it is open
            if c["kind"] == "menu":
                typed = (mine.get("city", "") if c["what"] in ("city", "location") else c["value"]) if c["typed"] else ""
                c["search"] = typed
                c["options"] = self._menu(c["n"], url, typed)
                chrome.run(form_fill.choose_script("close", c["n"], bool(typed), url))
                if typed and not c["options"]:      # the list knows your country under another name: all of its entries, then
                    c["search"] = ""
                    c["options"] = self._menu(c["n"], url, "")
                    chrome.run(form_fill.choose_script("close", c["n"], False, url))
        picks = {c["n"]: form_choices.settle(c, mine, job) for c in choices}
        for c in choices:                            # what you chose for the same question before
            if not picks[c["n"]] and c["options"]:
                earlier = answer_memory.recall(c["label"], (job or {}).get("company", ""), c["options"])
                picks[c["n"]] = earlier["answer"] if earlier else ""
        open_ones = [c for c in choices if not picks[c["n"]] and (c["kind"] in ("number", "text") or c["options"])]
        why = ""
        if open_ones:
            cv_text = self._cv.text()
            if not cv_text.strip():
                why = "Your master CV could not be read, so nothing could be chosen from it."
            else:
                try:
                    picks.update(form_choices.decide(open_ones, cv_text, mine, job))
                except Exception as e:  # noqa: BLE001 - said to the person as the reason; the rest of the form is still filled in
                    why = f"The choice could not be made: {str(e) or type(e).__name__}"
        for c in choices:
            pick = picks.get(c["n"], "")
            if not pick:
                left.append({"label": c["label"], "why": form_choices.NO_MENU if c["kind"] == "menu" and not c["options"]
                             else (why or (form_fill.UNKNOWN if c["kind"] == "text" else form_choices.NOT_SETTLED))})
            elif c["kind"] == "text" and c.get("most") and len(pick) > c["most"]:
                left.append({"label": c["label"], "why": form_fill.TOO_LONG.format(most=c["most"], size=len(pick))})
            elif c["kind"] in ("select", "number", "text"):
                to_fill.append({"n": c["n"], "label": c["label"], "value": pick, "kind": "choice", "check": form_choices.CHECK})
            elif c["kind"] == "radio":
                done = form_fill.choose_answer(chrome.run(form_fill.choose_script("radio", c["n"], c["options"].index(pick), url)))
                (chosen if done["ok"] else left).append({"label": c["label"], "value": pick, "kind": "choice", "check": form_choices.CHECK}
                                                        if done["ok"] else {"label": c["label"], "why": "The page did not take the choice. Choose it yourself."})
            else:
                options = self._menu(c["n"], url, c.get("search", ""))
                same = [k for k, o in enumerate(options) if o == pick]
                done = form_fill.choose_answer(chrome.run(form_fill.choose_script("pick", c["n"], same[0], url))) if same else {"ok": False}
                if not done["ok"]:
                    chrome.run(form_fill.choose_script("close", c["n"], bool(c.get("search")), url))
                (chosen if done["ok"] else left).append({"label": c["label"], "value": pick, "kind": "choice", "check": form_choices.CHECK}
                                                        if done["ok"] else {"label": c["label"], "why": "The page did not take the choice. Choose it yourself."})
        return to_fill, chosen, left

    def _more_rows(self, page: dict[str, Any], rows: dict[str, int], mine: dict[str, Any]) -> int:
        """Ask the form for the rows it does not show yet: one press of "Add another job" for each job of yours that
        has no row, the same for degrees. Returns how many rows were asked for. Nothing else is ever pressed."""
        pressed = 0
        for name, have in (("experience", len(mine.get("experience") or [])), ("education", len(mine.get("education") or [])),
                           ("languages", len(mine.get("languages") or []))):
            button = next((a for a in page["adds"] if a["kind"] == name), None)
            if not button:
                continue
            for _ in range(max(0, min(have - rows.get(name, 0), 6))):
                done = form_fill.choose_answer(chrome.run(form_fill.choose_script("add", 0, button["k"], page["url"])))
                if not done["ok"]:
                    break
                pressed += 1
                chrome.pause(0.4)
        return pressed

    def assistant_review(self, job_id=""):
        """Read the whole form back and say what looks wrong before it is sent: what a plain check finds (a required
        field left empty, a part still in square brackets) and, in one call, what Claude sees against your CV.
        The values of personal and payment fields are not looked at."""
        def no(msg):
            return {"ok": False, "action": "review", "msg": msg}
        self._browser()
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
            [j for j in jobs if j.get("status") in store.LEAD_STATUSES | {"waiting", "interview", "on_hold"}], page["url"], page["title"]))
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
                problems += [p for p in assistant_brain.review(job, cv_text, self._facts(job), [f for f in fields if not f["private"]], self._pay(job))
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

    def _job_docs(self, j) -> dict[str, list]:
        """The files of a job that can go into a form: its CV and its letter, the PDF before the Word file."""
        out: dict[str, list] = {"cv": [], "letter": []}
        for what, base, name in (("cv", config.TAILORED_CV_DIR, j.get("tailored_cv_file", "")), ("letter", config.LETTERS_DIR, j.get("cover_letter_file", ""))):
            name = str(name or "")
            if not name or os.path.basename(name) != name:
                continue
            docx = (base / name).with_suffix(".docx")
            tried = [docx.with_suffix(".pdf"), docx] + ([config.COVER_LETTERS_DIR / name] if what == "letter" else [])
            out[what] = [path for path in dict.fromkeys(tried) if path.is_file()]
        return out

    def _recently_opened(self) -> str:
        """The job whose posting you opened from the app within the last two hours ('' = none)."""
        job_id, when = getattr(self, "_opened", ("", 0.0))
        return job_id if job_id and time.time() - when < 2 * 3600 else ""

    def _job_of_page(self, jobs: list[dict], page: dict[str, Any]):
        """The job a form belongs to, although the form is rarely at the address of its posting (see form_fill.match_job)."""
        found = form_fill.match_job(jobs, page["url"], page["title"], page.get("from", ""))
        if not found:
            try:
                words = form_fill.page_answer(chrome.run(form_fill.PAGE))["text"][:6000]
            except (chrome.ChromeError, ValueError):
                words = ""
            found = form_fill.match_job(jobs, page["url"], page["title"], page.get("from", ""), words, self._recently_opened())
        return store.find(jobs, found) if found else None

    def _attach(self, wanted: list[dict[str, Any]], page: dict[str, Any], job) -> tuple[list[dict], list[dict], bool]:
        """Give the form's file fields the CV and the letter of this job. Returns (attached, left, the tab moved).
        Only a field that holds no file is given one; the field for further documents gets the letter when the
        form has no place of its own for it. Nothing is sent: the page holds the file until you press its button."""
        filled, left = [], []
        docs = self._job_docs(job) if job else {"cv": [], "letter": []}
        letter_placed = any(form_fill.classify(f)[0] == "letter" for f in page["fields"]) or any(i["kind"] == "letter" for i in wanted)
        for item in wanted:
            kind, check = item["kind"], form_fill.FILE_CHECK
            if not job:
                left.append({"label": item["label"], "why": form_fill.FILE_NO_JOB})
                continue
            if kind == "other":
                if letter_placed:
                    left.append({"label": item["label"], "why": form_fill.FILE_OTHER})
                    continue
                kind, letter_placed = "letter", True
            paths = docs[kind]
            if kind == "cv" and not paths:              # no CV adapted to this job: your own one, and said so
                master = agent1_cv.find_cv()
                paths, check = ([master] if master else []), form_fill.FILE_MASTER
            if not paths:
                left.append({"label": item["label"], "why": form_fill.FILE_NO_CV if kind == "cv" else form_fill.FILE_NO_LETTER})
                continue
            path = next((p for p in paths if form_fill.takes(item["accept"], p.name)), None)
            if path is None:
                left.append({"label": item["label"], "why": form_fill.FILE_FORMAT.format(accept=item["accept"], name=paths[0].name)})
                continue
            try:
                content = path.read_bytes() if path.stat().st_size <= form_fill.MAX_FILE else None
            except OSError:
                left.append({"label": item["label"], "why": form_fill.FILE_NO_CV if kind == "cv" else form_fill.FILE_NO_LETTER})
                continue
            if content is None:
                left.append({"label": item["label"], "why": form_fill.FILE_BIG.format(name=path.name)})
                continue
            key = "__jobhelper_" + secrets.token_hex(8)
            for piece in form_fill.put_scripts(key, content):
                chrome.run(piece)
            got = form_fill.attach_answer(chrome.run(form_fill.attach_script(item["n"], key, path.name, page["url"])))
            if got["moved"]:
                return filled, left, True
            if got["ok"] and got["size"] == len(content):
                filled.append({"label": item["label"], "value": path.name, "kind": "file", "check": check})
            else:
                left.append({"label": item["label"], "why": form_fill.FILE_REFUSED})
        return filled, left, False

    def assistant_fill(self, job_id="", skip=None):
        """Fill in the form in the browser tab in front. Only empty fields are written; the only things
        pressed are a menu, an entry of a menu and a radio button; file fields get the CV and the letter
        of the job; the form is not sent.
        Returns what was filled, what was left and why."""
        def no(msg, **more):
            return {"ok": False, "action": "fill", "msg": msg, **more}
        mine = details.load()
        self._browser()
        if not details.any_given(mine):
            return no("I do not know your details yet. Fill in My details once, save, then ask me again.", action="details")
        mine["start"] = str(self.options().get("about_start") or "").strip()      # when you can start: said once, under Options, About you
        try:
            tab = chrome.active_tab()
        except chrome.ChromeError as e:
            return no(str(e))
        host = form_fill.host_of(tab["url"])
        if not tab["url"].lower().startswith(("http://", "https://")) or not host:
            return no(f"The tab in front is not a web page with a form. Open the application form in {chrome.short()}, bring its tab to the front, and ask me again.")
        if mailhosts.never_used(host):
            return no("This app does not work with Russian services, so I do not fill in forms on this site.")
        try:
            page = form_fill.read_answer(chrome.run(form_fill.READ))
        except (chrome.ChromeError, ValueError) as e:
            return no(str(e))
        if not page["fields"]:
            if page["frames"]:
                inner = form_fill.host_of(page["frames"][0]) or "another site"
                return no(f"The form on this page sits inside a frame from {inner}, which I cannot reach from outside. "
                          "Press the button below: I open the form in a tab of its own and fill it in there.",
                          frame=page["frames"][0])
            return no(f"I found no form fields on this page ({page['title'] or host}). Open the page with the application form and ask me again.")
        jobs = store.load_jobs()
        job, guessed = None, False
        if job_id:
            job = store.find(jobs, job_id)
            if not job:
                return no("That job is not in the list any more. Choose another one.")
        else:
            open_ones = [j for j in jobs if j.get("status") in store.LEAD_STATUSES | {"waiting", "interview", "on_hold"}]
            job = self._job_of_page(open_ones, page)
            guessed = job is not None
        todo = form_fill.plan(page["fields"], mine, self._letter_text(job), has_job=job is not None)
        added = 0
        if page["adds"]:                    # the form shows fewer rows than you have jobs or degrees: ask it for more, then read it again
            try:
                added = self._more_rows(page, todo["rows"], mine)
                if added:
                    again = form_fill.read_answer(chrome.run(form_fill.READ))
                    if again["url"] == page["url"] and again["fields"]:
                        page = again
                        todo = form_fill.plan(page["fields"], mine, self._letter_text(job), has_job=job is not None)
            except (chrome.ChromeError, ValueError) as e:
                return no(str(e))
        fill, left = list(todo["fill"]), list(todo["left"])
        leave = [w for w in (" ".join(str(s).lower().split()) for s in (skip or [])) if w]

        def wanted(items):                  # "fill it in but skip the salary": what you named is left, and said so
            kept = []
            for item in items:
                if any(w in item["label"].lower() or w == item.get("what", "") for w in leave):
                    left.append({"label": item["label"], "why": form_fill.SKIPPED})
                else:
                    kept.append(item)
            return kept
        fill, todo["ask"], todo["choose"], todo["guess"] = wanted(fill), wanted(todo["ask"]), wanted(todo["choose"]), wanted(todo["guess"])
        todo["attach"] = wanted(todo["attach"])
        guesses = [{"n": g["n"], "kind": "text", "typed": False, "label": g["label"], "options": [], "what": "", "value": "", "most": g["most"]}
                   for g in todo["guess"][:8]]
        left += [{"label": g["label"], "why": form_fill.UNKNOWN} for g in todo["guess"][8:]]
        todo["choose"] = todo["choose"] + guesses
        if todo["ask"]:
            answers, why = self._answers(job, todo["ask"])
            for q in todo["ask"]:
                item = answers.get(q["label"].lower())
                if not item:
                    left.append({"label": q["label"], "why": why or "No answer was drafted. Write this one yourself."})
                elif q["most"] and len(item["answer"]) > q["most"]:
                    left.append({"label": q["label"], "why": form_fill.TOO_LONG.format(most=q["most"], size=len(item["answer"]))
                                 + " The answer is kept under Form answers for this job."})
                else:
                    fill.append({"n": q["n"], "label": q["label"], "value": item["answer"], "kind": "answer", "check": item["check"]})
        filled, done = [], {"done": []}
        if todo["choose"]:
            try:
                values, chosen, open_ones = self._choose(todo["choose"], page["url"], mine, job)
            except chrome.ChromeError as e:
                return no(str(e))
            fill += values
            filled += chosen
            left += open_ones
        for box in wanted(todo["tick"]):               # "I work here now", for a job of yours that goes on: the one tick box it may tick
            try:
                ticked = form_fill.choose_answer(chrome.run(form_fill.choose_script("tick", box["n"], "", page["url"])))
            except chrome.ChromeError as e:
                return no(str(e))
            if ticked["ok"]:
                filled.append({"label": box["label"], "value": "Ticked", "kind": "choice", "check": form_choices.CHECK})
            else:
                left.append({"label": box["label"], "why": "The page did not take the tick. Tick it yourself."})
        thrown: list[int] = []
        if fill:
            try:
                done = form_fill.fill_answer(chrome.run(form_fill.fill_script(fill, page["url"])))
            except (chrome.ChromeError, ValueError) as e:
                return no(str(e))
            if done["moved"]:
                return no("The tab changed while I was working, so I wrote nothing. Go back to the form and ask me again.")
            # some pages throw away what did not arrive as typing: look again, and write those the way typing arrives
            try:
                texts = [i["n"] for i in fill if i["n"] in done["done"]]
                if texts:
                    chrome.pause(0.35)
                    lost = set(form_fill.empty_answer(chrome.run(form_fill.empty_script(texts, page["url"]))))
                    if lost:
                        chrome.run(form_fill.fill_script([i for i in fill if i["n"] in lost], page["url"], typed=True))
                        chrome.pause(0.35)
                        thrown = form_fill.empty_answer(chrome.run(form_fill.empty_script(sorted(lost), page["url"])))
            except chrome.ChromeError:
                thrown = []                          # looking again failed: what was written is reported as it was
            done["done"] = [n for n in done["done"] if n not in thrown]
            for item in fill:
                if item["n"] in done["done"]:
                    filled.append({"label": item["label"], "kind": item["kind"], "check": item.get("check", ""),
                                   "value": item["value"] if len(item["value"]) <= SHOWN else item["value"][:SHOWN].rstrip() + "…"})
                elif item["n"] in thrown:
                    left.append({"label": item["label"], "why": form_fill.THROWN})
                else:
                    left.append({"label": item["label"], "why": "The page did not take it: the field changed or was filled in the meantime. Type this one yourself."})
        if todo["attach"]:
            try:
                attached, not_attached, moved = self._attach(todo["attach"], page, job)
            except (chrome.ChromeError, ValueError) as e:
                return no(str(e))
            if moved:
                return no("The tab changed while I was attaching your files. Go back to the form, look what it holds, and ask me again.")
            filled += attached
            left += not_attached
        kept = sum(1 for f in page["fields"] if f["filled"])
        label = f"{job.get('title', '')} at {job.get('company', '')}" if job else ""
        if job and filled and job.get("status") in store.LEAD_STATUSES:
            today = date.today().isoformat()        # so that the app can remind you when a filled form was never marked applied
            self._jobs.change(job["id"], lambda jobs, j: j.__setitem__("form_filled", today), render=False)
        # what the assistant itself wrote as answers: the only fields it may read back later, to learn your corrections
        self._last_fill = {"url": page["url"], "job_id": job["id"] if job else "", "company": job.get("company", "") if job else "",
                           "items": [{"n": i["n"], "label": i["label"], "value": i["value"]} for i in fill
                                     if i["kind"] in ("answer", "choice") and i["n"] in (done["done"] if fill else [])]}
        return {"ok": True, "action": "fill", "host": host, "url": page["url"],
                "job_id": job["id"] if job else "", "job": label, "guessed": guessed,
                "wants_file": any(i["why"] in form_fill.FILE_REASONS or "Attach it yourself" in i["why"] for i in left),
                "has_files": bool(mine["files"] or (job and (job.get("tailored_cv_file") or job.get("cover_letter_file")))),
                "is_lead": bool(job and job.get("status") in store.LEAD_STATUSES), "can_learn": bool(self._last_fill["items"]),
                "filled": filled, "left": left, "kept": kept, "boxes": page["boxes"],
                "added_rows": added,
                "say": assistant.summary(host, filled, left, kept, page["boxes"], label, guessed)
                       + (f" I asked the form for {added} more row{'' if added == 1 else 's'} for your jobs and degrees." if added else "")}
