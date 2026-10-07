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
