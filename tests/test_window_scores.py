"""The window, loaded offscreen: scoring again, Options, documents, the light theme and the illustrated guide.

Its tests share one window and follow on from each other, so they run on one worker in this order (see
tests/window_harness.py). The other window test files run beside it, each with a window of its own."""

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.xdist_group("test_window_scores")


from jobhelper import api_core, config, qt_bridge, store, ui_api  # noqa: E402
from tests.conftest import ROOT  # noqa: E402
from tests.window_harness import (READY, _contrast, _open, _open_job, _until_closed, _until_open, _until_true, _wait_scored, qml_source)  # noqa: E402


# ── score again ─────────────────────────────────────────────────────────────
def test_score_again_from_the_job_window(ui, monkeypatch):
    import time

    from jobhelper import llm
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: "Alex Novak\nPython.")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 35, "match_reason": "Another field."})
    _open_job(ui, "lead")
    assert ui.find("scoreAgain").property("text") == "Score again" and ui.js("detailDialog.job.can_rescore") is True
    ui.js("detailDialog.scoreAgain()")
    assert ui.js("detailDialog.scoreBusy") is True and ui.find("scoreAgain").property("enabled") is False
    for _ in range(200):
        time.sleep(0.02)
        ui.wait(10)
        if ui.js("detailDialog.scoreBusy") is False:
            break
    assert ui.find("scoreNote").property("text") == "Scored again: 80 before, 35 now."
    assert ui.js("detailDialog.job.score") == 35 and ui.js("detailDialog.job.score_before") == 80
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    _open_job(ui, "lead")                                                       # later it still says what it was
    assert ui.find("scoreNote").property("text") == "It was 80 before it was scored again."
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    _open_job(ui, "app")
    assert ui.js("detailDialog.job.can_rescore") is False                         # an application is not scored again
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(match_score=80, match_reason="", score_before=None), render=False)
    assert ui.warnings == []


def test_score_again_says_why_it_failed_and_keeps_the_score(ui, monkeypatch):
    import time

    from jobhelper import llm

    def limit(*a, **k):
        raise llm.LimitReached("Claude's 7-day limit is used up (99%). It resets at 18:00.")
    monkeypatch.setattr(llm, "ask_json", limit)
    _open_job(ui, "lead")
    ui.js("detailDialog.scoreAgain()")
    for _ in range(200):
        time.sleep(0.02)
        ui.wait(10)
        if ui.js("detailDialog.scoreBusy") is False:
            break
    assert "Not scored again: Claude's 7-day limit is used up" in ui.find("scoreNote").property("text") and ui.js("detailDialog.scoreBad") is True
    assert ui.js("detailDialog.job.score") == 80
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    assert ui.warnings == []


def test_score_all_again_asks_before_spending_the_limit(ui, monkeypatch):
    started = []
    monkeypatch.setattr(qt_bridge.Bridge, "rescoreAll", lambda self: started.append(1) or {"ok": False, "msg": "A run is already in progress."})
    ui.js('openView("new")')
    _until_open(ui, "tableDialog")
    button = ui.find("rescoreAll")
    assert button.property("visible") is True and button.property("text") == "Score all again"
    source = qml_source()
    assert "Only scores change; no letter is written or removed. Press again to start." in source
    ui.js("tableDialog.confirmRescore = true; tableDialog.rescoreJobs = 1")
    assert button.property("text") == "Yes, score 1 again"
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")
    assert ui.js("tableDialog.confirmRescore") is False and started == []         # closing takes the confirmation back; nothing started
    ui.js('openView("app")')
    _until_open(ui, "tableDialog")
    assert button.property("visible") is False                                    # only in New Jobs
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")
    assert ui.warnings == []


# ── Options: changes are not thrown away unasked ────────────────────────────
def test_options_ask_once_before_discarding_changes(ui):
    dialog = ui.find("optDialog")
    start = ui.bridge.options()
    ui.bridge.saveOptions({**start, "where": "Prague"})
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    assert ui.js("optDialog.changed()") is False
    ui.js("optDialog.tryClose()")                                               # nothing changed: closes at once
    ui.wait(450)
    assert dialog.property("visible") is False
    _open(ui, dialog, 450)
    ui.js("thrSpin.value = thrSpin.value + 5")
    assert ui.js("optDialog.changed()") is True
    ui.js("optDialog.tryClose()")
    ui.wait(250)
    assert dialog.property("visible") is True and "did not save" in ui.js("optDialog.optErr")
    assert ui.find("optCancel").property("text") == "Discard changes"
    ui.js("thrSpin.value = thrSpin.value - 5")                                  # put back by hand: nothing to lose any more
    assert ui.js("optDialog.changed()") is False
    ui.js('skipTags.add("contractor"); optDialog.confirmClose = false; optDialog.tryClose()')
    ui.wait(200)
    assert dialog.property("visible") is True                                     # a tag counts as a change too
    ui.js("optDialog.tryClose()")                                               # the second time it goes
    ui.wait(450)
    assert dialog.property("visible") is False and "contractor" not in ui.bridge.options()["skip_words"]
    assert ui.js("optDialog.closePolicy === 0") is True                           # Esc cannot bypass the question
    ui.bridge.saveOptions(start)
    ui.js("optsData = bridge.options()")
    assert ui.warnings == []


# ── what a score rests on, pasted text, documents left from a higher score ──
def test_a_title_only_score_is_marked_and_the_posting_can_be_pasted(ui, monkeypatch):
    from jobhelper import llm
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: "Alex Novak\nPython.")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"match_score": 65, "match_reason": "Fits."})
    start = store.find(store.load_jobs(), "lead")
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(description="", match_score=40), render=False)
    ui.js('openView("new")')
    _until_open(ui, "tableDialog")
    assert "scored from the title only" in ui.js("listView.model[0].secondary")
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")
    _open_job(ui, "lead")
    assert ui.find("basisRow").property("visible") is True and ui.js("detailDialog.job.basis") == "title"
    ui.js('detailDialog.pasteOpen = true; pastedText.text = "too short"; detailDialog.savePasted()')
    assert ui.find("pasteHint").property("text") == "That is only 9 characters. Paste the whole posting (at least 200)."
    ui.js('pastedText.text = "' + "x" * 20010 + '"; detailDialog.pasteErr = ""')
    assert ui.find("pasteHint").property("text") == "10 characters too long (the limit is 20000)"
    ui.js("detailDialog.savePasted()")
    assert "the most is 20000" in ui.find("pasteHint").property("text") and ui.js("detailDialog.pasteOpen") is True      # refused, stays open
    ui.js('pastedText.text = "' + "We build internal tools in Python and test them well. " * 10 + '"; detailDialog.savePasted()')
    assert ui.js("detailDialog.pasteOpen") is False and ui.js("detailDialog.job.basis") == ""
    assert ui.find("basisRow").property("visible") is False
    assert ui.js("detailDialog.scoreBusy") is True                                   # the new text is scored at once, unasked
    assert ui.find("scoreNote").property("text") == "The posting's text is saved. Asking Claude…"
    _wait_scored(ui)
    assert ui.find("scoreNote").property("text") == "The posting's text is saved. Scored again: 40 before, 65 now."
    assert ui.js("detailDialog.job.score") == 65 and ui.js("detailDialog.scoreLead") == ""
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(description=start.get("description", ""), match_score=80, description_by_hand=False), render=False)
    assert ui.warnings == []


