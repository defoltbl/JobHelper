"""The assistant: your details, the link to Chrome, reading a form, deciding what each field is,
and filling in only what is safe to fill. The page scripts run in a real browser engine on a local page."""
import json
import os
import subprocess
import sys

import pytest

from jobhelper import answer_memory, assistant, chrome, config, details, form_answers, form_choices, form_fill, llm, store, ui_api, vault
from tests.conftest import FIXTURES

MINE = {**details.empty(), "first_name": "Alex", "last_name": "Novak", "email": "alex@example.com", "phone": "+420 123 456 789", "street": "",
        "city": "Brno", "postcode": "602 00", "country": "Czechia", "linkedin": "https://linkedin.com/in/alexnovak",
        "github": "https://github.com/alexnovak", "website": ""}
CV = "Alex Novak\nalex@example.com | +420 123 456 789 | linkedin.com/in/alexnovak | github.com/alexnovak\nJunior analyst. SQL, Excel, Python."


@pytest.fixture
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "JOBS_JSON", tmp_path / "jobs.json")
    monkeypatch.setattr(config, "LETTERS_DIR", tmp_path / "letters")
    for name, value in (("RESPONSES_DB", tmp_path / "responses.db"), ("PROFILE_JSON", tmp_path / "profile.json"), ("CV_DIR", tmp_path / "cv"),
                        ("TAILORED_CV_DIR", tmp_path / "tailored"), ("EXCEL_PATH", tmp_path / "a.xlsx"), ("NEW_JOBS_EXCEL", tmp_path / "n.xlsx")):
        monkeypatch.setattr(config, name, value)          # nothing of the real data folder is in reach
    for folder in ("cv", "tailored", "letters"):
        (tmp_path / folder).mkdir()
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
    assert details.any_given(details.empty()) is False and details.any_given(MINE)
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
    (_field("Why do you want to work with us?", kind="textarea"), "question"), (_field("What are your salary expectations?"), "salary"),
    (_field("Notice period"), "notice_period"), (_field("Current employer"), "employer"), (_field("Most recent company"), "employer"),
    (_field("Company"), "employer"), (_field("Company name"), "employer"), (_field("Job title"), "job_title"), (_field("Current position"), "job_title"),
    (_field("Position"), "job_title"), (_field("Title"), "job_title"), (_field("School name"), "school"), (_field("Institution"), "school"),
    (_field("University"), "school"), (_field("Degree"), "degree"), (_field("Field of study"), "study_field"), (_field("Major"), "study_field"),
    (_field("Notice period", kind="select"), "choice"), (_field("Phone country code", kind="select"), "choice"),
    (_field("Do you need a visa?", kind="radio"), "choice"), (_field("Location", kind="menu"), "choice"), (_field("Country", kind="menu"), "choice"),
    (_field("City", combo=True), "choice"), (_field("Years of experience with SQL", kind="number"), "choice"),
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
    (_field("", kind="select"), form_fill.CHOICE), (_field("", kind="radio"), form_fill.CHOICE), (_field("Volume", kind="range"), form_fill.CHOICE),
    (_field("Gender", kind="radio"), form_fill.PRIVATE), (_field("Gender", kind="menu"), form_fill.PRIVATE), (_field("Age", kind="number"), form_fill.PRIVATE),
    (_field("Position applied"), form_fill.UNKNOWN), (_field("Referee's employer"), form_fill.UNKNOWN), (_field("Referee's name"), form_fill.UNKNOWN),
    (_field("Username"), form_fill.UNKNOWN), (_field("", kind="number"), form_fill.UNKNOWN),
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
    for never in (".click(", "submit(", "requestSubmit", "fetch(", "XMLHttpRequest", "sendBeacon", "eval(", "innerHTML", "cookie", "localStorage"):
        assert never not in form_fill.CHOOSE, never
    assert "el.type === 'submit' || el.closest('[type=submit]')" in form_fill.CHOOSE, "what sends a form is never pressed"
    assert form_fill.CHOOSE.count("press(") == 5, "pressed: a radio button, an entry of a menu, and what opens a menu (an input or another element); nothing else"
    with pytest.raises(AssertionError):
        form_fill.choose_script("submit", 1, "", "https://x.example/")
    assert json.loads(form_fill.choose_script("open", 4, 'a"b', "https://x.example/").rsplit("})(", 1)[1][:-1].join("[]")) == ["open", 4, 'a"b', "https://x.example/"]
    assert form_fill.choose_answer("nonsense") == {"ok": False, "moved": False, "options": []}
    assert form_fill.choose_answer('{"options": ["  A  b ", 5]}')["options"] == ["A b", "5"]
    for code in (form_fill.READ, form_fill.FILL):
        for never in (".click(", "submit(", "requestSubmit", "fetch(", "XMLHttpRequest", "sendBeacon", "eval(", "innerHTML", "cookie", "localStorage"):
            assert never not in code, never
    read = form_fill.READ.replace("String(el.value || '').trim() !== ''", "").replace("(el.getAttribute('aria-label') || el.value)", "")
    assert "el.value" not in read, "what you typed is only ever tested for being empty (a radio button's value is the page's own name for it)"


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
    ("hi", "help"), ("what can you do?", "help"), ("how does this work", "help"), ("thanks", "unknown"), ("", "unknown"),
    ("why did this score 62?", "question"), ("how many applications are waiting", "question"), ("is this job still open?", "question"),
    ("tell me about this company", "question"), ("what does the limit mean?", "question")])
def test_a_request_is_understood_by_its_words(text, what):
    assert assistant.intent(text) == what


def test_requests_are_checked_before_anything_is_done(isolate):
    api = ui_api.Api()
    assert api.assistant_ask("   ") == {"ok": False, "action": "none", "msg": assistant.EMPTY}
    assert api.assistant_ask("x" * 301)["msg"] == assistant.TOO_LONG and api.assistant_ask(None)["ok"] is False
    assert api.assistant_ask("my details")["action"] == "details"
    assert api.assistant_ask("hello")["say"] == assistant.HELP and api.assistant_ask("sing")["say"].startswith("I did not understand")
    assert "lists, menus and yes/no" in assistant.HELP
    refused = api.assistant_ask("fill the form in chrome")
    assert refused["ok"] is False and refused["action"] == "details" and "My details" in refused["msg"], "nothing to fill in with yet"


