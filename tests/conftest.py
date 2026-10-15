"""Make the project root importable and provide shared fixtures."""
import base64
import os
import sys

# Before anything imports jobhelper: tests must never talk to the real Keychain.
os.environ["JOBHELPER_VAULT_BACKEND"] = "memory"
os.environ.pop("IMAP_PASSWORD", None)
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


TEST_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")


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
    monkeypatch.setattr(notify, "ensure_app", lambda: None)   # nor build the helper app
    import types

    from jobhelper import api_core, api_system  # noqa: F401
    monkeypatch.setattr(api_core.Desktop, "open", lambda self, target: None)   # never open a real file, folder or web page
    monkeypatch.setattr(api_core.Desktop, "reveal", lambda self, target: None)  # nor a real Finder window
    from jobhelper import agent2_search
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)                         # the app refuses to ask with it set; tests set it on purpose
    monkeypatch.setattr(agent2_search, "refetch_description", lambda job: "")     # never read a real job board
    monkeypatch.setattr(agent2_search, "posting_closed", lambda job: None)        # nor ask one whether a posting is still open
    from jobhelper import email_client
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


@pytest.fixture(scope="session")
def qapp():
    """One offscreen Qt application for the whole test session (UI tests)."""
    import os

    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])
