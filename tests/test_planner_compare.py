"""Dates to remember, notes per company, the CV comparison, stated pay,
the wider mailbox scan and replies pasted in by hand."""
import imaplib
import re
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage

import docx
import pytest

from jobhelper import (agent5_responses, compare, config, db, email_client, insights, llm, planner, salary, store,
                       ui_api, vault)

TODAY = date(2026, 10, 7)


def _job(id="a", **kw):
    kw.setdefault("status", "waiting")
    extra = {k: kw.pop(k) for k in ("event", "event_notified") if k in kw}     # set by the app, not part of a new job
    job = store.new_job(id=id, title=kw.pop("title", "Junior Developer"), company=kw.pop("company", "Acme"), **kw)
    job.update(extra)
    return job


# ── dates to remember ───────────────────────────────────────────────────────
@pytest.mark.parametrize("day, time, kind, problem", [
    ("2026-10-15", "", "interview", ""), ("2026-10-15", "14:30", "deadline", ""), ("2026-10-07", "", "call", ""),
    ("15.10.2026", "", "interview", "YYYY-MM-DD"), ("", "", "interview", "YYYY-MM-DD"),
    ("2026-09-01", "", "interview", "already passed"), ("2026-10-06", "", "interview", "already passed"), ("2030-01-01", "", "interview", "two years"),
    ("2026-10-15", "2pm", "interview", "HH:MM"), ("2026-10-15", "25:00", "interview", "HH:MM"),
    ("2026-10-15", "", "party", "kind"),
])
def test_check_event(day, time, kind, problem):
    iso, said = planner.check_event(day, time, kind, today=TODAY)
    if problem:
        assert iso == "" and problem in said
    else:
        assert iso == day and said == ""


@pytest.mark.parametrize("day, time, kind, note, field", [
    ("15.10.2026", "", "interview", "", "date"), ("2026-09-01", "", "interview", "", "date"), ("2030-01-01", "", "interview", "", "date"),
    ("2026-10-15", "25:00", "interview", "", "time"), ("2026-10-15", "", "party", "", "kind"), ("2026-10-15", "", "call", "x" * 201, "note"),
    ("2026-10-15", "14:30", "call", "x" * 200, ""),
])
def test_an_event_refusal_names_the_field_it_is_about(day, time, kind, note, field):
    """The window marks only that field red: a wrong time once made the date red and left the time box plain."""
    check = planner.EventCheck(day, time, kind, note, today=TODAY)
    assert check.field == field and check.ok is (field == "")
    assert check.answer() == ({"ok": True} if field == "" else {"ok": False, "msg": check.problem, "field": field})
    job = {}
    assert check.put_on(job) is check and ("event" in job) is check.ok, "a refused date is never saved"


def test_set_and_clear_event():
    job = _job(event_notified="2026-10-01:1")
    day = (date.today() + timedelta(days=3)).isoformat()
    assert "300 characters long; the most is 200" in planner.set_event(job, day, "09:00", "test task", "x" * 300)     # refused, not cut
    assert "event" not in job
    assert planner.set_event(job, day, " 09:00 ", "test task", "  " + "x" * 200) == ""
    assert job["event"] == {"date": day, "time": "09:00", "kind": "test task", "note": "x" * 200}
    assert "event_notified" not in job                                # a new date is announced again
    assert "YYYY-MM-DD" in planner.set_event(job, "soon") and job["event"]["date"] == day   # a bad date changes nothing
    planner.clear_event(job)
    assert "event" not in job


def test_upcoming_is_sorted_and_skips_the_past():
    def on(id, days, time=""):
        return _job(id, event={"date": (TODAY + timedelta(days=days)).isoformat(), "time": time, "kind": "interview", "note": ""})
    jobs = [on("later", 5), on("past", -1), on("noon", 1, "12:00"), on("morning", 1, "09:00"), on("allday", 1),
            on("now", 0), _job("none"), _job("broken", event={"date": "soon"})]
    got = planner.upcoming(jobs, TODAY)
    assert [g["id"] for g in got] == ["now", "morning", "noon", "allday", "later"]
    assert [g["label"] for g in got] == ["today", "tomorrow", "tomorrow", "tomorrow", "in 5 days"]
    assert len(planner.upcoming(jobs, TODAY, limit=2)) == 2
    jobs[0]["status"] = "rejected"                                    # a closed application is not announced
    assert "later" not in [g["id"] for g in planner.upcoming(jobs, TODAY)]


