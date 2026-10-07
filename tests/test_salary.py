from jobhelper import salary


def test_estimate_junior_roles():
    m, a = salary.estimate("Python Developer", "junior")
    assert m == 58000 and a == 58000 * 12
    m2, _ = salary.estimate("IT Support Specialist", "junior")
    assert m2 == 42000
    m3, _ = salary.estimate("GenAI Engineer", "junior")
    assert m3 == 65000


def test_seniority_multiplier():
    jm, _ = salary.estimate("Backend Engineer", "junior")
    sm, _ = salary.estimate("Backend Engineer", "senior")
    assert sm > jm


def test_unknown_role_default():
    m, a = salary.estimate("Chief Happiness Officer", "junior")
    assert m == 50000 and a == 600000


def test_annual_is_twelve_months():
    m, a = salary.estimate("Data Analyst", "junior")
    assert a == m * 12
