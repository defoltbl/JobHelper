"""Agent 5 (response analysis) + SQLite DB tests — mocked email + LLM."""
from jobhelper import agent5_responses, db, email_client, llm, store


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
