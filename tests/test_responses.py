"""Agent 5 (response analysis) + SQLite DB tests — mocked email + LLM."""
import pytest

from jobhelper import agent5_responses, db, email_client, llm, store

_REAL_TRY_LOGIN = email_client.try_login


def test_db_upsert_and_dedupe(isolate_data):
    rec = {"msg_id": "<a@x>", "company": "Acme", "stage": "rejection",
           "rejection_category": "experience_insufficient"}
    db.upsert_response(rec)
    db.upsert_response(rec)  # same msg_id → no duplicate
    assert db.total() == 1
    assert db.has_response("<a@x>")
    assert not db.has_response("<z@x>")


def test_db_counts_by(isolate_data):
    db.upsert_response({"msg_id": "1", "stage": "rejection", "rejection_category": "skills_mismatch"})
    db.upsert_response({"msg_id": "2", "stage": "rejection", "rejection_category": "skills_mismatch"})
    db.upsert_response({"msg_id": "3", "stage": "interview", "rejection_category": "no_reason_given"})
    assert db.counts_by("stage") == {"rejection": 2, "interview": 1}


def test_process_inbox_stores_and_updates_status(isolate_data, monkeypatch):
    jobs = [store.new_job(id="jobscz-1", company="Acme", title="Python Dev", status="waiting")]

    monkeypatch.setattr(email_client, "fetch_recent", lambda *a, **k: [
        {"msg_id": "<r1@acme>", "date": "Mon, 01 Sep 2026", "sender": "hr@acme.com",
         "subject": "Your application", "body": "Unfortunately we chose another candidate."},
        {"msg_id": "<n1@news>", "date": "Mon, 01 Sep 2026", "sender": "news@promo.com",
         "subject": "Weekly deals", "body": "Buy now"},
    ])

    def fake_llm(prompt, *a, **k):
        if "another candidate" in prompt:
            return {"is_response": True, "stage": "rejection", "company": "Acme", "role": "Python Dev",
                    "rejection_reason": "chose another candidate",
                    "rejection_category": "went_with_other_candidate",
                    "sentiment": "negative", "next_step": "", "summary": "Rejected: other candidate"}
        return {"is_response": False, "stage": "other", "rejection_category": "no_reason_given"}

    monkeypatch.setattr(llm, "ask_json", fake_llm)

    stats = agent5_responses.process_inbox(jobs)
    assert stats["scanned"] == 2
    assert stats["new_responses"] == 1   # newsletter ignored
    assert stats["rejections"] == 1
    assert jobs[0]["status"] == "rejected"
    assert db.total() == 1


def test_analytics(isolate_data, monkeypatch):
    jobs = [store.new_job(id="a", status="waiting"), store.new_job(id="b", status="rejected"),
            store.new_job(id="c", status="interview")]
    db.upsert_response({"msg_id": "1", "stage": "rejection", "rejection_category": "skills_mismatch"})
    db.upsert_response({"msg_id": "2", "stage": "interview", "rejection_category": "no_reason_given"})

    a = agent5_responses.analytics(jobs)
    assert a["applications_tracked"] == 3
    assert a["response_emails"] == 2
    assert a["by_stage"]["rejection"] == 1
    assert a["rejection_reasons"] == {"skills_mismatch": 1}
    assert a["response_rate"] <= 100.0


def test_build_report_writes_file(isolate_data):
    db.upsert_response({"msg_id": "1", "company": "Acme", "stage": "rejection",
                        "rejection_category": "overqualified"})
    agent5_responses.build_report([store.new_job(id="a", status="rejected")])
    assert isolate_data.joinpath("responses_report.xlsx").exists()


