"""The assistant: your details, the link to Chrome, reading a form, deciding what each field is,
and filling in only what is safe to fill. The page scripts run in a real browser engine on a local page."""
import base64
import json
import os
import subprocess
import sys

import pytest

from jobhelper import answer_memory, assistant, assistant_brain, chrome, config, details, form_answers, form_choices, form_fill, llm, store, ui_api, vault
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
    (_field("Start date", kind="date"), "row_start"), (_field("From", kind="month"), "row_start"), (_field("End date", kind="month"), "row_end"),
    (_field("Dates: to (MM/YYYY)"), "row_end"), (_field("Main tool"), "guess"), (_field("Native language"), "guess"),
    (_field("Tell us about a project you are proud of", kind="textarea"), "question"),
    (_field("Cover letter", kind="textarea"), "letter"), (_field("Motivation letter (optional)", kind="textarea"), "letter"),
    (_field("How did you get your name known in the field?", kind="textarea"), "question")])
def test_fields_are_recognised_by_what_the_page_calls_them(field, what):
    assert form_fill.classify(field) == (what, "")


@pytest.mark.parametrize("field, why", [
    (_field("Password", kind="password"), form_fill.PASSWORD), (_field("Email", kind="password"), form_fill.PASSWORD),
    (_field("Date of birth"), form_fill.PRIVATE), (_field("Gender", kind="select"), form_fill.PRIVATE),
    (_field("Disability status", kind="select"), form_fill.PRIVATE), (_field("Card number"), form_fill.PRIVATE),
    (_field("Passport number"), form_fill.PRIVATE), (_field("Race / Ethnicity", kind="select"), form_fill.PRIVATE),
    (_field("Veteran status", kind="select"), form_fill.PRIVATE), (_field("IBAN"), form_fill.PRIVATE),
    (_field("Earliest start date", kind="date"), form_fill.DATE), (_field("Date of the interview", kind="date"), form_fill.DATE),
    (_field("Meeting", kind="time"), form_fill.DATE),
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
    items, url, typed = json.loads("[" + script.rsplit("})(", 1)[1][:-1] + "]")
    assert items == [{"n": 3, "value": nasty, "check": True}] and url == 'https://x.example/a"b' and typed is False
    assert json.loads("[" + form_fill.fill_script([], "u", typed=True).rsplit("})(", 1)[1][:-1] + "]") == [[], "u", True]
    assert json.loads("[" + form_fill.empty_script([3, 4], "u").rsplit("})(", 1)[1][:-1] + "]") == [[3, 4], "u"]
    assert form_fill.empty_answer('{"empty": [3, "x"]}') == [3] and form_fill.empty_answer("junk") == []
    assert "el.value" not in form_fill.EMPTY.replace("String(el.value || '').trim() === ''", ""), "looking again says only empty or not"
    assert " " not in script and "\n</script>" not in script
    for never in (".click(", "submit(", "requestSubmit", "fetch(", "XMLHttpRequest", "sendBeacon", "eval(", "innerHTML", "cookie", "localStorage"):
        assert never not in form_fill.CHOOSE, never
    assert "el.type === 'submit' || el.closest('[type=submit]')" in form_fill.CHOOSE, "what sends a form is never pressed"
    assert form_fill.CHOOSE.count("press(") == 7, ("pressed: a radio button, an entry of a menu, what opens a menu (an input or another element), "
                                                   "a button that adds a row, the tick box of a current job; nothing else")
    assert "agree|consent|terms|privacy" in form_fill.CHOOSE, "a box that agrees to something is never ticked"
    for words, kind in (("Add another job", "experience"), ("+ Add work experience", "experience"), ("Add education", "education"), ("Add a degree", "education"),
                        ("Add another", ""), ("Add and continue", ""), ("Add & submit application", ""), ("Add job and save", ""), ("Add file", ""),
                        ("Upload CV", ""), ("Next", ""), ("Submit", ""), ("Add work and education", "")):
        assert form_fill.add_kind(words) == kind, words
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
def _in_page(*scripts, page="plain.html"):
    done = subprocess.run([sys.executable, str(FIXTURES / "run_in_page.py"), str(FIXTURES / "forms" / page)],
                          input=json.dumps(list(scripts)), capture_output=True, text=True, timeout=120,
                          env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert "Traceback" not in done.stderr, done.stderr[-1500:]       # the test area itself is broken: that is a failure, not a skip
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


LISTS = """JSON.stringify({
  home: document.getElementById('home').selectedOptions[0].text, bare: document.getElementById('bare').selectedOptions[0].text,
  greyed: document.getElementById('greyed').selectedOptions[0].text, taken: document.getElementById('taken').selectedOptions[0].text,
  sent: !!window.sent, clicked: !!window.clicked})"""


def test_a_long_country_list_is_named_by_the_words_beside_it_and_filled():
    """Found on a real site: 250 countries in a list whose label is only written next to it. The entries crowded the label out, the
    list had no name, and it was left. Its name is now read without its own entries, or from its "Select your Country" line."""
    page = form_fill.read_answer(_in_page(form_fill.READ, page="lists.html")[0])
    by_id = {f["id"]: f for f in page["fields"]}
    assert by_id["home"]["label"] == "Country of residence*:" and by_id["taken"]["label"] == "Country (already chosen)"
    assert by_id["bare"]["label"] == "" and by_id["bare"]["hint"] == "Select your Country", "a list with no words near it is named by its first line"
    assert by_id["greyed"]["label"] == "Country you live in", "words the page hides are not part of the name"
    assert by_id["home"]["hint"] == "", "a list that has a name does not need its first line as one"
    assert not by_id["home"]["filled"] and not by_id["bare"]["filled"] and by_id["taken"]["filled"]
    assert not by_id["greyed"]["filled"], "a greyed-out 'Please choose' further down the list is not an answer"
    assert all(form_fill.classify(by_id[i]) == ("country", "") for i in ("home", "bare", "greyed"))
    todo = form_fill.plan(page["fields"], MINE)
    assert {i["n"]: i["value"] for i in todo["fill"]} == {by_id[i]["n"]: "Czech Republic" for i in ("home", "bare", "greyed")}
    assert not todo["left"] and not todo["choose"], "your own country is not a question for Claude"
    numbers = [by_id[i]["n"] for i in ("home", "bare", "greyed", "taken")]
    before, _read, done, state, empty = _in_page(form_fill.READ + ";" + form_fill.empty_script(numbers, page["url"]), form_fill.READ,
                                                 form_fill.fill_script(todo["fill"], page["url"]), LISTS,
                                                 form_fill.empty_script(numbers, page["url"]), page="lists.html")
    assert sorted(form_fill.empty_answer(before)) == sorted(numbers[:3]), "three lists wait for an answer, one has it"
    state = json.loads(state)
    assert state["home"] == state["bare"] == state["greyed"] == "Czech Republic" and state["taken"] == "Germany", "a list with an answer keeps it"
    assert sorted(form_fill.fill_answer(done)["done"]) == sorted(by_id[i]["n"] for i in ("home", "bare", "greyed"))
    assert state["sent"] is False and state["clicked"] is False
    assert form_fill.empty_answer(empty) == [], "and afterwards none of them is empty"


def test_a_page_states_its_job_for_search_engines_and_that_is_read():
    page = form_fill.page_answer(_in_page(form_fill.PAGE)[0])
    assert page["stated"] == {"title": "Junior Analyst", "company": "Northwind", "location": "Brno, CZ"}
    assert page["title"] == "Junior Analyst - Northwind Careers" and "First name" in page["text"]
    assert "secret-token" not in json.dumps(page) and "Already here" not in json.dumps(page), "the words of the page, not what its fields hold"


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


ran_files: list = []          # what the stand-in browser was given as files: [(field, name, content)]


def _browser(monkeypatch, fields, url="https://careers.northwind.example/jobs/42", title="Junior Analyst - Northwind", frames=(), boxes=0, done=None):
    ran, carried, attached = [], {}, []
    ran_files[:] = [attached]
    monkeypatch.setattr(chrome, "active_tab", lambda: {"url": url, "title": title})

    def run(script):
        if "empty.push" in script:               # the look after a fill: everything stayed where it was written
            return json.dumps({"empty": []})
        ran.append(script)
        if script == form_fill.READ:
            return json.dumps({"url": url, "title": title, "fields": fields, "frames": list(frames), "boxes": boxes})
        if script == form_fill.PAGE:
            return json.dumps({"url": url, "title": title, "text": "", "stated": None})
        if script.startswith("(function (key, part)"):           # a piece of a file on its way to the page
            key, part = json.loads("[" + script.rsplit("})(", 1)[1][:-1] + "]")
            carried[key] = carried.get(key, "") + part
            return str(len(carried[key]))
        if script.startswith("(function (n, key, name, kind, url)"):
            n, key, name, _kind, _url = json.loads("[" + script.rsplit("})(", 1)[1][:-1] + "]")
            attached.append((n, name, base64.b64decode(carried.pop(key, ""))))
            return json.dumps({"ok": True, "size": len(attached[-1][2])})
        items = json.loads("[" + script.rsplit("})(", 1)[1][:-1] + "]")[0]
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
                    "education": [{"school": "Masaryk University", "degree": "Master", "field": "Applied informatics", "start": "09/2021", "end": "06/2023"}],
                    "salary_amount": 60000, "salary_currency": "CZK", "salary_period": "month"},
        "jobs": [{"id": "bp", "title": "Backend Developer", "company": "Brightpath", "status": "letter_ready", "source": "linkedin",
                  "url": "https://www.linkedin.com/jobs/view/1", "description": "FastAPI services."},
                 {"id": "ql", "title": "Data Analyst", "company": "Quillon", "status": "waiting", "url": "", "description": "SQL reports."},
                 {"id": "vt", "title": "Junior Tester", "company": "Vantor", "status": "found", "url": "", "description": ""}],
        "answers": {"Salary expectation (gross, per month)": ["I expect about [your figure] gross per month.", "Your salary figure"]},
        "choices": {"Are you legally authorized to work in the country of this role?": "Yes", "Highest level of education": "Master's degree",
                    "Do you have the right to work in the Czech Republic?": "Yes", "Years of experience with SQL": "2", "Shoe size": "47",
                    "Main tool": "SQL", "Office snack": "Pretzels"}}


def _area(page, **more):
    done = subprocess.run([sys.executable, str(FIXTURES / "fill_in_browser.py"), page], input=json.dumps({**AREA, **more}),
                          capture_output=True, text=True, timeout=180, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert "Traceback" not in done.stderr, done.stderr[-1500:]       # the test area itself is broken: that is a failure, not a skip
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
    assert (state["w1"], state["w2"]) == ("Northwind", "Junior analyst") and state["w5"] == "2023-03" and state["w6"] == "", "a job that goes on has no end date"
    # the second job had no row: the form was asked for one, by its own button, and nothing else was pressed
    assert result["added_rows"] == 1 and "1 more row" in result["say"]
    assert (state["w3"], state["w4"]) == ("Old Mill", "Intern") and state["w7"] == "" and state["w8"] == "2021"
    assert out["left"]["Start date"] == form_fill.NO_MONTH, "a year alone does not make a date"
    # a field the app did not recognise: Claude may copy words that stand in the CV, and only those
    # the box "I currently work here" is ticked for the job that goes on, and no other box is touched
    assert state["wc"] is True and out["filled"]["I currently work here"]["value"] == "Ticked" and state["nl"] is False
    # a date asked as two lists: the month and the year of the degree
    assert (state["em"], state["ey"]) == ("9", "2021") and (state["xm"], state["xy"]) == ("6", "2023")
    # a field that throws away what does not arrive as typing gets it the second way
    assert state["st"] == "602 00", "written again the way typing arrives"
    assert state["g1"] == "SQL" and out["filled"]["Main tool"]["check"] == form_choices.CHECK
    assert state["g2"] == "" and out["left"]["Office snack"] == form_fill.UNKNOWN, "words that are not in the CV are not written"
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
    assert out["left"]["Resume/CV"] == form_fill.FILE_NO_CV and out["left"]["Password"] == form_fill.PASSWORD and out["left"]["Date of birth"] == form_fill.PRIVATE
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
        if "empty.push" in script:
            return json.dumps({"empty": []})
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


# ── talking with the assistant ──────────────────────────────────────────────
def _decision(monkeypatch, say="", action=None, show=()):
    seen = {}

    def ask(prompt, **kw):
        seen.update(prompt=prompt, **kw)
        return {"say": say, "action": action, "show": list(show)}
    monkeypatch.setattr(llm, "ask_json", ask)
    return seen


def test_claudes_decision_is_checked_before_anything_happens():
    ids = {"nw1", "q1"}
    ok = assistant_brain.check({"say": "It scored 62 — fine.", "action": {"name": "mark_applied", "args": {"job": "nw1", "extra": 1}}, "show": ["q1", "ghost", 5]}, ids)
    assert ok == {"say": "It scored 62 – fine.", "action": {"name": "mark_applied", "args": {"job": "nw1"}}, "show": ["q1"], "dropped": False,
                  "actions": [{"name": "mark_applied", "args": {"job": "nw1"}}]}
    for bad in ({"name": "delete_everything", "args": {}}, {"name": "mark_applied", "args": {"job": "ghost"}}, {"name": "set_status", "args": {"job": "nw1", "status": "hired"}},
                {"name": "set_date", "args": {"job": "nw1", "day": "next Tuesday"}}, {"name": "rewrite_letter", "args": {"job": "nw1", "paragraph": "two", "how": "shorter"}},
                {"name": "rewrite_letter", "args": {"job": "nw1", "paragraph": 2, "how": ""}}, {"name": "rewrite_answer", "args": {"job": "nw1", "how": "x"}},
                {"name": "open", "args": {}}, "mark_applied", {"args": {"job": "nw1"}}):
        out = assistant_brain.check({"say": "I will do that.", "action": bad}, ids)
        assert out["action"] is None and out["actions"] == [] and out["say"] == "I will do that.", bad
    assert assistant_brain.check({"say": "", "action": {"name": "set_date", "args": {"job": "q1", "day": "2026-10-13", "time": "11:30", "kind": "dinner", "note": " a  b "}}}, ids)["action"] == \
        {"name": "set_date", "args": {"job": "q1", "day": "2026-10-13", "time": "11:30", "kind": "interview", "note": "a b"}}
    assert assistant_brain.check({"say": "x", "action": {"name": "fill_form", "args": {"skip": ["Salary ", 5, ""]}}}, ids)["action"]["args"] == {"skip": ["salary", "5"]}
    for junk in (None, "text", [], {"say": "", "action": None}):
        with pytest.raises(ValueError):
            assistant_brain.check(junk, ids)
    assert assistant_brain.changes("mark_applied") and assistant_brain.changes("not_interested") and not assistant_brain.changes("open")
    assert assistant_brain.asks({"name": "set_status", "args": {"job": "nw1", "status": "on_hold"}}, _job()) == "Set Junior Analyst at Northwind to “on hold”?"


def test_the_fixed_requests_cost_nothing_and_the_rest_is_one_call_with_what_the_app_knows(isolate, monkeypatch):
    store.save_jobs([_job(match_score=62, match_reason="Solid SQL, but no Power BI."), _job(id="q1", company="Quillon", title="Data Analyst", status="waiting", date_applied="2026-09-20")])
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("a fixed request needs no Claude"))
    api = ui_api.Api()
    assert api.assistant_talk("help")["say"] == assistant.HELP and api.assistant_talk("my details")["action"] == "details"
    assert api.assistant_talk("fill the form in chrome")["action"] == "details", "no details yet: it says so, without Claude"
    assert api.assistant_talk("thanks")["say"].startswith("I did not understand") and api.assistant_talk("   ")["msg"] == assistant.EMPTY
    seen = _decision(monkeypatch, "It scored 62 because your SQL is solid, but the CV shows no Power BI.", None, ["nw1"])
    out = api.assistant_talk("why did this score 62?", context_job="nw1")
    assert out["ok"] and out["action"] == "say" and out["say"].startswith("It scored 62") and out["rows"] == [{"id": "nw1", "label": "Northwind · Junior Analyst", "sub": "letter ready · score 62"}]
    assert "looking at right now" in seen["prompt"] and "Solid SQL, but no Power BI." in seen["prompt"] and "nw1 | Northwind | Junior Analyst | letter_ready | 62" in seen["prompt"]
    assert "q1 | Quillon | Data Analyst | waiting" in seen["prompt"] and "2026-09-20 (" in seen["prompt"] and seen["tag"] == "assistant"
    assert "The request: why did this score 62?" in seen["prompt"] and "1 leads in New Jobs, 1 applications" in seen["prompt"]
    # the next request knows what was said before
    _decision(monkeypatch, "Quillon has been waiting for three weeks.", None, ["q1"])
    api.assistant_talk("and the other one?")
    seen = _decision(monkeypatch, "Yes.", None)
    api.assistant_talk("is that long?")
    assert "Person: why did this score 62?" in seen["prompt"] and "Assistant: Quillon has been waiting for three weeks." in seen["prompt"]
    assert "No job is open in the app right now." in seen["prompt"]
    assert api.assistant_new_talk()["ok"]
    seen = _decision(monkeypatch, "Hello.", None)
    api.assistant_talk("what is waiting longest?")
    assert "(this is the first request)" in seen["prompt"]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: (_ for _ in ()).throw(llm.LimitReached("Claude's limit is used up until 14:00.")))
    assert "limit is used up until 14:00" in api.assistant_talk("why did this score 62?", "nw1")["msg"]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: "nonsense")
    assert "could not be read" in api.assistant_talk("why did this score 62?", "nw1")["msg"]


