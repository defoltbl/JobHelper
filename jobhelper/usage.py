"""Claude usage tracker.

Every model call reports token counts, an API-equivalent cost (total_cost_usd),
and occasionally a rate-limit snapshot. We accumulate these so you can see how
much you've used. Persisted to data/usage.json.

Important: your Claude *subscription's* exact remaining quota (the Pro/Max
5-hour and weekly limits) is not exposed as a number by the API. This tracker
shows tokens used and the API-equivalent cost (a good proxy for "how much"),
plus the latest rate-limit snapshot the SDK reports when it does. For the
authoritative subscription limits, run `/usage` inside the Claude Code terminal.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from typing import Any

from . import config


def _format_rate_limit(info: Any) -> list[str]:
    """Render subscription-window utilization if the SDK provided it."""
    if not isinstance(info, dict):
        return [f"Rate-limit snapshot: {info}"]
    windows = info.get("unifiedWindows") or {}
    if not windows:
        status = info.get("status", "?")
        return [f"Rate-limit snapshot: status={status}"]
    lines = ["Subscription usage (live from Claude):"]
    labels = {"five_hour": "5-hour window", "seven_day": "7-day window"}
    for key in ("five_hour", "seven_day"):
        w = windows.get(key)
        if not w:
            continue
        util = w.get("utilization")
        pct = f"{util * 100:.0f}% used" if isinstance(util, (int, float)) else "usage n/a"
        resets = w.get("resetsAt")
        when = ""
        if isinstance(resets, (int, float)):
            when = f"  (resets {datetime.fromtimestamp(resets):%Y-%m-%d %H:%M})"
        left = ""
        if isinstance(util, (int, float)):
            left = f"  →  ~{max(0, (1 - util)) * 100:.0f}% left"
        lines.append(f"   {labels[key]:<14} {pct}{left}{when}")
    return lines

_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
           "cache_creation_input_tokens", "cost_usd")
_WINDOW_WORDS = (("seven_day", re.compile(r"week|7[- ]?day|seven[- ]day", re.IGNORECASE)),
                 ("five_hour", re.compile(r"session|5[- ]?hour|five[- ]hour", re.IGNORECASE)))
WINDOWS = ("five_hour", "seven_day")
STALE_AFTER = 3600      # seconds: Claude reports the limits only with an answer, so an older number is shown with its time
LOW_LEFT = 20           # per cent left or less: the card says when the window resets, and its bar turns red
REFRESH_AFTER = 600     # seconds: while the window is open, a reading older than this is asked for again (one small question)
FULL = 0.99             # used this much or more: the window is used up


def _blank() -> dict[str, Any]:
    d = {k: 0 for k in _FIELDS}
    d["calls"] = 0
    return d


def _number(value: Any) -> float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _fmt(d: dict[str, Any]) -> str:
    return (f"{d['calls']} calls | in {d['input_tokens']:,} + out {d['output_tokens']:,} tok "
            f"| cache read {d.get('cache_read_input_tokens', 0):,} "
            f"| ~${d['cost_usd']:.4f} (API-equiv.)")


def _moment(text: Any) -> float:
    """The epoch of a saved local time ("2026-10-18T09:22:53"), 0 when it is not one."""
    try:
        return datetime.fromisoformat(str(text)).timestamp()
    except ValueError:
        return 0.0


def _window(used: float | None, resets_at: float, as_of: float, now: float, reset_passed: float = 0.0) -> dict[str, Any]:
    return {"used": used, "resets_at": resets_at, "as_of": as_of,
            "stale": used is not None and as_of > 0 and now - as_of > STALE_AFTER, "reset_passed": reset_passed,
            "held_until": 0.0}


def window_named(message: str) -> str:
    """Which limit Claude's refusal talks about: 'five_hour' ("session limit"), 'seven_day' ("weekly limit") or ''."""
    for name, words in _WINDOW_WORDS:
        if words.search(message or ""):
            return name
    return ""


