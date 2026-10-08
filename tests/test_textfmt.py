"""A scraped description is laid out for reading without changing a word."""
import re

from jobhelper import textfmt

BRIGHTLINE = ("About BRIGHTLINE BRIGHTLINE is an AI robotics company developing physical intelligence for general-purpose humanoid robots. "
         "This role is on-site with our engineering team in the Czech Republic. Responsibilities 3+ years of relevant professional "
         "experience Train and evaluate models Requirements Strong Python and PyTorch Robot learning, imitation or RL experience "
         "Bonus qualifications Biosignal ML NVIDIA Isaac Sim Bonuses Work That Ships: We capture how skilled humans work. You put "
         "robots on a paying customer's floor The Team: Colleagues from NVIDIA and founders you work with directly Equity for Key "
         "Roles: For select positions, stock options How to apply Apply through the link on this posting. Compensation Range: "
         "€65K - €108K Show more Show less")


def _words(text):
    return re.sub(r"\W+", "", text).lower()


def test_headings_and_list_items_get_their_own_lines():
    out = textfmt.readable(BRIGHTLINE)
    lines = out.split("\n")
    for heading in ("RESPONSIBILITIES", "REQUIREMENTS", "BONUS QUALIFICATIONS", "BONUSES", "HOW TO APPLY", "COMPENSATION RANGE"):
        assert heading in lines, heading
    assert "• Work That Ships: We capture how skilled humans work. You put robots on a paying customer's floor" in lines
    assert any(line.startswith("• The Team: Colleagues from NVIDIA") for line in lines)
    assert any(line.startswith("• Equity for Key Roles:") for line in lines)
    assert lines[lines.index("COMPENSATION RANGE") + 1] == "€65K - €108K"
    assert "Show more" not in out and "Show less" not in out


def test_no_word_is_changed():
    assert _words(textfmt.readable(BRIGHTLINE)) == _words(BRIGHTLINE.replace("Show more Show less", ""))


def test_a_heading_word_inside_a_sentence_is_left_alone():
    text = "We need someone with strong experience in Python and good skills in SQL. You will gain experience quickly."
    assert textfmt.readable(text) == text


def test_a_long_paragraph_is_split_at_sentences():
    text = " ".join(f"Sentence number {i} says something about the work and the team here." for i in range(14))
    out = textfmt.readable(text)
    assert out.count("\n\n") >= 2 and all(len(block) <= 450 for block in out.split("\n\n")) and _words(out) == _words(text)


def test_text_that_already_has_lines_is_only_tidied():
    text = "Line one\n\n\n\nLine two   \nLine three\n• item\n• item two\nLast"
    assert textfmt.readable(text) == "Line one\n\nLine two\nLine three\n• item\n• item two\nLast"


def test_inline_bullets_and_empty_input():
    assert textfmt.readable("We offer • Flexible hours • Home office • Meal vouchers") == "WE OFFER\n• Flexible hours\n• Home office\n• Meal vouchers"
    assert textfmt.readable("") == "" and textfmt.readable(None) == "" and textfmt.readable("  Show more Show less ") == ""
