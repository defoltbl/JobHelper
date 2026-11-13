"""The job list between threads of the window's process (#96). store.RunLock is held per process, so it never kept two
threads apart: a hand edit, a short worker and the run's worker each read the list, changed it and wrote it back, and
the later write put an older copy over the other's change. Each test forces one such order with real threads."""
import errno
import threading
import time
import types

import pytest

from jobhelper import api_core, bridge_runs, config, store, ui_api, weekly

T_OUT = 10.0      # the most a wait that must end may take; the right code never comes near it
NOT_NOW = 0.5     # how long a test waits to prove that another thread does NOT get in while a change is open


@pytest.fixture(autouse=True)
def _no_refusal_left_behind():
    """RunLock keeps the reason of a thread's last refusal: a test that ends refused must not hand it to the next test
    on this thread (one that stubs take() would show it instead of BUSY)."""
    yield
    store.RunLock._last.fault = ""


def _seed(*jobs):
    config.ensure_dirs()
    store.save_jobs([store.new_job(**job) for job in jobs])


def _saved():
    return {j["id"]: j for j in store.load_jobs()}


def _run(name, fn, results, done=None):
    """Start `fn` on a thread of its own; its result, or the error it raised, goes into `results`."""
    def body():
        try:
            results.append(fn())
        except BaseException as e:  # noqa: BLE001 - the test reads it
            results.append(e)
        finally:
            if done is not None:
                done.set()
    thread = threading.Thread(target=body, name=name, daemon=True)
    thread.start()
    return thread


def test_a_hand_edit_and_the_run_s_save_never_write_over_each_other(isolate_data):
    """Loss 1: the edit read the list, the run saved its copy with a new job, then the edit wrote the older copy over
    it. Now the run's save waits for the whole edit, and the edit reaches the run's copy too."""
    _seed({"id": "a", "title": "Tester", "company": "Acme"})
    editor = api_core.JobEditor()
    published, go_save, run_saved = threading.Event(), threading.Event(), threading.Event()

    def run():                                          # the search's worker: holds the claim, works on its own copy
        assert store.RunLock.take()
        try:
            with store.RunLock.holding():
                jobs = editor.live = store.load_jobs()
            jobs.append(store.new_job(id="new", title="Developer", company="Beta"))
            published.set()
            go_save.wait(T_OUT)
            store.save_jobs(jobs)
            run_saved.set()
        finally:
            editor.live = None
            store.RunLock.release()

    first = []

    def edit(jobs, j):
        j["notes"] = "Called back."
        if not first:                                   # the saved copy; the second call is the run's copy
            first.append(j)
            go_save.set()
            run_saved.wait(NOT_NOW)                     # the old code let the run save here

    results = []
    worker = _run("run", run, results)
    try:
        assert published.wait(T_OUT)
        assert editor.change("a", edit, render=False) == {"ok": True}
    finally:
        go_save.set()
        worker.join(T_OUT)
    assert not worker.is_alive() and results == [None]
    saved = _saved()
    assert "new" in saved, "the run's new job is still on the disk"
    assert saved["a"]["notes"] == "Called back."


def test_two_hand_edits_on_two_threads_both_reach_the_disk(isolate_data):
    """Loss 2: two threads each read the list and changed one job; the later write put the older copy over the other
    edit."""
    _seed({"id": "a", "title": "Tester", "company": "Acme"}, {"id": "b", "title": "Analyst", "company": "Beta"})
    editor = api_core.JobEditor()
    first_inside, second_done = threading.Event(), threading.Event()

    def first(jobs, j):
        j["notes"] = "First."
        first_inside.set()
        second_done.wait(NOT_NOW)                       # the old code let the second edit read, change and write here

    def second(jobs, j):
        j["notes"] = "Second."

    results = []
    one = _run("edit 1", lambda: editor.change("a", first, render=False), results)
    try:
        assert first_inside.wait(T_OUT)
        two = _run("edit 2", lambda: editor.change("b", second, render=False), results, done=second_done)
    finally:
        one.join(T_OUT)
    two.join(T_OUT)
    assert not one.is_alive() and not two.is_alive() and results == [{"ok": True}, {"ok": True}]
    saved = _saved()
    assert (saved["a"]["notes"], saved["b"]["notes"]) == ("First.", "Second.")