def test_documents_from_a_higher_score_are_marked_and_moved_only_after_asking(ui, monkeypatch):
    for folder, name in ((config.TAILORED_CV_DIR, "cv_lead.docx"), (config.LETTERS_DIR, "L_lead.docx")):
        (folder / name).write_bytes(b"x")
    monkeypatch.setattr(ui_api.Api, "threshold", lambda self: 50)
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(tailored_cv_file="cv_lead.docx", cover_letter_file="L_lead.docx",
                                                             status="letter_ready", match_score=30), render=False)
    ui.js('openView("new")')
    _until_open(ui, "tableDialog")
    assert "documents from a higher score" in ui.js("listView.model[0].secondary")
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")
    _open_job(ui, "lead")
    assert ui.find("staleRow").property("visible") is True and "below your limit of 50" in ui.find("staleText").property("text")
    ui.js("detailDialog.shelve()")
    assert ui.find("shelveDocs").property("text") == "Yes, move them" and (config.LETTERS_DIR / "L_lead.docx").exists()      # asked first
    ui.js("detailDialog.shelve()")
    assert ui.find("staleText").property("text").endswith("files moved to the backup.") and not (config.LETTERS_DIR / "L_lead.docx").exists()
    assert ui.js("detailDialog.job.docs_stale") is False and ui.find("shelveDocs").property("visible") is False
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(match_score=80, status="letter_ready"), render=False)
    assert ui.warnings == []


def test_read_it_again_button_reports_both_outcomes(ui, monkeypatch):
    from jobhelper import agent2_search
    start = store.find(store.load_jobs(), "lead")
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(description="", match_score=40, url="https://example.com/job"), render=False)
    _open_job(ui, "lead")
    assert ui.find("rereadPosting").property("visible") is True
    got = ui.js("bridge.rereadPosting(detailDialog.job.id)")
    assert got["ok"] is False and "paste its text instead" in got["msg"]
    ui.js("detailDialog.readAgain()")                                                # the button: nothing new to read
    assert "paste its text instead" in ui.find("scoreNote").property("text") and ui.js("detailDialog.scoreBad") is True
    assert ui.js("detailDialog.scoreBusy") is False
    text = "We build internal tools in Python and test them well. " * 10
    monkeypatch.setattr(agent2_search, "refetch_description", lambda job: text)
    ui.js("win.appRunning = true; detailDialog.readAgain()")                         # read, but a search is running: no scoring now
    assert ui.find("scoreNote").property("text") == f"Read {len(text)} characters of the posting. A search or scan is running: press Score again when it has finished."
    assert ui.js("detailDialog.scoreBusy") is False and ui.js("detailDialog.job.basis") == "" and ui.find("basisRow").property("visible") is False
    ui.js("win.appRunning = false")

    from jobhelper import llm
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: "Alex Novak\nPython.")
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(description="", match_score=40), render=False)
    ui.js("detailDialog.refresh()")

    def limit(*a, **k):
        raise llm.LimitReached("Claude's 7-day limit is used up.")
    monkeypatch.setattr(llm, "ask_json", limit)
    ui.js("detailDialog.readAgain()")
    assert ui.find("rereadPosting").property("enabled") is False
    _wait_scored(ui)
    note = ui.find("scoreNote").property("text")                                     # the text is kept, and the reason it was not scored is said
    assert note.startswith(f"Read {len(text)} characters of the posting. Not scored again:") and ui.js("detailDialog.scoreBad") is True
    assert store.find(store.load_jobs(), "lead")["description"] == text and ui.js("detailDialog.job.score") == 40

    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(description="", match_score=None), render=False)   # a job with no score yet
    ui.js("detailDialog.refresh(); detailDialog.readAgain()")
    assert ui.js("detailDialog.scoreBusy") is False and ui.js("ticker.text") == f"Read {len(text)} characters of the posting. The next search will score it."
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(description=start.get("description", ""), match_score=80, url=""), render=False)
    assert ui.warnings == []


# ── New Jobs: all documents below the limit at once, and the score a job had before ──
def test_documents_below_the_limit_are_moved_together_only_after_asking(ui, monkeypatch):
    for folder, name in ((config.TAILORED_CV_DIR, "cv_lead.docx"), (config.LETTERS_DIR, "L_lead.docx")):
        (folder / name).write_bytes(b"x")
    monkeypatch.setattr(ui_api.Api, "threshold", lambda self: 50)
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(tailored_cv_file="cv_lead.docx", cover_letter_file="L_lead.docx",
                                                             status="letter_ready", match_score=30), render=False)
    ui.js('openView("new")')
    _until_open(ui, "tableDialog")
    bar, button, text = ui.find("staleBar"), ui.find("shelveAll"), ui.find("staleBarText")
    assert bar.property("visible") is True and button.property("text") == "Move them to backup"
    assert text.property("text") == "1 job has documents from a score that is now below your limit."
    ui.js("tableDialog.shelveAll()")                                                # first press only asks, and names the jobs
    assert button.property("text") == "Yes, move documents of 1 job" and "A letter of your own is never moved." in text.property("text")
    title = store.find(store.load_jobs(), "lead")["title"]
    assert ui.find("staleNames").property("visible") is True and title in ui.find("staleNames").property("text")
    assert (config.LETTERS_DIR / "L_lead.docx").exists()
    ui.js('tableDialog.confirmStale = false')                                       # Cancel
    assert button.property("text") == "Move them to backup" and (config.LETTERS_DIR / "L_lead.docx").exists()
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")
    ui.js('openView("new")')
    _until_open(ui, "tableDialog")
    assert ui.js("tableDialog.confirmStale") is False                               # a closed window forgets the question

    ui.js("tableDialog.shelveAll()")
    ui.js("win.appRunning = true; tableDialog.shelveAll()")                         # a search started meanwhile
    assert "A search or scan is running" in ui.find("staleNote").property("text") and ui.js("tableDialog.staleBad") is True
    assert (config.LETTERS_DIR / "L_lead.docx").exists()
    ui.js("win.appRunning = false")

    ui.bridge._running = True                                                       # the bridge refuses too, whatever the window thinks
    try:
        assert "A search or scan is running" in ui.bridge.shelveAllDocs(1)["msg"] and (config.LETTERS_DIR / "L_lead.docx").exists()
    finally:
        ui.bridge._running = False

    ui.js("tableDialog.staleRows = [{id: 'x', title: 'T', company: 'C', score: 1}, {id: 'y', title: 'T', company: 'C', score: 1}]; tableDialog.confirmStale = true")
    ui.js("tableDialog.shelveAll()")                                                # the list is not what was asked about
    assert "The list changed: it is now 1 job" in ui.find("staleNote").property("text") and (config.LETTERS_DIR / "L_lead.docx").exists()
    assert ui.js("tableDialog.confirmStale") is True and ui.js("tableDialog.staleRows.length") == 1
    ui.js("tableDialog.shelveAll()")
    assert not (config.LETTERS_DIR / "L_lead.docx").exists() and not (config.TAILORED_CV_DIR / "cv_lead.docx").exists()
    assert "Documents of 1 job moved to the backup (2 files)." in ui.js("ticker.text")
    assert "documents from a higher score" not in ui.js("listView.model[0].secondary")
    assert ui.find("staleBarText").property("visible") is False                     # nothing left to move …

    undo = ui.find("undoRow")                                                       # … and what was moved can be put back
    assert bar.property("visible") is True and undo.property("visible") is True
    assert ui.find("undoText").property("text").startswith("Documents of 1 job were moved to the backup on 20")
    ui.js("win.appRunning = true; tableDialog.putBack()")
    assert "A search or scan is running. Put the documents back" in ui.find("staleNote").property("text") and not (config.LETTERS_DIR / "L_lead.docx").exists()
    ui.js("win.appRunning = false")
    ui.bridge._running = True
    try:
        assert "A search or scan is running" in ui.bridge.unshelveLast("")["msg"] and "A search or scan is running" in ui.bridge.unshelveDocs("lead")["msg"]
    finally:
        ui.bridge._running = False
    ui.js("tableDialog.lastShelved = {batch: 'gone', when: '2026-01-01T10:00:00', jobs: [{id: 'lead'}]}; tableDialog.putBack()")
    assert "The list changed. Look at it again" in ui.find("staleNote").property("text") and ui.js("tableDialog.staleBad") is True
    assert ui.js("tableDialog.lastShelved.batch") != "gone" and not (config.LETTERS_DIR / "L_lead.docx").exists()      # the real batch is shown again
    ui.js("tableDialog.putBack()")
    assert (config.LETTERS_DIR / "L_lead.docx").exists() and (config.TAILORED_CV_DIR / "cv_lead.docx").exists()
    assert "Documents of 1 job are back in place (2 files)." in ui.js("ticker.text")
    assert undo.property("visible") is False and ui.find("staleBarText").property("visible") is True                    # below the limit again, so offered again
    assert "documents from a higher score" in ui.js("listView.model[0].secondary")
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")

    _open_job(ui, "lead")                                                           # the same for one job, in its window
    ui.js("detailDialog.shelve(); detailDialog.shelve()")
    assert not (config.LETTERS_DIR / "L_lead.docx").exists() and ui.find("unshelveDocs").property("visible") is True
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    _open_job(ui, "lead")
    assert ui.find("staleRow").property("visible") is True and ui.find("staleText").property("text").startswith("The documents the app wrote for this job were moved to the backup on 20")
    ui.js("win.appRunning = true; detailDialog.unshelve()")
    assert "A search or scan is running" in ui.find("staleText").property("text") and ui.js("detailDialog.shelveBad") is True
    ui.js("win.appRunning = false")
    (config.LETTERS_DIR / "L_lead.docx").write_bytes(b"in the way")
    ui.js("detailDialog.unshelve()")
    assert "A file named L_lead.docx is already in its folder" in ui.find("staleText").property("text") and ui.js("detailDialog.shelveBad") is True
    (config.LETTERS_DIR / "L_lead.docx").unlink()
    ui.js("detailDialog.unshelve()")
    assert ui.find("staleText").property("text") == "2 files are back in place." and ui.js("detailDialog.shelveBad") is False
    assert (config.LETTERS_DIR / "L_lead.docx").read_bytes() == b"x" and ui.find("unshelveDocs").property("visible") is False
    assert ui.find("shelveDocs").property("visible") is True
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")

    ui.js('openView("app")')
    _until_open(ui, "tableDialog")
    assert bar.property("visible") is False                                         # only in New Jobs
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(match_score=80, status="letter_ready"), render=False)
    assert ui.warnings == []


