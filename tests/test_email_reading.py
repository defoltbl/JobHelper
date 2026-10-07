"""Reading reply emails: HTML-only messages, rejection wording, and the repair
of replies an older version filed wrongly."""
from email.message import EmailMessage

import pytest

from jobhelper import agent5_responses, db, email_client, llm, store

REJECT_HTML = """<html><head><style>p{color:red}</style><title>Update</title></head><body>
<p>Hello Alex,</p><p>Thank you for your interest in our <b>QA&nbsp;Engineer</b> position.<br>
We are moving forward with other candidates at this time.</p><script>track()</script></body></html>"""


def _html_only(html=REJECT_HTML):
    msg = EmailMessage()
    msg.set_content(html, subtype="html")
    return msg


# ── body extraction ─────────────────────────────────────────────────────────
def test_html_only_email_is_read_as_text():
    text = email_client._body_text(_html_only())
    assert "moving forward with other candidates" in text and "QA Engineer" in text
    assert "track()" not in text and "color:red" not in text and "<p>" not in text
    assert email_client._has_plain_text(_html_only()) is False


def test_plain_part_is_preferred_when_present():
    msg = EmailMessage()
    msg.set_content("Plain version of the message.")
    msg.add_alternative("<p>HTML version</p>", subtype="html")
    assert email_client._body_text(msg).strip() == "Plain version of the message."
    assert email_client._has_plain_text(msg) is True


def test_empty_plain_part_falls_back_to_html():
    msg = EmailMessage()
    msg.set_content("   \n")
    msg.add_alternative("<p>We regret to inform you.</p>", subtype="html")
    assert "regret to inform you" in email_client._body_text(msg)


def test_attachments_are_not_read_as_the_body():
    msg = EmailMessage()
    msg.set_content("<p>See attachment</p>", subtype="html")
    msg.add_attachment("secret notes", filename="notes.txt")
    assert email_client._body_text(msg) == "See attachment"


# ── rejection wording ───────────────────────────────────────────────────────
@pytest.mark.parametrize("text, category", [
    ("We wanted to inform you that this role has now been filled.", "position_filled"),
    ("We are moving forward with other candidates at this time.", "went_with_other_candidate"),
    ("Unfortunately, we have made the decision to move forward with other candidates whose experience fits.", "went_with_other_candidate"),
    ("At this time, we will be progressing with other candidates whose background fits better.", "went_with_other_candidate"),
    ("We regret to inform you that we have decided not to move forward with your candidacy.", "no_reason_given"),
    ("After careful consideration, we decided not to continue with you in this hiring process.", "no_reason_given"),
    ("Unfortunately, we will not be moving forward with your application.", "no_reason_given"),
    ("Bohužel jsme Vás nevybrali do dalšího kola.", "no_reason_given"),
])
def test_clear_rejections_are_recognised(text, category):
    assert email_client.rejection_wording(text) == category


@pytest.mark.parametrize("text", [
    "Thank you for applying. Unfortunately we cannot reply to every applicant individually.",
    "If you do not hear from us in the next couple of weeks, please allow this email to serve as a notification "
    "that you were not selected for an initial interview.",
    "If you see the job moved to an inactive state, that means the position is either no longer open, "
    "you withdrew from consideration, or you were not selected for the role.",
    "We received your application. If your profile matches we will move forward and contact you.",
    "Please share your feedback about your interview experience.",
    "",
])
def test_confirmations_and_hypotheticals_are_not_rejections(text):
    assert email_client.rejection_wording(text) == ""


@pytest.mark.parametrize("left, right", [("CSOB", "ČSOB (KBC)"), ("Skoda Auto", "Škoda Auto a.s."), ("TDSYNNEX", "TD SYNNEX")])
def test_company_key_ignores_accents_brackets_and_spacing(left, right):
    assert email_client.norm_company(left) == email_client.norm_company(right)


# ── scanning ────────────────────────────────────────────────────────────────
def _mail(msg_id, body, subject="An update on your application", html_only=True):
    return {"msg_id": msg_id, "date": "Mon, 5 Oct 2026 10:00:00 +0200", "sender": "acme@myworkday.com",
            "subject": subject, "body": body, "was_html_only": html_only}


def test_scan_overrides_a_vague_reading_when_the_text_is_a_rejection(isolate_data, monkeypatch):
    jobs = [store.new_job(id="acme", title="QA Engineer", company="Acme", status="waiting")]
    monkeypatch.setattr(email_client, "fetch_recent", lambda days=None: [
        _mail("<1@x>", "Hello, we are moving forward with other candidates at this time.")])
    monkeypatch.setattr(email_client, "looks_like_application", lambda *a, **k: True)
    monkeypatch.setattr(email_client, "match_job", lambda *a, **k: jobs[0])
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"is_response": True, "stage": "other", "company": "Acme",
                                                          "summary": "A status update."})
    stats = agent5_responses.process_inbox(jobs)
    assert stats["rejections"] == 1 and jobs[0]["status"] == "rejected"
    rec = db.all_responses()[0]
    assert (rec["stage"], rec["rejection_category"]) == ("rejection", "went_with_other_candidate")


