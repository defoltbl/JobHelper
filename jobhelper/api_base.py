"""What every part of the window's back end shares: reads that survive locked data, changes of the job list that wait for
no other process, and small text helpers."""
from __future__ import annotations

import functools
import os

from . import store, vault


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


def _holding_jobs(refused=None):
    """A change of the job list made while holding its lock (store.RunLock) from the first read to the last write, so the
    weekly run never starts in between (#72), nor another change from another thread of the window (#96). While another
    process holds it, the call changes nothing and returns `refused` (a value, or a function that makes it); the default
    is the refusal {ok: False, msg: RunLock.BUSY}, or what RunLock says when its lock file cannot be opened."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            try:
                with store.RunLock.holding():
                    return fn(*args, **kwargs)
            except store.JobsBusy as busy:
                if refused is None:
                    return {"ok": False, "msg": str(busy)}
                return refused() if callable(refused) else refused
        return inner
    return wrap


def _stem(name: str) -> str:
    """A stored document name without its extension."""
    return os.path.splitext(os.path.basename(name))[0]

