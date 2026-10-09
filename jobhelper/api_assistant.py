"""The assistant's part of the window's back end: your details, and filling in the form that is open in Chrome."""
from __future__ import annotations

from typing import Any

from . import assistant, chrome, config, cover_letter, details, form_answers, form_choices, form_fill, mailhosts, store
from .api_base import _guarded

SHOWN = 90      # characters of a filled-in value shown in the report


class AssistantApi:
    # ── My details ──────────────────────────────────────────────
    @_guarded(dict)
    def my_details(self):
        """What the page shows: the saved details, and in empty fields what the CV plainly states (offered, not saved)."""
        kept = details.load()
        offered = details.from_cv(self._cv_text(), self._my_name())
        from_cv = [key for key in details.KEYS if not kept[key] and offered.get(key)]
        return {"details": {key: kept[key] or offered.get(key, "") for key in details.KEYS}, "from_cv": from_cv,
                "saved": any(kept.values()),
                "fields": [{"key": key, "label": label, "most": most} for key, label, most in details.FIELDS]}

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
        fresh = [q["label"] for q in asked if q["label"].lower() not in kept]
        if not fresh:
            return kept, ""
        cv_text = self._cv_text()
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
        self._change(job["id"], keep, render=False)
        return {**kept, **{k: v for k, v in new.items() if v["answer"]}}, ""

    def _menu(self, n: int, url: str, typed: str = "") -> list[str]:
        """Open a menu the page draws itself and read its entries (they are numbered on the page for the pick that follows)."""
        chrome.run(form_fill.choose_script("open", n, typed, url))
        options: list[str] = []
        for wait in (0.35, 0.7):
            chrome.pause(wait)
            options = form_fill.choose_answer(chrome.run(form_fill.choose_script("options", n, "", url)))["options"]
            if options:
                break
        return options

    def _choose(self, choices: list[dict[str, Any]], url: str, mine: dict[str, str], job) -> tuple[list[dict], list[dict], list[dict]]:
        """Decide and make the choices of a form. Returns (values for plain lists and number fields, to be
        written with the rest; what was chosen by pressing; what is left, with the reason)."""
        to_fill, chosen, left = [], [], []
        for extra in choices[form_choices.MAX_CHOICES:]:
            left.append({"label": extra["label"], "why": form_choices.TOO_MANY})
        choices = choices[:form_choices.MAX_CHOICES]
        for c in choices:                            # a menu shows its entries only once it is open
            if c["kind"] == "menu":
                typed = (mine.get("city", "") if c["what"] in ("city", "location") else c["value"]) if c["typed"] else ""
                c["search"] = typed
                c["options"] = self._menu(c["n"], url, typed)
                chrome.run(form_fill.choose_script("close", c["n"], bool(typed), url))
        picks = {c["n"]: form_choices.settle(c, mine, job) for c in choices}
        open_ones = [c for c in choices if not picks[c["n"]] and (c["kind"] == "number" or c["options"])]
        why = ""
        if open_ones:
            cv_text = self._cv_text()
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
                             else (why or form_choices.NOT_SETTLED)})
            elif c["kind"] in ("select", "number"):
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

    def assistant_fill(self, job_id=""):
        """Fill in the form in the Chrome tab in front. Only empty fields are written; the only things
        pressed are a menu, an entry of a menu and a radio button; the form is not sent.
        Returns what was filled, what was left and why."""
        def no(msg, **more):
            return {"ok": False, "action": "fill", "msg": msg, **more}
        mine = details.load()
        if not any(mine.values()):
            return no("I do not know your details yet. Fill in My details once, save, then ask me again.", action="details")
        try:
            tab = chrome.active_tab()
        except chrome.ChromeError as e:
            return no(str(e))
        host = form_fill.host_of(tab["url"])
        if not tab["url"].lower().startswith(("http://", "https://")) or not host:
            return no("The tab in front is not a web page with a form. Open the application form in Chrome, bring its tab to the front, and ask me again.")
        if mailhosts.never_used(host):
            return no("This app does not work with Russian services, so I do not fill in forms on this site.")
        try:
            page = form_fill.read_answer(chrome.run(form_fill.READ))
        except (chrome.ChromeError, ValueError) as e:
            return no(str(e))
        if not page["fields"]:
            if page["frames"]:
                inner = form_fill.host_of(page["frames"][0]) or "another site"
                return no(f"The form on this page sits inside a frame from {inner}, which cannot be reached from outside. "
                          f"Open the form on its own page (the Apply button often does that), or open this address in a tab: {page['frames'][0]}")
            return no(f"I found no form fields on this page ({page['title'] or host}). Open the page with the application form and ask me again.")
        jobs = store.load_jobs()
        job, guessed = None, False
        if job_id:
            job = store.find(jobs, job_id)
            if not job:
                return no("That job is not in the list any more. Choose another one.")
        else:
            open_ones = [j for j in jobs if j.get("status") in store.LEAD_STATUSES | {"waiting", "interview", "on_hold"}]
            job = store.find(jobs, form_fill.match_job(open_ones, page["url"], page["title"]))
            guessed = job is not None
        todo = form_fill.plan(page["fields"], mine, self._letter_text(job), has_job=job is not None)
        fill, left = list(todo["fill"]), list(todo["left"])
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
        filled = []
        if todo["choose"]:
            try:
                values, chosen, open_ones = self._choose(todo["choose"], page["url"], mine, job)
            except chrome.ChromeError as e:
                return no(str(e))
            fill += values
            filled += chosen
            left += open_ones
        if fill:
            try:
                done = form_fill.fill_answer(chrome.run(form_fill.fill_script(fill, page["url"])))
            except (chrome.ChromeError, ValueError) as e:
                return no(str(e))
            if done["moved"]:
                return no("The tab changed while I was working, so I wrote nothing. Go back to the form and ask me again.")
            for item in fill:
                if item["n"] in done["done"]:
                    filled.append({"label": item["label"], "kind": item["kind"], "check": item.get("check", ""),
                                   "value": item["value"] if len(item["value"]) <= SHOWN else item["value"][:SHOWN].rstrip() + "…"})
                else:
                    left.append({"label": item["label"], "why": "The page did not take it: the field changed or was filled in the meantime. Type this one yourself."})
        kept = sum(1 for f in page["fields"] if f["filled"])
        label = f"{job.get('title', '')} at {job.get('company', '')}" if job else ""
        return {"ok": True, "action": "fill", "host": host, "url": page["url"],
                "job_id": job["id"] if job else "", "job": label, "guessed": guessed,
                "filled": filled, "left": left, "kept": kept, "boxes": page["boxes"],
                "say": assistant.summary(host, filled, left, kept, page["boxes"], label, guessed)}