def test_a_date_with_a_time_leaves_an_hour_after_it_started():
    """A 13:30 interview still showed under "Coming up" at 18:52: only the date was compared, never the time."""
    jobs = [_job("talk", event={"date": TODAY.isoformat(), "time": "13:30", "kind": "interview", "note": ""}),
            _job("allday", event={"date": TODAY.isoformat(), "time": "", "kind": "deadline", "note": ""}),
            _job("next", event={"date": (TODAY + timedelta(days=1)).isoformat(), "time": "09:00", "kind": "call", "note": ""})]

    def shown(hour, minute):
        return [g["id"] for g in planner.upcoming(jobs, now=datetime.combine(TODAY, time(hour, minute)))]
    assert shown(13, 0) == ["talk", "allday", "next"]
    assert shown(14, 29) == ["talk", "allday", "next"]               # its first hour: it may be going on
    assert shown(14, 30) == ["allday", "next"] == shown(18, 52)
    assert shown(23, 59) == ["allday", "next"]                         # without a time it lasts the whole day
    assert [g["id"] for g in planner.upcoming(jobs, TODAY)] == ["talk", "allday", "next"]   # asked about the whole day
    assert planner.has_passed({"date": TODAY.isoformat(), "time": "bad"}, datetime.combine(TODAY, time(23, 0))) is False


def test_no_reminder_for_a_date_that_is_already_over():
    jobs = [_job("talk", event={"date": TODAY.isoformat(), "time": "09:00", "kind": "interview", "note": ""})]
    assert planner.due_reminders(jobs, now=datetime.combine(TODAY, time(18, 0))) == []
    assert [d["id"] for d in planner.due_reminders(jobs, now=datetime.combine(TODAY, time(7, 0)))] == ["talk"]


def test_reminders_once_the_day_before_and_once_on_the_day():
    jobs = [_job("a", event={"date": "2026-10-08", "time": "14:30", "kind": "interview", "note": ""}),
            _job("far", event={"date": "2026-10-20", "time": "", "kind": "deadline", "note": ""})]
    first = planner.due_reminders(jobs, TODAY)
    assert [d["id"] for d in first] == ["a"]
    assert planner.reminder_text(first[0]) == "Tomorrow at 14:30: interview · Acme"
    assert planner.due_reminders(jobs, TODAY) == []                   # not twice on one day
    again = planner.due_reminders(jobs, TODAY + timedelta(days=1))
    assert [d["label"] for d in again] == ["today"]
    assert planner.due_reminders(jobs, TODAY + timedelta(days=1)) == []
    assert planner.due_reminders(jobs, TODAY + timedelta(days=2)) == []   # over


# ── notes per company ───────────────────────────────────────────────────────
def test_company_notes_are_shared_by_spelling_and_encrypted(isolate_data):
    assert planner.company_notes("Valeo")["contact"] == ""
    assert planner.save_company_notes("Valeo s.r.o.", {"contact": " Jana, HR ", "salary": "55k", "unknown": "x"}) is True
    got = planner.company_notes("VALEO")
    assert (got["contact"], got["salary"], got["asked"], got["updated"]) == ("Jana, HR", "55k", "", date.today().isoformat())
    raw = (isolate_data / "company_notes.json").read_bytes()
    assert raw.startswith(b"JHENC1\n") and b"Jana" not in raw
    assert planner.save_company_notes("Valeo", {"contact": "", "salary": " "}) is True       # emptied: entry removed
    assert planner.company_notes("Valeo")["updated"] == ""
    assert planner.save_company_notes("", {"notes": "x"}) is False
    assert planner.save_company_notes("unknown", {"notes": "x"}) is False


# ── CV comparison ───────────────────────────────────────────────────────────
def _docx(path, paragraphs):
    d = docx.Document()
    for p in paragraphs:
        d.add_paragraph(p)
    d.save(str(path))
    return path


