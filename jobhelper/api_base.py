"""What every part of the window's back end shares: reads that survive locked data, and small text helpers."""
from __future__ import annotations

import functools
import os

from . import vault


def _guarded(default):
    """A read that returns `default` instead of raising while the data is locked
    (encrypted with a key that is not in the Keychain)."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except vault.VaultError:
                return default() if callable(default) else default
        return inner
    return wrap


def _stem(name: str) -> str:
    """A stored document name without its extension."""
    return os.path.splitext(os.path.basename(name))[0]


def textfmt_clean(text) -> str:
    """Pasted text with its line ends tidied (the words are left as they are)."""
    lines = [ln.rstrip() for ln in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out = "\n".join(lines).strip()
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out
