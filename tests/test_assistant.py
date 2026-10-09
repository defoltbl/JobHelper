"""The assistant: your details, the link to Chrome, reading a form, deciding what each field is,
and filling in only what is safe to fill. The page scripts run in a real browser engine on a local page."""
import json
import os
import subprocess
import sys

import pytest

from jobhelper import assistant, chrome, config, details, form_answers, form_fill, llm, store, ui_api, vault
from tests.conftest import FIXTURES

MINE = {"first_name": "Alex", "last_name": "Novak", "email": "alex@example.com", "phone": "+420 123 456 789", "street": "",
        "city": "Brno", "postcode": "602 00", "country": "Czechia", "linkedin": "https://linkedin.com/in/alexnovak",
        "github": "https://github.com/alexnovak", "website": ""}
CV = "Alex Novak\nalex@example.com | +420 123 456 789 | linkedin.com/in/alexnovak | github.com/alexnovak\nJunior analyst. SQL, Excel, Python."


@pytest.fixture
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "JOBS_JSON", tmp_path / "jobs.json")
    monkeypatch.setattr(config, "LETTERS_DIR", tmp_path / "letters")
    monkeypatch.setattr(config, "ensure_dirs", lambda: None)
    monkeypatch.setattr(ui_api.agent4_tracker, "render_all", lambda jobs: None)
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: CV)
    monkeypatch.setattr(ui_api.Api, "_my_name", lambda self: "Alex Novak")
    return tmp_path


def _job(**more):
    return {"id": "nw1", "title": "Junior Analyst", "company": "Northwind", "location": "Brno", "status": "letter_ready",
            "url": "https://careers.northwind.example/jobs/42", "description": "Reports in SQL.", **more}


# ── My details ──────────────────────────────────────────────────────────────
def test_details_are_checked_field_by_field():
    clean, problem = details.check({**MINE, "linkedin": "linkedin.com/in/alexnovak", "first_name": "  Alex  "})
    assert problem == {} and clean["linkedin"] == "https://linkedin.com/in/alexnovak" and clean["first_name"] == "Alex"
    assert details.check({})[0] == details.empty(), "every field may be left empty"
    for field, bad, word in (("email", "alex@example", "email address"), ("email", "alex example.com", "email address"),
                             ("phone", "call me", "digits"), ("phone", "12345", "6 to 15"), ("phone", "+420 +123 456 789", "digits"),
                             ("first_name", "Alex2", "letters"), ("country", "CZ-1", "letters"), ("postcode", "602;00", "postcode"),
                             ("linkedin", "https://example.com/alex", "linkedin.com"), ("github", "my git hub", "no spaces"),
                             ("website", "not a link", "no spaces"), ("city", "x" * 81, "the most is 80"), ("email", 5, "must be text")):
        clean, problem = details.check({**MINE, field: bad})
        assert clean == {} and problem["field"] == field and word in problem["msg"], (field, bad, problem)
    assert details.check("nonsense")[1]["msg"] and details.check(None)[1]["msg"]


def test_details_are_saved_encrypted_and_read_back(isolate):
    assert details.load() == details.empty()
    assert details.save({**MINE, "email": "nope"}) == {"ok": False, "field": "email", "msg": details.check({"email": "nope"})[1]["msg"]}
    assert not details.path().exists(), "a refused page saves nothing"
    assert details.save(MINE)["ok"] and details.load() == MINE
    assert details.path() in vault.data_files(), "kept with the files that are encrypted and backed up"
    details.path().write_text("{ not json")
    assert details.load() == details.empty()


