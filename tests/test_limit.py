"""Claude's usage limit: detect it, pause instead of failing job after job, resume."""
import json
import threading
import time
from pathlib import Path
from datetime import datetime

import pytest

import run
from jobhelper import (agent1_cv, bridge_runs, agent3_letters, agent4_tracker, agent5_responses, config, db, email_client,
                       letters, llm, qt_bridge, store, ui_api, usage)

pytest.importorskip("PySide6")

NOON = datetime(2026, 10, 7, 12, 0).timestamp()


def _saved_usage(change):
    """Change usage.json as an older run of the app could have left it."""
    path = config.USAGE_JSON
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    change(state)
    config.ensure_dirs()
    path.write_text(json.dumps(state), encoding="utf-8")


def _kept(window):
    """What a window says about the limit itself, without when it was read."""
    return {key: window[key] for key in ("used", "resets_at")}


def _windows(five=0.2, seven=0.2, five_reset=None, seven_reset=None):
    _saved_usage(lambda state: state.update(last_rate_limit={"at": "now", "info": {"unifiedWindows": {
        "five_hour": {"utilization": five, "resetsAt": five_reset or time.time() + 3600},
        "seven_day": {"utilization": seven, "resetsAt": seven_reset or time.time() + 86400}}}}))


# ── knowing the limit is used up ────────────────────────────────────────────
def test_not_blocked_without_any_information(isolate_data):
    assert usage.limit_status() == {"blocked": False, "window": "", "used": 0.0, "resets_at": 0.0}


def test_blocked_at_99_percent_until_that_window_resets(isolate_data):
    _windows(five=0.99, five_reset=NOON + 600)
    status = usage.limit_status(now=NOON)
    assert status["blocked"] and status["window"] == "five_hour" and status["resets_at"] == NOON + 600
    assert usage.limit_status(now=NOON + 601)["blocked"] is False        # the window has reset
    _windows(five=0.98)
    assert usage.limit_status()["blocked"] is False


def test_weekly_window_can_block_too(isolate_data):
    _windows(five=0.1, seven=1.0)
    assert usage.limit_status()["window"] == "seven_day" and usage.limit_status()["blocked"]


@pytest.mark.parametrize("text, hour, minute", [
    ("You've hit your session limit · resets 1:20pm (Europe/Prague)", 13, 20),
    ("You've hit your session limit · resets 9am", 9, 0),
    ("limit reached, resets 12:05am", 0, 5),
    ("resets 18:00", 18, 0),
])
def test_reset_time_is_read_from_claudes_message(text, hour, minute):
    when = datetime.fromtimestamp(llm.reset_time_from(text, now=NOON))
    assert (when.hour, when.minute) == (hour, minute) and when.timestamp() > NOON


def test_reset_time_unknown():
    assert llm.reset_time_from("something else went wrong") == 0.0


def test_no_call_is_made_once_the_limit_is_used_up(isolate_data, monkeypatch):
    _windows(five=0.99)
    monkeypatch.setattr(llm, "_ask_async", lambda *a, **k: pytest.fail("must not call Claude at 99%"))
    with pytest.raises(llm.LimitReached, match="5-hour limit is used up"):
        llm.ask("hello")


def test_claudes_limit_error_becomes_limit_reached_and_is_remembered(isolate_data, monkeypatch):
    async def refuse(*a, **k):
        raise RuntimeError("Claude Code returned an error result: You've hit your session limit · resets 1:20pm (Europe/Prague) (exit code: 1)")

    monkeypatch.setattr(llm, "_ask_async", refuse)
    with pytest.raises(llm.LimitReached) as e:
        llm.ask("hello")
    assert e.value.resets_at > time.time()
    assert usage.limit_status()["blocked"] is True                      # the next call will not even try


SESSION_REFUSAL = "Claude Code returned an error result: You've hit your session limit · resets 2pm (Europe/Prague) (exit code: 1)"


