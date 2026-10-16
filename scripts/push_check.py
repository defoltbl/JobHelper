#!/usr/bin/env python3
"""Check what a push would publish, before it leaves this Mac.

    python scripts/push_check.py                      # check the whole history of this repository
    python scripts/push_check.py --repo PATH          # check another repository (a bare copy too)
    python scripts/push_check.py --install-hook       # run the check by itself before every git push

The check looks at every commit that a push would send, and at every file in those commits
(also inside Word files and PDFs). It stops the push when it finds:

- a personal detail of the owner: the name, an email address, a phone number or a profile
  address. They are read at run time from the master CV and the mailbox settings in the data
  home (and from push_check_words.txt there, one word per line), so the list itself is never
  in the repository. Allowed: the README's "## Author" section and the copyright line of LICENSE
  ("Copyright (c) …" or "Required Notice: Copyright …");
- a secret: an API key, a token, a password, a private key;
- an author or committer email that is not a GitHub noreply address;
- an assistant credit line in a commit message;
- the data folder or a .env file.

What it reports names the kind and the place, never the private word itself.
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZERO = "0" * 40
PROJECT = "JobHelper"        # the repository's own address github.com/<owner>/JobHelper is public anyway (badges need it)
NOREPLY = "@users.noreply.github.com"

SECRETS = {
    "an Anthropic API key": r"sk-ant-[A-Za-z0-9_\-]{10,}",
    "an API key (sk-…)": r"\bsk-[A-Za-z0-9]{20,}",
    "a GitHub token": r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}",
    "an AWS key": r"\bAKIA[0-9A-Z]{16}\b",
    "a Slack token": r"\bxox[baprs]-[A-Za-z0-9-]{10,}",
    "a Google API key": r"\bAIza[0-9A-Za-z_\-]{30,}",
    "a private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "a web token (JWT)": r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
    # also JOOBLE_API_KEY=…, ADZUNA_APP_KEY=…: the secret word may end a longer setting name
    "a password or key in a setting": r"(?i:\b\w*(?:password|passwd|secret|api_key|apikey|app_key|app_id|token))\s*[=:]\s*[\"']?(?P<value>[A-Za-z0-9/+_\-]{16,})",
}
CREDIT = re.compile(r"(?im)^\s*(co-authored-by:|.*generated with \[?claude code)")
SKIP = (".png", ".jpg", ".icns", ".wav", ".lock", ".ico")


@dataclass(frozen=True)
class Finding:
    """One thing that must not be published: what kind, and where (never the private word itself)."""
    kind: str
    where: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.where}"


@dataclass
class PrivateWords:
    """The owner's details to look for, read from their own data (never stored in the repository)."""
    words: list[str] = field(default_factory=list)

    @classmethod
    def from_data_home(cls) -> "PrivateWords":
        sys.path.insert(0, str(ROOT))
        from jobhelper import api_core, config
        text = ""
        try:
            text = api_core.CvSource().text() or ""
        except Exception:  # noqa: BLE001 - without a CV, only the settings and the word list are used
            pass
        words: set[str] = set()
        first = next((line for line in text.splitlines() if line.strip()), "")
        words |= {w for w in re.findall(r"[^\W\d_]{3,}", first)}                    # the name on the CV
        words |= set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text))
        for phone in re.findall(r"\+?\d[\d \-()]{8,}\d", text):
            digits = re.sub(r"\D", "", phone)
            if len(digits) >= 9:
                words |= {phone.strip(), digits, digits[-9:]}
        words |= {u.rstrip("/.,)") for u in re.findall(r"(?:linkedin\.com/in/|github\.com/)[\w\-./]+", text)}
        words |= {str(config.IMAP_USER or ""), str(config.IMAP_USER_2 or "")}
        extra = config.HOME.library / "push_check_words.txt"
        if extra.is_file():
            words |= {line.strip() for line in extra.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")}
        return cls(sorted(w for w in words if len(w) >= 3))


class PushCheck:
    """Everything a push would publish, checked against the rules above."""

    def __init__(self, repo: Path, private: PrivateWords) -> None:
        self._repo = Path(repo)
        self._words = [(w, w.lower()) for w in private.words]
        self._secrets = {kind: re.compile(rx) for kind, rx in SECRETS.items()}

    def _git(self, *args: str, binary: bool = False):
        done = subprocess.run(["git", "-C", str(self._repo), *args], capture_output=True)
        if done.returncode:
            raise RuntimeError(done.stderr.decode("utf-8", "ignore").strip() or f"git {' '.join(args)} failed")
        return done.stdout if binary else done.stdout.decode("utf-8", "ignore")

    # ── what a push sends ────────────────────────────────────────────────────
    def commits(self, ranges: list[tuple[str, str]] | None = None) -> list[str]:
        """The commits to check: for each (local, remote) pair those the remote does not have; without pairs, all."""
        if not ranges:
            return self._git("rev-list", "--all").split()
        out: list[str] = []
        for local, remote in ranges:
            if local == ZERO:                               # a branch is deleted: nothing is sent
                continue
            spec = [local] if remote == ZERO else [local, f"^{remote}"]
            out += self._git("rev-list", *spec).split()
        return list(dict.fromkeys(out))

    # ── the checks ───────────────────────────────────────────────────────────
    def check_commit(self, sha: str) -> list[Finding]:
        found = []
        author, committer, message = self._git("show", "-s", "--format=%ae%x00%ce%x00%B", sha).split("\x00", 2)
        short = sha[:9]
        for who, email in (("author", author), ("committer", committer)):
            if not email.strip().endswith(NOREPLY):
                found.append(Finding(f"the {who} email is not a GitHub noreply address", f"commit {short}"))
        if CREDIT.search(message):
            found.append(Finding("an assistant credit line in the message", f"commit {short}"))
        found += [Finding("a personal detail in the message", f"commit {short}") for _w, low in self._words if low in message.lower()][:1]
        return found

    def check_file(self, path: str, data: bytes) -> list[Finding]:
        if path == ".env" or path.endswith("/.env") or path.startswith("data/"):
            return [Finding("a private file (the data folder or .env)", path)]
        if path.endswith(SKIP):
            return []
        text = self._text_of(path, data)
        if text is None:
            return []
        found = []
        for kind, rx in self._secrets.items():
            if any(self._random(m) for m in rx.finditer(text)):
                found.append(Finding(kind, path))
        lines = text.splitlines()
        allowed = self._allowed_lines(path, lines)
        for number, line in enumerate(lines, 1):
            if number in allowed:
                continue
            low = self._without_own_address(line.lower())
            if any(w in low for _w, w in self._words):
                found.append(Finding("a personal detail", f"{path}:{number}" if not path.endswith((".docx", ".pdf")) else path))
                if path.endswith((".docx", ".pdf")):
                    break
        return found

    def _without_own_address(self, low: str) -> str:
        """The line without this repository's own GitHub address (the owner's name in it is public with the repository)."""
        for word, w in self._words:
            if w.startswith("github.com/"):
                low = low.replace(f"{w}/{PROJECT.lower()}", "")
        return low

    @staticmethod
    def _random(match: re.Match) -> bool:
        """A real secret is random: a test's made-up value ("abcdabcdabcdabcd") has few different characters."""
        value = match.groupdict().get("value")
        return value is None or len(set(value)) >= 10

    @staticmethod
    def _allowed_lines(path: str, lines: list[str]) -> set[int]:
        """Where the owner may be named: README's Author section (the last one), and LICENSE's copyright line."""
        if path == "README.md" and "## Author" in lines:
            return set(range(lines.index("## Author") + 1, len(lines) + 1))
        if path == "LICENSE":
            return {n for n, line in enumerate(lines, 1) if line.startswith(("Copyright (c)", "Required Notice: Copyright"))}
        return set()

    @staticmethod
    def _text_of(path: str, data: bytes) -> str | None:
        try:
            if path.endswith(".docx"):
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    return "\n".join(z.read(p).decode("utf-8", "ignore") for p in z.namelist() if p.endswith((".xml", ".rels")))
            if path.endswith(".pdf"):
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(data))
                meta = " ".join(str(v) for v in (reader.metadata or {}).values())
                return meta + "\n" + "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:  # noqa: BLE001 - a file that cannot be opened is not text
            return None
        return data.decode("utf-8", "ignore")

    def run(self, ranges: list[tuple[str, str]] | None = None) -> list[Finding]:
        commits = self.commits(ranges)
        findings: list[Finding] = []
        for sha in commits:
            findings += self.check_commit(sha)
        if commits:
            objects = self._git("rev-list", "--objects", *commits, "--not", *self._remote_tips(ranges)) if ranges else \
                self._git("rev-list", "--objects", "--all")
            paths: dict[str, str] = {}
            for line in objects.splitlines():
                sha, _, path = line.partition(" ")
                if path and sha not in paths:
                    paths[sha] = path
            for sha, data in self._blobs(list(paths)):
                findings += self.check_file(paths[sha], data)
        return list(dict.fromkeys(findings))

    def _blobs(self, shas: list[str]):
        """(sha, content) of every file among `shas`, read through one git process (one per object took minutes)."""
        if not shas:
            return
        done = subprocess.run(["git", "-C", str(self._repo), "cat-file", "--batch"], input="\n".join(shas).encode() + b"\n",
                              capture_output=True)
        out, at = done.stdout, 0
        while at < len(out):
            end = out.index(b"\n", at)
            header = out[at:end].split()
            at = end + 1
            if len(header) < 3:                              # "<sha> missing"
                continue
            size = int(header[2])
            if header[1] == b"blob":
                yield header[0].decode(), out[at:at + size]
            at += size + 1

    @staticmethod
    def _remote_tips(ranges: list[tuple[str, str]] | None) -> list[str]:
        return [remote for _local, remote in (ranges or []) if remote != ZERO]