def test_compare_marks_changed_added_and_removed(tmp_path):
    master = _docx(tmp_path / "m.docx", ["Alex Novak", "P R O F I L E", "Junior developer with Python & SQL.",
                                         "K E Y   S K I L L S", "Python, SQL", "Old line", "EDUCATION", "Some University"])
    adapted = _docx(tmp_path / "a.docx", ["Alex Novak", "P R O F I L E", "Junior developer with Python & Docker.",
                                          "K E Y   S K I L L S", "Python, SQL", "EDUCATION", "Some University", "New closing line"])
    got = compare.compare(master, adapted)
    assert (got["changed"], got["added"], got["removed"], got["same"]) == (1, 1, 1, 6)
    changed, removed, added = got["rows"]
    assert changed["section"] == "Profile" and changed["state"] == "changed"
    assert changed["master"] == "Junior developer with Python &amp; <s>SQL</s>."
    assert changed["adapted"] == "Junior developer with Python &amp; <b>Docker</b>."
    assert removed == {"section": "Key Skills", "state": "removed", "master": "<s>Old line</s>", "adapted": ""}
    assert added["state"] == "added" and added["adapted"] == "<b>New closing line</b>" and added["master"] == ""


def test_compare_identical_files(tmp_path):
    a = _docx(tmp_path / "a.docx", ["One", "Two"])
    assert compare.compare(a, a) == {"rows": [], "same": 2, "changed": 0, "added": 0, "removed": 0}


# ── what a posting pays ─────────────────────────────────────────────────────
@pytest.mark.parametrize("job, low, high", [
    ({"salary": "45 000 - 60 000 Kč"}, 45000, 60000),
    ({"salary": "CZK 50,000 per month"}, 50000, 50000),
    ({"description": "We offer 2 000 - 2 400 EUR monthly."}, 50000, 60000),
    ({"description": "Salary 720 000 CZK per year."}, 60000, 60000),
    ({"description": "Salary: 600000 CZK"}, 50000, 50000),                         # too large to be monthly
])
def test_stated_pay(job, low, high):
    got = salary.stated(job)
    assert got and (got["low"], got["high"]) == (low, high) and got["text"]


@pytest.mark.parametrize("job", [
    {}, {"description": "Founded in 2015, we have 12 000 employees."}, {"description": "Call +420 777 123 456."},
    {"salary": "competitive"}, {"description": "Bonus of 5 000 CZK."},
])
def test_no_pay_stated(job):
    assert salary.stated(job) is None


def test_salary_overview_compares_with_the_target():
    jobs = [_job("hi", status="found", salary="70 000 - 80 000 CZK", desired_monthly_czk=60000, match_score=40),
            _job("mid", status="found", salary="55 000 - 65 000 CZK", desired_monthly_czk=60000, match_score=90),
            _job("lo", salary="40 000 CZK", desired_monthly_czk="60000", match_score=None),
            _job("no_target", status="found", salary="50 000 CZK"),
            _job("silent", status="found"),
            _job("gone", status=store.NOT_INTERESTED, salary="90 000 CZK")]
    got = insights.salaries(jobs)
    assert [r["id"] for r in got["rows"]][0] == "mid"                              # best score first
    by = {r["id"]: r["verdict"] for r in got["rows"]}
    assert by == {"hi": "above your target", "mid": "around your target", "lo": "below your target", "no_target": ""}
    assert (got["stated"], got["postings"], got["lowest"], got["highest"]) == (4, 5, 40000, 80000)
    assert got["median"] == 60000
    assert insights.salaries([])["median"] == 0


# ── scanning more than the Inbox ────────────────────────────────────────────
def _raw(msg_id, sender="hr@acme.com", subject="Your application"):
    m = EmailMessage()
    m["Message-ID"], m["From"], m["Subject"], m["Date"] = msg_id, sender, subject, "Wed, 07 Oct 2026 10:00:00 +0200"
    m.set_content("Thank you for applying.")
    return m.as_bytes()


LISTING = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\All \\HasNoChildren) "/" "[Gmail]/All Mail"',
           b'(\\HasNoChildren \\Junk) "/" "[Gmail]/Spam"', b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"']


