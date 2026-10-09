"""The Qt bridge between the window and the agents — everything external is stubbed."""
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from jobhelper import (agent1_cv, agent2_search, agent3_letters, agent4_tracker,  # noqa: E402
                       agent5_responses, config, integrity, letters, qt_bridge, store, ui_api, usage, vault)

READY = {"claude": True, "plan": "pro", "claude_email": "me@example.com", "paid_api": False,
         "email": True, "email_addr": "jobs@example.com", "cv": "cv.docx"}


@pytest.fixture
def bridge(qapp, isolate_data, monkeypatch):
    conn = dict(READY)
    monkeypatch.setattr(ui_api.Api, "connections", lambda self: dict(conn))
    monkeypatch.setattr(config, "MODEL", config.MODEL)
    monkeypatch.setattr(config, "MIN_LEAD_SCORE", config.MIN_LEAD_SCORE)
    b = qt_bridge.Bridge()
    b.conn = conn
    return b


def _no_thread(monkeypatch):
    """Make runSearch/scanEmail record the worker instead of starting it."""
    started = []

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target, self.args = target, args

        def start(self):
            started.append(self.target.__name__)

    monkeypatch.setattr(qt_bridge.threading, "Thread", FakeThread)
    return started


# ── start guards ────────────────────────────────────────────────────────────
def test_run_search_starts_when_everything_is_connected(bridge, monkeypatch):
    started = _no_thread(monkeypatch)
    assert bridge.runSearch({"where": "Brno"}) == {"ok": True}
    assert started == ["_pipeline"] and bridge.running is True


def test_run_search_refuses_a_second_run(bridge, monkeypatch):
    _no_thread(monkeypatch)
    bridge.runSearch({"where": "Brno"})
    again = bridge.runSearch({"where": "Brno"})
    assert again["ok"] is False and "already" in again["msg"]


@pytest.mark.parametrize("change, fix", [({"claude": False}, "claude"), ({"cv": ""}, "cv")])
def test_run_search_points_at_what_is_missing(bridge, monkeypatch, change, fix):
    started = _no_thread(monkeypatch)
    bridge.conn.update(change)
    result = bridge.runSearch({"where": "Brno"})
    assert result["ok"] is False and result["fix"] == fix
    assert started == [] and bridge.running is False


def test_run_search_refuses_the_paid_api(bridge, monkeypatch):
    started = _no_thread(monkeypatch)
    bridge.conn["paid_api"] = True
    result = bridge.runSearch({"where": "Brno"})
    assert result["ok"] is False and "ANTHROPIC_API_KEY" in result["msg"]
    assert started == []


def test_scan_email_needs_the_job_email(bridge, monkeypatch):
    started = _no_thread(monkeypatch)
    monkeypatch.setattr(config, "IMAP_USER", "")
    monkeypatch.setattr(config, "IMAP_PASSWORD", "")
    result = bridge.scanEmail()
    assert result["ok"] is False and result["fix"] == "email" and started == []
    monkeypatch.setattr(config, "IMAP_USER", "jobs@example.com")
    monkeypatch.setattr(config, "IMAP_PASSWORD", "abcdabcdabcdabcd")
    assert bridge.scanEmail() == {"ok": True} and started == ["_scan"]


# ── the pipeline worker ─────────────────────────────────────────────────────
def _stub_agents(monkeypatch, search=None):
    def default_search(queries, progress=None, **kw):
        if progress:
            progress(0, 2)
            progress(1, 2)
        return [store.new_job(id="n1", title="Dev", company="Acme")]

    def process(jobs, profile, progress=None, **kw):
        if progress:
            progress(0, 1)
        return {"scored": 1, "letters": 1, "tailored_cvs": 1, "skipped": 0}

    monkeypatch.setattr(agent1_cv, "load_profile", lambda current_only=False: {"seniority": "junior", "search_queries": ["dev"]})
    monkeypatch.setattr(agent1_cv, "find_cv", lambda: None)
    monkeypatch.setattr(agent2_search, "search", search or default_search)
    monkeypatch.setattr(letters, "import_letters", lambda jobs: {"scanned": 0, "linked": 0, "seeded": 0})
    monkeypatch.setattr(agent3_letters, "process", process)
    monkeypatch.setattr(agent5_responses, "annotate_progress", lambda jobs: None)
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)


