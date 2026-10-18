"""How the suite itself runs: on every core, with the window tests kept together in their order."""
import re

from tests.conftest import ROOT


def test_the_tests_run_on_every_core_and_the_window_tests_stay_together():
    ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert re.search(r"^addopts = .*-n auto --dist loadgroup", ini, re.MULTILINE), "every core, groups kept on one worker"
    window = (ROOT / "tests" / "test_ui_qml.py").read_text(encoding="utf-8")
    assert 'pytestmark = pytest.mark.xdist_group("window")' in window, \
        "the window tests share one window and follow on from each other: spread over workers, three of them failed"


def test_the_package_that_runs_them_is_locked_with_its_hash():
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    for name in ("pytest-xdist", "execnet"):
        assert re.search(rf"^{name}==[\d.]+ \\\n    --hash=sha256:[0-9a-f]{{64}}$", lock, re.MULTILINE), name
    assert "pytest-xdist" in (ROOT / "requirements.txt").read_text(encoding="utf-8")