def test_the_list_shows_the_score_before(ui):
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(score_before=55, match_score=30), render=False)
    ui.js('openView("new")')
    _until_open(ui, "tableDialog")
    row = ui.js("(function(){ var m = listView.model; for (var i = 0; i < m.length; i++) if (m[i].id === 'lead') return m[i]; return {}; })()")
    assert row["was"] == "was 55" and row["value"] == "30" and ui.js("tableDialog.anyWas") is True
    assert not row["secondary"].startswith(" ") and "·   ·" not in row["secondary"]      # no separator before the first note
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(score_before=80, match_score=80), render=False)
    ui.js('openView("new")')
    _until_open(ui, "tableDialog")
    assert ui.js("tableDialog.anyWas") is False and ui.js("listView.model.map(function (r) { return r.was || ''; }).join('')") == ""
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")
    assert "the score it had before it was scored again" in qml_source()
    assert ui.warnings == []


# ── Options: old moved documents are removed only after asking, with the count ──
def test_old_moved_documents_are_removed_from_options_after_asking(ui):
    from datetime import datetime, timedelta

    from jobhelper import housekeeping, vault
    folder = vault.backups_dir() / housekeeping.SHELF
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        old.unlink()

    def copy(name, days):
        path = folder / f"{name}.{(datetime.now() - timedelta(days=days, minutes=5)).strftime('%Y%m%d_%H%M%S')}.docx.enc"
        path.write_bytes(b"x" * 4096)
        return path
    fresh, old_one, old_two = copy("fresh", 1), copy("one", 40), copy("two", 90)
    dialog = ui.find("optDialog")
    _open(ui, dialog, 450)
    note, button = ui.find("shelfNote"), ui.find("tidyShelf")
    assert note.property("text") == "3 moved documents are in the backup (12 KB). 2 are older than 30 days (8 KB)."
    assert button.property("text") == "Remove" and button.property("enabled") is True
    ui.js("shelfSpin.value = 200")                                                    # another age: counted again at once
    assert note.property("text").endswith("None is older than 200 days.") and button.property("enabled") is False
    ui.js("optDialog.tidyShelf()")
    assert ui.js("optDialog.confirmTidy") is False and old_two.exists()               # nothing to ask about
    ui.js("shelfSpin.value = 60; optDialog.tidyShelf()")                              # first press only asks
    assert button.property("text") == "Yes, move 1 to the Trash" and "The app can then no longer put them back" in note.property("text") and old_two.exists()
    assert ui.find("tidyCancel").property("visible") is True
    ui.js("shelfSpin.value = 30")                                                     # the age changed: the question is taken back
    assert ui.js("optDialog.confirmTidy") is False and button.property("text") == "Remove"
    ui.js("optDialog.tidyShelf(); win.appRunning = true; optDialog.tidyShelf()")      # a search started meanwhile
    assert "A search or scan is running" in note.property("text") and ui.js("optDialog.shelfBad") is True and old_one.exists()
    ui.js("win.appRunning = false")
    ui.bridge._running = True
    try:
        assert "A search or scan is running" in ui.bridge.tidyShelf(30, 2)["msg"] and old_one.exists()
    finally:
        ui.bridge._running = False
    ui.js("optDialog.tidyShelf()")
    copy("three", 50)                                                                 # the folder changed after the question
    ui.js("optDialog.tidyShelf()")
    assert "The number changed: it is now 3" in note.property("text") and button.property("text") == "Yes, move 3 to the Trash" and old_one.exists()
    ui.js("optDialog.tidyShelf()")
    assert note.property("text") == "Moved 3 old copies to the Trash (12 KB)." and ui.js("optDialog.shelfBad") is False
    assert (housekeeping.trash_dir(old_one) / old_one.name).exists()
    assert not old_one.exists() and not old_two.exists() and fresh.exists() and button.property("enabled") is False
    assert "wrapMode: Text.WordWrap" in qml_source().split('objectName: "shelfNote"')[1][:200]
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
    _open(ui, dialog, 450)
    assert note.property("text") == "1 moved document is in the backup (4 KB). None is older than 30 days."
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
    fresh.unlink()
    assert ui.warnings == []