# ── filling in, end to end (Chrome replaced by a real browser engine on a local page) ──
def _in_page(*scripts):
    done = subprocess.run([sys.executable, str(FIXTURES / "run_in_page.py"), str(FIXTURES / "forms" / "plain.html")],
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
                            "cover_letter", "cv", "password", "dob", "company_name", "zip", "github", "visa"}, "hidden fields and tick boxes are not listed"
    assert by_name["visa"]["type"] == "radio" and by_name["visa"]["options"] == ["Yes", "No"], "the radio buttons of one question are one field"
    assert by_name["city"]["filled"] and not by_name["first_name"]["filled"] and page["boxes"] == 1
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
    for part in ("4 fields", "2 from My details", "2 answers drafted from your CV", "Junior Analyst at Northwind", "1 of them needs", "2 fields are left",
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
    _browser(monkeypatch, [_field("Email", n=1), _field("Why Northwind?", kind="textarea", n=2), _field("Country", kind="select", n=3, options=["Choose", "Czechia"])],
             done={"done": [1], "skipped": [3]})
    out = ui_api.Api().assistant_fill("nw1")
    assert out["ok"] and [f["label"] for f in out["filled"]] == ["Email"]
    left = {i["label"]: i["why"] for i in out["left"]}
    assert "limit is used up until 14:00" in left["Why Northwind?"] and "did not take it" in left["Country"]
    assert "form_answers" not in store.find(store.load_jobs(), "nw1")


def test_the_job_list_for_the_assistant_holds_open_jobs_only(isolate):
    store.save_jobs([_job(), _job(id="r", status="rejected", company="Closed"), _job(id="w", status="waiting", company="Waiting")])
    assert [j["id"] for j in ui_api.Api().assistant_jobs()] == ["nw1", "w"] and ui_api.Api().assistant_jobs()[0]["label"] == "Northwind · Junior Analyst"


# ── the test area: the whole request, on forms served on this machine, in a real browser engine ──
AREA = {"details": {**MINE, "street": "Long Street 5", "notice_period": "1 month",
                    "experience": [{"employer": "Old Mill", "title": "Intern", "start": "2020", "end": "2021", "current": False},
                                   {"employer": "Northwind", "title": "Junior analyst", "start": "03/2023", "end": "", "current": True}],
                    "education": [{"school": "Masaryk University", "degree": "Master", "field": "Applied informatics", "start": "2021", "end": "2023"}],
                    "salary_amount": 60000, "salary_currency": "CZK", "salary_period": "month"},
        "jobs": [{"id": "bp", "title": "Backend Developer", "company": "Brightpath", "status": "letter_ready", "source": "linkedin",
                  "url": "https://www.linkedin.com/jobs/view/1", "description": "FastAPI services."},
                 {"id": "ql", "title": "Data Analyst", "company": "Quillon", "status": "waiting", "url": "", "description": "SQL reports."},
                 {"id": "vt", "title": "Junior Tester", "company": "Vantor", "status": "found", "url": "", "description": ""}],
        "answers": {"Salary expectation (gross, per month)": ["I expect about [your figure] gross per month.", "Your salary figure"]},
        "choices": {"Are you legally authorized to work in the country of this role?": "Yes", "Highest level of education": "Master's degree",
                    "Do you have the right to work in the Czech Republic?": "Yes", "Years of experience with SQL": "2", "Shoe size": "47"}}


def _area(page, **more):
    done = subprocess.run([sys.executable, str(FIXTURES / "fill_in_browser.py"), page], input=json.dumps({**AREA, **more}),
                          capture_output=True, text=True, timeout=180, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    if done.returncode != 0:
        pytest.skip(f"the browser engine did not start here: {done.stderr[-200:]}")
    out = json.loads(done.stdout)
    assert out["sent"] is False and out["clicked"] is False, "whatever the form, it is never sent and its button is never pressed"
    out["left"] = {i["label"]: i["why"] for i in out["result"].get("left", [])}
    out["filled"] = {i["label"]: i for i in out["result"].get("filled", [])}
    return out


def test_area_a_form_built_from_components_believes_what_was_written():
    """Pages built with a component library keep each value themselves and undo anything that did not arrive like typing;
    their lists are menus that hold nothing until they are opened."""
    out = _area("components.html")
    result, state = out["result"], out["state"]
    assert result["ok"] and result["job_id"] == "bp" and result["guessed"], "the company is named in the page's title"
    assert {"First Name *", "Last Name *", "Email *", "Phone", "LinkedIn Profile", "What interests you about Brightpath?"} <= set(out["filled"])
    assert out["kept"]["c1"] == "Alex" and out["kept"]["c3"] == "alex@example.com" and out["kept"]["c9"] == state["c9"] != "", \
        "the page's own record holds the values: they will still be there when the form is sent"
    # menus: opened, read, and the entry pressed
    assert out["menus"] == {"c5": "Brno, Czech Republic", "c6": "Czech Republic", "c11": "Yes", "c14": "LinkedIn"}
    assert state["c5"] == "Brno, Czech Republic", "the city is typed into the search box and the entry in your country is taken, not the other Brno"
    assert out["filled"]["How did you hear about us?"]["value"] == "LinkedIn", "known from where the posting was found, without asking Claude"
    assert all(out["filled"][label]["check"] == form_choices.CHECK for label in ("Country", "Location (City)", "How did you hear about us?"))
    assert out["left"]["Favourite colour of our logo"] == form_choices.NOT_SETTLED and "c15" not in out["menus"], "opened to read it, closed without choosing"
    assert out["left"]["Gender"] == form_fill.PRIVATE and "c12" not in out["opened"], "a personal question is not even opened"
    assert sorted(out["chosen"]) == ["Are you legally authorized to work in the country of this role?", "Favourite colour of our logo"]
    assert "website" in out["left"]["Website"]
    assert "60 characters" in out["left"]["Describe a back-end service you built and what you would change today."] and state["c10"] == ""
    assert result["boxes"] == 1 and state["c13"] is False, "the tick box is counted and left alone"
    assert len(out["asked"]) == 2 and state["c1#outline"] == "green"


def test_area_a_long_form_is_filled_in_as_far_as_is_safe():
    out = _area("long.html")
    result, state = out["result"], out["state"]
    assert result["ok"] and result["job_id"] == "ql"
    assert state["a1"] == "Alex Novak" and state["a2"] == state["a3"] == "alex@example.com" and state["a6"] == "Long Street 5"
    assert state["a7"] == "602 00" and state["a8"] == "Brno" and state["a10"] == MINE["github"] and state["a13"] == "Northwind"
    assert state["a9"] == "cz" and "Country" in out["filled"], "Czechia is chosen from a list that calls it Czech Republic"
    assert state["a5"] == "" and "9 characters" in out["left"]["Mobile"], "a number that does not fit even without spaces is left"
    # the rows of jobs and degrees: your current job first, then the earlier one
    assert state["a13"] == "Northwind", "the current employer, asked on its own"
    assert (state["w1"], state["w2"], state["w3"], state["w4"]) == ("Northwind", "Junior analyst", "Old Mill", "Intern"), "each row gets one job, whole"
    assert (state["e1"], state["e2"], state["e3"]) == ("Masaryk University", "Master", "Applied informatics")
    # lists, radio buttons and a number
    assert state["a4"] == "+420", "the country code is read off your phone number"
    assert state["a19"] == "1" and out["filled"]["Notice period"]["value"] == "1 month", "from My details, without asking Claude"
    assert state["a20"] == "Master's degree" and state["a12"] == "2" and state["r1"] is True and state["r2"] is False
    assert state["a21"] == "" and out["left"]["Shoe size"] == form_choices.NOT_SETTLED, "an answer that is not one of the options is not written"
    assert state["r3"] is False and state["r4"] is False and out["left"]["Are you willing to relocate to Mars?"] == form_choices.NOT_SETTLED
    assert state["r5"] is False and state["r6"] is False and out["left"]["Gender"] == form_fill.PRIVATE
    assert "Notice period" not in out["chosen"] and "Phone country code" not in out["chosen"] and "Gender" not in out["chosen"]
    assert all(out["filled"][label]["check"] == form_choices.CHECK and state[key + "#outline"] == "amber"
               for label, key in (("Notice period", "a19"), ("Highest level of education", "a20"), ("Years of experience with SQL", "a12")))
    assert state["a11"] == "" and out["left"]["Earliest start date"] == form_fill.DATE
    assert state["a15"] == "60 000 CZK gross per month" and state["a15#outline"] == "green", "the figure and currency from My details, no draft"
    assert state["a16"] != "" and state["a17"] == "" and "same question" in out["left"]["Why do you want this role?"]
    assert len(out["asked"]) == form_answers.MAX_QUESTIONS and sum(1 for why in out["left"].values() if why == form_fill.TOO_MANY) == 3
    assert state["a40"] == "" and state["a41"] == 0 and state["a42"] == "" and state["a43"] == ""
    assert out["left"]["National ID number"] == form_fill.PRIVATE and out["left"]["Create a password for your candidate account"] == form_fill.PASSWORD


def test_area_a_form_in_a_frame_from_another_site_is_named_not_guessed():
    out = _area("framed.html")
    assert out["result"]["ok"] is False and out["state"] == {} and out["asked"] == []
    assert "inside a frame from localhost" in out["result"]["msg"] and "/plain.html" in out["result"]["msg"]


def test_area_the_plain_form_and_a_chosen_job():
    out = _area("plain.html", job_id="vt", choices={"Yes No": "No"})
    result, state = out["result"], out["state"]
    assert result["ok"] and result["job_id"] == "vt" and not result["guessed"]
    assert state["fn"] == "Alex" and state["country"] == "CZ" and state["zip"] == "602 00" and state["gh"] == MINE["github"]
    assert state["city"] == "Already here" and result["kept"] == 1 and state["token"] == "secret-token"
    assert state["why"].startswith("An answer to: Why do you want to work at Northwind?") and out["asked"] == ["Why do you want to work at Northwind?"]
    assert out["left"]["Resume/CV"] == form_fill.FILE and out["left"]["Password"] == form_fill.PASSWORD and out["left"]["Date of birth"] == form_fill.PRIVATE
    assert state["notice"] == "One month", "the only entry that says the same as My details"
    assert state["terms"] is False and state["pw"] == "" and state["dob"] == "" and state["visa"] is False


def test_area_what_you_rewrite_on_the_page_is_learned_and_the_form_is_watched():
    out = _area("components.html", edit={"c9": "I like that Brightpath publishes its API design notes.", "c3": "other@example.com"})
    learned, (before, after) = out["learned"], out["watch"]
    assert learned["ok"] and learned["learned"] == 1 and learned["remembered"] == 1, "the answer you rewrote; not the email you changed"
    assert "What interests you about Brightpath?" in learned["say"]
    assert before["ok"] and after["ok"] and before["url"] == after["url"] and before["sign"] == after["sign"], "the same page: the same fields"
    assert before["empty"] > after["empty"] > 0, "fewer empty fields after filling, some still left for you"


# ── choosing ────────────────────────────────────────────────────────────────
def test_an_option_is_matched_only_when_one_says_the_same():
    assert form_choices.match_option(["Immediately", "1 month", "2 months"], "1 month") == "1 month"
    assert form_choices.match_option(["One month", "3 months"], "1 month") == "One month", "a number in words is the same number"
    assert form_choices.match_option(["Immediately", "1 Month notice", "3 months"], "1 month") == "1 Month notice"
    assert form_choices.match_option(["1 month", "1 month or more"], "1 month") == "1 month", "the exact one wins"
    assert form_choices.match_option(["Less than 1 month", "More than 1 month"], "1 month") == "", "two say it: you choose"
    assert form_choices.match_option(["Yes", "No"], "") == "" and form_choices.match_option([], "x") == ""


def test_what_your_details_and_the_job_settle_needs_no_claude():
    pick = lambda **c: form_choices.settle({"kind": "select", "label": "", "options": [], "what": "", "value": "", **c}, MINE, _job(source="linkedin/guest"))   # noqa: E731
    assert pick(what="country", options=["Germany", "Czech Republic"]) == "Czech Republic"
    assert pick(what="city", options=["Brno, Slovakia", "Brno, Czech Republic", "Bristol"]) == "Brno, Czech Republic"
    assert pick(what="city", options=["Brno", "Bratislava"]) == "Brno" and pick(what="city", options=["Bratislava"]) == ""
    assert pick(what="phone", options=["+4 Other", "+42 Old", "+420 Czechia", "+49 Germany"]) == "+420 Czechia"
    assert pick(what="notice_period", value="2 months", options=["1 month", "2 months"]) == "2 months"
    assert pick(label="How did you hear about us?", options=["Job board", "LinkedIn", "Friend"]) == "LinkedIn"
    assert pick(label="How did you hear about us?", options=["Friend", "Other"]) == "" and pick(label="Shoe size", options=["40"]) == ""
    assert form_choices.settle({"kind": "number", "label": "Years", "options": [], "what": "", "value": "3"}, MINE, None) == ""


def test_claude_may_only_pick_an_option_that_exists_and_may_leave_it_open(monkeypatch):
    seen = {}

    def ask(prompt, **kw):
        seen.update(prompt=prompt, system=kw.get("system"))
        return {"choices": [{"n": 1, "answer": "yes"}, {"n": 2, "answer": "Maybe"}, {"n": 3, "answer": None}, {"n": 4, "answer": "3"},
                            {"n": 5, "answer": "about three"}, {"n": 9, "answer": "Yes"}, "junk"]}
    monkeypatch.setattr(llm, "ask_json", ask)
    choices = [{"n": 1, "kind": "radio", "label": "Right to work?", "options": ["Yes", "No"]}, {"n": 2, "kind": "select", "label": "Relocate?", "options": ["Yes", "No"]},
               {"n": 3, "kind": "menu", "label": "Level", "options": ["A", "B"]}, {"n": 4, "kind": "number", "label": "Years of SQL", "options": []},
               {"n": 5, "kind": "number", "label": "Years of Excel", "options": []}, {"n": 6, "kind": "menu", "label": "Never opened", "options": []}]
    assert form_choices.decide(choices, CV, MINE, _job(source="linkedin")) == {1: "Yes", 4: "3"}
    assert "1. Right to work?\n   options: Yes | No" in seen["prompt"] and "4. Years of SQL\n   (a number)" in seen["prompt"] and "Never opened" not in seen["prompt"]
    assert "Found the posting on: linkedin" in seen["prompt"] and "Lives in: Czechia" in seen["prompt"] and "never guess" in seen["system"]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("nothing to ask"))
    assert form_choices.decide([{"n": 6, "kind": "menu", "label": "x", "options": []}], CV, MINE, None) == {}


def test_choices_are_planned_apart_from_text_fields():
    todo = form_fill.plan([_field("Notice period", kind="select", n=1, options=["", "1 month"]), _field("Country", kind="menu", n=2),
                           _field("City", n=3, combo=True), _field("Years of SQL", kind="number", n=4), _field("Gender", kind="radio", n=5),
                           _field("Current employer", n=6), _field("What is your current notice period, in weeks?", n=7),
                           _field("Visa?", kind="radio", n=8, filled=True)],
                          {**MINE, "notice_period": "1 month"}, has_job=True)
    assert [(c["n"], c["kind"], c["typed"], c["what"], c["value"]) for c in todo["choose"]] == [
        (1, "select", False, "notice_period", "1 month"), (2, "menu", False, "country", "Czechia"), (3, "menu", True, "city", "Brno"), (4, "number", False, "", "")]
    assert todo["left"] == [{"label": "Gender", "why": form_fill.PRIVATE}, {"label": "Current employer", "why": form_fill.NO_DETAIL.format(what="jobs")}]
    assert todo["fill"] == [{"n": 7, "label": "What is your current notice period, in weeks?", "value": "1 month", "kind": "detail"}]
    empty = form_fill.plan([_field("What is your current notice period, in weeks?", n=7)], MINE, has_job=True)
    assert empty["ask"] == [{"n": 7, "label": "What is your current notice period, in weeks?", "most": 0}], "not in My details: drafted like any open question"


def test_choosing_goes_through_the_page_step_by_step(isolate, monkeypatch):
    """Without a browser: which scripts are sent, in which order, and what happens when the page refuses."""
    store.save_jobs([_job()])
    details.save(MINE)
    monkeypatch.setattr(chrome, "pause", lambda seconds: None)
    monkeypatch.setattr(chrome, "active_tab", lambda: {"url": "https://careers.northwind.example/jobs/42", "title": "Junior Analyst - Northwind"})
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: {"choices": [{"n": 2, "answer": "No"}, {"n": 4, "answer": "Blue"}]})
    fields = [_field("Country", kind="menu", n=1), _field("Do you need sponsorship?", kind="radio", n=2, options=["Yes", "No"]),
              _field("Team", kind="menu", n=3), _field("Colour", kind="menu", n=4)]
    steps = []

    def run(script):
        if script == form_fill.READ:
            return json.dumps({"url": "https://careers.northwind.example/jobs/42", "title": "t", "fields": fields, "frames": [], "boxes": 0})
        action, n, arg, _url = json.loads("[" + script.rsplit("})(", 1)[1][:-1] + "]")
        steps.append((action, n, arg))
        if action == "options":
            return json.dumps({"options": {1: ["Germany", "Czech Republic"], 3: [], 4: ["Blue", "Green"]}[n]})
        return json.dumps({"ok": not (action == "pick" and n == 4)})
    monkeypatch.setattr(chrome, "run", run)
    out = ui_api.Api().assistant_fill("nw1")
    assert out["ok"] and [(f["label"], f["value"], f["check"]) for f in out["filled"]] == [
        ("Country", "Czech Republic", form_choices.CHECK), ("Do you need sponsorship?", "No", form_choices.CHECK)]
    left = {i["label"]: i["why"] for i in out["left"]}
    assert left == {"Team": form_choices.NO_MENU, "Colour": "The page did not take the choice. Choose it yourself."}
    assert steps[:3] == [("open", 1, ""), ("options", 1, ""), ("close", 1, False)], "every menu is opened, read and closed before anything is chosen"
    assert ("pick", 1, 1) in steps and ("radio", 2, 1) in steps and steps[-1] == ("close", 4, False), "a menu the page did not let go of is closed again"
    assert "2 choices made for you" in out["say"] and "2 of them need" in out["say"]


