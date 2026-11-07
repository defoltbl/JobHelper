"""Make the project root importable and provide shared fixtures."""
import base64
import os
import sys

# Before anything imports jobhelper: tests must never talk to the real Keychain.
os.environ["JOBHELPER_VAULT_BACKEND"] = "memory"
# ... nor use your own data folder: a test that forgets isolate_data writes into a throwaway one.
import tempfile  # noqa: E402

if not os.environ.get("JOBHELPER_TEST_HOME"):          # once, also when a test imports this file again
    os.environ["JOBHELPER_TEST_HOME"] = tempfile.mkdtemp(prefix="jobhelper-test-home-")
os.environ["JOBHELPER_HOME"] = os.environ["JOBHELPER_TEST_HOME"]     # never a JOBHELPER_HOME of your own shell
os.environ.pop("IMAP_PASSWORD", None)
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


TEST_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")


# ── the last line of defence: the run fails if anything in your own data/ changed ──
def _real_data_folders() -> list[Path]:
    """Every place your own data can be: the Library folder, and the old one in the project folder."""
    from jobhelper import home
    return [home.LIBRARY, ROOT / "data"]


def _data_snapshot() -> dict[str, tuple[int, int]]:
    """Size and change time of every file of your own data (the contents are never read)."""
    out = {}
    for root in _real_data_folders():
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and not path.name.startswith("."):      # Finder's own .DS_Store files are not data
                info = path.stat()
                out[str(path)] = (info.st_size, info.st_mtime_ns)
    return out


def data_changes(before: dict, after: dict) -> list[str]:
    """The files of data/ that were added, removed or changed between two snapshots."""
    return sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))


def pytest_sessionstart(session):
    # the first line of defence: the run does not start at all when the data folder is a real one (#79)
    from jobhelper import config
    for real in _real_data_folders():
        if real.resolve() in (config.DATA_DIR.resolve(), *config.DATA_DIR.resolve().parents):
            pytest.exit(f"The tests would use your own data folder ({real.name}): JOBHELPER_HOME is not a test folder.", 2)
    session.config.stash_data_before = _data_snapshot()


def pytest_sessionfinish(session, exitstatus):
    before = getattr(session.config, "stash_data_before", None)
    if before is None:
        return
    changed = data_changes(before, _data_snapshot())
    if changed:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        message = ("Files of your own data changed during the test run: " + ", ".join(changed[:10])
                   + ". A test must use isolate_data. (If the app was open, it may have been the app.)")
        if reporter:
            reporter.write_line(message, red=True, bold=True)
        session.exitstatus = 1


def _fresh_keychain():
    from jobhelper import vault
    vault.use_keychain(vault.MemoryKeychain({vault.KEY_ACCOUNT: TEST_KEY}))


_fresh_keychain()        # also for module-scoped fixtures, which run before the per-test one


@pytest.fixture(autouse=True)
def safe_environment(tmp_path_factory, monkeypatch):
    """Every test gets an in-memory Keychain (with a fixed data key) and a
    throwaway .env, so nothing can reach the real Keychain or the real .env."""
    from jobhelper import config, vault

    assert not isinstance(vault.keychain(), vault.MacKeychain)
    _fresh_keychain()
    monkeypatch.setattr(config, "ENV_PATH", tmp_path_factory.mktemp("env") / ".env")
    own = tmp_path_factory.mktemp("own_letters")              # never your real letters folder, even without isolate_data
    monkeypatch.setattr(config, "MY_LETTERS_DIR", own)
    monkeypatch.setattr(config, "COVER_LETTERS_DIR", own)
    from jobhelper import pdf
    monkeypatch.setattr(pdf, "find_soffice", lambda: "")      # tests do not depend on LibreOffice (pdf tests opt in)
    from jobhelper import llm, usage

    async def no_claude(*args, **kwargs):
        raise AssertionError("A test tried to call Claude. Mock llm.ask / llm.ask_json instead.")

    monkeypatch.setattr(llm, "_ask_async", no_claude)         # never spend the subscription from a test
    from jobhelper import notify
    monkeypatch.setattr(notify, "_run", lambda cmd: None)     # never show a real notification from a test
    monkeypatch.setattr(notify.AppNotifier, "of_the_app", classmethod(lambda cls: None))   # nor the app's own way
    import types

    from jobhelper import api_core, api_system  # noqa: F401
    monkeypatch.setattr(api_core.Desktop, "real_open", api_core.Desktop.open, raising=False)    # for a test that fakes `open` itself
    monkeypatch.setattr(api_core.Desktop, "open", lambda self, target: True)   # never open a real file, folder or web page
    monkeypatch.setattr(api_core.Desktop, "reveal", lambda self, target: None)  # nor a real Finder window
    import webbrowser

    def no_browser(*args, **kwargs):
        raise AssertionError("A test tried to open a real web browser.")
    for name in ("open", "open_new", "open_new_tab"):                             # nor a browser through a library (#79)
        monkeypatch.setattr(webbrowser, name, no_browser)
    from jobhelper import agent2_search
    for name in config.PAID_SETTINGS:                                               # the app refuses to ask with one set; tests set them on purpose
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(agent2_search, "real_refetch_description", agent2_search.refetch_description, raising=False)  # for a test that fakes the readers
    monkeypatch.setattr(agent2_search, "refetch_description", lambda job: "")     # never read a real job board
    monkeypatch.setattr(agent2_search, "posting_closed", lambda job: None)        # nor ask one whether a posting is still open
    from jobhelper import email_client
    monkeypatch.setattr(email_client, "real_try_login", email_client.try_login, raising=False)    # for a test that fakes _open itself
    monkeypatch.setattr(email_client, "try_login", lambda user, password, timeout=8.0, host="": {"ok": True, "msg": ""})   # never a real mail server
    from jobhelper import chrome, trouble

    def no_chrome(*args, **kwargs):
        raise AssertionError("A test tried to talk to the real Chrome. Replace chrome.active_tab / chrome.run instead.")

    monkeypatch.setattr(chrome, "_osascript", no_chrome)      # never reach into the browser of whoever runs the tests
    real_data, spare = config.DATA_DIR, tmp_path_factory.mktemp("trouble")
    monkeypatch.setattr(trouble, "_folder", lambda: spare if config.DATA_DIR == real_data else config.DATA_DIR)   # never a line in the real trouble log
    from jobhelper import housekeeping
    trash = tmp_path_factory.mktemp("trash")
    monkeypatch.setattr(housekeeping, "trash_dir", lambda path: trash)             # never put anything in the real Trash
    monkeypatch.setattr(api_system, "_claude_auth_status",        # never ask the real Claude CLI who is signed in
                        lambda: types.SimpleNamespace(stdout="{}", returncode=1))
    monkeypatch.setattr(config, "USAGE_JSON", tmp_path_factory.mktemp("usage") / "usage.json")
    assert usage.limit_status()["blocked"] is False
    monkeypatch.delenv("JOBHELPER_ENCRYPT", raising=False)
    yield
    _fresh_keychain()