def test_the_cv_only_offers_what_it_plainly_states(isolate):
    offered = details.from_cv(CV, "Alex Novak")
    assert offered == {"first_name": "Alex", "last_name": "Novak", "email": "alex@example.com", "phone": "+420 123 456 789",
                       "linkedin": "https://linkedin.com/in/alexnovak", "github": "https://github.com/alexnovak"}
    assert details.from_cv("Worked 2019 - 2023 on 12 000 000 rows", "") == {}, "years and counts are not a phone number"
    api = ui_api.Api()
    shown = api.my_details()
    assert shown["saved"] is False and shown["details"]["email"] == "alex@example.com" and "email" in shown["from_cv"]
    assert shown["details"]["city"] == "" and [f["key"] for f in shown["fields"]] == list(details.KEYS)
    assert not details.path().exists(), "offered, not saved"
    assert api.save_my_details({**shown["details"], "city": "Brno"})["ok"]
    again = api.my_details()
    assert again["saved"] and again["from_cv"] == [] and again["details"]["city"] == "Brno"
    assert api.check_my_details({"phone": "x"})["field"] == "phone" and api.check_my_details(MINE) == {}


# ── the link to Chrome ──────────────────────────────────────────────────────
class _Done:
    def __init__(self, out="", err="", code=0):
        self.stdout, self.stderr, self.returncode = out, err, code


def _chrome(monkeypatch, done=None, error=None):
    calls = []

    def run(command, **kw):
        calls.append((command, kw))
        if error:
            raise error
        return done
    monkeypatch.setattr(chrome, "_osascript", chrome_osascript)
    monkeypatch.setattr(chrome.subprocess, "run", run)
    return calls


chrome_osascript = chrome._osascript       # the real one: conftest replaces it with a guard for every test


def test_the_tab_in_front_is_read_and_a_script_travels_as_an_argument(monkeypatch):
    calls = _chrome(monkeypatch, _Done("https://jobs.example.com/apply/7\nApply - Example\n"))
    assert chrome.active_tab() == {"url": "https://jobs.example.com/apply/7", "title": "Apply - Example"}
    command, kw = calls[0]
    assert command[0] == "osascript" and kw["timeout"] == chrome.TIMEOUT and kw["capture_output"] and "shell" not in kw
    assert any("is not running" in part for part in command), "Chrome is never started by the app"
    calls = _chrome(monkeypatch, _Done('{"a": 1}\n'))
    script = 'alert("x\\\'y"); `back`'
    assert chrome.run(script) == '{"a": 1}'
    command = calls[0][0]
    assert command[-1] == script and not any(script in part for part in command[:-1]), "the script is data for AppleScript, not part of it"
    _chrome(monkeypatch, _Done("missing value\n"))
    assert chrome.run("void 0") == ""


@pytest.mark.parametrize("done, error, said", [
    (_Done("JOBHELPER_NOT_RUNNING\n"), None, chrome.NOT_RUNNING),
    (_Done("JOBHELPER_NO_WINDOW\n"), None, chrome.NO_WINDOW),
    (_Done(err="execution error: Not authorized to send Apple events to Google Chrome. (-1743)", code=1), None, chrome.NO_CONSENT),
    (_Done(err="execution error: Google Chrome got an error: Executing JavaScript through AppleScript is turned off. To turn it on, "
               "from the menu bar, go to View > Developer > Allow JavaScript from Apple Events.", code=1), None, chrome.NO_SCRIPTS),
    (_Done(err="execution error: Google Chrome got an error: Can’t get window 1. Invalid index. (-1719)", code=1), None, chrome.NO_WINDOW),
    (_Done(err="something else entirely", code=1), None, "Chrome refused the request"),
    (None, subprocess.TimeoutExpired("osascript", 20), chrome.NO_ANSWER),
    (None, FileNotFoundError("osascript"), chrome.NO_OSASCRIPT)])
def test_every_way_chrome_can_refuse_is_said_in_words(monkeypatch, done, error, said):
    _chrome(monkeypatch, done, error)
    with pytest.raises(chrome.ChromeError) as e:
        chrome.run("1")
    assert said in str(e.value)
    assert "osascript" not in str(e.value) or said == chrome.NO_OSASCRIPT


def test_tests_cannot_reach_the_real_chrome():
    with pytest.raises(AssertionError):
        chrome.active_tab()


# ── what a field is ─────────────────────────────────────────────────────────
def _field(label="", kind="text", **more):
    return {"n": 1, "type": kind, "label": label, "name": "", "id": "", "auto": "", "hint": "", "filled": False, "most": 0, "options": [], **more}


