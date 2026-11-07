"""How the suite itself runs: on every core, with the window tests kept together in their order."""
import re

import pytest

from tests.conftest import ROOT


def test_the_tests_run_on_every_core_and_the_window_tests_stay_together():
    ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert re.search(r"^addopts = .*-n auto --dist loadgroup", ini, re.MULTILINE), "every core, groups kept on one worker"
    windows = [f for f in sorted((ROOT / "tests").glob("test_*.py")) if re.search(r"^def test_\w+\([^)]*\bui\b", f.read_text(encoding="utf-8"), re.M)]
    assert len(windows) >= 4, "the window tests are split into parts that run side by side"
    for f in windows:
        assert f'pytestmark = pytest.mark.xdist_group("{f.stem}")' in f.read_text(encoding="utf-8"), \
            f"{f.name}: its tests share one window and follow on from each other, so they need a worker group of their own"
    groups = [re.search(r'xdist_group\("([^"]+)"\)', f.read_text(encoding="utf-8")).group(1) for f in windows]
    assert len(set(groups)) == len(groups), "each window file has a group of its own"
    assert not (ROOT / "tests" / "test_ui_qml.py").exists()


def test_the_package_that_runs_them_is_locked_with_its_hash():
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    for name in ("pytest-xdist", "execnet"):
        assert re.search(rf"^{name}==[\d.]+ \\\n    --hash=sha256:[0-9a-f]{{64}}$", lock, re.MULTILINE), name
    assert "pytest-xdist" in (ROOT / "requirements.txt").read_text(encoding="utf-8")


def test_no_test_can_open_a_real_web_browser():
    """#79: webbrowser was not patched, so a library could open a real browser from a test."""
    import webbrowser
    with pytest.raises(AssertionError, match="real web browser"):
        webbrowser.open("https://example.com")


def test_the_run_does_not_start_on_your_own_data_folder(monkeypatch, tmp_path):
    """#79: nothing checked at the start that the data folder is not the real one."""
    from jobhelper import config
    from tests import conftest
    exits = []
    monkeypatch.setattr(conftest.pytest, "exit", lambda msg, code=None: exits.append(msg))
    monkeypatch.setattr(conftest, "_real_data_folders", lambda: [tmp_path / "real"])
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "real" / "data")

    class Session:
        config = type("Config", (), {})()
    monkeypatch.setattr(conftest, "_data_snapshot", lambda: {})
    conftest.pytest_sessionstart(Session)
    assert exits and "your own data folder" in exits[0]
    exits.clear()
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "test-home" / "data")
    conftest.pytest_sessionstart(Session)
    assert exits == []