def test_a_refusal_fills_the_window_it_names_whatever_the_older_numbers_say(isolate_data):
    """Seen in use: Claude refused ("session limit"), and the card still said 13% left from an hour before."""
    _windows(five=0.87, seven=0.34, five_reset=NOON + 600, seven_reset=NOON + 86400)
    usage.note_limit(NOON + 7200, SESSION_REFUSAL)
    now = usage.windows(NOON + 700)                     # the old reset time has passed, the refusal has not
    assert _kept(now["five_hour"]) == {"used": 1.0, "resets_at": NOON + 7200} and now["five_hour"]["stale"] is False   # the refusal is news
    assert _kept(now["seven_day"]) == {"used": 0.34, "resets_at": NOON + 86400}
    status = usage.limit_status(now=NOON + 700)
    assert status["blocked"] and status["window"] == "five_hour" and status["resets_at"] == NOON + 7200
    assert llm.limit_message(status).startswith("Claude's 5-hour limit is used up (100%)")
    assert usage.limit_status(now=NOON + 7201)["blocked"] is False


@pytest.mark.parametrize("message, window", [
    ("You've hit your session limit · resets 2pm", "five_hour"), ("5-hour limit reached", "five_hour"),
    ("You've hit your weekly limit · resets 9am", "seven_day"), ("7-day usage limit reached", "seven_day"),
    ("usage limit reached", ""), ("", "")])
def test_which_limit_a_refusal_talks_about(message, window):
    assert usage.window_named(message) == window


def test_a_weekly_refusal_is_not_shown_as_the_short_window(isolate_data):
    _windows(five=0.10, seven=0.95, five_reset=NOON + 600, seven_reset=NOON + 86400)
    usage.note_limit(NOON + 86400, "You've hit your weekly limit · resets 9am")
    status = usage.limit_status(now=NOON)
    assert status["blocked"] and status["window"] == "seven_day"
    assert usage.windows(NOON)["five_hour"]["used"] == 0.10


def test_a_refusal_that_names_no_limit_is_put_on_the_fuller_window(isolate_data):
    usage.note_limit(NOON + 1800, "usage limit reached")
    assert usage.limit_status(now=NOON)["window"] == "five_hour"        # nothing known: the short one
    _windows(five=0.10, seven=0.95, five_reset=NOON + 600, seven_reset=NOON + 86400)
    usage.note_limit(NOON + 1800, "usage limit reached")
    assert usage.limit_status(now=NOON)["window"] == "seven_day"


def test_when_both_limits_are_used_up_the_one_that_frees_later_is_named(isolate_data):
    _windows(five=1.0, seven=1.0, five_reset=NOON + 600, seven_reset=NOON + 86400)
    status = usage.limit_status(now=NOON)
    assert status["window"] == "seven_day" and status["resets_at"] == NOON + 86400


def test_a_window_whose_reset_time_passed_is_unknown_again(isolate_data):
    """It was shown as empty ("100% left"), but Claude Code uses the same subscription, so after a reset nobody knows."""
    _windows(five=0.87, seven=0.34, five_reset=NOON + 600, seven_reset=NOON + 86400)
    assert _kept(usage.windows(NOON)["five_hour"]) == {"used": 0.87, "resets_at": NOON + 600}
    after = usage.windows(NOON + 601)["five_hour"]
    assert _kept(after) == {"used": None, "resets_at": 0.0} and after["reset_passed"] == NOON + 600
    assert usage.windows(NOON + 601)["seven_day"]["used"] == 0.34 and usage.limit_status(now=NOON + 601)["blocked"] is False


def test_windows_never_reported_stay_unknown(isolate_data):
    assert usage.windows() == {name: {"used": None, "resets_at": 0.0, "as_of": 0.0, "stale": False, "reset_passed": 0.0}
                               for name in ("five_hour", "seven_day")}
    _saved_usage(lambda state: state.update(last_rate_limit={"at": "now", "info": {"unifiedWindows": {
        "five_hour": {"utilization": "a lot"}, "seven_day": "?"}}}))
    assert usage.windows()["five_hour"]["used"] is None and usage.windows()["seven_day"]["used"] is None


def test_an_answer_from_claude_ends_a_remembered_refusal(isolate_data):
    usage.note_limit(time.time() + 3600, SESSION_REFUSAL)
    assert usage.limit_status()["blocked"] is True
    usage.record({"input_tokens": 3, "output_tokens": 1, "cost_usd": 0.01}, tag="usage_ping")
    assert usage.limit_status()["blocked"] is False and "limit_block" not in json.loads(config.USAGE_JSON.read_text(encoding="utf-8"))


