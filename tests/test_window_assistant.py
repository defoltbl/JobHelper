"""The window, loaded offscreen: the assistant.

Its tests share one window and follow on from each other, so they run on one worker in this order (see
tests/window_harness.py). The other window test files run beside it, each with a window of its own."""
import os
import re

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.xdist_group("test_window_assistant")

from PySide6.QtCore import QMetaObject, QPointF  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from jobhelper import config, qt_bridge, store, ui_api  # noqa: E402
from tests.conftest import ROOT  # noqa: E402
from tests.window_harness import (_listed, _open, _open_job, _until_closed, _until_open, _until_settled, _until_shown, _until_true, _wait_idle)  # noqa: E402


# ── the assistant ───────────────────────────────────────────────────────────
def test_the_assistant_stands_on_the_line_blinks_and_waves(ui):
    bot = ui.find("assistantBot")
    assert bot.property("visible") and bot.property("x") + bot.property("width") <= 1000 and bot.property("y") + bot.property("height") <= 560
    for robot in ("a4", "a5"):                                  # it does not stand on a station of the line
        other = ui.find(robot)
        assert bot.property("x") > other.property("x") + 130
    lids = []
    for _ in range(90):                                         # the eyes close and open by themselves
        lids.append(bot.property("lid"))
        ui.wait(40)
        if max(lids) > 0.6 and lids[-1] < 0.2:
            break
    assert max(lids) > 0.6 and lids[-1] < 0.2, "it blinked"
    arm, bubble = ui.drawn("assistantArm", "stagePanel"), ui.drawn("assistantBubble", "stagePanel")
    bot.setProperty("greeting", False)                          # it may still be telling the morning's briefing
    _until_true(ui, lambda: arm.property("rotation") > -40 and bubble.property("opacity") == 0)
    assert arm.property("rotation") > -40 and bubble.property("opacity") == 0
    ui.js("stagePanel.assistant.greet()")
    _until_true(ui, lambda: arm.property("rotation") < -100 and bubble.property("opacity") == 1)
    assert bot.property("greeting") and arm.property("rotation") < -100, "the arm is up, waving"
    assert bubble.property("opacity") == 1 and bot.property("says").startswith("Hi!")
    assert bubble.mapToItem(bot.parentItem(), 0, 0).x() >= 0, "the bubble stays on the floor"
    floor = bot.parentItem()
    for words in ("", "The interview for Junior Backend Developer at Brightline Works is in two days and there is no preparation yet. " * 2):
        ui.js("stagePanel.assistant.tell(" + repr(words) + ")")
        ui.wait(450)
        top, left = bubble.mapToItem(floor, 0, 0).y(), bubble.mapToItem(floor, 0, 0).x()
        assert top >= 452 and left >= 0 and top + bubble.property("height") <= 560, \
            "what it says lies under the line (the line ends at y 450) and on the floor, however long it is"
        for name in ("a4", "a5"):
            other = ui.find(name)
            assert top >= other.property("y") + 100, "and never over a robot"
    ui.js("stagePanel.assistant.greet()")
    _until_true(ui, lambda: ui.js("stagePanel.assistant.parent.scale") > 0 and bubble.property("opacity") == 1
                and bot.property("shown").startswith("Hi!"))
    # the bubble grows to its words after it shows: wait for its own target, not for a pause in the animation (a slow
    # machine, as the CI runner, can pause between frames and look settled at 195 of 420)
    _until_true(ui, lambda: bubble.property("width") == bubble.property("target"))
    assert floor.property("height") == 560 and ui.js("stagePanel.assistant.parent.scale") > 0
    wide = bubble.property("width")
    bot.setProperty("greeting", False)
    sizes = []
    for _ in range(12):                                         # on its way out the bubble keeps its words and its size
        sizes.append((bot.property("shown"), bubble.property("width")))
        ui.wait(20)
    assert set(sizes) == {("Hi! Tap me to fill in a form.", wide)}, "it used to switch to the other text and jump while fading"
    _until_true(ui, lambda: arm.property("rotation") > -40 and bubble.property("opacity") == 0)
    assert arm.property("rotation") > -40 and bubble.property("opacity") == 0
    bot.setProperty("hovered", True)
    _until_true(ui, lambda: bubble.property("opacity") == 1 and bot.property("shown") == "Assistant · tap to ask")
    assert bot.property("shown") == "Assistant · tap to ask" and bubble.property("opacity") == 1
    bot.setProperty("hovered", False)
    _until_true(ui, lambda: bubble.property("opacity") == 0)
    assert ui.warnings == []


def test_the_assistant_asks_for_your_details_first_and_checks_them(ui):
    from jobhelper import details
    dialog = ui.find("assistantDialog")
    ui.js('stagePanel.assistant.tapped()')
    _until_open(ui, "assistantDialog")
    assert dialog.property("opened") and dialog.property("page") == "details", "nothing is saved yet: the details come first"
    assert ui.js("fieldModel.count") == len(details.KEYS) and ui.js("talk.count") == 1
    ui.js("assistantDialog.saveDetails()")
    assert "Every field is empty" in ui.find("asDetailsNote").property("text") and not details.path().exists()
    ui.js('assistantDialog.setField("first_name", "Alex"); assistantDialog.setField("last_name", "Novak"); assistantDialog.setField("email", "alex@example")')
    assert dialog.property("dirty") and ui.js("assistantDialog.problem.field") == "email"
    assert "email address" in ui.js('assistantDialog.faultAt("email")') and ui.find("asDetailsNote").property("text") == \
        "1 field needs a change: see the red lines above.", "said once, under its field (hands-on F11)"
    ui.js('assistantDialog.setField("phone", "call me")')
    assert ui.find("asDetailsNote").property("text").startswith("2 fields need a change") and "digits" in ui.js('assistantDialog.faultAt("phone")')
    ui.js('assistantDialog.setField("phone", "")')
    ui.js("assistantDialog.saveDetails()")
    assert not details.path().exists(), "a wrong field is not saved"
    ui.js("assistantDialog.tryClose()")
    assert dialog.property("opened") and "did not save" in ui.find("asDetailsNote").property("text"), "closing with unsaved changes asks once"
    ui.js('assistantDialog.setField("email", "alex@example.com"); assistantDialog.setField("linkedin", "linkedin.com/in/alexnovak")')
    assert ui.js("!assistantDialog.problem.msg")
    ui.js("assistantDialog.saveDetails()")
    assert details.load()["email"] == "alex@example.com" and details.load()["linkedin"] == "https://linkedin.com/in/alexnovak"
    assert not dialog.property("dirty") and dialog.property("detailsSaved") and "Saved" in ui.find("asDetailsNote").property("text")
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, dialog)
    assert dialog.property("visible") is False and ui.warnings == []


def test_the_assistant_takes_a_request_and_shows_what_it_filled(ui, monkeypatch):
    import threading
    dialog, gate, asked = ui.find("assistantDialog"), threading.Event(), []

    def answer(self, text, job_id=""):
        asked.append((text, job_id))
        gate.wait(5)
        return {"ok": True, "action": "fill", "host": "careers.northwind.example", "job_id": "lead", "job": "Junior Python Developer at Acme", "guessed": True,
                "filled": [{"label": "First name", "value": "Alex", "kind": "detail", "check": ""},
                           {"label": "When can you start?", "value": "I can start on [your start date].", "kind": "answer", "check": "Your start date"}],
                "left": [{"label": "Resume/CV", "why": "Attach the file yourself: a page cannot be handed a file from outside."}],
                "kept": 0, "boxes": 1, "say": "I filled in 2 fields on careers.northwind.example. I never press Submit."}
    monkeypatch.setattr(ui_api.Api, "assistant_ask", answer)
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    assert dialog.property("page") == "ask", "details are saved: it opens ready to be asked"
    assert [j["id"] for j in dialog.property("jobs").toVariant()] == ["", "lead", "app"]
    before = ui.js("talk.count")
    ui.js('assistantDialog.ask("   ")')
    assert "Write what you need" in ui.find("asErr").property("text") and ui.js("talk.count") == before and asked == []
    ui.js('assistantDialog.ask("' + "x" * 301 + '")')
    assert "longer than 300" in ui.find("asErr").property("text") and asked == []
    ui.js('assistantDialog.forJob("app")')
    ui.js('assistantDialog.ask("fill the form in chrome")')
    assert dialog.property("busy") and ui.find("assistantBot").property("busy") and ui.find("asFill").property("enabled") is False
    ui.js('assistantDialog.ask("again")')
    assert "still working" in ui.find("asErr").property("text")
    ui.js("assistantDialog.tryClose()")
    assert dialog.property("opened"), "it is not closed in the middle of a request"
    gate.set()
    for _ in range(100):
        if not dialog.property("busy"):
            break
        ui.wait(30)
    assert asked == [("fill the form in chrome", "app")]
    assert ui.js("talk.count") == before + 2 and ui.js("talk.get(talk.count - 1).text").startswith("I filled in 2 fields")
    assert ui.js("filledModel.count") == 2 and ui.js("filledModel.get(1).check") == "Your start date" and ui.js("leftModel.get(0).label") == "Resume/CV"
    monkeypatch.setattr(ui_api.Api, "assistant_ask", lambda self, text, job_id="": {"ok": False, "action": "fill", "msg": "Google Chrome is not open."})
    ui.js("assistantDialog.ask(\"fill it\")")
    for _ in range(100):
        if not dialog.property("busy"):
            break
        ui.wait(30)
    assert ui.js("talk.get(talk.count - 1).bad") is True and ui.js("talk.get(talk.count - 1).text") == "Google Chrome is not open."
    assert ui.js("filledModel.count") == 0, "an old report does not stay under a new answer"
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, dialog)
    assert dialog.property("visible") is False and ui.warnings == []


def test_the_assistant_looks_at_the_pointer_nods_and_shakes_its_head(ui):
    bot = ui.find("assistantBot")
    eyes, head = ui.drawn("assistantEyes", "stagePanel"), ui.drawn("assistantHead", "stagePanel")
    rest_x, rest_y = eyes.property("x"), head.property("y")
    ui.js("stagePanel.assistant.lookAt(100, 100)")                # far to the left and above
    _until_true(ui, lambda: bot.property("lookX") == -1 and bot.property("lookY") == -1 and eyes.property("x") < rest_x - 3)
    assert bot.property("lookX") == -1 and bot.property("lookY") == -1 and eyes.property("x") < rest_x - 3
    ui.js("stagePanel.assistant.lookAt(stagePanel.assistant.x + 60, stagePanel.assistant.y + 36)")
    _until_true(ui, lambda: 0 < bot.property("lookX") < 0.3)
    assert 0 < bot.property("lookX") < 0.3, "a pointer close by moves the eyes a little"
    ui.js("stagePanel.assistant.lookAhead()")
    _until_true(ui, lambda: bot.property("lookX") == 0 and abs(eyes.property("x") - rest_x) < 0.01)
    assert bot.property("lookX") == 0 and abs(eyes.property("x") - rest_x) < 0.01
    for move, part, name in (("nod", "y", "nodBy"), ("shake", "x", "shakeBy")):
        start = head.property(part)
        ui.js(f"stagePanel.assistant.{move}()")
        seen = []
        for _ in range(40):
            seen.append(head.property(part) - start)
            ui.wait(20)
        assert max(abs(s) for s in seen) > 3, f"the head moved ({move})"
        assert bot.property(name) == 0 and abs(head.property(part) - start) < 0.01, "and came back"
    assert head.property("y") == rest_y and ui.warnings == []