def install_hook(repo: Path) -> Path:
    """Write the pre-push hook of a repository (a working one or a bare copy): this script, with this Python."""
    git_dir = Path(subprocess.run(["git", "-C", str(repo), "rev-parse", "--absolute-git-dir"],
                                  capture_output=True, text=True, check=True).stdout.strip())
    hook = git_dir / "hooks" / "pre-push"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(f'#!/bin/sh\n# JobHelper: check what this push would publish (scripts/push_check.py)\n'
                    f'exec "{sys.executable}" "{Path(__file__).resolve()}" --hook --repo "{git_dir}"\n', encoding="utf-8")
    hook.chmod(0o755)
    return hook


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check what a git push would publish.")
    parser.add_argument("--repo", default=str(ROOT), help="the repository to check (default: this project)")
    parser.add_argument("--hook", action="store_true", help="run as git's pre-push hook (reads the refs from stdin)")
    parser.add_argument("--install-hook", action="store_true", help="make git run this check before every push")
    args = parser.parse_args(argv)
    repo = Path(args.repo)
    if args.install_hook:
        print(f"Installed: {install_hook(repo)}")
        return 0
    ranges = None
    if args.hook:                                           # git gives: <local ref> <local sha> <remote ref> <remote sha>
        ranges = [(parts[1], parts[3]) for parts in (line.split() for line in sys.stdin) if len(parts) == 4]
    private = PrivateWords.from_data_home()
    if not private.words:
        print("Push check: no personal details could be read (no CV in the data home); only secrets and emails are checked.")
    findings = PushCheck(repo, private).run(ranges)
    if not findings:
        print("Push check: nothing private found. The push may go ahead.")
        return 0
    print(f"Push check: {len(findings)} problems. Nothing was pushed.")
    kinds: dict[str, list[Finding]] = {}
    for finding in findings:
        kinds.setdefault(finding.kind, []).append(finding)
    for kind, items in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
        places = ", ".join(f.where for f in items[:6]) + (f", … and {len(items) - 6} more" if len(items) > 6 else "")
        print(f"  - {kind} ({len(items)}): {places}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