def _record(bridge):
    events = []
    bridge.agentChanged.connect(lambda key, status, info: events.append(("agent", key, status)))
    bridge.progressChanged.connect(lambda key, done, total: events.append(("progress", key, done, total)))
    bridge.runFinished.connect(lambda mode, summary: events.append(("finished", mode, summary)))
    return events


def test_pipeline_runs_agents_in_order_and_reports_progress(bridge, monkeypatch):
    _stub_agents(monkeypatch)
    events = _record(bridge)
    bridge._set_running(True)
    bridge._pipeline({})
    agents = [(e[1], e[2]) for e in events if e[0] == "agent"]
    assert agents == [("a1", "running"), ("a1", "done"), ("a2", "running"), ("a2", "done"),
                      ("a3", "running"), ("a3", "done"), ("a4", "running"), ("a4", "done")]
    progress = [e[1:] for e in events if e[0] == "progress"]
    assert ("a3", 0, 1) in progress
    assert [p for p in progress if p[0] == "a2"], "search progress must reach the UI"
    assert events[-1][0] == "finished" and events[-1][2].startswith("Done")
    assert bridge.running is False
    assert [j["id"] for j in store.load_jobs()] == ["n1"]


def test_a_search_notes_what_it_alone_would_have_cost(bridge, monkeypatch):
    """The Last run card shows the price of the last run, not of everything ever asked."""
    _stub_agents(monkeypatch)
    usage.record({"cost_usd": 33.5}, tag="earlier")

    def process(jobs, profile, progress=None, **kw):
        usage.record({"cost_usd": 0.4}, tag="score")
        usage.record({"cost_usd": 0.014}, tag="letter")
        return {"scored": 1, "letters": 1, "tailored_cvs": 1, "skipped": 0}

    monkeypatch.setattr(agent3_letters, "process", process)
    bridge._set_running(True)
    bridge._pipeline({})
    last = bridge.lastRun()
    assert last["cost"] == 0.41 and last["cost_of"] == "search"


def test_a_longer_scan_can_be_asked_for_once(bridge, monkeypatch):
    started = _no_thread(monkeypatch)
    monkeypatch.setattr(config, "IMAP_USER", "jobs@example.com")
    monkeypatch.setattr(config, "IMAP_PASSWORD", "abcdabcdabcdabcd")
    for wrong in (0, -5, 366, 100000):
        assert bridge.scanEmailBack(wrong)["ok"] is False and "between 1 and 365" in bridge.scanEmailBack(wrong)["msg"]
    assert started == []
    assert bridge.scanEmailBack(90) == {"ok": True} and started == ["_scan"]
    assert "running" in bridge.scanEmailBack(90)["msg"] and started == ["_scan"]


def test_a_longer_scan_reads_that_period_and_leaves_the_setting(bridge, monkeypatch):
    seen = []

    def read(jobs, lookback_days=None, progress=None, on_limit=None):
        seen.append(lookback_days)
        return {"scanned": 45, "already_read": 40, "asked": 5, "new_responses": 0, "rejections": 0}

    monkeypatch.setattr(agent5_responses, "process_inbox", read)
    for name in ("backfill_roles", "annotate_progress", "build_report"):
        monkeypatch.setattr(agent5_responses, name, lambda jobs: None)
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)
    events = _record(bridge)
    before = bridge.options()["scan_days"]
    bridge._scan(90)
    bridge._scan()
    assert seen == [90, before] and bridge.options()["scan_days"] == before
    assert bridge.lastRun()["scan_detail"] == "45 · 5 to Claude"
    assert "Scanned 45 emails (40 read before, 5 sent to Claude) · 0 new." in events[-1][2]