def test_jobs_that_could_not_be_put_back_are_listed_one_by_one(ui, monkeypatch):
    monkeypatch.setattr(ui_api.Api, "threshold", lambda self: 50)
    jobs = store.load_jobs()
    for name in ("one", "two"):
        (config.LETTERS_DIR / f"L_{name}.docx").write_bytes(b"x")
        jobs.append(store.new_job(id=f"pb_{name}", title=f"Tester {name}", company="Acme <b>Labs</b>", match_score=20, status="letter_ready",
                                  cover_letter_file=f"L_{name}.docx", description="x" * 900))
    store.save_jobs(jobs)
    try:
        ui.js('openView("new")')
        _until_open(ui, "tableDialog")
        ui.js("tableDialog.shelveAll(); tableDialog.shelveAll()")
        assert not (config.LETTERS_DIR / "L_one.docx").exists() and ui.js("tableDialog.staleFailed.length") == 0
        (config.LETTERS_DIR / "L_one.docx").write_bytes(b"in the way")
        ui.js("tableDialog.putBack()")
        failed = ui.find("staleFailed")
        assert ui.find("staleNote").property("text") == "Documents of 1 job are back in place (1 file). Not put back:" and ui.js("tableDialog.staleBad") is True
        assert failed.property("visible") is True
        assert failed.property("text") == "Tester one  ·  Acme <b>Labs</b>: A file named L_one.docx is already in its folder, so nothing was put back."
        assert (config.LETTERS_DIR / "L_two.docx").exists() and ui.find("undoRow").property("visible") is True          # the one left is still offered
        ui.js("tableDialog.putBack()")                                                    # nothing could be done this time: said per job too
        assert ui.find("staleNote").property("text") == "Couldn't put the documents back. The reason for each job:"
        assert "Tester one" in failed.property("text") and failed.property("text").count("\n") == 0
        (config.LETTERS_DIR / "L_one.docx").unlink()
        ui.js("tableDialog.putBack()")
        assert ui.js("tableDialog.staleFailed.length") == 0 and failed.property("visible") is False and (config.LETTERS_DIR / "L_one.docx").read_bytes() == b"x"
        source = qml_source().split('objectName: "staleFailed"')[1][:260]
        assert "textFormat: Text.PlainText" in qml_source().split('objectName: "staleFailed"')[0][-120:] + source and "wrapMode: Text.WordWrap" in source
        ui.js("tableDialog.close()")
        _until_closed(ui, "tableDialog")
        assert ui.js("tableDialog.staleFailed.length") == 0
    finally:
        store.save_jobs([j for j in store.load_jobs() if not j["id"].startswith("pb_")])
        for name in ("one", "two"):
            (config.LETTERS_DIR / f"L_{name}.docx").unlink(missing_ok=True)
    assert ui.warnings == []


# ── light theme: small text must read against the light surfaces ────────────


def test_light_theme_text_colours_read_on_light_surfaces():
    import re
    main = (ROOT / "ui_qt" / "Main.qml").read_text(encoding="utf-8")
    light = {name: value for name, value in re.findall(r'property color (\w+): win\.dark \? "#[0-9a-fA-F]{6}" : "(#[0-9a-fA-F]{6})"', main)}
    assert {"winbg", "surface", "surface2", "inset", "ink", "soft", "faint", "steel", "accent", "good", "warn", "crit", "a6"} <= set(light)
    for text in ("ink", "soft", "faint", "steel", "accent", "good", "warn", "crit", "a6"):   # accent: links; a6: the assistant's words
        for ground in ("winbg", "surface", "surface2", "inset"):
            assert _contrast(light[text], light[ground]) >= 4.5, (text, ground, round(_contrast(light[text], light[ground]), 2))
    assert _contrast(light["accentInk"], light["accent"]) >= 4.5 and _contrast(light["accentInk"], light["good"]) >= 4.5   # the label on a main button, the tick
    assert _contrast(light["warn"], light["warnbg"]) >= 4.5 and _contrast(light["good"], light["goodbg"]) >= 4.5 and _contrast(light["crit"], light["critbg"]) >= 4.5


def test_dark_theme_text_colours_read_on_dark_surfaces():
    import re
    main = (ROOT / "ui_qt" / "Main.qml").read_text(encoding="utf-8")
    dark = {name: value for name, value in re.findall(r'property color (\w+): win\.dark \? "(#[0-9a-fA-F]{6})" : "#[0-9a-fA-F]{6}"', main)}
    assert {"winbg", "surface", "surface2", "ink", "soft", "faint", "accent", "accentInk", "good", "warn", "crit"} <= set(dark)
    for text in ("ink", "soft", "faint", "good", "warn", "crit", "accent"):
        for ground in ("winbg", "surface", "surface2"):
            assert _contrast(dark[text], dark[ground]) >= 4.5, (text, ground, round(_contrast(dark[text], dark[ground]), 2))
    assert _contrast(dark["accentInk"], dark["accent"]) >= 4.5 and _contrast(dark["accentInk"], dark["good"]) >= 4.5   # the label on a main button, the tick
    assert _contrast(dark["warn"], dark["warnbg"]) >= 4.5 and _contrast(dark["good"], dark["goodbg"]) >= 4.5 and _contrast(dark["crit"], dark["critbg"]) >= 4.5


def test_a_badge_label_is_the_one_that_reads_better_on_its_colour(ui):
    """The counter on a gate takes white or near-black from the theme, whichever reads better on that robot's colour:
    white on the orange Tracker read at 2.3:1. Both a real colour and "#rrggbb" text are understood."""
    import re
    main = (ROOT / "ui_qt" / "Main.qml").read_text(encoding="utf-8")
    labels = ("#ffffff", re.search(r'property color night: "(#[0-9a-f]{6})"', main).group(1))
    colours = dict(re.findall(r'property color (a[1-5]): "(#[0-9a-fA-F]{6})"', main))
    colours["light assistant"] = re.search(r'property color a6: win\.dark \? "#[0-9a-fA-F]{6}" : "(#[0-9a-fA-F]{6})"', main).group(1)
    for name, colour in colours.items():
        best = max(labels, key=lambda label: _contrast(label, colour))
        assert ui.js(f'"" + theme.labelOn(Qt.color("{colour}"))') == best, name
        assert ui.js(f'"" + theme.labelOn("{colour}")') == best, name               # the same answer for colour text
    assert {ui.js(f'"" + theme.labelOn("{c}")') for c in colours.values()} == set(labels)   # both labels are really used
    assert _contrast(ui.js(f'"" + theme.labelOn("{colours["a4"]}")'), colours["a4"]) >= 4.5
    assert "theme.labelOn(g.ag)" in (ROOT / "ui_qt" / "Gate.qml").read_text(encoding="utf-8")


def test_the_resume_button_s_white_label_reads_on_its_blue(ui):
    assert _contrast("#ffffff", ui.js('"" + theme.resume')) >= 4.5 and "theme.resume" in qml_source()


def test_every_colour_of_the_window_lives_in_the_theme():
    """The robots' screens, the Resume blue and the sheets on the belt are named in the theme, and the robots take their
    theme as a required property: no stale fallback colour can show (the old steel #6b7787 lingered there)."""
    import re
    main = (ROOT / "ui_qt" / "Main.qml").read_text(encoding="utf-8")
    for name in ("night", "resume", "paper", "paperLine"):
        assert re.search(rf"property color {name}: ", main), name
    for path in (ROOT / "ui_qt").glob("*.qml"):
        if path.name == "Main.qml":
            continue
        text = path.read_text(encoding="utf-8")
        for literal in ("#0d141c", "#2563eb", "#8b97a5", "#eef2f7", "#6b7787"):
            assert literal not in text, (path.name, literal)
        assert not re.search(r'theme \? (root\.)?theme\.\w+ : "#', text), path.name
    for robot in ("Robot.qml", "AssistantBot.qml"):
        assert "required property var theme" in (ROOT / "ui_qt" / robot).read_text(encoding="utf-8")


def test_no_label_on_the_accent_is_fixed_white():
    """A main button, a picked chip and the tick take their label colour from the theme: white suits only the light theme."""
    for name in ("SmallButton", "PillButton", "TableDialog", "HelpDialog", "OptionsDialog", "DetailDialog", "FormAnswersDialog", "PrepDialog",
                 "PrepEditDialog", "LetterDialog", "CompareDialog"):
        text = (ROOT / "ui_qt" / f"{name}.qml").read_text(encoding="utf-8")
        assert '"#ffffff"' not in text and '"white"' not in text, name
    assert "theme.accentInk" in (ROOT / "ui_qt" / "SmallButton.qml").read_text(encoding="utf-8")


