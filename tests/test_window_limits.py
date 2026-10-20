"""The window keeps no copy of a limit: it reads them from the back end, which checks the same numbers."""
import re
from pathlib import Path

from jobhelper import assistant, config, cover_letter, details, form_answers, housekeeping, mailhosts, planner, scrapers_ats
from jobhelper.api_options import OptionsService
from jobhelper.ui_api import Api

UI = Path(__file__).resolve().parent.parent / "ui_qt"


def test_the_limits_come_from_the_module_that_checks_them():
    limits = Api().limits()
    assert (limits["request"], limits["question"], limits["answer"]) == (assistant.MAX_REQUEST, form_answers.MAX_QUESTION, form_answers.MAX_ANSWER)
    assert limits["company_notes"] == planner.NOTE_LIMITS and limits["event_note"] == planner.MAX_EVENT_NOTE
    assert limits["experience_notes"] == config.MAX_EXPERIENCE_NOTES and limits["letter_hint"] == cover_letter.MAX_HINT
    assert limits["options"] == OptionsService.OPTION_TEXTS and limits["list_word"] == OptionsService.MAX_WORD
    assert (limits["company_name"], limits["pay_role"], limits["mail_server"]) == (OptionsService.MAX_COMPANY_NAME, OptionsService.MAX_PAY_ROLE, mailhosts.MAX_HOST)
    assert limits["numbers"] == {key: list(span) for key, span in OptionsService.OPTION_NUMBERS.items()}
    assert limits["shelf_days"] == [housekeeping.SHELF_MIN_DAYS, Api().SHELF_MAX_DAYS] and limits["look_back"] == list(config.LOOK_BACK_ONCE)



def test_the_choices_a_list_offers_are_the_ones_the_check_accepts():
    choices = Api().limits()["choices"]
    assert choices == {"event_kinds": list(planner.KINDS), "ats": list(scrapers_ats.ATS_NAMES),
                       "models": list(OptionsService.MODELS), "text_sizes": list(config.TEXT_SIZES)}


def test_no_dialog_keeps_its_own_copy_of_a_list_the_back_end_checks():
    copies = {"DetailDialog.qml": '"test task"', "OptionsDialog.qml": ('"smartrecruiters"', '"opus"', '"125%"', "[100, 110")}
    for name, words in copies.items():
        text = (UI / name).read_text(encoding="utf-8")
        for word in (words if isinstance(words, tuple) else (words,)):
            assert word not in text, (name, word)

def test_the_rows_of_my_details_come_with_their_data(isolate_data):
    columns = Api().my_details()["columns"]
    assert {name: tuple((c["key"], c["label"], c["most"]) for c in cols) for name, cols in columns.items()} == details.ROWS
    assert [c["key"] for c in columns["experience"] if c["long"]] == list(details.LONG)


def test_no_dialog_keeps_its_own_copy_of_a_checked_limit():
    """Fields whose length the back end checks take it from `win.limits` or from their data; search boxes may keep their own."""
    own = {("RemoteCountriesDialog.qml", 60), ("ResponseDialog.qml", 80), ("WelcomeOverlay.qml", 200)}   # search boxes; the recovery key
    found = {(f.name, int(n)) for f in UI.glob("*.qml") for n in re.findall(r"maximumLength: (\d+)", f.read_text(encoding="utf-8"))}
    assert found <= own, found - own
    for name, word in (("AssistantDialog.qml", "maxRequest: 300"), ("FormAnswersDialog.qml", "maxAnswer: 3000"),
                       ("DetailDialog.qml", "notesMax: 2000"), ("OptionsDialog.qml", "expMax: 4000"), ("LetterDialog.qml", "hintMax: 300"),
                       ("PrepEditDialog.qml", "maxLines: 12"), ("TagEditor.qml", "length > 40"), ("AssistantDialog.qml", "most: 2000")):
        assert word not in (UI / name).read_text(encoding="utf-8"), (name, word)


def test_no_number_box_keeps_its_own_range_and_every_limited_box_says_when_it_is_over():
    """A saved value above a box's own range was cut to fit when Options opened, and saved lower (max age 120 → 90)."""
    options = (UI / "OptionsDialog.qml").read_text(encoding="utf-8")
    spins = re.findall(r"ThemedSpin \{[^\n]*", options)
    assert len(spins) >= 10 and not [line for line in spins if re.search(r"from: \d+; to: \d+", line)], spins
    rows = (UI / "RowsEditor.qml").read_text(encoding="utf-8")
    assert rows.count("TooLong {") == 2, "a single-line cell says it is over, like the text area"
    assistant_qml = (UI / "AssistantDialog.qml").read_text(encoding="utf-8")
    assert assistant_qml.count("TooLong {") == 3 and "most: win.limits.question" in assistant_qml
    assert "characters; the most is" not in rows + assistant_qml, "in these two windows the sentence is TooLong's alone"


def test_the_limits_never_depend_on_the_data(isolate_data, monkeypatch):
    """The window binds to them at once; while the data was locked they came back as [] and every box threw."""
    from jobhelper import vault

    def locked(*a, **k):
        raise vault.VaultError("The key in the Keychain does not match this data.")
    monkeypatch.setattr(vault, "read_text", locked)
    monkeypatch.setattr(vault, "data_key", locked)
    limits = Api().limits()
    assert isinstance(limits, dict) and limits["numbers"]["scan_days"] and limits["look_back"]
