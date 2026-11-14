"""One fill of a form is one FormFillRun: a step that cannot go on stops the run with what the person is told."""
import json

import pytest

from jobhelper import chrome, form_choices, form_fill, form_run, store, ui_api
from tests import test_assistant as ta


class _App:
    """The little of the facade a run asks for before it reads a page."""

    def __init__(self):
        self.browser_asked = 0

    def browser(self):
        self.browser_asked += 1

    def options(self):
        return {}


def test_a_stop_is_the_answer_the_person_gets():
    stop = form_run.Stop("The tab changed.", frame="https://forms.example")
    assert stop.answer == {"ok": False, "action": "fill", "msg": "The tab changed.", "frame": "https://forms.example"}
    assert str(stop) == "The tab changed."


def test_without_your_details_nothing_is_read_from_the_page(isolate_data, monkeypatch):
    read = []
    monkeypatch.setattr(chrome, "active_tab", lambda: read.append("tab") or {"url": "https://forms.example"})
    app = _App()
    out = form_run.FormFillRun(app, editor=None, cv=None).result()
    assert out["ok"] is False and out["action"] == "details" and "My details" in out["msg"]
    assert app.browser_asked == 1 and read == [], "the browser is chosen first, and no page is touched"


def test_a_stopped_fill_keeps_what_the_last_one_learned(isolate_data, monkeypatch):
    api = ui_api.Api()
    service = api._assistant
    service._last_fill = {"url": "https://earlier.example", "job_id": "a", "company": "Acme", "items": [{"n": 1, "label": "Why", "value": "x"}]}
    out = api.assistant_fill()
    assert out["ok"] is False and service._last_fill["url"] == "https://earlier.example"


def test_one_rule_says_which_pages_the_assistant_works_on():
    from jobhelper import form_fill
    page = form_fill.PageAddress("  https://careers.northwind.example/apply?id=4 ")
    assert page.is_web and not page.refused and page.host == "careers.northwind.example" and page.url.startswith("https://")
    for bad in ("", "chrome://settings", "file:///tmp/form.html", "https://", "javascript:alert(1)"):
        assert not form_fill.PageAddress(bad).is_web, bad
    assert form_fill.PageAddress("https://jobs.example.ru/1").refused
    assert form_fill.PageAddress("https://x.ru").refusal("read this site") == \
        "This app does not work with Russian services, so I do not read this site."


def test_the_plain_checks_of_a_form_read_back():
    from jobhelper import form_fill
    fields = [{"label": "Name", "value": "", "filled": False, "required": True, "kind": "text"},
              {"label": "Why us", "value": "Because [reason].", "filled": True, "required": False, "kind": "textarea"},
              {"label": "Email", "value": "Old@Example.com", "filled": True, "required": True, "kind": "email"},
              {"label": "Email again", "value": "alex@example.com", "filled": True, "required": True, "kind": "email"}]
    assert [p["field"] for p in form_fill.plain_problems(fields, "alex@example.com")] == ["Name", "Why us", "Email"]
    assert [p["field"] for p in form_fill.plain_problems(fields)] == ["Name", "Why us"], "no address in My details: none compared"


def test_the_review_says_the_note_before_what_is_yours_to_check():
    from jobhelper import assistant
    fields = [{"filled": True}, {"filled": False}]
    note = " Your master CV could not be read, so only the plain checks were made."
    assert assistant.review_summary("forms.example", fields, [{"field": "Name"}], note) == (
        "I read the form on forms.example: 1 of 2 fields are filled in, and 1 thing looks wrong."
        " Your master CV could not be read, so only the plain checks were made."
        " Tick boxes, files and personal questions are yours to check. I did not send anything.")
    assert "and I see nothing wrong. Tick boxes" in assistant.review_summary("forms.example", fields, [])


# ── #91: a fault after the page was changed still reports what is on it ─────
isolate = ta.isolate          # the helpers below share the stand-in browser and the data folder of test_assistant
URL = "https://careers.northwind.example/jobs/42"


def _fault_on_call(monkeypatch, module, name, at, error=KeyError("size")):
    """`module.name` works as before until its call number `at`, which raises `error`."""
    real, calls = getattr(module, name), []

    def wrapped(*args, **kw):
        calls.append(1)
        if len(calls) == at:
            raise error
        return real(*args, **kw)
    monkeypatch.setattr(module, name, wrapped)