def test_a_run_holding_the_list_never_makes_a_hand_edit_wait(isolate_data):
    """A run holds the process's claim for minutes, never the section of one change: an edit goes on at once."""
    _seed({"id": "a", "title": "Tester", "company": "Acme"})
    editor = api_core.JobEditor()
    claimed, run_over = threading.Event(), threading.Event()

    def run():
        assert store.RunLock.take()
        claimed.set()
        try:
            run_over.wait(T_OUT)                        # the run works on
        finally:
            store.RunLock.release()

    results = []
    worker = _run("run", run, results)
    try:
        assert claimed.wait(T_OUT)
        edit = _run("edit", lambda: editor.change("a", lambda jobs, j: j.__setitem__("notes", "Done."), render=False),
                    results)
        edit.join(T_OUT)
        assert not edit.is_alive(), "the edit waited for the run"
        assert results == [{"ok": True}] and _saved()["a"]["notes"] == "Done." and store.RunLock._held == 1
    finally:
        run_over.set()
        worker.join(T_OUT)
    assert not worker.is_alive() and results == [{"ok": True}, None] and store.RunLock._held == 0


def test_a_hand_edit_made_while_the_run_reads_the_list_reaches_the_run_s_copy(qapp, isolate_data, monkeypatch):
    """Loss 3: the run's worker read the list, an edit was saved before the run published its copy as `live`, so the
    edit never reached that copy and the run's next save dropped it. Goes through the real worker (score again)."""
    from jobhelper import agent1_cv, agent3_letters, agent4_tracker, qt_bridge
    _seed({"id": "a", "title": "Tester", "company": "Acme", "match_score": 80, "description": "x"})
    monkeypatch.setattr(agent1_cv, "load_profile", lambda current_only=False: {})
    monkeypatch.setattr(agent4_tracker, "render_all", lambda jobs: None)

    def rescore(jobs, ids, *args, **kwargs):            # the run's own result, with no Claude call
        store.find(jobs, "a")["match_score"] = 55
        return {"changed": [], "scored": 1, "failed": 0}
    monkeypatch.setattr(agent3_letters, "rescore", rescore)
    read, edited = threading.Event(), threading.Event()
    real_load = store.load_jobs

    def load_jobs():
        jobs = real_load()
        if threading.current_thread().name == "run":
            read.set()
            edited.wait(NOT_NOW)                        # the old code let the edit reach the disk here, before `live`
        return jobs
    monkeypatch.setattr(store, "load_jobs", load_jobs)
    bridge = qt_bridge.Bridge()

    results = []
    worker = _run("run", bridge._rescore, results)
    try:
        assert read.wait(T_OUT)
        assert bridge._api.editor.change("a", lambda jobs, j: j.__setitem__("notes", "Called back."),
                                         render=False) == {"ok": True}
    finally:
        edited.set()
        worker.join(T_OUT)
    assert not worker.is_alive() and results == [None] and bridge._api.live is None
    saved = _saved()["a"]
    assert (saved["notes"], saved["match_score"]) == ("Called back.", 55)


def test_many_hand_edits_on_many_threads_lose_none(isolate_data):
    """A bounded stress: 4 threads make 25 edits each on the same job; every one of them is on the disk."""
    _seed({"id": "a", "title": "Tester", "company": "Acme"})
    editor = api_core.JobEditor()
    start = threading.Barrier(4)

    def add_one(jobs, j):
        j["notes"] = (j.get("notes") or "") + "x"

    def edits():
        start.wait(T_OUT)
        return [editor.change("a", add_one, render=False)["ok"] for _ in range(25)]

    results = []
    threads = [_run("edit %d" % n, edits, results) for n in range(4)]
    for thread in threads:
        thread.join(T_OUT * 3)
    assert not any(t.is_alive() for t in threads) and results == [[True] * 25] * 4
    assert len(_saved()["a"]["notes"]) == 100


def test_a_lock_file_that_cannot_be_opened_is_refused_with_its_reason(isolate_data, monkeypatch, capsys):
    """An error from opening the lock file (no right to it, a read-only disk) escaped take() and every save. Now it is
    refused at once: the lock is not held, nothing is written, and the person reads why – not that a run is busy."""
    _seed({"id": "a", "title": "Tester", "company": "Acme"})
    before = store.load_jobs()

    def no_right(*args, **kwargs):
        raise PermissionError(errno.EACCES, "Permission denied")

    with monkeypatch.context() as patch:
        patch.setattr(store.os, "open", no_right)
        start = time.monotonic()
        assert store.RunLock.take(5.0) is False                 # waiting does not mend a file's rights
        assert time.monotonic() - start < 2.0
        assert store.RunLock._held == 0 and store.RunLock._file is None
        said = store.RunLock.fault()
        assert "Permission denied" in said and ".jobs.lock" in said and said != store.RunLock.BUSY
        with pytest.raises(store.JobsBusy, match="Permission denied"):
            store.save_jobs([])
        refused = api_core.JobEditor().change("a", lambda jobs, j: j.__setitem__("notes", "x"))
        assert refused == {"ok": False, "msg": said}
        assert store.RunLock.command(lambda: 0) == 1
        assert capsys.readouterr().out.strip() == "✗ " + said
        assert store.RunLock.refusal() == said
        run = types.SimpleNamespace(_holds_jobs=False)
        assert bridge_runs.RunSlots._claim_jobs(run) == {"ok": False, "msg": said} and run._holds_jobs is False
        log = config.DATA_DIR / "weekly_test.log"
        assert weekly.WeeklyRun(log, steps=[], wait=5.0).run() == weekly.WeeklyRun.BUSY_CODE
        assert "Permission denied" in log.read_text() and "working on your jobs" not in log.read_text()
    assert store.load_jobs() == before and store.RunLock._held == 0
    assert store.RunLock.take() is True and store.RunLock.fault() == ""      # the next try carries no old reason
    store.RunLock.release()


