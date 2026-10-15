"""The small objects the window's back end shares (jobhelper/api_core.py)."""
from jobhelper import api_core, store, trouble


def test_the_cv_is_read_once_until_the_file_changes(tmp_path, monkeypatch):
    cv = tmp_path / "cv.txt"
    cv.write_text("first", encoding="utf-8")
    reads = []
    monkeypatch.setattr(api_core.agent1_cv, "find_cv", lambda: cv)
    monkeypatch.setattr(api_core.agent1_cv, "read_cv_text", lambda path: reads.append(path) or path.read_text(encoding="utf-8"))
    source = api_core.CvSource()
    assert source.text() == "first" and source.text() == "first" and len(reads) == 1
    import os
    cv.write_text("second", encoding="utf-8")
    os.utime(cv, (cv.stat().st_atime, cv.stat().st_mtime + 5))
    assert source.text() == "second" and len(reads) == 2
    assert api_core.CvSource().text() == "second"                      # each source keeps its own copy, nothing global
    monkeypatch.setattr(api_core.agent1_cv, "find_cv", lambda: None)
    assert api_core.CvSource().text() == ""


def test_a_hand_edit_reaches_the_saved_list_and_the_running_one(isolate_data):
    store.save_jobs([store.new_job(id="a", title="T", company="C", status="waiting")])
    editor = api_core.JobEditor()
    running = store.load_jobs()
    editor.live = running
    assert editor.change("a", lambda jobs, j: j.update(status="interview"), render=False) == {"ok": True}
    assert store.find(store.load_jobs(), "a")["status"] == "interview" and running[0]["status"] == "interview"
    refused = editor.change("a", lambda jobs, j: {"ok": False, "msg": "no"}, render=False)
    assert refused == {"ok": False, "msg": "no"}
    assert editor.change("zzz", lambda jobs, j: None)["ok"] is False


def test_the_desktop_notes_a_failure_instead_of_raising(monkeypatch):
    noted = []
    monkeypatch.undo()          # the guard in conftest replaces open/reveal; this test uses the real ones, with no program to run
    monkeypatch.setattr(trouble, "note", lambda what, e: noted.append(what))
    def broken(*a, **k):
        raise OSError("no such program")
    monkeypatch.setattr(api_core.subprocess, "Popen", broken)
    api_core.Desktop().open("/nowhere")
    api_core.Desktop().reveal("/nowhere/file.pdf")
    assert noted == ["opening a file or folder", "showing a file in its folder"]
