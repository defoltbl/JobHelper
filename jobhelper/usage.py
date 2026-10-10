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

# In-process accumulator for the current run.
_SESSION: dict[str, Any] = {k: 0 for k in _FIELDS}
_SESSION["calls"] = 0


def _blank() -> dict[str, Any]:
    d = {k: 0 for k in _FIELDS}
    d["calls"] = 0
    return d


def _number(value: Any) -> float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _load() -> dict[str, Any]:
    """The saved counters, always in the shape the rest expects. A file that is damaged, or was written by hand with
    a part missing, must not make every answer from Claude fail when its use is noted."""
    state: Any = None
    if config.USAGE_JSON.exists():
        try:
            state = json.loads(config.USAGE_JSON.read_text(encoding="utf-8"))
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


_LOCK = threading.Lock()        # a search and a question to the assistant can both note a call at the same moment


def _save(state: dict[str, Any]) -> None:
    config.ensure_dirs()
    # written whole or not at all: a half-written file would read as "no usage yet" and the totals would start again
    tmp = config.USAGE_JSON.with_name(f"{config.USAGE_JSON.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, config.USAGE_JSON)


def record(rec: dict[str, Any], tag: str = "general") -> None:
    """Add one model call's usage to the session, per-tag, and lifetime totals."""
    with _LOCK:
        state = _load()
        for bucket in (state["totals"], state["by_tag"].setdefault(tag, _blank()), _SESSION):
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
        _save(state)


_WINDOW_WORDS = (("seven_day", re.compile(r"week|7[- ]?day|seven[- ]day", re.IGNORECASE)),
                 ("five_hour", re.compile(r"session|5[- ]?hour|five[- ]hour", re.IGNORECASE)))
WINDOWS = ("five_hour", "seven_day")


def window_named(message: str) -> str:
    """Which limit Claude's refusal talks about: 'five_hour' ("session limit"), 'seven_day' ("weekly limit") or ''."""
    for name, words in _WINDOW_WORDS:
        if words.search(message or ""):
            return name
    return ""


def note_limit(until: float, message: str = "") -> None:
    """Remember that Claude refused a call because a limit was hit, until `until` (epoch)."""
    with _LOCK:
        state = _load()
        state["limit_block"] = {"until": float(until), "message": message, "window": window_named(message),
                                "at": datetime.now().isoformat(timespec="seconds")}
        _save(state)


def windows(now: float | None = None) -> dict[str, dict[str, Any]]:
    """Each limit as it stands now: {window: {used (0..1 or None = never reported), resets_at (epoch, 0 = unknown)}}.

    The numbers Claude last reported, corrected by what is known since: a window
    whose reset time has passed is empty again, and a window Claude refused a call
    for is full until the reset it named, whatever the older numbers say."""
    import time
    now = time.time() if now is None else now
    state = _load()
    info = (state.get("last_rate_limit") or {}).get("info")
    reported = info.get("unifiedWindows") if isinstance(info, dict) else None
    out: dict[str, dict[str, Any]] = {}
    for name in WINDOWS:
        w = (reported or {}).get(name)
        used, resets = (w.get("utilization"), float(w.get("resetsAt") or 0)) if isinstance(w, dict) else (None, 0.0)
        if not isinstance(used, (int, float)) or isinstance(used, bool):
            used, resets = None, 0.0
        elif resets and resets <= now:
            used, resets = 0.0, 0.0
        out[name] = {"used": None if used is None else float(used), "resets_at": resets}
    block = state.get("limit_block") or {}
    until = float(_number(block.get("until")))
    if until > now:
        name = block.get("window") if block.get("window") in WINDOWS else ""
        if not name:            # the refusal did not say which: the fuller one, the short window when neither is known
            name = max(WINDOWS, key=lambda k: out[k]["used"] or 0.0) if any(out[k]["used"] for k in WINDOWS) else "five_hour"
        out[name] = {"used": 1.0, "resets_at": until}
    return out


def limit_status(threshold: float = 0.99, now: float | None = None) -> dict[str, Any]:
    """Is the subscription limit used up right now?

    {blocked, window ('five_hour' | 'seven_day' | ''), used (0..1), resets_at (epoch, 0 = unknown)}.
    Blocked when Claude said so (until the reset it named) or when the last
    reported utilisation of a window is at/above `threshold` and that window
    has not reset yet. A window whose reset time has passed counts as free.
    When both are used up, the one that frees later is the one to wait for."""
    best = {"blocked": False, "window": "", "used": 0.0, "resets_at": 0.0}
    full = []
    for name, w in windows(now).items():
        used = w["used"] or 0.0
        if used >= threshold:
            full.append((w["resets_at"], name, used))
        if used > best["used"]:
            best.update(used=used, window=name, resets_at=w["resets_at"])
    if full:
        resets, name, used = max(full)
        best.update(blocked=True, window=name, used=used, resets_at=resets)
    return best


def total_cost() -> float:
    """What every call so far would have cost through the paid API (a run notes the difference)."""
    try:
        return float(_load().get("totals", {}).get("cost_usd", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def session() -> dict[str, Any]:
    return dict(_SESSION)


def reset() -> None:
    _save({"totals": _blank(), "by_tag": {}, "last_rate_limit": None, "runs": []})
    for k in _SESSION:
        _SESSION[k] = 0


def _fmt(d: dict[str, Any]) -> str:
    return (f"{d['calls']} calls | in {d['input_tokens']:,} + out {d['output_tokens']:,} tok "
            f"| cache read {d.get('cache_read_input_tokens', 0):,} "
            f"| ~${d['cost_usd']:.4f} (API-equiv.)")


def format_report(show_session: bool = True) -> str:
    state = _load()
    lines = ["── Claude usage ──"]
    if show_session and _SESSION["calls"]:
        lines.append(f"This run:  {_fmt(_SESSION)}")
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
        lines.append("Subscription usage: no snapshot yet — run the app once, or "
                     "check /usage in the Claude Code terminal.")
    return "\n".join(lines)