def test_after_a_fill_the_assistant_offers_what_applies(ui, monkeypatch):
    dialog, did = ui.find("assistantDialog"), []
    fill = {"ok": True, "action": "fill", "host": "careers.acme.example", "url": "https://careers.acme.example/apply", "job_id": "lead",
            "job": "Junior Python Developer at Acme", "guessed": False, "kept": 0, "boxes": 0, "say": "I filled in 1 field.",
            "filled": [{"label": "Why Acme?", "value": "Because.", "kind": "answer", "check": ""}],
            "left": [{"label": "Resume/CV", "why": "Attach the file yourself: a page cannot be handed a file from outside."}],
            "wants_file": True, "has_files": True, "is_lead": True, "can_learn": True}
    monkeypatch.setattr(ui_api.Api, "assistant_ask", lambda self, text, job_id="": dict(fill))
    monkeypatch.setattr(ui_api.Api, "assistant_watch", lambda self: {"ok": False, "url": "", "sign": "", "empty": 0})
    monkeypatch.setattr(ui_api.Api, "assistant_files", lambda self, job_id: did.append(("files", job_id)) or {"ok": True, "say": "Shown in Finder: CV."})
    monkeypatch.setattr(ui_api.Api, "assistant_learn", lambda self: did.append(("learn",)) or {"ok": True, "learned": 1, "say": "I will use your wording for 1 question."})
    monkeypatch.setattr(ui_api.Api, "assistant_memory", lambda self: {"count": len([d for d in did if d[0] == "learn"])})
    monkeypatch.setattr(ui_api.Api, "assistant_forget", lambda self: did.append(("forget",)) or {"ok": True, "say": "Forgotten: 1 remembered answers."})
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    assert not ui.find("asNext").property("visible"), "nothing is offered before anything was done"
    ui.js('assistantDialog.ask("fill the form")')
    _wait_idle(ui, dialog)
    assert all(dialog.property(name) for name in ("canShowFiles", "canLearn", "canApply")) and not dialog.property("canOpenForm")
    assert ui.find("asNext").property("visible") and ui.find("asFiles").property("visible") and not ui.find("asOpenForm").property("visible")
    ui.js('assistantDialog.act("files", "", "Show my CV and letter in Finder")')
    _wait_idle(ui, dialog)
    ui.js('assistantDialog.act("learn", "", "Remember what I changed on the page")')
    _wait_idle(ui, dialog)
    assert did == [("files", "lead"), ("learn",)] and dialog.property("remembered") == 1
    assert ui.js("talk.get(talk.count - 1).text") == "I will use your wording for 1 question."
    # the form moves on to its next page
    assert dialog.property("watchSign") == "pending" and not dialog.property("nextPage")
    ui.bridge.formWatched.emit({"ok": True, "url": "https://careers.acme.example/apply", "sign": "4:a|b", "empty": 2})
    ui.bridge.formWatched.emit({"ok": True, "url": "https://careers.acme.example/apply", "sign": "4:a|b", "empty": 1})
    ui.wait(100)
    assert not dialog.property("nextPage"), "the same fields: the same page"
    ui.bridge.formWatched.emit({"ok": True, "url": "https://careers.acme.example/apply", "sign": "3:c|d", "empty": 0})
    assert not dialog.property("nextPage"), "other fields, but nothing empty to fill"
    ui.bridge.formWatched.emit({"ok": False, "url": "", "sign": "", "empty": 0})
    ui.bridge.formWatched.emit({"ok": True, "url": "https://careers.acme.example/apply", "sign": "3:c|d", "empty": 3})
    ui.wait(100)
    assert dialog.property("nextPage") and ui.find("asNextPage").property("visible")
    assert "other fields now" in ui.js("talk.get(talk.count - 1).text")
    # mark applied, from here
    assert store.find(store.load_jobs(), "lead")["status"] in store.LEAD_STATUSES
    ui.js("assistantDialog.markApplied()")
    _until_true(ui, lambda: store.find(store.load_jobs(), "lead")["status"] == "waiting")
    assert store.find(store.load_jobs(), "lead")["status"] == "waiting" and not dialog.property("canApply")
    assert "Moved Junior Python Developer at Acme to Applications" in ui.js("talk.get(talk.count - 1).text")
    # the memory can be emptied, after asking once
    ui.js('assistantDialog.page = "details"')
    ui.wait(100)
    assert "1 answer of your own is remembered" in ui.find("asMemory").property("text")
    ui.js("assistantDialog.forget()")
    assert dialog.property("confirmForget") and "once more" in ui.find("asMemory").property("text") and ("forget",) not in did
    ui.js("assistantDialog.forget()")
    _wait_idle(ui, dialog)
    assert did[-1] == ("forget",) and ui.js("talk.get(talk.count - 1).text").startswith("Forgotten")
    # a form in a frame: the button opens it; a failure makes the robot shake its head
    opened = []
    monkeypatch.setattr(ui_api.Api, "assistant_ask", lambda self, text, job_id="": {
        "ok": False, "action": "fill", "msg": "The form on this page sits inside a frame.", "frame": "https://boards.example.net/embed?id=7"})
    monkeypatch.setattr(ui_api.Api, "assistant_open_form", lambda self, url, job_id="": opened.append(url) or {
        "ok": True, "action": "fill", "host": "boards.example.net", "url": url, "job_id": "", "job": "", "guessed": False, "wants_file": False, "has_files": False,
        "is_lead": False, "can_learn": False, "kept": 0, "boxes": 0, "added_rows": 0, "left": [],
        "filled": [{"label": "First name", "value": "Alex", "kind": "detail", "check": ""}],
        "say": "I opened the form from boards.example.net in a tab of its own. I filled in 1 field on boards.example.net."})
    ui.js('assistantDialog.ask("fill the form")')
    moved = []
    for _ in range(60):
        moved.append(abs(ui.find("assistantBot").property("shakeBy")))
        ui.wait(20)
    assert max(moved) > 3, "it shook its head"
    assert dialog.property("canOpenForm") and not dialog.property("canLearn") and ui.find("asOpenForm").property("visible")
    assert ui.find("asOpenForm").property("text") == "Open the form in its own tab and fill it in"
    ui.js('assistantDialog.act("open_form", assistantDialog.last.frame, "Open the form in its own tab and fill it in")')
    _wait_idle(ui, dialog)
    assert opened == ["https://boards.example.net/embed?id=7"]
    assert not dialog.property("canOpenForm") and ui.js("filledModel.count") == 1, "one press: the form is open and what was filled is listed"
    assert "in a tab of its own" in ui.js("talk.get(talk.count - 1).text") or ui.js("assistantDialog.typingIndex") >= 0
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, "assistantDialog")
    store.save_jobs([dict(j, status="letter_ready") if j["id"] == "lead" else j for j in store.load_jobs()])      # as the other tests expect it
    ui.js("win.reloadAll()")
    assert dialog.property("visible") is False and ui.warnings == []


