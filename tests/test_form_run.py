"""One fill of a form is one FormFillRun: a step that cannot go on stops the run with what the person is told."""
from jobhelper import chrome, form_run, ui_api


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
    for bad in ("", "chrome://settings", "file:///Users/x/form.html", "https://", "javascript:alert(1)"):
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