def test_scan_keeps_the_models_reading_for_a_real_confirmation(isolate_data, monkeypatch):
    jobs = [store.new_job(id="acme", title="QA Engineer", company="Acme", status="waiting")]
    monkeypatch.setattr(email_client, "fetch_recent", lambda days=None: [
        _mail("<1@x>", "Thank you for applying. Unfortunately we cannot reply to everyone.")])
    monkeypatch.setattr(email_client, "looks_like_application", lambda *a, **k: True)
    monkeypatch.setattr(email_client, "match_job", lambda *a, **k: jobs[0])
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"is_response": True, "stage": "acknowledged", "company": "Acme"})
    agent5_responses.process_inbox(jobs)
    assert db.all_responses()[0]["stage"] == "acknowledged" and jobs[0]["status"] == "waiting"


# ── repairing what was misread ──────────────────────────────────────────────
def _stored(msg_id, stage, job_id="acme", company="Acme"):
    db.upsert_response({"msg_id": msg_id, "job_id": job_id, "company": company, "stage": stage,
                        "received_date": "Mon, 5 Oct 2026 10:00:00 +0200", "summary": "no details in the body"})
    db.mark_seen(msg_id)


def test_repair_turns_misread_updates_into_rejections_without_the_model(isolate_data, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("the repair must not use Claude"))
    monkeypatch.setattr(llm, "ask", lambda *a, **k: pytest.fail("the repair must not use Claude"))
    jobs = [store.new_job(id="acme", title="QA Engineer", company="Acme", status="waiting"),
            store.new_job(id="beta", title="Dev", company="Beta", status="waiting")]
    _stored("<rej@x>", "other")
    _stored("<ack@x>", "acknowledged", job_id="beta", company="Beta")
    emails = [_mail("<rej@x>", "We wanted to inform you that this role has now been filled."),
              _mail("<ack@x>", "Thank you for applying to Beta. We will review your application.")]
    stats = agent5_responses.repair_unread_bodies(jobs, emails)
    assert stats == {"rejections_found": 1, "jobs_rejected": 1, "requeued": 0}
    by = {r["msg_id"]: r for r in db.all_responses()}
    assert (by["<rej@x>"]["stage"], by["<rej@x>"]["rejection_category"]) == ("rejection", "position_filled")
    assert by["<ack@x>"]["stage"] == "acknowledged"
    assert jobs[0]["status"] == "rejected" and "re-reading" in jobs[0]["notes"]
    assert jobs[1]["status"] == "waiting"


def test_repair_requeues_what_only_the_model_can_judge(isolate_data, monkeypatch):
    monkeypatch.setattr(email_client, "looks_like_application",
                        lambda sender, subject, body, jobs: "application" in body)
    _stored("<other@x>", "other")
    db.mark_seen("<skipped@x>")
    db.mark_seen("<newsletter@x>")
    emails = [_mail("<other@x>", "Your interview feedback survey."),
              _mail("<skipped@x>", "About your application: please pick a time."),
              _mail("<newsletter@x>", "Our quarterly product news."),
              _mail("<plain@x>", "We regret to inform you ...", html_only=False)]
    stats = agent5_responses.repair_unread_bodies([], emails)
    assert stats["requeued"] == 2 and stats["rejections_found"] == 0
    assert not db.is_seen("<other@x>") and not db.is_seen("<skipped@x>") and db.is_seen("<newsletter@x>")


def test_repair_leaves_emails_that_were_read_correctly(isolate_data):
    jobs = [store.new_job(id="acme", title="QA", company="Acme", status="waiting")]
    _stored("<plain@x>", "other")
    stats = agent5_responses.repair_unread_bodies(
        jobs, [_mail("<plain@x>", "We regret to inform you that ...", html_only=False)])
    assert stats == {"rejections_found": 0, "jobs_rejected": 0, "requeued": 0}
    assert jobs[0]["status"] == "waiting"


def test_unmark_seen_counts_only_what_was_there(isolate_data):
    db.mark_seen("<a@x>")
    assert db.unmark_seen(["<a@x>", "<never@x>"]) == 1
    assert db.unmark_seen([]) == 0 and not db.is_seen("<a@x>")


