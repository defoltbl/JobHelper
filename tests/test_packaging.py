"""The packaged app: its recipe, its window check, and the quiet bridge that check uses."""
import ast
import re
import sys
from pathlib import Path

import pytest

import app_qt
from jobhelper import app_info, llm, qt_bridge

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "JobHelper.spec"


def _unused_qt() -> tuple[str, ...]:
    text = SPEC.read_text(encoding="utf-8")
    found = re.search(r"UNUSED_QT = (\(.*?\))\n", text, re.S)
    return ast.literal_eval(found.group(1))


def test_the_recipe_never_drops_a_qt_part_the_window_imports():
    used = set()
    for qml in (ROOT / "ui_qt").glob("*.qml"):
        used |= set(re.findall(r"^import (Qt\w*(?:\.\w+)*)", qml.read_text(encoding="utf-8"), re.M))
    assert {"QtQuick", "QtQuick.Layouts", "QtQuick.Dialogs"} <= used
    for name in used:
        top = name.split(".")[0]
        assert not top.startswith(_unused_qt()) or top == "QtQuick", name
        assert not name.replace(".", "").startswith(_unused_qt()), name
    assert "QtWebEngine" in _unused_qt()                                          # the biggest part the app never uses


def test_the_recipe_carries_what_is_loaded_by_name():
    text = SPEC.read_text(encoding="utf-8")
    for needed in ('"run"', '"status"', '"PySide6.QtQuick"', 'collect_submodules("jobhelper")', '"_bundled" / "claude"',
                   '"ui_qt"', '"CHANGELOG.md"', "NSAppleEventsUsageDescription", "app_info.BUNDLE_ID"):
        assert needed in text, needed


def test_the_app_identity_is_in_one_place():
    assert app_info.NAME == "JobHelper" and re.fullmatch(r"\d+\.\d+\.\d+", app_info.VERSION)
    assert app_info.BUNDLE_ID.count(".") >= 2 and "Chrome" in app_info.APPLE_EVENTS_REASON


@pytest.mark.parametrize("environ, refused", [
    ({}, "JOBHELPER_HOME"),
    ({"JOBHELPER_HOME": "/tmp/x"}, "JOBHELPER_VAULT_BACKEND=memory"),
    ({"JOBHELPER_HOME": "  ", "JOBHELPER_VAULT_BACKEND": "memory"}, "JOBHELPER_HOME"),
    ({"JOBHELPER_HOME": "/tmp/x", "JOBHELPER_VAULT_BACKEND": "keychain"}, "JOBHELPER_VAULT_BACKEND=memory"),
    ({"JOBHELPER_HOME": "/tmp/x", "JOBHELPER_VAULT_BACKEND": "MEMORY"}, ""),
])
def test_the_window_check_runs_only_on_throwaway_data(environ, refused):
    said = app_qt.check_refusal(environ)
    assert (refused in said) if refused else said == ""


def test_the_window_check_is_refused_by_the_app_on_real_data(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["JobHelper", "--check-window"])
    monkeypatch.delenv("JOBHELPER_HOME")
    monkeypatch.setattr(app_qt, "check_window", lambda: pytest.fail("the window check must not run"))
    assert app_qt.main() == 2 and "throwaway data folder" in capsys.readouterr().out


def test_the_window_check_is_started_with_its_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["JobHelper", "--check-window"])
    monkeypatch.setattr(app_qt, "check_window", lambda: 0)
    from jobhelper import home
    monkeypatch.setattr(home, "start", lambda: pytest.fail("the check never moves data"))
    assert app_qt.main() == 0


@pytest.fixture
def quiet(qapp, isolate_data):
    return qt_bridge.Bridge(quiet=True)


def test_a_quiet_bridge_asks_claude_nothing_and_gives_no_reminder(quiet, monkeypatch):
    monkeypatch.setattr(llm, "ask", lambda *a, **k: pytest.fail("the window check asked Claude"))
    monkeypatch.setattr(qt_bridge.Api, "due_reminders", lambda self: pytest.fail("the window check used up a reminder"))
    ready = []
    quiet.usageReady.connect(lambda: ready.append(True))
    quiet._ping_usage()
    assert ready == [True]                                                        # the usage card still gets its answer
    assert quiet.remind() == 0


def test_a_normal_bridge_still_reminds(qapp, isolate_data, monkeypatch):
    monkeypatch.setattr(qt_bridge.Api, "due_reminders", lambda self: [])
    assert qt_bridge.Bridge().remind() == 0                                       # asked, nothing due


def test_the_build_check_names_what_a_broken_app_lacks(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_app
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    app = tmp_path / "JobHelper.app"
    (app / "Contents" / "Resources" / "ui_qt").mkdir(parents=True)
    (app / "Contents" / "Resources" / "ui_qt" / "Main.qml").write_text("")
    import plistlib
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "other.id"}))
    check = build_app.AppCheck(app)
    assert check.run() is False
    wrong = " | ".join(check.problems)
    for missing in ("its program", "bundle id", "Chrome", "icon.icns", "Claude program", "signed"):
        assert missing in wrong, missing
    assert "Main.qml" not in wrong                                                # what is there is not reported
