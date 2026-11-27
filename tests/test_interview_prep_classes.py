"""The parts of an interview preparation as small classes (jobhelper/interview_prep.py)."""
from jobhelper import interview_prep as ip


def test_each_part_cleans_itself_and_refuses_what_is_unusable():
    q = ip.Question.from_reply({"question": "Why us?", "answer": "I like robots.", "kind": "odd", "audience": ""})
    assert q.to_dict() == {"audience": "hr", "kind": "about you", "question": "Why us?", "why": "", "answer": "I like robots."}
    assert ip.Question.from_reply({"question": "No answer"}) is None
    assert ip.Question.from_reply({"question": "Tell me about PPO.", "answer": "I used it.", "kind": "technical"}).audience == "technical"
    assert ip.Tool.from_reply({"tool": "PyTorch", "use": ""}) is None                              # a tool that did nothing is no tool
    project = ip.Project.from_reply({"name": "Agent", "what": "I built it.", "tools": "PyTorch",
                                     "tech": [{"tool": "PyTorch", "about": "A library.", "use": "It trained the model.", "why": "It is fast."}, "junk"]})
    assert project.tools == ["PyTorch"] and [t.tool for t in project.tech] == ["PyTorch"]           # one sentence where a list was asked: one item
    assert project.to_dict()["tech"] == [{"tool": "PyTorch", "about": "A library.", "use": "It trained the model.", "why": "It is fast."}]
    assert ip.Project.from_reply({"name": "", "what": "x"}) is None and ip.Skill.from_reply({"skill": "Python", "proof": ""}) is None
    assert ip.WorkStory.from_reply({"job": "Intern, Acme", "story": "I wrote tests."}).to_dict()["gained"] == []


def test_a_preparation_holds_everything_said_in_your_voice_to_the_cv():
    prep = ip.Preparation.from_reply({
        "questions": [{"question": "Tech?", "answer": "I deployed it with Kubernetes.", "kind": "technical", "audience": "technical"},
                      {"question": "You?", "answer": "I am Alex and I like data.", "kind": "about you", "audience": "hr"}],
        "pitch": "I build agents.", "projects": [{"name": "Agent", "what": "I built it.", "plain": "A game program.",
                                                  "tech": [{"tool": "Kubernetes", "about": "Runs containers.", "use": "I ran it on Kubernetes.", "why": "It scales."}]}],
        "skills": [{"skill": "Python", "proof": "Every project.", "detail": "I wrote the loop."}]})
    saved = prep.as_dict()
    assert [q["audience"] for q in saved["questions"]] == ["hr", "technical"]                     # HR first, as the documents read them
    where = [w for w, _ in prep.voice()]
    assert "The opening pitch" in where and "The project Agent" in where and "The project Agent for HR" in where and "The skill Python" in where
    bad, third = prep.problems(["Kubernetes"], "Alex")
    # what the model is asked to fix is what the user sees marked: the tool's use too, not only the answers
    assert bad == [('The answer to "Tech?"', "Kubernetes"), ("What Kubernetes did in Agent", "Kubernetes")]
    assert third == ['The answer to "You?"']
    prep.mark(["Kubernetes"])
    assert saved["questions"][1]["check"] == "Kubernetes" and saved["questions"][0]["check"] == ""
    assert saved["checks"] == ["What Kubernetes did in Agent mentions Kubernetes as experience, which is not in your CV."]


def test_the_retry_and_the_marks_read_the_same_parts():
    """Before, the plain stories and the words about the company were sent back but never marked, and a skill's proof
    and a tool's use were marked but never sent back: one list now serves both."""
    prep = ip.Preparation.from_reply({
        "questions": [{"question": "Q", "answer": "A plain answer.", "kind": "about you", "audience": "hr"}],
        "company_say": "I have used Kafka in production for years.",
        "experience": [{"job": "Intern, Acme", "story": "I wrote tests.", "plain": "I ran Kafka every day."}],
        "skills": [{"skill": "Python", "proof": "I deployed Kafka with it.", "detail": ""}]})
    bad, _ = prep.problems(["Kafka"])
    prep.mark(["Kafka"])
    sent = [where for where, _ in bad]
    marked = [c.split(" mentions ")[0] for c in prep.as_dict()["checks"]]
    assert sent == marked == ["What to say about the company", "The plain story about Intern, Acme", "The skill Python"]


def test_an_honest_bridge_is_fine_in_an_interview_but_not_a_claim():
    assert ip.unbacked("I have not used Kafka; the closest I have done is RabbitMQ.", ["Kafka"]) == ""
    assert ip.unbacked("I have worked with Kafka for two years.", ["Kafka"]) == "Kafka"
    assert ip.unbacked("I would like to work with Kafka.", ["Kafka"]) == ""


