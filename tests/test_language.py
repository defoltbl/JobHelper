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


# ── long English ads with a few Czech letters (found by the filtered-out list) ──
ENGLISH_AD = ("About us ČSOB is part of KBC Group which is an integrated bank-insurance group. We are looking for a "
              "colleague to join our team in Prague or Plzeň. You will build and validate risk models, work with the "
              "data and present the results. We offer flexible working hours and a friendly team. ") * 6


def test_a_long_english_ad_with_a_few_czech_letters_is_english():
    from jobhelper import language
    assert sum(ch in "čšžňřěýáíéůú" for ch in ENGLISH_AD.lower()) >= 3
    assert language.is_english(ENGLISH_AD) is True


def test_czech_text_is_still_czech_whatever_its_length():
    from jobhelper import language
    czech = "Hledáme vývojáře do našeho týmu. Nabízíme zajímavou práci, přátelský kolektiv a možnost růstu. " * 20
    assert language.is_english(czech) is False
    assert language.is_english("Softwarový vývojář") is False
    assert language.is_english("Vývojář") is True                     # too short to judge: kept, as before


def test_an_english_ad_inside_a_czech_page_frame_is_english():
    from jobhelper import language
    page = ("Nabídky práce Detail nabídky Aktualizováno včera UX Designer Plat neuveden. "
            + "We are looking for a designer who will work with our product team and the developers. "
              "You have experience with user research and you are able to present your work in English. " * 12)
    assert language.is_english(page) is True
