"""The Claude program used for the sign-in: the SDK's own copy first, an installed one only without it."""
import sys

import pytest

from jobhelper import claude_cli, qt_bridge
from jobhelper.claude_cli import ClaudeCli


def _program(path, says='{"loggedIn": true}'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\necho '{says}' \"$@\"\n")
    path.chmod(0o755)
    return path


def test_the_sdks_copy_comes_first(tmp_path):
    bundled = _program(tmp_path / "sdk" / "claude")
    cli = ClaudeCli(bundled, which=lambda name: "/somewhere/else/claude")
    assert cli.path() == str(bundled)


def test_without_the_sdks_copy_the_path_then_the_usual_folders(tmp_path):
    usual = _program(tmp_path / "home" / ".local" / "bin" / "claude")
    assert ClaudeCli(tmp_path / "missing", which=lambda name: "/opt/x/claude").path() == "/opt/x/claude"
    # an app opened from Finder: nothing on its PATH, but the program is in a usual folder
    assert ClaudeCli(None, which=lambda name: None, places=(str(tmp_path / "nowhere"), str(usual))).path() == str(usual)


def test_a_file_that_cannot_run_is_not_the_program(tmp_path):
    stub = tmp_path / "sdk" / "claude"
    stub.parent.mkdir()
    stub.write_text("not a program")
    assert ClaudeCli(stub, which=lambda name: None, places=()).path() == ""


def test_auth_status_runs_the_found_program(tmp_path):
    cli = ClaudeCli(_program(tmp_path / "claude"), which=lambda name: None, places=())
    done = cli.auth_status()
    assert done.returncode == 0 and done.stdout.strip() == '{"loggedIn": true} auth status'


def test_no_program_is_a_clear_sentence(tmp_path):
    cli = ClaudeCli(None, which=lambda name: None, places=())
    with pytest.raises(FileNotFoundError, match="Claude program is not on this Mac"):
        cli.auth_status()
    with pytest.raises(FileNotFoundError):
        cli.login_script()


def test_the_sign_in_opens_terminal_on_the_full_path_quoted(tmp_path):
    odd = _program(tmp_path / "Application Support" / 'it\'s "here"' / "claude")
    script = ClaudeCli(odd, which=lambda name: None, places=()).login_script()
    assert script[0] == "osascript" and 'tell application "Terminal" to activate' in script
    line = script[-1]
    assert line.startswith('tell application "Terminal" to do script "') and line.endswith(' auth login"')
    import re
    import shlex
    inner = re.sub(r"\\(.)", r"\1", line[len('tell application "Terminal" to do script "'):-1])   # as AppleScript reads it
    assert shlex.split(inner) == [str(odd), "auth", "login"]                  # the shell gets exactly the program


def test_the_real_sdk_carries_a_copy():
    assert ClaudeCli.of_the_sdk().path().endswith("/_bundled/claude")              # only looked at, never run


@pytest.fixture
def bridge(qapp, isolate_data):
    return qt_bridge.Bridge()


def test_sign_in_button_starts_terminal_with_the_found_program(bridge, monkeypatch, tmp_path):
    started = []
    program = _program(tmp_path / "claude")
    monkeypatch.setattr(ClaudeCli, "of_the_sdk", classmethod(lambda cls: cls(program, which=lambda n: None, places=())))
    monkeypatch.setattr(qt_bridge.subprocess, "Popen", lambda args: started.append(args))
    monkeypatch.setattr(sys, "platform", "darwin")
    assert bridge.claudeLogin() == {"ok": True} and str(program) in started[0][-1]


def test_sign_in_button_without_the_program_says_so(bridge, monkeypatch):
    monkeypatch.setattr(ClaudeCli, "of_the_sdk", classmethod(lambda cls: cls(None, which=lambda n: None, places=())))
    monkeypatch.setattr(qt_bridge.subprocess, "Popen", lambda args: pytest.fail("nothing to start"))
    monkeypatch.setattr(sys, "platform", "darwin")
    assert bridge.claudeLogin() == {"ok": False, "msg": claude_cli.MISSING}


def test_sign_in_button_says_when_terminal_cannot_open(bridge, monkeypatch, tmp_path):
    program = _program(tmp_path / "claude")
    monkeypatch.setattr(ClaudeCli, "of_the_sdk", classmethod(lambda cls: cls(program, which=lambda n: None, places=())))

    def no_osascript(args):
        raise FileNotFoundError("osascript")
    monkeypatch.setattr(qt_bridge.subprocess, "Popen", no_osascript)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert bridge.claudeLogin() == {"ok": False, "msg": "Terminal could not be opened."}
