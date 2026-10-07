"""requirements.lock must pin every package by exact version and SHA-256."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = re.compile(r"^([A-Za-z0-9_.\-]+)==([^\s\\]+) \\\n    --hash=sha256:([0-9a-f]{64})$", re.M)


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _lock() -> dict[str, tuple[str, str]]:
    text = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    return {_norm(name): (version, digest) for name, version, digest in ENTRY.findall(text)}


def test_every_line_is_pinned_with_a_hash():
    text = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    body = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    entries = ENTRY.findall(text)
    assert entries, "requirements.lock is empty"
    assert len(body) == 2 * len(entries), "a line is not a 'name==version' + '--hash=sha256:' pair"
    assert not any(">=" in ln or "~=" in ln for ln in body)


def test_every_direct_requirement_is_locked():
    wanted = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            wanted.append(_norm(re.split(r"[<>=!~\[ ]", line, maxsplit=1)[0]))
    missing = [name for name in wanted if name not in _lock()]
    assert not missing, f"run scripts/lock_requirements.py - not locked: {missing}"


def test_the_encryption_library_is_locked():
    assert "cryptography" in _lock()
