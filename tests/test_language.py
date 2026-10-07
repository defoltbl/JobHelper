from jobhelper import language


def test_english_text_is_english():
    assert language.is_english(
        "We are looking for a Python developer to join our team. "
        "You will work with our data platform and REST APIs."
    )


def test_czech_text_is_not_english():
    assert not language.is_english(
        "Hledáme vývojáře v jazyce Python. Nabízíme zajímavou práci a "
        "možnost odborného růstu. Požadujeme znalost a zkušenosti."
    )


def test_czech_diacritics_detected():
    assert not language.is_english("Softwarový vývojář pro naši společnost")


def test_short_or_empty_defaults_english():
    assert language.is_english("")
    assert language.is_english("DevOps")


def test_english_title_only():
    assert language.is_english("Senior Backend Engineer (Python)")