class FakeImap:
    """A mailbox with three folders; records what was done to it (and the time limit it was given)."""
    boxes = {}
    listing = []
    gm_raw = True
    broken = ()
    log = []

    def __init__(self, *a, timeout=None, ssl_context=None):
        self.folder = None

    def login(self, user, password):
        FakeImap.log.append(("login", user))

    def list(self):
        return "OK", self.listing

    def select(self, folder, readonly=False):
        FakeImap.log.append(("select", folder, readonly))
        folder = folder.strip('"')                     # names with spaces arrive quoted, as the server needs them
        if folder in self.broken:
            raise imaplib.IMAP4.error("no such folder")
        self.folder = folder
        return "OK", [b"1"]

    def search(self, charset, *criteria):
        FakeImap.log.append(("search", self.folder) + criteria)
        if criteria[0] == "X-GM-RAW" and not self.gm_raw:
            raise imaplib.IMAP4.error("unknown search key")
        return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self.boxes.get(self.folder, []))))]

    def fetch(self, num, what):
        FakeImap.log.append(("fetch", what))
        return "OK", [(b"x", self.boxes[self.folder][int(num) - 1])]

    def logout(self):
        FakeImap.log.append(("logout",))

    def __getattr__(self, name):                       # store, copy, expunge, append, delete …
        raise AssertionError(f"the scan must be read-only, but called imap.{name}")


@pytest.fixture
def imap(monkeypatch):
    FakeImap.log, FakeImap.gm_raw, FakeImap.broken = [], True, ()
    FakeImap.listing = list(LISTING)
    FakeImap.boxes = {
        "INBOX": [_raw("<1>"), _raw("<self>", sender="Me <me@example.com>")],
        "[Gmail]/All Mail": [_raw("<1>"), _raw("<arch>"), _raw("<sent>", sender="me@example.com")],
        "[Gmail]/Spam": [_raw("<spam>")],
    }
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeImap)
    return FakeImap


def test_inbox_only_by_default(imap):
    got = email_client.read_mailbox("me@example.com", "pw", "07-Sep-2026").messages
    assert [(m["msg_id"], m["folder"]) for m in got] == [("<self>", "inbox"), ("<1>", "inbox")]
    assert [e[1] for e in imap.log if e[0] == "select"] == ["INBOX"]


def test_all_folders_adds_archive_and_spam_read_only(imap):
    got = email_client.read_mailbox("me@example.com", "pw", "07-Sep-2026", all_folders=True).messages
    assert [(m["msg_id"], m["folder"]) for m in got] == [("<self>", "inbox"), ("<1>", "inbox"), ("<arch>", "archive"), ("<spam>", "spam")]
    selects = [e for e in imap.log if e[0] == "select"]
    assert [s[1].strip('"') for s in selects] == ["INBOX", "[Gmail]/All Mail", "[Gmail]/Spam"] and all(s[2] is True for s in selects)
    assert all(e[1] == "(BODY.PEEK[])" for e in imap.log if e[0] == "fetch")       # never marks mail as read
    raw = next(e for e in imap.log if e[0] == "search" and e[2] == "X-GM-RAW")
    assert raw[3] == '"-in:inbox -in:sent -in:drafts -in:chats after:2026/09/07"'
    assert imap.log[-1] == ("logout",) and all(m["mailbox"] == "me@example.com" for m in got)


def test_other_providers_fall_back_to_a_plain_date_search(imap):
    imap.gm_raw = False
    got = email_client.read_mailbox("me@example.com", "pw", "07-Sep-2026", all_folders=True).messages
    assert "<arch>" in [m["msg_id"] for m in got]
    assert ("search", "[Gmail]/All Mail", '(SINCE "07-Sep-2026")') in imap.log


def test_a_folder_that_cannot_be_opened_is_a_warning_not_an_error(imap):
    imap.broken = ("[Gmail]/Spam",)
    got = email_client.read_mailbox("me@example.com", "pw", "07-Sep-2026", all_folders=True)
    assert "<arch>" in [m["msg_id"] for m in got.messages] and "<spam>" not in [m["msg_id"] for m in got.messages]
    assert got.warnings == ("The spam folder of me@example.com could not be read.",)
    assert email_client.read_mailbox("me@example.com", "pw", "07-Sep-2026", all_folders=True).warnings == got.warnings, \
        "each read has its own warnings: they do not pile up from one scan to the next"