def test_saving_a_mailbox_tries_it_first(bridge, monkeypatch):
    from jobhelper import email_client
    saved, tried = [], []
    monkeypatch.setattr(config, "set_imap", lambda user, pwd, lookback=None: saved.append((1, user, pwd)))
    monkeypatch.setattr(config, "set_imap2", lambda user, pwd: saved.append((2, user, pwd)))
    monkeypatch.setattr(config, "IMAP_USER", "main@example.com")
    monkeypatch.setattr(config, "IMAP_PASSWORD", "oldpasswordoldpw")
    monkeypatch.setattr(config, "IMAP_PASSWORD_2", "")
    answer = {"ok": True, "msg": ""}
    monkeypatch.setattr(email_client, "try_login", lambda user, password, timeout=8.0: tried.append((user, password)) or dict(answer))
    check = bridge._save_email_checked
    # wrong input never reaches the mail server
    assert check(3, "a@example.com", "abcdabcdabcdabcd")["ok"] is False
    assert check(1, "not an address", "abcdabcdabcdabcd")["ok"] is False
    assert "main job email" in check(2, "MAIN@example.com", "abcdabcdabcdabcd")["msg"]
    assert "App Password" in check(2, "two@example.com", "")["msg"]
    assert tried == [] and saved == []
    # accepted: saved; an empty password means the one already kept
    assert check(1, " main@example.com ", "") == {"ok": True}
    assert tried == [("main@example.com", "oldpasswordoldpw")] and saved == [(1, "main@example.com", "oldpasswordoldpw")]
    # refused: not saved, and the reason does not repeat the password
    answer.update(ok=False, msg="The mail server refused this address and App Password.")
    result = check(2, "two@example.com", "wrongwrongwrongw")
    assert result["ok"] is False and "refused" in result["msg"] and "wrongwrongwrongw" not in result["msg"] and len(saved) == 1
    # the server cannot be reached: saved, with a note
    answer.update(ok=None, msg="The mail server could not be reached, so the password was not tried.")
    result = check(2, "two@example.com", "abcdabcdabcdabcd")
    assert result["ok"] is True and "not tried" in result["note"] and saved[-1] == (2, "two@example.com", "abcdabcdabcdabcd")


def test_the_mailbox_check_answers_the_window(bridge, monkeypatch):
    got = []
    bridge.emailSaved.connect(got.append)
    monkeypatch.setattr(qt_bridge.Bridge, "_save_email_checked", lambda self, box, user, password: (_ for _ in ()).throw(RuntimeError("boom")))
    bridge.saveEmailChecked(2, "two@example.com", "abcdabcdabcdabcd")
    from PySide6.QtTest import QTest
    for _ in range(100):
        QTest.qWait(10)
        time.sleep(0.005)
        if got:
            break
    assert got == [{"ok": False, "msg": "The mailbox could not be saved.", "box": 2}]


def test_an_email_scan_notes_its_own_cost(bridge, monkeypatch):
    usage.record({"cost_usd": 33.5}, tag="earlier")

    def read(jobs, lookback_days=None, progress=None, on_limit=None):
        usage.record({"cost_usd": 0.075}, tag="email")
        return {"scanned": 5, "new_responses": 0, "rejections": 0}

    monkeypatch.setattr(agent5_responses, "process_inbox", read)
    for name in ("backfill_roles", "annotate_progress", "build_report"):
        monkeypatch.setattr(agent5_responses, name, lambda jobs: None)
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)
    bridge._scan()
    last = bridge.lastRun()
    assert last["cost"] == 0.07 or last["cost"] == 0.08
    assert last["cost_of"] == "email scan" and last["scan"].endswith("0 new")


def test_a_run_that_asked_nothing_cost_nothing(bridge, monkeypatch):
    _stub_agents(monkeypatch)
    usage.record({"cost_usd": 12.0}, tag="earlier")
    bridge._set_running(True)
    bridge._pipeline({})
    assert bridge.lastRun()["cost"] == 0.0


def test_pipeline_uses_the_keywords_from_options(bridge, monkeypatch):
    asked = {}

    def search(queries, progress=None, **kw):
        asked.update(queries=list(queries), where=kw["where"], source=kw["source"])
        return []

    _stub_agents(monkeypatch, search)
    bridge._pipeline({"queries": ["qa engineer"], "where": "Brno", "source": "linkedin"})
    assert asked == {"queries": ["qa engineer"], "where": "Brno", "source": "linkedin"}


def test_pipeline_failure_ends_cleanly(bridge, monkeypatch):
    def broken(queries, **kw):
        raise RuntimeError("No usable job source")

    _stub_agents(monkeypatch, broken)
    events = _record(bridge)
    bridge._set_running(True)
    bridge._pipeline({})
    assert events[-1] == ("finished", "search", "Error: No usable job source")
    assert bridge.running is False


