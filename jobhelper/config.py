"""Central configuration and filesystem paths.

Loads settings from a local .env file (if present). No secrets live in code.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from . import home, vault

# Project layout ------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent          # the program (in a packaged app: inside JobHelper.app)
HOME = home.here()                                     # your data: ~/Library/Application Support/JobHelper
DATA_DIR = HOME.data_dir()
CV_DIR = DATA_DIR / "cv"                     # your master CV(s)
TAILORED_CV_DIR = DATA_DIR / "tailored_cvs"  # per-application keyword-tailored CVs
CV_INSTRUCTION = DATA_DIR / "cv_adaptation_instruction.md"  # your rules for adapting the CV
LETTER_TEMPLATE = DATA_DIR / "cover_letter_template.docx"      # letter whose head/format is reused
LETTER_INSTRUCTION = DATA_DIR / "cover_letter_instruction.md"  # your rules for writing letters
LETTERS_DIR = DATA_DIR / "cover_letters"
JOBS_JSON = DATA_DIR / "jobs.json"          # source of truth (the working DB)
PROFILE_JSON = DATA_DIR / "profile.json"     # Agent 1 output
USAGE_JSON = DATA_DIR / "usage.json"         # Claude usage tracker
RESPONSES_DB = DATA_DIR / "responses.db"     # Agent 5: application-response database

# Excel deliverables — each in its own directory.
APPLICATIONS_DIR = DATA_DIR / "excel_applications"
LEADS_DIR = DATA_DIR / "excel_new_jobs"
REPORTS_DIR = DATA_DIR / "excel_reports"
EXCEL_PATH = APPLICATIONS_DIR / "applications.xlsx"  # applications you've sent (+ progress)
NEW_JOBS_EXCEL = LEADS_DIR / "new_jobs.xlsx"         # fresh leads from search, not applied yet
RESPONSES_REPORT = REPORTS_DIR / "responses_report.xlsx"  # Agent 5: analytics report

# Load .env from the data home (does not override real env vars).
ENV_PATH = HOME.env_path()
load_dotenv(ENV_PATH)

# Folder of your own, pre-written cover letters (imported into the tracker).
# Inside the app's data folder unless .env names another place.
MY_LETTERS_DIR = DATA_DIR / "my_letters"


def own_letters_dir(setting: str | None) -> Path:
    """The folder for your own letters: the COVER_LETTERS_DIR setting if it names one, else data/my_letters."""
    return Path(setting).expanduser() if (setting or "").strip() else MY_LETTERS_DIR


COVER_LETTERS_DIR = own_letters_dir(os.getenv("COVER_LETTERS_DIR"))

def _int_env(name: str, default: int, low: int | None = None, high: int | None = None) -> int:
    """A whole number from the environment. A value that is not a number (a typo in .env)
    falls back to the default instead of stopping the app before its window opens."""
    try:
        value = int(str(os.getenv(name, "") or "").strip() or default)
    except ValueError:
        return default
    if low is not None:
        value = max(low, value)
    return min(high, value) if high is not None else value


# Model -------------------------------------------------------------------
# "sonnet" | "opus" | "haiku". Uses your Claude subscription via the CLI as
# long as ANTHROPIC_API_KEY is NOT set.
MODEL = os.getenv("JOBHELPER_MODEL", "sonnet").strip() or "sonnet"

# Leads scoring below this (once scored) are hidden from new_jobs.xlsx.
# 0 = show every lead (user preference). Raise via JOBHELPER_MIN_LEAD_SCORE.
MIN_LEAD_SCORE = _int_env("JOBHELPER_MIN_LEAD_SCORE", 0, 0, 100)

# Only keep jobs posted within this many days (where a posting date is known).
# 0 disables the recency filter.
MAX_JOB_AGE_DAYS = _int_env("JOBHELPER_MAX_AGE_DAYS", 10, 0)

# Write a cover letter + tailored CV for jobs scoring at least this.
DEFAULT_THRESHOLD = _int_env("JOBHELPER_THRESHOLD", 50, 0, 100)
# At/above this a match is "strong"; between DEFAULT_THRESHOLD and this it's
# "moderate" (letter still written, but flagged to review before sending).
STRONG_THRESHOLD = 60
# How many postings are scored in one model call. Every call carries a fixed
# overhead of about ten thousand tokens, so five at a time uses far less of the
# subscription than five single calls.
SCORE_BATCH = _int_env("JOBHELPER_SCORE_BATCH", 5, 1, 20)

# Adzuna ------------------------------------------------------------------
# NOTE: Adzuna does NOT support the Czech Republic. Use it for other countries
# (pl, de, gb, at, ...). For Prague/Czech jobs, use Jooble below.
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "").strip()
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "").strip()
ADZUNA_COUNTRY = os.getenv("ADZUNA_COUNTRY", "pl").strip() or "pl"
ADZUNA_SUPPORTED = {
    "at", "au", "be", "br", "ca", "ch", "de", "es", "fr", "gb",
    "in", "it", "mx", "nl", "nz", "pl", "sg", "us", "za",
}

# Jooble ------------------------------------------------------------------
# Free API key (covers the Czech Republic / Prague). Request one at
# https://jooble.org/api/about
JOOBLE_API_KEY = os.getenv("JOOBLE_API_KEY", "").strip()

# IMAP (email sync) -------------------------------------------------------
# The mail server of each mailbox: read from the address (see mailhosts.py) unless one is set here.
IMAP_HOST = os.getenv("IMAP_HOST", "").strip()
IMAP_HOST_2 = os.getenv("IMAP_HOST_2", "").strip()
IMAP_PORT = _int_env("IMAP_PORT", 993, 1, 65535)
IMAP_USER = os.getenv("IMAP_USER", "").strip()
# The app password lives in the macOS Keychain; .env is only read for old setups.
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "").strip() or vault.get_secret(vault.IMAP_ACCOUNT)
IMAP_LOOKBACK_DAYS = _int_env("IMAP_LOOKBACK_DAYS", 30, 1)
# Optional second mailbox (same mail provider): replies that go to another address.
IMAP_USER_2 = os.getenv("IMAP_USER_2", "").strip()
IMAP_PASSWORD_2 = os.getenv("IMAP_PASSWORD_2", "").strip() or vault.get_secret(vault.IMAP_ACCOUNT_2)


def has_adzuna() -> bool:
    return bool(ADZUNA_APP_ID and ADZUNA_APP_KEY)


def adzuna_available() -> bool:
    """Adzuna configured AND the configured country is supported by Adzuna."""
    return has_adzuna() and ADZUNA_COUNTRY in ADZUNA_SUPPORTED


def has_jooble() -> bool:
    return bool(JOOBLE_API_KEY)


def has_imap() -> bool:
    return bool(IMAP_USER and IMAP_PASSWORD)


def using_paid_api() -> bool:
    """True if an API key is set, which would bill the paid API instead of
    the subscription. We warn the user about this."""
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def work_dir() -> Path:
    """An empty folder of the app's own that the app, the Claude program and the other programs it starts
    work in. A Mac app that Finder or launchd starts works in / (the whole disk), and the Claude program
    watches its working folder: there it touched Desktop, Downloads, Music and other apps' data, and
    macOS asked you about each of them."""
    folder = DATA_DIR / "work"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def ensure_dirs() -> None:
    for d in (DATA_DIR, CV_DIR, TAILORED_CV_DIR, LETTERS_DIR,
              APPLICATIONS_DIR, LEADS_DIR, REPORTS_DIR, COVER_LETTERS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _private(path: Path) -> None:
    """Readable by this user only."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def update_env(values: dict) -> None:
    """Create/update keys in the project .env (preserving other lines) and
    reflect them in os.environ immediately. Lets the app manage its own
    configuration instead of the user hand-editing .env."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    keys = set(values)
    out, seen = [], set()
    for ln in lines:
        head = ln.split("=", 1)[0].strip() if "=" in ln else None
        if head in keys:
            out.append(f"{head}={values[head]}")
            seen.add(head)
        else:
            out.append(ln)
    for k in keys:
        if k not in seen:
            out.append(f"{k}={values[k]}")
    ENV_PATH.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    _private(ENV_PATH)
    for k, v in values.items():
        os.environ[str(k)] = str(v)


def remove_env(keys) -> None:
    """Drop keys from the project .env (and from this process's environment)."""
    keys = set(keys)
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        kept = [ln for ln in lines if not ("=" in ln and ln.split("=", 1)[0].strip() in keys)]
        if kept != lines:
            ENV_PATH.write_text("\n".join(kept).rstrip("\n") + "\n", encoding="utf-8")
            _private(ENV_PATH)
    for k in keys:
        os.environ.pop(k, None)


def imap_host(box: int = 1) -> str:
    """The server a mailbox is read from: the one set for it, else the one its address tells, else Gmail's."""
    from . import mailhosts
    typed, user = (IMAP_HOST, IMAP_USER) if box == 1 else (IMAP_HOST_2, IMAP_USER_2)
    return typed or str(mailhosts.server_for(user)["host"]) or "imap.gmail.com"


def _keep_host(key: str, host: str | None) -> str:
    """Write (or, when empty, remove) a mailbox's own server in .env; None leaves it as it is."""
    if host is None:
        return IMAP_HOST if key == "IMAP_HOST" else IMAP_HOST_2
    host = host.strip().lower()
    if host:
        update_env({key: host})
    else:
        remove_env([key])
    return host


@dataclass(frozen=True)
class _Mailbox:
    """Where one mailbox is kept: its address in .env, its password in the Keychain (in .env only without one)."""
    user_key: str
    password_key: str
    account: str

    def save(self, user: str, password: str, known: str, also: dict | None = None) -> str:
        """Save the address (and `also`, more .env lines) and the password. A blank password keeps the one
        already saved (`known`): the address can change without typing the password again. Returns the password in use."""
        values = {self.user_key: user, **(also or {})}
        if vault.keychain().available:
            if password:
                vault.set_secret(self.account, password)
            update_env(values)
            remove_env([self.password_key])
        else:
            update_env({**values, self.password_key: password} if password else values)
        return password or known


_FIRST_MAILBOX = _Mailbox("IMAP_USER", "IMAP_PASSWORD", vault.IMAP_ACCOUNT)
_SECOND_MAILBOX = _Mailbox("IMAP_USER_2", "IMAP_PASSWORD_2", vault.IMAP_ACCOUNT_2)


def set_imap(user: str, password: str, lookback: int | None = None, host: str | None = None) -> None:
    """Save the mailbox login and apply it live: the address goes to .env,
    the app password to the macOS Keychain (to .env only where there is none)."""
    global IMAP_USER, IMAP_PASSWORD, IMAP_LOOKBACK_DAYS, IMAP_HOST
    user, password = user.strip(), password.strip()
    IMAP_HOST = _keep_host("IMAP_HOST", host)
    also = {}
    if lookback is not None:
        also["IMAP_LOOKBACK_DAYS"] = str(int(lookback))
        IMAP_LOOKBACK_DAYS = int(lookback)
    IMAP_PASSWORD = _FIRST_MAILBOX.save(user, password, IMAP_PASSWORD, also)
    IMAP_USER = user


def mailboxes() -> list[dict[str, str]]:
    """The mailboxes to scan: the main one, then the optional second one."""
    boxes = []
    if IMAP_USER and IMAP_PASSWORD:
        boxes.append({"user": IMAP_USER, "password": IMAP_PASSWORD, "host": imap_host(1)})
    if IMAP_USER_2 and IMAP_PASSWORD_2 and IMAP_USER_2.lower() != IMAP_USER.lower():
        boxes.append({"user": IMAP_USER_2, "password": IMAP_PASSWORD_2, "host": imap_host(2)})
    return boxes


def set_imap2(user: str, password: str, host: str | None = None) -> None:
    """Save or change the optional second mailbox (address in .env, password in the Keychain)."""
    global IMAP_USER_2, IMAP_PASSWORD_2, IMAP_HOST_2
    user, password = user.strip(), password.strip()
    IMAP_HOST_2 = _keep_host("IMAP_HOST_2", host)
    IMAP_PASSWORD_2 = _SECOND_MAILBOX.save(user, password, IMAP_PASSWORD_2)
    IMAP_USER_2 = user


def remove_imap2() -> None:
    """Forget the second mailbox: address, and its password from the Keychain."""
    global IMAP_USER_2, IMAP_PASSWORD_2, IMAP_HOST_2
    remove_env(["IMAP_USER_2", "IMAP_PASSWORD_2", "IMAP_HOST_2"])
    IMAP_HOST_2 = ""
    try:
        vault.delete_secret(vault.IMAP_ACCOUNT_2)
    except Exception as e:  # noqa: BLE001 - the address is forgotten either way
        from . import trouble
        trouble.note("removing the second mailbox's password from the Keychain", e)
    IMAP_USER_2 = IMAP_PASSWORD_2 = ""


def move_password_to_keychain() -> bool:
    """One-time upgrade: take IMAP_PASSWORD out of .env and keep it in the
    Keychain instead. The line is removed only after the Keychain copy reads
    back correctly. True if a password was moved."""
    global IMAP_PASSWORD
    if not vault.keychain().available or not ENV_PATH.exists():
        return False
    found = ""
    for ln in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in ln and ln.split("=", 1)[0].strip() == "IMAP_PASSWORD":
            found = ln.split("=", 1)[1].strip().strip("'\"")
    if not found:
        return False
    vault.set_secret(vault.IMAP_ACCOUNT, found)
    if vault.get_secret(vault.IMAP_ACCOUNT) != found:
        return False
    remove_env(["IMAP_PASSWORD"])
    IMAP_PASSWORD = found
    return True


TEXT_SIZES = (100, 110, 125, 150)     # per cent: everything in the window larger, for a large or very sharp screen


def text_scale() -> float:
    """How much larger the whole window is drawn (1.0 = as designed), from Options. Anything unexpected means 1.0."""
    size = ui_settings().get("text_size")
    return size / 100 if not isinstance(size, bool) and size in TEXT_SIZES else 1.0


def ui_settings() -> dict:
    """Options saved from the desktop app (data/ui_settings.json), or {}."""
    import json
    try:
        data = json.loads(vault.read_text(DATA_DIR / "ui_settings.json"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, vault.VaultError):
        return {}


def candidate_facts(cv_text: str = "") -> dict[str, str]:
    """What the app may say about the person besides the CV: name (first line of
    the CV), where they are based (the search city), and - only if entered in
    Options, "About you" - the right to work and when they can start."""
    o = ui_settings()
    lines = [ln.strip() for ln in (cv_text or "").splitlines() if ln.strip()]
    name = lines[0] if lines and len(lines[0]) <= 60 else ""
    first = name.split()[0] if name else ""
    return {"name": name, "first_name": first,
            "location": str(o.get("where") or "").strip(),
            "right_to_work": str(o.get("about_right_to_work") or "").strip(),
            "start": str(o.get("about_start") or "").strip()}


def search_country() -> str:
    """The country typed in Options for the search ('' = the country of the city)."""
    return str(ui_settings().get("country") or "").strip()


MAX_EXPERIENCE_NOTES = 4000


def experience_notes() -> str:
    """What the person wrote in Options about their real work beyond the CV (tasks, tools,
    team, results). It is theirs and true, so it may be used like the CV itself."""
    return str(ui_settings().get("about_experience") or "").strip()[:MAX_EXPERIENCE_NOTES]


def facts_block(cv_text: str = "") -> str:
    """The same facts as lines for a prompt. Facts that were not entered are
    named as unknown, so the model leaves them out instead of inventing them."""
    f = candidate_facts(cv_text)
    lines = [f"- Based in: {f['location'] or 'not stated - do not mention a location'}",
             f"- Right to work: {f['right_to_work'] or 'not stated - do not mention the right to work'}",
             f"- Can start: {f['start'] or 'not stated - do not mention a start date'}"]
    return "\n".join(lines)


def fill_placeholders(text: str, cv_text: str = "") -> str:
    """Replace {{name}}, {{first_name}}, {{location}}, {{right_to_work}} and {{start}}
    in a rules file, so one set of rules can serve whoever's CV is loaded."""
    facts = candidate_facts(cv_text)

    def swap(m):
        value = facts.get(m.group(1).lower())
        return value if value else m.group(0) if value is None else "(not stated)"
    return re.sub(r"\{\{\s*([A-Za-z_]+)\s*\}\}", swap, text or "")


def apply_ui_settings(opts: dict | None = None) -> None:
    """Make the app's saved "Claude model" and "Hide leads below" take effect."""
    global MODEL, MIN_LEAD_SCORE
    o = ui_settings() if opts is None else opts
    model = str(o.get("model") or "").strip()
    if model:
        MODEL = model
    try:
        MIN_LEAD_SCORE = max(0, min(100, int(o["min_lead_score"])))
    except (KeyError, TypeError, ValueError):
        pass