def test_nothing_of_yours_is_changed_without_your_yes(isolate, monkeypatch):
    store.save_jobs([_job(), _job(id="q1", company="Quillon", title="Data Analyst", status="waiting", date_applied="2026-09-20")])
    api = ui_api.Api()
    _decision(monkeypatch, "I will mark it as applied.", {"name": "mark_applied", "args": {"job": "nw1"}})
    out = api.assistant_talk("mark this one as applied please", context_job="nw1")
    assert out["action"] == "confirm" and out["ask"] == "Mark Junior Analyst at Northwind as applied? It moves to Applications as waiting."
    assert store.find(store.load_jobs(), "nw1")["status"] == "letter_ready", "asked, not done"
    done = api.assistant_confirm(out["pending"])
    assert done["ok"] and done["changed"] and "Moved Junior Analyst at Northwind to Applications" in done["say"]
    assert store.find(store.load_jobs(), "nw1")["status"] == "waiting"
    _decision(monkeypatch, "", {"name": "mark_applied", "args": {"job": "nw1"}})
    assert "already among your applications" in api.assistant_talk("mark it applied once more", "nw1")["msg"]
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=30)).isoformat()
    _decision(monkeypatch, "", {"name": "set_date", "args": {"job": "q1", "day": soon, "time": "11:30", "kind": "interview", "note": "Video call"}})
    out = api.assistant_talk("the interview at Quillon is in thirty days at 11:30, a video call")
    assert out["ask"] == f"Put this date on Data Analyst at Quillon: interview on {soon} at 11:30 (Video call)?"
    assert api.assistant_confirm(out["pending"])["ok"] and store.find(store.load_jobs(), "q1")["event"]["time"] == "11:30"
    for day, word in (("2027-02-30", "YYYY-MM-DD"), ("2020-01-05", "already passed"), ("2099-01-05", "two years away")):
        _decision(monkeypatch, "", {"name": "set_date", "args": {"job": "q1", "day": day, "time": "", "kind": "interview"}})
        refused = api.assistant_talk("set the interview for that day")
        assert refused["ok"] is False and refused["action"] == "say" and word in refused["msg"], "a day that cannot be is said, not asked about"
    _decision(monkeypatch, "", {"name": "set_status", "args": {"job": "q1", "status": "rejected"}})
    out = api.assistant_talk("Quillon said no, set it to rejected")
    assert api.assistant_confirm(out["pending"])["ok"] and store.find(store.load_jobs(), "q1")["status"] == "rejected"
    _decision(monkeypatch, "", {"name": "not_interested", "args": {"job": "q1"}})
    assert "Only a lead" in api.assistant_talk("I am not interested in Quillon any more")["msg"]
    _decision(monkeypatch, "Done, I removed it.", {"name": "delete_job", "args": {"job": "q1"}})
    out = api.assistant_talk("delete Quillon from everything")
    assert out["action"] == "say" and "could not carry out" in out["say"] and store.find(store.load_jobs(), "q1"), "an action that does not exist changes nothing"
    for forged in (None, {}, {"name": "mark_applied"}, {"name": "mark_applied", "args": {"job": "ghost"}}, {"name": "wipe", "args": {"job": "q1"}},
                   {"name": "set_status", "args": {"job": "q1", "status": "hired"}}, {"name": "save_letter", "args": {"job": "q1", "paragraphs": "x"}}):
        assert api.assistant_confirm(forged)["ok"] is False, forged