@pytest.mark.parametrize("field, what", [
    (_field("First name"), "first_name"), (_field("Given name(s) *"), "first_name"), (_field("", name="firstName"), "first_name"),
    (_field("Surname"), "last_name"), (_field("", id="applicant_last_name"), "last_name"),
    (_field("Full name"), "full_name"), (_field("Name"), "full_name"), (_field("Your name *"), "full_name"),
    (_field("Email address"), "email"), (_field("", kind="email"), "email"), (_field("Confirm e-mail"), "email"),
    (_field("Mobile number"), "phone"), (_field("", kind="tel"), "phone"),
    (_field("LinkedIn URL"), "linkedin"), (_field("GitHub profile"), "github"), (_field("Portfolio / website"), "website"),
    (_field("Postal code"), "postcode"), (_field("ZIP"), "postcode"), (_field("City"), "city"), (_field("Location (City)"), "city"),
    (_field("Current location"), "location"), (_field("Street address"), "street"), (_field("Country", kind="select"), "country"),
    (_field("", auto="section-a given-name"), "first_name"), (_field("x", auto="postal-code"), "postcode"),
    (_field("Why do you want to work with us?", kind="textarea"), "question"), (_field("What are your salary expectations?"), "question"),
    (_field("Tell us about a project you are proud of", kind="textarea"), "question"),
    (_field("Cover letter", kind="textarea"), "letter"), (_field("Motivation letter (optional)", kind="textarea"), "letter"),
    (_field("How did you get your name known in the field?", kind="textarea"), "question")])
def test_fields_are_recognised_by_what_the_page_calls_them(field, what):
    assert form_fill.classify(field) == (what, "")


@pytest.mark.parametrize("field, why", [
    (_field("Password", kind="password"), form_fill.PASSWORD), (_field("Email", kind="password"), form_fill.PASSWORD),
    (_field("Resume/CV", kind="file"), form_fill.FILE),
    (_field("Date of birth"), form_fill.PRIVATE), (_field("Gender", kind="select"), form_fill.PRIVATE),
    (_field("Disability status", kind="select"), form_fill.PRIVATE), (_field("Card number"), form_fill.PRIVATE),
    (_field("Passport number"), form_fill.PRIVATE), (_field("Race / Ethnicity", kind="select"), form_fill.PRIVATE),
    (_field("Veteran status", kind="select"), form_fill.PRIVATE), (_field("IBAN"), form_fill.PRIVATE),
    (_field("Start date", kind="date"), form_fill.DATE),
    (_field("Notice period", kind="select"), form_fill.CHOICE), (_field("Phone country code", kind="select"), form_fill.CHOICE),
    (_field("Company name"), form_fill.UNKNOWN), (_field("School name"), form_fill.UNKNOWN), (_field("Referee's name"), form_fill.UNKNOWN),
    (_field("Username"), form_fill.UNKNOWN), (_field("Job title"), form_fill.UNKNOWN), (_field("Years", kind="number"), form_fill.UNKNOWN),
    (_field(""), form_fill.UNKNOWN), (_field("???", kind="textarea"), form_fill.UNKNOWN)])
def test_what_is_not_the_assistants_to_fill_is_left_with_the_reason(field, why):
    assert form_fill.classify(field) == ("", why)