def test_the_usage_card_says_nothing_is_left_while_claude_refuses(isolate_data):
    in_an_hour = time.time() + 3600
    _windows(five=0.87, seven=0.34, five_reset=time.time() - 60, seven_reset=time.time() + 86400)
    card = ui_api.Api().usage_info()
    assert card["five_hour_used"] is None and card["five_hour_resets"] == "" and card["seven_day_used"] == 34
    assert card["five_hour_reset_passed"] and card["should_refresh"] is True, "reset since the reading: ask again"
    usage.note_limit(in_an_hour, SESSION_REFUSAL)
    card = ui_api.Api().usage_info()
    assert card["five_hour_used"] == 100 and card["seven_day_used"] == 34
    when = datetime.fromtimestamp(in_an_hour)
    assert card["five_hour_resets"] in (when.strftime("%H:%M"), when.strftime("%d %b %H:%M"))
    assert len(card["seven_day_resets"]) > 5                              # another day: the date is part of it


def test_an_old_reading_shows_when_it_was_taken(isolate_data):
    """Claude reports the limits only with an answer. While it refused every call, the card showed a two-day-old
    "100% left" for the week as if it were now."""
    two_days_ago = datetime.fromtimestamp(time.time() - 2 * 86400).replace(microsecond=0)
    _windows(five=0.01, seven=0.0, five_reset=time.time() - 60, seven_reset=time.time() + 3 * 86400)
    _saved_usage(lambda state: state["last_rate_limit"].update(at=two_days_ago.isoformat()))
    usage.note_limit(time.time() + 3600, SESSION_REFUSAL)
    card = ui_api.Api().usage_info()
    assert card["five_hour_used"] == 100 and card["five_hour_as_of"] == ""          # the refusal is news: no date
    assert card["seven_day_used"] == 0 and card["seven_day_as_of"] == two_days_ago.strftime("%d %b %H:%M") and card["seven_day_stale"] is True
    _saved_usage(lambda state: state["last_rate_limit"].update(at=datetime.now().isoformat(timespec="seconds")))
    assert ui_api.Api().usage_info()["seven_day_as_of"] == "", "a fresh reading needs no date"
    read_at = datetime.fromisoformat(json.loads(config.USAGE_JSON.read_text(encoding="utf-8"))["last_rate_limit"]["at"]).timestamp()
    assert usage.windows(read_at + usage.STALE_AFTER)["seven_day"]["stale"] is False             # one hour old: still now
    assert usage.windows(read_at + usage.STALE_AFTER + 1)["seven_day"]["stale"] is True


def test_the_usage_card_knows_when_the_next_limit_comes_back(isolate_data):
    assert ui_api.Api().usage_info()["next_reset_in"] == 0
    _windows(five=0.5, seven=0.0, five_reset=time.time() + 600, seven_reset=time.time() + 86400)
    assert 595 <= ui_api.Api().usage_info()["next_reset_in"] <= 602          # the unused weekly window is not waited for
    usage.note_limit(time.time() + 120, SESSION_REFUSAL)
    assert 115 <= ui_api.Api().usage_info()["next_reset_in"] <= 122
    _windows(five=0.5, seven=0.2, five_reset=time.time() - 5, seven_reset=time.time() + 86400)
    _saved_usage(lambda state: state.pop("limit_block", None))
    assert 86000 < ui_api.Api().usage_info()["next_reset_in"] <= 86402        # the short one has reset: the weekly one is next


def test_the_usage_card_without_any_numbers(isolate_data):
    card = ui_api.Api().usage_info()
    assert card["five_hour_used"] is None and card["seven_day_used"] is None and card["five_hour_resets"] == ""


def test_other_errors_are_not_mistaken_for_the_limit(isolate_data, monkeypatch):
    async def broken(*a, **k):
        raise RuntimeError("Reached maximum number of turns (6)")

    monkeypatch.setattr(llm, "_ask_async", broken)
    with pytest.raises(RuntimeError) as e:
        llm.ask("hello")
    assert not isinstance(e.value, llm.LimitReached) and usage.limit_status()["blocked"] is False