def test_folders_are_found_by_flag_in_any_language(imap):
    imap.listing = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\All) "/" "[Gmail]/V&AWE-echny zpr&AOE-vy"', b'(\\Junk) "/" "[Gmail]/Spam"']
    with email_client.Mailbox("me@example.com", "pw") as box:
        assert box.folders() == {"archive": '"[Gmail]/V&AWE-echny zpr&AOE-vy"', "spam": '"[Gmail]/Spam"'}

    class NoList:
        def login(self, user, password):
            pass

        def list(self):
            raise OSError("down")

        def logout(self):
            pass
    with email_client.Mailbox("me@example.com", "pw", connect=NoList) as box:
        assert box.folders() == {}


def test_the_mailbox_only_ever_reads_and_always_signs_out(imap):
    """The exact commands: sign in, open read-only, search, read with PEEK, list folders, sign out. Nothing else."""
    with email_client.Mailbox("me@example.com", "pw") as box:
        box.recent("07-Sep-2026", all_folders=True)
    assert {e[0] for e in imap.log} <= {"login", "select", "search", "fetch", "list", "logout"}
    assert all(e[2] is True for e in imap.log if e[0] == "select") and imap.log[-1] == ("logout",)
    assert not [name for name in vars(email_client.Mailbox) if re.search(r"store|copy|move|expunge|append|delete|flag", name)]
    imap.log.clear()
    with pytest.raises(RuntimeError):
        with email_client.Mailbox("me@example.com", "pw") as box:
            raise RuntimeError("something failed while reading")
    assert imap.log[-1] == ("logout",)                                  # signed out after an error too


def test_the_option_decides_whether_other_folders_are_read(imap, monkeypatch):
    monkeypatch.setattr(config, "mailboxes", lambda: [{"user": "me@example.com", "password": "pw"}])
    monkeypatch.setattr(config, "ui_settings", lambda: {"scan_all_folders": True})
    assert len(email_client.fetch_recent(30).messages) == 4
    monkeypatch.setattr(config, "ui_settings", lambda: {})
    assert len(email_client.fetch_recent(30).messages) == 2
    assert len(email_client.fetch_recent(30, all_folders=True).messages) == 4


# ── a reply pasted in by hand ───────────────────────────────────────────────
@pytest.mark.parametrize("text, stage", [
    ("Unfortunately we have decided not to move forward with your application.", "rejection"),
    ("We would like to invite you to an interview next week.", "interview"),
    ("Please complete the coding challenge on Codility.", "assessment"),
    ("We are pleased to offer you the position.", "offer"),
    ("Thank you for applying, we will review your profile.", "acknowledged"),
    ("Hello, how are you doing these days?", "other"),
])
def test_rules_read_a_reply_without_claude(text, stage):
    assert agent5_responses.classify_by_rules(text)["stage"] == stage


def test_pasted_reply_is_filed_and_moves_the_application(isolate_data, monkeypatch):
    asked = []
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **kw: asked.append(prompt) or
                        {"is_response": True, "stage": "interview", "summary": "Invited to a call", "company": "Acme"})
    jobs = [_job("a")]
    text = "Hi, we liked your profile and want to talk on Thursday.\nBest, Jana"
    got = agent5_responses.add_pasted_reply(jobs, "a", text)
    assert got == {"ok": True, "stage": "interview", "by_rules": False, "status": "interview", "summary": "Invited to a call"}
    assert len(asked) == 1 and "want to talk on Thursday" in asked[0]
    row = db.all_responses()[0]
    assert row["job_id"] == "a" and row["stage"] == "interview" and row["from_addr"] == "added by hand"
    assert row["msg_id"].startswith("pasted-") and db.is_seen(row["msg_id"])
    again = agent5_responses.add_pasted_reply(jobs, "a", text)
    assert again["ok"] is False and "already added" in again["msg"] and len(asked) == 1   # no second call


def test_pasted_reply_uses_the_rules_when_the_limit_is_reached(isolate_data, monkeypatch):
    def limit(*a, **kw):
        raise llm.LimitReached("limit")
    monkeypatch.setattr(llm, "ask_json", limit)
    jobs = [_job("a")]
    got = agent5_responses.add_pasted_reply(jobs, "a", "Unfortunately we have decided to proceed with other candidates.")
    assert (got["ok"], got["stage"], got["by_rules"], got["status"]) == (True, "rejection", True, "rejected")