def test_a_press_on_empty_space_ends_the_editing_of_a_field(ui):
    """The accent outline and the cursor of a text field used to stay when you clicked somewhere else in the window."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    dialog = ui.find("assistantDialog")
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    ui.js('assistantDialog.page = "ask"')
    box = ui.find("asBox")
    ui.js("forceActiveFocus()", box)
    ui.wait(100)
    assert box.property("activeFocus") is True
    spot = box.mapToScene(QPointF(box.width() / 2, -170)).toPoint()             # in the conversation above the field: empty space
    QTest.mouseClick(ui.win, Qt.LeftButton, Qt.NoModifier, QPoint(spot.x(), spot.y()))
    ui.wait(150)
    assert box.property("activeFocus") is False, "the field let go"
    QTest.mouseClick(ui.win, Qt.LeftButton, Qt.NoModifier, box.mapToScene(QPointF(box.width() / 2, box.height() / 2)).toPoint())
    ui.wait(150)
    assert box.property("activeFocus") is True, "and a click in the field still starts editing"
    # a list keeps its outline after a choice too: the same press lets go of it
    combo = ui.find("asJob")
    ui.js("forceActiveFocus()", combo)
    ui.wait(100)
    assert combo.property("activeFocus") is True
    QTest.mouseClick(ui.win, Qt.LeftButton, Qt.NoModifier, QPoint(spot.x(), spot.y()))
    ui.wait(150)
    assert combo.property("activeFocus") is False, "the list let go"
    header = box.mapToScene(QPointF(box.width() / 2, 0)).toPoint()
    QTest.mouseClick(ui.win, Qt.LeftButton, Qt.NoModifier, QPoint(header.x(), int(dialog.property("y")) + 30))   # beside the title
    ui.wait(150)
    assert box.property("activeFocus") is False
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, "assistantDialog")
    assert ui.warnings == []


def test_the_country_picker_lets_go_of_its_search_box_when_you_press_the_list(ui):
    """After typing a search and clicking a country, the search box kept its outline and cursor (17 October)."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    picker = ui.find("remoteDialog")
    ui.js("remoteDialog.show([], 'Czechia')")
    _until_open(ui, "remoteDialog")
    field, listing = ui.find("countrySearch"), ui.find("countryList")
    # the catcher lies over the list: it must not swallow the mouse wheel (checked before any simulated click,
    # which leaves the off-screen window in a state real use does not)
    from PySide6.QtCore import QCoreApplication, QPoint as _P
    from PySide6.QtGui import QWheelEvent
    assert _until_true(ui, lambda: (listing.property("contentHeight") or 0) > listing.property("height") * 2)   # all rows drawn
    middle = listing.mapToScene(QPointF(listing.width() / 2, listing.height() / 2))
    for _ in range(4):
        QCoreApplication.sendEvent(ui.win, QWheelEvent(middle, ui.win.mapToGlobal(middle), _P(0, 0), _P(0, -120),
                                                      Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
    assert _until_true(ui, lambda: (listing.property("contentY") or 0) > 0), "the wheel still scrolls the list"
    ui.js('forceActiveFocus(); text = "germ"', field)
    assert _until_true(ui, lambda: ui.js("remoteDialog.shown.length") == 1) and field.property("activeFocus") is True
    row = ui.drawn("country_germany", root="countryList")
    QTest.mouseClick(ui.win, Qt.LeftButton, Qt.NoModifier, row.mapToScene(QPointF(row.width() / 2, row.height() / 2)).toPoint())
    assert _until_true(ui, lambda: ui.js("remoteDialog.picked.indexOf('germany') >= 0")), "the click still ticks the country"
    assert _until_true(ui, lambda: field.property("activeFocus") is False), "and the search box let go"
    ui.js("forceActiveFocus()", field)
    assert _until_true(ui, lambda: field.property("activeFocus") is True)
    empty = listing.mapToScene(QPointF(listing.width() / 2, listing.height() - 20)).toPoint()     # below the one row: empty space
    QTest.mouseClick(ui.win, Qt.LeftButton, Qt.NoModifier, QPoint(empty.x(), empty.y()))
    assert _until_true(ui, lambda: field.property("activeFocus") is False), "a press on the empty list lets go too"
    assert ui.js("remoteDialog.picked.length") == 1                                    # and changed nothing
    QTest.mouseClick(ui.win, Qt.LeftButton, Qt.NoModifier, field.mapToScene(QPointF(field.width() / 2, field.height() / 2)).toPoint())
    assert _until_true(ui, lambda: field.property("activeFocus") is True), "a click in the box still starts typing"
    ui.js("remoteDialog.close()")
    _until_closed(ui, "remoteDialog")
    assert picker.property("visible") is False and ui.warnings == []


def test_the_job_table_lets_go_of_its_search_box_when_you_press_the_list(ui):
    from PySide6.QtCore import QPointF, Qt
    ui.js('openView("new")')
    _until_open(ui, "tableDialog")
    field, listing = ui.find("searchField"), ui.find("listView")
    ui.js("forceActiveFocus()", field)
    assert _until_true(ui, lambda: field.property("activeFocus") is True)
    empty = listing.mapToScene(QPointF(listing.width() / 2, listing.height() - 8)).toPoint()      # the bottom of the list
    QTest.mouseClick(ui.win, Qt.LeftButton, Qt.NoModifier, empty)
    assert _until_true(ui, lambda: field.property("activeFocus") is False), "the search box let go"
    ui.js("tableDialog.close()")
    _until_closed(ui, "tableDialog")
    assert ui.warnings == []


def test_every_window_with_a_text_field_lets_go_of_it():
    """A window that has a field to type in must have a way to end the editing by pressing beside it."""
    fields = re.compile(r"\b(TextField|TextEdit|TextArea|AutoField|ThemedSpin|TimeField|TagEditor) \{")
    for path in sorted((ROOT / "ui_qt").glob("*Dialog.qml")) + [ROOT / "ui_qt" / "WelcomeOverlay.qml"]:
        text = path.read_text(encoding="utf-8")
        if fields.search(text) or "ThemedCombo {" in text:
            assert "FocusCatcher {}" in text or "Sink.forceActiveFocus()" in text, f"{path.name} keeps a field's outline when you press beside it"
        for scroll in re.findall(r"\n( +)Flickable \{\n(?:.*\n){0,6}?\1    (\w+) \{", text):
            if "FocusCatcher {}" in text:
                assert scroll[1] in ("FocusCatcher", "MouseArea"), f"{path.name}: a scroll area without a FocusCatcher as its first child"
        if fields.search(text):                    # a list beside a field: rows take the press, so a catcher lies over them
            assert text.count("FocusCatcher { z: 2 }") >= text.count("ListView {"), \
                f"{path.name}: a list where pressing a row or the empty space keeps the field's outline"


def test_my_details_takes_several_jobs_degrees_a_salary_with_its_currency_and_files(ui, monkeypatch, tmp_path):
    from jobhelper import details
    details.path().unlink(missing_ok=True)
    dialog = ui.find("assistantDialog")
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    ui.js('assistantDialog.page = "details"')
    ui.js('assistantDialog.setField("first_name", "Alex"); assistantDialog.setField("last_name", "Novak")')
    # jobs: any number, several may be current
    for _ in range(3):
        ui.js("assistantDialog.addRow(jobModel, assistantDialog.jobCols, true)")
    assert ui.js("jobModel.count") == 3 and dialog.property("dirty")
    ui.js('assistantDialog.setRow(jobModel, 0, "employer", "Old Mill")')
    assert ui.js("assistantDialog.problem.field") == "experience.0.title" and "missing" in ui.js('assistantDialog.faultIn("experience").msg')
    assert ui.find("asDetailsNote").property("text").startswith("1 field needs a change"), "said under its row, counted in the footer"
    ui.js('assistantDialog.setRow(jobModel, 0, "title", "Intern"); assistantDialog.setRow(jobModel, 0, "start", "2020"); assistantDialog.setRow(jobModel, 0, "end", "2019")')
    assert ui.js("assistantDialog.problem.field") == "experience.0.end" and "earlier" in ui.js("assistantDialog.problem.msg")
    ui.js('assistantDialog.setRow(jobModel, 0, "end", "2021")')
    ui.js('assistantDialog.setRow(jobModel, 1, "employer", "Northwind"); assistantDialog.setRow(jobModel, 1, "title", "Junior analyst"); assistantDialog.setRow(jobModel, 1, "current", true)')
    ui.js('assistantDialog.setRow(jobModel, 2, "employer", "Evening School"); assistantDialog.setRow(jobModel, 2, "title", "Tutor"); assistantDialog.setRow(jobModel, 2, "current", true)')
    ui.js('assistantDialog.setRow(jobModel, 2, "start", "last year")')
    assert ui.js("assistantDialog.problem.field") == "experience.2.start"
    ui.js("assistantDialog.saveDetails()")
    assert not details.path().exists(), "nothing is saved while a line is wrong"
    ui.js('assistantDialog.setRow(jobModel, 2, "start", "2022")')
    assert ui.js("!assistantDialog.problem.msg")
    # degrees
    ui.js("assistantDialog.addRow(schoolModel, assistantDialog.schoolCols, false); assistantDialog.addRow(schoolModel, assistantDialog.schoolCols, false)")
    ui.js('assistantDialog.setRow(schoolModel, 0, "school", "Masaryk University"); assistantDialog.setRow(schoolModel, 0, "degree", "Master")')
    ui.js('assistantDialog.setRow(schoolModel, 1, "degree", "Bachelor")')
    assert ui.js("assistantDialog.problem.field") == "education.1.school"
    ui.js('assistantDialog.setRow(schoolModel, 1, "school", "Masaryk University")')
    # salary: a figure and a currency
    assert _listed(dialog.property("currencies"))[:4] == ["CZK", "EUR", "USD", "GBP"]
    ui.js('assistantDialog.setSalary("a lot", "EUR", "year")')
    assert ui.js("assistantDialog.problem.field") == "salary" and "whole number" in ui.js("assistantDialog.problem.msg")
    ui.js('assistantDialog.setSalary("52000", "EUR", "year")')
    # files
    paper = tmp_path / "AWS certificate.pdf"
    paper.write_bytes(b"x")
    ui.js(f'assistantDialog.addFile("file://{tmp_path}/missing.pdf")')
    assert ui.js("fileModel.count") == 0 and "not a file" in ui.js("assistantDialog.problem.msg")
    ui.js(f'assistantDialog.addFile("{paper.as_uri()}")')
    ui.js(f'assistantDialog.addFile("{paper.as_uri()}")')
    assert ui.js("fileModel.count") == 1 and ui.js("fileModel.get(0).label") == "AWS certificate" and "already" in ui.js("assistantDialog.problem.msg")
    ui.js("assistantDialog.touched()")
    _until_true(ui, lambda: ui.find("asJobs").property("visible") and ui.find("asSchools").property("visible"))
    assert ui.find("asJobs").property("visible") and ui.find("asSchools").property("visible") and ui.warnings == []
    ui.js("assistantDialog.saveDetails()")
    kept = details.load()
    assert [j["employer"] for j in kept["experience"]] == ["Old Mill", "Northwind", "Evening School"] and [j["current"] for j in kept["experience"]] == [False, True, True]
    assert [s["degree"] for s in kept["education"]] == ["Master", "Bachelor"] and details.salary_text(kept) == "52 000 EUR gross per year"
    assert kept["files"] == [{"label": "AWS certificate", "path": str(paper)}] and not dialog.property("dirty")
    assert ui.js("jobModel.count") == 3 and ui.js("jobModel.get(1).current") is True and dialog.property("salaryCurrency") == "EUR", "read back as it was saved"
    # the same from the CV, with Claude: offered, never over your rows without asking
    monkeypatch.setattr(ui_api.Api, "assistant_cv_lists", lambda self: {"ok": True, "say": "I read 1 jobs and 1 degrees from your CV.",
        "experience": [{"employer": "Riverside Labs", "title": "Developer", "start": "2024", "end": "", "current": True}],
        "education": [{"school": "Charles University", "degree": "Master", "field": "Computer science", "start": "2019", "end": "2021"}]})
    ui.js("assistantDialog.readCv()")
    assert not dialog.property("busy") and "replaces the jobs and degrees" in ui.js("assistantDialog.problem.msg") and ui.js("jobModel.count") == 3
    ui.js("assistantDialog.readCv()")
    _wait_idle(ui, dialog)
    assert ui.js("jobModel.count") == 1 and ui.js("jobModel.get(0).employer") == "Riverside Labs" and ui.js("schoolModel.get(0).field") == "Computer science"
    assert dialog.property("dirty") and "not saved yet" in ui.find("asDetailsNote").property("text")
    assert [j["employer"] for j in details.load()["experience"]] == ["Old Mill", "Northwind", "Evening School"], "offered, not saved"
    ui.js("assistantDialog.tryClose()")
    assert dialog.property("opened"), "unsaved rows: asked once"
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, "assistantDialog")
    details.path().unlink(missing_ok=True)
    assert dialog.property("visible") is False and ui.warnings == []


def test_my_answers_are_written_drafted_saved_and_removed(ui, monkeypatch):
    from jobhelper import answer_memory
    answer_memory.forget_all()
    dialog = ui.find("assistantDialog")
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    ui.js('assistantDialog.page = "answers"')
    assert ui.js("answerModel.count") == 0 and "When can you start?" in _listed(dialog.property("starters"))
    ui.js('assistantDialog.addAnswer("When can you start?")')
    assert ui.js("answerModel.count") == 1 and "When can you start?" not in _listed(dialog.property("starters"))
    ui.js('assistantDialog.addAnswer("When can you start?")')
    assert ui.js("answerModel.count") == 1 and "already" in ui.find("asAnswersNote").property("text")
    ui.js("assistantDialog.saveAnswer(0)")
    assert "empty" in ui.js("answerModel.get(0).err") and answer_memory.count() == 0
    ui.js('assistantDialog.setAnswer(0, "answer", "On [date].")')
    ui.js("assistantDialog.saveAnswer(0)")
    assert "square brackets" in ui.js("answerModel.get(0).err")
    ui.js('assistantDialog.setAnswer(0, "answer", "Two weeks after an offer.")')
    ui.js("assistantDialog.saveAnswer(0)")
    assert answer_memory.recall("When can you start?")["answer"] == "Two weeks after an offer." and ui.js("answerModel.get(0).dirty") is False
    assert "Kept" in ui.find("asAnswersNote").property("text") and dialog.property("remembered") == 1
    # a draft from the CV: not over your text without asking, and not kept until saved
    monkeypatch.setattr(ui_api.Api, "draft_my_answer", lambda self, question: {
        "ok": True, "question": question, "answer": "I am careful with data.", "check": "", "say": "Drafted from your CV. Read it, make it yours, then save."})
    ui.js('assistantDialog.addAnswer("What are your strengths?")')
    ui.js("assistantDialog.draftAnswer(0)")
    _wait_idle(ui, dialog)
    assert ui.js("answerModel.get(0).answer") == "I am careful with data." and ui.js("answerModel.get(0).dirty") is True and answer_memory.count() == 1
    ui.js("assistantDialog.draftAnswer(0)")
    assert not dialog.property("busy") and "replaces what is written" in ui.js("answerModel.get(0).err")
    monkeypatch.setattr(ui_api.Api, "draft_my_answer", lambda self, question: {"ok": False, "field": "question", "msg": "This question is about one company."})
    ui.js('assistantDialog.addAnswer("Why do you want to work here?")')
    ui.js("assistantDialog.draftAnswer(0)")
    _wait_idle(ui, dialog)
    assert ui.js("answerModel.get(0).err") == "This question is about one company." and "one company" in ui.find("asAnswersNote").property("text")
    ui.js("assistantDialog.tryClose()")
    assert dialog.property("opened") and "not saved" in ui.find("asAnswersNote").property("text"), "unsaved answers: asked once"
    ui.js("assistantDialog.removeAnswer(0)")                          # an empty row that was never kept: gone at once
    assert ui.js("answerModel.count") == 2
    ui.js("assistantDialog.removeAnswer(0)")                          # one with words in it: asked once
    assert ui.js("answerModel.count") == 2 and "once more" in ui.js("answerModel.get(0).err")
    ui.js("assistantDialog.removeAnswer(0)")
    assert ui.js("answerModel.count") == 1 and ui.js("answerModel.get(0).question") == "When can you start?"
    ui.js("assistantDialog.removeAnswer(0)")                          # a kept answer is not deleted on one press
    assert answer_memory.count() == 1 and "for good" in ui.js("answerModel.get(0).err")
    ui.js('assistantDialog.setAnswer(0, "answer", "Two weeks after an offer!")')      # typing takes the first press back
    ui.js("assistantDialog.removeAnswer(0)")
    assert answer_memory.count() == 1 and ui.js("answerModel.count") == 1
    ui.js("assistantDialog.removeAnswer(0)")
    assert answer_memory.count() == 0 and dialog.property("remembered") == 0 and ui.js("answerModel.count") == 0
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, dialog)
    assert dialog.property("visible") is False and ui.warnings == []