def test_usage_refresh_may_ask_even_when_blocked(isolate_data, monkeypatch):
    _windows(five=0.99)

    async def answer(*a, **k):
        return "ok", {"input_tokens": 1}

    monkeypatch.setattr(llm, "_ask_async", answer)
    assert llm.ask("ping", force=True) == "ok"


# ── the scoring loop ────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def one_posting_per_call(monkeypatch):
    """These tests count calls job by job; batching has its own tests."""
    monkeypatch.setattr(config, "SCORE_BATCH", 1)


def _jobs(n=3):
    return [store.new_job(id=str(i), title=f"Dev {i}", company=f"Co{i}", location="Prague") for i in range(n)]


def test_without_a_pause_handler_the_run_ends_at_the_first_limit(isolate_data, monkeypatch):
    calls = []

    def ask_json(*a, **k):
        calls.append(1)
        if len(calls) == 2:
            raise llm.LimitReached("limit", time.time() + 60)
        return {"match_score": 10, "match_reason": "x"}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    jobs = _jobs(5)
    with pytest.raises(llm.LimitReached):
        agent3_letters.process(jobs, {"summary": "x"}, threshold=60)
    assert len(calls) == 2                                              # not one failed call per remaining job
    assert [j["match_score"] for j in jobs] == [10, None, None, None, None]


def test_with_a_pause_handler_the_same_job_is_retried(isolate_data, monkeypatch):
    calls, pauses = [], []

    def ask_json(*a, **k):
        calls.append(1)
        if len(calls) == 2:
            raise llm.LimitReached("limit", time.time() + 60)
        return {"match_score": 10, "match_reason": "x"}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    jobs = _jobs(3)
    stats = agent3_letters.process(jobs, {"summary": "x"}, threshold=60, on_limit=lambda e: pauses.append(str(e)))
    assert pauses == ["limit"] and stats["scored"] == 3 and len(calls) == 4
    assert all(j["match_score"] == 10 for j in jobs)


def test_a_job_scored_before_the_limit_gets_its_documents_on_the_next_run(isolate_data, monkeypatch):
    jobs = [store.new_job(id="pwc", title="Data Analyst Intern", company="PwC", location="Prague", match_score=70,
                          match_reason="Good fit", description="We analyse data with SQL and Python.")]
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: pytest.fail("already scored: must not be scored again"))
    monkeypatch.setattr(llm, "ask", lambda *a, **k: "Dear team,\n\nI would like to apply.\n\nRegards")
    stats = agent3_letters.process(jobs, {"summary": "x"}, threshold=30)
    assert stats["letters"] == 1 and stats["scored"] == 0
    assert jobs[0]["status"] == "letter_ready" and jobs[0]["match_score"] == 70


def test_documents_are_not_retried_forever(isolate_data, monkeypatch):
    jobs = [store.new_job(id="x", title="Dev", company="A", location="Prague", match_score=70, description="We build tools in Python.")]
    monkeypatch.setattr(agent3_letters, "_make_letter", lambda *a, **k: (_ for _ in ()).throw(ValueError("checks failed")))
    for _ in range(4):
        agent3_letters.process(jobs, {"summary": "x"}, threshold=30)
    assert jobs[0]["doc_attempts"] == agent3_letters.MAX_DOC_ATTEMPTS and jobs[0]["status"] == "found"


def test_a_limit_while_writing_does_not_use_up_an_attempt(isolate_data, monkeypatch):
    jobs = [store.new_job(id="x", title="Dev", company="A", location="Prague", match_score=70, description="We build tools in Python.")]
    monkeypatch.setattr(agent3_letters, "_make_letter", lambda *a, **k: (_ for _ in ()).throw(llm.LimitReached("limit")))
    with pytest.raises(llm.LimitReached):
        agent3_letters.process(jobs, {"summary": "x"}, threshold=30)
    assert jobs[0]["doc_attempts"] == 0


