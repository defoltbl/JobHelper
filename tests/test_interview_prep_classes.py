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
    assert "the opening pitch" in where and "the project Agent" in where and "the project Agent for HR" in where and "the skill Python" in where
    bad, third = prep.problems(["Kubernetes"], "Alex")
    assert bad == [("Tech?", "Kubernetes")] and third == ["You?"]
    prep.mark(["Kubernetes"])
    assert saved["questions"][1]["check"] == "Kubernetes" and saved["questions"][0]["check"] == ""
    assert "What Kubernetes did in Agent mentions Kubernetes as experience, which is not in your CV." in saved["checks"]


def test_editing_by_hand_runs_the_same_check_as_making_it():
    prep = ip.Preparation.from_reply({"questions": [{"question": "Q", "answer": "A plain answer.", "kind": "about you", "audience": "hr"}],
                                      "projects": [{"name": "Agent", "what": "I built it.",
                                                    "tech": [{"tool": "Docker", "about": "Containers.", "use": "It packed the app.", "why": "Same everywhere."}]}]}).as_dict()
    new, problem = ip.apply_parts(prep, [{"key": "projects.0.what", "text": "I built it and ran it on Kubernetes."}], cv_text="I know Python and Docker.")
    assert problem == "" and new["checks"] == ["The project Agent mentions Kubernetes as experience, which is not in your CV."]