def test_a_country_is_found_in_a_list_however_it_is_spelt():
    assert form_fill.country_option(["Choose", "Germany", "Czech Republic"], "Czechia") == "Czech Republic"
    assert form_fill.country_option(["czechia"], "Czechia") == "czechia" and form_fill.country_option(["Chad", ""], "Czechia") == ""
    assert form_fill.country_option(["Atlantis"], "Atlantis") == "Atlantis", "a country the app does not know is matched by its name"
    todo = form_fill.plan([_field("Country", kind="select", options=["Select", "Germany"])], MINE)
    assert todo["fill"] == [] and todo["left"] == [{"label": "Country", "why": form_fill.NO_COUNTRY.format(country="Czechia")}]
    short = form_fill.plan([_field("Mobile", kind="tel", most=13)], MINE)
    assert short["fill"][0]["value"] == "+420123456789", "a short field gets the same number without its spaces"


# ── your own wording, remembered ────────────────────────────────────────────
def test_only_your_own_wording_is_remembered_and_only_where_it_fits(isolate):
    assert answer_memory.key("Why do you want to work at Northwind?", "Northwind") == answer_memory.key("why do you want to work at  QUILLON ?!", "Quillon")
    assert answer_memory.recall("When can you start?") is None and answer_memory.count() == 0
    assert answer_memory.remember("When can you start?", "  Within two weeks of an offer. ", "Northwind")
    assert answer_memory.recall("when can you start", "Quillon")["answer"] == "Within two weeks of an offer."
    assert answer_memory.path() in vault.data_files()
    for question, answer in (("When?", ""), ("Notice?", "It is [your notice period]."), ("?", "x"), ("Long?", "y" * 3001)):
        assert answer_memory.remember(question, answer) is False, (question, answer[:20])
    assert answer_memory.remember("Why do you want to work at Northwind?", "Because Northwind builds reporting tools I use.", "Northwind")
    assert answer_memory.recall("Why do you want to work at Northwind?", "Northwind")["answer"].startswith("Because Northwind")
    assert answer_memory.recall("Why do you want to work at Quillon?", "Quillon") is None, "an answer that names another company is not offered"
    assert answer_memory.remember("Why do you want to work at Northwind?", "I like building reports people use.", "Northwind")
    assert answer_memory.recall("Why do you want to work at Quillon?", "Quillon")["answer"] == "I like building reports people use."
    assert answer_memory.remember("Do you need sponsorship?", "No")
    assert answer_memory.recall("Do you need sponsorship?", options=["Yes", "no"])["answer"] == "no"
    assert answer_memory.recall("Do you need sponsorship?", options=["Ja", "Nein"]) is None, "only when it is one of this form's options"
    assert answer_memory.count() == 3 and answer_memory.forget_all() == 3 and answer_memory.count() == 0
    for i in range(answer_memory.MAX_ENTRIES + 5):
        answer_memory.remember(f"Question number {i} in words", "An answer.")
    assert answer_memory.count() == answer_memory.MAX_ENTRIES and answer_memory.recall("Question number 0 in words") is None
    answer_memory.path().write_text("{ broken")
    assert answer_memory.count() == 0 and answer_memory.recall("anything at all") is None
    assert answer_memory.changed("a  b", "a b") is False and answer_memory.changed("a", "b")