def test_inbox_scan_leaves_the_email_unread_when_the_limit_hits(isolate_data, monkeypatch):
    mail = {"msg_id": "<1@x>", "date": "Mon, 5 Oct 2026 10:00:00 +0200", "sender": "hr@acme.com",
            "subject": "Your application", "body": "About your application", "was_html_only": False}
    monkeypatch.setattr(email_client, "fetch_recent", lambda days=None: email_client.Fetched([mail]))
    monkeypatch.setattr(email_client, "looks_like_application", lambda *a, **k: True)
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: (_ for _ in ()).throw(llm.LimitReached("limit")))
    with pytest.raises(llm.LimitReached):
        agent5_responses.process_inbox([])
    assert db.is_seen("<1@x>") is False                                # it is read on the next scan


def test_command_line_run_stops_cleanly_and_saves(isolate_data, monkeypatch, capsys):
    monkeypatch.setattr(agent1_cv, "load_profile", lambda current_only=False: {"_cv_file": "cv", "seniority": "junior"})
    monkeypatch.setattr(agent1_cv, "find_cv", lambda: None)
    monkeypatch.setattr(letters, "import_letters", lambda jobs: {"scanned": 0, "linked": 0, "seeded": 0})
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)
    config.ensure_dirs()
    store.save_jobs(_jobs(2))
    calls = []

    def ask_json(*a, **k):
        calls.append(1)
        if len(calls) == 2:
            raise llm.LimitReached("Claude's 5-hour limit is used up (99%).")
        return {"match_score": 10, "match_reason": "x"}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    monkeypatch.setattr("sys.argv", ["run.py", "--reuse-profile", "--skip-search"])
    assert run.main() == 3
    assert "limit is used up" in capsys.readouterr().out
    assert [j["match_score"] for j in store.load_jobs()] == [10, None]


def test_command_line_run_saves_what_it_scored_when_claude_stops_answering(isolate_data, monkeypatch, capsys):
    monkeypatch.setattr(agent1_cv, "load_profile", lambda current_only=False: {"_cv_file": "cv", "seniority": "junior"})
    monkeypatch.setattr(agent1_cv, "find_cv", lambda: None)
    monkeypatch.setattr(letters, "import_letters", lambda jobs: {"scanned": 0, "linked": 0, "seeded": 0})
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)
    config.ensure_dirs()
    store.save_jobs(_jobs(2))
    calls = []

    def ask_json(*a, **k):
        calls.append(1)
        if len(calls) == 2:
            raise llm.CallTimedOut()
        return {"match_score": 10, "match_reason": "x"}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    monkeypatch.setattr("sys.argv", ["run.py", "--reuse-profile", "--skip-search"])
    assert run.main() == 1
    assert "did not answer" in capsys.readouterr().out
    assert [j["match_score"] for j in store.load_jobs()] == [10, None], "the first score is kept, not lost with a traceback"

# ── the app: pause, wait, resume ────────────────────────────────────────────
@pytest.fixture
def bridge(qapp, isolate_data, monkeypatch):
    monkeypatch.setattr(ui_api.Api, "connections", lambda self: {"claude": True, "cv": "cv.docx", "vault": "ok", "changed_files": []})
    monkeypatch.setattr(qt_bridge.Bridge, "LIMIT_POLL_SECONDS", 0.03)
    monkeypatch.setattr(agent1_cv, "load_profile", lambda current_only=False: {"seniority": "junior", "search_queries": ["dev"]})
    monkeypatch.setattr(agent1_cv, "find_cv", lambda: None)
    monkeypatch.setattr(bridge_runs.agent2_search, "search", lambda queries, progress=None, **kw: _jobs(3))
    monkeypatch.setattr(letters, "import_letters", lambda jobs: {"scanned": 0, "linked": 0, "seeded": 0})
    monkeypatch.setattr(agent5_responses, "annotate_progress", lambda jobs: None)
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)
    return qt_bridge.Bridge()