# ── connections and settings ────────────────────────────────────────────────
def test_check_connections_answers_through_the_signal(bridge, qapp):
    got = []
    bridge.connectionsReady.connect(lambda info: got.append(dict(info)))
    bridge.checkConnections()
    deadline = time.time() + 5
    while not got and time.time() < deadline:      # the answer is queued to the UI thread
        qapp.processEvents()
        time.sleep(0.02)
    assert got and got[0]["claude"] is True and got[0]["plan"] == "pro"


def test_set_master_cv_copies_the_file(bridge, tmp_path):
    src = tmp_path / "outside" / "My CV.docx"
    src.parent.mkdir()
    src.write_bytes(b"cv")
    result = bridge.setMasterCV("file://" + str(src).replace(" ", "%20"))
    assert result == {"ok": True, "name": "My CV.docx"}
    assert (config.CV_DIR / "My CV.docx").read_bytes() == b"cv"
    assert bridge.setMasterCV(str(config.CV_DIR / "My CV.docx")) == {"ok": True, "name": "My CV.docx"}


def test_set_master_cv_rejects_bad_files(bridge, tmp_path):
    picture = tmp_path / "photo.png"
    picture.write_bytes(b"x")
    assert bridge.setMasterCV(str(picture))["ok"] is False
    missing = bridge.setMasterCV(str(tmp_path / "nope.docx"))
    assert missing == {"ok": False, "msg": "File not found."}


def test_save_options_applies_model_and_lead_floor(bridge):
    bridge.saveOptions({"model": "opus", "min_lead_score": 40})
    assert (config.MODEL, config.MIN_LEAD_SCORE) == ("opus", 40)
    assert bridge.options()["model"] == "opus"


def test_save_companies_tolerates_odd_rows(bridge):
    bridge.saveCompanies([{"name": "Proton", "ats": "greenhouse", "token": "proton"}, 42, None])
    assert bridge.companies() == [{"name": "Proton", "ats": "greenhouse", "token": "proton"}]


def test_save_email_writes_to_env(bridge, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / ".env")
    for name in ("IMAP_USER", "IMAP_PASSWORD"):
        monkeypatch.setattr(config, name, "")
        monkeypatch.delenv(name, raising=False)
    assert bridge.saveEmail("jobs@example.com", "abcdabcdabcdabcd") == {"ok": True}
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "IMAP_USER=jobs@example.com" in env_text and "abcdabcdabcdabcd" not in env_text
    assert vault.get_secret(vault.IMAP_ACCOUNT) == "abcdabcdabcdabcd"
    assert bridge.saveEmail("other@example.com", "") == {"ok": True}        # blank keeps the password
    assert config.IMAP_PASSWORD == "abcdabcdabcdabcd" and config.IMAP_USER == "other@example.com"


# ── data protection ─────────────────────────────────────────────────────────
def test_run_search_refuses_while_the_data_is_locked(bridge, monkeypatch):
    started = _no_thread(monkeypatch)
    bridge.conn["vault"] = "locked"
    result = bridge.runSearch({"where": "Brno"})
    assert result["ok"] is False and result["fix"] == "vault" and started == []


def test_run_search_refuses_files_changed_outside_the_app(bridge, monkeypatch):
    started = _no_thread(monkeypatch)
    bridge.conn["changed_files"] = ["CV rules"]
    result = bridge.runSearch({"where": "Brno"})
    assert result["ok"] is False and result["fix"] == "integrity" and "CV rules" in result["msg"]
    assert started == []


def test_choosing_a_cv_in_the_app_counts_as_approved(bridge, tmp_path):
    integrity.approve()
    src = tmp_path / "outside" / "cv.docx"
    src.parent.mkdir()
    src.write_bytes(b"new cv")
    assert bridge.setMasterCV(str(src))["ok"] is True
    assert integrity.problems() == []


def test_approve_changes_clears_the_warning(bridge):
    config.ensure_dirs()
    config.CV_INSTRUCTION.write_text("rules v1", encoding="utf-8")
    integrity.approve()
    config.CV_INSTRUCTION.write_text("rules v2 - edited by hand", encoding="utf-8")
    assert [f["name"] for f in integrity.problems()] == ["cv_rules"]
    assert "cv_rules" in bridge.approveChanges()
    assert integrity.problems() == []