def test_an_answer_you_rewrote_is_used_at_the_next_company_without_claude(isolate, monkeypatch):
    store.save_jobs([_job(form_answers={"made": "1 Oct", "items": [{"question": "When can you start?", "answer": "I can start on [date].", "check": "x"},
                                                                 {"question": "Why Northwind?", "answer": "A draft.", "check": ""}]}),
                     _job(id="q1", company="Quillon", title="Data Analyst", url="")])
    details.save(MINE)
    api = ui_api.Api()
    assert api.save_form_answers("nw1", [{"question": "When can you start?", "answer": "Two weeks after an offer.", "check": ""},
                                         {"question": "Why Northwind?", "answer": "A draft.", "check": ""}])["ok"]
    assert answer_memory.count() == 1, "the one you rewrote, not the draft you left as it was"
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("your own answer is there: nothing to draft"))
    _browser(monkeypatch, [_field("When can you start?", n=1)], url="https://jobs.quillon.example/apply", title="Data Analyst - Quillon")
    out = api.assistant_fill("q1")
    assert out["filled"] == [{"label": "When can you start?", "kind": "answer", "check": answer_memory.CHECK, "value": "Two weeks after an offer."}]
    assert out["can_learn"] and out["is_lead"] and not out["wants_file"] and not out["has_files"]


