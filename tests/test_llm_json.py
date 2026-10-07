import pytest

from jobhelper import llm


def test_plain_json():
    assert llm._extract_json('{"a": 1}') == {"a": 1}


def test_json_with_surrounding_prose():
    assert llm._extract_json('Here is the result: {"a": 1, "b": [2, 3]} done') == {"a": 1, "b": [2, 3]}


def test_json_in_code_fence():
    assert llm._extract_json('```json\n{"x": true}\n```') == {"x": True}


def test_json_array():
    assert llm._extract_json("prefix [1, 2, 3] suffix") == [1, 2, 3]


def test_unparseable_raises():
    with pytest.raises(ValueError):
        llm._extract_json("no json here at all")