# ── Stop ────────────────────────────────────────────────────────────────────
def test_stop_does_nothing_when_idle(bridge):
    assert bridge.stopRun() is False


def test_stop_during_scoring_saves_finished_jobs(bridge, monkeypatch):
    rendered = []

    def process(jobs, profile, progress=None, **kw):
        for n, job in enumerate(jobs):
            progress(n, len(jobs))               # the stop point before each job
            job["match_score"] = 80
            if n == 0:
                bridge.stopRun()                 # user presses Stop while job 1 is being written
        return {"scored": len(jobs), "letters": 0, "tailored_cvs": 0, "skipped": 0}

    def search(queries, progress=None, **kw):
        return [store.new_job(id="n1", title="Dev", company="Acme"), store.new_job(id="n2", title="Dev", company="Beta")]

    _stub_agents(monkeypatch, search)
    monkeypatch.setattr(agent3_letters, "process", process)
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: rendered.append(len(jobs)))
    events = _record(bridge)
    bridge._stop.clear()
    bridge._set_running(True)
    bridge._pipeline({})
    assert events[-1][0] == "finished" and events[-1][2].startswith("Stopped")
    assert bridge.running is False and rendered == [2]
    saved = {j["id"]: j["match_score"] for j in store.load_jobs()}
    assert saved == {"n1": 80, "n2": None}                    # job 1 kept, job 2 never started
    assert ("a4", "running") not in [(e[1], e[2]) for e in events if e[0] == "agent"]


def test_stop_during_search_ends_before_scoring(bridge, monkeypatch):
    def search(queries, progress=None, **kw):
        bridge.stopRun()
        progress(0, 3)
        raise AssertionError("the search must stop at the next request")

    _stub_agents(monkeypatch, search)
    monkeypatch.setattr(agent3_letters, "process", lambda *a, **k: pytest.fail("scoring must not start"))
    events = _record(bridge)
    bridge._stop.clear()
    bridge._set_running(True)
    bridge._pipeline({})
    assert events[-1][2].startswith("Stopped") and bridge.running is False


def test_stop_during_email_scan_saves_progress(bridge, monkeypatch):
    def process_inbox(jobs, progress=None, **kw):
        progress(0, 5)
        jobs[0]["status"] = "interview"
        bridge.stopRun()
        progress(1, 5)
        raise AssertionError("the scan must stop before the second email")

    store.save_jobs([store.new_job(id="a", title="Dev", company="Acme", status="waiting")])
    monkeypatch.setattr(agent5_responses, "process_inbox", process_inbox)
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)
    events = _record(bridge)
    bridge._stop.clear()
    bridge._set_running(True)
    bridge._scan()
    assert events[-1] == ("finished", "scan", "Stopped. Emails read before that are saved.")
    assert ("progress", "a5", 0, 5) in events
    assert store.load_jobs()[0]["status"] == "interview" and bridge.running is False


def test_a_new_run_clears_an_old_stop_request(bridge, monkeypatch):
    _no_thread(monkeypatch)
    bridge._stop.set()
    assert bridge.runSearch({"where": "Brno"}) == {"ok": True}
    assert not bridge._stop.is_set()


# ── job detail and follow-ups ───────────────────────────────────────────────
def test_job_detail_and_followup_slots(bridge, qapp):
    from datetime import date, timedelta
    store.save_jobs([store.new_job(id="w", title="QA Engineer", company="Acme", status="waiting",
                                   date_applied=(date.today() - timedelta(days=20)).isoformat(),
                                   description="Python and Kubernetes")])
    detail = bridge.jobDetail("w")
    assert detail["title"] == "QA Engineer" and detail["followup"]["due"] is True
    assert "Kubernetes" in detail["missing"]
    assert bridge.jobDetail("nope") == {}
    draft = bridge.followupDraft("w")
    assert "QA Engineer" in draft["subject"] and "Acme" in draft["body"]
    assert bridge.copyText(draft["body"]) is True
    assert bridge.markFollowedUp("w") is True and bridge.markFollowedUp("nope") is False
    assert bridge.jobDetail("w")["followup"]["due"] is False