def test_pasted_reply_survives_an_unusable_answer_and_refuses_bad_input(isolate_data, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **kw: ["not", "a", "dict"])
    jobs = [_job("a")]
    got = agent5_responses.add_pasted_reply(jobs, "a", "Thank you for applying, we will review your documents soon.")
    assert got["ok"] and got["by_rules"] and got["stage"] == "acknowledged" and jobs[0]["status"] == "waiting"
    assert "too short" in agent5_responses.add_pasted_reply(jobs, "a", "ok thanks")["msg"]
    assert "not in the list" in agent5_responses.add_pasted_reply(jobs, "zzz", "x" * 40)["msg"]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **kw: pytest.fail("must not ask Claude"))
    assert agent5_responses.add_pasted_reply(jobs, "a", "We invite you to an interview on Monday morning.", use_model=False)["stage"] == "interview"


# ── through the app ─────────────────────────────────────────────────────────
@pytest.fixture
def api(isolate_data):
    config.ensure_dirs()
    return ui_api.Api()


def test_api_events_show_up_and_are_announced_once(api):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    store.save_jobs([_job("a"), _job("b", company="Beta")])
    assert api.set_event("a", "nonsense")["ok"] is False and api.upcoming() == []
    assert api.set_event("a", tomorrow, "9.30")["field"] == "time" and api.upcoming() == []
    assert api.set_event("a", tomorrow, "10:00", "interview", "Teams")["ok"] is True
    assert api.set_event("zzz", tomorrow)["ok"] is False
    assert [(u["id"], u["label"], u["time"]) for u in api.upcoming(4)] == [("a", "tomorrow", "10:00")]
    assert api.job_detail("a")["event"]["note"] == "Teams"
    api.live = [dict(j) for j in store.load_jobs()]                    # a run is going on
    assert [d["id"] for d in api.due_reminders()] == ["a"]
    assert store.find(api.live, "a")["event_notified"] == store.find(store.load_jobs(), "a")["event_notified"]
    assert api.due_reminders() == []
    api.live = None
    assert api.clear_event("a")["ok"] is True and api.upcoming() == [] and not api.job_detail("a").get("event")


def test_api_company_notes_follow_the_company(api):
    store.save_jobs([_job("a", company="Valeo s.r.o."), _job("b", company="Valeo", status="found")])
    assert api.save_company_notes("Valeo s.r.o.", {"contact": "Jana", "asked": "SQL joins"}) == {"ok": True}
    assert api.job_detail("b")["company_notes"]["asked"] == "SQL joins"           # the other job at the same company
    assert api.save_company_notes("", {"contact": "x"})["ok"] is False


def test_api_add_reply_updates_trackers_and_a_running_list(api, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **kw: {"stage": "rejection", "rejection_category": "other_candidate"})
    store.save_jobs([_job("a")])
    api.live = [dict(j) for j in store.load_jobs()]
    got = api.add_reply("a", "Thanks for your time, but we have chosen another candidate for this role.")
    assert got["ok"] and got["stage"] == "rejection"
    assert store.find(store.load_jobs(), "a")["status"] == "rejected" == store.find(api.live, "a")["status"]
    assert config.EXCEL_PATH.exists()
    assert api.add_reply("a", "short")["ok"] is False


def test_api_cv_compare_and_pay_in_the_job_window(api, monkeypatch, tmp_path):
    from jobhelper import agent1_cv
    master = _docx(tmp_path / "master.docx", ["Alex Novak", "PROFILE", "I know Python."])
    _docx(config.TAILORED_CV_DIR / "cv_a.docx", ["Alex Novak", "PROFILE", "I know Python and SQL."])
    monkeypatch.setattr(agent1_cv, "find_cv", lambda: master)
    store.save_jobs([_job("a", status="found", tailored_cv_file="cv_a.docx", salary="50 000 - 60 000 CZK"),
                     _job("pdf", status="found", tailored_cv_file="cv_a.pdf"), _job("none", status="found")])
    detail = api.job_detail("a")
    assert detail["can_compare"] is True and detail["pay"]["low"] == 50000
    assert api.job_detail("pdf")["can_compare"] is False and not api.job_detail("none")["pay"]
    got = api.cv_compare("a")
    assert got["ok"] and got["changed"] == 1 and got["file"] == "cv_a.docx" and "<b>" in got["rows"][0]["adapted"]
    assert api.cv_compare("none")["ok"] is False and api.cv_compare("zzz")["ok"] is False
    (config.TAILORED_CV_DIR / "cv_a.docx").write_bytes(b"not a docx")
    assert "could not be read" in api.cv_compare("a")["msg"]
    assert api.insights()["salaries"]["stated"] == 1
    assert ui_api.Api().options()["scan_all_folders"] is False