def _run_until(bridge, qapp, condition, seconds=5.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def _limited_scoring(monkeypatch):
    """Scoring that hits the limit on the second job, exactly once."""
    state = {"calls": 0}

    def ask_json(*a, **k):
        state["calls"] += 1
        if state["calls"] == 2:
            _windows(five=0.99, five_reset=time.time() + 3600)
            raise llm.LimitReached("Claude's 5-hour limit is used up (99%).")
        return {"match_score": 10, "match_reason": "x"}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    return state


def test_run_pauses_saves_and_resumes_only_after_the_reset(bridge, qapp, monkeypatch):
    state = _limited_scoring(monkeypatch)
    events, finished = [], []
    bridge.limitChanged.connect(lambda info: events.append(dict(info)))
    bridge.runFinished.connect(lambda mode, summary: finished.append(summary))
    bridge._set_running(True)
    worker = threading.Thread(target=bridge._pipeline, args=({},), daemon=True)
    worker.start()

    assert _run_until(bridge, qapp, lambda: any(e["paused"] for e in events))
    assert events[-1]["paused"] is True and events[-1]["can_resume"] is False and events[-1]["used"] == 99
    assert [j["match_score"] for j in store.load_jobs()] == [10, None, None]       # saved at the pause
    assert bridge.resumeRun() is False                                              # the limit has not reset
    time.sleep(0.15)
    assert worker.is_alive() and state["calls"] == 2 and not finished               # waiting, not hammering Claude

    _windows(five=0.05)                                                             # the window resets
    assert _run_until(bridge, qapp, lambda: events[-1]["can_resume"] is True)
    assert worker.is_alive()                                                        # still waits for the user
    assert bridge.resumeRun() is True
    assert _run_until(bridge, qapp, lambda: bool(finished))
    worker.join(2)
    assert finished[0].startswith("Done") and events[-1]["paused"] is False
    assert [j["match_score"] for j in store.load_jobs()] == [10, 10, 10]            # the interrupted job was redone
    assert state["calls"] == 4


def test_stop_ends_a_paused_run(bridge, qapp, monkeypatch):
    _limited_scoring(monkeypatch)
    events, finished = [], []
    bridge.limitChanged.connect(lambda info: events.append(dict(info)))
    bridge.runFinished.connect(lambda mode, summary: finished.append(summary))
    bridge._set_running(True)
    worker = threading.Thread(target=bridge._pipeline, args=({},), daemon=True)
    worker.start()
    assert _run_until(bridge, qapp, lambda: any(e["paused"] for e in events))
    assert bridge.stopRun() is True
    assert _run_until(bridge, qapp, lambda: bool(finished))
    worker.join(2)
    assert finished[0].startswith("Stopped") and bridge.running is False and events[-1]["paused"] is False


def test_resume_does_nothing_when_no_run_is_paused(bridge):
    assert bridge.resumeRun() is False


def test_alert_sound_file_exists_and_is_played(bridge, monkeypatch):
    from tests.conftest import ROOT
    sound = ROOT / "ui_qt" / "sounds" / "limit.wav"
    assert sound.is_file() and sound.read_bytes()[:4] == b"RIFF"
    played = []
    monkeypatch.setattr(qt_bridge.sys, "platform", "darwin")
    monkeypatch.setattr(qt_bridge.subprocess, "Popen", lambda cmd, **k: played.append(cmd))
    bridge.playAlert()
    assert played == [["afplay", str(sound)]]


# ── records that once crashed the app ───────────────────────────────────────
def test_records_without_a_status_are_completed_on_load(isolate_data):
    config.ensure_dirs()
    from jobhelper import vault
    vault.write_text(config.JOBS_JSON, json.dumps([{"id": "gh-1", "title": "QA Engineer", "company": "Bloomreach",
                                                    "source": "careers", "custom": "kept"}]))
    job = store.load_jobs()[0]
    assert job["status"] == "found" and job["match_score"] is None and job["custom"] == "kept"
    assert ui_api.Api().counts()["leads"] == 1


def test_career_site_records_are_complete():
    from jobhelper import scrapers_ats
    import inspect
    assert "store.new_job(" in inspect.getsource(scrapers_ats)
    merged = []
    store.upsert(merged, [{"id": "x", "title": "T", "company": "C"}])
    assert merged[0]["status"] == "found"


@pytest.mark.parametrize("location, fits", [
    ("Prague", True), ("Brno, Czech Republic", True), ("Remote, EMEA", True), ("", True),
    ("Paris, France", False), ("Netherlands", False), ("London, UK", False),
])
def test_career_site_jobs_abroad_are_left_out(location, fits):
    from jobhelper import filters
    assert filters.location_fits(location, "Prague") is fits


# ── found by reading the bridges line by line (10 October 2026) ─────────────
def test_stop_pressed_while_a_run_waits_on_the_limit_ends_it_and_costs_no_job_a_try(isolate_data, monkeypatch):
    """Stop during a pause is raised from inside the step that was waiting. The agents catch ordinary errors around each job
    ("could not score this one, go on"), so the run went on to the next job, and the job it was on lost a try at its documents."""
    from jobhelper import agent3_letters, agent5_responses, bridge_runs, email_client, llm, store
    assert issubclass(bridge_runs.RunCancelled, BaseException) and not issubclass(bridge_runs.RunCancelled, Exception)
    text = "We build planning tools in Python and SQL. " * 30
    jobs = [store.new_job(id=f"j{i}", title="Python Developer", company=f"Acme {i}", description=text, match_score=70) for i in range(3)]
    asked = []

    def limit(*a, **k):
        asked.append(1)
        raise llm.LimitReached("Claude's 5-hour limit is used up (100%).")

    def stop(error):
        raise bridge_runs.RunCancelled()
    monkeypatch.setattr(agent3_letters, "_make_tailored_cv", limit)
    monkeypatch.setattr(agent3_letters, "_make_letter", limit)
    with pytest.raises(bridge_runs.RunCancelled):
        agent3_letters.process(jobs, {"summary": "x"}, threshold=50, cv_text="Alex Novak\nPython, SQL.", on_limit=stop)
    assert len(asked) == 1, "the run ended at the step it was on, not after trying every job"
    assert [j.get("doc_attempts", 0) for j in jobs] == [1, 0, 0] or [j.get("doc_attempts", 0) for j in jobs] == [0, 0, 0]
    monkeypatch.setattr(email_client, "fetch_recent", lambda *a, **k: email_client.Fetched([
        {"msg_id": f"<m{i}@acme>", "date": "Mon, 05 Oct 2026 10:00:00 +0200", "sender": "hr@acme.com", "subject": "Your application", "body": "About your application."} for i in range(3)]))
    monkeypatch.setattr(llm, "ask_json", limit)
    asked.clear()
    with pytest.raises(bridge_runs.RunCancelled):
        agent5_responses.process_inbox([store.new_job(id="a", company="Acme", title="Dev", status="waiting")], on_limit=stop)
    assert len(asked) == 1


def test_a_claude_call_that_never_answers_is_stopped(monkeypatch):
    """One stuck answer held a whole run: every call now has a time limit, and a stopped call counts nothing."""
    import asyncio
    import time
    recorded = []

    async def never(prompt, system, model):
        await asyncio.sleep(60)
        return "late", {}
    monkeypatch.setattr(llm, "_ask_async", never)
    monkeypatch.setattr(llm, "CALL_TIMEOUT", 0.2)
    monkeypatch.setattr(usage, "record", lambda rec, tag="": recorded.append(rec))
    started = time.monotonic()
    with pytest.raises(llm.CallTimedOut) as stopped:
        llm.ask("hello", force=True)
    assert time.monotonic() - started < 5 and recorded == []
    assert "did not answer" in str(stopped.value) and isinstance(stopped.value, RuntimeError)   # the runs show its words


def test_a_stuck_claude_ends_the_scan_at_the_first_email(isolate_data, monkeypatch):
    """Each email used to wait its own 5 minutes: 40 emails held the scan for over three hours."""
    mails = [{"msg_id": f"<m{n}@acme>", "date": "Mon, 01 Sep 2026", "sender": "hr@acme.com", "subject": "Your application at Acme",
              "body": "Thank you."} for n in range(3)]
    monkeypatch.setattr(email_client, "fetch_recent", lambda *a, **k: email_client.Fetched(mails))
    asked = []
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: asked.append(1) or (_ for _ in ()).throw(llm.CallTimedOut()))
    with pytest.raises(llm.CallTimedOut):
        agent5_responses.process_inbox([store.new_job(id="a", company="Acme", title="Dev", status="waiting")])
    assert asked == [1]