def test_progress_rows(isolate_data):
    db.upsert_response({"msg_id": "1", "received_date": "2026-09-01", "company": "Acme",
                        "stage": "acknowledged", "job_id": "j1"})
    db.upsert_response({"msg_id": "2", "received_date": "2026-09-05", "company": "Acme",
                        "stage": "interview", "job_id": "j1", "next_step": "call Fri"})
    jobs = [store.new_job(id="j1", company="Acme", title="Dev", status="interview")]
    rows = agent5_responses.progress_rows(jobs)
    assert len(rows) == 1
    assert rows[0]["path"] == "acknowledged → interview"
    assert rows[0]["result"] == "interview"
    assert rows[0]["next_step"] == "call Fri"


def test_numbered_path_collapses_consecutive_and_numbers_separate():
    # Consecutive duplicates (email volume) collapse to one stage.
    assert agent5_responses._numbered_path(
        ["acknowledged", "interview", "interview", "interview", "rejection"]
    ) == "acknowledged → interview → rejection"
    # Genuinely separate repeats are numbered.
    assert agent5_responses._numbered_path(
        ["interview", "acknowledged", "interview", "rejection"]
    ) == "interview #1 → acknowledged → interview #2 → rejection"
    assert agent5_responses._numbered_path(["rejection"]) == "rejection"
    assert agent5_responses._numbered_path([]) == "(no response yet)"


def test_annotate_progress_sets_columns(isolate_data):
    db.upsert_response({"msg_id": "1", "received_date": "2026-09-01", "company": "Acme",
                        "stage": "interview", "job_id": "j1"})
    db.upsert_response({"msg_id": "2", "received_date": "2026-09-05", "company": "Acme",
                        "stage": "interview", "job_id": "j1", "next_step": "final round"})
    db.upsert_response({"msg_id": "3", "received_date": "2026-09-09", "company": "Acme",
                        "stage": "offer", "job_id": "j1"})
    jobs = [store.new_job(id="j1", company="Acme", title="Dev", status="offer")]
    agent5_responses.annotate_progress(jobs)
    assert jobs[0]["stages_path"] == "interview → offer"  # consecutive interviews collapse
    assert jobs[0]["result"] == "offer"
    assert jobs[0]["next_step"] == "final round"


def test_prefilter_skips_unrelated(isolate_data, monkeypatch):
    from jobhelper import email_client, llm
    monkeypatch.setattr(email_client, "fetch_recent", lambda *a, **k: [
        {"msg_id": "<n@promo>", "date": "", "sender": "news@promo.com",
         "subject": "Weekly deals", "body": "Buy shoes now"},
    ])
    # LLM should never be called for unrelated mail.
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called")))
    stats = agent5_responses.process_inbox([])
    assert stats["skipped_unrelated"] == 1
    assert stats["new_responses"] == 0


def test_backfill_roles(isolate_data):
    db.upsert_response({"msg_id": "1", "company": "Veeam", "role": "Software Developer in Test",
                        "stage": "interview"})
    db.upsert_response({"msg_id": "2", "company": "Veeam", "role": "Software Developer in Test",
                        "stage": "rejection"})
    jobs = [
        store.new_job(id="letter-veeam", company="Veeam Software", title="(existing application)",
                      source="manual", status="rejected"),
        store.new_job(id="keep", company="Acme", title="Python Developer", status="waiting"),
    ]
    updated = agent5_responses.backfill_roles(jobs)
    assert updated == 1
    assert jobs[0]["title"] == "Software Developer in Test"  # filled from email role
    assert jobs[1]["title"] == "Python Developer"            # real title untouched


TRACKED = [{"company": "International Rescue"}, {"company": "Northwind Systems"}, {"company": "Kestrel"},
           {"company": "Bright Praha s.r.o."}, {"company": "HP Inc."}, {"company": "Data Systems"}]


