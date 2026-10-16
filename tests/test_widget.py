"""The macOS widget: the summary the app writes for it, and the widget's promise to read only that."""
import json
import os
import plistlib
import re
import stat
import sys
from datetime import datetime
from pathlib import Path

import pytest

from jobhelper import api_system, config, schedule, store, trouble, ui_api, weekly, widget_feed

ROOT = Path(__file__).resolve().parent.parent
SWIFT = (ROOT / "widget" / "JobHelperWidget.swift").read_text(encoding="utf-8")


class FakeApp:
    """What the feed asks the back end, with invented numbers."""

    def __init__(self, **over):
        self.values = {"counts": {"leads": 9, "applications": 6, "responses": 5, "followups": 1, "duplicates": 2},
                       "upcoming": [{"id": "a", "kind": "interview", "company": "Brightline Works", "title": "Junior Backend Developer",
                                     "date": "2026-10-18", "time": "11:30", "days": 2, "label": "in 2 days", "note": "bring ID"}],
                       "last_run": {"when": "16 Oct 09:12", "found": 9, "letters": 5, "cost": 0.42, "scan_detail": "x"},
                       "usage_info": {"five_hour_used": 34, "seven_day_used": 12, "calls": 3}}
        self.values.update(over)

    def counts(self): return self.values["counts"]
    def upcoming(self, limit=0): return self.values["upcoming"][:limit or None]
    def last_run(self): return self.values["last_run"]
    def usage_info(self): return self.values["usage_info"]


@pytest.fixture
def jobs(isolate_data, monkeypatch):
    config.ensure_dirs()
    store.save_jobs([store.new_job(id="i", title="Dev", company="Acme", status="interview"),
                     store.new_job(id="o", title="QA", company="Beta", status="offer"),
                     store.new_job(id="w", title="Ops", company="Gamma", status="waiting")])
    monkeypatch.setattr(schedule, "read_schedule", lambda: {"enabled": True, "label": "Mon 09:00"})
    return isolate_data


def test_the_summary_holds_the_numbers_and_dates_and_nothing_private(jobs):
    s = widget_feed.WidgetFeed(FakeApp(), jobs / "w").snapshot(now=datetime(2026, 10, 16, 10, 0))
    assert s["updated"] == "2026-10-16T10:00:00" and s["version"] == 1
    assert s["counts"] == {"leads": 9, "applications": 6, "interviews": 1, "offers": 1, "followups": 1, "responses": 5}
    assert s["next"] == [{"kind": "interview", "company": "Brightline Works", "title": "Junior Backend Developer",
                          "date": "2026-10-18", "time": "11:30"}]                                 # no notes, no id
    assert s["last_run"] == {"when": "16 Oct 09:12", "found": 9, "letters": 5}                   # no costs or mail detail
    assert s["usage"] == {"five_hour_left": 66, "week_left": 88} and s["weekly"] == "Mon 09:00"
    assert set(s) == {"version", "updated", "counts", "next", "last_run", "usage", "weekly"}


def test_unknown_usage_and_no_run_yet(jobs):
    app = FakeApp(usage_info={"five_hour_used": None, "seven_day_used": None}, last_run={}, upcoming=[])
    s = widget_feed.WidgetFeed(app, jobs / "w").snapshot()
    assert s["usage"] == {"five_hour_left": None, "week_left": None} and s["last_run"] is None and s["next"] == []


def test_the_file_is_written_whole_and_readable_by_you_only(jobs):
    feed = widget_feed.WidgetFeed(FakeApp(), jobs / "widget")
    path = feed.write()
    assert path == jobs / "widget" / "snapshot.json" and json.loads(path.read_text())["counts"]["leads"] == 9
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert [p.name for p in (jobs / "widget").iterdir()] == ["snapshot.json"]                    # no draft left
    feed.write()
    assert [p.name for p in (jobs / "widget").iterdir()] == ["snapshot.json"]