def test_what_you_change_on_the_page_is_learned_from_the_assistants_own_fields_only(isolate, monkeypatch):
    store.save_jobs([_job()])
    details.save(MINE)
    api = ui_api.Api()
    assert api.assistant_learn()["ok"] is False, "nothing was filled in yet"
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: {"answers": [{"n": 1, "answer": "A first draft.", "needs_you": ""}]})
    url = "https://careers.northwind.example/jobs/42"
    monkeypatch.setattr(chrome, "active_tab", lambda: {"url": url, "title": "Junior Analyst - Northwind"})
    asked_for = []

    def run(script):
        if script == form_fill.READ:
            return json.dumps({"url": url, "title": "t", "frames": [], "boxes": 0, "fields": [_field("Email", n=1), _field("Why Northwind?", kind="textarea", n=2)]})
        tail = json.loads("[" + script.rsplit("})(", 1)[1][:-1] + "]")
        if isinstance(tail[0], list) and tail[0] and isinstance(tail[0][0], dict):
            return json.dumps({"done": [i["n"] for i in tail[0]], "skipped": []})
        asked_for.append(tail[0])
        return json.dumps({"values": {"2": "Because your reports are built in SQL.", "1": "someone@else.example"}})
    monkeypatch.setattr(chrome, "run", run)
    assert api.assistant_fill("nw1")["can_learn"]
    out = api.assistant_learn()
    assert asked_for == [[2]], "only the answer the assistant wrote is read back, never your email or anything else"
    assert out["ok"] and out["learned"] == 1 and "Why Northwind?" in out["say"]
    assert store.find(store.load_jobs(), "nw1")["form_answers"]["items"][0]["answer"] == "Because your reports are built in SQL."
    assert answer_memory.recall("Why Northwind?", "Northwind")["answer"] == "Because your reports are built in SQL."
    assert api.assistant_learn()["learned"] == 0, "the same text twice is nothing new"
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps({"moved": True}))
    assert "not in front any more" in api.assistant_learn()["msg"]
    assert api.assistant_memory() == {"count": 1} and "1 remembered" in api.assistant_forget()["say"] and api.assistant_memory() == {"count": 0}