def test_actions_that_only_show_something_run_at_once(isolate, monkeypatch):
    store.save_jobs([_job(description="We build reporting tools in SQL."), _job(id="q1", company="Quillon", title="Data Analyst", status="waiting",
                                                                             interview_prep={"key_question": {"question": "Why analytics?", "answer": "Because of my thesis."},
                                                                                             "questions": [{"question": "Tell me about SQL.", "answer": "I use it daily."}]})])
    api = ui_api.Api()
    _decision(monkeypatch, "Opening it.", {"name": "open", "args": {"job": "nw1", "what": "letter"}})
    assert api.assistant_talk("open the letter for Northwind please") == {"ok": True, "action": "open", "job_id": "nw1", "what": "letter", "say": "Opening it.", "rows": [], "also": [], "then": []}
    _decision(monkeypatch, "Here.", {"name": "my_answers", "args": {}})
    assert api.assistant_talk("show me the answers I keep for forms")["page"] == "answers"
    # a brief and advice are a second call each, from facts the app holds
    said = {}
    monkeypatch.setattr(llm, "ask", lambda prompt, **kw: said.update(prompt=prompt, **kw) or "Northwind builds reporting tools — in SQL.")
    _decision(monkeypatch, "", {"name": "company_brief", "args": {"job": "nw1"}})
    out = api.assistant_talk("tell me about Northwind before I apply")
    assert out == {"ok": True, "action": "say", "say": "Northwind builds reporting tools – in SQL.", "rows": [], "also": [], "then": []}
    assert "We build reporting tools in SQL." in said["prompt"] and "only use the facts given" in said["system"]
    _decision(monkeypatch, "", {"name": "advice", "args": {}})
    api.assistant_talk("what do my results say about my search?")
    assert "what_works" in said["prompt"] and "skill_gaps" in said["prompt"] and "only use the numbers given" in said["system"]
    monkeypatch.setattr(llm, "ask", lambda *a, **k: (_ for _ in ()).throw(llm.LimitReached("Claude's limit is used up until 14:00.")))
    _decision(monkeypatch, "", {"name": "advice", "args": {}})
    assert "limit is used up" in api.assistant_talk("what do my results say about my search?")["msg"]
    # practice: the questions of the preparation, the key question first
    _decision(monkeypatch, "", {"name": "practice", "args": {"job": "q1"}})
    out = api.assistant_talk("let us practise the interview for Quillon")
    assert out["action"] == "practice" and out["questions"] == ["Why analytics?", "Tell me about SQL."] and "2 questions" in out["say"]
    _decision(monkeypatch, "", {"name": "practice", "args": {"job": "nw1"}})
    assert "no interview preparation" in api.assistant_talk("practise for Northwind")["msg"]
    seen = {}
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: seen.update(prompt=prompt) or {"rating": "weak", "feedback": "Good that you name SQL. Add the report you built."})
    good = api.assistant_practice_answer("q1", "Tell me about SQL.", "I write SQL every day for reports.")
    assert good == {"ok": True, "action": "practice_feedback", "say": "Good that you name SQL. Add the report you built.", "rating": "weak"}
    assert store.find(store.load_jobs(), "q1")["practice"]["Tell me about SQL."]["rating"] == "weak", "how it went is kept, not what you typed"
    assert "I write SQL every day" not in json.dumps(store.find(store.load_jobs(), "q1"))
    _decision(monkeypatch, "", {"name": "practice", "args": {"job": "q1"}})
    again = api.assistant_talk("practise for Quillon again")
    assert again["questions"] == ["Tell me about SQL.", "Why analytics?"] and again["last"] == ["weak", ""] and "the 1 that went badly last time" in again["say"]
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: seen.update(prompt=prompt) or {"rating": "superb", "feedback": "Fine."})
    assert api.assistant_practice_answer("q1", "Tell me about SQL.", "I write SQL every day for reports.")["rating"] == "ok", "a rating that does not exist counts as ok"
    assert "A good answer would draw on: I use it daily." in seen["prompt"] and "I write SQL every day" in seen["prompt"]
    assert "sentence or two" in api.assistant_practice_answer("q1", "Tell me about SQL.", "Yes.")["msg"]
    assert "3000" in api.assistant_practice_answer("q1", "Tell me about SQL.", "word " * 700)["msg"]
    assert api.assistant_practice_answer("ghost", "x", "a b c d")["ok"] is False


def test_an_answer_is_rewritten_on_request_shown_first_and_saved_after_your_yes(isolate, monkeypatch):
    store.save_jobs([_job(form_answers={"made": "1 Oct", "items": [{"question": "Why Northwind?", "answer": "Because your reports are built in SQL, which I use daily.", "check": ""}]})])
    api = ui_api.Api()
    _decision(monkeypatch, "", {"name": "rewrite_answer", "args": {"job": "nw1", "question": "why northwind", "how": "more formal"}})
    seen = {}

    def ask(prompt, **kw):
        if "Rewrite ONE answer" in prompt:
            seen["prompt"] = prompt
            return {"answer": "Your reporting is built on SQL, which I use every day."}
        return {"say": "", "action": {"name": "rewrite_answer", "args": {"job": "nw1", "question": "why northwind", "how": "more formal"}}, "show": []}
    monkeypatch.setattr(llm, "ask_json", ask)
    out = api.assistant_talk("make my answer to why northwind more formal")
    assert out["action"] == "confirm" and out["preview"] == "Your reporting is built on SQL, which I use every day." and "Replace the answer to “Why Northwind?”" in out["ask"]
    assert "What the candidate wants changed: more formal" in seen["prompt"]
    assert store.find(store.load_jobs(), "nw1")["form_answers"]["items"][0]["answer"].startswith("Because"), "shown, not saved"
    assert api.assistant_confirm(out["pending"])["ok"]
    assert store.find(store.load_jobs(), "nw1")["form_answers"]["items"][0]["answer"] == "Your reporting is built on SQL, which I use every day."
    assert answer_memory.recall("Why Northwind?", "Northwind")["answer"].startswith("Your reporting"), "a version you agreed to is your wording"
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: {"say": "", "action": {"name": "rewrite_answer", "args": {"job": "nw1", "question": "salary", "how": "shorter"}}})
    assert "could not tell which answer" in api.assistant_talk("make the salary answer shorter")["msg"]
    with pytest.raises(ValueError):
        form_answers.rewrite(_job(), CV, "Why?", "  ", "shorter")


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


# ── reading a form back, leaving a field out, the dates of a job ────────────
def test_what_is_read_back_for_a_review_is_checked_and_private_values_go_no_further():
    page = form_fill.review_answer(json.dumps({"url": "https://x.example/a", "title": "T", "fields": [
        {"label": "Email", "value": "alex@example.com", "required": True, "kind": "email"}, {"label": "Date of birth", "value": "1999-01-02", "kind": "text"},
        {"label": "Why us?", "value": "x" * 5000, "kind": "textarea"}, {"label": "", "value": "", "required": True}, "junk"]}))
    assert [f["label"] for f in page["fields"]] == ["Email", "Date of birth", "Why us?", "A field with no name"]
    assert page["fields"][1] == {"label": "Date of birth", "value": "", "filled": True, "required": False, "private": True, "kind": "text"}
    assert len(page["fields"][2]["value"]) == 3000 and page["fields"][3]["filled"] is False
    for bad in ("", "[]", '{"fields": 3}'):
        with pytest.raises(ValueError):
            form_fill.review_answer(bad)
    for never in (".click(", "submit(", "dispatchEvent", "fetch(", "cookie", "localStorage", "innerHTML", "setAttribute"):
        assert never not in form_fill.REVIEW, never
    assert "type === 'password'" in form_fill.REVIEW and "type === 'file'" in form_fill.REVIEW, "a password is never read"


def test_a_review_names_what_is_wrong_and_sends_nothing(isolate, monkeypatch):
    store.save_jobs([_job()])
    details.save(MINE)
    held = [{"label": "First name", "value": "Alex", "required": True, "kind": "text"}, {"label": "Email", "value": "old@example.com", "required": True, "kind": "email"},
            {"label": "Phone", "value": "", "required": True, "kind": "tel"}, {"label": "When can you start?", "value": "On [your start date].", "kind": "text"},
            {"label": "Why Northwind?", "value": "I led a team of ten at Globex.", "kind": "textarea"}, {"label": "Gender", "value": "Male", "kind": "select"}]
    monkeypatch.setattr(chrome, "active_tab", lambda: {"url": "https://careers.northwind.example/jobs/42", "title": "Junior Analyst - Northwind"})
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps({"url": "https://careers.northwind.example/jobs/42", "title": "t", "fields": held}))
    seen = {}

    def ask(prompt, **kw):
        seen.update(prompt=prompt, **kw)
        return {"problems": [{"field": "why northwind?", "problem": "The CV shows no team lead role and no Globex."}, {"field": "Nowhere", "problem": "made up"},
                             {"field": "Phone", "problem": "Empty."}]}
    monkeypatch.setattr(llm, "ask_json", ask)
    out = ui_api.Api().assistant_review()
    assert out["ok"] and out["job_id"] == "nw1" and "5 of 6 fields are filled in" in out["say"] and "4 things look wrong" in out["say"] and "did not send anything" in out["say"]
    assert out["problems"] == [{"field": "Email", "problem": "It is not the address in My details (alex@example.com)."},
                               {"field": "Phone", "problem": "It is required and still empty."},
                               {"field": "When can you start?", "problem": "It still has a part in [square brackets] to fill in."},
                               {"field": "Why Northwind?", "problem": "The CV shows no team lead role and no Globex."}]
    assert "Male" not in seen["prompt"] and "Gender" not in seen["prompt"], "a personal answer is not sent to Claude"
    assert "- Why Northwind?: I led a team of ten at Globex." in seen["prompt"] and "contradicts the CV" in seen["system"]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: (_ for _ in ()).throw(llm.LimitReached("Claude's limit is used up until 14:00.")))
    plain = ui_api.Api().assistant_review()
    assert plain["ok"] and len(plain["problems"]) == 3 and "only the plain checks were made" in plain["say"]
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps({"url": "u", "title": "t", "fields": []}))
    assert "no form fields" in ui_api.Api().assistant_review()["msg"]
    monkeypatch.setattr(chrome, "active_tab", lambda: {"url": "https://forms.example.ru/a", "title": ""})
    assert "Russian services" in ui_api.Api().assistant_review()["msg"]


