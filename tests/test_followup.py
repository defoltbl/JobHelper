"""Follow-up reminders: when an application is due, and the draft email."""
from datetime import date

import pytest

from jobhelper import followup, store

TODAY = date(2026, 10, 20)


def _job(**kw):
    kw.setdefault("status", "waiting")
    kw.setdefault("date_found", "2026-09-01")
    kw.setdefault("last_update", "2026-09-01")
    return store.new_job(id=kw.pop("id", "j1"), title="QA Engineer", company="Acme", **kw)


def test_due_after_n_days_without_reply():
    state = followup.info(_job(date_applied="2026-10-05"), 10, today=TODAY)
    assert state == {"due": True, "stale": False, "days_waiting": 15, "since": "2026-10-05",
                     "had_reply": False, "followed_up": ""}


def test_not_due_before_n_days():
    assert followup.info(_job(date_applied="2026-10-15"), 10, today=TODAY)["due"] is False


@pytest.mark.parametrize("status", ["found", "letter_ready", "interview", "offer", "rejected", "on_hold"])
def test_only_waiting_applications_are_due(status):
    assert followup.info(_job(date_applied="2026-09-01", status=status), 10, today=TODAY)["due"] is False


def test_a_recent_reply_resets_the_clock():
    job = _job(date_applied="2026-09-01")
    recent = followup.info(job, 10, last_reply=date(2026, 10, 16), today=TODAY)
    assert recent["due"] is False and recent["had_reply"] is True
    older = followup.info(job, 10, last_reply=date(2026, 9, 20), today=TODAY)
    assert older["days_waiting"] == 30 and older["due"] is True


def test_marking_followed_up_resets_the_clock_and_adds_a_note():
    job = _job(date_applied="2026-10-01", notes="old note")
    followup.mark_sent(job, today=TODAY)
    state = followup.info(job, 10, today=TODAY)
    assert state["due"] is False and state["followed_up"] == "2026-10-20"
    assert job["notes"].startswith("[2026-10-20] Followed up by email.") and "old note" in job["notes"]
    assert followup.info(job, 10, today=date(2026, 11, 2))["due"] is True     # and it comes back later


def test_zero_days_turns_reminders_off():
    assert followup.info(_job(date_applied="2026-01-01"), 0, today=TODAY)["due"] is False


def test_long_silence_is_stale_not_due():
    state = followup.info(_job(date_applied="2026-08-01"), 10, today=TODAY)
    assert state["due"] is False and state["stale"] is True and state["days_waiting"] == 80
    edge = followup.info(_job(date_applied="2026-09-05"), 10, today=TODAY)          # exactly 45 days
    assert edge["due"] is True and edge["stale"] is False


def test_the_day_the_app_first_saw_a_job_is_not_an_apply_date():
    job = _job(date_applied="", date_found="2026-09-26", last_update="2026-10-01")
    assert followup.info(job, 10, today=TODAY) == {"due": False, "stale": False, "days_waiting": 0, "since": "",
                                                    "had_reply": False, "followed_up": ""}


def test_imported_letters_carry_the_import_day_not_a_real_apply_date():
    imported = _job(source="manual", date_applied="2026-09-26", date_found="2026-09-26")
    assert followup.info(imported, 10, today=TODAY)["due"] is False
    assert followup.info(imported, 10, today=TODAY)["since"] == ""
    # ... but a reply from the company is a real date
    assert followup.info(imported, 10, last_reply=date(2026, 10, 5), today=TODAY)["due"] is True
    # and an apply date you set yourself afterwards counts
    marked = _job(source="manual", date_applied="2026-10-02", date_found="2026-09-26")
    assert followup.info(marked, 10, today=TODAY)["due"] is True


def test_reply_dates_are_read_from_email_format():
    replies = followup.last_reply_by_job([
        {"job_id": "j1", "received_date": "Mon, 5 Oct 2026 10:15:00 +0200"},
        {"job_id": "j1", "received_date": "Thu, 1 Oct 2026 09:00:00 +0000"},
        {"job_id": "j2", "received_date": "2026-10-10T08:00:00"},
        {"job_id": "", "received_date": "Mon, 5 Oct 2026 10:15:00 +0200"},
        {"job_id": "j3", "received_date": "garbage"},
    ])
    assert replies == {"j1": date(2026, 10, 5), "j2": date(2026, 10, 10)}


def test_due_jobs_uses_replies():
    jobs = [_job(id="quiet", date_applied="2026-10-01"), _job(id="answered", date_applied="2026-10-01"),
            _job(id="rejected", date_applied="2026-10-01", status="rejected")]
    responses = [{"job_id": "answered", "received_date": "Sun, 18 Oct 2026 10:00:00 +0200"}]
    assert [j["id"] for j in followup.due_jobs(jobs, responses, 10, today=TODAY)] == ["quiet"]


def test_draft_names_role_company_date_and_sender():
    job = _job(date_applied="2026-10-06")
    job["company"] = "ESET Research s.r.o."
    d = followup.draft(job, "Alex Novak")
    assert d["subject"] == "Follow-up on my application: QA Engineer"
    assert "QA Engineer position on 6 October 2026" in d["body"]
    assert d["body"].startswith("Dear ESET Research s.r.o hiring team,")
    assert d["body"].rstrip().endswith("Kind regards,\nAlex Novak")
    assert ".." not in d["body"]


def test_draft_follows_the_writing_rules():
    body = followup.draft(_job(), "")["body"]
    assert "—" not in body and "[Your name]" in body and "recently" in body
    assert all(ord(ch) < 0x2600 for ch in body)          # no emoji


@pytest.mark.parametrize("profile, cv_file, expected", [
    ({"name": "Jane Doe"}, "x.docx", "Jane Doe"),
    ({}, "AlexNovak_CV_EN.docx", "Alex Novak"),
    ({"_cv_file": "AlexNovak_CV_EN.docx"}, "", "Alex Novak"),
    ({}, "cv.docx", ""),
    (None, "", ""),
])
def test_candidate_name(profile, cv_file, expected):
    assert followup.candidate_name(profile, cv_file) == expected
