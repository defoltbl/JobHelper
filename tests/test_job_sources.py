"""Where postings come from: JobSource and its kinds (jobhelper/job_sources.py)."""
import pytest

from jobhelper import config, job_sources, scrapers_ats


def test_each_setting_asks_its_own_sources_in_order(monkeypatch):
    monkeypatch.setattr(scrapers_ats, "load_companies", lambda: [{"name": "Acme", "ats": "greenhouse", "token": "acme"}])
    monkeypatch.setattr(config, "has_jooble", lambda: False)
    monkeypatch.setattr(config, "adzuna_available", lambda: False)
    names = lambda setting: [s.name for s in job_sources.sources_for(setting)]       # noqa: E731
    assert names("czech") == ["jobs.cz", "prace.cz", "linkedin", "careers"]
    assert names("remote") == ["remoteok", "weworkremotely"] and names("careers") == ["careers"] and names("jooble") == []
    assert names("all") == ["jobs.cz", "prace.cz", "linkedin", "remoteok", "weworkremotely", "careers"]
    monkeypatch.setattr(scrapers_ats, "load_companies", lambda: [])
    assert "careers" not in names("czech")                                            # no company list: not asked
    monkeypatch.setattr(config, "has_jooble", lambda: True)
    assert names("jooble") == ["jooble"]


def test_every_source_has_the_same_interface():
    for source in job_sources.all_sources(max_age_days=7):
        assert isinstance(source, job_sources.JobSource) and source.name and source.groups
        assert callable(source.find) and callable(source.reset) and isinstance(source.available(), bool)
    with pytest.raises(TypeError):
        job_sources.JobSource("abstract", ("all",))                                   # the interface itself finds nothing


def test_a_board_hands_the_search_to_its_function_and_linkedin_keeps_its_age_limit(monkeypatch):
    asked = []
    board = job_sources.Board("x", lambda q, where, n: asked.append((q, where, n)) or [{"id": "1"}])
    assert board.find("dev", "Prague", 5) == [{"id": "1"}] and asked == [("dev", "Prague", 5)]
    assert board.available() and job_sources.Board("y", lambda q, w, n: [], needs=lambda: []).available() is False
    seen = {}
    monkeypatch.setattr(job_sources.scrapers_intl, "linkedin", lambda q, w, n, max_age_days=0: seen.update(age=max_age_days) or [])
    job_sources.LinkedInSource(max_age_days=7).find("dev", "Prague", 5)
    assert seen == {"age": 7}


class _Reply:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_the_api_sources_turn_their_answers_into_job_records(monkeypatch):
    monkeypatch.setattr(job_sources.requests, "get", lambda url, params, timeout: _Reply({"results": [
        {"id": 7, "title": "<b>Dev</b>", "company": {"display_name": "Acme"}, "location": {"display_name": "Berlin"},
         "salary_min": 50000, "salary_max": 60000, "redirect_url": "https://example.com/7", "created": "2026-10-01T10:00:00Z"}]}))
    job = job_sources.AdzunaSource().find("dev", "Berlin", 5)[0]
    assert (job["id"], job["title"], job["company"], job["salary"], job["date_posted"]) == ("adzuna-7", "Dev", "Acme", "50 000 - 60 000", "2026-10-01")
    monkeypatch.setattr(job_sources.requests, "post", lambda url, json, timeout: _Reply({"jobs": [
        {"id": 1, "title": "QA", "company": "Beta", "location": "Prague", "source": "jobs.cz", "link": "https://example.com/1", "snippet": "Test."},
        {"id": 2, "title": "QA 2"}]}))
    found = job_sources.JoobleSource().find("qa", "Prague", 1)
    assert [j["id"] for j in found] == ["jooble-1"] and found[0]["source"] == "jooble/jobs.cz"


# ── remote boards on top of the chosen source ───────────────────────────────
@pytest.mark.parametrize("source, on, added", [
    ("czech", True, True), ("czech", False, False), ("", True, True),
    ("linkedin", True, False), ("careers", True, False),          # "… only" stays only that
    ("all", True, False), ("remote", True, False),                # they hold the remote boards already
    ("czech", "yes", False)])
def test_remote_boards_are_added_only_where_they_add_something(source, on, added):
    """"+ Remote" stayed on the main screen, and the boards were searched, with "LinkedIn only" or "career sites only"."""
    from jobhelper import agent2_search
    assert agent2_search.remote_added(source, on) is added


def test_the_search_the_options_and_the_window_use_one_rule(isolate_data):
    import json
    from pathlib import Path
    from jobhelper import config, ui_api, vault
    root = Path(__file__).resolve().parent.parent
    assert 'agent2_search.remote_added(o["source"], o.get("include_remote"))' in (root / "jobhelper" / "bridge_runs.py").read_text(encoding="utf-8")
    assert "optsData.remote_added === true" in (root / "ui_qt" / "NavPanel.qml").read_text(encoding="utf-8")
    assert "bridge.remoteCanBeAdded(srcCombo.currentValue)" in (root / "ui_qt" / "OptionsDialog.qml").read_text(encoding="utf-8")
    config.ensure_dirs()
    for source, added in (("czech", True), ("linkedin", False), ("careers", False)):
        vault.write_text(config.DATA_DIR / "ui_settings.json", json.dumps({"source": source, "include_remote": True}))
        assert ui_api.Api().options()["remote_added"] is added, source
    clean, problem = ui_api.Api().check_options({"source": "czech", "remote_added": True})
    assert problem == "" and "remote_added" not in clean                  # worked out when read, never saved