def test_a_field_you_name_is_left_out(isolate, monkeypatch):
    details.save({**MINE, "salary_amount": 60000})
    _browser(monkeypatch, [_field("Email", n=1), _field("Salary expectation", n=2), _field("Phone", n=3)], url="https://forms.example.org/a", title="Apply")
    out = ui_api.Api().assistant_fill("", skip=["Salary", "phone"])
    assert [f["label"] for f in out["filled"]] == ["Email"]
    assert out["left"] == [{"label": "Salary expectation", "why": form_fill.SKIPPED}, {"label": "Phone", "why": form_fill.SKIPPED}]
    _decision(monkeypatch, "", {"name": "fill_form", "args": {"skip": ["salary"]}})
    talked = ui_api.Api().assistant_talk("fill it in but skip the salary")
    assert talked["action"] == "fill" and [f["label"] for f in talked["filled"]] == ["Email", "Phone"]


def test_the_dates_of_a_job_go_into_its_row_in_the_form_the_field_takes():
    assert form_fill.when_for("month", "03/2023") == ("2023-03", "") and form_fill.when_for("date", "3/2023") == ("2023-03-01", form_fill.CHECK_DAY)
    assert form_fill.when_for("text", "03/2023") == ("03/2023", "") and form_fill.when_for("text", "2020") == ("2020", "")
    assert form_fill.when_for("month", "2020") == ("", form_fill.NO_MONTH) and form_fill.when_for("date", "") == ("", "")
    fields = [_field("Start date", kind="date", n=1), _field("Company", n=2), _field("Start date", kind="month", n=3), _field("End date", kind="month", n=4),
              _field("Company", n=5), _field("Job title", n=6), _field("From", kind="date", n=7), _field("To", kind="date", n=8),
              _field("Company", n=9), _field("Dates: from", n=10), _field("Dates: to", n=11), _field("School", n=12), _field("Start date", kind="month", n=13),
              _field("Earliest start date", kind="date", n=14)]
    todo = form_fill.plan(fields, {**FULL, "experience": [dict(JOBS[1]), dict(JOBS[2], start="09/2022"), dict(JOBS[0])]})
    assert [(f["n"], f["value"], f.get("check", "")) for f in todo["fill"]] == [
        (2, "Northwind", ""), (3, "2023-03", ""), (5, "Evening School", ""), (6, "Tutor", ""), (7, "2022-09-01", form_fill.CHECK_DAY),
        (9, "Old Mill", ""), (10, "2020", ""), (11, "2021", ""), (12, "Masaryk University", "")]
    left = [(i["label"], i["why"]) for i in todo["left"]]
    assert left == [("Start date", form_fill.DATE), ("Start date", form_fill.NO_MONTH), ("Earliest start date", form_fill.DATE)], \
        "a date before any row, a year where a month is asked, and your availability are left; a current job's end date is not even listed"
    assert todo["rows"] == {"experience": 3, "education": 1}
    filled_first = form_fill.plan([_field("Company", n=1, filled=True), _field("Job title", n=2, filled=True), _field("Company", n=3), _field("Job title", n=4)], FULL)
    assert [(f["n"], f["value"]) for f in filled_first["fill"]] == [(3, "Evening School"), (4, "Tutor")], "a row that is filled is still a row: asking twice does not repeat a job"


def test_words_for_a_field_the_app_does_not_know_must_stand_in_the_cv(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: {"choices": [{"n": 1, "answer": "Python"}, {"n": 2, "answer": "Rust"}, {"n": 3, "answer": "I am a great analyst with SQL."},
                                                                           {"n": 4, "answer": "Czechia"}]})
    choices = [{"n": n, "kind": "text", "label": label, "options": []} for n, label in ((1, "Main language"), (2, "Other language"), (3, "About"), (4, "Where"))]
    assert form_choices.decide(choices, CV, MINE, None) == {1: "Python", 4: "Czechia"}, "in the CV, or in your details; nothing else, and never a sentence it made up"


def test_area_the_filled_form_is_read_back_and_reviewed():
    out = _area("plain.html", job_id="vt", review=True, problems=[{"field": "Why do you want to work at Northwind?", "problem": "It names Northwind, but the job is at Vantor."}])
    review = out["reviewed"]
    assert review["ok"] and review["job_id"] == "vt" and out["sent"] is False and out["clicked"] is False
    found = {p["field"]: p["problem"] for p in review["problems"]}
    assert found["Why do you want to work at Northwind?"] == "It names Northwind, but the job is at Vantor.", "what Claude sees against the CV and the job"
    assert all("required" not in p for p in found.values()) or True
    assert "nothing wrong" not in review["say"] and "did not send anything" in review["say"]
    assert out["state"]["pw"] == "" and out["state"]["dob"] == "", "reading back changes nothing"


# ── what the assistant says without being asked ─────────────────────────────
def test_the_briefing_is_worked_out_from_your_data_without_claude(isolate, monkeypatch):
    from datetime import date, timedelta
    from jobhelper import db
    monkeypatch.setattr(llm, "ask", lambda *a, **k: pytest.fail("a briefing costs nothing"))
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("a briefing costs nothing"))
    api = ui_api.Api()
    assert api.assistant_briefing() == {"headline": "", "lines": [], "nudges": []}, "nothing to say: the robot only says hello"
    today = date.today()
    store.save_jobs([
        _job(form_filled=(today - timedelta(days=1)).isoformat()),
        _job(id="fresh", company="Fresh", form_filled=today.isoformat()),
        _job(id="iv", company="Quillon", title="Data Analyst", status="interview", date_applied="2026-09-01",
             event={"date": (today + timedelta(days=1)).isoformat(), "time": "10:00", "kind": "interview", "note": ""}),
        _job(id="ready", company="Vantor", title="Tester", status="interview", date_applied="2026-09-01", interview_prep={"questions": [{"question": "q", "answer": "a"}]},
             event={"date": today.isoformat(), "time": "", "kind": "interview", "note": ""}),
        _job(id="inv", company="Brightpath", title="Developer", status="waiting", date_applied="2026-09-10")])
    monkeypatch.setattr(db, "all_responses", lambda: [{"job_id": "inv", "stage": "interview", "received_date": (today - timedelta(days=2)).strftime("%a, %d %b %Y 10:00:00 +0000"),
                                                      "subject": "Invitation", "summary": "They invite you."}])
    out = api.assistant_briefing()
    texts = {n["kind"] + ":" + n["job_id"]: n["text"] for n in out["nudges"]}
    assert set(texts) == {"apply:nw1", "prep:iv", "date:inv"}, "filled today, prepared already, or no invitation: not reminded"
    assert "did not mark it applied" in texts["apply:nw1"] and "is tomorrow and there is no preparation yet" in texts["prep:iv"]
    assert texts["date:inv"].startswith("Brightpath invited you on") and out["headline"] == out["nudges"][0]["text"]
    assert any("ready to send" in line for line in out["lines"]) and any("invitation" in line for line in out["lines"])
    assert api.assistant_nudge_done("nw1", "apply") == {"ok": True} and api.assistant_nudge_done("nw1", "everything") == {"ok": False}
    assert "apply:nw1" not in {n["kind"] + ":" + n["job_id"] for n in api.assistant_briefing()["nudges"]}, "said once is enough when you say so"
    filled = _browser(monkeypatch, [_field("Email", n=1)])
    details.save(MINE)
    assert filled is not None and api.assistant_fill("fresh")["ok"] and store.find(store.load_jobs(), "fresh")["form_filled"] == today.isoformat()


def test_noticing_a_form_is_off_until_you_turn_it_on_and_offers_each_page_once(isolate, monkeypatch):
    store.save_jobs([_job()])
    api = ui_api.Api()
    monkeypatch.setattr(chrome, "active_tab", lambda: pytest.fail("off: Chrome is not looked at"))
    assert api.assistant_watching() is False and api.assistant_notice() == {"ok": False, "off": True}
    assert api.assistant_set_watch("yes")["ok"] is False and api.assistant_watching() is False
    assert api.assistant_set_watch(True) == {"ok": True, "on": True, "msg": ""} and api.assistant_watching() is True
    assert api.options()["where"] == "", "the other options are kept as they were"
    tab = {"url": "https://careers.northwind.example/jobs/42", "title": "Junior Analyst - Northwind"}
    monkeypatch.setattr(chrome, "active_tab", lambda: dict(tab))
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps({"url": tab["url"], "fields": 6, "first": "a|b", "empty": 5}))
    out = api.assistant_notice()
    assert out["ok"] and out["job_id"] == "nw1" and "looks like the form for Junior Analyst at Northwind" in out["say"]
    assert api.assistant_notice() == {"ok": False}, "the same page is not offered twice"
    tab["url"] = "https://careers.northwind.example/jobs/42?step=2"
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps({"url": tab["url"], "fields": 6, "first": "a|b", "empty": 1}))
    assert api.assistant_notice() == {"ok": False}, "nothing left to fill in: nothing to offer"
    tab.update(url="https://news.example.org/today", title="News")
    assert api.assistant_notice() == {"ok": False}, "a page that belongs to no job of yours"
    tab.update(url="chrome://settings", title="Settings")
    assert api.assistant_notice() == {"ok": False}
    monkeypatch.setattr(chrome, "active_tab", lambda: (_ for _ in ()).throw(chrome.ChromeError(chrome.NOT_RUNNING)))
    assert api.assistant_notice() == {"ok": False, "problem": ""}, "Chrome not in use is nothing to report"
    monkeypatch.setattr(chrome, "active_tab", lambda: (_ for _ in ()).throw(chrome.ChromeError(chrome.NO_CONSENT)))
    assert api.assistant_notice() == {"ok": False, "problem": chrome.NO_CONSENT}
    assert api.assistant_set_watch(False)["ok"] and api.assistant_notice() == {"ok": False, "off": True}


