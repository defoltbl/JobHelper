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
        assert isinstance(source, job_sources.JobSource) and source.name and job_sources.SourceChoice.known(source.kind)
        assert callable(source.find) and callable(source.reset) and isinstance(source.available(), bool)
    with pytest.raises(TypeError):
        job_sources.JobSource("abstract", "boards")                                   # the interface itself finds nothing


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


# ── which kinds of job source a search reads ────────────────────────────────
@pytest.mark.parametrize("opts, kinds", [
    ({"source": "czech"}, ("boards", "linkedin", "careers")),
    ({"source": "czech", "include_remote": True}, ("boards", "linkedin", "careers", "remote")),
    ({"source": "linkedin", "include_remote": True}, ("linkedin",)),          # "LinkedIn only" stays only that
    ({"source": "careers", "include_remote": True}, ("careers",)),
    ({"source": "all"}, ("boards", "linkedin", "careers", "remote", "adzuna", "jooble")),
    ({"sources": ["linkedin", "boards"]}, ("boards", "linkedin")),             # any combination, always in one order
    ({"sources": ["remote"], "source": "czech", "include_remote": False}, ("remote",)),   # the newer setting wins
    ({"sources": ["nonsense"]}, ("boards", "linkedin", "careers")),            # nothing known: the default
    ({}, ("boards", "linkedin", "careers"))])
def test_the_choice_reads_the_new_and_the_older_settings(opts, kinds):
    assert job_sources.SourceChoice.from_options(opts).kinds == kinds


def test_a_search_asks_every_source_of_the_kinds_picked(monkeypatch):
    monkeypatch.setattr(scrapers_ats, "load_companies", lambda: [{"name": "Acme"}])
    def names(choice, country="czechia"):
        return [s.name for s in job_sources.sources_for(choice, country=country)]
    choice = job_sources.SourceChoice
    assert names(choice(["linkedin", "boards"])) == ["jobs.cz", "prace.cz", "linkedin"]
    assert names(choice(["linkedin"])) == ["linkedin"] and names(choice(["careers"])) == ["careers"]
    assert names(choice(["remote"])) == ["remoteok", "weworkremotely"]
    assert names("czech") == ["jobs.cz", "prace.cz", "linkedin", "careers"] and names("linkedin") == ["linkedin"]   # the older values still work
    assert names(choice(["boards"]), "germany") == []                           # Czech boards are for Czechia only, and that is said
    assert job_sources.left_out(choice(["boards", "linkedin"]), "germany") == [(["jobs.cz", "prace.cz"], ("czechia",))]


def test_the_names_shown_and_offered():
    choice = job_sources.SourceChoice
    assert choice(["remote", "linkedin"]).names() == ["LinkedIn", "Remote boards"]
    assert [k["name"] for k in choice.offered()] == ["Czech boards", "LinkedIn", "Career sites", "Remote boards"]
    assert choice.known("boards") and choice.known("adzuna") and not choice.known("czech")


def test_the_search_the_weekly_run_the_options_and_the_window_use_one_choice(isolate_data):
    import json
    from pathlib import Path
    from jobhelper import ui_api, vault
    root = Path(__file__).resolve().parent.parent
    assert "source=job_sources.SourceChoice.from_options(o)" in (root / "jobhelper" / "bridge_runs.py").read_text(encoding="utf-8")
    assert "job_sources.SourceChoice.from_options(" in (root / "run.py").read_text(encoding="utf-8")
    assert "optsData.source_names" in (root / "ui_qt" / "NavPanel.qml").read_text(encoding="utf-8")
    assert "bridge.sourceKinds()" in (root / "ui_qt" / "OptionsDialog.qml").read_text(encoding="utf-8")
    config.ensure_dirs()
    vault.write_text(config.DATA_DIR / "ui_settings.json", json.dumps({"source": "czech", "include_remote": True}))
    o = ui_api.Api().options()
    assert o["sources"] == ["boards", "linkedin", "careers", "remote"] and o["source_names"] == ["Czech boards", "LinkedIn", "Career sites", "Remote boards"]
    vault.write_text(config.DATA_DIR / "ui_settings.json", json.dumps({"sources": ["linkedin", "boards"]}))
    assert ui_api.Api().options()["source_names"] == ["Czech boards", "LinkedIn"]
    check = ui_api.Api().check_options
    assert check({"sources": []})[1] == "Choose at least one job source."
    assert "not a job source" in check({"sources": ["somewhere"]})[1]
    clean, problem = check({"sources": ["remote", "boards"], "source_names": ["x"]})
    assert problem == "" and clean["sources"] == ["boards", "remote"] and "source_names" not in clean     # worked out when read, never saved