def test_a_fault_after_one_file_was_attached_still_reports_the_file(isolate, tmp_path, monkeypatch):
    """No text field was written, so a fault after the CV went in said only "I could not fill in the form"."""
    ta._with_files(tmp_path)
    ta._browser(monkeypatch, [ta._field("Resume", kind="file", n=1), ta._field("Cover letter", kind="file", n=2)])
    _fault_on_call(monkeypatch, form_fill, "attach_answer", at=2)
    out = ui_api.Api().assistant_fill("nw1")
    assert out["ok"] is True, out
    assert [f["label"] for f in out["filled"]] == ["Resume"] and "went wrong" in out["stopped"]
    assert {i["label"]: i["why"] for i in out["left"]} == {"Cover letter": form_run.FormFillRun.NOT_REACHED}


def test_a_fault_after_one_choice_was_made_still_reports_the_choice(isolate, monkeypatch):
    """No text field was written, so a fault after a radio button was pressed lost that choice from the report."""
    store.save_jobs([ta._job()])
    ta.details.save(ta.MINE)
    radios = [ta._field("Do you need a visa?", kind="radio", n=1, options=["Yes", "No"]),
              ta._field("Can you travel?", kind="radio", n=2, options=["Yes", "No"])]
    ta._browser(monkeypatch, radios)
    real = chrome.run
    pressed = {form_fill.choose_script("radio", n, k, URL) for n in (1, 2) for k in (0, 1)}
    monkeypatch.setattr(chrome, "run", lambda script: '{"ok": true}' if script in pressed else real(script))
    monkeypatch.setattr(form_choices, "decide", lambda choices, cv, mine, job: {1: "No", 2: "Yes"})
    _fault_on_call(monkeypatch, form_fill, "choose_answer", at=2)
    out = ui_api.Api().assistant_fill("nw1")
    assert out["ok"] is True, out
    assert [(f["label"], f["value"]) for f in out["filled"]] == [("Do you need a visa?", "No")] and "went wrong" in out["stopped"]
    assert {i["label"]: i["why"] for i in out["left"]} == {"Can you travel?": form_run.FormFillRun.NOT_REACHED}


def test_a_fault_while_listing_the_fields_not_reached_still_gives_the_report(isolate, monkeypatch):
    store.save_jobs([ta._job()])
    ta.details.save(ta.MINE)
    ta._browser(monkeypatch, [ta._field("First name", n=1), ta._field("Email", n=2)])

    def broken(self):
        self._todo["attach"].append({})                  # an item with no label: the list of fields not reached breaks on it
        raise KeyError("size")
    monkeypatch.setattr(form_run.FormFillRun, "_attach_files", broken)
    out = ui_api.Api().assistant_fill("nw1")
    assert out["ok"] is True and [f["label"] for f in out["filled"]] == ["First name", "Email"], out
    assert "went wrong" in out["stopped"] and out["stopped"].endswith(form_run.FormFillRun.UNLISTED)


def _second_look(monkeypatch, answer):
    """The page of ta._typing, whose look after the second, typed writing answers `answer`."""
    real, looks = chrome.run, []

    def run(script):
        if "empty.push" in script:
            looks.append(1)
            if len(looks) == 2:
                return answer
        return real(script)
    monkeypatch.setattr(chrome, "run", run)


@pytest.mark.parametrize("second, look, why", [
    (lambda: (_ for _ in ()).throw(chrome.ChromeError(chrome.NO_ANSWER)), None, form_run.FormFillRun.NOT_CHECKED),
    (lambda: json.dumps({"moved": True}), None, form_run.FormFillRun.NOT_CHECKED),
    (lambda: "junk", None, form_run.FormFillRun.NOT_CHECKED),
    (lambda: json.dumps({"done": [1], "skipped": []}), json.dumps({"moved": True}), form_run.FormFillRun.NOT_CHECKED),
    (lambda: json.dumps({"done": [1], "skipped": []}), "", form_run.FormFillRun.NOT_CHECKED),
    (lambda: json.dumps({"done": [1], "skipped": []}), json.dumps({"empty": [1]}), form_fill.THROWN),
    (lambda: json.dumps({"done": [], "skipped": [1]}), None, form_fill.THROWN)])
def test_a_field_the_second_check_could_not_see_is_not_said_to_be_thrown_away(isolate, monkeypatch, second, look, why):
    """#91: when Chrome stopped answering or the tab changed during the second check, the field was said to be
    thrown away twice, which nobody saw."""
    store.save_jobs([ta._job()])
    ta.details.save(ta.MINE)
    ta._typing(monkeypatch, second)
    if look is not None:
        _second_look(monkeypatch, look)
    out = ui_api.Api().assistant_fill("nw1")
    assert out["ok"], out
    assert [f["label"] for f in out["filled"]] == ["Email"]
    assert {i["label"]: i["why"] for i in out["left"]}["First name"] == why