@pytest.mark.parametrize("sender, subject, body", [
    # a conference advert: "international" is in a tracked company's name, and names nobody
    ("Conference <info@eu-conf.example>", "International scientific conference in Spain", "Submit your paper by Friday."),
    # a shop's advert that mentions a brand or a city somewhere in its text
    ("Shop <news@shop.example>", "Technology for everyone", "Laptops by Kestrel and others, from our store in Praha."),
    ("Shoes <akce@obuv.example>", "Celebrate with us", "Up to 25 % off. Our shop in Praha. Unsubscribe here."),
    # automatic mail from a company you applied to, with nothing about an application in it
    ("Kestrel <no-reply@kestrel.example>", "Your statement is available", "Open the app to see it."),
    ("Kestrel <hello@news.kestrel.example>", "What is new this month", "Three new features."),
    ("Kestrel <team@kestrel.example>", "What is new this month", "Three new features. Unsubscribe at any time."),
    # list mail that merely uses the words
    ("Big Blue <careers@bigblue.example>", "Advice for entry-level candidates", "How to get hired. Unsubscribe."),
    # job-board alerts and sign-up mail, even from a recruiting system
    ("jobs.cz <info@jobs.cz>", "41 nových nabídek práce, například u Acme", "Podívejte se."),
    ("jobs.cz <info@jobs.cz>", "Potvrďte svůj e-mail", "Klikněte."),
    ("Careers <system@successfactors.com>", "One-Time Password for Candidate Account", "Your code is 123456."),
])
def test_advertising_and_automatic_mail_is_not_sent_to_claude(sender, subject, body):
    assert email_client.looks_like_application(sender, subject, body, TRACKED) is False


@pytest.mark.parametrize("sender, subject, body", [
    # a person at the company, with no application words at all
    ("Jana <jana.novak@kestrel.example>", "Tuesday?", "Hi, are you free for a short call on Tuesday afternoon?"),
    # automatic mail from the company that does talk about the application
    ("Kestrel <no-reply@kestrel.example>", "News about your application", "We regret to inform you. Unsubscribe."),
    ("Northwind Systems Careers <noreply@northwind.example>", "Thank you for applying", "We received your CV."),
    # a recruiting system, and plain application wording from a stranger
    ("Acme via Greenhouse <no-reply@greenhouse.io>", "Update", "hello"),
    ("hr@other.example", "Your application", "We would like to invite you to an interview."),
    # a company whose name is too short to be a word, known by its domain
    ("Sam <sam@hp.example>", "Next steps", "Could you send me your availability?"),
    # a name made only of common words counts when all of it is there
    ("Data Systems <people@datasys.example>", "Hello from Data Systems", "Can we talk this week?"),
])
def test_real_replies_still_reach_claude(sender, subject, body):
    assert email_client.looks_like_application(sender, subject, body, TRACKED) is True


def test_a_shared_common_word_does_not_name_a_company():
    names = email_client.names_tracked_company
    assert names("info@eu-conf.example", "International conference", TRACKED) is False
    assert names("x@shop.example", "New systems for your home", TRACKED) is False          # "systems" alone
    assert names("x@shop.example", "Data for everyone", TRACKED) is False                  # half of "Data Systems"
    assert names("jobs@northwind.example", "Hello", TRACKED) is True
    assert names("x@mail.example", "Your interview at Kestrel", TRACKED) is True
    assert names("x@hp.example", "Hello", TRACKED) is True and names("x@php.example", "Hello", TRACKED) is False
    assert names("x@mail.example", "Hello", []) is False and names("", "", TRACKED) is False


def test_looks_like_application():
    from jobhelper import email_client
    assert email_client.looks_like_application("hr@x.com", "Your application", "We regret to inform you", [])
    assert email_client.looks_like_application("noreply@greenhouse.io", "Update", "hello", [])
    assert not email_client.looks_like_application("news@promo.com", "Weekly deals", "Buy shoes", [])