def test_the_widget_folder_is_in_the_data_home_never_in_the_data():
    assert widget_feed.folder() == config.HOME.library / "widget"
    assert widget_feed.folder() not in config.DATA_DIR.parents and config.DATA_DIR not in widget_feed.folder().parents


def test_the_app_writes_it_and_a_failure_is_only_noted(jobs, monkeypatch):
    monkeypatch.setattr(widget_feed, "folder", lambda: jobs / "widget")
    assert ui_api.Api().widget_update() == {"ok": True} and (jobs / "widget" / "snapshot.json").is_file()
    noted = []
    monkeypatch.setattr(trouble, "note", lambda where, e: noted.append(where))
    monkeypatch.setattr(widget_feed.WidgetFeed, "write", lambda self: (_ for _ in ()).throw(OSError("disk full")))
    result = ui_api.Api().widget_update()
    assert result["ok"] is False and "disk full" in result["msg"] and noted == ["writing the summary for the widget"]


def test_the_weekly_run_brings_the_widget_up_to_date(isolate_data, monkeypatch):
    calls = []
    monkeypatch.setattr(weekly.WeeklyRun, "run", lambda self: 0)
    monkeypatch.setattr(ui_api.Api, "widget_update", lambda self: calls.append(True) or {"ok": True})
    assert weekly.main() == 0 and calls == [True]


def test_the_window_refreshes_the_widget(qapp, isolate_data, monkeypatch):
    from jobhelper import qt_bridge
    done = []
    monkeypatch.setattr(ui_api.Api, "widget_update", lambda self: done.append(True) or {"ok": True})
    qt_bridge.Bridge().refreshWidget()
    for _ in range(50):
        if done:
            break
        import time
        time.sleep(0.02)
    assert done == [True]
    main = (ROOT / "ui_qt" / "Main.qml").read_text(encoding="utf-8")
    assert "bridge.refreshWidget()" in main.split("function reloadAll()")[1].split("}")[0]


# ── the widget itself (Swift): it reads what the app writes, and only that ──
def test_the_widget_reads_the_folder_the_app_writes():
    assert '"Library/Application Support/JobHelper/widget/snapshot.json"' in SWIFT
    assert widget_feed.FILE_NAME == "snapshot.json"


def test_the_widget_knows_every_key_the_app_writes(jobs):
    s = widget_feed.WidgetFeed(FakeApp(), jobs / "w").snapshot()
    keys = set(s) | set(s["counts"]) | set(s["next"][0]) | set(s["last_run"]) | set(s["usage"])
    for key in keys:
        assert re.search(rf'"{key}"|\b{key}\b', SWIFT), key


def test_the_widget_may_only_read_its_own_folder():
    rights = plistlib.loads((ROOT / "widget" / "JobHelperWidget.entitlements").read_bytes())
    assert rights == {"com.apple.security.app-sandbox": True,
                      "com.apple.security.temporary-exception.files.home-relative-path.read-only":
                          ["/Library/Application Support/JobHelper/widget/"]}
    assert str(widget_feed.folder()).endswith("JobHelper/widget") or "JOBHELPER_HOME" in os.environ


def test_the_widget_is_built_into_the_app():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_app
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    info = build_app.WidgetBuild(Path("/x/JobHelper.app")).info()
    assert info["NSExtension"] == {"NSExtensionPointIdentifier": "com.apple.widgetkit-extension"}
    assert info["CFBundleIdentifier"].startswith(info["CFBundleIdentifier"].rsplit(".", 1)[0]) and info["CFBundlePackageType"] == "XPC!"
    assert str(build_app.WidgetBuild(Path("/x/JobHelper.app")).appex).endswith("Contents/PlugIns/JobHelperWidget.appex")


def test_the_system_service_offers_it_on_the_facade():
    assert "widget_update" in vars(api_system.SystemService) and hasattr(ui_api.Api, "widget_update")
