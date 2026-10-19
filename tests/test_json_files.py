"""Every small encrypted JSON file is read and written through vault.JsonFile, and each keeps its own answer to a damaged
file and to a file the data key cannot open."""
import pytest

from jobhelper import agent1_cv, agent2_search, config, details, ui_api, vault


def _damage(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken")


def _key_cannot_open(monkeypatch):
    def refused(blob):
        raise vault.VaultError("An encrypted file is damaged or was written with a different key.")
    monkeypatch.setattr(vault, "decrypt", refused)


def test_load_is_strict_and_read_is_lenient(isolate_data):
    kept = vault.JsonFile("kept.json")
    assert kept.load() is None and kept.read() is None                  # no file
    kept.write({"a": 1}, indent=1)
    assert kept.load() == {"a": 1} and vault.is_encrypted(kept.path.read_bytes())
    _damage(kept.path)
    assert kept.read() is None
    with pytest.raises(ValueError):
        kept.load()
    moved = vault.JsonFile("ignored.json", where=lambda: isolate_data / "elsewhere" / "x.json")
    moved.write([1])
    assert moved.path == isolate_data / "elsewhere" / "x.json" and moved.read() == [1]


def test_the_last_run_card_is_empty_when_its_file_cannot_be_read(isolate_data, monkeypatch):
    api = ui_api.Api()
    assert api.last_run() == {}
    api.note_run(found="+3 new")
    assert api.last_run()["found"] == "+3 new"
    _key_cannot_open(monkeypatch)
    assert api.last_run() == {}
    monkeypatch.undo()
    _damage(config.DATA_DIR / "last_run.json")
    assert api.last_run() == {}


def test_options_fall_back_to_the_defaults_and_say_why(isolate_data, monkeypatch):
    noted = []
    from jobhelper import api_options
    monkeypatch.setattr(api_options.trouble, "note", lambda where, error: noted.append(where))
    config.save_ui_settings({"where": "Brno"})
    assert config.ui_settings() == {"where": "Brno"} and ui_api.Api().options()["where"] == "Brno"
    _damage(config.ui_settings_file())
    assert config.ui_settings() == {}
    assert ui_api.Api().options()["where"] == "" and noted == ["reading the saved Options"]
    config.save_ui_settings({"where": "Brno"})
    _key_cannot_open(monkeypatch)
    assert config.ui_settings() == {}, "the key cannot open them: the defaults, and the start-up check says why"


def test_what_a_search_filtered_out_is_only_shown(isolate_data, monkeypatch):
    agent2_search.save_dropped([{"title": "Senior Dev", "why": "level"}], when="19 Oct 08:00")
    assert agent2_search.load_dropped()["rows"] == [{"title": "Senior Dev", "why": "level"}]
    assert b"\n " in vault.decrypt((config.DATA_DIR / "filtered_out.json").read_bytes()), "written as before (indent 1)"
    _key_cannot_open(monkeypatch)
    assert agent2_search.load_dropped() == {"when": "", "total": 0, "rows": []}


def test_a_damaged_cv_analysis_is_made_again_but_a_locked_one_is_not_thrown_away(isolate_data, monkeypatch):
    assert agent1_cv.load_profile() is None
    config.PROFILE.write({"seniority": "junior"})
    assert agent1_cv.load_profile() == {"seniority": "junior"} and config.PROFILE.path == config.PROFILE_JSON
    _key_cannot_open(monkeypatch)
    with pytest.raises(vault.VaultError):
        agent1_cv.load_profile()
    monkeypatch.undo()
    _damage(config.PROFILE_JSON)
    assert agent1_cv.load_profile() is None


def test_my_details_read_empty_when_damaged_and_refuse_when_locked(isolate_data, monkeypatch):
    assert details.save({**details.empty(), "first_name": "Jordan", "last_name": "Weber"})["ok"]
    assert details.load()["first_name"] == "Jordan" and details.path() == config.MY_DETAILS.path
    _key_cannot_open(monkeypatch)
    with pytest.raises(vault.VaultError):
        details.load()
    monkeypatch.undo()
    _damage(details.path())
    assert details.load() == details.empty()


def test_each_file_is_named_once_and_follows_a_moved_path(isolate_data, monkeypatch):
    moved = isolate_data / "moved" / "profile.json"
    monkeypatch.setattr(config, "PROFILE_JSON", moved)
    agent1_cv_profile = {"seniority": "senior"}
    config.PROFILE.write(agent1_cv_profile)
    assert moved.is_file() and agent1_cv.load_profile() == agent1_cv_profile, "a setting that moves the file is followed"
    stores = [config.UI_SETTINGS, config.LAST_RUN, config.FILTERED_OUT, config.PROFILE, config.MY_DETAILS]
    assert {s.path for s in stores} <= set(vault.data_files()), "every one of them is kept encrypted and backed up"


def test_a_missing_file_is_simply_nothing_yet(isolate_data):
    assert agent1_cv.load_profile() is None and agent2_search.load_dropped() == {"when": "", "total": 0, "rows": []}
    assert config.ui_settings() == {} and ui_api.Api().last_run() == {} and details.load() == details.empty()


def test_an_options_file_that_holds_no_settings_is_noted(isolate_data, monkeypatch):
    noted = []
    from jobhelper import api_options
    monkeypatch.setattr(api_options.trouble, "note", lambda where, error: noted.append(where))
    for empty in (None, [1, 2]):
        config.UI_SETTINGS.write(empty)
        assert ui_api.Api().options()["where"] == ""
    assert noted == ["reading the saved Options"] * 2, "null and a list are noted like a damaged file, as before"