def test_the_label_on_a_main_button_follows_the_theme(ui):
    """Read from the running window: a colour that exists in the file but does not reach the label would pass the other tests."""
    start = ui.js("win.dark")
    try:
        ui.js("win.dark = true")
        assert ui.js('"" + theme.accentInk') == "#1b1305" and ui.js('"" + theme.accent') == "#f0a84a"
        ui.js('openView("new")')
        _until_open(ui, "tableDialog")
        ui.js("tableDialog.confirmRescore = true; tableDialog.rescoreJobs = 1")              # a main-style button
        button = ui.find("rescoreAll")
        assert ui.js('"" + contentItem.color', button) == "#1b1305"
        ui.js("win.dark = false")
        ui.wait(50)
        assert ui.js('"" + theme.accentInk') == "#ffffff" and ui.js('"" + contentItem.color', button) == "#ffffff"
        ui.js("tableDialog.close()")
        _until_closed(ui, "tableDialog")
    finally:
        ui.js("win.dark = %s" % ("true" if start else "false"))
    assert ui.warnings == []


# ── text wraps, it is never cut off ─────────────────────────────────────────
def test_no_text_in_the_window_is_cut_with_an_ellipsis():
    for path in sorted((ROOT / "ui_qt").glob("*.qml")):
        text = path.read_text(encoding="utf-8")
        assert "elide:" not in text and "maximumLineCount" not in text, f"{path.name} cuts a text short; let it wrap"


def test_a_long_title_makes_its_row_taller_instead_of_being_cut(ui):
    long_title = "Senior Principal Associate Vice Coordinator of Cross-Functional Platform Reliability and Developer Experience Enablement (Remote, EMEA)"
    start = store.find(store.load_jobs(), "lead")["title"]
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(title=long_title), render=False)
    try:
        ui.js('openView("new")')
        _until_open(ui, "tableDialog")
        heights = ui.js("(function(){ var out = []; for (var i = 0; i < listView.count; i++) { var it = listView.itemAtIndex(i); if (it) out.push(Math.round(it.height)); } return out.join(','); })()")
        heights = [int(h) for h in heights.split(",") if h]
        assert max(heights) > 54 and min(heights) >= 54                                 # the long one grew, the others kept their size
        ui.js("tableDialog.close()")
        _until_closed(ui, "tableDialog")
        _open_job(ui, "lead")
        title = ui.find("detailTitle")
        assert title.property("truncated") is False and title.property("lineCount") >= 2 and title.property("text") == long_title
        ui.js("detailDialog.close()")
        _until_closed(ui, "detailDialog")
        ui.js('ticker.text = "' + "A long message in the status line that has to be read to its last word. " * 4 + '"')
        for _ in range(60):                                  # the bar grows with its message (slower on a busy machine)
            ui.wait(50)
            if ui.js("statusBar.height") > 46:
                break
        assert ui.js("statusBar.height") > 46 and ui.js("ticker.truncated") is False
        ui.js('ticker.text = ""')
    finally:
        ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(title=start), render=False)
    assert ui.warnings == []


def test_help_describes_what_was_added_since_it_was_written():
    text = (ROOT / "ui_qt" / "HelpDialog.qml").read_text(encoding="utf-8")
    for words in ("Move documents to backup", "Put them back", "Trash", "Kinds of role you want", "Read it again", "was 55",
                  "no longer accepts applications", "app_trouble.log", "docs/GUIDE.md"):
        assert words in text, words


# ── the illustrated guide ───────────────────────────────────────────────────
def test_a_search_role_outside_software_can_be_added(ui):
    """The words the app knew for roles were all from software jobs: "registered nurse" was refused as not a role."""
    dialog = ui.find("optDialog")
    _open(ui, dialog, 450)
    before = ui.js("rolesModel.count")
    assert ui.js('optDialog.addRole("registered nurse")') is True and ui.js("optDialog.roleErr") == ""       # a profession the app knows
    assert ui.js('optDialog.addRole("junior accountant")') is True
    assert ui.js('optDialog.addRole("beekeeper")') is False                                                   # unknown: asked once …
    assert "is not a role the app knows" in ui.js("optDialog.roleErr") and "press Add again" in ui.js("optDialog.roleErr")
    assert ui.js("rolesModel.count") == before + 2
    assert ui.js('optDialog.addRole("beekeeper")') is True and ui.js("optDialog.roleErr") == ""               # … then added
    assert ui.js('optDialog.addRole("asdfgh")') is False and ui.js('optDialog.addRole("zzzzqq")') is False     # a different word is asked about afresh
    assert ui.js("rolesModel.count") == before + 3
    assert ui.js('optDialog.addRole("план")') is False and "Latin letters" in ui.js("optDialog.roleErr")       # the other checks still hold
    assert ui.js('optDialog.addRole("beekeeper")') is False and "already in the list" in ui.js("optDialog.roleErr")
    assert ui.bridge.knownRole("staff nurse") is True and ui.bridge.knownRole("beekeeper") is False and ui.bridge.knownRole("") is False
    ui.js("optDialog.pendingRole = ''; optDialog.roleErr = ''; optDialog.load()")
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
    assert ui.warnings == []


def test_the_job_window_asks_before_closing_with_unsaved_text(ui):
    _open_job(ui, "app")
    dialog = ui.find("detailDialog")
    assert ui.js("detailDialog.pending.length") == 0 and ui.js("detailDialog.closePolicy") != 0           # nothing typed: Esc closes
    ui.js('cnNotes.text = "They asked about pytest."')
    assert ui.js("detailDialog.pending.join('|')") == "the notes about the company" and ui.js("detailDialog.closePolicy") == 0   # Esc alone no longer closes
    ui.js("detailDialog.tryClose()")                                                                    # the ✕ (and Esc, through the shortcut)
    note = ui.find("closeNote")
    assert dialog.property("opened") is True and note.property("visible") is True
    assert note.property("text") == "Not saved yet: the notes about the company. Save it, or close once more to discard it."
    ui.js("detailDialog.saveNotes()")                                                                   # saved: nothing pending any more
    assert ui.js("detailDialog.pending.length") == 0
    ui.js('evNote.text = "bring the laptop"; replyText.text = "Dear Alex, thank you for your time today."')
    assert ui.js("detailDialog.pending.join('|')") == "the pasted reply|the date to remember"
    ui.js("detailDialog.confirmClose = false; detailDialog.tryClose()")
    assert "the pasted reply, the date to remember" in note.property("text") and dialog.property("opened") is True
    ui.js("detailDialog.tryClose()")                                                                    # the second time closes and discards
    ui.wait(350)
    assert dialog.property("opened") is False
    _open_job(ui, "app")                                                                                # opened again: clean
    assert ui.js("detailDialog.pending.length") == 0 and ui.js("detailDialog.closeNote") == "" and ui.js("replyText.text") == ""
    ui.js("detailDialog.tryClose()")
    ui.wait(350)
    assert dialog.property("opened") is False
    ui.bridge._api.save_company_notes("Beta", {"contact": "", "salary": "", "asked": "", "notes": ""})
    _open_job(ui, "lead")                                                                               # a new job has none of those fields filled
    assert ui.js("detailDialog.pending.length") == 0
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    assert ui.warnings == []