def test_a_link_in_place_of_the_lock_file_is_refused_and_never_followed(isolate_data):
    config.ensure_dirs()
    target = isolate_data / "somewhere_else"
    store.RunLock.path().symlink_to(target)
    assert store.RunLock.take() is False and store.RunLock._held == 0 and store.RunLock._file is None
    assert not target.exists(), "nothing was made through the link"
    with pytest.raises(store.JobsBusy, match="cannot be opened"):
        store.save_jobs([])
    assert not config.JOBS_JSON.exists()


def test_taking_back_a_letter_never_makes_another_edit_wait_for_its_pdf(isolate_data, monkeypatch):
    """#96: Undo held the job list's section through every step, and a letter's step makes a PDF (up to two minutes in
    LibreOffice). A hand edit on another thread then waited the whole time: the window froze."""
    _seed({"id": "a", "title": "Tester", "company": "Acme"})
    api = ui_api.Api()
    in_pdf, finish = threading.Event(), threading.Event()

    def slow_save(self, job_id, paragraphs):
        in_pdf.set()
        assert finish.wait(T_OUT), "the test never let the letter finish"
        return {"ok": True}
    monkeypatch.setattr(ui_api.Api, "save_letter", slow_save)
    api._talk._undo = [{"kind": "letter", "id": "a", "paragraphs": ["x"], "what": "The letter for Acme"}]
    undone = []
    undo = _run("undo", api.assistant_undo, undone)
    assert in_pdf.wait(T_OUT)
    edited = []
    edit = _run("edit", lambda: api_core.JobEditor().change("a", lambda jobs, j: j.__setitem__("notes", "kept")), edited)
    edit.join(T_OUT)
    try:
        assert not edit.is_alive() and edited == [{"ok": True}], "the edit waited for the letter's PDF"
    finally:
        finish.set()
        undo.join(T_OUT)
    assert undone[0]["ok"] and "as it was before" in undone[0]["say"]
    assert _saved()["a"]["notes"] == "kept" and store.RunLock._held == 0


def test_a_run_that_starts_during_undo_keeps_what_undo_took_back_off_the_list(isolate_data, monkeypatch):
    """#96: Undo holds only the claim, so a search can start while a letter's step makes its PDF. A later step then took
    an added posting off the disk alone; the run's copy wrote it back, and Undo said it was as it was before."""
    _seed({"id": "a", "title": "Tester", "company": "Acme"},
          {"id": "added-1", "title": "Analyst", "company": "Fabrikam", "status": "found", "url": "https://jobs.example/1"})
    api = ui_api.Api()

    def run_starts_meanwhile(self, job_id, paragraphs):
        with store.RunLock.holding():               # what the run's worker does when it starts
            api.live = store.load_jobs()
        return {"ok": True}
    monkeypatch.setattr(ui_api.Api, "save_letter", run_starts_meanwhile)
    api._talk._undo = [{"kind": "added", "id": "added-1", "what": "Analyst at Fabrikam"},
                       {"kind": "letter", "id": "a", "paragraphs": ["x"], "what": "The letter for Acme"}]
    said = api.assistant_undo()["say"]
    assert "Analyst at Fabrikam could not be put back" in said and "The letter for Acme is as it was before" in said
    assert "added-1" in _saved() and store.find(api.live, "added-1"), "disk and the run's copy still agree"


def test_a_posting_is_not_added_while_a_run_works_on_its_own_copy(isolate_data):
    """#96: the assistant's Add wrote the disk list while a run that had started meanwhile held its own copy."""
    _seed({"id": "a", "title": "Tester", "company": "Acme"})
    api = ui_api.Api()
    api.live = store.load_jobs()
    record = {"title": "Data Analyst", "company": "Fabrikam", "url": "https://jobs.example/9", "match_score": 70}
    ok, msg, _ = api._talk._add_job(record)
    assert ok is False and "is running" in msg and list(_saved()) == ["a"]