def test_the_plan_fills_details_asks_questions_and_leaves_the_rest():
    fields = [_field("First name", n=1), _field("Full name", n=2), _field("City", n=3, filled=True), _field("Website", n=4),
              _field("Why us?", kind="textarea", n=5), _field("Why us?", kind="textarea", n=6), _field("Cover letter", kind="textarea", n=7),
              _field("Email", n=8, most=5), _field("Where are you based", n=9), _field("Password", kind="password", n=10)]
    todo = form_fill.plan(fields, MINE, letter="Dear team,\n\nI write to apply.", has_job=True)
    assert [(f["n"], f["value"], f["kind"]) for f in todo["fill"]] == [(1, "Alex", "detail"), (2, "Alex Novak", "detail"),
                                                                       (7, "Dear team,\n\nI write to apply.", "letter"), (9, "Brno, Czechia", "detail")]
    assert todo["ask"] == [{"n": 5, "label": "Why us?", "most": 0}]
    left = {i["label"]: i["why"] for i in todo["left"]}
    assert "website" in left["Website"] and "My details" in left["Website"]
    assert "5 characters" in left["Email"] and left["Password"] == form_fill.PASSWORD and "same question" in left["Why us?"]
    assert "City" not in left and all(f["n"] != 3 for f in todo["fill"]), "a field that holds something is not touched"
    alone = form_fill.plan(fields, {**MINE, "last_name": ""}, has_job=False)
    assert alone["ask"] == [] and sum(1 for i in alone["left"] if i["why"] == form_fill.NO_JOB) == 2
    assert any(i["why"] == form_fill.NO_LETTER for i in alone["left"]) and all(f["n"] != 2 for f in alone["fill"]), "half a name is not a name"
    many = form_fill.plan([_field(f"Question number {i}, in words?", kind="textarea", n=i) for i in range(1, 20)], MINE, has_job=True)
    assert len(many["ask"]) == form_answers.MAX_QUESTIONS and sum(1 for i in many["left"] if i["why"] == form_fill.TOO_MANY) == 4


def test_what_a_page_answers_is_never_trusted():
    for bad in ("", "not json", "[]", '{"fields": "x"}', "null"):
        with pytest.raises(ValueError):
            form_fill.read_answer(bad)
    page = form_fill.read_answer(json.dumps({"url": "https://x.example/a", "title": 5, "boxes": "many", "frames": "none",
                                             "fields": [{"n": 1, "label": "A" * 900, "type": None, "options": "x", "most": "9"}, {"n": "2"}, "junk"]}))
    assert len(page["fields"]) == 1 and len(page["fields"][0]["label"]) == 300 and page["fields"][0]["options"] == [] and page["fields"][0]["most"] == 0
    assert page["boxes"] == 0 and page["frames"] == [] and page["title"] == "5"
    assert form_fill.fill_answer('{"moved": true}') == {"moved": True, "done": [], "skipped": []}
    assert form_fill.fill_answer('{"done": [1, "x", 3], "skipped": 7}') == {"moved": False, "done": [1, 3], "skipped": []}
    with pytest.raises(ValueError):
        form_fill.fill_answer("<html>")


def test_values_travel_into_the_page_as_data_and_nothing_is_ever_clicked():
    nasty = 'Alex"); document.forms[0].submit(); ("\n</script> `${1}`'
    script = form_fill.fill_script([{"n": 3, "value": nasty, "check": "look"}], 'https://x.example/a"b')
    tail = script[script.rindex("})(") + 3:-1]
    items, _sep, url = tail.rpartition(", ")
    assert json.loads(items) == [{"n": 3, "value": nasty, "check": True}] and json.loads(url) == 'https://x.example/a"b'
    assert " " not in script and "\n</script>" not in script
    for code in (form_fill.READ, form_fill.FILL):
        for never in (".click(", "submit(", ".checked", "requestSubmit", "fetch(", "XMLHttpRequest", "sendBeacon", "eval(", "innerHTML", "cookie", "localStorage"):
            assert never not in code, never
    assert "el.value" not in form_fill.READ.replace("String(el.value || '').trim() !== ''", ""), "what you typed is only ever tested for being empty"


def test_a_page_is_matched_to_a_job_only_when_it_is_plain():
    jobs = [_job(), _job(id="nw2", title="Data Analyst", url="https://careers.northwind.example/jobs/43"),
            _job(id="gd", company="Good Data", title="Analyst", url="https://gooddata.example/"),
            _job(id="solo", company="Brightpath s.r.o.", title="Analyst", url="")]
    assert form_fill.match_job(jobs, "https://careers.northwind.example/jobs/42/?utm=x", "Apply") == "nw1"
    assert form_fill.match_job(jobs, "https://boards.example.net/brightpath/apply", "Application") == "solo"
    assert form_fill.match_job(jobs, "https://ats.example.net/form/9", "Data Analyst - Northwind careers") == "nw2"
    assert form_fill.match_job(jobs, "https://ats.example.net/form/9", "Careers at Northwind") == "", "two jobs there: you choose"
    assert form_fill.match_job(jobs, "https://ats.example.net/form/9", "Good morning data fans") == "", "shared words name nobody"
    assert form_fill.match_job(jobs, "https://gooddata.example/", "Home") == "gd", "the company's own site"
    board = [_job(id="b1", company="Quillon", url="https://portal.example/")]
    assert form_fill.match_job(board, "https://portal.example/", "Home") == "", "a home page is not one posting's address"
    assert form_fill.match_job([], "not a url", "") == ""