def test_a_czech_confirmation_moves_the_lead_to_applications_with_a_date(isolate_data, monkeypatch):
    """The company may answer in Czech even for an English-speaking role."""
    jobs = [store.new_job(id="jobscz-1", title="IT Application Support Specialist", company="REED SPECIALIST RECRUITMENT",
                          status="letter_ready", match_score=72)]
    mail = {"msg_id": "<cz@x>", "date": "Wed, 7 Oct 2026 12:46:00 +0200", "sender": "noreply@jobs.cz",
            "subject": "Zařadili jsme Vás do výběrového řízení na pozici IT Application Support Specialist",
            "body": "Dobrý den, děkujeme za Váš zájem. Zařadili jsme Vás do výběrového řízení.", "was_html_only": False}
    monkeypatch.setattr(email_client, "fetch_recent", lambda days=None: [mail])
    monkeypatch.setattr(email_client, "match_job", lambda *a, **k: jobs[0])
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"is_response": True, "stage": "acknowledged",
                                                          "company": "REED SPECIALIST RECRUITMENT", "summary": "Application received."})
    assert email_client.looks_like_application(mail["sender"], mail["subject"], mail["body"], []) is True   # Czech keywords
    stats = agent5_responses.process_inbox(jobs)
    assert stats["status_updates"] == 1
    assert jobs[0]["status"] == "waiting" and jobs[0]["date_applied"] == "2026-10-07"
    assert jobs[0]["status"] in store.APPLICATION_STATUSES


def test_an_apply_date_you_already_have_is_kept(isolate_data, monkeypatch):
    jobs = [store.new_job(id="a", title="Dev", company="Acme", status="letter_ready", date_applied="2026-10-01")]
    monkeypatch.setattr(email_client, "fetch_recent", lambda days=None: [_mail("<1@x>", "We received your application.", html_only=False)])
    monkeypatch.setattr(email_client, "looks_like_application", lambda *a, **k: True)
    monkeypatch.setattr(email_client, "match_job", lambda *a, **k: jobs[0])
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"is_response": True, "stage": "acknowledged", "company": "Acme"})
    agent5_responses.process_inbox(jobs)
    assert jobs[0]["date_applied"] == "2026-10-01" and jobs[0]["status"] == "waiting"


# ── apply dates from the emails ─────────────────────────────────────────────
def _reply(msg_id, job_id, when, stage="acknowledged"):
    db.upsert_response({"msg_id": msg_id, "job_id": job_id, "company": "X", "stage": stage, "received_date": when})


def test_applications_get_their_date_from_the_first_email(isolate_data):
    jobs = [store.new_job(id="empty", title="A", company="A", status="rejected"),
            store.new_job(id="imported", title="B", company="B", status="waiting", source="manual",
                          date_applied="2026-09-13", date_found="2026-09-13"),
            store.new_job(id="real", title="C", company="C", status="waiting", date_applied="2026-07-01"),
            store.new_job(id="no-mail", title="D", company="D", status="waiting"),
            store.new_job(id="lead", title="E", company="E", status="found")]
    _reply("<1@x>", "empty", "Wed, 22 Jul 2026 10:00:00 +0200", "rejection")
    _reply("<2@x>", "empty", "Mon, 20 Jul 2026 09:00:00 +0200")               # the earlier one wins
    _reply("<3@x>", "imported", "Fri, 10 Jul 2026 08:00:00 +0000")
    _reply("<4@x>", "real", "Thu, 9 Jul 2026 08:00:00 +0000")
    _reply("<5@x>", "lead", "Thu, 9 Jul 2026 08:00:00 +0000")
    assert agent5_responses.backfill_apply_dates(jobs) == 2
    by = {j["id"]: j for j in jobs}
    assert (by["empty"]["date_applied"], by["empty"]["date_applied_source"]) == ("2026-07-20", "first email")
    assert by["imported"]["date_applied"] == "2026-07-10"                     # the import day was not a real date
    assert by["real"]["date_applied"] == "2026-07-01" and "date_applied_source" not in by["real"]
    assert by["no-mail"]["date_applied"] == "" and by["lead"]["date_applied"] == ""
    assert agent5_responses.backfill_apply_dates(jobs) == 0                   # nothing more to do


def test_an_earlier_email_found_later_moves_the_date_back(isolate_data):
    jobs = [store.new_job(id="a", title="A", company="A", status="waiting")]
    _reply("<1@x>", "a", "Wed, 22 Jul 2026 10:00:00 +0200")
    agent5_responses.backfill_apply_dates(jobs)
    _reply("<0@x>", "a", "Wed, 15 Jul 2026 10:00:00 +0200")
    assert agent5_responses.backfill_apply_dates(jobs) == 1 and jobs[0]["date_applied"] == "2026-07-15"


def test_marking_applied_in_the_app_is_a_real_date(isolate_data):
    from jobhelper import config, ui_api
    config.ensure_dirs()
    store.save_jobs([store.new_job(id="x", title="Dev", company="Acme", status="letter_ready")])
    ui_api.Api().apply_job("x")
    job = store.load_jobs()[0]
    assert job["date_applied"] and "date_applied_source" not in job
    _reply("<1@x>", "x", "Thu, 9 Jul 2026 08:00:00 +0000")
    assert agent5_responses.backfill_apply_dates([job]) == 0                  # never overwritten by an email