def test_the_assistant_asks_before_it_changes_anything_and_shows_what_it_found(ui, monkeypatch):
    dialog, did = ui.find("assistantDialog"), []
    talk = {"ok": True, "action": "confirm", "say": "", "ask": "Mark Junior Python Developer at Acme as applied? It moves to Applications as waiting.",
            "pending": {"name": "mark_applied", "args": {"job": "lead"}}, "rows": []}
    monkeypatch.setattr(ui_api.Api, "assistant_talk", lambda self, text, context_job="", chosen_job="", **kw: did.append(("talk", text, context_job, chosen_job)) or dict(talk))
    monkeypatch.setattr(ui_api.Api, "assistant_confirm", lambda self, pending: did.append(("confirm", pending)) or {
        "ok": True, "action": "done", "say": "Moved Junior Python Developer at Acme to Applications, as waiting.", "job_id": "lead", "changed": True})
    monkeypatch.setattr(ui_api.Api, "assistant_briefing", lambda self: {"headline": "", "lines": [], "nudges": []})
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    ui.js('assistantDialog.page = "ask"')
    assert not ui.find("asConfirm").property("visible")
    ui.js('assistantDialog.ask("mark the Acme job as applied")')
    _wait_idle(ui, dialog)
    assert did == [("talk", "mark the Acme job as applied", "", "")]
    assert ui.find("asConfirm").property("visible") and dialog.property("pendingAsk").startswith("Mark Junior Python Developer at Acme as applied?")
    assert ui.js("talk.get(talk.count - 1).text") == talk["ask"]
    ui.js('assistantDialog.ask("and another thing")')
    assert "Yes, do it or No" in ui.find("asErr").property("text") and len(did) == 1, "an open question is answered first"
    ui.js("assistantDialog.no()")
    assert not ui.find("asConfirm").property("visible") and ui.js("talk.get(talk.count - 1).text") == "Left as it was." and len(did) == 1
    ui.js('assistantDialog.ask("mark the Acme job as applied")')
    _wait_idle(ui, dialog)
    ui.js("assistantDialog.yes()")
    _wait_idle(ui, dialog)
    assert did[-1] == ("confirm", {"name": "mark_applied", "args": {"job": "lead"}}) and not ui.find("asConfirm").property("visible")
    assert ui.js("talk.get(talk.count - 1).text").startswith("Moved Junior Python Developer at Acme")
    # a rewrite is shown before it is saved
    talk.update(ask="Replace paragraph 2 of the letter for Acme with this version?", preview="I build reports people use.",
                pending={"name": "save_letter", "args": {"job": "lead", "paragraphs": ["a", "b"]}})
    ui.js('assistantDialog.ask("make the second paragraph shorter")')
    _wait_idle(ui, dialog)
    assert dialog.property("pendingPreview") == "I build reports people use." and ui.find("asConfirm").property("visible")
    ui.js("assistantDialog.no()")
    # an answer with jobs: listed, and a click opens the job; the open job is passed on as "this job"
    monkeypatch.setattr(ui_api.Api, "assistant_talk", lambda self, text, context_job="", chosen_job="", **kw: did.append(("talk", text, context_job, chosen_job)) or {
        "ok": True, "action": "say", "say": "Beta has waited 20 days.", "rows": [{"id": "app", "label": "Beta · QA Engineer", "sub": "waiting · score 64"}]})
    ui.js('assistantDialog.forJob("app"); assistantDialog.page = "ask"')
    ui.js('assistantDialog.ask("which application waits longest?")')
    _wait_idle(ui, dialog)
    assert did[-1] == ("talk", "which application waits longest?", "", "app")
    assert ui.find("asRows").property("visible") and ui.js("rowModel.get(0).label") == "Beta · QA Engineer"
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, "assistantDialog")
    ui.js('detailDialog.show("app")')
    _until_open(ui, "detailDialog")
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    ui.js('assistantDialog.ask("why did this score 64?")')
    _wait_idle(ui, dialog)
    assert did[-1] == ("talk", "why did this score 64?", "app", ""), "the job whose window is open is “this job”"
    ui.js("assistantDialog.tryClose(); detailDialog.close()")
    _until_closed(ui, "assistantDialog"); _until_closed(ui, "detailDialog")
    assert ui.warnings == []


def test_practising_an_interview_goes_question_by_question(ui, monkeypatch):
    dialog, did = ui.find("assistantDialog"), []
    monkeypatch.setattr(ui_api.Api, "assistant_briefing", lambda self: {"headline": "", "lines": [], "nudges": []})
    monkeypatch.setattr(ui_api.Api, "assistant_talk", lambda self, text, context_job="", chosen_job="", **kw: {
        "ok": True, "action": "practice", "job_id": "app", "job": "QA Engineer at Beta", "questions": ["Why testing?", "Tell me about Docker."], "say": "Let us practise: 2 questions."})

    def feedback(self, job_id, question, answer):
        did.append((job_id, question, answer))
        if answer == "Yes.":
            return {"ok": False, "action": "practice_feedback", "msg": "Answer in a sentence or two, as you would in the interview."}
        return {"ok": True, "action": "practice_feedback", "say": "Good. Add the pipeline you built."}
    monkeypatch.setattr(ui_api.Api, "assistant_practice_answer", feedback)
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    ui.js('assistantDialog.page = "ask"; assistantDialog.ask("practise the interview for Beta")')
    _wait_idle(ui, dialog)
    assert dialog.property("practising") and ui.find("asPractice").property("visible") and ui.js("talk.get(talk.count - 1).text") == "Question 1 of 2: Why testing?"
    ui.js('assistantDialog.ask("Yes.")')
    _wait_idle(ui, dialog)
    assert "sentence or two" in ui.find("asErr").property("text") and dialog.property("practiceIndex") == 0, "an answer that was not taken keeps the question"
    ui.js('assistantDialog.ask("Because I like finding what breaks.")')
    _wait_idle(ui, dialog)
    assert did[-1] == ("app", "Why testing?", "Because I like finding what breaks.") and dialog.property("practiceIndex") == 1
    assert ui.js("talk.get(talk.count - 2).text") == "Good. Add the pipeline you built." and ui.js("talk.get(talk.count - 1).text") == "Question 2 of 2: Tell me about Docker."
    ui.js('assistantDialog.ask("I run the tests in containers.")')
    _wait_idle(ui, dialog)
    assert not dialog.property("practising") and "last question" in ui.js("talk.get(talk.count - 1).text")
    ui.js('assistantDialog.ask("practise the interview for Beta")')
    _wait_idle(ui, dialog)
    ui.js('assistantDialog.ask("stop")')
    assert not dialog.property("practising") and len(did) == 3 and "Practice ended" in ui.js("talk.get(talk.count - 1).text")
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, "assistantDialog")
    assert ui.warnings == []