def test_inbox_scan_reports_progress_per_email(isolate_data, monkeypatch):
    from jobhelper import agent5_responses, email_client
    emails = [{"msg_id": f"<{n}@x>", "date": "Mon, 5 Oct 2026 10:00:00 +0200", "sender": "news@shop.com",
               "subject": "Sale", "body": "Buy now"} for n in range(3)]
    monkeypatch.setattr(email_client, "fetch_recent", lambda days=None: emails)
    monkeypatch.setattr(email_client, "looks_like_application", lambda *a, **k: False)
    seen = []
    stats = agent5_responses.process_inbox([], progress=lambda done, total: seen.append((done, total)))
    assert seen == [(0, 3), (1, 3), (2, 3)]
    assert stats["scanned"] == 3 and stats["skipped_unrelated"] == 3


# ── found on a real interview invitation ────────────────────────────────────
def _brightline():
    from jobhelper import store
    return [store.new_job(id="ros", title="Junior Robotics Software Engineer (ROS)", company="BRIGHTLINE", status="waiting", last_update="2026-09-30"),
            store.new_job(id="ml", title="Machine Learning Engineer", company="BRIGHTLINE", status="interview", last_update="2026-10-08"),
            store.new_job(id="cv", title="Computer Vision Engineer", company="BRIGHTLINE", status="found", last_update="2026-10-08"),
            store.new_job(id="old", title="Data Engineer", company="BRIGHTLINE", status="rejected", last_update="2026-10-09")]


def test_an_email_without_a_role_goes_to_the_open_application_furthest_along():
    from jobhelper import email_client
    jobs = _brightline()
    got = email_client.match_job("Petra <petra@brightlinerobotics.com>", "Invitation: Interview with Brightline Robotics", "When: Tuesday", jobs)
    assert got["id"] == "ml"                                           # not the first Brightline job in the list
    named = email_client.match_job("petra@brightlinerobotics.com", "Brightline Robotics - Junior Robotics Software Engineer - update", "", jobs)
    assert named["id"] == "ros"                                        # a role in the subject still decides
    assert email_client.best_job_for_company_role("Brightline Robotics", "Interview", jobs)["id"] == "ml"
    only_leads = [j for j in jobs if j["id"] == "cv"]
    assert email_client.match_job("x@brightlinerobotics.com", "Hello from Brightline", "", only_leads)["id"] == "cv"


def test_scan_summary_names_invitations_first():
    from jobhelper import agent5_responses as a5
    assert a5.scan_summary({"scanned": 12, "new_responses": 3, "rejections": 1, "invites": ["Brightline", "Brightline"]}) == \
        "Scanned 12 emails · 3 new: 2 invitations, 1 rejection."
    assert a5.scan_summary({"scanned": 1, "new_responses": 1, "rejections": 1, "invites": []}) == "Scanned 1 email · 1 new: 1 rejection."
    assert a5.scan_summary({"scanned": 9, "new_responses": 4, "rejections": 1, "invites": ["A"]}) == \
        "Scanned 9 emails · 4 new: 1 invitation, 1 rejection, 2 other."
    assert a5.scan_summary({"scanned": 5, "new_responses": 2, "rejections": 0, "invites": []}) == "Scanned 5 emails · 2 new."
    assert a5.scan_summary({"scanned": 0, "new_responses": 0, "rejections": 0, "invites": []}) == "Scanned 0 emails · 0 new."
    assert a5.scan_summary({"scanned": 3, "new_responses": 1, "rejections": 0, "invites": ["Brightline"], "dates": ["13 Oct 11:30 · BRIGHTLINE"]}) == \
        "Scanned 3 emails · 1 new: 1 invitation. Date saved: 13 Oct 11:30 · BRIGHTLINE."


def _soon(days=5):
    from datetime import date, timedelta
    return (date.today() + timedelta(days=days)).isoformat()