class UsageLog:
    """What the model calls used: the saved counters in usage.json (lifetime, per tag, the last calls, the
    last limit Claude reported or refused for) and the counters of this run, which are never saved."""

    def __init__(self) -> None:
        self._lock = threading.Lock()   # a search and a question to the assistant can both note a call at the same moment
        self._session = _blank()
        self._last_try = 0.0                # when this run of the app last asked Claude for the limits (never saved)

    @property
    def path(self):
        return config.USAGE_JSON

    def _read(self) -> dict[str, Any]:
        """The saved counters, always in the shape the rest expects. A file that is damaged, or was written by hand
        with a part missing, must not make every answer from Claude fail when its use is noted."""
        state: Any = None
        if self.path.exists():
            try:
                state = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                state = None
        if not isinstance(state, dict):
            state = {}
        totals = state.get("totals") if isinstance(state.get("totals"), dict) else {}
        state["totals"] = {**_blank(), **{k: _number(v) for k, v in totals.items()}}
        tags = state.get("by_tag") if isinstance(state.get("by_tag"), dict) else {}
        state["by_tag"] = {str(tag): {**_blank(), **{k: _number(v) for k, v in d.items()}} for tag, d in tags.items() if isinstance(d, dict)}
        state["runs"] = [r for r in state["runs"] if isinstance(r, dict)] if isinstance(state.get("runs"), list) else []
        state.setdefault("last_rate_limit", None)
        if not isinstance(state.get("last_rate_limit"), dict):
            state["last_rate_limit"] = None
        if "limit_block" in state and not isinstance(state["limit_block"], dict):
            state.pop("limit_block")
        return state

    def _write(self, state: dict[str, Any]) -> None:
        config.ensure_dirs()
        # written whole or not at all: a half-written file would read as "no usage yet" and the totals would start again
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def record(self, rec: dict[str, Any], tag: str = "general") -> None:
        """Add one model call's usage to the session, per-tag, and lifetime totals."""
        with self._lock:
            state = self._read()
            for bucket in (state["totals"], state["by_tag"].setdefault(tag, _blank()), self._session):
                bucket["calls"] += 1
                for f in _FIELDS:
                    bucket[f] += _number(rec.get(f))
            if rec.get("rate_limit_info"):
                state["last_rate_limit"] = {"at": datetime.now().isoformat(timespec="seconds"),
                                            "info": rec["rate_limit_info"]}
            state["runs"].append({
                "at": datetime.now().isoformat(timespec="seconds"), "tag": tag,
                "input_tokens": _number(rec.get("input_tokens")), "output_tokens": _number(rec.get("output_tokens")),
                "cost_usd": _number(rec.get("cost_usd")),
            })
            state["runs"] = state["runs"][-500:]  # keep the log bounded
            state.pop("limit_block", None)        # Claude answered, so an earlier refusal is over
            self._write(state)

    def note_limit(self, until: float, message: str = "") -> None:
        """Remember that Claude refused a call because a limit was hit, until `until` (epoch)."""
        with self._lock:
            state = self._read()
            state["limit_block"] = {"until": float(until), "message": message, "window": window_named(message),
                                    "at": datetime.now().isoformat(timespec="seconds")}
            self._write(state)

    def windows(self, now: float | None = None) -> dict[str, dict[str, Any]]:
        """Each limit as it stands now: {window: {used (0..1 or None = never reported), resets_at (epoch, 0 = unknown),
        as_of (epoch the number was true, 0 = unknown), stale (it is older than STALE_AFTER), reset_passed (epoch of a
        reset since the last reading, 0 = none), held_until (epoch the used-up weekly window frees the 5-hour one too,
        0 = it does not hold it)}}.

        The numbers Claude last reported, corrected by what is known since: a window whose reset time has passed is
        unknown again (Claude Code and the app share the subscription, so it need not be empty), and a window Claude
        refused a call for is full until the reset it named, whatever the older numbers say. Each window keeps its own
        figure and reset time; while the weekly window is used up, nothing can be used before it resets, so the 5-hour
        window also says when that is (when it would itself free earlier)."""
        import time
        now = time.time() if now is None else now
        state = self._read()
        info = (state.get("last_rate_limit") or {}).get("info")
        reported = info.get("unifiedWindows") if isinstance(info, dict) else None
        read_at = _moment((state.get("last_rate_limit") or {}).get("at"))
        out: dict[str, dict[str, Any]] = {}
        for name in WINDOWS:
            w = (reported or {}).get(name)
            used, resets, as_of = (w.get("utilization"), float(w.get("resetsAt") or 0), read_at) if isinstance(w, dict) else (None, 0.0, 0.0)
            passed = 0.0
            if not isinstance(used, (int, float)) or isinstance(used, bool):
                used, resets, as_of = None, 0.0, 0.0
            elif resets and resets <= now:
                used, resets, as_of, passed = None, 0.0, 0.0, resets      # reset since the reading: what is used now is not known
            out[name] = _window(None if used is None else float(used), resets, as_of, now, passed)
        block = state.get("limit_block") or {}
        until = float(_number(block.get("until")))
        if until > now:
            name = block.get("window") if block.get("window") in WINDOWS else ""
            if not name:            # the refusal did not say which: the fuller one, the short window when neither is known
                name = max(WINDOWS, key=lambda k: out[k]["used"] or 0.0) if any(out[k]["used"] for k in WINDOWS) else "five_hour"
            out[name] = _window(1.0, until, now, now)
        week, short = out["seven_day"], out["five_hour"]
        if (week["used"] or 0.0) >= FULL and week["resets_at"] > now and short["resets_at"] < week["resets_at"]:
            short["held_until"] = week["resets_at"]
        return out

    def note_try(self, now: float | None = None) -> None:
        """Remember that the app asked Claude for the limits, whatever came back: a question that brought no reading
        (no answer, no limits in it, not signed in) is not asked again before REFRESH_AFTER. Kept for this run only, so
        it never writes the file (a damaged usage.json must not be written over)."""
        import time
        self._last_try = time.time() if now is None else now

    def refresh_due(self, now: float | None = None, windows: dict[str, dict[str, Any]] | None = None) -> bool:
        """Is one small question to Claude worth it now? Yes when the last reading or question is older than
        REFRESH_AFTER, or a window reset since then; no while Claude refuses calls, because it tells nothing new until
        the reset it named. `windows` saves reading the file again when the caller has them for the same moment."""
        import time
        now = time.time() if now is None else now
        state = self._read()
        if float(_number((state.get("limit_block") or {}).get("until"))) > now:
            return False
        def known(moment: float) -> float:        # a time ahead of the clock (set back since) is not trusted
            return moment if moment <= now else 0.0
        tried = known(self._last_try)
        last = max(known(_moment((state.get("last_rate_limit") or {}).get("at"))), tried)
        windows = self.windows(now) if windows is None else windows
        return now - last > REFRESH_AFTER or any(w["reset_passed"] > tried for w in windows.values())

    def limit_status(self, threshold: float = FULL, now: float | None = None) -> dict[str, Any]:
        """Is the subscription limit used up right now?

        {blocked, window ('five_hour' | 'seven_day' | ''), used (0..1), resets_at (epoch, 0 = unknown)}.
        Blocked when Claude said so (until the reset it named) or when the last
        reported utilisation of a window is at/above `threshold` and that window
        has not reset yet. A window whose reset time has passed counts as free.
        When both are used up, the one that frees later is the one to wait for."""
        best = {"blocked": False, "window": "", "used": 0.0, "resets_at": 0.0}
        full = []
        for name, w in self.windows(now).items():
            used = w["used"] or 0.0
            if used >= threshold:
                full.append((w["resets_at"], name, used))
            if used > best["used"]:
                best.update(used=used, window=name, resets_at=w["resets_at"])
        if full:
            resets, name, used = max(full)
            best.update(blocked=True, window=name, used=used, resets_at=resets)
        return best

    def totals(self) -> dict[str, Any]:
        """Every call so far, added up: {calls, input_tokens, …, cost_usd}."""
        return self._read()["totals"]

    def by_tag(self) -> dict[str, dict[str, Any]]:
        """The same sums for each kind of work: {tag: {calls, …, cost_usd}}."""
        return self._read()["by_tag"]

    def total_cost(self) -> float:
        """What every call so far would have cost through the paid API (a run notes the difference)."""
        return float(self.totals()["cost_usd"])

    def session(self) -> dict[str, Any]:
        return dict(self._session)

    def reset(self) -> None:
        with self._lock:
            self._write({"totals": _blank(), "by_tag": {}, "last_rate_limit": None, "runs": []})
            self._session = _blank()

    def format_report(self, show_session: bool = True) -> str:
        state = self._read()
        lines = ["── Claude usage ──"]
        if show_session and self._session["calls"]:
            lines.append(f"This run:  {_fmt(self._session)}")
        lines.append(f"Lifetime:  {_fmt(state['totals'])}")
        if state["by_tag"]:
            lines.append("By agent:")
            for tag, d in sorted(state["by_tag"].items()):
                lines.append(f"   {tag:<16} {_fmt(d)}")
        rl = state.get("last_rate_limit")
        if rl:
            lines.extend(_format_rate_limit(rl.get("info")))
            lines.append(f"   (as of {rl['at']})")
        else:
            lines.append("Subscription usage: no snapshot yet – run the app once, or "
                         "check /usage in the Claude Code terminal.")
        return "\n".join(lines)


LOG = UsageLog()


def record(rec: dict[str, Any], tag: str = "general") -> None:
    LOG.record(rec, tag)


def note_limit(until: float, message: str = "") -> None:
    LOG.note_limit(until, message)


def windows(now: float | None = None) -> dict[str, dict[str, Any]]:
    return LOG.windows(now)


def limit_status(threshold: float = FULL, now: float | None = None) -> dict[str, Any]:
    return LOG.limit_status(threshold, now)


def note_try(now: float | None = None) -> None:
    LOG.note_try(now)


def refresh_due(now: float | None = None, windows: dict[str, dict[str, Any]] | None = None) -> bool:
    return LOG.refresh_due(now, windows)


def totals() -> dict[str, Any]:
    return LOG.totals()


def by_tag() -> dict[str, dict[str, Any]]:
    return LOG.by_tag()


def total_cost() -> float:
    return LOG.total_cost()


def session() -> dict[str, Any]:
    return LOG.session()


def reset() -> None:
    LOG.reset()


def format_report(show_session: bool = True) -> str:
    return LOG.format_report(show_session)
