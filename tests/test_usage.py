from jobhelper import usage


def test_record_accumulates(isolate_data):
    usage.reset()
    usage.record({"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.01}, tag="agent1_cv")
    usage.record({"input_tokens": 50, "output_tokens": 10, "cost_usd": 0.005}, tag="agent3_letters")

    sess = usage.session()
    assert sess["calls"] == 2
    assert sess["input_tokens"] == 150
    assert sess["output_tokens"] == 30
    assert abs(sess["cost_usd"] - 0.015) < 1e-9


def test_by_tag_breakdown(isolate_data):
    usage.reset()
    usage.record({"input_tokens": 10, "output_tokens": 2, "cost_usd": 0.001}, tag="agent3_letters")
    usage.record({"input_tokens": 10, "output_tokens": 2, "cost_usd": 0.001}, tag="agent3_letters")
    report = usage.format_report()
    assert "agent3_letters" in report
    assert "2 calls" in report


def test_reset_clears(isolate_data):
    usage.record({"input_tokens": 10, "output_tokens": 2, "cost_usd": 0.001})
    usage.reset()
    assert usage.session()["calls"] == 0
    assert "0 calls" in usage.format_report(show_session=False)


def test_rate_limit_snapshot_captured(isolate_data):
    usage.reset()
    usage.record({"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0,
                  "rate_limit_info": {"status": "allowed", "unifiedWindows": {
                      "five_hour": {"utilization": 0.68, "resetsAt": 1789311600},
                      "seven_day": {"utilization": 0.07, "resetsAt": 1789660800}}}},
                 tag="general")
    report = usage.format_report()
    assert "Subscription usage" in report
    assert "68% used" in report
    assert "32% left" in report


def test_format_rate_limit_handles_plain_dict():
    lines = usage._format_rate_limit({"status": "allowed"})
    assert any("status=allowed" in ln for ln in lines)


# ── found by reading usage.py line by line (10 October 2026) ────────────────
def test_a_damaged_usage_file_does_not_cost_an_answer(isolate_data, monkeypatch):
    """Every answer from Claude is noted in the usage counters after it arrives. A counters file with a part missing made
    that note fail, and with it the call: the answer was there and was thrown away."""
    import json as _json
    from jobhelper import config, llm, usage
    config.ensure_dirs()
    for damaged in ("{}", "[1, 2]", '{"totals": "many", "by_tag": [], "runs": "none", "limit_block": 5}', "not json",
                    '{"totals": {"calls": "three", "cost_usd": null}, "by_tag": {"agent3_letters": 7}, "runs": [1, {"tag": "x"}]}'):
        config.USAGE_JSON.write_text(damaged, encoding="utf-8")
        usage.record({"input_tokens": 10, "output_tokens": 5, "cost_usd": "a lot"}, tag="agent3_letters")
        state = _json.loads(config.USAGE_JSON.read_text(encoding="utf-8"))
        assert state["totals"]["calls"] == 1 and state["by_tag"]["agent3_letters"]["input_tokens"] == 10 and state["totals"]["cost_usd"] == 0, damaged
        assert usage.limit_status()["blocked"] is False and isinstance(usage.format_report(), str) and usage.total_cost() == 0.0

    async def answer(prompt, system, model):
        return "the answer", {"input_tokens": 1}
    monkeypatch.setattr(llm, "_ask_async", answer)
    monkeypatch.setattr(usage, "record", lambda rec, tag="general": (_ for _ in ()).throw(OSError("disk full")))
    assert llm.ask("a question") == "the answer", "keeping count failed; the answer is still given"


def test_two_threads_noting_calls_at_once_lose_none(isolate_data):
    import threading as _threading
    from jobhelper import config, usage
    config.ensure_dirs()
    usage.reset()
    workers = [_threading.Thread(target=lambda: [usage.record({"input_tokens": 1}, tag="t") for _ in range(25)]) for _ in range(4)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert usage.totals()["calls"] == 100 and usage.by_tag()["t"]["input_tokens"] == 100