def test_the_interview_day_in_an_email_becomes_the_date_to_remember():
    from datetime import date

    from jobhelper import agent5_responses as a5, store
    job = store.new_job(id="ml", title="ML Engineer", company="BRIGHTLINE", status="interview")
    day = _soon()
    saved = a5._save_date(job, {"when": f"{day} 9:30", "next_step": "Join the Google Meet call."}, "interview")
    when = date.fromisoformat(day)
    assert saved == f"{when.day} {when:%b} 09:30 · BRIGHTLINE"
    assert job["event"] == {"date": day, "time": "09:30", "kind": "interview", "note": "Join the Google Meet call."}
    assert a5._save_date(job, {"when": day}, "interview") != "" and job["event"]["time"] == ""      # the same day again: updated
    other = _soon(9)
    assert a5._save_date(job, {"when": other}, "interview") == "" and job["event"]["date"] == day   # your date is not overwritten
    for nothing in ("", None, "next Tuesday", "2020-01-01 10:00", "13.10.2026"):
        fresh = store.new_job(id="x", title="T", company="C")
        assert a5._save_date(fresh, {"when": nothing}, "interview") == "" and "event" not in fresh


def test_a_scan_files_both_emails_under_one_application_and_saves_the_date(isolate_data, monkeypatch):
    from jobhelper import agent5_responses as a5, email_client, llm
    day = _soon()
    mails = [{"msg_id": "<1>", "date": "Thu, 8 Oct 2026 17:24:00 +0200", "sender": "Petra <petra@brightlinerobotics.com>",
              "subject": "Brightline Robotics - Junior Machine Learning Engineer - Next Steps", "body": "We'd like to move to the next step. Book a time."},
             {"msg_id": "<2>", "date": "Thu, 8 Oct 2026 18:10:00 +0200", "sender": "Petra <petra@brightlinerobotics.com>",
              "subject": "Invitation from an unknown sender: Interview with Brightline Robotics", "body": f"When: {day} 11:30am"}]
    replies = [{"is_response": True, "stage": "interview", "company": "Brightline Robotics", "role": "Junior Machine Learning Engineer", "summary": "Invited.", "when": ""},
               {"is_response": True, "stage": "interview", "company": "Brightline Robotics", "role": "", "summary": "Scheduled.", "when": f"{day} 11:30",
                "next_step": "Attend on Google Meet."}]
    monkeypatch.setattr(email_client, "fetch_recent", lambda days=None: mails)
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: replies.pop(0))
    jobs = _brightline()
    jobs[1]["status"] = "found"                                        # the ML job was still a lead when the first email came
    stats = a5.process_inbox(jobs)
    by = {j["id"]: j for j in jobs}
    assert by["ml"]["status"] == "interview" and by["ros"]["status"] == "waiting"       # the other application is left alone
    assert by["ml"]["event"]["date"] == day and by["ml"]["event"]["time"] == "11:30" and "event" not in by["ros"]
    assert len(stats["invites"]) == 2 and len(stats["dates"]) == 1
    assert a5.scan_summary(stats).startswith("Scanned 2 emails (0 read before, 2 sent to Claude) · 2 new: 2 invitations. Date saved: ")


def test_reply_notification_wording():
    from jobhelper import agent5_responses as a5
    assert a5.replies_text({"new_responses": 0}) == "No new replies."
    assert a5.replies_text({"scanned": 12, "new_responses": 3, "rejections": 1, "invites": ["A", "A"]}) == "3 new replies: 2 invitations, 1 rejection."
    assert a5.replies_text({"scanned": 4, "new_responses": 1, "rejections": 1, "invites": []}) == "1 new reply: 1 rejection."
    assert a5.replies_text({"scanned": 4, "new_responses": 2, "rejections": 0, "invites": []}) == "2 new replies."