@pytest.fixture
def jobs_cz_html() -> str:
    return (FIXTURES / "jobs_cz_search.html").read_text(encoding="utf-8")


@pytest.fixture
def prace_cz_html() -> str:
    return (FIXTURES / "prace_cz_search.html").read_text(encoding="utf-8")


@pytest.fixture
def linkedin_html() -> str:
    return (FIXTURES / "linkedin_search.html").read_text(encoding="utf-8")


@pytest.fixture
def isolate_data(tmp_path, monkeypatch):
    """Redirect all on-disk paths into a temp dir so tests never touch data/."""
    from jobhelper import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    from jobhelper import usage
    monkeypatch.setattr(usage.LOG, "_last_try", 0.0)        # this run's last question for the limits: none yet
    monkeypatch.setattr(config, "CV_DIR", tmp_path / "cv")
    monkeypatch.setattr(config, "LETTERS_DIR", tmp_path / "cover_letters")
    monkeypatch.setattr(config, "MY_LETTERS_DIR", tmp_path / "my_letters")
    monkeypatch.setattr(config, "COVER_LETTERS_DIR", tmp_path / "my_letters")
    monkeypatch.setattr(config, "TAILORED_CV_DIR", tmp_path / "tailored_cvs")
    monkeypatch.setattr(config, "LETTER_TEMPLATE", tmp_path / "cover_letter_template.docx")
    monkeypatch.setattr(config, "JOBS_JSON", tmp_path / "jobs.json")
    monkeypatch.setattr(config, "EXCEL_PATH", tmp_path / "applications.xlsx")
    monkeypatch.setattr(config, "NEW_JOBS_EXCEL", tmp_path / "new_jobs.xlsx")
    monkeypatch.setattr(config, "PROFILE_JSON", tmp_path / "profile.json")
    monkeypatch.setattr(config, "USAGE_JSON", tmp_path / "usage.json")
    monkeypatch.setattr(config, "RESPONSES_DB", tmp_path / "responses.db")
    monkeypatch.setattr(config, "RESPONSES_REPORT", tmp_path / "responses_report.xlsx")
    monkeypatch.setattr(config, "CV_INSTRUCTION", tmp_path / "cv_adaptation_instruction.md")
    monkeypatch.setattr(config, "LETTER_INSTRUCTION", tmp_path / "cover_letter_instruction.md")
    return tmp_path


@pytest.fixture(scope="module")
def ui(qapp, tmp_path_factory):
    """The real window, loaded offscreen on a temporary data folder: one for each test file that asks for it, so the
    window test files can run side by side (see tests/window_harness.py)."""
    from tests.window_harness import loaded_window
    with loaded_window(tmp_path_factory) as handle:
        yield handle


@pytest.fixture(autouse=True)
def _windows_closed_after(request):
    """A window test leaves no window open, no review queue and no pretend run for the next one."""
    yield
    if "ui" in request.fixturenames:
        from tests.window_harness import close_left_windows
        close_left_windows(request.getfixturevalue("ui"))


@pytest.fixture(scope="session")
def qapp():
    """One offscreen Qt application for the whole test session (UI tests)."""
    import os

    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture(autouse=True)
def _job_list_lock_given_back():
    """store.RunLock counts its holders in class state: a test that left it held would hide another process's lock from
    every later test in this process."""
    yield
    from jobhelper import store
    while store.RunLock._held:
        store.RunLock.release()


@pytest.fixture
def jobs_held_elsewhere(isolate_data):
    """Another process (the weekly run) holds the job list's lock for the test."""
    import subprocess
    import sys
    from jobhelper import config, store
    config.ensure_dirs()
    holder = subprocess.Popen([sys.executable, "-c", (
        "import fcntl, sys, time; f = open(sys.argv[1], 'a+'); fcntl.flock(f, fcntl.LOCK_EX); print('held', flush=True); time.sleep(60)"),
        str(store.RunLock.path())], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        yield holder
    finally:
        holder.kill()
        holder.wait()