def test_a_reply_is_filed_under_another_application_from_its_window(ui, monkeypatch):
    from jobhelper import db
    db.upsert_response({"msg_id": "<move>", "received_date": "Tue, 18 Aug 2026 10:00:00 +0200", "from_addr": "hr@beta.example", "subject": "Interview",
                        "job_id": "", "company": "Beta", "role": "QA Engineer", "stage": "interview", "summary": "They invite you to a call."})
    dialog = ui.find("responseDialog")
    ui.js('responseDialog.show("<move>")')
    _until_open(ui, "responseDialog")
    button, note = ui.find("fileUnder"), ui.find("fileNote")
    assert button.property("text") == "File under…" and ui.find("filePicker").property("visible") is False
    ui.js("win.appRunning = true; responseDialog.startPicking()")
    assert dialog.property("picking") is False and dialog.property("fileBad") is True and "running" in note.property("text")
    ui.js("win.appRunning = false; responseDialog.startPicking()")
    assert dialog.property("picking") is True and button.property("text") == "Cancel"
    assert ui.find("pickList").property("count") == 1                                # the one application of the test data
    ui.find("pickFilter").setProperty("text", "nothing like this")
    ui.js('responseDialog.targets = bridge.filingTargets("nothing like this")')
    ui.wait(60)
    assert ui.find("pickList").property("count") == 0 and "No application matches" in ui.find("pickEmpty").property("text")
    ui.js('responseDialog.fileUnder("lead")')                                        # a new job, not an application: refused, said in red
    assert dialog.property("fileBad") is True and "Mark that job as applied first" in note.property("text") and dialog.property("picking") is True
    ui.js('responseDialog.fileUnder("app")')
    ui.wait(80)
    assert dialog.property("fileBad") is False and "Filed under Beta · QA Engineer." in note.property("text") and dialog.property("picking") is False
    assert ui.js("responseDialog.r.job_id") == "app" and button.property("text") == "File under another…"
    assert ui.bridge.jobDetail("app")["status"] == "interview"
    ui.js("responseDialog.startPicking()")
    assert ui.find("fileNowhere").property("visible") is True
    ui.js('responseDialog.fileUnder("")')
    assert ui.js("responseDialog.r.job_id") == "" and "not filed under any application now" in note.property("text")
    ui.js("responseDialog.close()")
    _until_closed(ui, "responseDialog")
    ui.bridge._api.editor.change("app", lambda jobs, j: j.update(status="waiting"), render=False)
    ui.bridge._set_running(True)
    assert "running" in ui.bridge.refileResponse("<move>", "app")["msg"]              # the backend refuses the same
    ui.bridge._set_running(False)
    ui.js('win.runMode = ""; win.resetRobots()')
    assert ui.warnings == []


def test_the_job_window_writes_documents_on_request(ui, monkeypatch):
    asked = []
    monkeypatch.setattr(ui_api.Api, "can_write_documents", lambda self, j: "" if j and j["id"] == "lead" else "no")
    monkeypatch.setattr(ui_api.Api, "write_documents", lambda self, job_id: asked.append(job_id) or {"ok": True, "cv": True, "letter": True,
                                                                                                      "msg": "Written: the CV and the letter."})
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(tailored_cv_file="", cover_letter_file=""), render=False)   # whatever earlier tests left
    ui.js('detailDialog.show("lead")')
    _until_open(ui, "detailDialog")
    button, note = ui.find("writeDocs"), ui.find("docsNote")
    assert ui.find("writeDocsRow").property("visible") is True and button.property("text") == "Write CV and letter"
    assert "No CV or letter was written for this job" in note.property("text")
    ui.js("win.appRunning = true; detailDialog.writeDocs()")
    assert asked == [] and ui.find("detailDialog").property("docsBad") is True and "running" in note.property("text")
    ui.js("win.appRunning = false; detailDialog.writeDocs()")
    assert ui.find("detailDialog").property("docsBusy") is True and button.property("text") == "Writing…" and "about a minute" in note.property("text")
    ui.js("detailDialog.writeDocs()")                                # a second press while it is writing: said, not started twice
    for _ in range(100):
        ui.wait(20)
        if not ui.find("detailDialog").property("docsBusy"):
            break
    assert asked == ["lead"] and note.property("text") == "Written: the CV and the letter." and ui.find("detailDialog").property("docsBad") is False
    monkeypatch.setattr(ui_api.Api, "write_documents", lambda self, job_id: {"ok": False, "msg": "Claude's 5-hour limit is used up."})
    ui.js("detailDialog.writeDocs()")
    for _ in range(100):
        ui.wait(20)
        if not ui.find("detailDialog").property("docsBusy"):
            break
    assert note.property("text") == "Not written: Claude's 5-hour limit is used up." and ui.find("detailDialog").property("docsBad") is True
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    ui.js('detailDialog.show("app")')                                # an application: the row is not offered
    _until_open(ui, "detailDialog")
    assert ui.find("writeDocsRow").property("visible") is False
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    assert ui.warnings == []


def test_help_shows_usage_and_the_log_of_problems(ui, monkeypatch):
    monkeypatch.setattr(ui_api.Api, "usage_overview", lambda self: {"calls": 12, "cost": 3.4, "kinds": [
        {"name": "Scoring jobs and writing letters", "calls": 9, "cost": 3.0}, {"name": "Reading replies", "calls": 3, "cost": 0.4}]})
    monkeypatch.setattr(ui_api.Api, "trouble_log", lambda self, most=25: {"lines": ["2026-10-09 12:15  a sound: it failed"], "total": 40, "file": "app_trouble.log"})
    shown = []
    monkeypatch.setattr(ui_api.Api, "show_trouble_log", lambda self: shown.append(1) or {"ok": True})
    ui.js("helpDialog.open()")
    _until_open(ui, "helpDialog")
    assert ui.find("usageCard").property("visible") is False                         # on its own tab
    ui.js('helpDialog.tab = "use"')
    ui.wait(120)
    assert ui.find("usageCard").property("visible") is True and ui.find("logCard").property("visible") is True
    total = ui.find("usageTotal").property("text")
    assert "12 questions in all" in total and "$3.40" in total and "subscription only" in total
    texts = {t.property("text") for t in ui.seen("usageCard") if isinstance(t.property("text"), str)}
    assert {"Scoring jobs and writing letters", "9 questions", "≈ $3.00", "≈ $0.40"} <= texts
    log_texts = {t.property("text") for t in ui.seen("logCard") if isinstance(t.property("text"), str)}
    assert "2026-10-09 12:15  a sound: it failed" in log_texts and any("1 of 40 shown" in t for t in log_texts)
    ui.js("bridge.showTroubleLog()")
    assert shown == [1]
    monkeypatch.setattr(ui_api.Api, "usage_overview", lambda self: {"calls": 0, "cost": 0.0, "kinds": []})
    monkeypatch.setattr(ui_api.Api, "trouble_log", lambda self, most=25: {"lines": [], "total": 0, "file": "app_trouble.log"})
    ui.js("helpDialog.close()")
    _until_closed(ui, "helpDialog")
    ui.js('helpDialog.open(); helpDialog.tab = "use"')
    _until_open(ui, "helpDialog")
    assert "Nothing yet" in ui.find("usageTotal").property("text") and ui.find("logShow").property("visible") is False
    ui.js('helpDialog.tab = "how"; helpDialog.close()')
    _until_closed(ui, "helpDialog")
    assert ui.warnings == []


