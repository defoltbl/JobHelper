"""run.py (also the weekly scheduled run) must search the way the app's Options say."""
import json

import pytest

import run
from jobhelper import agent1_cv, agent2_search, agent3_letters, agent4_tracker, config, letters, store, usage


@pytest.fixture
def cli(isolate_data, monkeypatch):
    seen = {}

    def search(queries, **kw):
        seen.setdefault("searches", []).append({"queries": list(queries), **kw})
        return []

    def process(jobs, profile, **kw):
        seen["threshold"] = kw["threshold"]
        return {"scored": 0, "letters": 0, "tailored_cvs": 0, "skipped": 0}

    monkeypatch.setattr(config, "MODEL", config.MODEL)
    monkeypatch.setattr(config, "MIN_LEAD_SCORE", config.MIN_LEAD_SCORE)
    monkeypatch.setattr(agent1_cv, "load_profile", lambda current_only=False: {"_cv_file": "cv.docx", "seniority": "junior",
                                                           "search_queries": ["from the cv"]})
    monkeypatch.setattr(agent1_cv, "find_cv", lambda: None)
    monkeypatch.setattr(agent2_search, "search", search)
    monkeypatch.setattr(letters, "import_letters", lambda jobs: {"scanned": 0, "linked": 0, "seeded": 0})
    monkeypatch.setattr(agent3_letters, "process", process)
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)
    monkeypatch.setattr(usage, "format_report", lambda: "")

    def go(*args, settings=None):
        config.ensure_dirs()
        if settings is not None:
            (config.DATA_DIR / "ui_settings.json").write_text(json.dumps(settings), encoding="utf-8")
        monkeypatch.setattr("sys.argv", ["run.py", "--reuse-profile", *args])
        assert run.main() == 0
        return seen

    return go


def test_defaults_without_saved_options(cli):
    seen = cli("--where", "Brno")
    first = seen["searches"][0]
    assert (first["where"], first["source"].kinds, first["queries"]) == ("Brno", ("boards", "linkedin", "careers"), ["from the cv"])
    assert seen["threshold"] == config.DEFAULT_THRESHOLD
    assert len(seen["searches"]) == 1


def test_saved_options_drive_the_run(cli):
    seen = cli(settings={"where": "Brno", "source": "linkedin", "threshold": 77, "per_query": 5,
                         "max_age_days": 3, "all_languages": True, "include_remote": True,
                         "queries": ["qa engineer"], "model": "opus", "min_lead_score": 45})
    [first] = seen["searches"]                       # "LinkedIn only" stays only that: no second, remote search
    assert (first["where"], first["source"].kinds, first["per_query"], first["max_age_days"]) == ("Brno", ("linkedin",), 5, 3)
    assert first["queries"] == ["qa engineer"] and first["english_only"] is False
    assert seen["threshold"] == 77
    assert (config.MODEL, config.MIN_LEAD_SCORE) == ("opus", 45)


def test_the_weekly_run_reads_the_sources_ticked_in_options(cli):
    seen = cli(settings={"where": "Brno", "sources": ["linkedin", "remote"], "source": "czech"})
    assert [s["source"].kinds for s in seen["searches"]] == [("linkedin", "remote")]


def test_sources_typed_on_the_command_line_beat_options(cli):
    seen = cli("--source", "linkedin", "--include-remote", settings={"where": "Brno", "sources": ["boards"]})
    assert [s["source"].kinds for s in seen["searches"]] == [("linkedin", "remote")]      # typed by hand: both, as asked


def test_command_line_flags_beat_saved_options(cli):
    seen = cli("--where", "Ostrava", "--threshold", "65", settings={"where": "Brno", "threshold": 77})
    assert seen["searches"][0]["where"] == "Ostrava" and seen["threshold"] == 65


def test_skip_search_does_not_search(cli):
    seen = cli("--skip-search")
    assert "searches" not in seen
    assert store.load_jobs() == []


def test_no_city_anywhere_stops_with_a_clear_message(cli, monkeypatch, capsys):
    config.ensure_dirs()
    monkeypatch.setattr("sys.argv", ["run.py", "--reuse-profile"])
    assert run.main() == 1
    assert "No city to search in" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["run.py", "--reuse-profile", "--skip-search"])     # nothing to search: no city needed
    assert run.main() == 0


def test_the_city_saved_in_options_is_used_and_none_is_built_in(cli):
    from pathlib import Path
    seen = cli(settings={"where": "Vienna"})
    assert seen["searches"][0]["where"] == "Vienna"
    assert "Praha" not in Path(run.__file__).read_text(encoding="utf-8")


def test_a_command_line_run_updates_the_last_run_card(cli):
    from jobhelper import ui_api
    cli(settings={"where": "Brno"})
    saved = ui_api.Api().last_run()
    assert saved["found"] == "+0 new" and saved["filtered"] == 0 and saved["letters"] == 0 and saved["when"]


@pytest.mark.parametrize("typed, kinds", [
    (("--source", "czech", "--include-remote"), ("boards", "linkedin", "careers", "remote")),
    (("--source", "all"), ("boards", "linkedin", "careers", "remote", "adzuna", "jooble")),
    (("--source", "remote", "--include-remote"), ("remote",)),
    (("--include-remote",), ("boards", "linkedin", "careers", "remote")),
])
def test_typed_sources_are_read_as_before(cli, typed, kinds):
    seen = cli(*typed, settings={"where": "Brno", "sources": ["linkedin"]})
    assert [s["source"].kinds for s in seen["searches"]] == [kinds]