# ── what a request means ────────────────────────────────────────────────────
@pytest.mark.parametrize("text, what", [
    ("fill form in chrome", "fill"), ("Please fill in the form", "fill"), ("help me apply", "fill"), ("complete this application", "fill"),
    ("fill in my details on the form", "fill"), ("my details", "details"), ("change my phone", "details"), ("show my contacts", "details"),
    ("hi", "help"), ("what can you do?", "help"), ("how does this work", "help"), ("sing a song", "unknown"), ("", "unknown")])
def test_a_request_is_understood_by_its_words(text, what):
    assert assistant.intent(text) == what


def test_requests_are_checked_before_anything_is_done(isolate):
    api = ui_api.Api()
    assert api.assistant_ask("   ") == {"ok": False, "action": "none", "msg": assistant.EMPTY}
    assert api.assistant_ask("x" * 301)["msg"] == assistant.TOO_LONG and api.assistant_ask(None)["ok"] is False
    assert api.assistant_ask("my details")["action"] == "details"
    assert api.assistant_ask("hello")["say"] == assistant.HELP and api.assistant_ask("sing")["say"].startswith("I did not understand")
    refused = api.assistant_ask("fill the form in chrome")
    assert refused["ok"] is False and refused["action"] == "details" and "My details" in refused["msg"], "nothing to fill in with yet"