# ── the small helpers around a fill ─────────────────────────────────────────
def test_a_framed_form_is_opened_in_its_own_tab_only_at_a_web_address(isolate, monkeypatch):
    opened = []
    monkeypatch.setattr(chrome, "open_tab", lambda url: opened.append(url))
    api = ui_api.Api()
    for bad in ("", "javascript:alert(1)", "file:///etc/passwd", "chrome://settings", "https://", "https://x.example/" + "a" * 2000):
        assert api.assistant_open_form(bad)["ok"] is False
    assert "Russian services" in api.assistant_open_form("https://forms.example.ru/a")["msg"] and opened == []
    assert api.assistant_open_form("https://boards.example.net/embed?id=7")["ok"] and opened == ["https://boards.example.net/embed?id=7"]
    monkeypatch.setattr(chrome, "open_tab", lambda url: (_ for _ in ()).throw(chrome.ChromeError(chrome.NOT_RUNNING)))
    assert api.assistant_open_form("https://boards.example.net/a")["msg"] == chrome.NOT_RUNNING
    details.save(MINE)
    _browser(monkeypatch, [], frames=["https://boards.frames.example/embed/job?id=7"])
    assert api.assistant_fill()["frame"] == "https://boards.frames.example/embed/job?id=7"


def test_opening_a_tab_asks_chrome_with_the_address_as_an_argument(monkeypatch):
    calls = _chrome(monkeypatch, _Done(""))
    chrome.open_tab("https://boards.example.net/a?b=\"c\"")
    command = calls[0][0]
    assert command[-1] == 'https://boards.example.net/a?b="c"' and any("make new tab" in part for part in command) and not any("example" in part for part in command[:-1])


def test_the_cv_and_letter_are_shown_in_finder_pdf_first(isolate, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "TAILORED_CV_DIR", tmp_path / "cvs")
    for folder in (config.TAILORED_CV_DIR, config.LETTERS_DIR):
        folder.mkdir(exist_ok=True)
    (config.TAILORED_CV_DIR / "cv_nw.docx").write_bytes(b"x")
    (config.TAILORED_CV_DIR / "cv_nw.pdf").write_bytes(b"x")
    (config.LETTERS_DIR / "letter_nw.docx").write_bytes(b"x")
    store.save_jobs([_job(tailored_cv_file="cv_nw.docx", cover_letter_file="letter_nw.docx"), _job(id="bare")])
    shown = []
    monkeypatch.setattr(ui_api.Api, "_reveal", lambda self, path: shown.append(path.name))
    api = ui_api.Api()
    out = api.assistant_files("nw1")
    assert out["ok"] and shown == ["cv_nw.pdf", "letter_nw.docx"] and "Drag them" in out["say"]
    assert api.assistant_files("bare")["ok"] is False and api.assistant_files("gone")["ok"] is False and len(shown) == 2


def test_watching_the_form_is_quiet_about_trouble(isolate, monkeypatch):
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps({"url": "https://x.example/step2", "fields": 4, "first": "a|b", "empty": 3}))
    assert ui_api.Api().assistant_watch() == {"ok": True, "url": "https://x.example/step2", "sign": "4:a|b", "empty": 3}
    monkeypatch.setattr(chrome, "run", lambda script: (_ for _ in ()).throw(chrome.ChromeError(chrome.NOT_RUNNING)))
    assert ui_api.Api().assistant_watch()["ok"] is False
    assert form_fill.watch_answer("junk") == {"url": "", "sign": "", "empty": 0} and form_fill.values_answer("junk") == {}
    for code in (form_fill.WATCH, form_fill.VALUES):
        for never in (".click(", "submit(", "dispatchEvent", "fetch(", "cookie", "localStorage", "innerHTML"):
            assert never not in code, never
    assert "el.value" not in form_fill.WATCH.replace("String(el.value || '').trim() === ''", ""), "watching only counts empty fields"


# ── free questions ──────────────────────────────────────────────────────────
def test_a_free_question_is_answered_from_what_the_app_knows(isolate, monkeypatch):
    store.save_jobs([_job(match_score=62, match_tier="strong", match_reason="Solid SQL, but no Power BI.")])
    seen = {}

    def ask(prompt, **kw):
        seen.update(prompt=prompt, **kw)
        return "It scored 62 because your SQL is solid — but the CV shows no Power BI."
    monkeypatch.setattr(llm, "ask", ask)
    api = ui_api.Api()
    out = api.assistant_ask("why did this score 62?", "nw1")
    assert out == {"ok": True, "action": "answer", "say": "It scored 62 because your SQL is solid – but the CV shows no Power BI."}
    assert "Score: 62" in seen["prompt"] and "Solid SQL, but no Power BI." in seen["prompt"] and "Northwind" in seen["prompt"]
    assert "The question: why did this score 62?" in seen["prompt"] and "Leads in New Jobs: 1" in seen["prompt"]
    assert seen["tag"] == "assistant" and "only the facts given" in seen["system"]
    api.assistant_ask("how many applications are waiting?")
    assert "No job is chosen" in seen["prompt"]
    monkeypatch.setattr(llm, "ask", lambda *a, **k: (_ for _ in ()).throw(llm.LimitReached("Claude's limit is used up until 14:00.")))
    assert "limit is used up until 14:00" in api.assistant_ask("why did this score 62?", "nw1")["msg"]
    monkeypatch.setattr(llm, "ask", lambda *a, **k: "   ")
    assert api.assistant_ask("is this job still open?", "nw1")["ok"] is False
    monkeypatch.setattr(llm, "ask", lambda *a, **k: pytest.fail("help costs nothing"))
    assert api.assistant_ask("help")["action"] == "help" and api.assistant_ask("my details")["action"] == "details"


# ── several jobs, several degrees, a salary with its currency, files of your own ──
JOBS = [{"employer": "Old Mill", "title": "Intern", "start": "2020", "end": "2021", "current": False},
        {"employer": "Northwind", "title": "Junior analyst", "start": "03/2023", "end": "", "current": True},
        {"employer": "Evening School", "title": "Tutor", "start": "2022", "end": "", "current": True}]