def test_the_assistant_speaks_first_reviews_a_form_and_notices_one_only_when_told_to(ui, monkeypatch):
    dialog, bot, did = ui.find("assistantDialog"), ui.find("assistantBot"), []
    monkeypatch.setattr(ui_api.Api, "assistant_briefing", lambda self: {
        "headline": "You filled in the form for QA Engineer at Beta yesterday but did not mark it applied.", "lines": ["2 jobs are ready to send", "1 follow-up due"],
        "nudges": [{"kind": "apply", "job_id": "lead", "text": "You filled in the form for Junior Python Developer at Acme yesterday but did not mark it applied."}]})
    monkeypatch.setattr(ui_api.Api, "assistant_nudge_done", lambda self, job_id, kind: did.append(("done", job_id, kind)) or {"ok": True})
    # the bubble carries the briefing when the app opens
    ui.js("welcome.shown = true")
    _until_shown(ui, "welcome")
    ui.js("welcome.finish()")
    _until_true(ui, lambda: bot.property("note").startswith("You filled in the form"), most_ms=6000)
    assert bot.property("note").startswith("You filled in the form for QA Engineer at Beta") and bot.property("greeting") and bot.property("shown") == bot.property("note")
    bubble = ui.drawn("assistantBubble", "stagePanel")
    assert bubble.mapToItem(bot.parentItem(), 0, 0).x() >= 0, "the longer bubble still stays on the floor"
    bot.setProperty("greeting", False)
    # the window lists what to look at, and a nudge can be told to stop
    ui.js("talk.clear(); assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    ui.js('assistantDialog.page = "ask"')
    assert ui.find("asNudges").property("visible") and ui.js("nudgeModel.count") == 1 and ui.js("talk.get(0).text") == "Today: 2 jobs are ready to send; 1 follow-up due."
    ui.js("assistantDialog.dropNudge(0)")
    assert did == [("done", "lead", "apply")] and not ui.find("asNudges").property("visible")
    # a review lists what is wrong
    monkeypatch.setattr(ui_api.Api, "assistant_review", lambda self, job_id="": {"ok": True, "action": "review", "say": "I read the form: 1 thing looks wrong.",
                                                                             "problems": [{"field": "Phone", "problem": "It is required and still empty."}]})
    ui.js('assistantDialog.page = "ask"; assistantDialog.act("review", "", "Review the form before I send it")')
    _wait_idle(ui, dialog)
    assert ui.find("asProblems").property("visible") and ui.js("problemModel.get(0).field") == "Phone"
    # noticing a form: off until the switch is on; a problem is said beside the switch
    from jobhelper import config
    assert dialog.property("watching") is False and not config.ui_settings().get("assistant_watch")
    ui.js("assistantDialog.setWatch(true)")
    assert dialog.property("watching") is True and config.ui_settings().get("assistant_watch") is True
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, "assistantDialog")
    ui.bridge.formNoticed.emit({"ok": False, "problem": "Chrome does not let other apps fill in pages yet."})
    assert dialog.property("watchProblem").startswith("Chrome does not let")
    ui.bridge.formNoticed.emit({"ok": True, "job_id": "app", "job": "QA Engineer at Beta", "say": "This looks like the form for QA Engineer at Beta. Tap me and I fill it in."})
    _until_true(ui, lambda: bot.property("note").startswith("This looks like the form"))
    assert bot.property("note").startswith("This looks like the form for QA Engineer at Beta") and bot.property("greeting") and dialog.property("watchProblem") == ""
    ui.js("stagePanel.assistant.tapped()")
    _until_open(ui, "assistantDialog")
    assert dialog.property("jobId") == "app", "the form it noticed is the job the answers are for"
    ui.js("assistantDialog.setWatch(false)")
    assert config.ui_settings().get("assistant_watch") is False
    bot.setProperty("greeting", False)
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, "assistantDialog")
    assert ui.warnings == []