# ── filling in, end to end (Chrome replaced by a real browser engine on a local page) ──
def _in_page(*scripts):
    done = subprocess.run([sys.executable, str(FIXTURES / "run_in_page.py"), str(FIXTURES / "application_form.html")],
                          input=json.dumps(list(scripts)), capture_output=True, text=True, timeout=120,
                          env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    if done.returncode != 0:
        pytest.skip(f"the browser engine did not start here: {done.stderr[-200:]}")
    return json.loads(done.stdout)


STATE = """JSON.stringify({
  fn: document.getElementById('fn').value, ln: document.getElementById('ln').value,
  email: document.querySelector('[type=email]').value, phone: document.querySelector('[type=tel]').value,
  linkedin: document.querySelector('[type=url]').value, city: document.getElementById('city').value,
  country: document.getElementById('country').value, notice: document.getElementById('notice').value,
  why: document.getElementById('why').value, letter: document.getElementById('letter').value,
  pw: document.getElementById('pw').value, dob: document.getElementById('dob').value, company: document.getElementById('company').value,
  terms: document.getElementById('terms').checked, visa: !!document.querySelector('[name=visa]:checked'),
  token: document.querySelector('[name=token]').value, trap: document.querySelector('[name=trap]').value,
  zip: document.getElementById('host').shadowRoot.getElementById('zip').value,
  github: document.getElementById('inner').contentDocument.getElementById('gh').value,
  heard: window.heard, sent: !!window.sent, clicked: !!window.clicked,
  outline: document.getElementById('fn').style.outline, amber: document.getElementById('why').style.outline})"""


def test_a_real_form_is_read_filled_and_never_sent():
    page = form_fill.read_answer(_in_page(form_fill.READ)[0])
    by_name = {f["name"]: f for f in page["fields"]}
    assert set(by_name) == {"first_name", "last_name", "applicant[email]", "phone", "urls[LinkedIn]", "city", "country", "notice", "why",
                            "cover_letter", "cv", "password", "dob", "company_name", "zip", "github"}, "hidden fields and tick boxes are not listed"
    assert by_name["city"]["filled"] and not by_name["first_name"]["filled"] and page["boxes"] == 3
    assert by_name["applicant[email]"]["label"] == "Email address" and by_name["zip"]["label"] == "Postal code"
    assert "Already here" not in json.dumps(page) and "secret-token" not in json.dumps(page), "what the page holds is not sent back"
    todo = form_fill.plan(page["fields"], MINE, letter="Dear team,\n\nI apply.", has_job=True)
    assert [q["label"] for q in todo["ask"]] == ["Why do you want to work at Northwind?"]
    fill = todo["fill"] + [{"n": todo["ask"][0]["n"], "value": "Because of your SQL reports.", "check": "look"},
                           {"n": by_name["city"]["n"], "value": "Overwritten?"}, {"n": 999, "value": "nowhere"}]
    read_again, done, state = _in_page(form_fill.READ, form_fill.fill_script(fill, page["url"]), STATE)
    assert form_fill.read_answer(read_again)["fields"] == page["fields"], "reading twice numbers the fields the same way"
    done, state = form_fill.fill_answer(done), json.loads(state)
    assert state["fn"] == "Alex" and state["ln"] == "Novak" and state["email"] == "alex@example.com" and state["phone"] == "+420 123 456 789"
    assert state["linkedin"] == MINE["linkedin"] and state["country"] == "CZ" and state["zip"] == "602 00" and state["github"] == MINE["github"]
    assert state["why"] == "Because of your SQL reports." and state["letter"] == "Dear team,\n\nI apply."
    assert state["heard"] == ["Alex"], "the page was told, the way a person typing tells it"
    assert "34, 197, 94" in state["outline"] and "245, 158, 11" in state["amber"], "green for filled, amber for check this"
    assert state["city"] == "Already here" and by_name["city"]["n"] in done["skipped"] and 999 in done["skipped"]
    assert state["notice"] == "" and state["pw"] == "" and state["dob"] == "" and state["company"] == "" and state["trap"] == ""
    assert state["terms"] is False and state["visa"] is False and state["token"] == "secret-token"
    assert state["sent"] is False and state["clicked"] is False
    assert _in_page(form_fill.fill_script(todo["fill"], "https://elsewhere.example/"))[0] == '{"moved":true}', "another page gets nothing"


def _browser(monkeypatch, fields, url="https://careers.northwind.example/jobs/42", title="Junior Analyst - Northwind", frames=(), boxes=0, done=None):
    ran = []
    monkeypatch.setattr(chrome, "active_tab", lambda: {"url": url, "title": title})

    def run(script):
        ran.append(script)
        if script == form_fill.READ:
            return json.dumps({"url": url, "title": title, "fields": fields, "frames": list(frames), "boxes": boxes})
        items = json.loads(script[script.rindex("})(") + 3:-1].rpartition(", ")[0])
        return json.dumps(done if done is not None else {"done": [i["n"] for i in items], "skipped": []})
    monkeypatch.setattr(chrome, "run", run)
    return ran


def test_the_assistant_fills_in_details_and_answers_and_says_what_it_did(isolate, monkeypatch):
    store.save_jobs([_job()])
    details.save(MINE)
    asked = []
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: asked.append(prompt) or {"answers": [
        {"n": 1, "answer": "Your reports are built in SQL, which I use daily.", "needs_you": ""},
        {"n": 2, "answer": "I can start on [your start date].", "needs_you": "Your start date"}]})
    fields = [_field("First name", n=1), _field("Email", n=2), _field("Why Northwind?", kind="textarea", n=3), _field("When can you start?", n=4),
              _field("CV", kind="file", n=5), _field("City", n=6, filled=True), _field("Notice period", kind="select", n=7)]
    ran = _browser(monkeypatch, fields, boxes=2)
    api = ui_api.Api()
    out = api.assistant_ask("fill the form in chrome")
    assert out["ok"] and out["action"] == "fill" and out["host"] == "careers.northwind.example"
    assert out["job_id"] == "nw1" and out["guessed"] and out["job"] == "Junior Analyst at Northwind"
    assert [(f["label"], f["kind"]) for f in out["filled"]] == [("First name", "detail"), ("Email", "detail"), ("Why Northwind?", "answer"), ("When can you start?", "answer")]
    assert out["filled"][3]["check"] == "Your start date" and out["filled"][2]["check"] == ""
    assert {i["label"] for i in out["left"]} == {"CV", "Notice period"} and out["kept"] == 1 and out["boxes"] == 2
    for part in ("4 fields", "2 from My details", "2 answers drafted from your CV", "Junior Analyst at Northwind", "1 answer needs", "2 fields are left",
                 "1 field already held", "2 tick boxes", "I never press Submit"):
        assert part in out["say"], part
    assert len(asked) == 1 and "1. Why Northwind?\n2. When can you start?" in asked[0] and len(ran) == 2
    kept = store.find(store.load_jobs(), "nw1")["form_answers"]["items"]
    assert [i["question"] for i in kept] == ["Why Northwind?", "When can you start?"], "the answers are kept with the job"
    again = api.assistant_fill("nw1")
    assert again["ok"] and not again["guessed"] and len(asked) == 1, "answers kept with the job are used again, not paid for twice"
    assert "The answers are for Junior Analyst at Northwind." in again["say"]