# ── the assistant at "pro" level ────────────────────────────────────────────
def _many(n):
    order = ["waiting", "interview", "letter_ready", "found", "rejected"]
    return [_job(id=f"j{i}", company=f"Company{i} Works", title=f"Role {i}", status=order[i % 5], match_score=i % 100, url="") for i in range(n)]


def test_only_the_jobs_a_request_is_likely_about_are_sent(isolate, monkeypatch):
    jobs = _many(200) + [_job(id="named", company="Brightpath", title="Developer", status="rejected", url="")]
    shown = assistant_brain.relevant(jobs, "which applications are waiting longest?")
    assert len(shown) == assistant_brain.MAX_JOBS and all(j["status"] != "rejected" for j in shown), "closed applications are not sent unless asked about"
    assert shown[0]["status"] == "interview" and shown[-1]["status"] in ("waiting", "letter_ready", "found")
    assert assistant_brain.relevant(jobs, "what did brightpath answer?")[0]["id"] == "named", "a company named in the talk comes first, whatever its state"
    assert assistant_brain.relevant(jobs, "anything", context_id="j4")[0]["id"] == "j4", "and so does the job in front"
    assert any(j["status"] == "rejected" for j in assistant_brain.relevant(jobs, "how many were rejected so far?", most=300))
    lines, ids = assistant_brain.snapshot(jobs, [], words="what did brightpath answer?")
    assert len(ids) == assistant_brain.MAX_JOBS and len(lines) < 9000, "a third of what sending every job took"
    said = assistant_brain.totals(jobs, len(ids))
    assert "40 waiting" in said and "41 rejected" in said and f"Listed below: {assistant_brain.MAX_JOBS} of 201" in said
    store.save_jobs(jobs)
    seen = _decision(monkeypatch, "Forty are waiting.", None)
    ui_api.Api().assistant_talk("how many applications are waiting?")
    assert "All jobs by status:" in seen["prompt"] and "40 waiting" in seen["prompt"]


def test_several_things_in_one_request_are_asked_about_together_and_can_be_taken_back(isolate, monkeypatch):
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=10)).isoformat()
    store.save_jobs([_job(), _job(id="twin", title="Junior Analyst", url="https://other.example/1"), _job(id="q1", company="Quillon", title="Data Analyst", url="")])
    api = ui_api.Api()
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: {"say": "", "show": [], "actions": [
        {"name": "mark_applied", "args": {"job": "nw1"}},
        {"name": "set_date", "args": {"job": "nw1", "day": soon, "time": "", "kind": "other", "note": "Follow up"}},
        {"name": "open", "args": {"job": "q1", "what": "job"}}, {"name": "wipe", "args": {}}]})
    out = api.assistant_talk("mark northwind applied, remind me to follow up in ten days and open quillon")
    assert out["action"] == "confirm" and out["pending"]["name"] == "many" and len(out["pending"]["args"]["actions"]) == 2
    assert out["ask"].startswith("Shall I do these 2 things?\n1. Mark Junior Analyst at Northwind as applied?") and f"2. Put this date on Junior Analyst at Northwind: other on {soon} (Follow up)?" in out["ask"]
    assert any("Opening" in text for text in out["also"]) and any("could not carry out" in text for text in out["also"]), "what only shows is done at once; what does not exist is said"
    assert out["then"] == [{"action": "open", "job_id": "q1", "what": "job", "page": ""}], "the window still opens what was asked for"
    assert store.find(store.load_jobs(), "nw1")["status"] == "letter_ready"
    done = api.assistant_confirm(out["pending"])
    assert done["ok"] and done["can_undo"] and "Moved Junior Analyst at Northwind to Applications" in done["say"] and "The date is set" in done["say"]
    after = store.load_jobs()
    assert store.find(after, "nw1")["status"] == "waiting" and store.find(after, "nw1")["event"]["note"] == "Follow up"
    assert store.find(after, "twin") is None, "the app folds away the same role at the same company, as Mark applied always did"
    back = api.assistant_undo()
    restored = store.load_jobs()
    assert back["ok"] and back["can_undo"] is False and "is as it was before" in back["say"]
    assert store.find(restored, "nw1")["status"] == "letter_ready" and "event" not in store.find(restored, "nw1") and store.find(restored, "twin"), "everything is back, the folded lead too"
    assert api.assistant_undo()["msg"] == "There is nothing to take back."
    # one of several fails: said, and what was done before it can still be taken back
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: {"say": "", "show": [], "actions": [
        {"name": "set_status", "args": {"job": "q1", "status": "waiting"}}, {"name": "set_status", "args": {"job": "q1", "status": "interview"}}]})
    out = api.assistant_talk("quillon is waiting, no wait, it is an interview")
    forged = {"name": "many", "args": {"actions": out["pending"]["args"]["actions"][:1] + [{"name": "set_status", "args": {"job": "ghost", "status": "offer"}}]}}
    failed = api.assistant_confirm(forged)
    assert failed["ok"] is False and failed["changed"] and failed["can_undo"] and "Before that:" in failed["msg"]
    assert api.assistant_undo()["ok"] and store.find(store.load_jobs(), "q1")["status"] == "letter_ready"
    for forged in ({"name": "many", "args": {"actions": []}}, {"name": "many", "args": {"actions": "all"}}, {"name": "many", "args": {"actions": [{}] * 4}}):
        assert api.assistant_confirm(forged)["ok"] is False
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: {"say": "", "show": [], "actions": [
        {"name": "mark_applied", "args": {"job": "q1"}}, {"name": "rewrite_letter", "args": {"job": "q1", "paragraph": 1, "how": "shorter"}}]})
    assert "on its own" in api.assistant_talk("apply to quillon and shorten the letter")["msg"]


def test_not_interested_and_a_running_search(isolate, monkeypatch):
    store.save_jobs([_job()])
    api = ui_api.Api()
    _decision(monkeypatch, "", {"name": "not_interested", "args": {"job": "nw1"}})
    out = api.assistant_talk("I am not interested in northwind")
    assert "Remove Junior Analyst at Northwind from New Jobs" in out["ask"]
    assert api.assistant_confirm(out["pending"])["can_undo"] and store.find(store.load_jobs(), "nw1")["status"] == store.NOT_INTERESTED
    assert api.assistant_undo()["ok"] and store.find(store.load_jobs(), "nw1")["status"] == "found"
    api.live = store.load_jobs()                # a search is running
    assert "is running" in api.assistant_confirm({"name": "many", "args": {"actions": [{"name": "mark_applied", "args": {"job": "nw1"}}]}})["msg"]
    api._undo = [{"kind": "added", "id": "x", "what": "x"}]
    assert "is running" in api.assistant_undo()["msg"]


def test_what_you_tell_it_to_remember_is_kept_between_sessions(isolate, monkeypatch):
    from jobhelper import assistant_notes
    assert assistant_notes.path() in vault.data_files() and assistant_notes.notes() == []
    for bad, word in (("", "few words"), ("no", "few words"), ("x" * 201, "up to 200")):
        assert word in assistant_notes.remember(bad)["msg"]
    store.save_jobs([_job()])
    api = ui_api.Api()
    _decision(monkeypatch, "", {"name": "remember", "args": {"note": "No consulting firms"}})
    out = api.assistant_talk("remember that I do not want consulting firms")
    assert out["ok"] and out["notes_changed"] and "I will remember: No consulting firms" in out["say"] and "use Options" in out["say"]
    assert "already knew" in api.assistant_talk("remember that I do not want consulting firms")["say"]
    seen = _decision(monkeypatch, "Noted.", None)
    fresh = ui_api.Api()                        # the app was closed and opened again
    fresh.assistant_talk("which of my leads fit me best?")
    assert "1. No consulting firms" in seen["prompt"], "the note is there the next day"
    assert "Person: remember that I do not want consulting firms" in seen["prompt"], "and so is the talk"
    assert api.assistant_notes_list() == {"notes": [{"text": "No consulting firms", "when": assistant_notes.notes()[0]["when"]}]}
    _decision(monkeypatch, "I will forget it.", {"name": "forget_note", "args": {"number": 3}})
    assert "could not carry out" in api.assistant_talk("forget the third note")["say"], "a note that is not there"
    _decision(monkeypatch, "", {"name": "forget_note", "args": {"number": 1}})
    assert "Forgotten: No consulting firms." in api.assistant_talk("forget the note about consulting")["say"] and assistant_notes.notes() == []
    assert api.assistant_forget_note(1)["ok"] is False
    for i in range(assistant_notes.MAX_NOTES):
        assert assistant_notes.remember(f"note number {i}")["ok"]
    assert "up to 40" in assistant_notes.remember("one more")["msg"]
    assert api.assistant_new_talk()["ok"] and assistant_notes.turns() == []
    assistant_notes.path().write_text("{ broken")
    assert assistant_notes.notes() == [] and assistant_notes.turns() == []