# ── pinned before the OOP rewrite (18 October 2026): every setting finds exactly the same sources ──
_CZ = ["jobs.cz", "prace.cz"]
_PINNED = [
    ("czech", "czechia", _CZ + ["linkedin", "careers"], []), ("czech", "germany", ["linkedin", "careers"], [(_CZ, ("czechia",))]),
    ("czech", "", _CZ + ["linkedin", "careers"], []), ("linkedin", "germany", ["linkedin"], []),
    ("remote", "czechia", ["remoteok", "weworkremotely"], []), ("careers", "", ["careers"], []),
    ("adzuna", "czechia", ["adzuna"], []), ("jooble", "germany", ["jooble"], []),
    ("all", "czechia", _CZ + ["linkedin", "remoteok", "weworkremotely", "careers", "jooble", "adzuna"], []),
    ("all", "germany", ["linkedin", "remoteok", "weworkremotely", "careers", "jooble", "adzuna"], [(_CZ, ("czechia",))]),
    (["boards"], "czechia", _CZ, []), (["boards"], "germany", [], [(_CZ, ("czechia",))]),
    (["boards", "remote"], "", _CZ + ["remoteok", "weworkremotely"], []),
    (["linkedin", "careers"], "czechia", ["linkedin", "careers"], []),
    (("choice", ["remote", "linkedin"]), "germany", ["linkedin", "remoteok", "weworkremotely"], []),
    (("options", {"source": "czech", "include_remote": True}), "germany",
     ["linkedin", "remoteok", "weworkremotely", "careers"], [(_CZ, ("czechia",))]),
]


@pytest.mark.parametrize("setting, country, names, left", _PINNED)
def test_every_setting_finds_the_same_sources_as_before(setting, country, names, left, monkeypatch):
    for cls in (job_sources.JobSource, job_sources.Board, job_sources.AdzunaSource, job_sources.JoobleSource):
        monkeypatch.setattr(cls, "available", lambda self: True)                     # every source set up
    if isinstance(setting, tuple):
        kind, value = setting
        setting = job_sources.SourceChoice(value) if kind == "choice" else job_sources.SourceChoice.from_options(value)
    assert [s.name for s in job_sources.sources_for(setting, country=country)] == names
    assert job_sources.left_out(setting, country) == left


def test_one_owner_decides_which_sources_a_setting_includes():
    """SourceChoice is the only place that knows the older words; a source knows just its own kind."""
    assert job_sources.SourceChoice.of("czech").kinds == ("boards", "linkedin", "careers")
    assert job_sources.SourceChoice.of(["remote", "boards"]).kinds == ("boards", "remote")
    assert job_sources.SourceChoice.of("no such word").kinds == ()
    choice = job_sources.SourceChoice(["linkedin"])
    assert job_sources.SourceChoice.of(choice) is choice
    assert job_sources.SourceChoice.from_command_line("linkedin", True).kinds == ("linkedin", "remote")
    assert not hasattr(job_sources, "_tags")
    assert {s.kind for s in job_sources.all_sources()} <= {k for k, _n in job_sources.SourceChoice.KINDS + job_sources.SourceChoice.EXTRA}
