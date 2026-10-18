"""One claim check for every text written in the person's voice (jobhelper/claims.py)."""
from jobhelper import claims, cover_letter, cv_tailor, interview_prep
from jobhelper.claims import ClaimCheck


def test_a_claim_is_hands_on_wording_about_a_technology_the_cv_lacks():
    check = ClaimCheck(["Kubernetes", "Kafka"])
    assert check.claimed_in("I deployed the service on Kubernetes.") == "Kubernetes"
    assert check.claimed_in("I would like to work with Kubernetes.") == ""                 # a wish
    assert check.claimed_in("Your team runs Kafka.") == ""                                 # the employer's platform
    assert check.claimed_in("I have experience with Python.") == ""                        # backed by the CV
    assert check.claimed_in("I have not used Kafka, but I have experience with queues.") == "Kafka"
    assert check.claimed_in("I have not used Kafka, but I have experience with queues.", honest_ok=True) == ""


def test_a_term_is_named_only_as_a_whole_word():
    assert claims.mentions("I used Go daily.", "Go") and not claims.mentions("I used Google Docs.", "Go")
    assert claims.mentions("We used C++ there.", "C++") and not claims.mentions("", "C++")


def test_unbacked_reads_every_sentence_and_names_the_first_claim():
    text = "I like data. I have built pipelines with Kafka. I also used Kubernetes."
    assert ClaimCheck(["Kubernetes", "Kafka"]).unbacked(text) == "Kafka"
    assert ClaimCheck([]).unbacked(text) == "" and ClaimCheck(None).unbacked(text) == ""


def test_a_text_that_names_the_person_talks_about_them_not_as_them():
    assert claims.names_candidate("Jordan built the tool.", "Jordan")
    assert not claims.names_candidate("I built the tool.", "Jordan") and not claims.names_candidate("Jordan built it.", "")
    assert not claims.names_candidate("Jordanian food.", "Jordan")


def test_the_note_sent_back_lists_every_problem():
    note = claims.rejected(["One.", "Two."], "draft")
    assert note == "\nYour previous draft was rejected. Fix these problems:\n- One.\n- Two.\n"


def test_letters_answers_and_interviews_share_the_one_check():
    """The rule used to live in cover_letter and be borrowed through private names; now each asks claims."""
    assert cover_letter._GAP is claims.GAP and cv_tailor.mentions is claims.mentions
    sentence = "I have deployed Kubernetes clusters."
    assert interview_prep.unbacked(sentence, ["Kubernetes"]) == ClaimCheck(["Kubernetes"]).unbacked(sentence, honest_ok=True)
    assert cover_letter.content_problems(["I deployed Kubernetes daily."], ["Kubernetes"])[-1].startswith("Paragraph 1 presents 'Kubernetes'")


def test_instruction_sections_keep_only_the_numbers_asked(tmp_path):
    rules = tmp_path / "rules.md"
    rules.write_text("# Title\n## 1. Keep\none\n## 2. Skip\ntwo\n## 10. Not one\nten\n## 4. Keep too\nfour\n", encoding="utf-8")
    assert cv_tailor.instruction_sections(rules, ("1", "4"), "", "fallback") == "## 1. Keep\none\n## 4. Keep too\nfour"
    assert cv_tailor.instruction_sections(rules, ("7",), "", "fallback") == "fallback"
    assert cv_tailor.instruction_sections(tmp_path / "missing.md", ("1",), "", "fallback") == "fallback"