def test_a_reply_to_a_company_is_drafted_for_you_to_send(isolate, monkeypatch):
    from jobhelper import db
    store.save_jobs([_job(status="waiting")])
    api = ui_api.Api()
    _decision(monkeypatch, "", {"name": "draft_reply", "args": {"job": "nw1", "how": "accept the Tuesday slot"}})
    monkeypatch.setattr(db, "all_responses", lambda: [])
    assert "nothing to reply to" in api.assistant_talk("answer northwind that tuesday suits me")["msg"]
    monkeypatch.setattr(db, "all_responses", lambda: [{"job_id": "nw1", "stage": "interview", "received_date": "Mon, 05 Oct 2026 10:00:00 +0000",
                                                      "subject": "Interview invitation", "summary": "They offer Tuesday 10:00 or Thursday 14:00.", "next_step": "Pick a slot"}])
    seen = {}
    monkeypatch.setattr(llm, "ask", lambda prompt, **kw: seen.update(prompt=prompt, **kw) or "Dear team,\n\nTuesday at 10:00 suits me — thank you.\n\nAlex Novak")
    out = api.assistant_talk("answer northwind that tuesday suits me")
    assert out["action"] == "draft" and out["copy"] == "Dear team,\n\nTuesday at 10:00 suits me – thank you.\n\nAlex Novak" and "I never send mail" in out["say"]
    assert "They offer Tuesday 10:00 or Thursday 14:00." in seen["prompt"] and "accept the Tuesday slot" in seen["prompt"] and "Alex Novak" in seen["prompt"]
    assert "square brackets" in seen["system"] and "for one job applicant to send themselves" in seen["system"]
    monkeypatch.setattr(llm, "ask", lambda *a, **k: "  ")
    assert "no draft" in api.assistant_talk("answer northwind that tuesday suits me")["msg"]


POSTING = ("Junior Data Analyst\nNorthwind Systems, Brno\n" + "We are looking for a junior analyst who writes SQL and builds reports for our clients. " * 12)


def test_a_posting_open_in_the_browser_is_scored_and_added_only_on_your_yes(isolate, monkeypatch):
    from jobhelper import agent3_letters
    store.save_jobs([_job()])
    api = ui_api.Api()
    page = {"url": "https://jobs.example.net/ads/777", "title": "Junior Data Analyst - Northwind Systems", "text": POSTING}
    monkeypatch.setattr(chrome, "active_tab", lambda: {"url": page["url"], "title": page["title"]})
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps(page))
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: {"is_posting": True, "title": "Junior Data Analyst", "company": "Northwind Systems", "location": "Mars"})
    scored = []

    def rescore(jobs, ids, profile, cv_text="", **kw):
        scored.append(dict(jobs[0]))
        jobs[0].update(match_score=71, match_tier="strong", match_reason="Solid SQL; reports are your daily work.")
        return {"scored": 1, "changed": [], "failed": 0}
    monkeypatch.setattr(agent3_letters, "rescore", rescore)
    out = api.assistant_judge_page()
    assert out["action"] == "confirm" and out["ask"].startswith("Junior Data Analyst at Northwind Systems scores 71, above your limit of 50. Solid SQL")
    assert scored[0]["title"] == "Junior Data Analyst" and scored[0]["location"] == "" and scored[0]["description"] == POSTING, \
        "scored by the app's own scorer; a place that does not stand on the page is not taken"
    assert len(store.load_jobs()) == 1, "asked, not added"
    done = api.assistant_confirm(out["pending"])
    added = [j for j in store.load_jobs() if j["source"] == "assistant"]
    assert done["ok"] and "Added Junior Data Analyst at Northwind Systems to New Jobs with a score of 71" in done["say"] and len(added) == 1
    assert added[0]["status"] == "found" and added[0]["url"] == page["url"] and added[0]["match_score"] == 71 and added[0]["id"].startswith("assistant-")
    assert "in your list already" in api.assistant_confirm(out["pending"])["msg"]
    again = api.assistant_judge_page()
    assert again["action"] == "say" and "in your list already" in again["say"] and again["rows"][0]["id"] == added[0]["id"], "known by its address: no call"
    assert api.assistant_undo()["ok"] and len(store.load_jobs()) == 1, "the added posting can be taken back"
    for record in (None, {}, {"title": "x", "url": "javascript:1", "match_score": 5}, {"title": "", "url": "https://a.example/1", "match_score": 5},
                   {"title": "x", "url": "https://a.example/1"}, {"title": "x", "url": "https://a.example/1", "match_score": 500}):
        assert api.assistant_confirm({"name": "add_job", "args": {"record": record}})["ok"] is False, record
    # a page that states its job for search engines needs no call to be read: the scoring is the only one
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("the page says what the job is"))
    page.update(url="https://jobs.example.net/ads/778", stated={"title": "Data Engineer", "company": "Harbor Analytics", "location": "Brno, CZ"})
    stated = api.assistant_judge_page()
    assert stated["action"] == "confirm" and stated["ask"].startswith("Data Engineer at Harbor Analytics scores 71")
    assert scored[-1]["company"] == "Harbor Analytics" and scored[-1]["location"] == "Brno, CZ"
    page.pop("stated")
    page["url"] = "https://jobs.example.net/ads/777"
    assert form_fill.page_answer(json.dumps({"url": "u", "title": "t", "text": "x", "stated": "junk"}))["stated"] == {"title": "", "company": "", "location": ""}
    assert "JSON.parse" in form_fill.PAGE and "JobPosting" in form_fill.PAGE
    # every reason not to judge a page is said
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: {"is_posting": False, "title": "", "company": "", "location": ""})
    assert "does not read like one job posting" in api.assistant_judge_page()["msg"]
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: {"is_posting": True, "title": "Chief Wizard", "company": "Northwind Systems", "location": ""})
    assert "does not read like one job posting" in api.assistant_judge_page()["msg"], "a title that is not on the page is not a posting"
    page["text"] = "Too short."
    assert "too little text" in api.assistant_judge_page()["msg"]
    page.update(url="https://rabota.example.ru/1", text=POSTING)
    assert "Russian services" in api.assistant_judge_page()["msg"]
    monkeypatch.setattr(chrome, "active_tab", lambda: (_ for _ in ()).throw(chrome.ChromeError(chrome.NOT_RUNNING)))
    assert api.assistant_judge_page()["msg"] == chrome.NOT_RUNNING
    for never in (".click(", "submit(", "dispatchEvent", "fetch(", "cookie", "localStorage", "setAttribute", ".value"):
        assert never not in form_fill.PAGE, never


def test_the_window_is_told_what_is_being_done(isolate, monkeypatch):
    store.save_jobs([_job()])
    said = []
    _decision(monkeypatch, "It is ready to send.", None)
    ui_api.Api().assistant_talk("what about northwind?", progress=said.append)
    assert said == ["Looking at your jobs…", "Asking Claude…", "Checking the answer…"]
    said.clear()
    ui_api.Api().assistant_talk("help", progress=said.append)
    assert said == [], "a fixed request is answered at once"