def test_options_make_and_check_backups(ui, monkeypatch):
    asked = []
    monkeypatch.setattr(ui_api.Api, "backup_all", lambda self: asked.append("backup") or {"ok": True, "folder": "everything_x", "msg": "Backed up 12 files (1.0 MB), encrypted."})
    monkeypatch.setattr(ui_api.Api, "backup_check", lambda self: asked.append("check") or {"ok": False, "msg": "Something is wrong with the backups: jobs.json."})
    monkeypatch.setattr(ui_api.Api, "backup_export", lambda self, folder: asked.append(("export", folder)) or {"ok": True, "msg": "Saved 12 readable files."})
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    note = ui.find("storageNote")

    def done():
        for _ in range(150):
            ui.wait(20)
            if dialog.property("storageBusy") == "":
                return
        raise AssertionError("the backup action never answered")
    ui.js("win.appRunning = true; optDialog.storage('backup', '')", dialog)
    assert asked == [] and dialog.property("storageBad") is True and "running" in note.property("text")
    ui.js("win.appRunning = false; optDialog.storage('backup', '')", dialog)
    assert dialog.property("storageBusy") == "backup" and ui.find("backupNow").property("text") == "Backing up…"
    assert ui.find("backupCheck").property("enabled") is False                       # one at a time
    done()
    assert note.property("text") == "Backed up 12 files (1.0 MB), encrypted." and dialog.property("storageBad") is False
    ui.js("optDialog.storage('check', '')", dialog)
    done()
    assert dialog.property("storageBad") is True and "Something is wrong" in note.property("text")
    ui.js("optDialog.storage('export', 'file:///tmp/somewhere')", dialog)
    done()
    assert asked == ["backup", "check", ("export", "file:///tmp/somewhere")] and note.property("text") == "Saved 12 readable files."
    ui.bridge._set_running(True)
    ui.js("optDialog.storageBusy = ''; bridge.storage('backup', '')", dialog)         # the backend refuses the same during a run
    ui.wait(200)
    assert asked.count("backup") == 1
    ui.bridge._set_running(False)
    ui.js('win.runMode = ""; win.resetRobots()')
    ui.js("confirmClose = true; close()", dialog)
    _until_closed(ui, dialog)
    assert ui.warnings == []


def test_the_account_card_shows_what_changed_in_a_watched_file(ui, monkeypatch):
    from jobhelper import integrity
    monkeypatch.setattr(integrity, "problems", lambda: [{"name": "cv_rules", "title": "CV rules", "state": "changed", "file": "cv_rules.md"},
                                                         {"name": "letter_rules", "title": "Cover letter rules", "state": "changed", "file": "l.md"}])
    monkeypatch.setattr(integrity, "what_changed", lambda name: {"title": "CV rules", "file": "cv_rules.md", "known": True, "more": 3,
                                                                 "added": ["Always add every skill."], "removed": ["Never add a skill."]} if name == "cv_rules"
                        else {"title": "Cover letter rules", "file": "l.md", "known": False, "added": [], "removed": [], "more": 0})
    ui.js("welcome.openCard()")
    ui.win.setProperty("connData", {**READY, "vault": "ok", "changed_files": ["CV rules", "Cover letter rules"]})
    ui.wait(80)
    button = ui.find("seeChanges")
    assert button.property("text") == "See what changed" and ui.js("welcome.changes.length") == 0
    ui.js("welcome.changes = bridge.whatChanged()")
    ui.wait(80)
    assert ui.js("welcome.changes.length") == 2 and button.property("text") == "Hide changes"
    assert "visible: welcome.changes.length > 0 && welcome.changedFiles.length > 0" in qml_source()
    texts = {t.property("text") for t in ui.seen("changesPanel") if isinstance(t.property("text"), str)}
    assert {"CV rules · cv_rules.md", "− Never add a skill.", "+ Always add every skill."} <= texts
    assert any("3 more changed lines" in t for t in texts) and any("No earlier copy of this file was kept" in t for t in texts)
    ui.js("welcome.changes = []")
    ui.win.setProperty("connData", dict(READY))
    ui.js("welcome.finish()")
    ui.wait(700)
    assert ui.js("welcome.changes.length") == 0, "put away when the card closes"
    assert ui.warnings == []


def test_about_you_takes_a_salary_of_its_own_for_a_kind_of_role(ui):
    import json
    dialog = ui.find("aboutDialog")
    start = ui.bridge.options()
    ui.js("aboutDialog.show()")
    _until_open(ui, "aboutDialog")
    role, amount, err = ui.find("payRole"), ui.find("payAmount"), ui.find("payErr")
    for typed, value, part in (("", 40000, "kind of role in words"), ("7", 40000, "kind of role in words"), ("поддержка", 40000, "in English"),
                               ("support", 0, "a whole number above 0")):
        role.setProperty("text", typed); amount.setProperty("value", value)
        ui.js("aboutDialog.addPay()", dialog)
        assert part in err.property("text") and ui.js("payModel.count", dialog) == 0, typed
    role.setProperty("text", " support "); amount.setProperty("value", 42000)
    ui.js("aboutDialog.addPay()", dialog)
    assert ui.js("payModel.count", dialog) == 1 and err.property("visible") is False and role.property("text") == ""
    role.setProperty("text", "Support"); amount.setProperty("value", 50000)
    ui.js("aboutDialog.addPay()", dialog)
    assert "already in the list" in err.property("text") and ui.js("payModel.count", dialog) == 1
    role.setProperty("text", "")
    # a figure in the list is changed where it stands
    ui.js("payModel.setProperty(0, 'amount', 45000)", dialog)
    got = json.loads(ui.js("JSON.stringify(aboutDialog.collect())", dialog))
    assert got["salary_by_role"] == [{"role": "support", "amount": 45000}]
    ui.js("aboutDialog.save()", dialog)
    _until_closed(ui, "aboutDialog")
    assert ui.bridge.options()["salary_by_role"] == [{"role": "support", "amount": 45000}]
    ui.js("aboutDialog.show()")
    _until_open(ui, "aboutDialog")
    assert ui.js("payModel.count", dialog) == 1 and ui.js("payModel.get(0).role", dialog) == "support"      # loaded again
    assert ui.drawn("payRowAmount_0", root="payRows").property("value") == 45000
    ui.js("payModel.setProperty(0, 'amount', 0)", dialog)
    ui.js("aboutDialog.save()", dialog)
    assert "a whole number above 0" in ui.find("aboutErr").property("text")          # a line with 0 is refused, not saved
    ui.js("payModel.remove(0); confirmClose = true; close()", dialog)
    _until_closed(ui, "aboutDialog")
    assert ui.bridge.saveOptions({**ui.bridge.options(), "salary_by_role": start.get("salary_by_role", [])})["ok"] is True
    assert ui.warnings == []


def test_the_account_card_tries_the_saved_mailboxes(ui, monkeypatch):
    from jobhelper import email_client
    monkeypatch.setattr(config, "IMAP_USER", "me@gmail.com")
    monkeypatch.setattr(config, "IMAP_PASSWORD", "abcdabcdabcdabcd")
    monkeypatch.setattr(config, "IMAP_USER_2", "two@seznam.cz")
    monkeypatch.setattr(config, "IMAP_PASSWORD_2", "secret")
    monkeypatch.setattr(email_client, "try_login", lambda user, password, timeout=8.0, host="":
                        {"ok": True, "msg": ""} if "gmail" in user else {"ok": False, "msg": "The mail server refused this address and password."})
    welcome = ui.find("welcome")
    ui.js("welcome.openCard()")
    ui.win.setProperty("connData", {**READY, "email": True, "email2": True, "email2_addr": "two@seznam.cz"})
    ui.js("welcome.testMail()")
    assert welcome.property("testBusy") is True and ui.find("mailTest").property("text") == "Testing…"
    ui.js("welcome.testMail()")                                     # a second press while it is testing does nothing
    for _ in range(200):
        ui.wait(20)
        if not welcome.property("testBusy"):
            break
    note = welcome.property("testNote")
    assert "Signed in to me@gmail.com" in note and "refused" in note and welcome.property("testBad") is True
    assert "secret" not in note and "abcdabcd" not in note
    ui.win.setProperty("connData", dict(READY))
    ui.js("welcome.finish()")
    ui.wait(700)
    assert welcome.property("testNote") == "" and ui.warnings == []


