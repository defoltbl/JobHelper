"""Changing a job by hand, merging one application that was recorded twice,
and the optional second mailbox."""
import imaplib
from datetime import date, timedelta

import pytest

from jobhelper import agent3_letters, agent5_responses, config, db, email_client, merge, store, ui_api, vault


@pytest.fixture
def api(isolate_data):
    config.ensure_dirs()
    return ui_api.Api()


def _seed(*jobs):
    store.save_jobs(list(jobs))


def _app(id, company, title="(existing application)", status="waiting", **kw):
    return store.new_job(id=id, company=company, title=title, status=status, **kw)


# ── status and apply date by hand ───────────────────────────────────────────
def test_mark_rejected_by_hand(api):
    _seed(_app("a", "Acme", "QA Engineer"))
    assert api.set_status("a", "rejected") == {"ok": True}
    job = store.find(store.load_jobs(), "a")
    assert job["status"] == "rejected" and "Marked rejected by you" in job["notes"]
    assert config.EXCEL_PATH.exists()                       # the tracker is rebuilt
    assert api.set_status("a", "rejected") == {"ok": True}  # again: no second note
    assert store.find(store.load_jobs(), "a")["notes"].count("Marked rejected") == 1


def test_status_can_be_corrected_and_unknown_values_are_refused(api):
    _seed(_app("a", "Acme", "QA Engineer", status="rejected"))
    assert api.set_status("a", "interview")["ok"] and store.find(store.load_jobs(), "a")["status"] == "interview"
    assert api.set_status("a", "found")["ok"] is False and api.set_status("a", "nonsense")["ok"] is False
    assert api.set_status("missing", "rejected")["ok"] is False


def test_marking_a_lead_moves_it_to_applications_with_todays_date(api):
    _seed(store.new_job(id="lead", title="Dev", company="Acme", status="letter_ready"))
    assert api.set_status("lead", "waiting")["ok"]
    job = store.find(store.load_jobs(), "lead")
    assert job["status"] == "waiting" and job["date_applied"] == date.today().isoformat()


@pytest.mark.parametrize("text, problem", [
    ("07.10.2026", "YYYY-MM-DD"), ("2026-13-40", "YYYY-MM-DD"), ("yesterday", "YYYY-MM-DD"), ("", "YYYY-MM-DD"),
    ((date.today() + timedelta(days=3)).isoformat(), "future"), ("2015-01-01", "too far in the past"),
])
def test_bad_apply_dates_are_refused_with_a_reason(api, text, problem):
    _seed(_app("a", "Acme", date_applied="2026-09-01"))
    result = api.set_apply_date("a", text)
    assert result["ok"] is False and problem in result["msg"]
    assert store.find(store.load_jobs(), "a")["date_applied"] == "2026-09-01"


def test_apply_date_you_set_is_yours_and_emails_do_not_change_it(api):
    _seed(_app("a", "Acme", date_applied="2026-09-20", date_applied_source="first email"))
    job = store.find(store.load_jobs(), "a"); job["date_applied_source"] = "first email"; store.save_jobs([job])
    assert api.set_apply_date("a", " 2026-09-12 ") == {"ok": True}
    job = store.find(store.load_jobs(), "a")
    assert job["date_applied"] == "2026-09-12" and "date_applied_source" not in job
    db.upsert_response({"msg_id": "<1@x>", "job_id": "a", "company": "Acme", "stage": "acknowledged",
                        "received_date": "Tue, 1 Sep 2026 10:00:00 +0200"})
    assert agent5_responses.backfill_apply_dates([job]) == 0 and job["date_applied"] == "2026-09-12"
    assert api.job_detail("a")["applied_from_email"] is False


def test_skipped_job_can_be_sent_to_scoring(api):
    _seed(store.new_job(id="s", title="Major Account Executive", company="GitLab"))
    job = store.load_jobs()[0]; job["prefilter"] = "The title is another profession (account executive)."; store.save_jobs([job])
    assert api.leads()[0]["tier"] == "skipped" and "another profession" in api.job_detail("s")["prefilter"]
    assert api.score_anyway("s") == {"ok": True}
    detail = api.job_detail("s")
    assert detail["prefilter"] == "" and detail["score_queued"] is True and api.leads()[0]["tier"] == ""


def test_skipped_jobs_are_listed_after_the_scored_ones(api):
    low, skipped = store.new_job(id="low", title="Dev", company="A", match_score=5), store.new_job(id="skip", title="Sales", company="B")
    skipped["prefilter"] = "x"
    _seed(skipped, low)
    assert [r["id"] for r in api.leads()] == ["low", "skip"]