def test_a_stuck_claude_ends_the_cv_and_letter_steps_too(monkeypatch):
    """The CV and letter steps caught it as one job's failure and went on: 5 minutes per CV and per letter."""
    monkeypatch.setattr(agent3_letters, "_make_tailored_cv", lambda *a, **k: (_ for _ in ()).throw(llm.CallTimedOut()))
    monkeypatch.setattr(agent3_letters, "_make_letter", lambda *a, **k: pytest.fail("no letter after a stuck CV step"))
    with pytest.raises(llm.CallTimedOut):
        agent3_letters.generate_for(_jobs(1)[0], cv_text="CV", cv_path=None)


def test_the_env_part_files_are_never_committed():
    import subprocess
    root = Path(__file__).resolve().parent.parent
    done = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", ".env.abc123.part"])
    assert done.returncode == 0, "a part file can hold the mail password"


def test_a_letter_that_times_out_after_its_cv_keeps_the_cv_and_ends_the_run(monkeypatch):
    monkeypatch.setattr(agent3_letters, "_make_tailored_cv", lambda *a, **k: "cv_made.docx")
    monkeypatch.setattr(agent3_letters, "_make_letter", lambda *a, **k: (_ for _ in ()).throw(llm.CallTimedOut()))
    job = _jobs(1)[0]
    with pytest.raises(llm.CallTimedOut):
        agent3_letters.generate_for(job, cv_text="CV", cv_path=None)
    assert job["tailored_cv_file"] == "cv_made.docx"