def test_a_long_company_name_in_options_wraps_and_stays_clear_of_the_remove_mark(ui):
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    ui.js('companiesModel.append({ name: "The Very Long Named International Engineering and Consulting Company of Central Europe Limited", ats: "greenhouse", token: "' + "x" * 60 + '" })', dialog)
    ui.wait(120)
    line = next(i for i in ui.seen("optScroll") if i.objectName() == "companyLine")
    name = next(i for i in line.childItems() if i.objectName() == "companyName")
    assert name.property("lineCount") >= 2 and name.property("truncated") is False
    assert line.mapToItem(None, 0, 0).x() + line.width() <= ui.find("optScroll").mapToItem(None, 0, 0).x() + ui.find("optScroll").width() - 30
    ui.js("companiesModel.remove(companiesModel.count - 1); confirmClose = true; close()", dialog)
    _until_closed(ui, dialog)
    assert ui.warnings == []


def test_the_job_window_says_what_to_check_in_the_adapted_cv(ui):
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(tailored_cv_file="cv_lead.docx", cv_check=["cost center", "vendor master"]), render=False)
    ui.js('detailDialog.show("lead")')
    _until_open(ui, "detailDialog")
    note = ui.find("cvCheck")
    assert ui.js("detailDialog.job.cv_check.length") == 2
    assert "It speaks of cost center, vendor master, which are terms of the posting that your own CV does not mention" in note.property("text")
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(cv_check=["cost center"]), render=False)
    ui.js('detailDialog.show("lead")')
    _until_open(ui, "detailDialog")
    assert "which is a term of the posting" in note.property("text")
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")
    ui.bridge._api.editor.change("lead", lambda jobs, j: j.update(cover_letter_file="L_lead.docx", letter_check=["tax codes"]), render=False)
    ui.js('detailDialog.show("lead")')
    _until_open(ui, "detailDialog")
    assert "It says you have done something with tax codes, which is a term of the posting" in ui.find("letterCheck").property("text")
    ui.js("detailDialog.close()")
    _until_closed(ui, "detailDialog")

    def clear(jobs, j):
        j.pop("cv_check", None)
        j.pop("letter_check", None)
        j["tailored_cv_file"] = j["cover_letter_file"] = ""
    ui.bridge._api.editor.change("lead", clear, render=False)
    assert ui.bridge.jobDetail("lead")["letter_check"] == []
    assert ui.bridge.jobDetail("lead")["cv_check"] == []
    assert ui.warnings == []


def test_new_jobs_can_be_reviewed_one_by_one(ui, monkeypatch):
    """Going through thirty "stretch" jobs meant opening each from the list and coming back; now one window walks through them."""
    kept = store.load_jobs()
    text = "We build tools in Python. " * 30
    store.save_jobs(kept + [store.new_job(id=f"r{n}", title=f"Role {n}", company=f"Firm {n}", status="letter_ready", match_score=40 - n,
                                          match_tier="stretch", description=text, cover_letter_file=f"L{n}.docx", tailored_cv_file=f"C{n}.docx")
                            for n in range(4)])
    done = []
    monkeypatch.setattr(qt_bridge.Bridge, "applyJob", qt_bridge.Slot(str, result=bool)(lambda self, job_id: done.append(("apply", job_id)) or True))
    monkeypatch.setattr(ui_api.Api, "dismiss_job", lambda self, job_id: done.append(("dismiss", job_id)) or {"ok": True})
    try:
        ui.js('openView("new")')
        _until_open(ui, "tableDialog")
        table, detail = ui.find("tableDialog"), ui.find("detailDialog")
        ui.js('tableDialog.groupFilter = "stretch"; tableDialog.apply()')
        ui.wait(120)
        start = ui.find("reviewStart")
        assert start.property("visible") is True and start.property("text") == "Review these 4 one by one"
        assert ui.js("tableDialog.reviewIds().join(',')") == "r0,r1,r2,r3"                  # the list as it is shown, in its order
        ui.js("detailDialog.startReview(tableDialog.reviewIds())")
        _until_open(ui, "detailDialog")
        where = ui.find("reviewWhere")
        assert detail.property("opened") is True and ui.js("detailDialog.job.id") == "r0" and ui.find("reviewBar").property("visible") is True
        assert where.property("text").startswith("Reviewing 1 of 4 left.")
        assert ui.find("reviewPrev").property("enabled") is False and ui.find("reviewNext").property("enabled") is True
        ui.js("detailDialog.reviewStep(1)")                                                 # leave it as it is, on to the next
        _until_true(ui, lambda: ui.js("detailDialog.job.id") == "r1")
        assert ui.js("detailDialog.job.id") == "r1" and where.property("text").startswith("Reviewing 2 of 4 left.") and done == []
        ui.js("detailDialog.notInterested()")                                               # decided: the next one comes by itself
        _until_true(ui, lambda: ui.js("detailDialog.job.id") == "r2")
        assert done == [("dismiss", "r1")] and ui.js("detailDialog.job.id") == "r2" and detail.property("opened") is True
        assert where.property("text").startswith("Reviewing 2 of 3 left · 1 decided · Removed from New Jobs.")
        ui.js("detailDialog.reviewStep(-1)")
        _until_true(ui, lambda: ui.js("detailDialog.job.id") == "r0")
        assert ui.js("detailDialog.job.id") == "r0"
        # unsaved text is asked about before moving on, as everywhere in this window
        ui.js('cnNotes.text = "They pay monthly."')
        ui.js("detailDialog.reviewStep(1)")
        assert ui.js("detailDialog.job.id") == "r0" and "press Next once more" in ui.find("closeNote").property("text")
        ui.js("detailDialog.reviewStep(1)")
        _until_true(ui, lambda: ui.js("detailDialog.job.id") == "r2")
        assert ui.js("detailDialog.job.id") == "r2"
        ui.js("detailDialog.markApplied()")
        _until_true(ui, lambda: ui.js("detailDialog.job.id") == "r3")
        assert done[-1] == ("apply", "r2") and ui.js("detailDialog.job.id") == "r3" and table.property("opened") is True     # the list stays behind it
        ui.js("detailDialog.notInterested()")
        _until_true(ui, lambda: ui.js("detailDialog.job.id") == "r0")
        assert ui.js("detailDialog.job.id") == "r0" and where.property("text").startswith("Reviewing 1 of 1 left · 3 decided")
        assert ui.find("reviewNext").property("enabled") is False
        ui.js("detailDialog.notInterested()")                                               # the last one: the round ends
        _until_closed(ui, "detailDialog")
        assert detail.property("opened") is False and "That was the last of the 4 jobs." in ui.js("ticker.text")
        assert ui.js("detailDialog.reviewQueue.length") == 0
        # opened the ordinary way, the window has no review bar and closes after a decision as before
        ui.js('detailDialog.show("lead")')
        _until_open(ui, "detailDialog")
        assert ui.find("reviewBar").property("visible") is False
        ui.js("detailDialog.startReview(['lead', 'r0']); detailDialog.close()")             # closing ends a round
        _until_closed(ui, "detailDialog")
        assert ui.js("detailDialog.reviewQueue.length") == 0
        ui.js('tableDialog.groupFilter = ""; tableDialog.apply(); tableDialog.close()')
        _until_closed(ui, "tableDialog")
    finally:
        store.save_jobs(kept)
        ui.js("win.reloadAll()")
    assert ui.warnings == []