# ── one application recorded twice ──────────────────────────────────────────
@pytest.mark.parametrize("a, b, level", [
    (_app("1", "CSOB"), _app("2", "ČSOB (KBC)", "Python Software Engineer (m/f)"), "sure"),
    (_app("1", "TDSYNNEX"), _app("2", "TD SYNNEX", "AI Integrator / AI Engineer"), "sure"),
    (_app("1", "Valeo s.r.o.", "SW Tool Developer"), _app("2", "Valeo", "SW Tool Developer"), "sure"),
    (_app("1", "Good Data"), _app("2", "GoodData.AI", "(Sr.) Backend Developer"), "possible"),
    (_app("1", "SAP", "CPIT Academy: Junior AI Solutions Engineer"), _app("2", "SAP", "(Junior) Data Engineer - Integration & AI"), ""),
    (_app("1", "Deloitte", "GenAI Engineer"), _app("2", "Deloitte", "AWS Agentic AI Engineer"), ""),
    (_app("1", "Acme"), _app("2", "Beta"), ""),
    (_app("1", "unknown", "(from email response)"), _app("2", "unknown", "(from email response)"), ""),
])
def test_which_records_count_as_the_same_application(a, b, level):
    assert merge.confidence(a, b) == level


def test_a_title_starting_with_a_bracket_is_a_real_role():
    assert merge.is_placeholder(_app("1", "X")) and merge.is_placeholder(_app("1", "X", "(from email response)"))
    assert not merge.is_placeholder(_app("1", "X", "(Junior) Data Engineer - Integration & AI"))


def test_merge_keeps_everything_and_protects_your_own_letter(isolate_data):
    config.ensure_dirs()
    (config.LETTERS_DIR / "my_letter.docx").write_bytes(b"mine")
    placeholder = _app("manual-1", "CSOB", status="waiting", source="manual", cover_letter_file="my_letter.docx",
                       date_applied="2026-09-13", date_found="2026-09-13", notes="imported letter")
    real = _app("email-9", "ČSOB (KBC)", "Python Software Engineer (m/f)", status="rejected", source="email",
                date_applied="2026-07-04", notes="[2026-07-30] rejected", url="https://csob.example/job")
    real["date_applied_source"] = "first email"
    jobs = [placeholder, real, _app("other", "Beta", "Dev")]
    db.upsert_response({"msg_id": "<1@x>", "job_id": "manual-1", "company": "CSOB", "stage": "acknowledged"})
    db.upsert_response({"msg_id": "<2@x>", "job_id": "email-9", "company": "ČSOB", "stage": "rejection"})

    pair = merge.find(jobs)[0]
    assert (pair["keep"], pair["drop"], pair["confidence"]) == ("email-9", "manual-1", "sure")
    assert merge.merge(jobs, pair["keep"], pair["drop"]) is True
    assert [j["id"] for j in jobs] == ["email-9", "other"]
    kept = jobs[0]
    assert kept["status"] == "rejected" and kept["cover_letter_file"] == "my_letter.docx" and kept["own_letter"] is True
    assert kept["date_applied"] == "2026-07-04" and kept["date_applied_source"] == "first email"   # not the import day
    assert "imported letter" in kept["notes"] and "rejected" in kept["notes"]
    assert {r["job_id"] for r in db.all_responses()} == {"email-9"}                 # both emails now on one record
    assert agent3_letters._generated_letter(kept) is False                           # your letter is still never rewritten


def test_a_rejection_wins_and_otherwise_the_furthest_stage(isolate_data):
    jobs = [_app("1", "Acme", "Dev", status="interview"), _app("2", "Acme", status="waiting")]
    merge.merge(jobs, "1", "2")
    assert jobs[0]["status"] == "interview"
    jobs = [_app("1", "Acme", "Dev", status="waiting"), _app("2", "Acme", status="rejected")]
    merge.merge(jobs, "1", "2")
    assert jobs[0]["status"] == "rejected"


def test_only_certain_pairs_merge_by_themselves(isolate_data):
    jobs = [_app("1", "CSOB"), _app("2", "ČSOB (KBC)", "Python Engineer"),
            _app("3", "Good Data"), _app("4", "GoodData.AI", "Backend Developer"),
            _app("5", "SAP", "Role A"), _app("6", "SAP", "Role B")]
    done = merge.auto_merge(jobs)
    assert done == [{"kept": "ČSOB (KBC)", "dropped": "CSOB"}]
    assert [j["id"] for j in jobs] == ["2", "3", "4", "5", "6"]
    assert [(p["keep"], p["drop"], p["confidence"]) for p in merge.find(jobs)] == [("4", "3", "possible")]


def test_leads_are_never_merged(isolate_data):
    jobs = [store.new_job(id="lead", title="(existing application)", company="Acme", status="found"), _app("app", "Acme", "Dev")]
    assert merge.find(jobs) == []


def test_possible_duplicate_is_offered_and_can_be_declined_or_merged(api):
    _seed(_app("3", "Good Data", status="rejected"), _app("4", "GoodData.AI", "Backend Developer", status="rejected"))
    assert api.counts()["duplicates"] == 1
    assert [r["duplicate"] for r in api.applications()] == [True, True]
    other = api.job_detail("4")["duplicate"]
    assert (other["id"], other["keep"], other["drop"]) == ("3", "4", "3")
    assert api.keep_separate("4", "3")["ok"] and api.counts()["duplicates"] == 0 and api.job_detail("4")["duplicate"] == {}

    _seed(_app("3", "Good Data", status="rejected"), _app("4", "GoodData.AI", "Backend Developer", status="rejected"))
    assert api.merge_jobs("4", "3") == {"ok": True}
    assert [j["id"] for j in store.load_jobs()] == ["4"] and api.counts()["duplicates"] == 0
    assert api.merge_jobs("4", "gone")["ok"] is False