SCHOOLS = [{"school": "Masaryk University", "degree": "Master", "field": "Applied informatics", "start": "2021", "end": "2023"},
           {"school": "Masaryk University", "degree": "Bachelor", "field": "Informatics", "start": "2018", "end": "2021"}]
FULL = {**MINE, "experience": JOBS, "education": SCHOOLS, "salary_amount": 60000, "salary_currency": "CZK", "salary_period": "month"}


def test_jobs_degrees_salary_and_files_are_checked_row_by_row(tmp_path):
    clean, problem = details.check({**FULL, "experience": JOBS + [{"employer": "", "title": "", "start": "", "end": ""}]})
    assert problem == {} and clean["experience"] == JOBS and clean["education"] == SCHOOLS, "an empty line is not a job"
    for change, where, word in (
            ({"experience": [{"employer": "Acme", "title": ""}]}, "experience.0.title", "missing"),
            ({"experience": [{"employer": "", "title": "Dev"}]}, "experience.0.employer", "missing"),
            ({"experience": [JOBS[0], {"employer": "A", "title": "B", "start": "spring 23"}]}, "experience.1.start", "2023 or 03/2023"),
            ({"experience": [{"employer": "A", "title": "B", "start": "13/2023"}]}, "experience.0.start", "2023 or 03/2023"),
            ({"experience": [{"employer": "A", "title": "B", "start": "2023", "end": "2021"}]}, "experience.0.end", "earlier"),
            ({"experience": [{"employer": "A", "title": "B", "end": "2024", "current": True}]}, "experience.0.end", "no end date"),
            ({"experience": [{"employer": "x" * 101, "title": "B"}]}, "experience.0.employer", "the most is 100"),
            ({"experience": [{"employer": "A", "title": "B"}] * 16}, "experience", "the most is 15"),
            ({"experience": "three"}, "experience", "list"), ({"experience": ["x"]}, "experience.0", "row"),
            ({"education": [{"school": "", "degree": "Master"}]}, "education.0.school", "missing"),
            ({"salary_amount": "a lot"}, "salary", "whole number"), ({"salary_amount": -5}, "salary", "between"),
            ({"salary_currency": "RUB"}, "salary", "not a currency"), ({"salary_period": "week"}, "salary", "per month or per year"),
            ({"files": [{"label": "Diploma", "path": str(tmp_path / "gone.pdf")}]}, "files.0", "not there any more"),
            ({"files": [{"label": "Diploma", "path": "relative.pdf"}]}, "files.0", "not there any more"),
            ({"files": "one"}, "files", "list")):
        clean, problem = details.check({**FULL, **change})
        assert clean == {} and problem["field"] == where and word in problem["msg"], (change, problem)
    paper = tmp_path / "AWS certificate.pdf"
    paper.write_bytes(b"x")
    clean, problem = details.check({**FULL, "files": [{"label": "", "path": str(paper)}, {"label": "", "path": ""}], "salary_amount": "65 000", "salary_currency": "eur"})
    assert problem == {} and clean["files"] == [{"label": "AWS certificate", "path": str(paper)}] and clean["salary_amount"] == 65000 and clean["salary_currency"] == "EUR"
    assert "twice" in details.check({**FULL, "files": [{"path": str(paper)}, {"path": str(paper)}]})[1]["msg"]


def test_what_a_form_is_given_from_the_lists():
    assert [j["employer"] for j in details.jobs(FULL)] == ["Northwind", "Evening School", "Old Mill"], "the current jobs first"
    assert details.salary_text(FULL) == "60 000 CZK gross per month" and details.salary_text(MINE) == ""
    assert details.salary_text({**FULL, "salary_amount": 52000, "salary_currency": "EUR", "salary_period": "year"}) == "52 000 EUR gross per year"
    assert details.facts(FULL) == ["- Job: Junior analyst at Northwind (03/2023 to now) - a current job", "- Job: Tutor at Evening School (2022 to now) - a current job",
                                   "- Job: Intern at Old Mill (2020 to 2021)", "- Education: Master, Applied informatics at Masaryk University (2021 to 2023)",
                                   "- Education: Bachelor, Informatics at Masaryk University (2018 to 2021)", "- Salary expectation: 60 000 CZK gross per month"]
    assert details.facts(MINE) == []
    fields = [_field("Company", n=1), _field("Job title", n=2), _field("Company", n=3), _field("Job title", n=4), _field("Company", n=5), _field("Title", n=6),
              _field("Company", n=7), _field("School", n=8), _field("Degree", n=9), _field("Field of study", n=10), _field("School", n=11), _field("Degree", n=12),
              _field("School", n=13), _field("Expected salary", n=14), _field("Current employer", n=15, filled=True)]
    todo = form_fill.plan(fields, FULL)
    assert [(f["n"], f["value"]) for f in todo["fill"]] == [
        (1, "Northwind"), (2, "Junior analyst"), (3, "Evening School"), (4, "Tutor"), (5, "Old Mill"), (6, "Intern"),
        (8, "Masaryk University"), (9, "Master"), (10, "Applied informatics"), (11, "Masaryk University"), (12, "Bachelor"), (14, "60 000 CZK gross per month")]
    assert todo["left"] == [{"label": "Company", "why": form_fill.MORE_ROWS.format(have="3 jobs")}, {"label": "School", "why": form_fill.MORE_ROWS.format(have="2 degrees")}]
    ragged = form_fill.plan([_field("Current employer", n=1), _field("Company", n=2), _field("Job title", n=3), _field("Job title", n=4), _field("Company", n=5),
                             _field("Current job title", n=6)], FULL)
    assert [(f["n"], f["value"]) for f in ragged["fill"]] == [(1, "Northwind"), (2, "Northwind"), (3, "Junior analyst"), (4, "Tutor"), (5, "Evening School"),
                                                              (6, "Junior analyst")], "a row ends where one of its fields comes round again"
    assert form_fill.plan([_field("Company", n=1)], MINE)["left"] == [{"label": "Company", "why": form_fill.NO_DETAIL.format(what="jobs")}]
    assert "Job: Junior analyst at Northwind" in form_choices.facts_block(CV, FULL, None) and "Education: Master" in form_choices.facts_block(CV, FULL, None)