def test_email_scan_uses_the_period_from_options(bridge, monkeypatch):
    seen = {}
    monkeypatch.setattr(agent5_responses, "process_inbox",
                        lambda jobs, lookback_days=None, progress=None, on_limit=None: seen.update(days=lookback_days) or
                        {"scanned": 0, "new_responses": 0, "rejections": 0})
    for name in ("backfill_roles", "annotate_progress", "build_report"):
        monkeypatch.setattr(agent5_responses, name, lambda jobs: None)
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)
    assert bridge.options()["scan_days"] == config.IMAP_LOOKBACK_DAYS
    bridge.saveOptions({**bridge.options(), "scan_days": 14})
    bridge._scan()
    assert seen == {"days": 14}


def test_pipeline_drops_a_lead_already_listed_from_another_board(bridge, monkeypatch):
    store.save_jobs([store.new_job(id="jobscz-1", title="IT Helpdesk Specialist", company="RÖDL", match_score=35)])

    def search(queries, progress=None, **kw):
        return [store.new_job(id="pracecz-9", title="IT Helpdesk Specialist", company="Rödl"),
                store.new_job(id="new", title="QA Engineer", company="Beta")]

    _stub_agents(monkeypatch, search)
    events = _record(bridge)
    bridge._pipeline({})
    assert sorted(j["id"] for j in store.load_jobs()) == ["jobscz-1", "new"]
    assert ("agent", "a2", "done") in [e[:3] for e in events]


def test_pipeline_passes_full_time_only_from_options(bridge, monkeypatch):
    seen = []

    def search(queries, progress=None, **kw):
        seen.append(kw["full_time_only"])
        return []

    _stub_agents(monkeypatch, search)
    bridge._pipeline({})
    bridge._pipeline({"full_time_only": False})
    assert seen == [True, False]


def test_search_and_scan_results_are_kept_for_the_last_run_card(bridge, monkeypatch):
    _stub_agents(monkeypatch)
    bridge._pipeline({})
    saved = bridge.lastRun()
    assert saved["found"] == "+1 new" and (saved["letters"], saved["cvs"]) == (1, 1) and saved["when"]
    assert vault.file_is_encrypted(config.DATA_DIR / "last_run.json")
    monkeypatch.setattr(agent5_responses, "process_inbox",
                        lambda jobs, lookback_days=None, progress=None, on_limit=None:
                        {"scanned": 9, "new_responses": 2, "rejections": 1})
    for name in ("backfill_roles", "annotate_progress", "build_report"):
        monkeypatch.setattr(agent5_responses, name, lambda jobs: None)
    bridge._scan()
    again = qt_bridge.Bridge().lastRun()                       # a fresh start still knows
    assert again["scan"].endswith("· 2 new") and again["found"] == "+1 new"


# ── dates, notes, pasted replies, CV comparison ─────────────────────────────
def test_reminder_slot_sends_one_notification_per_due_date(bridge, monkeypatch):
    from datetime import date, timedelta

    from jobhelper import notify, store
    sent = []
    monkeypatch.setattr(notify, "send", lambda message, subtitle="": sent.append((message, subtitle)) or True)
    store.save_jobs([store.new_job(id="a", title="Developer", company="Acme", status="waiting"),
                     store.new_job(id="b", title="Tester", company="Beta", status="waiting")])
    today, later = date.today().isoformat(), (date.today() + timedelta(days=9)).isoformat()
    assert bridge.setEvent("a", today, "", "deadline", "")["ok"] is True
    assert bridge.setEvent("b", later, "09:00", "interview", "")["ok"] is True
    assert bridge.setEvent("a", "tomorrow", "", "deadline", "")["ok"] is False
    assert [u["id"] for u in bridge.upcoming()] == ["a", "b"]
    assert bridge.remind() == 1 and bridge.remind() == 0
    assert sent == [("Today: deadline · Acme", "Reminder")]
    assert bridge.clearEvent("a")["ok"] is True and [u["id"] for u in bridge.upcoming()] == ["b"]


def test_notes_and_compare_slots(bridge):
    from jobhelper import planner, store
    store.save_jobs([store.new_job(id="a", title="Developer", company="Acme", status="waiting")])
    assert bridge.saveCompanyNotes("Acme", {"contact": "Jana"}) == {"ok": True}
    assert planner.company_notes("ACME")["contact"] == "Jana"
    assert bridge.saveCompanyNotes("", {"contact": "Jana"})["ok"] is False
    assert bridge.cvCompare("a")["ok"] is False                 # no adapted CV: a reason, not a crash


