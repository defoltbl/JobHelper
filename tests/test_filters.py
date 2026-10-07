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