def test_jobs_and_degrees_are_copied_from_the_cv_and_never_made_up(isolate, monkeypatch):
    cv = CV + "\nExperience\nJunior analyst, Northwind, 03/2023 - present\nIntern, Old Mill, 2020 - 2021\nEducation\nMasaryk University, Master, Applied informatics, 2021 - 2023"
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: cv)
    seen = {}

    def ask(prompt, **kw):
        seen.update(prompt=prompt, **kw)
        return {"experience": [{"employer": "Northwind", "title": "Junior analyst", "start": "03/2023", "end": "present", "current": True},
                               {"employer": "Old Mill", "title": "Intern", "start": "2020", "end": "2021", "current": False},
                               {"employer": "Globex", "title": "Director", "start": "2019", "end": "2020"},
                               {"employer": "Northwind", "title": "", "start": "", "end": ""}, "junk"],
                "education": [{"school": "Masaryk University", "degree": "Master", "field": "Applied informatics", "start": "2021", "end": "2023"},
                              {"school": "Harvard", "degree": "PhD", "field": "", "start": "", "end": ""}]}
    monkeypatch.setattr(llm, "ask_json", ask)
    out = ui_api.Api().assistant_cv_lists()
    assert out["ok"] and [j["employer"] for j in out["experience"]] == ["Northwind", "Old Mill"], "an employer that is not in the CV is dropped, and so is a row with no title"
    assert out["experience"][0] == {"employer": "Northwind", "title": "Junior analyst", "start": "03/2023", "end": "", "current": True}
    assert [s["school"] for s in out["education"]] == ["Masaryk University"] and "2 jobs and 1 degrees" in out["say"]
    assert "never add, guess" in seen["system"] and seen["tag"] == "assistant" and not details.path().exists(), "offered, not saved"
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"experience": [], "education": []})
    assert "found no jobs or degrees" in ui_api.Api().assistant_cv_lists()["msg"]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: (_ for _ in ()).throw(llm.LimitReached("Claude's limit is used up until 14:00.")))
    assert "limit is used up" in ui_api.Api().assistant_cv_lists()["msg"]
    monkeypatch.setattr(ui_api.Api, "_cv_text", lambda self: "")
    assert "could not be read" in ui_api.Api().assistant_cv_lists()["msg"]


def test_your_own_files_are_shown_with_the_cv_or_alone(isolate, monkeypatch, tmp_path):
    paper = tmp_path / "diploma.pdf"
    paper.write_bytes(b"x")
    store.save_jobs([_job()])
    shown = []
    monkeypatch.setattr(ui_api.Api, "_reveal", lambda self, path: shown.append(os.path.basename(str(path))))
    api = ui_api.Api()
    assert api.assistant_files("")["ok"] is False and "no file of your own" in api.assistant_files("nw1")["msg"]
    assert details.save({**MINE, "files": [{"label": "Diploma", "path": str(paper)}]})["ok"]
    out = api.assistant_files("")
    assert out["ok"] and shown == ["diploma.pdf"] and "Diploma (diploma.pdf)" in out["say"]
    assert api.my_details()["files"] == [{"label": "Diploma", "path": str(paper), "name": "diploma.pdf"}]
    assert api.my_details()["currencies"][:3] == ["CZK", "EUR", "USD"] and api.my_details()["periods"] == ["month", "year"]
    paper.unlink()
    assert details.load()["files"] == [] or details.load() == details.empty(), "a file that is gone does not break the page"


# ── answers of your own ─────────────────────────────────────────────────────
def test_answers_of_your_own_are_kept_changed_and_removed(isolate):
    api = ui_api.Api()
    first = api.my_answers()
    assert first["items"] == [] and "When can you start?" in first["starters"]
    for question, answer, where, word in (("", "x", "question", "in words"), ("???", "x", "question", "in words"), ("q" * 301 + " word", "x", "question", "the most is 300"),
                                          ("When can you start?", "  ", "answer", "empty"), ("When can you start?", "On [date].", "answer", "square brackets"),
                                          ("When can you start?", "y" * 3001, "answer", "the most is 3000")):
        out = api.save_my_answer(question, answer)
        assert out["ok"] is False and out["field"] == where and word in out["msg"], (question, out)
    assert api.save_my_answer("When can you start?", "Two weeks after an offer.")["ok"]
    assert api.save_my_answer("What are your strengths?", "I finish what I start.")["ok"]
    kept = api.my_answers()
    assert [i["question"] for i in kept["items"]] == ["What are your strengths?", "When can you start?"] and "When can you start?" not in kept["starters"]
    assert api.save_my_answer("When could you start?", "Two weeks after an offer.", "When can you start?")["ok"], "a reworded question replaces the old entry"
    assert [i["question"] for i in api.my_answers()["items"]] == ["When could you start?", "What are your strengths?"]
    assert api.delete_my_answer("What are your strengths?") == {"ok": True} and api.delete_my_answer("never asked") == {"ok": False}
    assert answer_memory.recall("when could you start")["answer"] == "Two weeks after an offer."


def test_a_draft_of_your_own_answer_comes_from_the_cv_and_is_not_kept_until_you_save(isolate, monkeypatch):
    details.save(FULL)
    seen = {}

    def ask(prompt, **kw):
        seen["prompt"] = prompt
        return {"answers": [{"n": 1, "answer": "I work carefully with data in SQL and Python.", "needs_you": ""}]}
    monkeypatch.setattr(llm, "ask_json", ask)
    api = ui_api.Api()
    out = api.draft_my_answer("What are your strengths?")
    assert out["ok"] and out["answer"].startswith("I work carefully") and answer_memory.count() == 0
    assert "Junior analyst at Northwind" in seen["prompt"] and "do not name a company" in seen["prompt"]
    for question in ("Why do you want to work here?", "Why do you want to join our company?", "What attracts you to this role?", "Why us?"):
        refused = api.draft_my_answer(question)
        assert refused["ok"] is False and refused["msg"] == assistant.ABOUT_ONE_COMPANY, question
    assert api.draft_my_answer("?")["field"] == "question"
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: (_ for _ in ()).throw(llm.LimitReached("Claude's limit is used up until 14:00.")))
    assert "limit is used up" in api.draft_my_answer("What are your strengths?")["msg"]
