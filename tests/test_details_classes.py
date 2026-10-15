"""My details as classes: DetailsProblem, RowList and its kinds, FileList, Salary, MyDetails (jobhelper/details.py)."""
import pytest

from jobhelper import details


def test_each_list_checks_its_own_rules():
    with pytest.raises(details.DetailsProblem) as caught:
        details.JobList().clean([{"employer": "Acme", "title": "Dev", "end": "2024", "current": True}])
    assert caught.value.as_dict() == {"field": "experience.0.end", "msg": "A current job has no end date. Clear “To”, or turn off “current”."}
    assert details.LanguageList().clean([{"language": "english", "level": "native"}]) == [{"language": "english", "level": "Native"}]
    with pytest.raises(details.DetailsProblem) as caught:
        details.LanguageList().clean([{"language": "English", "level": "Fluent"}, {"language": "english"}])
    assert caught.value.field == "languages.1.language"
    assert details.DegreeList().clean([{"school": ""}, {"school": "CTU", "start": "2019", "end": "2023"}])[0]["school"] == "CTU"   # an empty line is no degree
    with pytest.raises(details.DetailsProblem):
        details.DegreeList().clean([{"school": "CTU", "start": "2023", "end": "2019"}])
    assert set(details.LISTS) == {"experience", "education", "languages"}
    assert all(issubclass(kind, details.RowList) for kind in details.LISTS.values())


def test_the_salary_checks_and_writes_itself():
    pay = details.Salary.from_values({"salary_amount": "60 000", "salary_currency": "eur", "salary_period": "YEAR"})
    assert pay == details.Salary(60000, "EUR", "year") and pay.text().endswith("gross per year")
    assert details.Salary().text() == "" and details.Salary.of({}).to_dict() == {"salary_amount": 0, "salary_currency": "CZK", "salary_period": "month"}
    with pytest.raises(details.DetailsProblem) as caught:
        details.Salary.from_values({"salary_amount": "abc"})
    assert caught.value.field == "salary"


def test_check_still_answers_with_a_pair_and_my_details_reads_the_saved_values():
    clean, problem = details.check({"email": "bad@"})
    assert clean == {} and problem["field"] == "email"
    mine = details.MyDetails({"first_name": "Alex", "last_name": "Novak",
                              "experience": [{"employer": "A", "title": "T", "current": False}, {"employer": "B", "title": "U", "current": True}]})
    assert mine.full_name() == "Alex Novak" and [j["employer"] for j in mine.jobs()] == ["B", "A"]      # the current job first
    assert mine.any_given() and not details.MyDetails({}).any_given()
    assert mine.facts()[0] == "- Job: U at B (? to now) - a current job"
