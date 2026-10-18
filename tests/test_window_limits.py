"""The window keeps no copy of a limit: it reads them from the back end, which checks the same numbers."""
import re
from pathlib import Path

from jobhelper import assistant, config, cover_letter, details, form_answers, mailhosts, planner
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