def test_add_reply_answers_through_the_signal_even_on_failure(bridge, monkeypatch, qapp):
    import time

    from jobhelper import store, ui_api as api_module
    store.save_jobs([store.new_job(id="a", title="Developer", company="Acme", status="waiting")])
    got = []
    bridge.replyReady.connect(got.append)

    def boom(self, job_id, text):
        raise RuntimeError("disk full")
    monkeypatch.setattr(api_module.Api, "add_reply", boom)
    bridge.addReply("a", "Thank you for applying, we will get back to you soon.")
    for _ in range(200):
        time.sleep(0.01)
        qapp.processEvents()
        if got:
            break
    assert got == [{"ok": False, "msg": "disk full", "job_id": "a"}]


def test_a_search_saves_what_it_filtered_out_and_counts_it(bridge, monkeypatch):
    from jobhelper import store

    def search(queries, progress=None, dropped=None, **kw):
        agent2_search.note_dropped(dropped, {"title": "Intern", "company": "Acme", "url": "https://example.com/i"},
                                   "skip word", 'The title has a word you skip ("intern").')
        return [store.new_job(id="n1", title="Dev", company="Acme"),
                store.new_job(id="n2", title="QA Engineer", company="Beta")]
    _stub_agents(monkeypatch, search)
    store.save_jobs([store.new_job(id="old", title="QA Engineer", company="Beta", status="waiting")])
    bridge._pipeline({})
    saved = bridge.filteredOut()
    assert [(r["group"], r["title"]) for r in saved["rows"]] == [("skip word", "Intern"), ("already applied", "QA Engineer")]
    assert bridge.lastRun()["filtered"] == 2
    opened = []
    monkeypatch.setattr(ui_api.Api, "_open", lambda self, target: opened.append(target))
    assert bridge.openFiltered(0) == {"ok": True} and opened == ["https://example.com/i"]
    assert bridge.openFiltered(1) == {"ok": False}


def test_pipeline_passes_level_words_and_years_from_options(bridge, monkeypatch):
    seen = []

    def search(queries, progress=None, **kw):
        seen.append((kw["level_words"], kw["max_years"]))
        return []
    _stub_agents(monkeypatch, search)
    bridge._pipeline({})
    bridge._pipeline({"level_words": [], "max_years": 0})
    assert "senior" in seen[0][0] and seen[0][1] == 4                 # a junior CV: the usual words and limit
    assert seen[1] == ([], 0)


def test_run_search_needs_a_city(bridge, monkeypatch):
    _no_thread(monkeypatch)
    got = bridge.runSearch({})
    assert got == {"ok": False, "fix": "city", "msg": "Choose the city to search in first (Options)."}
    assert bridge.runSearch({"where": "   "})["fix"] == "city"
    bridge._api.save_options({"where": "Vienna"})                        # a saved city is enough
    assert bridge.runSearch({}) == {"ok": True}


def test_draft_answers_reports_through_the_signal(bridge, monkeypatch, qapp):
    import time

    from jobhelper import store, ui_api as api_module
    store.save_jobs([store.new_job(id="a", title="Developer", company="Acme")])
    got = []
    bridge.answersReady.connect(got.append)
    monkeypatch.setattr(api_module.Api, "make_form_answers", lambda self, job_id, text: {"ok": True, "count": 2, "to_check": 1})
    bridge.draftAnswers("a", "Why us?\nSalary?")
    for _ in range(200):
        time.sleep(0.01)
        qapp.processEvents()
        if got:
            break
    assert got == [{"ok": True, "count": 2, "to_check": 1, "job_id": "a"}]

    def boom(self, job_id, text):
        raise RuntimeError("disk full")
    monkeypatch.setattr(api_module.Api, "make_form_answers", boom)
    bridge.draftAnswers("a", "Why us?")
    for _ in range(200):
        time.sleep(0.01)
        qapp.processEvents()
        if len(got) == 2:
            break
    assert got[1] == {"ok": False, "msg": "disk full", "job_id": "a"}
    assert bridge.formAnswers("a")["company"] == "Acme" and bridge.saveFormAnswers("a", [{"question": "Q?", "answer": "A."}])["count"] == 1