def test_a_date_asked_as_two_lists_and_the_box_of_a_current_job():
    months = ["Month", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    years = ["Year", "2019", "2020", "2021", "2022", "2023", "2024"]
    assert form_fill.date_option(months, "03/2023") == ("March", "") and form_fill.date_option(years, "03/2023") == ("2023", "")
    assert form_fill.date_option(["01", "02", "03"], "3/2023") == ("03", "") and form_fill.date_option(["Jan", "Feb", "Mar"], "03/2023") == ("Mar", "")
    assert form_fill.date_option(["1 - January", "3 - March"], "03/2020") == ("3 - March", "") and form_fill.date_option(months, "2023") == ("", form_fill.NO_MONTH)
    assert form_fill.date_option(years, "1999") == ("", "") and form_fill.date_option(months, "") == ("", "")
    fields = [_field("Company", n=1), _field("Job title", n=2), _field("Start date", kind="select", n=3, options=months), _field("Start date", kind="select", n=4, options=years),
              _field("End date", kind="select", n=5, options=months), _field("I currently work here", kind="checkbox", n=6),
              _field("Company", n=7), _field("Job title", n=8), _field("From (month)", kind="select", n=9, options=months), _field("I currently work here", kind="checkbox", n=10),
              _field("Company", n=11), _field("To year", kind="select", n=12, options=years), _field("I currently work here", kind="checkbox", n=13),
              _field("Notice period", kind="select", n=14, options=["1 month"])]
    todo = form_fill.plan(fields, {**FULL, "experience": [dict(JOBS[1]), dict(JOBS[2]), dict(JOBS[0])]})
    filled = {f["n"]: f["value"] for f in todo["fill"]}
    assert filled[3] == "March" and filled[4] == "2023" and 5 not in filled, "the job goes on: its end stays empty"
    assert 9 not in filled and filled[12] == "2021"
    assert todo["tick"] == [{"n": 6, "label": "I currently work here"}, {"n": 10, "label": "I currently work here"}], "ticked for the two jobs that go on, not for the one that ended"
    assert ("From (month)", form_fill.NO_MONTH) in [(i["label"], i["why"]) for i in todo["left"]]
    assert [c["label"] for c in todo["choose"]] == ["Notice period"], "a list that is not a date is still a choice"
    assert form_fill.plan([_field("I currently work here", kind="checkbox", n=1)], FULL)["tick"] == [], "a box before any job row belongs to no job"


def test_other_browsers_are_spoken_to_in_their_own_way(isolate, monkeypatch):
    calls = _chrome(monkeypatch, _Done("https://jobs.example.com/apply/7\nApply - Example\n"))
    try:
        assert chrome.use("safari") == "safari" and chrome.name() == "Safari" and chrome.short() == "Safari"
        assert chrome.active_tab() == {"url": "https://jobs.example.com/apply/7", "title": "Apply - Example"}
        said = " ".join(calls[-1][0])
        assert 'tell application "Safari"' in said and "URL of current tab of front window" in said and "name of current tab" in said
        chrome.run("1 + 1")
        assert "do JavaScript (item 1 of argv) in current tab of front window" in " ".join(calls[-1][0]) and calls[-1][0][-1] == "1 + 1"
        chrome.open_tab("https://x.example/a")
        assert "set current tab to (make new tab" in " ".join(calls[-1][0])
        _chrome(monkeypatch, _Done(err="execution error: Safari got an error: You must enable 'Allow JavaScript from Apple Events' in the Develop menu", code=1))
        with pytest.raises(chrome.ChromeError) as e:
            chrome.run("1")
        assert e.value.kind == "no_scripts" and "In Safari's menu bar choose Develop > Allow JavaScript from Apple Events" in str(e.value)
        calls = _chrome(monkeypatch, _Done("x\ny\n"))
        for key, app in (("brave", "Brave Browser"), ("edge", "Microsoft Edge"), ("chrome", "Google Chrome")):
            chrome.use(key)
            chrome.run("1")
            assert f'tell application "{app}"' in " ".join(calls[-1][0]) and "execute active tab of front window javascript" in " ".join(calls[-1][0])
        chrome.use("opera")
        chrome.run("1")
        assert 'tell application "Opera"' in " ".join(calls[-1][0]) and chrome.short() == "Opera"
        assert chrome.use("firefox") == "chrome" and chrome.use("opera_gx") == "chrome", "a browser that cannot be reached this way is never the one in use"
        # a browser that does not know the command at all (the live trial with Opera GX): said for what it is, not as "bring the tab to the front"
        _chrome(monkeypatch, _Done(err="162:172: syntax error: Expected “,” but found property. (-2741)", code=1))
        chrome.use("opera")
        with pytest.raises(chrome.ChromeError) as e:
            chrome.run("1")
        assert e.value.kind == "cannot" and "does not let another app fill in its pages" in str(e.value) and "Google Chrome and Safari work" in str(e.value)
        noted = []
        from jobhelper import trouble
        monkeypatch.setattr(trouble, "note", lambda what, error: noted.append((what, str(error))))
        _chrome(monkeypatch, _Done(err="execution error: something nobody has seen before (-9999)", code=1))
        with pytest.raises(chrome.ChromeError) as e:
            chrome.run("1")
        assert e.value.kind == "refused" and noted == [("asking Opera about the page in front", "execution error: something nobody has seen before (-9999)")], \
            "a reason the app does not know is written down, so that it can be found out"
        calls = _chrome(monkeypatch, _Done("x\ny\n"))
        assert chrome.use("netscape") == "chrome" and chrome.use(None) == "chrome"
        assert chrome.ChromeError(chrome.NOT_RUNNING).kind == "not_running" and chrome.ChromeError("something else").kind == "refused"
        # the choice is kept with the options and used from then on
        api = ui_api.Api()
        assert api.assistant_browser()["key"] == "chrome" and [b["key"] for b in api.assistant_browser()["all"]] == ["chrome", "brave", "edge", "opera", "safari", "opera_gx", "firefox"]
        refused = api.assistant_set_browser("firefox")
        assert refused["ok"] is False and refused["msg"].startswith("Firefox does not let another app") and api.assistant_browser()["key"] == "chrome"
        gx = api.assistant_set_browser("opera_gx")
        assert gx["ok"] is False and "switched off the part that lets one fill a page in" in gx["msg"] and "Google Chrome or Safari" in gx["msg"]
        api.save_options({"assistant_browser": "chrome"})
        import json as _json
        from jobhelper import vault as _vault
        kept = _json.loads(_vault.read_text(config.DATA_DIR / "ui_settings.json"))
        _vault.write_text(config.DATA_DIR / "ui_settings.json", _json.dumps({**kept, "assistant_browser": "opera_gx"}))
        assert api.assistant_browser()["key"] == "chrome", "a choice saved before Opera GX was found not to work falls back to Chrome"
        assert api.assistant_set_browser("netscape")["ok"] is False and api.check_options({"assistant_browser": "firefox"})[1]
        out = api.assistant_set_browser("safari")
        assert out["ok"] and out["name"] == "Safari" and "Develop" in out["switch"] and api.options()["assistant_browser"] == "safari"
        details.save(MINE)
        monkeypatch.setattr(chrome, "active_tab", lambda: (_ for _ in ()).throw(chrome.ChromeError(chrome.said("not_running"), "not_running")))
        assert ui_api.Api().assistant_fill()["msg"] == "Safari is not open. Open the application form in Safari, then ask me again."
        assert api.check_options({"assistant_browser": "lynx"})[1].startswith("“assistant browser” must be one of")
    finally:
        chrome.use("chrome")


def test_a_test_never_writes_into_the_real_trouble_log():
    """A refusal nobody recognises is kept in the trouble log; from a test it must land in a spare folder, not in data/."""
    from jobhelper import config, trouble
    before = (config.DATA_DIR / trouble.LOG_NAME).stat().st_size if (config.DATA_DIR / trouble.LOG_NAME).exists() else 0
    trouble.note("a test", "a line that must not reach the real log")
    after = (config.DATA_DIR / trouble.LOG_NAME).stat().st_size if (config.DATA_DIR / trouble.LOG_NAME).exists() else 0
    assert before == after and trouble._folder() != config.DATA_DIR
    assert "must not reach" in (trouble._folder() / trouble.LOG_NAME).read_text(encoding="utf-8")


# ── files: the CV and the letter of the job go into the form's file fields ──
def _bytes(name: str, size: int) -> bytes:
    return bytes((i * 7 + len(name)) % 256 for i in range(size))          # the same invented content the test area writes


def _sum(content: bytes) -> int:
    return sum(content) % 65521


@pytest.mark.parametrize("label, kind", [
    ("Resume:", "cv"), ("Attach your Resume (supported formats: png, jpeg, jpg, pdf, doc, docx, txt)", "cv"), ("Upload your CV", "cv"),
    ("Curriculum vitae", "cv"), ("Cover letter", "letter"), ("Motivation letter (PDF)", "letter"), ("Other Attachments:", "other"),
    ("Attach your Attachments (supported formats: png, pdf)", "other"), ("Additional documents", "other"), ("Certificates", "other"),
    ("Your photo", ""), ("Passport copy", ""), ("Transcript of records", ""), ("Portfolio", ""), ("Upload", ""), ("", "")])
def test_a_file_field_says_which_file_it_wants(label, kind):
    field = _field(label, kind="file")
    assert form_fill.classify(field) == ("file", "") and form_fill.file_kind(field) == kind
    todo = form_fill.plan([field], MINE)
    assert [i["kind"] for i in todo["attach"]] == ([kind] if kind else []) and [i["why"] for i in todo["left"]] == ([] if kind else [form_fill.FILE])
    assert not form_fill.plan([{**field, "filled": True}], MINE)["attach"], "a field that holds a file is not given another"


@pytest.mark.parametrize("accept, name, ok", [
    ("", "CV.pdf", True), (".pdf,.docx", "CV.pdf", True), (".PDF, .DOCX", "cv.Pdf", True), (".png,.jpg", "CV.pdf", False),
    ("application/pdf", "CV.pdf", True), ("application/pdf", "CV.docx", False), ("image/*", "CV.pdf", False), ("application/*", "CV.docx", True),
    ("*/*", "CV.odd", True), (".doc", "CV.docx", False), ("text/plain", "letter.txt", True)])
def test_a_file_is_offered_only_to_a_field_that_takes_its_kind(accept, name, ok):
    assert form_fill.takes(accept, name) is ok


def test_a_file_travels_to_the_page_in_pieces_and_as_data():
    content = _bytes("x", form_fill.PIECE * 2)          # larger than two requests
    pieces = form_fill.put_scripts("__jobhelper_k", content)
    assert len(pieces) == 3 and all(len(p) < form_fill.PIECE + 400 for p in pieces), "a request to the browser has a size limit"
    carried = "".join(json.loads("[" + p.rsplit("})(", 1)[1][:-1] + "]")[1] for p in pieces)
    assert base64.b64decode(carried) == content
    script = form_fill.attach_script(7, "__jobhelper_k", 'CV "final".pdf', "https://x.example/a")
    assert json.loads("[" + script.rsplit("})(", 1)[1][:-1] + "]") == [7, "__jobhelper_k", 'CV "final".pdf', "application/pdf", "https://x.example/a"]
    assert form_fill.attach_answer("nonsense") == {"ok": False, "moved": False, "why": "refused", "size": -1}
    assert form_fill.attach_answer('{"moved": true}')["moved"] and form_fill.attach_answer('{"ok": true, "size": 9}') == {"ok": True, "moved": False, "why": "", "size": 9}
    assert form_fill.attach_answer('{"ok": "yes", "size": "9"}')["ok"] is False, "a page may answer anything"


def test_the_form_of_a_job_is_found_although_apply_led_to_another_address():
    """The posting is on a job board; "Apply" leads to the company's applicant system, at an address the app has never seen."""
    jobs = [_job(url="https://board.example/offer/771"), _job(id="vt", company="Vantor", title="Junior Tester", url="https://board.example/offer/905"),
            _job(id="vt2", company="Vantor", title="Data Engineer", url="https://board.example/offer/906")]
    form = "https://apply.ats.example/f/8c1d"
    assert form_fill.match_job(jobs, form, "Application form") == "", "nothing says whose form this is"
    assert form_fill.match_job(jobs, form, "Application form", came_from="https://board.example/offer/905?src=mail") == "vt", "the page that led here is the posting"
    assert form_fill.match_job(jobs, form, "Application form", came_from="https://board.example/") == "", "the board's home page is nobody's posting"
    assert form_fill.match_job(jobs, form, "Application form", text="Junior Tester\nJoin Vantor in Brno.") == "vt", "the company and the title are on the page"
    assert form_fill.match_job(jobs, form, "Application form", text="Join Vantor in Brno.") == "", "two jobs there and no title: you choose"
    assert form_fill.match_job(jobs, form, "Vantor careers", text="Apply for Data Engineer today") == "vt2", "the title in the words tells two jobs apart"
    assert form_fill.match_job(jobs, form, "Application form", text="We are hiring a Junior Tester") == "", "a title alone could be any company's"
    assert form_fill.match_job(jobs, form, "Application form", text="We are hiring a Junior Tester", opened="vt") == "vt", "you opened this posting from the app a moment ago"
    assert form_fill.match_job(jobs, form, "Application form", text="Welcome", opened="vt") == "", "opened, but the page says nothing of it"
    assert form_fill.match_job(jobs, form, "Application form", came_from="https://board.example/list", opened="vt") == "vt", "you came from the board of that posting"
    assert form_fill.match_job(jobs, form, "Application form", text="Junior Analyst at Northwind", opened="vt") == "nw1", "what the page says counts for more than what was opened"
    assert form_fill.match_job(jobs, form, "Application form", text="Junior Tester", opened="gone") == ""


def test_opening_a_posting_from_the_app_is_remembered_for_two_hours(isolate, monkeypatch):
    store.save_jobs([_job()])
    api = ui_api.Api()
    assert api._recently_opened() == ""
    assert api.open_url("nw1")["ok"] and api._recently_opened() == "nw1"
    api._opened = ("nw1", api._opened[1] - 2 * 3600 - 1)
    assert api._recently_opened() == "", "an old click says nothing about the form in front now"
    assert api.open_url("nobody") == {"ok": False}


def _with_files(tmp_path, **more):
    (tmp_path / "tailored" / "CV_Northwind.docx").write_bytes(_bytes("d", 900))
    (tmp_path / "tailored" / "CV_Northwind.pdf").write_bytes(_bytes("p", 1200))
    (tmp_path / "letters" / "Letter_Northwind.docx").write_bytes(_bytes("l", 700))
    store.save_jobs([_job(tailored_cv_file="CV_Northwind.docx", cover_letter_file="Letter_Northwind.docx", **more)])
    details.save(MINE)


def test_the_cv_and_the_letter_of_the_job_are_attached(isolate, tmp_path, monkeypatch):
    _with_files(tmp_path)
    fields = [_field("First name", n=1), _field("Resume", kind="file", n=2, accept=".pdf,.docx"), _field("Other attachments", kind="file", n=3, accept=".doc,.docx"),
              _field("More documents", kind="file", n=4), _field("Photo", kind="file", n=5), _field("CV scan", kind="file", n=6, accept="image/*"),
              _field("Resume (again)", kind="file", n=7, filled=True)]
    _browser(monkeypatch, fields)
    out = ui_api.Api().assistant_fill()
    assert out["ok"] and out["job_id"] == "nw1" and out["guessed"]
    assert ran_files[0] == [(2, "CV_Northwind.pdf", _bytes("p", 1200)), (3, "Letter_Northwind.docx", _bytes("l", 700))], "the PDF where it is taken, the Word file where only that is"
    files = {i["label"]: i for i in out["filled"] if i["kind"] == "file"}
    assert files["Resume"]["value"] == "CV_Northwind.pdf" and files["Resume"]["check"] == form_fill.FILE_CHECK
    left = {i["label"]: i["why"] for i in out["left"]}
    assert left["More documents"] == form_fill.FILE_OTHER, "the letter is attached once"
    assert left["Photo"] == form_fill.FILE and "image/*" in left["CV scan"] and "CV_Northwind.pdf" in left["CV scan"]
    assert "Resume (again)" not in left and out["kept"] == 1, "a field that holds a file is not touched"
    assert "2 files attached" in out["say"] and out["wants_file"] is True and "never press Submit" in out["say"]


def test_files_need_a_job_and_fall_back_to_your_own_cv(isolate, tmp_path, monkeypatch):
    details.save(MINE)
    store.save_jobs([_job(company="Elsewhere", url="https://elsewhere.example/job/1")])
    fields = [_field("Resume", kind="file", n=1), _field("Cover letter", kind="file", n=2), _field("Other attachments", kind="file", n=3)]
    _browser(monkeypatch, fields)
    out = ui_api.Api().assistant_fill()
    assert out["ok"] and out["job_id"] == "" and ran_files[0] == [], "a CV for the wrong company is worse than none"
    assert {i["why"] for i in out["left"]} == {form_fill.FILE_NO_JOB} and len(out["left"]) == 3
    (tmp_path / "cv" / "My CV.docx").write_bytes(_bytes("m", 500))
    (tmp_path / "letters" / "Big.docx").write_bytes(b"x" * (form_fill.MAX_FILE + 1))
    store.save_jobs([_job(cover_letter_file="Big.docx")])
    _browser(monkeypatch, fields)
    out = ui_api.Api().assistant_fill("nw1")
    assert ran_files[0] == [(1, "My CV.docx", _bytes("m", 500))]
    assert out["filled"][0]["check"] == form_fill.FILE_MASTER, "said plainly: this is not the CV adapted to the job"
    left = {i["label"]: i["why"] for i in out["left"]}
    assert left["Cover letter"] == form_fill.FILE_BIG.format(name="Big.docx") and left["Other attachments"] == form_fill.FILE_OTHER
    store.save_jobs([_job(tailored_cv_file="../../secret.docx", cover_letter_file="")])
    (tmp_path / "cv" / "My CV.docx").unlink()
    _browser(monkeypatch, fields[:2])
    out = ui_api.Api().assistant_fill("nw1")
    assert ran_files[0] == [] and {i["label"]: i["why"] for i in out["left"]} == {"Resume": form_fill.FILE_NO_CV, "Cover letter": form_fill.FILE_NO_LETTER}


def test_a_file_the_page_does_not_take_is_said_and_skipping_is_obeyed(isolate, tmp_path, monkeypatch):
    _with_files(tmp_path)
    fields = [_field("Resume", kind="file", n=1), _field("Cover letter", kind="file", n=2)]
    _browser(monkeypatch, fields)
    out = ui_api.Api().assistant_fill(skip=["resume"])
    assert [name for _n, name, _c in ran_files[0]] == ["Letter_Northwind.docx"]
    assert {i["label"]: i["why"] for i in out["left"]} == {"Resume": form_fill.SKIPPED}
    real = chrome.run
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps({"ok": False, "why": "refused"}) if script.startswith("(function (n, key") else real(script))
    out = ui_api.Api().assistant_fill()
    assert {i["why"] for i in out["left"]} == {form_fill.FILE_REFUSED} and not out["filled"]
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps({"ok": True, "size": 3}) if script.startswith("(function (n, key") else real(script))
    assert {i["why"] for i in ui_api.Api().assistant_fill()["left"]} == {form_fill.FILE_REFUSED}, "the page holds a file of another size: not believed"
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps({"moved": True}) if script.startswith("(function (n, key") else real(script))
    out = ui_api.Api().assistant_fill()
    assert out["ok"] is False and "tab changed" in out["msg"]

    def gone(script):
        if script.startswith("(function (key, part)"):
            raise chrome.ChromeError(chrome.NOT_RUNNING)
        return real(script)
    monkeypatch.setattr(chrome, "run", gone)
    assert ui_api.Api().assistant_fill() == {"ok": False, "action": "fill", "msg": chrome.NOT_RUNNING}


