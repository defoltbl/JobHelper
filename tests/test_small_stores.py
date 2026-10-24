"""The small stores (assistant notes, remembered answers, company notes, usage) each are one object over one file."""
import json

import pytest

from jobhelper import answer_memory, assistant_notes, planner, ui_api, usage, vault


def test_a_json_file_reads_what_was_written_and_keeps_it_encrypted(isolate_data):
    kept = vault.JsonFile("kept.json")
    assert kept.path == isolate_data / "kept.json" and kept.read() is None          # no file yet
    kept.write({"name": "Ondra Kovář", "items": [1, 2]})
    assert kept.read() == {"name": "Ondra Kovář", "items": [1, 2]}
    assert vault.is_encrypted(kept.path.read_bytes())
    kept.path.write_text("{ broken")
    assert kept.read() is None                                                     # damaged: read as nothing


def test_a_damaged_encrypted_file_is_not_read_as_empty(isolate_data, monkeypatch):
    planner.save_company_notes("Brightline", {"contact": "Mia, HR"})
    before = (isolate_data / "company_notes.json").read_bytes()

    def damaged(blob):
        raise vault.VaultError("An encrypted file is damaged or was written with a different key.")
    monkeypatch.setattr(vault, "decrypt", damaged)
    assert planner.company_notes("Brightline")["contact"] == ""                    # a job's details still open
    with pytest.raises(vault.VaultError):          # before: read as no notes, and the save wrote over every company's notes
        planner.save_company_notes("Fernhill", {"contact": "Tom"})
    out = ui_api.Api().save_company_notes("Fernhill", {"contact": "Tom"})
    assert out == {"ok": False, "msg": planner.CompanyNotes.UNREADABLE}            # a red line in the window, not a crash
    assert (isolate_data / "company_notes.json").read_bytes() == before


def test_each_store_works_on_the_file_it_is_given(isolate_data):
    notes = assistant_notes.AssistantNotes(vault.JsonFile("other_notes.json"))
    memory = answer_memory.AnswerMemory(vault.JsonFile("other_answers.json"))
    companies = planner.CompanyNotes(vault.JsonFile("other_companies.json"))
    assert notes.remember("No agencies")["ok"] and notes.notes()[0]["text"] == "No agencies"
    assert memory.remember("Why do you want this job?", "I like the product.") and memory.count() == 1
    assert companies.save("Brightline", {"salary": "60k"}) and companies.of("BRIGHTLINE")["salary"] == "60k"
    assert {p.name for p in isolate_data.glob("*.json")} == {"vault.json", "other_notes.json", "other_answers.json", "other_companies.json"}
    assert assistant_notes.notes() == [] and answer_memory.count() == 0 and planner.company_notes("Brightline")["salary"] == ""


def test_the_module_functions_use_the_one_store_of_each_kind(isolate_data):
    assert assistant_notes.path() == assistant_notes.NOTES.path == isolate_data / "assistant_notes.json"
    assert answer_memory.path() == answer_memory.MEMORY.path == isolate_data / "answer_memory.json"
    assert planner.COMPANY_NOTES.path == isolate_data / "company_notes.json"
    assert {assistant_notes.path(), answer_memory.path(), planner.COMPANY_NOTES.path} <= set(vault.data_files())


def test_the_usage_log_tells_its_sums_and_keeps_this_run_apart(isolate_data):
    log, app_run = usage.UsageLog(), usage.session()["calls"]
    log.record({"input_tokens": 10, "output_tokens": 2, "cost_usd": 0.25}, tag="assistant")
    log.record({"input_tokens": 5, "cost_usd": "a lot"}, tag="assistant")
    assert log.totals()["calls"] == 2 and log.totals()["input_tokens"] == 15 and log.total_cost() == 0.25
    assert log.by_tag()["assistant"]["calls"] == 2
    assert log.session()["calls"] == 2 and usage.session()["calls"] == app_run    # each log counts only its own run
    assert usage.totals()["calls"] == 2                                            # the saved sums are one file
    log.session()["calls"] = 99
    assert log.session()["calls"] == 2                                             # a copy, not its own counters
    log.reset()
    assert log.session()["calls"] == 0 and json.loads(usage.LOG.path.read_text(encoding="utf-8"))["totals"]["calls"] == 0


@pytest.mark.parametrize("change", ["answer", "note", "turns", "details", "company", "forget", "forget_all", "forget_note"])
def test_a_change_never_writes_over_a_damaged_store(isolate_data, change):
    """A damaged file was read as empty, and the next save wrote the empty store over it; it is moved aside first now."""
    from jobhelper import config, details
    files = {"answer": answer_memory.MEMORY.path, "note": assistant_notes.NOTES.path, "turns": assistant_notes.NOTES.path,
             "details": config.MY_DETAILS.path, "company": planner.COMPANY_NOTES.path, "forget": answer_memory.MEMORY.path,
             "forget_all": answer_memory.MEMORY.path, "forget_note": assistant_notes.NOTES.path}
    path = files[change]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ damaged")
    if change == "answer":
        assert answer_memory.remember("Why do you want this job?", "I like the product.")
    elif change == "note":
        assert assistant_notes.NOTES.remember("No agencies")["ok"]
    elif change == "turns":
        assistant_notes.NOTES.keep_turns([("you", "hi")])
    elif change == "company":
        assert planner.save_company_notes("Fernhill", {"contact": "Tom"})
    elif change == "forget":
        answer_memory.forget("Why do you want this job?")
    elif change == "forget_all":
        answer_memory.forget_all()
    elif change == "forget_note":
        assistant_notes.NOTES.forget(1)
    else:
        assert details.save({**details.empty(), "first_name": "Ondra", "last_name": "Kovář", "email": "ondra@example.com"})["ok"]
    kept = list((vault.backups_dir() / vault.DAMAGED).iterdir())
    assert len(kept) == 1 and kept[0].read_text() == "{ damaged", "the damaged file is kept, never written over"


def test_an_answer_that_cannot_be_kept_leaves_the_old_one(isolate_data, monkeypatch):
    api = ui_api.Api()
    assert api.save_my_answer("Why do you want this job?", "I like the product.")["ok"]
    monkeypatch.setattr(answer_memory, "remember", lambda *a, **k: False)
    assert api.save_my_answer("Why this job?", "Because.", was="Why do you want this job?")["ok"] is False
    assert answer_memory.recall("Why do you want this job?")["answer"] == "I like the product.", "removed before the new one was kept"


def test_renaming_an_answer_in_a_full_store_drops_no_other_answer(isolate_data):
    """With the store full, the new wording made room by dropping the oldest answer, then the old wording went too."""
    for i in range(answer_memory.MAX_ENTRIES):
        assert answer_memory.remember(f"Question number {i} about the role?", f"Answer {i}.")
    assert ui_api.Api().save_my_answer("Question five, asked again?", "Answer 5.", was="Question number 5 about the role?")["ok"]
    assert answer_memory.MEMORY.count() == answer_memory.MAX_ENTRIES
    assert answer_memory.recall("Question number 0 about the role?")["answer"] == "Answer 0.", "the oldest answer is still kept"
    assert answer_memory.recall("Question number 5 about the role?") is None
