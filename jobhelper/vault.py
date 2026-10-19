"""Secrets and encryption at rest.

* Secrets (the mailbox passwords, the data key) live in the macOS Keychain,
  never in a file inside the project.
* Data files (jobs, profile, options, the responses database) and everything
  under ``data/backups/`` are stored AES-256-GCM encrypted with the data key.

Reading is transparent: a file that is not encrypted yet is returned as is, so
old data keeps working and is encrypted the next time it is saved (or right
away by ``protect_all``). Documents you open in Word or Excel (CVs, letters,
trackers) are not encrypted here - protect those with an encrypted drive.

Without a Keychain (not macOS) or with ``JOBHELPER_ENCRYPT=0`` everything falls
back to plain files.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SERVICE = os.getenv("JOBHELPER_VAULT_SERVICE", "JobHelper")
MAGIC = b"JHENC1\n"                 # start of every encrypted file
BACKUP_SUFFIX = ".enc"

KEY_ACCOUNT = "data_key"
IMAP_ACCOUNT = "imap_password"
IMAP_ACCOUNT_2 = "imap_password_2"
LABELS = {
    KEY_ACCOUNT: "JobHelper: data encryption key",
    IMAP_ACCOUNT: "JobHelper: mailbox password",
    IMAP_ACCOUNT_2: "JobHelper: mailbox password (second mailbox)",
    "integrity_baseline": "JobHelper: tamper-check baseline",
}


class VaultError(RuntimeError):
    """The data cannot be protected or opened (missing or wrong key, damaged file)."""


# ── where secrets are kept ──────────────────────────────────────────────────
class MemoryKeychain:
    """In-process store, used by the tests instead of the real Keychain."""
    available = True

    def __init__(self, items: dict[str, str] | None = None) -> None:
        self.items = dict(items or {})

    def get(self, account: str) -> str | None:
        return self.items.get(account)

    def set(self, account: str, value: str) -> None:
        self.items[account] = value

    def delete(self, account: str) -> None:
        self.items.pop(account, None)


class NoKeychain(MemoryKeychain):
    """No secure store on this system: nothing is kept, encryption stays off."""
    available = False

    def set(self, account: str, value: str) -> None:
        raise VaultError("No Keychain is available on this system.")


class MacKeychain:
    """The login Keychain, through the system ``security`` tool."""
    available = True

    NOT_THERE = 44          # what `security` answers when the Keychain has no such item

    def get(self, account: str) -> str | None:
        """The secret, or None when the Keychain holds none under this name. A Keychain that cannot be read (locked,
        not answering) is an error, not "none": taking it for "none" could start a new data key over the real one."""
        try:
            r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
                               capture_output=True, text=True, timeout=20)
        except (subprocess.TimeoutExpired, OSError) as e:
            raise VaultError("The Keychain did not answer. Unlock it (log in to this Mac again) and try once more.") from e
        if r.returncode == self.NOT_THERE or (r.returncode != 0 and "could not be found" in (r.stderr or "")):
            return None
        if r.returncode != 0:
            raise VaultError("The Keychain could not be read (it may be locked). Unlock it and try once more.")
        return r.stdout.rstrip("\n")

    def set(self, account: str, value: str) -> None:
        if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise VaultError("That value cannot be stored in the Keychain.")
        # Sent on stdin (interactive mode), so the secret never shows up in the
        # process list the way a command-line argument would.
        cmd = "add-generic-password -U -s %s -a %s -l %s -w %s\n" % (
            _quote(SERVICE), _quote(account), _quote(LABELS.get(account, "JobHelper: " + account)), _quote(value))
        r = subprocess.run(["security", "-i"], input=cmd, capture_output=True, text=True, timeout=20)
        if r.returncode != 0 or self.get(account) != value:
            raise VaultError("Could not save to the Keychain. " + (r.stderr or "").strip())

    def delete(self, account: str) -> None:
        subprocess.run(["security", "delete-generic-password", "-s", SERVICE, "-a", account],
                       capture_output=True, text=True, timeout=20)


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


_keychain = None


def keychain():
    global _keychain
    if _keychain is None:
        kind = os.getenv("JOBHELPER_VAULT_BACKEND", "").lower()
        if kind == "memory":
            _keychain = MemoryKeychain()
        elif kind == "none" or sys.platform != "darwin":
            _keychain = NoKeychain()
        else:
            _keychain = MacKeychain()
    return _keychain


def use_keychain(backend) -> None:
    """Swap the secret store (tests) and forget any cached key."""
    global _keychain, _key
    _keychain, _key = backend, None


def get_secret(account: str) -> str:
    try:
        return keychain().get(account) or ""
    except Exception:  # noqa: BLE001 - a broken Keychain must not crash a read
        return ""


def set_secret(account: str, value: str) -> None:
    keychain().set(account, value)


def delete_secret(account: str) -> None:
    keychain().delete(account)


# ── the data key ────────────────────────────────────────────────────────────
_key: bytes | None = None


def enabled() -> bool:
    return os.getenv("JOBHELPER_ENCRYPT", "1") != "0" and keychain().available


def _marker() -> Path:
    from . import config
    return config.DATA_DIR / "vault.json"


def _key_id(key: bytes) -> str:
    return hashlib.sha256(b"jobhelper-key-id" + key).hexdigest()[:16]


def _read_marker() -> dict:
    try:
        data = json.loads(_marker().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _decode_key(text: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(text.strip().encode("ascii"))
    except Exception as e:  # noqa: BLE001
        raise VaultError("That is not a valid JobHelper key.") from e
    if len(key) != 32:
        raise VaultError("That is not a valid JobHelper key.")
    return key


def data_key() -> bytes:
    """The 256-bit key for this data folder; created on first use.

    A new key is only ever created for a folder that has never been encrypted.
    If the folder was encrypted with a key that is no longer in the Keychain
    (new Mac, Keychain reset) this raises instead of silently starting over.
    """
    global _key
    if _key is not None:
        return _key
    if not enabled():
        raise VaultError("Encryption is not available on this system.")
    marker = _read_marker()
    stored = keychain().get(KEY_ACCOUNT)
    if stored:
        key = _decode_key(stored)
        if marker.get("key_id") and marker["key_id"] != _key_id(key):
            raise VaultError("The key in the Keychain does not match this data. Paste your recovery key in the Account card.")
    else:
        if marker.get("key_id") or any(file_is_encrypted(path) for path in data_files()):
            # (the second test: the note of the key, vault.json, is gone but the data is plainly encrypted)
            raise VaultError("This data is encrypted, but its key is not in the Keychain. Paste your recovery key in the "
                             "Account card.")
        key = os.urandom(32)
        keychain().set(KEY_ACCOUNT, base64.urlsafe_b64encode(key).decode("ascii"))
    if not marker.get("key_id"):
        from . import config
        config.ensure_dirs()
        _marker().write_text(json.dumps({"key_id": _key_id(key), "created": datetime.now().isoformat(timespec="seconds")},
                                        indent=2), encoding="utf-8")
    _key = key
    return key


def recovery_key() -> str:
    """The key as text, for the user to keep somewhere safe."""
    return base64.urlsafe_b64encode(data_key()).decode("ascii")


def restore_key(text: str) -> None:
    """Put a saved recovery key back into the Keychain (new Mac, Keychain reset)."""
    global _key
    key = _decode_key(text)
    marker = _read_marker()
    if marker.get("key_id") and marker["key_id"] != _key_id(key):
        raise VaultError("That key does not belong to this data.")
    keychain().set(KEY_ACCOUNT, base64.urlsafe_b64encode(key).decode("ascii"))
    _key = None
    data_key()


def state() -> str:
    """'ok' (encrypting), 'off' (no Keychain / switched off) or 'locked' (key problem)."""
    if not enabled():
        return "off"
    try:
        data_key()
        return "ok"
    except VaultError:
        return "locked"


# ── bytes ───────────────────────────────────────────────────────────────────
def is_encrypted(data: bytes) -> bool:
    return data.startswith(MAGIC)


def encrypt(data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(data_key()).encrypt(nonce, data, MAGIC)


def decrypt(blob: bytes) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not is_encrypted(blob):
        return blob
    body = blob[len(MAGIC):]
    try:
        return AESGCM(data_key()).decrypt(body[:12], body[12:], MAGIC)
    except InvalidTag as e:
        raise VaultError("An encrypted file is damaged or was written with a different key.") from e


# ── files ───────────────────────────────────────────────────────────────────
def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # its own temporary file per writer: the window and a running search can save the same file at once
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    try:
        os.chmod(tmp, 0o600)             # readable by this user only
    except OSError:
        pass
    os.replace(tmp, path)


def read_bytes(path: Path) -> bytes:
    return decrypt(Path(path).read_bytes())


def write_bytes(path: Path, data: bytes) -> None:
    _write_atomic(Path(path), encrypt(data) if enabled() else data)


def read_text(path: Path) -> str:
    return read_bytes(path).decode("utf-8")


def write_text(path: Path, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))


class JsonFile:
    """One small JSON store, kept encrypted: `name` in the data folder, or the path `where()` gives (read at each use,
    so a setting that moves the file is followed).

    `load` is strict: None when there is no file, ValueError when it is damaged. `read` is lenient: None when there is
    no file or it cannot be parsed. Both raise VaultError for a file the data key cannot open: a store must not read
    it as empty, or its next save writes an empty store over what is kept. A store that may show nothing in that case
    catches VaultError itself."""

    def __init__(self, name: str, where: Callable[[], Path] | None = None) -> None:
        self._name, self._where = name, where

    @property
    def path(self) -> Path:
        if self._where is not None:
            return Path(self._where())
        from . import config
        return config.DATA_DIR / self._name

    def load(self) -> Any:
        try:
            text = read_text(self.path)
        except FileNotFoundError:
            return None
        return json.loads(text)

    def read(self) -> Any:
        try:
            return self.load()
        except VaultError:
            raise
        except (OSError, ValueError):
            return None

    def exists(self) -> bool:
        return self.path.exists()

    def write(self, value: Any, indent: int = 2) -> None:
        from . import config
        config.ensure_dirs()
        write_text(self.path, json.dumps(value, ensure_ascii=False, indent=indent))


def file_is_encrypted(path: Path) -> bool:
    try:
        with Path(path).open("rb") as f:
            return f.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def data_files() -> list[Path]:
    """The files that are kept encrypted."""
    from . import answer_memory, assistant_notes, config, planner     # each small store names its own file
    return [config.JOBS_JSON, config.PROFILE_JSON, config.ui_settings_file(), config.RESPONSES_DB,
            config.DATA_DIR / "last_run.json", planner.COMPANY_NOTES.path, config.DATA_DIR / "filtered_out.json",
            config.DATA_DIR / "my_details.json", answer_memory.MEMORY.path, assistant_notes.NOTES.path]


def encrypt_file(path: Path) -> bool:
    """Encrypt one file in place, after proving it decrypts back. True if it changed."""
    path = Path(path)
    if not path.is_file() or file_is_encrypted(path):
        return False
    plain = path.read_bytes()
    blob = encrypt(plain)
    if decrypt(blob) != plain:
        raise VaultError(f"Self-check failed while encrypting {path.name}; it was left untouched.")
    _write_atomic(path, blob)
    return True


# ── backups ─────────────────────────────────────────────────────────────────
def backups_dir() -> Path:
    from . import config
    return config.DATA_DIR / "backups"


def encrypt_tree(root: Path) -> int:
    """Encrypt every plain file under root (name gets '.enc'). Returns how many."""
    root, done = Path(root), 0
    if not root.is_dir():
        return 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name == ".DS_Store" or path.name.endswith(".tmp"):
            continue
        if path.suffix == BACKUP_SUFFIX and file_is_encrypted(path):
            continue
        plain = path.read_bytes()
        blob = plain if is_encrypted(plain) else encrypt(plain)
        if decrypt(blob) != decrypt(plain):
            raise VaultError(f"Self-check failed while encrypting {path.name}; it was left untouched.")
        _write_atomic(path.with_name(path.name + BACKUP_SUFFIX), blob)
        path.unlink()
        done += 1
    return done


def _backup_copy(dest: Path, plain: bytes) -> Path:
    """Write a file into a backup: with ".enc" and encrypted while protection is on, as it is otherwise. Returns it."""
    out = dest.with_name(dest.name + BACKUP_SUFFIX) if enabled() else dest
    _write_atomic(out, encrypt(plain) if enabled() else plain)
    return out


def make_backup(label: str, paths: list[Path] | None = None) -> Path:
    """Copy the given files (default: the data files) into an encrypted backup folder."""
    dest = backups_dir() / f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    dest.mkdir(parents=True, exist_ok=True)
    for src in (paths if paths is not None else data_files()):
        src = Path(src)
        if src.is_file():
            _backup_copy(dest / src.name, read_bytes(src))
    return dest


def keep_copy(path: Path, folder: str) -> Path | None:
    """Put an encrypted copy of one file into backups/<folder>/ (time-stamped name).
    Used before the app overwrites or removes a document."""
    path = Path(path)
    if not path.is_file():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _backup_copy(backups_dir() / folder / f"{path.stem}.{stamp}{path.suffix}", path.read_bytes())


def stash(paths, folder: str) -> int:
    """Move files out of the working folders into backups/<folder>/ (encrypted). Returns how many."""
    moved = 0
    for path in paths:
        path = Path(path)
        if keep_copy(path, folder):
            path.unlink()
            moved += 1
    return moved


def restore_backup(src: Path, dest: Path) -> int:
    """Decrypt a backup file or folder into dest (plain, openable files)."""
    src, dest, done = Path(src), Path(dest), 0
    files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file())
    base = src.parent if src.is_file() else src
    for path in files:
        if path.name == ".DS_Store":
            continue
        rel = path.relative_to(base)
        name = rel.name[:-len(BACKUP_SUFFIX)] if rel.name.endswith(BACKUP_SUFFIX) else rel.name
        out = dest / rel.parent / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(read_bytes(path))
        done += 1
    return done


def set_aside(path: Path, folder: str) -> Path | None:
    """Move a file, as it is on disk, into backups/<folder>/ with a time-stamped name (a damaged file that is
    replaced is kept there, never deleted). Returns where it went, or None when there was no file."""
    path = Path(path)
    if not path.is_file():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backups_dir() / folder / f"{path.stem}.{stamp}{path.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    path.replace(dest)
    return dest


def newest_good_copy(path: Path) -> tuple[bytes, Path] | None:
    """The newest backup copy of a data file that decrypts and opens as what it is (JSON, a database):
    (its plain bytes, the backup file), or None when no copy is usable."""
    path = Path(path)
    names = {path.name, path.name + BACKUP_SUFFIX}
    copies = [p for p in backups_dir().rglob("*") if p.is_file() and p.name in names] if backups_dir().is_dir() else []
    for copy in sorted(copies, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = read_bytes(copy)
        except Exception:  # noqa: BLE001 - a copy that cannot be read is skipped
            continue
        if not _usable(path.name, data):
            return data, copy
    return None


# ── one call that brings a data folder up to date ───────────────────────────
def protect_all() -> dict:
    """Move secrets to the Keychain, encrypt data files and backups, and take the
    first tamper-check baseline. Safe to call on every start: it only does what
    is still missing. Returns what it did."""
    from . import config, integrity
    report = {"state": state(), "password_moved": False, "files": [], "backups": 0, "baseline": False}
    if report["state"] != "ok":
        return report
    report["password_moved"] = config.move_password_to_keychain()
    for path in data_files():
        if encrypt_file(path):
            report["files"].append(path.name)
    report["backups"] = encrypt_tree(backups_dir())
    report["baseline"] = integrity.ensure_baseline()
    from . import housekeeping
    report["housekeeping"] = housekeeping.run()      # old backups and long logs
    return report


# ── proof that a backup can really be restored ──────────────────────────────
def _usable(name: str, data: bytes) -> str:
    """'' if restored content can be used as what it is, otherwise what is wrong with it."""
    import json
    import sqlite3
    try:
        if name.endswith(".json"):
            json.loads(data.decode("utf-8"))
        elif name.endswith(".db"):
            conn = sqlite3.connect(":memory:")
            try:
                conn.deserialize(data)
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    return "the database is damaged"
            finally:
                conn.close()
    except Exception as e:  # noqa: BLE001 - any failure means "not usable"
        return f"cannot be opened ({type(e).__name__})"
    return ""


def restore_test() -> dict:
    """Back up the data files, restore that backup into a throwaway folder, and
    compare every restored file with the live data. Then try to decrypt every
    older backup too. The live data is only read; the throwaway folder (plain
    copies of your data) is removed before this returns.

    {ok, backup, files: [{name, ok, problem}], older: {files, readable, unreadable: [names]}}"""
    import shutil
    import tempfile
    if state() != "ok":
        raise VaultError("Protection is off on this Mac, so there are no encrypted backups to test.")
    live = {p.name: read_bytes(p) for p in data_files() if Path(p).is_file()}
    backup = make_backup("restore_test")
    scratch = Path(tempfile.mkdtemp(prefix="jobhelper-restore-"))
    files = []
    try:
        restore_backup(backup, scratch)
        for name, original in sorted(live.items()):
            restored = scratch / name
            if not restored.is_file():
                problem = "missing from the restored copy"
            elif restored.read_bytes() != original:
                problem = "differs from the live data"
            else:
                problem = _usable(name, restored.read_bytes())
            files.append({"name": name, "ok": not problem, "problem": problem})
    finally:
        shutil.rmtree(scratch, ignore_errors=True)       # plain copies of your data must not stay behind
    older = {"files": 0, "readable": 0, "unreadable": []}
    for path in sorted(backups_dir().rglob("*")):
        if not path.is_file() or path.name == ".DS_Store" or backup in path.parents:
            continue
        older["files"] += 1
        try:
            read_bytes(path)
            older["readable"] += 1
        except Exception:  # noqa: BLE001 - VaultError, a damaged file, anything
            older["unreadable"].append(str(path.relative_to(backups_dir())))
    return {"ok": bool(files) and all(f["ok"] for f in files) and not older["unreadable"],
            "backup": backup.name, "files": files, "older": older}


# ── one backup of everything: the data files and your documents ─────────────
def everything() -> list[tuple[Path, str]]:
    """Every file worth keeping, with the name it gets inside a backup:
    the app's data files, your master CV, your own letters, the letters and CVs
    the app wrote, the two rule files, the letter template and the career-site list."""
    from . import config
    found: dict[str, Path] = {}

    def add(path: Path, name: str) -> None:
        if path.is_file() and path.name != ".DS_Store" and ".editing." not in path.name:
            found.setdefault(name, path)

    for path in data_files():
        add(Path(path), Path(path).name)
    for path in (config.CV_INSTRUCTION, config.LETTER_INSTRUCTION, config.LETTER_TEMPLATE, config.DATA_DIR / "companies.json"):
        add(path, path.name)
    for folder, name in ((config.CV_DIR, "cv"), (config.COVER_LETTERS_DIR, "my_letters"),
                         (config.LETTERS_DIR, "cover_letters"), (config.TAILORED_CV_DIR, "tailored_cvs")):
        if folder.is_dir():
            for path in sorted(folder.rglob("*")):
                add(path, f"{name}/{path.relative_to(folder).as_posix()}")
    return [(path, name) for name, path in sorted(found.items())]


def backup_everything() -> dict:
    """Write one encrypted backup folder holding everything (see `everything`).
    Restore it with restore_backup(folder, destination). {folder, files, bytes}"""
    if state() == "locked":
        data_key()                                  # raises with the reason and the way out
    dest = backups_dir() / f"everything_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    files = size = 0
    for path, name in everything():
        plain = read_bytes(path)                    # data files are decrypted first, documents are read as they are
        _backup_copy(dest / name, plain)
        files += 1
        size += len(plain)
    return {"folder": dest, "files": files, "bytes": size}