def test_certain_duplicates_are_merged_after_every_scan(isolate_data):
    config.ensure_dirs()
    jobs = [_app("1", "TDSYNNEX", status="waiting"), _app("2", "TD SYNNEX", "AI Engineer", status="rejected")]
    agent5_responses.annotate_progress(jobs)
    assert [j["id"] for j in jobs] == ["2"]


# ── the optional second mailbox ─────────────────────────────────────────────
@pytest.fixture
def mail(isolate_data, monkeypatch):
    for name, value in (("IMAP_USER", "main@example.com"), ("IMAP_PASSWORD", "abcdabcdabcdabcd"),
                        ("IMAP_USER_2", ""), ("IMAP_PASSWORD_2", "")):
        monkeypatch.setattr(config, name, value)
    for key in ("IMAP_USER_2", "IMAP_PASSWORD_2"):
        monkeypatch.delenv(key, raising=False)
    boxes = {"main@example.com": [{"msg_id": "<m1>"}, {"msg_id": "<both>"}],
             "second@example.com": [{"msg_id": "<s1>"}, {"msg_id": "<both>"}]}
    asked = []

    def fetch(user, password, since, all_folders=False, host=""):
        asked.append(user)
        if isinstance(boxes.get(user), Exception):
            raise boxes[user]
        return [dict(m, mailbox=user) for m in boxes[user]]

    monkeypatch.setattr(email_client, "_fetch_box", fetch)
    return boxes, asked


def test_one_mailbox_is_enough(mail):
    boxes, asked = mail
    assert [b["user"] for b in config.mailboxes()] == ["main@example.com"]
    assert [m["msg_id"] for m in email_client.fetch_recent(10)] == ["<m1>", "<both>"] and asked == ["main@example.com"]


def test_second_mailbox_is_read_too_and_the_same_mail_counts_once(mail):
    boxes, asked = mail
    config.set_imap2("second@example.com", "wxyzwxyzwxyzwxyz")
    assert vault.get_secret(vault.IMAP_ACCOUNT_2) == "wxyzwxyzwxyzwxyz"
    text = config.ENV_PATH.read_text(encoding="utf-8")
    assert "IMAP_USER_2=second@example.com" in text and "wxyz" not in text          # password only in the Keychain
    got = email_client.fetch_recent(10)
    assert [m["msg_id"] for m in got] == ["<m1>", "<both>", "<s1>"] and asked == ["main@example.com", "second@example.com"]
    assert got[-1]["mailbox"] == "second@example.com" and email_client.last_warnings == []


def test_a_broken_second_mailbox_does_not_stop_the_scan(mail):
    boxes, asked = mail
    config.set_imap2("second@example.com", "wxyzwxyzwxyzwxyz")
    boxes["second@example.com"] = imaplib.IMAP4.error("AUTHENTICATIONFAILED")
    got = email_client.fetch_recent(10)
    assert [m["msg_id"] for m in got] == ["<m1>", "<both>"]
    assert "second@example.com" in email_client.last_warnings[0] and "check its password" in email_client.last_warnings[0]


def test_a_broken_main_mailbox_is_still_an_error(mail):
    boxes, asked = mail
    boxes["main@example.com"] = imaplib.IMAP4.error("AUTHENTICATIONFAILED")
    with pytest.raises(imaplib.IMAP4.error):
        email_client.fetch_recent(10)


def test_second_mailbox_can_be_removed(mail):
    config.set_imap2("second@example.com", "wxyzwxyzwxyzwxyz")
    config.remove_imap2()
    assert len(config.mailboxes()) == 1 and vault.get_secret(vault.IMAP_ACCOUNT_2) == ""
    assert "IMAP_USER_2" not in config.ENV_PATH.read_text(encoding="utf-8")


def test_the_same_address_twice_is_not_a_second_mailbox(mail, qapp):
    from jobhelper import qt_bridge
    bridge = qt_bridge.Bridge()
    assert bridge.saveEmail2("MAIN@example.com", "wxyzwxyzwxyzwxyz")["ok"] is False
    assert bridge.saveEmail2("second@example.com", "wxyzwxyzwxyzwxyz") == {"ok": True}
    assert bridge.saveEmail2("second@example.com", "") == {"ok": True}               # blank keeps the password
    assert config.IMAP_PASSWORD_2 == "wxyzwxyzwxyzwxyz"
    conn = ui_api.Api().connections()
    assert conn["email2"] is True and conn["email2_addr"] == "second@example.com"
    assert bridge.removeEmail2() == {"ok": True} and ui_api.Api().connections()["email2"] is False


def test_no_mailbox_at_all_explains_what_to_do(mail, monkeypatch):
    monkeypatch.setattr(config, "IMAP_USER", "")
    with pytest.raises(RuntimeError, match="Account card"):
        email_client.fetch_recent(10)