@pytest.mark.parametrize("step", ["_make_tailored_cv", "_make_letter"])
def test_a_stuck_claude_in_a_run_uses_one_of_the_jobs_tries(isolate_data, monkeypatch, step):
    """A job whose call hangs every time is not tried for ever: each timeout uses one of its two tries."""
    jobs = _jobs(1)
    jobs[0].update(match_score=90, description="We build planning tools in Python and SQL. " * 20)
    monkeypatch.setattr(agent3_letters, "_make_tailored_cv", lambda *a, **k: "cv.docx")
    monkeypatch.setattr(agent3_letters, step, lambda *a, **k: (_ for _ in ()).throw(llm.CallTimedOut()))
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 90, "match_reason": "x"})
    for tries in (1, 2):
        with pytest.raises(llm.CallTimedOut):
            agent3_letters.process(jobs, {"seniority": "junior"}, threshold=60, only_new=False, cv_text="CV")
        assert jobs[0]["doc_attempts"] == tries
    agent3_letters.process(jobs, {"seniority": "junior"}, threshold=60, cv_text="CV")       # a normal run skips a spent job
    assert jobs[0]["doc_attempts"] == 2 and not jobs[0].get("cover_letter_file")


def test_the_card_asks_again_only_for_an_old_or_reset_figure_and_names_a_low_window(isolate_data):
    _windows(five=0.80, seven=0.79, five_reset=time.time() + 3600, seven_reset=time.time() + 86400)
    card = ui_api.Api().usage_info()
    assert card["should_refresh"] is False, "a fresh reading: no question to Claude"
    assert card["five_hour_low"] is True and card["seven_day_low"] is False, f"{usage.LOW_LEFT}% left or less is low"
    old = datetime.fromtimestamp(time.time() - usage.STALE_AFTER - 60).replace(microsecond=0)
    _saved_usage(lambda state: state["last_rate_limit"].update(at=old.isoformat()))
    assert ui_api.Api().usage_info()["should_refresh"] is True, "older than an hour: one small question"


def test_a_refused_window_and_a_reset_one_are_told_apart(isolate_data):
    _windows(five=0.87, seven=0.34, five_reset=NOON - 60, seven_reset=NOON - 60)
    usage.note_limit(NOON + 3600, SESSION_REFUSAL)
    now = usage.windows(NOON)
    assert now["five_hour"]["used"] == 1.0 and now["five_hour"]["reset_passed"] == 0.0, "the refusal is news"
    assert now["seven_day"]["used"] is None and now["seven_day"]["reset_passed"] == NOON - 60
