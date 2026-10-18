"""The scripts the assistant runs on a page get their values as data, and every answer of a page is read by one rule."""
import json

import pytest

from jobhelper import form_fill


def test_values_go_into_a_script_as_data_never_as_code():
    script = "(function (n, text, on) { })(__N__, __TEXT__, __ON__)"
    typed = "Alex\"); alert(1); (\"</script>"
    out = form_fill.with_values(script, n=7, text=typed, on=True)
    assert out == "(function (n, text, on) { })(7, " + json.dumps(typed) + ", true)"
    assert form_fill.with_values("f(__WANTED__)", wanted=[1, 2]) == "f([1, 2])"
    assert form_fill.with_values("f(__URL__)") == "f(__URL__)", "a value not given is not guessed"
    assert form_fill.with_values("f(__A__, __B__)", a="__B__", b=1) == 'f("__B__", 1)', "what a person typed is never filled in again"
    filled = form_fill.fill_script([{"n": 1, "value": "See __URL__ and __TYPED__"}], "https://careers.example", typed=True)
    assert '"See __URL__ and __TYPED__"' in filled and filled.endswith('"https://careers.example", true)')
    assert form_fill.fill_script([], "u", typed=False).endswith('"u", false)')
    assert form_fill.attach_script(4, "k", "cv.pdf", "u").endswith('(4, "k", "cv.pdf", "application/pdf", "u")')


def test_every_builder_fills_all_of_its_values():
    built = [form_fill.choose_script("pick", 2, 5, "https://careers.example"), form_fill.fill_script([{"n": 1, "value": "x"}], "u"),
             form_fill.values_script([1], "u"), form_fill.empty_script([1], "u"), form_fill.attach_script(1, "k", "cv.pdf", "u"),
             *form_fill.put_scripts("k", b"abc")]
    for script in built:
        assert "__" not in script.replace("data-jobhelper", ""), script[-120:]


@pytest.mark.parametrize("text", ["", "null", "[]", "5", '"words"', "{", "<html>"])
def test_an_answer_that_is_not_an_object_is_refused_or_nothing(text):
    assert form_fill.page_reply(text) is None
    with pytest.raises(ValueError, match="Reload it"):
        form_fill.page_reply(text, "The page did not answer. Reload it and ask me again.")


def test_an_object_comes_back_as_it_is():
    assert form_fill.page_reply('{"ok": true, "n": [1]}') == {"ok": True, "n": [1]}
    with pytest.raises(ValueError, match="page with a form"):
        form_fill.read_answer('{"fields": "not a list"}')
    assert form_fill.read_answer('{"fields": []}')["fields"] == []


@pytest.mark.parametrize("text", ["", "[]", "not json"])
def test_each_reader_has_its_own_answer_for_a_page_that_said_nothing_usable(text):
    assert form_fill.choose_answer(text) == {"ok": False, "moved": False, "options": []}
    assert form_fill.watch_answer(text) == {"url": "", "sign": "", "empty": 0}
    assert form_fill.attach_answer(text) == {"ok": False, "moved": False, "why": "refused", "size": -1}
    assert form_fill.values_answer(text) == {} and form_fill.empty_answer(text) == []
    for reader, words in ((form_fill.fill_answer, "outlined fields were filled"), (form_fill.page_answer, "did not answer"),
                          (form_fill.review_answer, "page with a form"), (form_fill.read_answer, "page with a form")):
        with pytest.raises(ValueError, match=words):
            reader(text)
