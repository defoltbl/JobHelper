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


def test_a_role_the_table_does_not_know_gets_no_figure():
    """It used to get 50 000 CZK, a junior software figure, whatever the profession."""
    for title in ("Chief Happiness Officer", "Registered Nurse", "Accountant", "Warehouse Operative", ""):
        assert salary.estimate(title, "junior") == (0, 0), title


def test_annual_is_twelve_months():
    m, a = salary.estimate("Data Analyst", "junior")
    assert a == m * 12


# ── your own figure, in your own currency ───────────────────────────────────
JOB = {"title": "Python Developer", "desired_monthly_czk": 58000}


def test_your_own_figure_comes_first():
    assert salary.asked(JOB, {"salary_target": 3200, "salary_currency": "EUR", "where": "Berlin"}) == (3200, "EUR", True)
    assert salary.asked(JOB, {"salary_target": 70000, "where": "Prague"}) == (70000, "CZK", True)
    assert salary.asked({}, {"salary_target": 4000, "salary_currency": "gbp"}) == (4000, "GBP", True)


def test_the_app_s_estimate_is_offered_in_czechia_only():
    assert salary.asked(JOB, {"where": "Prague"}) == (58000, "CZK", False)
    assert salary.asked(JOB, {"where": "Brno", "salary_currency": "EUR"}) == (58000, "CZK", False)      # the estimate is in crowns
    assert salary.asked(JOB, {}) == (58000, "CZK", False)                                               # no city yet: as before
    assert salary.asked(JOB, {"where": "Berlin"}) == (0, "CZK", False)
    assert salary.asked(JOB, {"where": "Berlin", "salary_currency": "EUR"}) == (0, "EUR", False)
    assert salary.asked(JOB, {"where": "Smallville"}) == (0, "CZK", False)                               # a place the app does not know
    assert salary.asked(JOB, {"where": "Smallville", "country": "Czechia"}) == (58000, "CZK", False)
    assert salary.asked({"title": "Nurse", "desired_monthly_czk": ""}, {"where": "Prague"}) == (0, "CZK", False)
    assert salary.asked({"desired_monthly_czk": "nonsense"}, {"salary_target": "nonsense", "salary_currency": "XXX"}) == (0, "CZK", False)


def test_a_posting_s_pay_is_given_in_your_currency():
    job = {"salary": "70 000 - 80 000 CZK"}
    assert salary.stated(job) == {"low": 70000, "high": 80000, "currency": "CZK", "text": "70 000 - 80 000 CZK"}
    euros = salary.stated(job, "EUR")
    assert (euros["low"], euros["high"], euros["currency"]) == (2800, 3200, "EUR")
    assert salary.stated({"salary": "€3,000 - €3,500"}, "EUR")["low"] == 3000
    assert salary.stated({"salary": "£45,000 per year"}, "GBP")["low"] == 3800           # 45 000 / 12, to the hundred
    assert salary.stated({"salary": "12 000 - 15 000 PLN"}, "PLN")["high"] == 15000
    assert salary.stated({"salary": "12 000 - 15 000 zł"})["low"] == 70000               # in crowns, roughly


def test_money_is_written_as_people_write_it():
    assert salary.money(60000) == "60 000 CZK" and salary.money(3200, "EUR") == "3 200 EUR"
    assert salary.span(55000, 65000) == "55–65k CZK" and salary.span(60000, 60000) == "60k CZK"
    assert salary.span(2600, 3200, "EUR") == "2 600–3 200 EUR" and salary.span(3000, 3000, "EUR") == "3 000 EUR"
    assert salary.tidy(58400) == 58000 and salary.tidy(2840) == 2800


def test_a_kind_of_role_can_have_its_own_figure():
    opts = {"where": "Prague", "salary_target": 60000, "salary_by_role": [{"role": "support", "amount": 42000}, {"role": "data engineer", "amount": 70000}]}
    assert salary.asked({"title": "IT Support Specialist"}, opts) == (42000, "CZK", True)
    assert salary.asked({"title": "Junior Data Engineer (m/f)"}, opts) == (70000, "CZK", True)
    assert salary.asked({"title": "Python Developer"}, opts) == (60000, "CZK", True)                 # no line for it: the general figure
    assert salary.asked({"title": "Supporter of Engineers"}, opts) == (60000, "CZK", True)           # whole words only
    assert salary.asked({"title": "Support"}, {"salary_by_role": [{"role": "support", "amount": 0}, "nonsense", {"role": "", "amount": 5}]}) == (0, "CZK", False)
    assert salary.asked({"title": "IT Support"}, {"where": "Berlin", "salary_currency": "EUR", "salary_by_role": [{"role": "support", "amount": 2800}]}) == (2800, "EUR", True)
