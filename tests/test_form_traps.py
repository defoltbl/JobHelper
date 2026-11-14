"""Robot traps a person cannot see (#77, #91): the boxes the form filler leaves out, and the real fields beside them that it
still fills. The pages are served from this machine and run in a real browser engine; nothing here touches Chrome,
Claude, the Keychain or real data."""
import json
import os
import subprocess
import sys

import pytest

from jobhelper import chrome, details, form_fill, form_run
from tests import test_assistant as ta
from tests.conftest import FIXTURES
from tests.test_form_run import _App

# The test area and run_in_page.py draw no window: the page has no width or height, so the rules that measure by the window
# (screens away to the side, covered by another box, a right-to-left page scrolled sideways) need a drawn one.
_DRAWN = r"""
import json, sys
from PySide6.QtCore import QCoreApplication, Qt, QTimer, QUrl
from PySide6.QtWidgets import QApplication
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
app = QApplication(sys.argv[:1])
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
view = QWebEngineView()
view.page().settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
view.resize(760, 1500)
view.show()
script = sys.stdin.read()
def done(result):
    print(json.dumps(result))
    app.quit()
view.loadFinished.connect(lambda ok: QTimer.singleShot(150, lambda: view.page().runJavaScript(script, 0, done)) if ok else app.exit(2))
view.load(QUrl.fromLocalFile(sys.argv[1]))
QTimer.singleShot(40000, lambda: app.exit(3))
sys.exit(app.exec())
"""