def test_who_asks_a_question_is_one_rule_for_the_sheet_and_the_documents():
    from jobhelper import prep_doc
    assert prep_doc.audience_of is ip.audience_of and prep_doc.AUDIENCES == ip.AUDIENCES
    assert ip.audience_of({"kind": "technical"}) == "technical" and ip.audience_of({"kind": "about you"}) == "hr"
    assert ip.audience_of({"audience": "HR ", "kind": "technical"}) == "hr" and ip.audience_of({"audience": "odd", "kind": "your projects"}) == "technical"


def test_editing_by_hand_runs_the_same_check_as_making_it():
    prep = ip.Preparation.from_reply({"questions": [{"question": "Q", "answer": "A plain answer.", "kind": "about you", "audience": "hr"}],
                                      "projects": [{"name": "Agent", "what": "I built it.",
                                                    "tech": [{"tool": "Docker", "about": "Containers.", "use": "It packed the app.", "why": "Same everywhere."}]}]}).as_dict()
    new, problem = ip.apply_parts(prep, [{"key": "projects.0.what", "text": "I built it and ran it on Kubernetes."}], cv_text="I know Python and Docker.")
    assert problem == "" and new["checks"] == ["The project Agent mentions Kubernetes as experience, which is not in your CV."]
    # the CV could not be read this time: the checks stay as they were, they are not wiped
    again, problem = ip.apply_parts(new, [{"key": "projects.0.what", "text": "I built it and ran it on Kubernetes, at scale."}], cv_text="")
    assert problem == "" and again["checks"] == new["checks"]



def test_editing_by_hand_knows_the_company_the_preparation_is_for(isolate_data):
    """Review of #149: after an edit, "Contoso Labs" (the company written to) was read as the former "Fabrikam Labs"."""
    from tests.test_claims import TWO_JOBS
    prep = ip.Preparation.from_reply({"questions": [{"question": "Why us?", "answer": "A plain answer.", "kind": "about you", "audience": "hr"}]}).as_dict()
    edit = [{"key": "questions.0.answer", "text": "At Contoso Labs I would build REST APIs."}]
    new, problem = ip.apply_parts(prep, edit, TWO_JOBS, company="Contoso Labs")
    assert problem == "" and new["checks"] == []
    blind, _ = ip.apply_parts(prep, edit, TWO_JOBS)
    assert any("at Fabrikam Labs" in c for c in blind["checks"]), "without the company the same edit is marked"


def test_saving_edited_parts_passes_the_job_s_company(isolate_data, monkeypatch):
    from jobhelper import api_core, config, store, ui_api
    from tests.test_claims import TWO_JOBS
    config.ensure_dirs()
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: TWO_JOBS)
    store.save_jobs([store.new_job(id="a", title="Developer", company="Contoso Labs", status="interview")])
    api = ui_api.Api()
    prep = ip.Preparation.from_reply({"questions": [{"question": "Why us?", "answer": "A plain answer.", "kind": "about you", "audience": "hr"}]}).as_dict()
    api.editor.change("a", lambda jobs, j: j.update(interview_prep=prep), render=False)
    assert api.save_prep_parts("a", [{"key": "questions.0.answer", "text": "At Contoso Labs I would build REST APIs."}]) == {"ok": True, "to_check": 0}


PLACED_CV = """Mira Testova
Junior Developer
EXPERIENCE
Junior Developer – Kestrel Freight (2023 – present): built Django REST endpoints and wrote pytest suites.
KEY SKILLS
Python, Docker, Git
"""
_PLACED = {"summary": "s", "pitch": "I build web services in Python.",
           "questions": [{"kind": "technical", "question": "How do you work with others?", "why": "",
                          "answer": "In my current role I branch and review every change in Git."}]}
_FIXED = {"summary": "s", "pitch": "I build web services in Python.",
          "questions": [{"kind": "technical", "question": "How do you work with others?", "why": "",
                         "answer": "I know Git well and review changes with care."}]}


def test_a_skills_only_tool_placed_in_my_current_role_is_sent_back_once(isolate_data, monkeypatch):
    """#149: the sheet put a tool of the skills list "in my current role"; the model is told so once, and a fixed sheet
    keeps no check."""
    from jobhelper import llm
    prompts, replies = [], [_PLACED, _FIXED]
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: prompts.append(prompt) or replies.pop(0))
    prep = ip.generate({"title": "Python Developer", "company": "Contoso", "description": "Python."}, PLACED_CV)
    assert len(prompts) == 2 and "'Git' at Kestrel Freight" in prompts[1] and "'Git' at" not in prompts[0]
    assert prep["checks"] == []


def test_a_skills_only_tool_still_placed_after_the_retry_is_in_the_checks(isolate_data, monkeypatch):
    from jobhelper import llm
    monkeypatch.setattr(llm, "ask_json", lambda prompt, **k: dict(_PLACED))
    prep = ip.generate({"title": "Python Developer", "company": "Contoso", "description": "Python."}, PLACED_CV)
    assert [c for c in prep["checks"] if "'Git' at Kestrel Freight" in c] == [
        "The answer to \"How do you work with others?\" puts 'Git' at Kestrel Freight, but the CV does not name that work "
        "under that position. Keep each piece of work with the job where it was done."]