def test_the_assistant_at_pro_level_in_the_window(ui, monkeypatch):
    from jobhelper import config
    dialog, did = ui.find("assistantDialog"), []
    monkeypatch.setattr(ui_api.Api, "assistant_briefing", lambda self: {"headline": "", "lines": [], "nudges": []})

    def talk(self, text, context_job="", chosen_job="", progress=None):
        did.append(text)
        progress("Asking Claude…")
        if "reply" in text:
            return {"ok": True, "action": "draft", "copy": "Dear team,\nTuesday suits me.\nAlex", "preview": "x", "say": "A reply for you to copy. I never send mail.", "also": [], "then": []}
        if "remember" in text:
            return {"ok": True, "action": "say", "say": "I will remember: No consulting firms.", "notes_changed": True, "also": [], "then": []}
        return {"ok": True, "action": "confirm", "say": "", "ask": "Shall I do these 2 things?\n1. Mark it applied?\n2. Set a date?",
                "pending": {"name": "many", "args": {"actions": [{"name": "mark_applied", "args": {"job": "lead"}}]}},
                "also": ["Opening QA Engineer at Beta."], "then": [{"action": "open", "job_id": "app", "what": "job", "page": ""}], "rows": []}
    monkeypatch.setattr(ui_api.Api, "assistant_talk", talk)
    monkeypatch.setattr(ui_api.Api, "assistant_confirm", lambda self, pending: did.append(("confirm", pending["name"])) or {
        "ok": True, "action": "done", "say": "Moved it to Applications. The date is set.", "job_id": "lead", "changed": True, "can_undo": True})
    monkeypatch.setattr(ui_api.Api, "assistant_undo", lambda self: did.append("undo") or {"ok": True, "action": "done", "say": "It is as it was before.", "changed": True, "can_undo": False})
    notes = [{"text": "No consulting firms", "when": "2026-10-10"}]
    monkeypatch.setattr(ui_api.Api, "assistant_notes_list", lambda self: {"notes": list(notes)})
    monkeypatch.setattr(ui_api.Api, "assistant_forget_note", lambda self, number: did.append(("forget", number)) or (notes.clear() or {"ok": True, "text": "x"}))
    ui.js("talk.clear(); assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    ui.js('assistantDialog.page = "ask"')
    assert ui.find("asFill").property("text") == "Fill in the form" and "open in Google Chrome" in ui.find("asErr").property("text") and ui.find("asStarters").property("visible")
    # several things at once: what only shows is done, the rest is one question; then it can be taken back
    ui.js('assistantDialog.ask("mark acme applied, set a date and open beta")')
    _wait_idle(ui, dialog)
    _until_true(ui, lambda: ui.find("detailDialog").property("visible"))
    assert ui.find("detailDialog").property("visible"), "what was to be opened is opened"
    assert ui.js("talk.get(talk.count - 2).text") == "Opening QA Engineer at Beta." and ui.find("asConfirm").property("visible")
    assert not ui.find("asStarters").property("visible"), "a question is open: nothing else is offered"
    ui.js("assistantDialog.yes()")
    _wait_idle(ui, dialog)
    assert ("confirm", "many") in did and dialog.property("canUndo") and ui.find("asUndo").property("visible")
    ui.js('assistantDialog.act("undo", "", "Undo that")')
    _wait_idle(ui, dialog)
    assert did[-1] == "undo" and not dialog.property("canUndo") and ui.js("talk.get(talk.count - 1).text") == "It is as it was before."
    ui.js("detailDialog.close()")
    # a reply to copy
    ui.js('assistantDialog.ask("draft a reply to beta")')
    _wait_idle(ui, dialog)
    assert ui.find("asDraft").property("visible") and dialog.property("draftText").startswith("Dear team,")
    ui.js("bridge.copyText(assistantDialog.draftText)")
    # a long answer is written out, and whole in the end
    monkeypatch.setattr(ui_api.Api, "assistant_talk", lambda self, text, *a, **kw: {"ok": True, "action": "say", "say": "word " * 60, "also": [], "then": [], "rows": []})
    ui.js('assistantDialog.ask("what needs my attention today?")')
    _wait_idle(ui, dialog)
    assert dialog.property("typingIndex") >= 0 or ui.js("talk.get(talk.count - 1).text.length") == 300
    for _ in range(80):                                      # written out in well under a second; longer on a busy machine
        ui.wait(50)
        if dialog.property("typingIndex") == -1:
            break
    assert dialog.property("typingIndex") == -1 and ui.js("talk.get(talk.count - 1).text.length") == 300
    monkeypatch.setattr(ui_api.Api, "assistant_talk", talk)
    # notes: listed on the My details page, and one can be forgotten there
    ui.js('assistantDialog.ask("remember that I do not want consulting firms")')
    _wait_idle(ui, dialog)
    ui.js('assistantDialog.page = "details"')
    ui.wait(150)
    assert ui.js("noteModel.count") == 1 and ui.find("asNotes").property("visible")
    ui.js("assistantDialog.forgetNote(0)")
    assert ("forget", 1) in did and ui.js("noteModel.count") == 0
    # the browser is chosen here, and the button says which
    ui.js('assistantDialog.setBrowser("safari")')
    assert config.ui_settings().get("assistant_browser") == "safari" and "Develop" in ui.find("asDetailsNote").property("text")
    ui.js('assistantDialog.page = "ask"')
    assert "open in Safari" in ui.find("asErr").property("text"), "the line under the box says which browser"
    ui.js('assistantDialog.setBrowser("netscape")')
    assert config.ui_settings().get("assistant_browser") == "safari" and dialog.property("browser")["key"] == "safari"
    ui.js('assistantDialog.page = "details"; assistantDialog.setBrowser("firefox")')
    assert "Firefox does not let another app" in ui.find("asDetailsNote").property("text") and config.ui_settings().get("assistant_browser") == "safari"
    names = [b["name"] for b in dialog.property("browser")["all"]]
    assert names == ["Google Chrome", "Brave Browser", "Microsoft Edge", "Opera", "Safari", "Opera GX (not possible)", "Firefox (not possible)"]
    ui.js('assistantDialog.setBrowser("opera_gx")')
    assert config.ui_settings().get("assistant_browser") == "safari" and "Opera GX tells another app which page is open" in ui.find("asDetailsNote").property("text")
    ui.js('assistantDialog.setBrowser("chrome")')
    ui.js("assistantDialog.dirty = false; assistantDialog.tryClose()")
    _until_closed(ui, "assistantDialog")
    from jobhelper import chrome
    chrome.use("chrome")
    assert ui.warnings == []


def test_a_job_is_found_for_the_assistant_by_typing_part_of_its_name(ui, monkeypatch):
    """Among 150 open jobs the list alone is slow to use: typing part of a company or a title narrows it, and when one job is
    left its full name is shown and it is chosen. A name no job has is said in red, where it was typed."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    jobs = [{"id": "nw", "label": "Northwind Systems · Junior Python Developer"}, {"id": "nw2", "label": "Northwind Systems · Data Analyst"},
            {"id": "vt", "label": "Vantor · Junior Tester"}, {"id": "bp", "label": "Brightpath s.r.o. · Machine Learning Engineer"}]
    monkeypatch.setattr(ui_api.Api, "assistant_jobs", lambda self: jobs)
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    ui.js('assistantDialog.page = "ask"')
    ui.wait(100)
    dialog, find, combo, err = ui.find("assistantDialog"), ui.find("asJobFind"), ui.find("asJob"), ui.find("asJobFindErr")
    assert find.property("visible") is True and find.property("width") >= 150 and combo.property("count") == 5 and combo.property("currentText") == "Find the job from the page"
    QTest.mouseClick(ui.win, Qt.LeftButton, Qt.NoModifier, find.mapToScene(QPointF(20, find.height() / 2)).toPoint())
    ui.wait(100)
    def type_in(words):                             # key by key, the way a person types
        for letter in words:
            QTest.keyClick(ui.win, Qt.Key_Space if letter == " " else Qt.Key(ord(letter.upper())), Qt.ShiftModifier if letter.isupper() else Qt.NoModifier)
    type_in("northw")
    ui.wait(150)
    assert combo.property("count") == 3 and dialog.property("jobId") == "", "two jobs at Northwind: narrowed, not chosen for you"
    type_in(" ANALYST")
    ui.wait(150)
    assert combo.property("count") == 2 and dialog.property("jobId") == "nw2", "one job left: it is chosen"
    assert combo.property("currentText") == "Northwind Systems · Data Analyst", "and its full name is shown"
    assert err.property("visible") is False
    ui.js("text = 'zzz'; assistantDialog.findJob(text)", find)
    ui.wait(100)
    assert dialog.property("jobId") == "" and combo.property("count") == 1 and err.property("visible") is True
    assert '"zzz"' in err.property("text") and "Check the spelling" in err.property("text")
    assert 0 < err.property("width") <= dialog.property("width") and err.property("lineCount") >= 1 and err.property("truncated") is False, "the message wraps, it is not cut"
    ui.js("text = '" + "x" * 81 + "'; assistantDialog.findJob(text)", find)
    assert "too long" in dialog.property("jobFindErr")
    ui.js("text = 'tester'; assistantDialog.findJob(text)", find)
    assert dialog.property("jobId") == "vt" and dialog.property("jobFindErr") == ""
    ui.js("text = ''; assistantDialog.findJob('')", find)
    assert combo.property("count") == 5 and dialog.property("jobId") == "vt", "the whole list again, and what you chose stays chosen"
    ui.js("text = 'north'; assistantDialog.findJob(text)", find)
    assert dialog.property("jobId") == "" and combo.property("currentIndex") == 0, "the chosen job is not among these: none is chosen, and the list says so"
    ui.js("assistantDialog.forJob('bp')")               # opened from a job's window: the typed words are put away
    _until_true(ui, lambda: dialog.property("jobId") == "bp")
    assert find.property("text") == "" and combo.property("count") == 5 and dialog.property("jobId") == "bp"
    # the recurring bug: the box lets go of the cursor on a press beside it
    ui.js("forceActiveFocus()", find)
    ui.wait(100)
    box = ui.find("asBox")
    spot = box.mapToScene(QPointF(box.width() / 2, -170)).toPoint()
    QTest.mouseClick(ui.win, Qt.LeftButton, Qt.NoModifier, QPoint(spot.x(), spot.y()))
    ui.wait(150)
    assert find.property("activeFocus") is False
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, "assistantDialog")
    assert ui.warnings == []


def test_the_size_of_text_and_controls_is_an_option_used_at_the_next_start(ui, monkeypatch):
    """On a 27-inch 4K screen the window's text is small. Options has a size for everything in the window; it is checked
    like any other option and takes effect the next time the app is opened (Qt has to know before the window exists)."""
    import app_qt
    api = ui.bridge._api
    assert api.options()["text_size"] == 100 and config.text_scale() == 1.0 and app_qt.apply_text_size({}) == ""
    for wrong in (90, 200, "big", None, True, 125.5):
        result = api.save_options({"text_size": wrong})
        assert result["ok"] is False and "100%, 110%, 125%, 150%" in result["msg"], wrong
    assert api.options()["text_size"] == 100, "a wrong size changes nothing"
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    combo = ui.find("sizeCombo")
    assert combo.property("currentText") == "100%" and combo.property("count") == 4
    def hint():                                     # the line of small words beside the setting
        row = combo.parentItem()
        while row is not None and not isinstance(row.property("hint"), str):
            row = row.parentItem()
        return row.property("hint")
    assert "for a large screen" in hint()
    ui.js("currentIndex = 2", combo)
    ui.wait(100)
    assert "saved with Save" in hint(), "said where you look: nothing changes until Save, and then at the next start"
    assert ui.js("optDialog.collect().options.text_size", dialog) == 125 and ui.js("optDialog.changed()") is True, "Save stores it, and closing asks first"
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
    assert api.save_options({"text_size": 125})["ok"] and api.options()["text_size"] == 125 and config.text_scale() == 1.25
    env = {}
    assert app_qt.apply_text_size(env) == "1.25" and env == {"QT_SCALE_FACTOR": "1.25"}
    assert app_qt.apply_text_size({"QT_SCALE_FACTOR": "2"}) == "", "a size set from outside is left alone"
    monkeypatch.setattr(config, "ui_settings", lambda: {"text_size": "huge"})
    assert config.text_scale() == 1.0 and app_qt.apply_text_size({}) == ""
    monkeypatch.setattr(config, "text_scale", lambda: 1 / 0)
    assert app_qt.apply_text_size({}) == "", "the window opens whatever the settings file holds"
    monkeypatch.undo()
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    assert ui.find("sizeCombo").property("currentText") == "125%", "the saved size is shown again"
    ui.js("close()", dialog)
    _until_closed(ui, dialog)
    api.save_options({"text_size": 100})
    assert ui.warnings == []


def test_my_details_keeps_languages_and_what_you_did_in_each_job(ui):
    """Forms ask, inside each job, where it was and what you did there, and they ask for each language and how well you speak it.
    Both are kept on the My details page; a level in words of your own is refused where you typed it."""
    from jobhelper import details
    saved = {**details.empty(), "first_name": "Alex", "last_name": "Novak", "email": "alex@example.com",
             "experience": [{"employer": "Northwind", "title": "Junior analyst", "start": "03/2023", "end": "", "current": True,
                             "location": "Brno, Czechia", "description": "Built SQL reports\nAutomated the monthly close"}],
             "languages": [{"language": "English", "level": "Fluent"}]}
    assert details.save(saved)["ok"]
    dialog = ui.find("assistantDialog")
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    ui.js('assistantDialog.page = "details"')
    _until_true(ui, lambda: ui.js("jobModel.count") > 0 and ui.js("jobModel.get(0).location") == "Brno, Czechia")
    assert ui.js("jobModel.get(0).location") == "Brno, Czechia" and ui.js("jobModel.get(0).description") == "Built SQL reports\nAutomated the monthly close"
    area = ui.drawn("rowArea_description", "asJobs")
    assert area is not None and area.property("text").startswith("Built SQL reports") and area.property("height") >= 60, "a box of several lines, not one cut line"
    assert ui.js("langModel.count") == 1 and ui.js("langModel.get(0).level") == "Fluent" and ui.find("asAddLang").property("visible")
    ui.js("assistantDialog.addRow(langModel, assistantDialog.langCols, false)")
    ui.js('assistantDialog.setRow(langModel, 1, "language", "Ukrainian"); assistantDialog.setRow(langModel, 1, "level", "mother tongue")')
    ui.wait(150)
    assert ui.js("assistantDialog.problem.field") == "languages.1.level" and "Native, Fluent, Advanced, Intermediate, Basic" in ui.js("assistantDialog.problem.msg")
    ui.js("assistantDialog.saveDetails()")
    assert len(details.load()["languages"]) == 1, "a wrong level is not saved"
    ui.js('assistantDialog.setRow(langModel, 1, "level", "native")')
    ui.wait(150)
    assert ui.js("!assistantDialog.problem.msg")
    ui.js('assistantDialog.setRow(jobModel, 0, "description", "Built SQL reports for finance")')
    ui.js("assistantDialog.saveDetails()")
    kept = details.load()
    assert kept["languages"] == [{"language": "English", "level": "Fluent"}, {"language": "Ukrainian", "level": "Native"}]
    assert kept["experience"][0]["description"] == "Built SQL reports for finance" and kept["experience"][0]["location"] == "Brno, Czechia"
    ui.js("assistantDialog.tryClose()")
    _until_closed(ui, dialog)
    assert dialog.property("visible") is False and ui.warnings == []


def test_number_box_follows_its_buttons_after_typing(ui):
    """After a number was typed and the box left, + and - must still change the number that is shown."""
    ui.js("optDialog.open()"); _until_open(ui, "optDialog")
    spin = ui.find("yearsSpin")
    box = spin.property("contentItem")
    spin.setProperty("value", 4); ui.wait(30)
    box.setProperty("text", "7")
    QMetaObject.invokeMethod(box, "textEdited"); ui.wait(30)
    QMetaObject.invokeMethod(box, "editingFinished"); ui.wait(30)
    assert spin.property("value") == 7 and box.property("text") == "7"
    QMetaObject.invokeMethod(spin, "increase"); ui.wait(30)
    assert spin.property("value") == 8
    assert box.property("text") == "8", "the box still shows the typed number"
    ui.js("optDialog.close()"); _until_closed(ui, "optDialog")


def test_a_suggestion_can_be_chosen_with_the_keyboard(ui):
    """Arrow down marks a suggested role and Return takes it; without the arrow Return takes what was typed."""
    ui.js("optDialog.open()"); _until_open(ui, "optDialog")
    ui.js("roleField.suggestions = ['junior python developer', 'junior data analyst']")
    roles = lambda: ui.js("(function () { var o = []; for (var i = 0; i < rolesModel.count; i++) o.push(rolesModel.get(i).text); return o.join('|'); })()")  # noqa: E731
    try:
        ui.js("roleField.text = 'junior'"); ui.js("roleField.suggest()"); ui.wait(60)
        assert ui.js("roleField.marked") == -1
        ui.js("roleField.down()"); ui.js("roleField.down()"); ui.js("roleField.down()"); ui.wait(30)
        assert ui.js("roleField.marked") == 1                       # it stops at the last one
        ui.js("roleField.take()"); ui.wait(30)
        assert "junior data analyst" in roles().split("|") and "junior" not in roles().split("|")
        ui.js("roleField.text = 'junior qa tester'"); ui.js("roleField.suggest()"); ui.wait(30)
        ui.js("roleField.take()"); ui.wait(30)
        assert "junior qa tester" in roles().split("|")
    finally:
        ui.js("roleField.text = ''; optDialog.roleErr = ''")
        ui.js("roleField.suggestions = Qt.binding(function () { return win.roleSuggestions; })")
    ui.js("optDialog.close()"); _until_closed(ui, "optDialog")


def test_a_long_reply_fits_the_smallest_window(ui):
    """A long summary with the list of applications open must not push the reply window past the app window."""
    from jobhelper import db
    db.upsert_response({"msg_id": "<tall>", "received_date": "Tue, 18 Aug 2026 10:00:00 +0200", "from_addr": "hr@beta.example", "subject": "Your application",
                        "job_id": "", "company": "Beta", "role": "QA Engineer", "stage": "rejection", "rejection_category": "other",
                        "rejection_reason": "They chose somebody with more years in the field. " * 6,
                        "next_step": "Nothing to do now; they keep the CV for later openings. " * 4,
                        "summary": "They thank you for the time you took and say the team was impressed, and then explain at length. " * 9})
    size = (ui.win.width(), ui.win.height())
    ui.win.setWidth(940); ui.win.setHeight(620); ui.wait(80)
    try:
        ui.js('responseDialog.show("<tall>")'); _until_open(ui, "responseDialog")
        ui.js("responseDialog.startPicking()"); ui.wait(120)
        dialog = ui.find("responseDialog")
        assert dialog.property("opened") is True
        assert dialog.property("height") <= 580, f"the reply window is {dialog.property('height')} high in a window of 620"
        flick, picker = ui.find("respFlick"), ui.find("filePicker")
        assert flick.property("contentHeight") > flick.property("height") >= 90          # the long text scrolls
        assert picker.property("height") >= picker.property("implicitHeight") > 60       # and the list under it keeps its room
        assert ui.find("pickFilter").property("height") >= 30
    finally:
        ui.js("responseDialog.close()"); _until_closed(ui, "responseDialog")
        ui.win.setWidth(size[0]); ui.win.setHeight(size[1]); ui.wait(80)
        with db._connect(write=True) as conn:
            conn.execute("DELETE FROM responses WHERE msg_id = ?", ("<tall>",))


def test_a_refused_mark_applied_is_not_reported_as_done(ui, monkeypatch):
    """When the back end refuses (the job is already an application, or gone), the status line must not say it moved."""
    monkeypatch.setattr(qt_bridge.Bridge, "applyJob", qt_bridge.Slot(str, result=bool)(lambda self, job_id: False))
    ui.js('detailDialog.show("lead")'); _until_open(ui, "detailDialog")
    ui.js("detailDialog.markApplied()")                                          # it answers at once
    said = ui.js("ticker.text")
    assert "was not moved" in said and "Moved to Applications" not in said
    assert ui.find("detailDialog").property("opened") is False
    ui.js("tableDialog.close()"); _until_closed(ui, "tableDialog")
    for name in ("DetailDialog.qml", "TableDialog.qml"):                    # neither place ignores the answer
        source = (ROOT / "ui_qt" / name).read_text(encoding="utf-8")
        assert "bridge.applyJob(" in source and "\n        bridge.applyJob(" not in source and "\n                                    bridge.applyJob(" not in source


def test_the_window_uses_no_em_dash_in_what_it_says():
    """The dash rule of the documents holds for the window: an en dash, never an em dash, inside a sentence.
    (A lone "—" for "no value" is a sign, not a sentence, and stays.)"""
    for path in sorted((ROOT / "ui_qt").glob("*.qml")) + sorted((ROOT / "ui_qt").glob("*.js")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("//")[0]
            assert " — " not in code, f"{path.name}:{number} has an em dash in its text"


def test_the_reply_emails_in_analytics_add_up(ui):
    """Every kind of reply email has its row, so the rows under "Reply emails" add up to it (an offer email was left out)."""
    from jobhelper import agent5_responses, db
    db.upsert_response({"msg_id": "<offer-mail>", "received_date": "Tue, 18 Aug 2026 10:00:00 +0200", "from_addr": "hr@beta.example", "subject": "Offer",
                        "job_id": "", "company": "Beta", "role": "QA Engineer", "stage": "offer", "summary": "They offer you the job."})
    try:
        ui.js('win.openView("ana")'); _until_open(ui, "tableDialog")
        rows = ui.js("(function () { var m = listView.model, o = []; for (var i = 0; i < m.length; i++) o.push(m[i].primary + '=' + m[i].value); return o.join('|'); })()",
                     ui.find("tableDialog")).split("|")
        value = lambda label: int(next(r for r in rows if r.startswith(label + "=")).split("=")[1])      # noqa: E731
        kinds = ["↳ confirmations", "↳ interview emails", "↳ tests and tasks", "↳ offer emails", "↳ rejections", "↳ other"]
        assert value("↳ offer emails") >= 1
        assert sum(value(k) for k in kinds) == value("Reply emails")
        assert set(agent5_responses.STAGES) == {"acknowledged", "interview", "assessment", "offer", "rejection", "other"}   # a new kind needs a row too
    finally:
        ui.js("tableDialog.close()"); _until_closed(ui, "tableDialog")
        with db._connect(write=True) as conn:
            conn.execute("DELETE FROM responses WHERE msg_id = ?", ("<offer-mail>",))


def test_the_account_card_stays_inside_the_smallest_window(ui):
    """With the mailbox editor open the card is taller than a small window: it scrolls, and Done stays in view."""
    size = (ui.win.width(), ui.win.height())
    ui.win.setWidth(940); ui.win.setHeight(620); ui.wait(80)
    try:
        ui.js("welcome.openCard()"); _until_shown(ui, "welcome")
        ui.js("welcome.editBox = 1; welcome.editEmail = true")
        done = ui.drawn("welcomeStart", "welcome")
        _until_settled(ui, lambda: done.mapToScene(QPointF(0, done.height())).y())   # the card grows to the mailbox editor
        if os.environ.get("JH_SHOT"):
            ui.win.grabWindow().save(os.environ["JH_SHOT"] + "/card_small.png")
        bottom = done.mapToScene(QPointF(0, done.height())).y()
        assert bottom <= 620, f"the Done button ends at {bottom} in a window 620 high"
        assert done.mapToScene(QPointF(0, 0)).y() > 0
    finally:
        ui.js("welcome.editEmail = false; welcome.finish()")
        _until_true(ui, lambda: ui.find("welcome").property("visible") is False)
        ui.win.setWidth(size[0]); ui.win.setHeight(size[1]); ui.wait(80)


def test_saving_one_part_of_the_job_window_keeps_what_was_typed_in_the_others(ui):
    """A date typed and not saved yet must still be there after the company notes are saved (and the other way round)."""
    _open_job(ui, "app")
    try:
        ui.js('evDate.text = "2026-11-03"; evTime.text = "10:30"; evNote.text = "second round"; detailDialog.eventKind = "call"')
        ui.js('cnNotes.text = "They pay monthly."')
        ui.js("detailDialog.saveNotes()"); ui.wait(60)
        assert ui.js("detailDialog.notesBad") is False
        assert ui.js("evDate.text") == "2026-11-03" and ui.js("evTime.text") == "10:30" and ui.js("evNote.text") == "second round"
        assert ui.js("detailDialog.eventKind") == "call"
        assert ui.js("detailDialog.pending.join('|')") == "the date to remember"          # the notes are saved, the date is still open
        ui.js('cnAsked.text = "about my last project"')
        ui.js("detailDialog.saveEvent()"); ui.wait(60)
        assert ui.js("detailDialog.eventErr") == ""
        assert ui.js("cnAsked.text") == "about my last project"
        assert ui.js("detailDialog.pending.join('|')") == "the notes about the company"
        ui.js('dateField.text = "2026-09-01"')
        ui.js("detailDialog.refresh()"); ui.wait(30)                                       # what a finished scoring or a ticked step does
        assert ui.js("dateField.text") == "2026-09-01" and ui.js("cnAsked.text") == "about my last project"
    finally:
        ui.bridge._api.set_event("app", "", "", "interview", "")
        ui.bridge._api.save_company_notes("Beta", {"contact": "", "salary": "", "asked": "", "notes": ""})
        ui.js("detailDialog.confirmClose = true; detailDialog.close()"); _until_closed(ui, "detailDialog")


def test_options_says_when_something_was_typed_but_not_added(ui):
    """A role or a word typed into a box with its own Add button is not saved: Save says so instead of dropping it."""
    start = ui.bridge.options()
    ui.js("optsData = bridge.options(); optDialog.open()"); _until_open(ui, "optDialog")
    try:
        assert ui.js("optDialog.notAdded()") == ""
        ui.js('roleField.text = "junior qa tester"')
        said = ui.js("optDialog.notAdded()")
        assert "“junior qa tester”" in said and "Search roles" in said and "not added" in said
        ui.js('roleField.text = ""')
        ui.js('skipTags.setAll(["intern"])')
        field = [item for item in ui.seen("optScroll") if item.property("placeholderText") == "e.g. intern"]
        assert len(field) == 1
        field[0].setProperty("text", "trainee"); ui.wait(20)
        said = ui.js("optDialog.notAdded()")
        assert "“trainee”" in said and "Skip titles with" in said
        assert "Save" in ROOT.joinpath("ui_qt", "OptionsDialog.qml").read_text(encoding="utf-8").split("var left = optDialog.notAdded();")[0][-3000:]   # asked on Save
        ui.js("optDialog.close()"); _until_closed(ui, "optDialog")
        ui.js("optDialog.open()"); _until_open(ui, "optDialog")                       # opened again: the half-typed word is gone
        assert ui.js("optDialog.notAdded()") == "" and ui.js("skipTags.typed") == ""
    finally:
        ui.js("optDialog.close()"); _until_closed(ui, "optDialog")
        ui.bridge.saveOptions(start)
        ui.js("optsData = bridge.options()")


def test_the_preparation_window_shows_projects_and_skills(ui):
    """Projects with each tool explained, and skills with their proof, before the questions; an older preparation says how to get them."""
    prep = {"made": "2026-10-15", "summary": "s", "questions": [{"kind": "about you", "audience": "hr", "question": "Tell me about yourself.", "why": "",
                                                                "answer": "I am a junior developer.", "check": ""}],
            "projects": [{"name": "Game-AI agent", "what": "I built an agent that learns to play.", "plain": "", "tools": ["PyTorch"],
                          "tech": [{"tool": "PyTorch", "about": "A library for neural networks.", "use": "It trained the policy.", "why": "It is fast to try ideas in <2 lines>."}],
                          "result": "Shown at two conferences.", "ask": []}],
            "skills": [{"skill": "Python", "proof": "Used in every project.", "detail": "I wrote the training loop."}]}
    ui.bridge._api.editor.change("app", lambda jobs, j: j.__setitem__("interview_prep", prep), render=False)
    try:
        ui.js('prepDialog.show("app")'); _until_open(ui, "prepDialog")
        assert ui.find("prepProjects").property("visible") is True and ui.find("prepSkills").property("visible") is True
        assert ui.find("prepNoProjects").property("visible") is False
        said = [item.property("text") for item in ui.seen("prepProjects") + ui.seen("prepSkills") if item.property("text")]
        assert "Game-AI agent" in said and "Result: Shown at two conferences." in said
        assert any("<b>PyTorch.</b>" in t and "<i>Why:</i> It is fast to try ideas in &lt;2 lines&gt;." in t for t in said)   # its own < is a letter
        assert any("<b>Python:</b> Used in every project. I wrote the training loop." in t for t in said)
        ui.js("prepDialog.close()"); _until_closed(ui, "prepDialog")
        ui.bridge._api.editor.change("app", lambda jobs, j: j.__setitem__("interview_prep", dict(prep, projects=[], skills=[])), render=False)
        ui.js('prepDialog.show("app")'); _until_open(ui, "prepDialog")
        assert ui.find("prepProjects").property("visible") is False and ui.find("prepNoProjects").property("visible") is True
    finally:
        ui.js("prepDialog.close()"); _until_closed(ui, "prepDialog")
        ui.bridge._api.editor.change("app", lambda jobs, j: j.update(interview_prep={}), render=False)
    assert ui.warnings == []


def test_my_details_columns_come_from_the_back_end_with_the_same_words(ui):
    """The columns of the job, degree and language rows were a copy of details.ROWS in the window; now the back end sends
    them and the window adds only its examples. What the page shows did not change."""
    from jobhelper import details
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    ui.js('assistantDialog.page = "details"')
    _until_true(ui, lambda: ui.js("assistantDialog.jobCols.length") == len(details.ROWS["experience"]))
    import json
    read = lambda name: json.loads(ui.js(f"JSON.stringify(assistantDialog.{name})"))      # noqa: E731
    cols = {c["key"]: c for c in read("jobCols")}
    assert cols["description"]["label"] == "What you did there (as your CV says it; forms ask for it inside each job)"
    assert cols["description"]["area"] is True and cols["description"]["most"] == 2000 and cols["start"]["hint"] == "03/2023"
    langs = {c["key"]: c for c in read("langCols")}
    assert langs["level"]["hint"] == "Native, Fluent, Advanced, Intermediate or Basic" and langs["language"]["most"] == 40
    assert [c["key"] for c in read("schoolCols")] == [k for k, _l, _m in details.ROWS["education"]]
    assert ui.js("win.limits.answer") == 3000 and ui.js("assistantDialog.maxRequest") == 300


def test_the_country_picker_finds_a_country_by_the_start_of_its_words_or_another_of_its_names(ui):
    """Typing "Ge" listed Algeria, Argentina, Niger and Nigeria too (they have "ge" inside). Now what you type must start
    a word of the name, or one of the other names the app knows for it ("usa", "england")."""
    dialog, picker = ui.find("optDialog"), ui.find("remoteDialog")
    plain = lambda v: v.toVariant() if hasattr(v, "toVariant") else v                    # noqa: E731
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    ui.js('cityCombo.editText = "Prague"; countryField.text = ""; remoteWhere = "country"; pickedRemote = []', dialog)
    ui.js("remoteAddBtn.clicked()", dialog)
    _until_open(ui, "remoteDialog")
    keys = lambda typed: (ui.js(f'searchField.text = "{typed}"', picker), [c["key"] for c in plain(ui.js("remoteDialog.shown"))])[1]  # noqa: E731
    assert keys("Ge") == ["georgia", "germany"] and keys("ge") == keys("GE")
    assert keys("zealand") == ["new zealand"] and keys("usa") == ["united states"] and "united kingdom" in keys("england")
    assert "niger" in keys("Ni") and "nigeria" in keys("Ni") and "algeria" not in keys("Ni")
    ui.js('searchField.text = ""; remoteDialog.close()', picker)
    _until_closed(ui, "remoteDialog")


def test_suggestions_and_the_city_box_follow_the_same_rules_as_the_other_fields(ui):
    """The city box drew a blue frame of the style's own inside its orange one; suggestions matched letters anywhere."""
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    assert ui.js("cityCombo.contentItem.background.visible", dialog) is False                # only the box's own frame is drawn
    assert ui.js("win.matchesStart(['Software Developer'], 'dev')") is True and ui.js("win.matchesStart('Algeria', 'ge')") is False
    assert ui.js("win.matchesStart(['Kraków'], 'krak')") is True and ui.js("win.matchesStart('C# Developer', 'c#')") is True


def test_about_you_has_its_own_window_under_options(ui):
    """About you moved out of Options into its own window, opened by its own button under Options (with a person icon)."""
    from jobhelper import details
    start = ui.bridge.options()
    details.save({**details.empty(), "first_name": "Alex", "last_name": "Novak", "email": "alex@example.com",
                  "experience": [{"employer": "Northwind", "title": "Junior analyst", "start": "03/2023", "end": "", "current": True}]})
    ui.bridge.saveOptions({**start, "where": "Prague", "about_jobs": [{"job": "Tester, Gone Ltd", "notes": "Ran checks."}]})
    dialog = ui.find("aboutDialog")
    ui.js("clicked()", ui.find("aboutButton"))
    _until_open(ui, "aboutDialog")
    # right to work: a usual answer fills the field, which can still be changed
    assert ui.js("aboutDialog.info.right_choices[0]") == "Full right to work in Czechia"
    ui.js("rightField.text = aboutDialog.info.right_choices[1]", dialog)
    assert ui.find("rightField").property("text") == "EU/EEA citizen: no work permit needed"
    # the start: the date forms will get, or why there is none, as you type
    ui.js('startField.text = "2030-01-15"; aboutDialog.start = bridge.startPreview(startField.text)', dialog)
    assert ui.find("startPreview").property("text") == "Forms get: 15 January 2030"
    ui.js('startField.text = "after my exams"; aboutDialog.start = bridge.startPreview(startField.text)', dialog)
    assert "cannot get a date" in ui.find("startPreview").property("text") and ui.js("aboutDialog.start.ok") is False
    # a box for each job of My details, and the note of a job that is gone, which can be removed
    assert ui.js("boxModel.count", dialog) == 2 and ui.js("boxModel.get(0).job", dialog) == "Junior analyst, Northwind"
    assert ui.js("boxModel.get(1).earlier", dialog) is True and ui.drawn("boxRemove_1", root="aboutScroll").property("visible") is True
    ui.js("boxModel.setProperty(0, 'notes', 'I built the monthly SQL reports.'); boxModel.remove(1)", dialog)
    ui.js('startField.text = "one month"', dialog)
    # unsaved changes: closing asks once
    ui.js("aboutDialog.tryClose()", dialog)
    assert dialog.property("visible") is True and "did not save" in ui.find("aboutErr").property("text")
    ui.js("aboutDialog.save()", dialog)
    _until_closed(ui, "aboutDialog")
    saved = ui.bridge.options()
    assert saved["about_jobs"] == [{"job": "Junior analyst, Northwind", "notes": "I built the monthly SQL reports."}]
    assert saved["about_right_to_work"] == "EU/EEA citizen: no work permit needed" and saved["about_start"] == "one month"
    ui.bridge.saveOptions(start)
    details.save(details.empty())
    assert ui.warnings == []


def test_options_lead_to_about_you(ui):
    dialog = ui.find("optDialog")
    ui.js("optsData = bridge.options()")
    _open(ui, dialog, 450)
    ui.js('countryField.text = "Germany"', dialog)                                     # a change not saved yet
    ui.js("clicked()", ui.find("openAbout"))
    assert dialog.property("visible") is True and "Save or cancel the Options first" in ui.js("optDialog.optErr")
    assert ui.find("aboutDialog").property("visible") is False
    ui.js('countryField.text = ""; optDialog.optErr = ""', dialog)
    ui.js("clicked()", ui.find("openAbout"))
    _until_closed(ui, "optDialog")
    _until_open(ui, "aboutDialog")
    ui.js("close()", ui.find("aboutDialog"))
    _until_closed(ui, "aboutDialog")


def test_the_right_column_fits_and_scrolls_only_when_the_window_is_short(ui):
    """With About you under Options, the column was taller than an 800-pixel window and Help was cut off at its foot."""
    scroll, help_button = ui.find("statusScroll"), ui.find("helpButton")
    height = ui.win.height()
    try:
        ui.win.resize(ui.win.width(), 800)
        assert _until_true(ui, lambda: ui.win.height() == 800)
        assert scroll.property("interactive") is False                                   # it fits: nothing scrolls
        bottom = help_button.mapToItem(scroll, 0, help_button.property("height")).y()
        assert bottom <= scroll.property("height")                                       # Help is whole, not cut off
        ui.win.resize(ui.win.width(), 560)
        assert _until_true(ui, lambda: scroll.property("interactive") is True)          # a short window: the column scrolls
    finally:
        ui.win.resize(ui.win.width(), height)
        _until_true(ui, lambda: ui.win.height() == height)


def test_the_notes_count_includes_the_job_names_and_follows_each_box(ui):
    """The count must be what the app reads (WorkNotes.size, with "At <job>: "), and must change as you type in a job's box."""
    from jobhelper import details
    from jobhelper.about_you import WorkNotes
    start = ui.bridge.options()
    details.save({**details.empty(), "first_name": "Alex", "last_name": "Novak", "email": "alex@example.com",
                  "experience": [{"employer": "Northwind", "title": "Junior analyst", "start": "03/2023", "end": "", "current": True}]})
    ui.js("aboutDialog.show()")
    _until_open(ui, "aboutDialog")
    box = ui.drawn("boxNotes_0", root="aboutScroll")
    box.setProperty("text", "I built the monthly SQL reports.")
    expected = WorkNotes([{"job": "Junior analyst, Northwind", "notes": "I built the monthly SQL reports."}]).size()
    assert _until_true(ui, lambda: ui.find("notesCount").property("text") == f"{expected} of 4000 characters, all notes together")
    assert expected > len("I built the monthly SQL reports.")                     # the job's name counts too
    ui.js("confirmClose = true; close()", ui.find("aboutDialog"))
    _until_closed(ui, "aboutDialog")
    ui.bridge.saveOptions(start)
    details.save(details.empty())
    assert ui.warnings == []


def test_my_details_keeps_every_fault_after_save_salary_too(ui):
    """Review of F11: a refused Save dropped the per-field messages, and a salary fault showed only when it came first."""
    ui.js("assistantDialog.show()")
    _until_open(ui, "assistantDialog")
    dialog = ui.find("assistantDialog")
    try:
        ui.js('assistantDialog.page = "details"')
        ui.js('assistantDialog.setField("first_name", "Alex"); assistantDialog.setField("email", "alex@example"); assistantDialog.setField("phone", "call me")')
        ui.js("assistantDialog.saveDetails()")
        assert "email address" in ui.js('assistantDialog.faultAt("email")') and "digits" in ui.js('assistantDialog.faultAt("phone")'), \
            "Save keeps every field's own message"
        ui.js('assistantDialog.salaryAmount = "a lot"; assistantDialog.touched()', dialog)
        ui.js("assistantDialog.problem = bridge.checkMyDetails(JSON.stringify(assistantDialog.values()))")
        assert ui.js('assistantDialog.faultIn("salary").msg') != "" and ui.js("assistantDialog.faultCount()") >= 3
    finally:
        ui.js("assistantDialog.dirty = false; assistantDialog.confirmClose = false; assistantDialog.problem = ({}); assistantDialog.close()")
        _until_closed(ui, "assistantDialog")