# ── score again ─────────────────────────────────────────────────────────────
def test_score_all_again_runs_like_a_search_and_reports(bridge, monkeypatch):
    from jobhelper import llm, store
    monkeypatch.setattr(agent1_cv, "load_profile", lambda current_only=False: {"target_roles": ["Python developer"]})
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)
    store.save_jobs([store.new_job(id="e", title="Economist", company="A", match_score=80, description="x"),
                     store.new_job(id="d", title="Developer", company="B", match_score=60, description="y"),
                     store.new_job(id="app", title="QA", company="C", status="waiting", match_score=70)])
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"scores": [{"id": "J1", "match_score": 30, "match_reason": "Another field."},
                                                                   {"id": "J2", "match_score": 72, "match_reason": "Fits."}]})
    events = _record(bridge)
    assert bridge.rescorePlan() == {"jobs": 2, "calls": 1}
    bridge._rescore()
    saved = {j["id"]: j["match_score"] for j in store.load_jobs()}
    assert saved == {"e": 30, "d": 72, "app": 70}                              # an application is never rescored
    finished = [e for e in events if e[0] == "finished"]
    assert finished[-1][1:] == ("rescore", "Scored 2 jobs again: 2 changed (1 lower, 1 higher).")
    assert ("agent", "a3", "done") in [e[:3] for e in events] and bridge._api.live is None


def test_score_all_again_refuses_when_there_is_nothing_or_no_sign_in(bridge, monkeypatch):
    from jobhelper import store
    _no_thread(monkeypatch)
    assert bridge.rescoreAll() == {"ok": False, "msg": "There are no scored new jobs to score again."}
    store.save_jobs([store.new_job(id="e", title="Economist", company="A", match_score=80)])
    bridge.conn["claude"] = False
    assert bridge.rescoreAll()["fix"] == "claude"
    bridge.conn["claude"] = True
    assert bridge.rescoreAll() == {"ok": True}
    assert bridge.rescoreAll() == {"ok": False, "msg": "A run is already in progress."}


def test_score_again_for_one_job_answers_through_the_signal(bridge, monkeypatch, qapp):
    import time

    from jobhelper import ui_api as api_module
    got = []
    bridge.rescoreReady.connect(got.append)
    monkeypatch.setattr(api_module.Api, "rescore_one", lambda self, job_id: {"ok": True, "score": 30, "before": 80})
    bridge.rescoreJob("e")
    for _ in range(200):
        time.sleep(0.01)
        qapp.processEvents()
        if got:
            break
    assert got == [{"ok": True, "score": 30, "before": 80, "job_id": "e"}]


# ── the bridge and the main window are put together from parts ──────────────
def test_every_bridge_call_in_the_window_is_a_real_slot_and_no_name_is_defined_twice():
    import re

    from jobhelper import bridge_jobs, bridge_runs
    parts = [qt_bridge.Bridge, bridge_runs.RunSlots, bridge_jobs.JobSlots]
    seen = {}
    for part in parts:
        for name in vars(part):
            if name.startswith("__") or name == "staticMetaObject":
                continue
            assert name not in seen, f"{name} is defined in {seen[name].__name__} and in {part.__name__}"
            seen[name] = part
    root = Path(qt_bridge.__file__).resolve().parent.parent / "ui_qt"
    text = "\n".join(p.read_text(encoding="utf-8") for p in list(root.glob("*.qml")) + list(root.glob("*.js")))
    called = set(re.findall(r"\bbridge\.([A-Za-z_]\w*)\(", text)) - {"running"}        # `running` is a property, named in a comment
    meta = qt_bridge.Bridge.staticMetaObject
    slots = {bytes(meta.method(i).name()).decode() for i in range(meta.methodCount())}
    assert len(called) > 80 and called <= slots, sorted(called - slots)


def test_the_main_window_is_made_of_its_parts():
    root = Path(qt_bridge.__file__).resolve().parent.parent / "ui_qt"
    main = (root / "Main.qml").read_text(encoding="utf-8")
    for part in ("NavPanel", "StagePanel", "StatusPanel", "PipelineBar"):
        assert (root / f"{part}.qml").is_file() and f"{part} {{ id: " in main, part
    assert 'import "views.js" as Views' in main and len(main.splitlines()) < 600
    stage = (root / "StagePanel.qml").read_text(encoding="utf-8")
    assert "theme: theme;" not in stage            # inside a part that would bind a robot's theme to itself
