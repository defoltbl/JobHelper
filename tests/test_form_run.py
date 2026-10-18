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
