"""One fill of the form in the browser tab in front: read it, decide each field, write what is empty, attach the
job's files, and say what was done and what is left. Nothing is ever sent: the only things pressed are a menu, an
entry of a menu, a radio button, the one tick box for a job that goes on, and a form's own "Add another" button."""
from __future__ import annotations

import os
import secrets
from datetime import date
from typing import Any

from . import (agent1_cv, answer_memory, assistant, chrome, config, cover_letter, details, form_answers, form_choices,
               form_fill, mailhosts, store)

SHOWN = 90      # characters of a filled-in value shown in the report


class Stop(Exception):
    """A step that cannot go on. Its answer is what the person is told; nothing after it runs."""

    def __init__(self, msg: str, **more: Any) -> None:
        super().__init__(msg)
        self.answer = {"ok": False, "action": "fill", "msg": msg, **more}


class FormFillRun:
    """One fill, from reading the page to the report. Only empty fields are written, and the form is not sent.

    `app` is the facade (`ui_api.Api`), `editor` saves a change to one job, `cv` reads the master CV. `skip` names
    what to leave out ("fill it in but skip the salary")."""

    def __init__(self, app, editor, cv, job_id: str = "", skip=None) -> None:
        self._app, self._editor, self._cv = app, editor, cv
        self._job_id = job_id
        self._leave = [w for w in (" ".join(str(s).lower().split()) for s in (skip or [])) if w]
        self._mine: dict[str, Any] = {}
        self._page: dict[str, Any] = {}
        self._job = None
        self._guessed = False
        self._todo: dict[str, Any] = {}
        self._added = 0
        self._fill: list[dict] = []           # values to write into the page
        self._filled: list[dict] = []         # what the report shows as done
        self._left: list[dict] = []           # what is left to the person, with the reason
        self._written: list[int] = []         # numbers of the fields the page took

    def result(self) -> dict[str, Any]:
        """Do the whole fill and say what happened (see `AssistantService.assistant_fill`)."""
        try:
            self._know_you()
            host = self._read_page()
            self._find_job()
            self._plan()
            self._leave_out_what_you_named()
            self._draft_answers()
            self._choose()
            self._tick()
            self._write()
            self._attach_files()
        except Stop as stop:
            return stop.answer
        return self._report(host)

    def learned(self) -> dict[str, Any]:
        """What the assistant itself wrote as answers: the only fields it may read back later, to learn your corrections."""
        job = self._job
        return {"url": self._page["url"], "job_id": job["id"] if job else "", "company": job.get("company", "") if job else "",
                "items": [{"n": i["n"], "label": i["label"], "value": i["value"]} for i in self._fill
                          if i["kind"] in ("answer", "choice") and i["n"] in self._written]}

    # ── the steps, in order ─────────────────────────────────────
    def _know_you(self) -> None:
        self._mine = details.load()
        self._app.browser()
        if not details.any_given(self._mine):
            raise Stop("I do not know your details yet. Fill in My details once, save, then ask me again.", action="details")
        self._mine["start"] = str(self._app.options().get("about_start") or "").strip()     # when you can start: said once, in About you

    def _read_page(self) -> str:
        try:
            tab = chrome.active_tab()
        except chrome.ChromeError as e:
            raise Stop(str(e)) from e
        host = form_fill.host_of(tab["url"])
        if not tab["url"].lower().startswith(("http://", "https://")) or not host:
            raise Stop(f"The tab in front is not a web page with a form. Open the application form in {chrome.short()}, bring its tab to the front, and ask me again.")
        if mailhosts.never_used(host):
            raise Stop("This app does not work with Russian services, so I do not fill in forms on this site.")
        self._page = self._read()
        if not self._page["fields"]:
            if self._page["frames"]:
                inner = form_fill.host_of(self._page["frames"][0]) or "another site"
                raise Stop(f"The form on this page sits inside a frame from {inner}, which I cannot reach from outside. "
                           "Press the button below: I open the form in a tab of its own and fill it in there.",
                           frame=self._page["frames"][0])
            raise Stop(f"I found no form fields on this page ({self._page['title'] or host}). Open the page with the application form and ask me again.")
        return host

    def _read(self) -> dict[str, Any]:
        try:
            return form_fill.read_answer(chrome.run(form_fill.READ))
        except (chrome.ChromeError, ValueError) as e:
            raise Stop(str(e)) from e

    def _find_job(self) -> None:
        jobs = store.load_jobs()
        if self._job_id:
            self._job = store.find(jobs, self._job_id)
            if not self._job:
                raise Stop("That job is not in the list any more. Choose another one.")
        else:
            self._job = self._job_of_page([j for j in jobs if j.get("status") in store.OPEN_STATUSES], self._page)
            self._guessed = self._job is not None

    def _plan(self) -> None:
        self._todo = form_fill.plan(self._page["fields"], self._mine, self._letter_text(self._job), has_job=self._job is not None)
        if not self._page["adds"]:
            return
        try:                                # the form shows fewer rows than you have jobs or degrees: ask it for more, then read it again
            self._added = self._more_rows(self._page, self._todo["rows"], self._mine)
            if self._added:
                again = self._read()
                if again["url"] == self._page["url"] and again["fields"]:
                    self._page = again
                    self._todo = form_fill.plan(self._page["fields"], self._mine, self._letter_text(self._job), has_job=self._job is not None)
        except (chrome.ChromeError, ValueError) as e:
            raise Stop(str(e)) from e

    def _wanted(self, items: list[dict]) -> list[dict]:
        """The items you did not name to be left out; the others are left, and said so."""
        kept = []
        for item in items:
            if any(w in item["label"].lower() or w == item.get("what", "") for w in self._leave):
                self._left.append({"label": item["label"], "why": form_fill.SKIPPED})
            else:
                kept.append(item)
        return kept

    def _leave_out_what_you_named(self) -> None:
        todo = self._todo
        self._left += todo["left"]
        self._fill = self._wanted(list(todo["fill"]))
        for key in ("ask", "choose", "guess", "attach"):
            todo[key] = self._wanted(todo[key])
        guesses = [{"n": g["n"], "kind": "text", "typed": False, "label": g["label"], "options": [], "what": "", "value": "", "most": g["most"]}
                   for g in todo["guess"][:8]]
        self._left += [{"label": g["label"], "why": form_fill.UNKNOWN} for g in todo["guess"][8:]]
        todo["choose"] = todo["choose"] + guesses

    def _draft_answers(self) -> None:
        asked = self._todo["ask"]
        if not asked:
            return
        answers, why = self._answers(self._job, asked)
        for q in asked:
            item = answers.get(q["label"].lower())
            if not item:
                self._left.append({"label": q["label"], "why": why or "No answer was drafted. Write this one yourself."})
            elif q["most"] and len(item["answer"]) > q["most"]:
                self._left.append({"label": q["label"], "why": form_fill.TOO_LONG.format(most=q["most"], size=len(item["answer"]))
                                  + " The answer is kept under Form answers for this job."})
            else:
                self._fill.append({"n": q["n"], "label": q["label"], "value": item["answer"], "kind": "answer", "check": item["check"]})

    def _choose(self) -> None:
        if not self._todo["choose"]:
            return
        try:
            values, chosen, open_ones = self._choices(self._todo["choose"], self._page["url"], self._mine, self._job)
        except chrome.ChromeError as e:
            raise Stop(str(e)) from e
        self._fill += values
        self._filled += chosen
        self._left += open_ones

    def _tick(self) -> None:
        for box in self._wanted(self._todo["tick"]):    # "I work here now", for a job of yours that goes on: the one tick box it may tick
            try:
                ticked = form_fill.choose_answer(chrome.run(form_fill.choose_script("tick", box["n"], "", self._page["url"])))
            except chrome.ChromeError as e:
                raise Stop(str(e)) from e
            if ticked["ok"]:
                self._filled.append({"label": box["label"], "value": "Ticked", "kind": "choice", "check": form_choices.CHECK})
            else:
                self._left.append({"label": box["label"], "why": "The page did not take the tick. Tick it yourself."})

    def _write(self) -> None:
        fill, url = self._fill, self._page["url"]
        if not fill:
            return
        try:
            done = form_fill.fill_answer(chrome.run(form_fill.fill_script(fill, url)))
        except (chrome.ChromeError, ValueError) as e:
            raise Stop(str(e)) from e
        if done["moved"]:
            raise Stop("The tab changed while I was working, so I wrote nothing. Go back to the form and ask me again.")
        thrown = self._type_again([i["n"] for i in fill if i["n"] in done["done"]])
        self._written = [n for n in done["done"] if n not in thrown]
        for item in fill:
            if item["n"] in self._written:
                self._filled.append({"label": item["label"], "kind": item["kind"], "check": item.get("check", ""),
                                    "value": item["value"] if len(item["value"]) <= SHOWN else item["value"][:SHOWN].rstrip() + "…"})
            elif item["n"] in thrown:
                self._left.append({"label": item["label"], "why": form_fill.THROWN})
            else:
                self._left.append({"label": item["label"], "why": "The page did not take it: the field changed or was filled in the meantime. Type this one yourself."})

    def _type_again(self, texts: list[int]) -> list[int]:
        """Some pages throw away what did not arrive as typing: look again, and write those the way typing arrives.
        Returns the fields that are still empty after that."""
        if not texts:
            return []
        url = self._page["url"]
        try:
            chrome.pause(0.35)
            lost = set(form_fill.empty_answer(chrome.run(form_fill.empty_script(texts, url))))
            if not lost:
                return []
            chrome.run(form_fill.fill_script([i for i in self._fill if i["n"] in lost], url, typed=True))
            chrome.pause(0.35)
            return form_fill.empty_answer(chrome.run(form_fill.empty_script(sorted(lost), url)))
        except chrome.ChromeError:
            return []                       # looking again failed: what was written is reported as it was

    def _attach_files(self) -> None:
        if not self._todo["attach"]:
            return
        try:
            attached, not_attached, moved = self._attach(self._todo["attach"], self._page, self._job)
        except (chrome.ChromeError, ValueError) as e:
            raise Stop(str(e)) from e
        if moved:
            raise Stop("The tab changed while I was attaching your files. Go back to the form, look what it holds, and ask me again.")
        self._filled += attached
        self._left += not_attached

    def _report(self, host: str) -> dict[str, Any]:
        page, job, filled, left, added = self._page, self._job, self._filled, self._left, self._added
        kept = sum(1 for f in page["fields"] if f["filled"])
        label = f"{job.get('title', '')} at {job.get('company', '')}" if job else ""
        if job and filled and job.get("status") in store.LEAD_STATUSES:
            today = date.today().isoformat()        # so that the app can remind you when a filled form was never marked applied
            self._editor.change(job["id"], lambda jobs, j: j.__setitem__("form_filled", today), render=False)
        return {"ok": True, "action": "fill", "host": host, "url": page["url"],
                "job_id": job["id"] if job else "", "job": label, "guessed": self._guessed,
                "wants_file": any(i["why"] in form_fill.FILE_REASONS or "Attach it yourself" in i["why"] for i in left),
                "has_files": bool(self._mine["files"] or (job and (job.get("tailored_cv_file") or job.get("cover_letter_file")))),
                "is_lead": bool(job and job.get("status") in store.LEAD_STATUSES), "can_learn": bool(self.learned()["items"]),
                "filled": filled, "left": left, "kept": kept, "boxes": page["boxes"],
                "added_rows": added,
                "say": assistant.summary(host, filled, left, kept, page["boxes"], label, self._guessed)
                       + (f" I asked the form for {added} more row{'' if added == 1 else 's'} for your jobs and degrees." if added else "")}

    # ── how each step talks to the page ─────────────────────────
    def _letter_text(self, j) -> str:
        """The body of the letter the app wrote for this job ('' when there is none it can read)."""
        try:
            if j and self._app.editable_letter(j):
                return "\n\n".join(p for p in cover_letter.read_letter(self._app.letter_path(j))["paragraphs"] if p.strip())
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
        self._editor.change(job["id"], keep, render=False)
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

    def _choices(self, choices: list[dict[str, Any]], url: str, mine: dict[str, str], job) -> tuple[list[dict], list[dict], list[dict]]:
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

    def _job_of_page(self, jobs: list[dict], page: dict[str, Any]):
        """The job a form belongs to, although the form is rarely at the address of its posting (see form_fill.match_job)."""
        found = form_fill.match_job(jobs, page["url"], page["title"], page.get("from", ""))
        if not found:
            try:
                words = form_fill.page_answer(chrome.run(form_fill.PAGE))["text"][:6000]
            except (chrome.ChromeError, ValueError):
                words = ""
            found = form_fill.match_job(jobs, page["url"], page["title"], page.get("from", ""), words, self._app.recently_opened())
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
