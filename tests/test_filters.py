from jobhelper import filters


def test_drops_senior_for_junior():
    for title in ["Senior Python Developer", "Lead Data Engineer", "Engineering Manager",
                  "Principal Architect", "Head of Data", "Sr. Backend Engineer"]:
        assert filters.is_too_senior_for(title, "junior")


def test_keeps_junior_and_mid_titles():
    for title in ["Junior Python Developer", "Python Developer", "IT Support Specialist",
                  "QA Tester", "Help Desk Technician", "Medior Backend Developer"]:
        assert not filters.is_too_senior_for(title, "junior")


def test_senior_candidate_not_filtered():
    assert not filters.is_too_senior_for("Senior Python Developer", "senior")
    assert not filters.is_too_senior_for("Lead Engineer", "lead")


def test_mid_candidate_still_drops_senior():
    assert filters.is_too_senior_for("Senior Developer", "mid")


def test_requires_czech_detects_requirement():
    assert filters.requires_czech("Fluent Czech and English required.")
    assert filters.requires_czech("Czech language at B2 level is required")
    assert filters.requires_czech("Native Czech speaker.")
    assert filters.requires_czech("Knowledge of Czech is essential.")


def test_requires_czech_ignores_optional_and_location():
    assert not filters.requires_czech("Based in Prague, Czech Republic.")
    assert not filters.requires_czech("Czech language is a plus.")
    assert not filters.requires_czech("Czech would be an advantage.")
    assert not filters.requires_czech("English is required; Czech nice to have.")
    assert not filters.requires_czech("We build backend services in Python.")


def test_years_that_are_only_a_wish_do_not_count():
    assert filters.years_required("5 years of experience in a similar position is an advantage.") == 0
    assert filters.years_required("Ideally 6+ years of experience would be nice to have. 2 years of experience with Python.") == 2
    assert filters.years_required("You have 5+ years of experience with Java.") == 5
    assert filters.years_required("Requirements: 4+ years of commercial experience in software development") == 4


# ── a required language the CV does not show ────────────────────────────────
import pytest  # noqa: E402

CV_LANGS = ("Prague, Czech Republic\nNative Polish and Italian speaker, B2 English, seeking an English-speaking IT role.\n"
            "Recognized as equivalent to a Czech Master's degree.\nLANGUAGES\nPolish – Native   ·   Italian – Native   ·   English – B2   ·   Czech – Beginner")


def test_languages_read_from_a_cv():
    assert filters.cv_languages(CV_LANGS) == {"english", "russian", "ukrainian"}        # "Czech Master's" is not a language; Beginner does not count
    assert filters.cv_languages("German – C1 · French – A2 · Spanish (fluent)") == {"english", "german", "spanish"}
    assert filters.cv_languages("") == {"english"}


@pytest.mark.parametrize("text, groups", [
    ("Excellent communication skills in Czech or Slovak and English (B2+)", [["czech", "slovak"], ["english"]]),
    ("Fluency in Czech and at least B2-level English", [["czech"], ["english"]]),
    ("Fluent in Dutch or German or French, with English", [["dutch", "german", "french"], ["english"]]),
    ("Fluent French language skills (required)", [["french"]]),
    ("Native POLISH speaker", [["polish"]]),
    ("German is a plus.", []), ("Knowledge of Czech is an advantage", []),
    ("Czech is not required for this role, we communicate in English.", []),
    ("If you are multilingual, we can assign you to our German or Spanish customers.", []),
    ("We are a leader on the Czech market and work with German clients.", []),
    ("You will join our office in the Czech Republic.", []),
])
def test_required_languages(text, groups):
    assert filters.required_languages(text) == groups


def test_unmet_language_names_what_is_missing():
    assert filters.unmet_language("Excellent communication skills in Czech or Slovak and English (B2+)", CV_LANGS) == "Czech or Slovak"
    assert filters.unmet_language("Fluent English is required. Russian is a plus.", CV_LANGS) == ""
    assert filters.unmet_language("Fluent in Ukrainian or Polish.", CV_LANGS) == ""            # one of the alternatives is enough
    assert filters.unmet_language("Fluent German and English required.", "German – C1") == ""