def test_without_a_job_only_details_are_filled_and_claude_is_not_asked(isolate, monkeypatch):
    details.save(MINE)
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("no job: nothing to ask about"))
    _browser(monkeypatch, [_field("Email", n=1), _field("Why us?", kind="textarea", n=2)], url="https://forms.example.org/a", title="Apply")
    out = ui_api.Api().assistant_fill()
    assert out["ok"] and out["job_id"] == "" and [f["label"] for f in out["filled"]] == ["Email"]
    assert out["left"] == [{"label": "Why us?", "why": form_fill.NO_JOB}]


@pytest.mark.parametrize("change, said", [
    (dict(url="chrome://settings/"), "not a web page with a form"),
    (dict(url="https://rabota.example.ru/apply"), "Russian services"),
    (dict(fields=[]), "no form fields"),
    (dict(fields=[], frames=["https://boards.frames.example/embed/job?id=7"]), "inside a frame from boards.frames.example"),
    (dict(done={"moved": True}), "tab changed"),
    (dict(job="gone"), "not in the list any more")])
def test_every_reason_not_to_fill_is_said(isolate, monkeypatch, change, said):
    store.save_jobs([_job()])
    details.save(MINE)
    job = change.pop("job", "")
    ran = _browser(monkeypatch, **{"fields": [_field("Email", n=1)], **change})
    out = ui_api.Api().assistant_fill(job)
    assert out["ok"] is False and said in out["msg"]
    if "url" in change:
        assert ran == [], "such a page is not even read"


def test_trouble_with_chrome_or_claude_is_told_and_the_rest_is_still_done(isolate, monkeypatch):
    store.save_jobs([_job()])
    details.save(MINE)
    monkeypatch.setattr(chrome, "active_tab", lambda: (_ for _ in ()).throw(chrome.ChromeError(chrome.NO_SCRIPTS)))
    assert ui_api.Api().assistant_fill()["msg"] == chrome.NO_SCRIPTS
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: (_ for _ in ()).throw(llm.LimitReached("Claude's limit is used up until 14:00.")))
    _browser(monkeypatch, [_field("Email", n=1), _field("Why Northwind?", kind="textarea", n=2), _field("Country", kind="select", n=3)],
             done={"done": [1], "skipped": [3]})
    out = ui_api.Api().assistant_fill("nw1")
    assert out["ok"] and [f["label"] for f in out["filled"]] == ["Email"]
    left = {i["label"]: i["why"] for i in out["left"]}
    assert "limit is used up until 14:00" in left["Why Northwind?"] and "did not take it" in left["Country"]
    assert "form_answers" not in store.find(store.load_jobs(), "nw1")


def test_the_job_list_for_the_assistant_holds_open_jobs_only(isolate):
    store.save_jobs([_job(), _job(id="r", status="rejected", company="Closed"), _job(id="w", status="waiting", company="Waiting")])
    assert [j["id"] for j in ui_api.Api().assistant_jobs()] == ["nw1", "w"] and ui_api.Api().assistant_jobs()[0]["label"] == "Northwind · Junior Analyst"