def test_notes_file_unreadable_is_treated_as_empty(isolate_data):
    (isolate_data / "company_notes.json").write_text("{broken")
    assert planner.company_notes("Acme")["notes"] == ""
    assert vault  # imported for the VaultError path used above


def test_compare_ignores_punctuation_next_to_an_unchanged_word(tmp_path):
    master = _docx(tmp_path / "m.docx", ["Python, Kotlin, SQL, C++ and CI/CD"])
    adapted = _docx(tmp_path / "a.docx", ["Python, SQL, C++ and CI/CD pipelines"])
    row = compare.compare(master, adapted)["rows"][0]
    assert row["master"] == "Python<s>, Kotlin</s>, SQL, C++ and CI/CD"
    assert row["adapted"] == "Python, SQL, C++ and CI/CD<b> pipelines</b>"


def test_company_notes_are_part_of_backups_and_key_changes(isolate_data):
    planner.save_company_notes("Acme", {"notes": "x"})
    assert isolate_data / "company_notes.json" in vault.data_files()


def test_add_reply_keeps_an_edit_made_while_claude_was_reading(api, monkeypatch):
    """The call takes seconds; a change saved meanwhile must not be overwritten by the older copy."""
    def slow_claude(*a, **kw):
        jobs = store.load_jobs()                                       # meanwhile: a hand edit on another job
        store.find(jobs, "b")["notes"] = "edited during the call"
        store.save_jobs(jobs)
        return {"stage": "interview"}
    monkeypatch.setattr(llm, "ask_json", slow_claude)
    store.save_jobs([_job("a"), _job("b", company="Beta")])
    assert api.add_reply("a", "We would like to invite you to an interview next week, please pick a time.")["ok"]
    saved = store.load_jobs()
    assert store.find(saved, "a")["status"] == "interview" and store.find(saved, "b")["notes"] == "edited during the call"


def test_compare_says_when_the_cv_was_adapted_from_an_earlier_master(api, monkeypatch, tmp_path):
    import os

    from jobhelper import agent1_cv
    master = _docx(tmp_path / "master.docx", ["Alex Novak", "PROFILE", "I know Python."])
    adapted = _docx(config.TAILORED_CV_DIR / "cv_a.docx", ["Alex Novak", "PROFILE", "I know Python and SQL."])
    monkeypatch.setattr(agent1_cv, "find_cv", lambda: master)
    store.save_jobs([_job("a", status="found", tailored_cv_file="cv_a.docx")])
    os.utime(master, (1_000_000, 1_000_000)); os.utime(adapted, (2_000_000, 2_000_000))
    assert api.cv_compare("a")["older_master"] is False                # adapted after the master: nothing to explain
    os.utime(master, (3_000_000, 3_000_000))                           # the master CV was changed later
    assert api.cv_compare("a")["older_master"] is True


# ── reminders by the hour, for a date with a time ───────────────────────────


def _at(hour, minute=0, day=TODAY):
    return datetime(day.year, day.month, day.day, hour, minute)