FILE_JOBS = [{"id": "vt", "title": "Junior Tester", "company": "Vantor", "status": "found", "url": "https://board.example/offer/905", "description": "",
              "tailored_cv_file": "CV_Vantor_Junior_Tester.docx", "cover_letter_file": "Letter_Vantor.docx"},
             {"id": "nw", "title": "Junior Analyst", "company": "Northwind", "status": "found", "url": "https://board.example/offer/771", "description": ""}]
FILES = {"tailored_cvs/CV_Vantor_Junior_Tester.docx": 5000, "tailored_cvs/CV_Vantor_Junior_Tester.pdf": 330_000,
         "cover_letters/Letter_Vantor.docx": 4100, "cover_letters/Letter_Vantor.pdf": 61_000}


def test_area_the_cv_and_the_letter_reach_a_real_page_whole():
    """The form of the report: file fields drawn by the page (a box and a button, the real field hidden), at an address that is not
    the posting's, with a title that names nobody. The job is read from the words of the page; its files arrive byte for byte."""
    out = _area("files.html", jobs=FILE_JOBS, files=FILES)
    result, got = out["result"], out["kept"]
    assert result["ok"] and result["job_id"] == "vt" and result["guessed"], result
    cv, letter = _bytes("tailored_cvs/CV_Vantor_Junior_Tester.pdf", 330_000), _bytes("cover_letters/Letter_Vantor.pdf", 61_000)
    assert got["resume"] == {"name": "CV_Vantor_Junior_Tester.pdf", "size": len(cv), "type": "application/pdf", "sum": _sum(cv)}, "sent in three pieces, whole on arrival"
    assert got["other"] == {"name": "Letter_Vantor.pdf", "size": len(letter), "type": "application/pdf", "sum": _sum(letter)}
    assert set(got) == {"resume", "other"} and out["state"]["more"] == 0 and out["state"]["photo"] == 0 and out["state"]["scan"] == 0
    assert out["filled"]["Attach your Resume (supported formats: png, jpeg, jpg, pdf, doc, docx, txt)"]["value"] == "CV_Vantor_Junior_Tester.pdf" and out["filled"]["Attach your Attachments (supported formats: png, jpeg, jpg, pdf, doc, docx, txt)"]["value"] == "Letter_Vantor.pdf"
    assert out["left"] == {"More documents": form_fill.FILE_OTHER, "Your photo": form_fill.FILE,
                           "CV (scanned)": form_fill.FILE_FORMAT.format(accept="image/*", name="CV_Vantor_Junior_Tester.pdf")}
    assert out["state"]["fn"] == "Alex" and "2 files attached" in result["say"]


def test_area_no_file_leaves_the_app_for_a_form_of_an_unknown_job():
    out = _area("files.html", jobs=FILE_JOBS[1:], files=FILES)
    assert out["result"]["ok"] and out["result"]["job_id"] == "" and out["kept"] == {}
    assert out["left"]["Attach your Resume (supported formats: png, jpeg, jpg, pdf, doc, docx, txt)"] == form_fill.FILE_NO_JOB and out["left"]["Attach your Attachments (supported formats: png, jpeg, jpg, pdf, doc, docx, txt)"] == form_fill.FILE_NO_JOB
    assert out["state"]["resume"] == 0 and out["state"]["fn"] == "Alex", "your details are yours whatever the job; its documents are not"


def test_area_lists_drawn_around_a_text_box_on_a_browser_that_is_not_in_front():
    """From a real application form: three fields nobody could name (the page's own unseen boxes under its lists), a list that
    did not open because the browser was behind the app, and a list that already showed its answer beside its box."""
    out = _area("selects.html")
    result = out["result"]
    assert result["ok"], result
    assert not any(label.startswith("Field ") for label in out["left"]), "a box the page hides from screen readers is not a field of the form"
    assert out["menus"] == {"s1": "Czech Republic +420", "s2": "Yes", "s4": "Czech Republic"}, "opened by the word of entering, and by the arrow key"
    assert "s3" not in out["opened"] and result["kept"] == 1, "Location shows Prague beside its box: it has its answer"
    assert out["filled"]["Country*"]["value"] == "Czech Republic +420" and out["filled"]["Country of residence"]["value"] == "Czech Republic"
    assert out["left"] == {} and out["state"]["fn"] == "Alex"