def _drawn(page, script):
    """What the script answers on a page drawn in a 760 x 1500 window (there typing arrives too: execCommand works)."""
    done = subprocess.run([sys.executable, "-c", _DRAWN, str(FIXTURES / "forms" / page)], input=script,
                          capture_output=True, text=True, timeout=120, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert "Traceback" not in done.stderr, done.stderr[-1500:]       # the runner itself is broken: that is a failure, not a skip
    if done.returncode != 0:
        ta._engine_did_not_start(done)
    return json.loads(done.stdout)


def _read_drawn(page, before=""):
    """The fields READ reports on a drawn page; `before` runs in the same task, just before READ."""
    return {f["id"] for f in form_fill.read_answer(_drawn(page, before + "\n" + form_fill.READ))["fields"]}


REAL = {"fn", "ln", "em", "city", "pc", "st", "w1", "w2", "w5", "w6", "wc", "tool"}
TRAPS = {"hpa1", "hpa2", "hpb1", "hpb2", "hpc1", "hpc2", "hpd", "hpe", "hpf1", "hpf2", "hpg", "hph", "hpi", "hpj", "snack"}


def test_area_traps_a_person_cannot_see_stay_empty_and_the_fields_beside_them_are_filled():
    """#91: a parent of no height, the "visually hidden" class, a 2 px dot, a box at 1 % opacity, an inert part, a box no click
    reaches, a hidden frame, a field scrolled out in a closed component and a see-through menu were all filled or opened.
    A floating label, a card with round corners, a sheet that scrolls, a sticky title and a small tick box are no trap."""
    out = ta._area("hidden_boxes.html")
    state = out["state"]
    assert state["fn"] == "Alex" and state["ln"] == "Novak", "a floating label lies over the last name"
    assert state["em"] == ta.MINE["email"], "a card with round corners keeps its box"
    assert state["city"] == ta.MINE["city"] and state["pc"] == ta.MINE["postcode"], "a sheet that scrolls"
    assert state["st"] == "Long Street 5", "under the sticky title of its sheet"
    assert state["wc"] is True, "the 16 px box is ticked for the job that goes on"
    assert out["menus"].get("tool") == "SQL", "the page's own menu a person sees"
    # hpc1, hpc2 and hph need a drawn window to be told apart: the next test
    left = {"hpa1", "hpa2", "hpb1", "hpb2", "hpd", "hpe", "hpf1", "hpf2", "hpg", "hpi", "hpj"}
    assert {k: state[k] for k in left if state[k] != ""} == {}, "no trap is filled"
    assert "snack" not in out["opened"], "a see-through menu is never opened"


def test_area_traps_that_need_a_window_are_left_out_where_the_page_is_drawn():
    """#91: a box screens away to the right, moved there by a transform, or covered by another box was reported; a floating
    label, a sheet scrolled past a field still on the screen, and a sticky title over a field must not read as a cover."""
    ids = _read_drawn("hidden_boxes.html")
    assert REAL <= ids, REAL - ids
    assert ids & TRAPS == set(), "no trap is even reported"


def test_area_a_right_to_left_page_scrolled_to_its_left_end_keeps_its_fields():
    """#91: on a right-to-left page the scroll runs to negative numbers. Scrolled to its left end, the fields there (and in a
    right-to-left box scrolled the same way) read as placed left of the page."""
    ids = _read_drawn("rtl.html")
    assert {"fn", "ln", "em"} <= ids, "the fields at the left end, and the one at the right end the person scrolled away from"
    assert not ids & {"hp1", "hp2"}, "right of where the page starts, and screens away to its left"


# boxes beside the form, made by the page in the same task as the reading
BOXES = """
  var at = document.createElement('div');
  at.style.cssText = 'position: absolute; top: 40px; left: 340px; width: 180px';
  document.body.appendChild(at);
  function box(id, css) {
    var p = document.createElement('p'), el = document.createElement('input');
    el.id = id; el.setAttribute('aria-label', 'Note ' + id); el.style.cssText = 'width: 150px;' + (css || '');
    p.appendChild(el); at.appendChild(p); return el;
  }"""
FADES = "(function () {" + BOXES + """
  var soon = box('fade_soon', 'opacity: 0; transition: opacity 0.5s'), late = box('fade_late', 'opacity: 0; transition: opacity 0.4s 5s');
  getComputedStyle(soon).opacity; getComputedStyle(late).opacity;          // both start to fade in now
  soon.style.opacity = '1'; late.style.opacity = '1';
  var turn = [{transform: 'rotate(0deg)'}, {transform: 'rotate(360deg)'}], show = [{opacity: 0}, {opacity: 1}];
  box('spin', 'opacity: 0').animate(turn, {duration: 1000, iterations: Infinity});
  box('fade_minute', 'opacity: 0').animate(show, 60000);
  box('fade_loop', 'opacity: 0').animate(show, {duration: 500, iterations: Infinity});
  var step = box('in_step');                                                  // a step fading in, with a box that turns inside it
  step.parentNode.animate(show, 1000);
  step.animate(turn, {duration: 1000, iterations: Infinity});
})();"""


def test_area_a_see_through_box_is_fading_in_only_when_its_fade_ends_soon():
    """#91 (owner decisions 1-3): any animation passed for a fade. Now only an opacity animation that ends within about 2 s
    does, asked of the first see-through box alone; the fades start in the same task as the reading, so no wait decides."""
    ids = _read_drawn("hidden_boxes.html", FADES)
    assert {"fade_soon", "in_step"} <= ids, "a fade that ends soon, also of the step around a turning box"
    assert not ids & {"fade_late", "spin", "fade_minute", "fade_loop"}, "a late fade, a turn, a minute's fade, a fade for ever"


FADES_AWAY = "(function () {" + BOXES + """
  var show = [{opacity: 0}, {opacity: 1}];
  box('fade_tiny', 'opacity: 0').animate([{opacity: 0}, {opacity: 0.01}], 500);
  box('fade_none', 'opacity: 0').animate([{opacity: 0}, {opacity: 0}], 500);
  box('fade_out', 'opacity: 0').animate([{opacity: 0.05}, {opacity: 0}], 500);
  var gone = box('fade_trans_out', 'opacity: 0.05; transition: opacity 0.5s');
  getComputedStyle(gone).opacity; gone.style.opacity = '0';
  box('fade_back', 'opacity: 0').animate(show, {duration: 500, delay: 200, direction: 'reverse'});
  box('fade_still', 'opacity: 0').animate(show, 500).playbackRate = 0;
  box('fade_fast', 'opacity: 0').animate(show, 4000).playbackRate = 4;
})();"""


def test_area_a_fade_that_ends_see_through_is_no_fade_in():
    """#91: any opacity animation that ended within 2 s passed for a fade-in, also one to 1 % opacity, from nothing to nothing,
    a fade-out, one played backwards and one that stands still. The opacity it ends at decides; the time left counts its speed."""
    ids = _read_drawn("hidden_boxes.html", FADES_AWAY)
    assert "fade_fast" in ids, "a 4 s fade played four times as fast ends in 1 s"
    assert not ids & {"fade_tiny", "fade_none", "fade_out", "fade_trans_out", "fade_back", "fade_still"}, ids


def test_area_a_menu_that_makes_the_page_under_it_take_no_click_is_still_read_picked_and_closed():
    """#91: CHOOSE asked whether a person sees the menu before every step. A menu drawn like Radix or shadcn sets
    pointer-events: none on the page while it is open, so it was opened and then never read, picked or closed."""
    out = ta._area("pointer_menu.html")
    assert out["menus"] == {"tool": "SQL"}, out["menus"]
    assert out["state"]["fn"] == "Alex" and out["state"]["ln"] == "Novak"


SIGNED = "box.setAttribute('data-jobhelper', '50'); box.setAttribute('data-jobhelper-sign', 'INPUT|tel|phone_frame|hp_frame');"
FRAMED = "document.getElementById('faint_frame').contentDocument.getElementById('hp_frame')"


def test_area_a_mark_planted_in_a_hidden_frame_is_taken_off_and_never_written():
    """#91: READ skipped a frame out of sight but left any mark a page planted in it, and FILL, ATTACH and CHOOSE asked sight only
    of the box, never of the frame around it: a mark planted there with the right stamp had the box written."""
    plant = "(function () { var box = " + FRAMED + "; " + SIGNED + " return 'ok'; })()"
    fill = form_fill.fill_script([{"n": 50, "value": "123 456 789"}], "X").replace('"X", false)', "location.href, false)")
    _, read, left, _, said, value = ta._in_page(plant, form_fill.READ, "String(" + FRAMED + ".attributes.length)", plant, fill,
                                                FRAMED + ".value", page="out_of_sight.html")
    assert "hp_frame" not in {f["id"] for f in form_fill.read_answer(read)["fields"]}
    assert left == "3", "READ takes the planted mark and stamp off: only id, type and name stay"
    assert form_fill.fill_answer(said)["skipped"] == [50] and value == "", "a mark planted after READ: the box is never written"


def test_area_a_box_that_breaks_the_measuring_is_left_out_and_the_rest_is_read():
    """#91: a page whose box throws when it is measured made READ fail as a whole. That box is not known to be seen: it is left
    out, and the other fields are read."""
    breaks = "document.getElementById('breaks').getBoundingClientRect = function () { throw new Error('no size'); }; 'ok'"
    _, read = ta._in_page(breaks, form_fill.READ, page="out_of_sight.html")
    ids = {f["id"] for f in form_fill.read_answer(read)["fields"]}
    assert "breaks" not in ids and {"fn", "ln", "em", "city"} <= ids, ids


HIDDEN = {"hp_product", "hp_circle", "hp_ellipse", "hp_line", "hp_frame"}


def test_area_see_through_parents_and_shapes_with_no_area_are_traps():
    """#91: two parents at 30 % opacity each (9 % together), a clip-path circle or ellipse of no radius and a polygon on one line
    read as boxes a person sees. A round clip that keeps the whole box stays a field."""
    ids = {f["id"] for f in form_fill.read_answer(ta._in_page(form_fill.READ, page="out_of_sight.html")[0])["fields"]}
    assert {"fn", "ln", "em", "city", "breaks", "team"} <= ids and not ids & HIDDEN, ids


def test_area_another_fields_label_or_a_block_of_words_over_a_box_is_a_cover():
    """#91: any label and any words over the middle of a box were taken for its own label, so a honeypot under another field's
    label or under a block of text read as a field. A list's own "Select..." over its small search box is still no cover."""
    ids = _read_drawn("out_of_sight.html")
    assert {"fn", "ln", "em", "city", "breaks", "team"} <= ids, ids
    assert not ids & ({"hp_foreign", "hp_words"} | HIDDEN), ids


def test_area_review_and_watch_leave_out_what_a_person_cannot_see():
    """#91: REVIEW and WATCH counted every box of 2 px or more, so a box READ left out as a trap was checked as a field the
    person left empty and counted as one of the page's fields."""
    review, watch = ta._in_page(form_fill.REVIEW, form_fill.WATCH, page="out_of_sight.html")
    ids = {f["id"] for f in json.loads(review)["fields"]}
    assert {"fn", "ln", "em", "city"} <= ids and not ids & HIDDEN, ids
    assert len(form_fill.review_answer(review)["fields"]) == len(ids), "the checked answer keeps every field the page reported"
    names = set(json.loads(watch)["first"].split("|"))
    assert "first_name" in names and not names & {"phone_check", "homepage", "email_check", "city_check"}, names


def test_area_a_hidden_file_field_with_nothing_to_open_it_is_left_to_the_person():
    """#91 (owner's decision): a file field the page hides, with no label and no button of its own beside it, got the CV by its
    name alone. It is the page's own tool: the person is told to use the page's buttons, and nothing is attached."""
    out = ta._area("out_of_sight.html", jobs=ta.FILE_JOBS, files=ta.FILES)
    assert out["state"]["hp_file"] == 0 and out["left"].get("Files") == form_fill.FILE_BUTTON, out["left"]


def test_area_a_hidden_file_field_opened_by_a_zone_a_link_or_a_click_box_is_attached_to():
    """#91: only a button or a label up to 3 parents out counted as a way to open a hidden file field, so a drop zone, a span or a
    link the page draws to open it, or an "Attach" link past four wrappers, made a real upload one left to the person."""
    fields = form_fill.read_answer(_drawn("press_targets.html", form_fill.READ))["fields"]
    bare = {f["id"]: f["bare"] for f in fields if f["id"] in {"drop", "by_span", "by_link", "by_click", "far", "none"}}
    assert bare == {"drop": False, "by_span": False, "by_link": False, "by_click": False, "far": False, "none": True}, bare


FADES_BACK = "(function () {" + BOXES + """
  // see-through for most of 100 s, visible in its first second: played backwards it is seen only once it is back at its start
  var show = [{opacity: 1}, {opacity: 0, offset: 0.01}, {opacity: 0}];
  var soon = box('back_soon', 'opacity: 0').animate(show, 100000); soon.currentTime = 1500; soon.playbackRate = -1;
  var late = box('back_late', 'opacity: 0').animate(show, 100000); late.currentTime = 30000; late.playbackRate = -1;
})();"""


def test_area_a_fade_played_backwards_counts_the_time_left_down_to_its_start():
    """#91: a fade played backwards was timed to its end, not to its start where it stops, so one done in 1 s read as a minute's."""
    ids = _read_drawn("hidden_boxes.html", FADES_BACK)
    assert "back_soon" in ids and "back_late" not in ids, ids


def _left(out):
    return {i["label"]: i["why"] for i in out["result"]["left"]}


def test_area_a_mark_the_page_copies_onto_a_hidden_box_writes_into_neither():
    """#91: FILL took the last box with a mark, so a page script that copied the mark of the first name onto a hidden box after
    READ had that box written. A mark on two boxes is refused, and the run says the field was not taken."""
    out = ta._area("marks_moved.html")
    assert out["state"]["fn_twin"] == "" and out["state"]["fn"] == "", "neither box with the copied mark is written"
    assert "First name" in _left(out) and out["state"]["ln"] == "Novak", "the field is reported, the rest of the form is filled"


def test_area_a_mark_the_page_moves_to_another_box_writes_nothing_there():
    """#91: a page script that moved the mark of the email (with all the filler put on it) to a box with another name had that
    box written. The box must still be the one READ saw: same kind, name and id."""
    out = ta._area("marks_moved.html")
    assert out["state"]["nick"] == "", "the email never goes into the other box"
    assert "Email" in _left(out) and "Email" not in {f["label"] for f in out["result"]["filled"]}


def test_area_a_page_that_keeps_only_typing_and_passes_the_focus_on_gets_the_value_in_its_own_box():
    """#91, the whole run: a page that keeps only typing and passes the focus on gets the value in the box itself, the way
    typing arrives, and the other box stays empty. (Typing does not arrive here: the drawn test below shows the hole.)"""
    out = ta._area("focus_moves.html")
    assert out["state"]["other"] == "", "the box that took the focus is never written"
    assert out["state"]["fn"] == "Alex" and "First name" in {f["label"] for f in out["result"]["filled"]}


def test_area_typed_writing_never_goes_into_the_box_the_page_passed_the_focus_to_where_typing_arrives():
    """#91: on a drawn page typing arrives (execCommand), and it went into the box the page had passed the focus to. It is
    used only when the box in front is the box to write; else the value goes into the box itself."""
    fill = form_fill.fill_script([{"n": 1, "value": "Alex"}], "X", typed=True).replace('"X", true)', "location.href, true)")
    out = json.loads(_drawn("focus_moves.html", "(function () { var read = " + form_fill.READ + "; var done = " + fill + ";"
                            " return JSON.stringify({read: JSON.parse(read).fields.map(function (f) { return f.id; }), done: JSON.parse(done),"
                            " fn: document.getElementById('fn').value, other: document.getElementById('other').value}); })()"))
    assert out["read"] == ["fn", "ln"] and out["done"]["done"] == [1], out
    assert out["other"] == "" and out["fn"] == "Alex", out


MARKED = "String(document.querySelectorAll('[data-jobhelper], [data-jobhelper-opt], [data-jobhelper-sign]').length)"


def test_area_read_for_another_host_marks_nothing_on_the_page():
    """#91: READ marked the fields of whatever page was in front, and only then was its host compared."""
    moved, marks, plain, marked = ta._in_page(form_fill.read_script("careers.example"), MARKED, form_fill.READ, MARKED)
    assert form_fill.read_answer(moved)["moved"] is True and marks == "0", "a page of another host: nothing is marked"
    assert form_fill.read_answer(plain)["fields"] and int(marked) > 0, "READ itself checks no host"
    assert form_fill.read_script("Careers.Example") == form_fill.read_script("careers.example")


def test_the_run_reads_the_form_for_the_host_of_the_tab_and_writes_nothing_when_it_moved(isolate_data, monkeypatch):
    """#91: the run sent READ with no host, so a tab that changed to another site had its fields marked before the check."""
    details.save(ta.MINE)
    monkeypatch.setattr(chrome, "active_tab", lambda: {"url": "https://Careers.Northwind.example/jobs/42", "title": "Apply"})
    sent = []
    monkeypatch.setattr(chrome, "run", lambda script: sent.append(script) or json.dumps({"moved": True, "url": "https://other.example/"}))
    out = form_run.FormFillRun(_App(), editor=None, cv=None).result()
    assert sent == [form_fill.read_script("careers.northwind.example")] and sent[0] != form_fill.READ, "one READ, for the tab's host"
    assert out["ok"] is False and out["msg"].startswith("The tab changed while I was reading"), out


@pytest.mark.parametrize("answer, said", [({"url": "about:blank", "title": "", "fields": []}, form_run.FormFillRun.LOADING),
                                          ({"url": "", "title": "", "fields": []}, form_run.FormFillRun.LOADING),
                                          ({"moved": True, "url": "https://other.example/"}, "The tab changed while I was reading")])
def test_an_empty_page_in_front_says_it_is_loading_not_that_the_tab_changed(isolate_data, monkeypatch, answer, said):
    """#91: a page still loading (about:blank, no address yet) was reported as a changed tab."""
    details.save(ta.MINE)
    monkeypatch.setattr(chrome, "active_tab", lambda: {"url": "https://careers.example/apply", "title": "Apply"})
    monkeypatch.setattr(chrome, "run", lambda script: json.dumps(answer))
    out = form_run.FormFillRun(_App(), editor=None, cv=None).result()
    assert out["ok"] is False and out["msg"].startswith(said), out


# A page script that, after READ, copies every marked box to a hidden twin after it (the last one on the page), or moves the
# marks (with all the filler put on them) to a twin beside it that a person sees.
TWINS = """(function (move) {
  document.querySelectorAll('[data-jobhelper], [data-jobhelper-opt]').forEach(function (el) {
    var twin = el.cloneNode(false);
    twin.id = el.id + '_twin';
    if (move) { el.parentNode.insertBefore(twin, el.nextSibling); ['data-jobhelper', 'data-jobhelper-opt', 'data-jobhelper-sign'].forEach(function (a) { el.removeAttribute(a); }); }
    else { twin.style.cssText = 'position: absolute; left: -10000px; top: 0'; document.body.appendChild(twin); }
  });
  window.__jobhelper_k = btoa('%PDF-1.4 a CV');
  return 'ok';
})(MOVE)"""
HERE = '"X")'
STATE = ("JSON.stringify({ry: document.getElementById('ry').checked, twin: document.getElementById('ry_twin').checked,"
         " cv: document.getElementById('cv').files.length, cv_twin: document.getElementById('cv_twin').files.length})")


def _doubled(move, script):
    read, made, said, state = ta._in_page(form_fill.READ, TWINS.replace("(MOVE)", "(true)" if move else "(false)"), script.replace(HERE, "location.href)"), STATE,
                                          page="doubled.html")
    fields = {f["id"] or f["name"]: f["n"] for f in form_fill.read_answer(read)["fields"]}
    assert fields == {"fn": 1, "remote": 2, "cv": 3} and made == "ok", fields     # the numbers the scripts below were built for
    return said, json.loads(state)


@pytest.mark.parametrize("move", [False, True], ids=["copied", "moved"])
def test_area_choose_never_presses_a_radio_button_whose_mark_the_page_copied_or_moved(move):
    said, state = _doubled(move, form_fill.choose_script("radio", 2, 0, "X"))
    assert form_fill.choose_answer(said)["ok"] is False and state["ry"] is False and state["twin"] is False


@pytest.mark.parametrize("move", [False, True], ids=["copied", "moved"])
def test_area_attach_never_gives_the_file_to_a_box_whose_mark_the_page_copied_or_moved(move):
    said, state = _doubled(move, form_fill.attach_script(3, "__jobhelper_k", "cv.pdf", "X"))
    assert form_fill.attach_answer(said)["why"] == "gone" and state["cv"] == 0 and state["cv_twin"] == 0


@pytest.mark.parametrize("move", [False, True], ids=["copied", "moved"])
def test_area_the_look_after_a_fill_counts_a_copied_or_moved_mark_as_not_known_to_hold_it(move):
    said, _ = _doubled(move, form_fill.empty_script([1], "X"))
    assert form_fill.empty_answer(said) == [1], "both boxes hold the name, yet neither is known to be the field"


@pytest.mark.parametrize("move", [False, True], ids=["copied", "moved"])
def test_area_what_a_field_holds_now_leaves_out_a_copied_or_moved_mark(move):
    said, _ = _doubled(move, form_fill.values_script([1], "X"))
    assert form_fill.values_answer(said) == {}, "what the other box holds is never saved as your answer"