def test_a_field_the_second_writing_took_is_reported_written(isolate, monkeypatch):
    store.save_jobs([ta._job()])
    ta.details.save(ta.MINE)
    ta._typing(monkeypatch, lambda: json.dumps({"done": [1], "skipped": []}))
    out = ui_api.Api().assistant_fill("nw1")
    assert [f["label"] for f in out["filled"]] == ["First name", "Email"] and out["left"] == [], out


def _chrome_stops_at(monkeypatch, *starts):
    """The stand-in browser stops answering at every script that holds one of `starts`."""
    real = chrome.run

    def run(script):
        if any(part in script for part in starts):
            raise chrome.ChromeError(chrome.NO_ANSWER)
        return real(script)
    monkeypatch.setattr(chrome, "run", run)
    monkeypatch.setattr(chrome, "pause", lambda seconds: None)


def test_a_stop_after_a_field_was_written_but_not_checked_still_reports_it(isolate, tmp_path, monkeypatch):
    """#91: the only text field was written, but Chrome stopped answering at the look after it and then at the file:
    nothing was filled, so the run said only that Chrome stopped, and the field on the page was not named."""
    ta._with_files(tmp_path)
    ta._browser(monkeypatch, [ta._field("First name", n=1), ta._field("Resume", kind="file", n=2)])
    _chrome_stops_at(monkeypatch, "empty.push", "(function (key, part, url)")
    out = ui_api.Api().assistant_fill("nw1")
    assert out["ok"] is True and out["filled"] == [] and out["stopped"] == chrome.NO_ANSWER, out
    assert {i["label"]: i["why"] for i in out["left"]} == {"First name": form_run.FormFillRun.NOT_CHECKED,
                                                           "Resume": form_run.FormFillRun.NOT_REACHED}


def test_a_stop_while_the_only_radio_was_pressed_names_it_to_be_checked(isolate, monkeypatch):
    """#91: Chrome stopped answering during the press of the only radio button, which may have taken: the run said
    only that Chrome stopped, and not which choice to check."""
    store.save_jobs([ta._job()])
    ta.details.save(ta.MINE)
    ta._browser(monkeypatch, [ta._field("Do you need a visa?", kind="radio", n=1, options=["Yes", "No"])])
    monkeypatch.setattr(form_choices, "decide", lambda choices, cv, mine, job: {1: "No"})
    _chrome_stops_at(monkeypatch, form_fill.choose_script("radio", 1, 1, URL))
    out = ui_api.Api().assistant_fill("nw1")
    assert out["ok"] is True and out["filled"] == [] and out["stopped"] == chrome.NO_ANSWER, out
    assert {i["label"]: i["why"] for i in out["left"]} == {"Do you need a visa?": form_run.FormChoices.UNSURE.format(pick="No")}


def test_a_choice_the_page_refused_keeps_its_reason_after_a_fault(isolate, monkeypatch):
    """#91: a fault at the next press replaced "The page did not take the choice" with "I stopped before I came to it"."""
    store.save_jobs([ta._job()])
    ta.details.save(ta.MINE)
    asked = ["Do you need a visa?", "Can you travel?", "Can you relocate?"]
    ta._browser(monkeypatch, [ta._field(label, kind="radio", n=n, options=["Yes", "No"]) for n, label in enumerate(asked, 1)])
    real = chrome.run
    answers = {form_fill.choose_script("radio", n, 1, URL): ok for n, ok in ((1, "true"), (2, "false"), (3, "true"))}
    monkeypatch.setattr(chrome, "run", lambda script: '{"ok": %s}' % answers[script] if script in answers else real(script))
    monkeypatch.setattr(form_choices, "decide", lambda choices, cv, mine, job: {1: "No", 2: "No", 3: "No"})
    _fault_on_call(monkeypatch, form_fill, "choose_answer", at=3)
    out = ui_api.Api().assistant_fill("nw1")
    assert out["ok"] is True and [f["label"] for f in out["filled"]] == ["Do you need a visa?"] and "went wrong" in out["stopped"], out
    assert {i["label"]: i["why"] for i in out["left"]} == {"Can you travel?": "The page did not take the choice. Choose it yourself.",
                                                           "Can you relocate?": form_run.FormFillRun.NOT_REACHED}


def test_the_tab_changed_texts_are_the_runs_own():
    run = form_run.FormFillRun
    assert run.MOVED_READING.startswith("The tab changed while I was reading") and "wrote nothing" in run.MOVED_READING
    assert run.MOVED_WRITING.startswith("The tab changed while I was working") and "wrote nothing" in run.MOVED_WRITING
