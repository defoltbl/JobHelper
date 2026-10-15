"""Where the data lives: the Library folder, and the one-time move of an old folder from the project."""
import os
import shutil
from pathlib import Path

import pytest

from jobhelper import config, health, home


@pytest.fixture
def places(tmp_path):
    """An old project folder with data and .env, and an empty Library: never the real ones."""
    project, library = tmp_path / "project", tmp_path / "Library" / "JobHelper"
    old = project / "data"
    (old / "cv").mkdir(parents=True)
    (old / "jobs.json").write_bytes(b"JHENC1\nencrypted jobs")
    (old / "cv" / "master.docx").write_bytes(b"cv bytes")
    (old / "backups" / "before_x_20261001_100000").mkdir(parents=True)
    (old / "backups" / "before_x_20261001_100000" / "jobs.json.enc").write_bytes(b"old copy")
    (project / ".env").write_text("IMAP_USER=someone@example.com\n", encoding="utf-8")
    return home.DataHome(library, old, project / ".env"), old, library, project


def _files(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_an_old_folder_with_data_stays_in_use_until_it_moves(places):
    where, old, library, project = places
    assert where.moved is False and where.data_dir() == old and where.env_path() == project / ".env"


def test_the_move_copies_everything_checks_it_and_keeps_the_old_folder(places):
    where, old, library, project = places
    before = _files(old)
    done = where.settle()
    assert done.moved is True and done.files == 3 and done.source == old
    assert _files(library / "data") == before                                     # byte for byte, backups too
    assert (library / ".env").read_text(encoding="utf-8") == "IMAP_USER=someone@example.com\n"
    assert not old.exists() and _files(project / "data_moved_to_Library") == before   # moved aside, never deleted
    assert (project / ".env_moved_to_Library").is_file() and not (project / ".env").exists()
    assert where.moved and where.data_dir() == library / "data" and where.env_path() == library / ".env"
    assert not (library / "data.incoming").exists()
    assert where.settle().moved is False                                          # once only


def test_a_new_mac_starts_in_the_library(tmp_path):
    where = home.DataHome(tmp_path / "Library", tmp_path / "project" / "data", tmp_path / "project" / ".env")
    assert where.data_dir() == tmp_path / "Library" / "data"
    assert where.settle().moved is False and where.moved and (tmp_path / "Library" / "data").is_dir()


def test_an_old_folder_with_only_a_log_is_not_data(tmp_path):
    old = tmp_path / "project" / "data"
    old.mkdir(parents=True)
    (old / "weekly_jobhelper.log").write_text("a line", encoding="utf-8")
    where = home.DataHome(tmp_path / "Library", old)
    assert where.data_dir() == tmp_path / "Library" / "data"
    where.settle()
    assert (old / "weekly_jobhelper.log").is_file()                                # not moved, not touched


def test_a_library_folder_that_already_holds_files_is_never_mixed(places):
    where, old, library, _ = places
    (library / "data").mkdir(parents=True)
    (library / "data" / "jobs.json").write_bytes(b"someone else's")
    before = _files(old)
    with pytest.raises(home.HomeError, match="already holds files"):
        where.settle()
    assert _files(old) == before and where.data_dir() == old and not where.moved


def test_a_copy_that_differs_is_thrown_away_and_the_old_folder_stays(places, monkeypatch):
    where, old, library, _ = places
    monkeypatch.setattr(home, "_differences", lambda source, copy: ["jobs.json"])
    with pytest.raises(home.HomeError, match="not copied correctly"):
        where.settle()
    assert old.is_dir() and not (library / "data.incoming").exists() and not (library / "data").exists()
    assert where.data_dir() == old


def test_a_disk_error_is_a_clear_message(places, monkeypatch):
    where, old, library, _ = places

    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(shutil, "copytree", full)
    with pytest.raises(home.HomeError, match="No space left on device"):
        where.settle()
    assert old.is_dir() and where.data_dir() == old


def test_a_copy_that_stopped_halfway_is_replaced(places):
    where, old, library, _ = places
    (library / "data.incoming").mkdir(parents=True)
    (library / "data.incoming" / "half.bin").write_bytes(b"x")
    where.settle()
    assert not (library / "data" / "half.bin").exists() and where.moved


def test_the_kept_name_never_replaces_an_earlier_one(places):
    where, old, library, project = places
    (project / "data_moved_to_Library").mkdir()
    assert where.settle().kept == project / "data_moved_to_Library_2"


def test_an_override_uses_only_that_folder(tmp_path):
    where = home.DataHome.for_this_mac({"JOBHELPER_HOME": str(tmp_path / "other")})
    assert where.data_dir() == tmp_path / "other" / "data" and where.env_path() == tmp_path / "other" / ".env"
    real = home.DataHome.for_this_mac({})
    assert real.library == home.LIBRARY


def test_tests_never_use_your_own_data_folder():
    assert config.DATA_DIR != home.ROOT / "data" and home.LIBRARY not in config.DATA_DIR.parents
    assert Path(os.environ["JOBHELPER_HOME"]) in config.DATA_DIR.parents


def test_start_remembers_why_a_move_failed_and_the_check_shows_it(monkeypatch):
    def refuse(self):
        raise home.HomeError("The folder X already holds files.")
    monkeypatch.setattr(home.DataHome, "settle", refuse)
    assert home.start().moved is False and home.problem() == "The folder X already holds files."
    check = next(c for c in health.run()["checks"] if c["name"] == "Data folder")
    assert check["ok"] is False and "could not be moved into the Library" in check["problem"] and "already holds files" in check["problem"]
    monkeypatch.setattr(home.DataHome, "settle", lambda self: home.Move(False))
    home.start()
    assert home.problem() == ""


@pytest.mark.parametrize("frozen, argv, expected", [
    (False, ["app_qt.py"], ["/py", "app_qt.py"]),
    (True, ["/Applications/JobHelper.app/Contents/MacOS/JobHelper", "-psn"], ["/bin/JobHelper", "-psn"]),
])
def test_the_app_starts_again_with_the_same_arguments(frozen, argv, expected):
    executable = "/bin/JobHelper" if frozen else "/py"
    assert home.restart_command(argv, executable, frozen) == expected