def test_trying_a_mailbox_tells_refused_from_unreachable(monkeypatch):
    import imaplib

    class Box:
        def __init__(self, fail=None):
            self.fail, self.calls = fail, []

        def login(self, user, password):
            self.calls.append("login")
            if self.fail:
                raise self.fail

        def logout(self):
            self.calls.append("logout")

    box, hosts = Box(), []
    monkeypatch.setattr(imaplib, "IMAP4_SSL", lambda host, port, timeout=None: hosts.append(host) or box)
    real = _REAL_TRY_LOGIN                    # conftest replaces the function for every test; this is the real one
    assert real("me@example.com", "abcdabcdabcdabcd", host="imap.example.com") == {"ok": True, "msg": ""}
    assert box.calls == ["login", "logout"] and hosts == ["imap.example.com"]     # nothing is opened or read
    box = Box(imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials"))
    refused = real("me@example.com", "secretsecretsecr")
    assert refused["ok"] is False and "refused" in refused["msg"] and "secretsecretsecr" not in refused["msg"] and box.calls[-1] == "logout"
    box = Box(OSError("timed out"))
    assert real("me@example.com", "abcdabcdabcdabcd")["ok"] is None

    def unreachable(host, port, timeout=None):
        raise OSError("no route to host")
    monkeypatch.setattr(imaplib, "IMAP4_SSL", unreachable)
    lost = real("me@example.com", "abcdabcdabcdabcd")
    assert lost["ok"] is None and "not tried" in lost["msg"]


def test_a_reply_is_not_filed_to_a_company_by_a_word_many_companies_share():
    jobs = [{"id": "a", "company": "International Rescue", "title": "Developer", "status": "waiting"},
            {"id": "b", "company": "Northwind Systems", "title": "Developer", "status": "waiting"},
            {"id": "c", "company": "Bright Praha s.r.o.", "title": "Tester", "status": "waiting"},
            {"id": "d", "company": "Data Systems", "title": "Analyst", "status": "waiting"}]
    match = email_client.match_job
    assert match("info@eu-conf.example", "International scientific conference", "Submit your paper.", jobs) is None
    assert match("shop@obuv.example", "Sale", "Visit our shop in Praha. New systems for your home.", jobs) is None
    assert match("x@mail.example", "Data for everyone", "Big data.", jobs) is None                      # half of "Data Systems"
    # a real name word still does it, from the sender, the subject or the text
    assert match("jobs@northwind.example", "Your application", "", jobs)["id"] == "b"
    assert match("hr@mail.example", "Interview at International Rescue", "", jobs)["id"] == "a"
    assert match("hr@mail.example", "Your application", "Thank you for applying to Bright.", jobs)["id"] == "c"
    # a name made only of common words: all of it must be there
    assert match("people@mail.example", "Hello from Data Systems", "", jobs)["id"] == "d"
    # between two companies, the one named by its own word wins over one that only shares a common word
    both = jobs + [{"id": "e", "company": "Kestrel International", "title": "Developer", "status": "waiting"}]
    assert match("careers@kestrel.example", "Kestrel International: your application", "", both)["id"] == "e"


def test_a_word_of_a_job_title_in_a_company_name_does_not_match_a_reply():
    """A rejection for an "IT Support Specialist" role at one company was filed under "Reed Specialist Recruitment"."""
    jobs = [{"id": "reed", "company": "REED SPECIALIST RECRUITMENT", "title": "IT Application Support Specialist", "status": "waiting"},
            {"id": "user", "company": "Usercentrics", "title": "Technical Support Specialist", "status": "waiting"},
            {"id": "nn", "company": "NN Digital Hub", "title": "Analyst", "status": "waiting"},
            {"id": "actum", "company": "Actum Digital", "title": "Consultant", "status": "waiting"}]
    match = email_client.match_job
    assert match("no-reply@usercentrics.example", "IT Support Specialist (m/f/d) - Usercentrics", "Thank you for applying.", jobs)["id"] == "user"
    assert match("jobs@mail.example", "Your application: IT Support Specialist", "We regret to inform you.", jobs) is None
    assert match("hr@nn.example", "Thank you for your application at NN Digital Hub", "", jobs)["id"] == "nn"       # all of a common-word name
    assert match("hr@reed.example", "Your application at Reed", "", jobs)["id"] == "reed"
    assert email_client.names_tracked_company("jobs@mail.example", "IT Support Specialist", jobs) is False