def test_hour_reminders_three_hours_and_one_hour_before():
    jobs = [_job("a", event={"date": "2026-10-07", "time": "14:30", "kind": "test task", "note": ""})]
    morning = planner.due_reminders(jobs, now=_at(8, 0))
    assert [d["label"] for d in morning] == ["today"] and "minutes" not in morning[0]       # the usual on-the-day reminder
    assert planner.due_reminders(jobs, now=_at(9, 0)) == []
    three = planner.due_reminders(jobs, now=_at(11, 40))                                     # 170 minutes left
    assert [d["minutes"] for d in three] == [170]
    assert planner.reminder_text(three[0]) == "In 2 hours 50 min (14:30): test task · Acme"
    assert planner.due_reminders(jobs, now=_at(12, 30)) == []                                # not again at two hours
    one = planner.due_reminders(jobs, now=_at(13, 35))
    assert planner.reminder_text(one[0]) == "In 55 minutes (14:30): test task · Acme"
    assert planner.due_reminders(jobs, now=_at(14, 0)) == []
    assert planner.due_reminders(jobs, now=_at(15, 0)) == []                                 # it has started: nothing more


def test_first_reminder_of_the_day_inside_the_last_hours_is_one_message():
    jobs = [_job("a", event={"date": "2026-10-07", "time": "10:00", "kind": "interview", "note": ""})]
    got = planner.due_reminders(jobs, now=_at(9, 20))                  # the app was opened 40 minutes before
    assert len(got) == 1 and got[0]["minutes"] == 40
    assert planner.reminder_text(got[0]) == "In 40 minutes (10:00): interview · Acme"
    assert planner.due_reminders(jobs, now=_at(9, 30)) == []


def test_a_date_without_a_time_keeps_the_two_day_reminders_only():
    jobs = [_job("a", event={"date": "2026-10-07", "time": "", "kind": "deadline", "note": ""})]
    assert len(planner.due_reminders(jobs, now=_at(8))) == 1
    assert planner.due_reminders(jobs, now=_at(12)) == [] and planner.due_reminders(jobs, now=_at(23, 30)) == []


def test_old_single_mark_is_understood_and_a_new_date_starts_fresh():
    jobs = [_job("a", event={"date": "2026-10-07", "time": "18:00", "kind": "call", "note": ""}, event_notified="2026-10-07:0")]
    assert planner.due_reminders(jobs, now=_at(8)) == []                                     # already announced by the older version
    assert len(planner.due_reminders(jobs, now=_at(15, 30))) == 1
    day = (date.today() + timedelta(days=2)).isoformat()
    assert planner.set_event(jobs[0], day, "18:00", "call") == "" and "event_marks" not in jobs[0]


@pytest.mark.parametrize("minutes, text", [(1, "In 1 minute"), (45, "In 45 minutes"), (60, "In 1 hour"), (63, "In 1 hour"),
                                           (95, "In 1 hour 35 min"), (180, "In 3 hours")])
def test_time_left_wording(minutes, text):
    assert planner._in(minutes) == text


# ── nothing the user typed is cut silently ──────────────────────────────────
@pytest.mark.parametrize("fields, problem", [
    ({"contact": "c" * 201}, "“Who you spoke to” is 201 characters long; the most is 200."),
    ({"asked": "a" * 401}, "“What they asked” is 401 characters long; the most is 400."),
    ({"notes": "n" * 2001}, "“Notes” is 2001 characters long; the most is 2000."),
    ({"contact": "c" * 200, "notes": "n" * 2000}, ""), ({}, ""), (None, ""),
])
def test_company_notes_over_the_limit_are_refused_with_the_reason(isolate_data, fields, problem):
    assert planner.check_company_notes(fields).startswith(problem) and (problem != "" or planner.check_company_notes(fields) == "")
    if problem:
        assert planner.save_company_notes("Acme", fields) is False and planner.company_notes("Acme")["updated"] == ""


def test_api_says_why_notes_answers_and_a_pasted_reply_were_refused(api, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("must not ask Claude"))
    store.save_jobs([_job("a")])
    got = api.save_company_notes("Acme", {"notes": "n" * 2500})
    assert got["ok"] is False and "2500 characters long; the most is 2000" in got["msg"]
    got = api.save_form_answers("a", [{"question": "Why us?", "answer": "a" * 3001}])
    assert got["ok"] is False and "The answer to “Why us?” is 3001 characters long; the most is 3000" in got["msg"]
    assert api.form_answers("a")["items"] == []                                  # not saved in a cut form
    got = api.add_reply("a", "x" * 8001)
    assert got["ok"] is False and "Paste only the message itself" in got["msg"] and "8001 characters" in got["msg"]
