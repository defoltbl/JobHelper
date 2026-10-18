"""Takes the pictures for docs/GUIDE.md.

Not part of the test suite (the file name keeps pytest from collecting it). Run it on purpose:

    pytest tests/guide_shots.py -q -o addopts=""

It loads the real window offscreen on a made-up data set (invented people and companies, in a
temporary folder), walks through the screens and saves one picture per screen to docs/img/.
Nothing of yours is read, and Claude is never asked.
"""
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, Qt
from PySide6.QtQuick import QQuickWindow

from jobhelper import api_core, agent1_cv, agent2_search, config, db, llm, store, ui_api
from tests.conftest import ROOT
from tests import test_ui_qml

ui = test_ui_qml.ui            # the fixture that loads the window on a temporary data folder

OUT = ROOT / "docs" / "img"
TODAY = date.today()

CV = """Alex Novak
Prague, Czechia · alex.novak@example.com

PROFILE
Junior software developer with a master's degree in computer science. Builds and tests back-end services in Python.

KEY SKILLS
Python, FastAPI, SQL, PostgreSQL, Docker, Git, Linux, pytest, REST

EXPERIENCE
Intern developer, Example Labs (2025): internal tools in Python, unit tests, code reviews.

LANGUAGES
English - C1, Czech - A2
"""

POSTING = ("We are a product team of twelve building tools for logistics planners. You will write and test back-end services in "
           "Python and FastAPI, work with PostgreSQL and Docker, and review your colleagues' code. We deploy to AWS with Kubernetes "
           "and Terraform. What we expect: a degree in computer science or similar, good Python, SQL, Git, and English at B2 or "
           "better. Experience with Kafka is a plus. We offer mentoring, a learning budget and flexible hours. ")


def _days(n):
    return (TODAY - timedelta(days=n)).isoformat()


def _lead(i, title, company, score, tier="", reason="", **kw):
    docs = score is not None and score >= 50 and not kw.pop("no_docs", False)
    job = store.new_job(id=f"lead{i}", title=title, company=company, location="Prague", source=kw.pop("source", "linkedin"),
                        url=f"https://example.com/jobs/{i}", date_posted=_days(i % 9 + 1), match_score=score, match_tier=tier,
                        match_reason=reason, description=kw.pop("description", POSTING * 2), desired_monthly_czk=kw.pop("pay", 60000),
                        status="letter_ready" if docs else "found",
                        cover_letter_file=f"AlexNovak_CoverLetter_{company.replace(' ', '')}.docx" if docs else "",
                        tailored_cv_file=f"AlexNovak_CV_{company.replace(' ', '')}.docx" if docs else "")
    job.update(kw)
    return job


def _data():
    leads = [
        _lead(1, "Junior Python Developer", "Northwind Systems", 82, "strong", "Python, FastAPI and PostgreSQL are all in your CV; the role is junior and the posting asks for no experience you lack."),
        _lead(2, "Backend Developer (Python)", "Kestrel Data", 74, "strong", "Strong match on Python and SQL. Kafka is asked for as a plus and is not in your CV."),
        _lead(3, "Junior Software Engineer", "Pinecrest Software", 68, "strong", "A graduate role on a Python team. Kubernetes is used but not required."),
        _lead(4, "Graduate Developer", "Lumen Robotics", 57, "moderate", "The work is mostly C++; your Python projects are relevant but not the main language here."),
        _lead(5, "QA Automation Engineer", "Blue Harbor", 52, "moderate", "Test automation with pytest fits; the role is testing, next to the development roles you look for.", score_before=64),
        _lead(6, "Data Engineer", "Aldermoor Labs", 45, "", "Adjacent to your direction; asks for two years with Spark, which your CV does not show.", no_docs=True,
              description="Data pipelines in Spark and Airflow for a retail analytics team."),
        _lead(7, "IT Support Specialist", "Orchard Bank", 25, "", "Helpdesk work, another field than the roles you look for.", score_before=55, no_docs=False),
        _lead(8, "Junior Tester", "Tallis & Co", 20, "", "Requires Czech at B2, which your CV does not show at a working level.", score_before=55),
        _lead(9, "Account Executive", "Brightline Media", None, "", "", prefilter="The title is another profession (account executive)."),
    ]
    for j in leads[6:8]:                       # two jobs whose documents were written at a higher score
        j.update(status="letter_ready", cover_letter_file=f"AlexNovak_CoverLetter_{j['company'].replace(' ', '')}.docx",
                 tailored_cv_file=f"AlexNovak_CV_{j['company'].replace(' ', '')}.docx")
    apps = [
        store.new_job(id="app1", title="Junior Backend Developer", company="Brightline Works", location="Prague", source="linkedin", status="interview",
                      date_applied=_days(12), match_score=78, match_tier="strong", description=POSTING * 2,
                      match_reason="Python and FastAPI match; the team works in English.", url="https://example.com/jobs/a1",
                      cover_letter_file="AlexNovak_CoverLetter_BrightlineWorks.docx", tailored_cv_file="AlexNovak_CV_BrightlineWorks.docx"),
        store.new_job(id="app2", title="Python Developer", company="Harbour Analytics", location="Prague", source="jobs.cz", status="waiting", date_applied=_days(14),
                      match_score=71, match_tier="strong", description=POSTING, match_reason="Good match on Python and SQL."),
        store.new_job(id="app3", title="Software Engineer in Test", company="Meridian Health", location="Brno", source="jobs.cz", status="waiting", date_applied=_days(4),
                      match_score=63, match_tier="strong", description=POSTING),
        store.new_job(id="app4", title="Junior Developer", company="Cobalt Games", location="Prague", source="linkedin", status="rejected", date_applied=_days(25),
                      match_score=58, match_tier="moderate", description=POSTING),
        store.new_job(id="app5", title="Graduate Engineer", company="Sable Energy", location="Prague", source="careers", status="rejected", date_applied=_days(30),
                      match_score=55, match_tier="moderate", description=POSTING),
        store.new_job(id="app6", title="Backend Engineer", company="Fennel Pay", location="Remote", source="linkedin", status="offer", date_applied=_days(40),
                      match_score=80, match_tier="strong", description=POSTING),
    ]
    return leads + apps


def _replies():
    rows = [("app1", "Brightline Works", "Junior Backend Developer", "interview", "", "", 3, "Invitation to a first interview", "They invite you to a 45-minute video call with the team lead next week."),
            ("app4", "Cobalt Games", "Junior Developer", "rejection", "They went with a candidate who has shipped a game.", "experience", 9, "Your application at Cobalt Games", "A polite rejection; they keep your CV for junior openings."),
            ("app5", "Sable Energy", "Graduate Engineer", "rejection", "The position was filled internally.", "position_filled", 15, "Update on your application", "The role was filled before interviews started."),
            ("app6", "Fennel Pay", "Backend Engineer", "offer", "", "", 2, "Offer: Backend Engineer", "A written offer with a start date to agree."),
            ("app2", "Harbour Analytics", "Python Developer", "acknowledged", "", "", 14, "We received your application", "An automatic confirmation.")]
    for i, (job_id, company, role, stage, reason, category, ago, subject, summary) in enumerate(rows):
        db.upsert_response({"msg_id": f"<{i}@example.com>", "received_date": _days(ago), "from_addr": f"careers@{company.split()[0].lower()}.example.com",
                            "subject": subject, "job_id": job_id, "company": company, "role": role, "stage": stage, "rejection_reason": reason,
                            "rejection_category": category, "sentiment": "", "next_step": "video call" if stage == "interview" else "", "summary": summary})


def _dropped():
    rows = []
    for title, company, group, reason in (
            ("Senior Backend Engineer", "Northwind Systems", "too senior", "The title is above your level (senior)."),
            ("Vývojář Python", "Datová Dílna", "other language", "The ad is written in Czech."),
            ("Python Developer (part-time)", "Kestrel Data", "part time", "Part-time; you asked for full-time only."),
            ("Backend Developer", "Harbour Analytics", "already applied", "You already applied to this role at this company."),
            ("Junior Developer", "Quiet Lake", "too old", "Posted more than 10 days ago."),
            ("Staff Engineer", "Lumen Robotics", "too senior", "The title is above your level (staff)."),
            ("Software Engineer", "Pinecrest Software", "years", "Asks for 5+ years of experience; your limit is 3.")):
        agent2_search.note_dropped(rows, store.new_job(id=f"d{len(rows)}", title=title, company=company, location="Prague", source="jobs.cz",
                                                         url="https://example.com/d"), group, reason)
    agent2_search.save_dropped(rows, TODAY.strftime("%d %b"))


def test_guide_shots(ui, monkeypatch):
    OUT.mkdir(parents=True, exist_ok=True)
    done, failed = [], []
    profile = {"summary": "Junior software developer.", "seniority": "junior", "target_roles": ["Junior Python Developer", "Backend Developer", "Software Engineer"],
               "adjacent_roles": ["QA Automation Engineer"], "search_queries": ["junior python developer", "backend developer", "software engineer"],
               "key_skills": ["Python", "FastAPI", "SQL"]}
    monkeypatch.setattr(agent1_cv, "load_profile", lambda: dict(profile))
    monkeypatch.setattr(api_core.CvSource, "text", lambda self: CV)
    monkeypatch.setattr(ui_api.Api, "threshold", lambda self: 50)
    monkeypatch.setattr(ui_api.Api, "old_format_letter", lambda self, j: False)      # the stand-in files are not real letters
    monkeypatch.setattr(ui_api.Api, "usage_info", lambda self: {"five_hour_used": 34, "five_hour_resets": "", "seven_day_used": 12, "seven_day_resets": "",
                                                              "model": "sonnet", "calls": 41, "cost": 1.87})
    letter = ["I am writing to apply for the Junior Python Developer role at Northwind Systems. Your posting describes back-end services in "
              "Python and FastAPI for logistics planners, which is the kind of work I did during my internship and want to do full time.",
              "At Example Labs I built internal tools in Python and wrote the unit tests for them with pytest. I worked with PostgreSQL "
              "every day and packaged the services with Docker, so the stack in your posting is familiar ground.",
              "I have not worked with Kubernetes or Terraform yet. I learn tools of that kind quickly when a team uses them, and I would "
              "rather say so than claim otherwise.",
              "What draws me to Northwind is that the tools are used by planners every day, so a small improvement in a service is felt "
              "at once. Reviewing colleagues' code, which your posting mentions, is how I learned most during my internship.",
              "I would be glad to talk about the role. I am in Prague and can start four weeks after an offer."]
    monkeypatch.setattr(ui_api.Api, "letter_for_edit", lambda self, job_id: {
        "ok": True, "id": job_id, "company": "Northwind Systems", "title": "Junior Python Developer", "paragraphs": list(letter),
        "title_line": "Junior Python Developer", "date_text": TODAY.strftime("%d %B %Y"), "min_words": 180, "max_words": 320})
    monkeypatch.setattr(ui_api.Api, "usage_overview", lambda self: {"calls": 214, "cost": 9.86, "kinds": [
        {"name": "Scoring jobs and writing letters", "calls": 121, "cost": 6.42}, {"name": "Adapting CVs", "calls": 38, "cost": 2.31},
        {"name": "Reading replies", "calls": 41, "cost": 0.74}, {"name": "Interview preparation", "calls": 3, "cost": 0.27},
        {"name": "Form answers", "calls": 4, "cost": 0.09}, {"name": "Asking how much is left", "calls": 7, "cost": 0.03}]})
    monkeypatch.setattr(ui_api.Api, "trouble_log", lambda self, most=25: {"total": 2, "file": "app_trouble.log", "lines": [
        TODAY.strftime("%Y-%m-%d") + " 09:14  reading one posting again: the page did not answer in time",
        TODAY.strftime("%Y-%m-%d") + " 09:02  playing the finished sound: no sound device"]})
    monkeypatch.setattr(ui_api.Api, "cv_compare", lambda self, job_id: {
        "ok": True, "company": "Northwind Systems", "title": "Junior Python Developer", "file": "AlexNovak_CV_NorthwindSystems.docx", "older_master": False,
        "rows": [{"state": "changed", "section": "PROFILE",
                  "master": "Junior software developer with a master's degree in computer science. Builds and tests back-end services in Python.",
                  "adapted": "Junior <b>Python</b> developer with a master's degree in computer science who builds and tests <b>FastAPI services on PostgreSQL</b>."},
                 {"state": "changed", "section": "KEY SKILLS", "master": "Python, FastAPI, SQL, PostgreSQL, Docker, Git, Linux, pytest, REST",
                  "adapted": "<b>Python, FastAPI, PostgreSQL, SQL, Docker</b>, Git, Linux, pytest, REST"}],
        "same": 4, "changed": 2, "added": 0, "removed": 0})
    (config.CV_DIR / "AlexNovak_CV_EN.txt").write_text(CV, encoding="utf-8")
    saved_jobs = store.load_jobs()
    store.save_jobs(_data())
    for j in store.load_jobs():                     # the files the documents point to
        for folder, name in ((config.LETTERS_DIR, j.get("cover_letter_file")), (config.TAILORED_CV_DIR, j.get("tailored_cv_file"))):
            if name:
                (folder / name).write_bytes(b"made-up document")
    _replies()
    _dropped()
    api = ui.bridge._api
    api.save_options({**api.options(), "where": "Prague", "threshold": 50, "wanted_roles": ["junior python developer", "backend developer"],
                      "unwanted_roles": ["tester"], "skip_words": ["intern"], "max_years": 3})
    api.note_run(when=TODAY.strftime("%d %b") + " 09:12", found="+9 new", filtered=7, letters=5, cvs=5, scan=TODAY.strftime("%d %b") + " · 2 new",
                 scan_detail="45 · 5 asked", cost=0.42, cost_of="search")
    api.set_event("app1", (TODAY + timedelta(days=2)).isoformat(), "11:30", "interview", "Video call with the team lead")

    def shot(name, part=None, zoom=2):
        """The whole window, or one part of it (x, y, width, height) enlarged so its small text can be read."""
        ui.wait(450)
        path = OUT / f"{name}.png"
        picture = QQuickWindow.grabWindow(ui.win)
        if part:
            x, y, w, h = part
            picture = picture.copy(x, y, w, h).scaled(w * zoom, h * zoom, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        picture.save(str(path))
        done.append(name)

    RIGHT = (ui.win.width() - 236, 0, 236, 470)          # the column on the right: usage, last run, weekly run

    def scroll(dialog_name, target_name, above=200):
        dialog, target = ui.find(dialog_name), ui.find(target_name)
        for f in dialog.findChildren(QObject):
            if f.metaObject().className().startswith("QQuickFlickable") and (f.property("contentHeight") or 0) > 700:
                f.setProperty("contentY", max(0, target.mapToItem(f.property("contentItem"), 0, 0).y() - above))
                return

    def step(name, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - one picture must not stop the others
            failed.append(f"{name}: {type(e).__name__}: {e}")

    def welcome_card():
        ui.js("welcome.shown = true; welcome.phase = 'card'")
        shot("01_welcome")
        ui.js("welcome.finish()")
        ui.wait(900)

    def main_screen():
        ui.js("win.reloadAll(); win.healthData = bridge.selfCheck(true); win.healthHidden = true")
        ui.js('ticker.text = "Search finished: 9 new jobs, 5 letters and 5 CVs written."')
        shot("02_main")
        shot("25_sidebar", (0, 0, 238, 420))
        shot("26_usage_and_last_run", RIGHT)
        ui.js('usageData = ({ model: "sonnet", five_hour_used: 100, five_hour_resets: "14:00", seven_day_used: 34, seven_day_resets: "" })')
        shot("27_limit_used_up", (ui.win.width() - 236, 0, 236, 190))
        ui.js("usageData = bridge.usageInfo()")
        ui.js('win.healthData = ({ ok: false, problems: 1, checks: [], message: "No master CV yet. Add yours in the Account card." }); win.healthHidden = false')
        shot("28_startup_check", (238, 0, 726, 120), 1.5)
        ui.js("win.healthData = bridge.selfCheck(true); win.healthHidden = true")
        ui.bridge._set_running(True)
        ui.js('win.runMode = "search"; win.elapsed = 147')
        ui.bridge.agentChanged.emit("a1", "done", "profile ready")
        ui.bridge.agentChanged.emit("a2", "done", "+9 new")
        ui.bridge.agentChanged.emit("a3", "running", "")
        ui.bridge.progressChanged.emit("a3", 6, 14)
        ui.bridge.logChanged.emit("Writing CV and letter 2 of 5: Kestrel Data…")
        shot("03_running")
        ui.js('win.limitData = ({ paused: true, can_resume: false, window: "5-hour", used: 100, resets_at: "14:00", resets_day: "' + TODAY.strftime("%d %b")
              + '", message: "Claude\'s 5-hour limit is used up (100%). It resets at 14:00." }); win.paused = true; limitDialog.open()')
        shot("29_limit_pause")
        ui.js("limitDialog.close(); win.paused = false; win.limitData = ({})")
        ui.wait(350)
        ui.bridge._set_running(False)
        ui.js('win.resetRobots(); win.runMode = ""; win.stageKey = ""; win.runProgress = 0; win.runResult = ""')
        ui.js('ticker.text = "Line idle. Press Run search to start the pipeline."')

    def new_jobs():
        ui.js('openView("new")')
        shot("04_new_jobs")
        ui.js("tableDialog.shelveAll()")
        shot("05_move_documents")
        ui.js("tableDialog.confirmStale = false")
        ui.js('tableDialog.groupFilter = "moderate"; tableDialog.apply()')
        ui.wait(200)
        ui.js("detailDialog.startReview(tableDialog.reviewIds())")
        shot("36_review_one_by_one")
        ui.js("detailDialog.close()")
        ui.wait(350)
        ui.js('tableDialog.groupFilter = ""; tableDialog.apply(); tableDialog.close()')
        ui.wait(350)

    def job_window():
        ui.js('detailDialog.show("lead1")')
        shot("06_job_window")
        scroll("detailDialog", "scoreNote", 60)
        shot("07_job_score_keywords")
        ui.js("detailDialog.close()")
        ui.wait(350)
        ui.js('detailDialog.show("lead7")')
        shot("08_job_below_limit")
        ui.js("detailDialog.close()")
        ui.wait(350)

    def compare():
        ui.js('compareDialog.show("lead1")')
        shot("09_compare_cv")
        ui.js("compareDialog.close()")
        ui.wait(350)

    def letter_editor():
        ui.js('letterDialog.show("lead1")')
        shot("30_letter_editor")
        ui.js("letterDialog.close()")
        ui.wait(350)

    def form_answers():
        monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"answers": [
            {"n": 1, "answer": "I am looking for a gross monthly salary of [your figure] CZK.", "needs_you": "Your salary figure"},
            {"n": 2, "answer": "I can start four weeks after an offer.", "needs_you": ""},
            {"n": 3, "answer": "Northwind builds planning tools in Python and FastAPI, which is the work I did in my internship and want to do full time.", "needs_you": ""}]})
        ui.js('formDialog.show("lead1")')
        ui.wait(400)
        ui.js('fmQuestions.text = "What are your salary expectations?\\nWhen can you start?\\nWhy do you want to work at Northwind Systems?"; formDialog.draft()')
        import time
        for _ in range(200):
            time.sleep(0.02)
            ui.wait(10)
            if ui.js("formDialog.busy") is False:
                break
        shot("10_form_answers")
        ui.js("formDialog.dirty = false; formDialog.close()")
        ui.wait(350)

    def applications():
        ui.js('openView("app")')
        shot("11_applications")
        ui.js("tableDialog.close()")
        ui.wait(350)
        ui.js('detailDialog.show("app1")')
        shot("12_application_window")
        scroll("detailDialog", "dateSave", 260)
        shot("13_application_dates_notes")
        ui.js("detailDialog.close()")
        ui.wait(350)

    def interview():
        prep = {"made": TODAY.isoformat(), "summary": "A first call with the team lead: expect questions about your Python projects and how you test your code.",
                "pitch": "I am a junior developer who likes clear, tested back-end code.", "fit": ["Python and FastAPI", "pytest"],
                "company": ["Builds planning tools for logistics teams (from the posting)."],
                "questions": [{"audience": "hr", "kind": "about you", "question": "Tell me about yourself.", "why": "Opens most calls.",
                               "answer": "I finished my master's in computer science this year and spent my internship building internal tools in Python.", "check": ""},
                              {"audience": "technical", "kind": "technical", "question": "How do you test an API endpoint?", "why": "The posting names testing.",
                               "answer": "With pytest and a test client: one test for the normal case, and one for each way the input can be wrong.", "check": ""}],
                "ask_hr": ["What are the next steps and the timeline?"], "ask_technical": ["How is code reviewed in the team?"], "ask_them": [], "checks": []}
        ui.bridge._api.editor.change("app1", lambda jobs, j: j.update(interview_prep=dict(prep)), render=False)
        ui.js('prepDialog.show("app1")')
        shot("14_interview_preparation")
        ui.js("prepDialog.close()")
        ui.wait(350)

    def replies():
        ui.js('openView("resp")')
        shot("15_responses")
        ui.js("tableDialog.close()")
        ui.wait(350)
        ui.js('responseDialog.show("<0@example.com>")')
        shot("31_one_reply")
        ui.js("responseDialog.startPicking()")
        shot("34_file_reply")
        ui.js("responseDialog.close()")
        ui.wait(350)
        ui.js('openView("ana")')
        shot("16_analytics")
        ui.js("tableDialog.close()")
        ui.wait(350)

    def filtered_and_insights():
        ui.js('openView("skip")')
        shot("17_filtered_out")
        ui.js("tableDialog.close()")
        ui.wait(350)
        ui.js('openView("ins")')
        shot("18_insights")
        ui.js("tableDialog.close()")
        ui.wait(350)

    def options():
        dialog = ui.find("optDialog")
        ui.js("optsData = bridge.options()")
        ui.js("open()", dialog)
        ui.wait(500)
        shot("19_options_search")
        ui.js("remoteDialog.show(['germany', 'poland', 'south korea'], optDialog.homeName)")
        ui.wait(500)
        ui.js('remoteDialog.area = "europe"')
        ui.js("countryList.positionViewAtIndex(remoteDialog.shown.findIndex(c => c.key === 'germany') - 1, ListView.Beginning)",
              ui.find("remoteDialog"))
        shot("34_remote_countries")
        ui.js("remoteDialog.close()")
        ui.wait(350)
        scroll("optDialog", "fieldsNote", 260)
        shot("20_options_roles")
        scroll("optDialog", "shelfNote", 320)
        shot("21_options_storage")
        scroll("optDialog", "foldersSw", 420)
        shot("33_options_email")
        ui.js("close()", dialog)
        ui.wait(350)

    def others():
        ui.js("schedDialog.open()")
        shot("22_weekly_run")
        ui.js("schedDialog.close()")
        ui.wait(350)
        ui.js("helpDialog.open()")
        shot("23_help")
        ui.js('helpDialog.tab = "use"')
        shot("35_help_usage")
        ui.js('helpDialog.tab = "how"')
        ui.js("helpDialog.close()")
        ui.wait(350)
        ui.js("win.dark = false")
        shot("24_light_theme")
        ui.js("win.dark = true")

    def about_you():
        from jobhelper import details
        details.save({**details.empty(), "first_name": "Alex", "last_name": "Novak", "email": "alex.novak@example.com",
                      "experience": [{"employer": "Riverside Labs", "title": "Junior developer", "start": "03/2024", "end": "", "current": True},
                                     {"employer": "Evening Code School", "title": "Tutor", "start": "2023", "end": "", "current": True}]})
        api.save_about_you({"salary_target": 0, "salary_currency": "CZK",
                            "salary_by_role": [{"role": "support", "amount": 42000}],
                            "about_right_to_work": "Full right to work in Czechia", "about_start": "within two weeks",
                            "about_jobs": [{"job": "Junior developer, Riverside Labs",
                                            "notes": "I wrote the import service in Python with FastAPI, added its tests, and fixed about thirty tickets."},
                                           {"job": "Tutor, Evening Code School", "notes": "I teach Python basics to two groups of ten adults each week."}],
                            "about_experience": "A chess club website in Django, for a club of forty members."})
        ui.js("aboutDialog.show()")
        ui.wait(600)
        shot("32_about_you")
        scroll("aboutDialog", "noJobs", 110)
        shot("35_about_you_work")
        ui.js("aboutDialog.close()")
        ui.wait(350)

    def assistant():
        from jobhelper import details
        ui.js("stagePanel.assistant.greet()")
        ui.wait(700)
        shot("37_assistant", (238, 60, ui.win.width() - 238 - 236, ui.win.height() - 60 - 110), 1.5)
        ui.find("assistantBot").setProperty("greeting", False)
        details.save({"first_name": "Alex", "last_name": "Novak", "email": "alex.novak@example.com", "phone": "+420 123 456 789", "street": "",
                      "city": "Prague", "postcode": "110 00", "country": "Czechia", "linkedin": "linkedin.com/in/alexnovak",
                      "github": "github.com/alexnovak", "website": "", "notice_period": "1 month",
                      "experience": [{"employer": "Riverside Labs", "title": "Junior developer", "start": "03/2024", "end": "", "current": True},
                                     {"employer": "Evening Code School", "title": "Tutor", "start": "2023", "end": "", "current": True},
                                     {"employer": "Old Mill Software", "title": "Intern", "start": "2022", "end": "2023", "current": False}],
                      "education": [{"school": "Charles University", "degree": "Master", "field": "Computer science", "start": "2021", "end": "2023"},
                                    {"school": "Charles University", "degree": "Bachelor", "field": "Informatics", "start": "2018", "end": "2021"}],
                      "salary_amount": 60000, "salary_currency": "CZK", "salary_period": "month"})
        monkeypatch.setattr(ui_api.Api, "my_answers", lambda self: {"starters": ["What are your strengths?", "Tell us about yourself.", "Are you willing to relocate?"], "items": [
            {"question": "When can you start?", "answer": "Two weeks after an offer; my notice period is one month at most.", "company": "", "when": ""},
            {"question": "Why are you looking for a new job?", "company": "", "when": "",
             "answer": "I want to build back-end services full time. In my current role that is a small part of the work."}]})
        monkeypatch.setattr(ui_api.Api, "assistant_ask", lambda self, text, job_id="": {
            "ok": True, "action": "fill", "host": "careers.northwind.example", "job_id": "lead1", "job": "Junior Python Developer at Northwind Systems", "guessed": True,
            "filled": [{"label": "First name", "value": "Alex", "kind": "detail", "check": ""}, {"label": "Last name", "value": "Novak", "kind": "detail", "check": ""},
                       {"label": "Email", "value": "alex.novak@example.com", "kind": "detail", "check": ""},
                       {"label": "LinkedIn profile", "value": "https://linkedin.com/in/alexnovak", "kind": "detail", "check": ""},
                       {"label": "Why do you want to work at Northwind Systems?", "kind": "answer", "check": "",
                        "value": "Your back-end services are written in FastAPI on PostgreSQL, the stack of my own project…"},
                       {"label": "When can you start?", "value": "I can start on [your start date].", "kind": "answer", "check": "Your start date"},
                       {"label": "Country", "value": "Czech Republic", "kind": "choice", "check": "Chosen for you: check it."},
                       {"label": "Resume/CV", "value": "CV_Northwind_Systems_Junior_Python_Developer.pdf", "kind": "file", "check": "Look that the page shows the file."},
                       {"label": "Do you have the right to work in the Czech Republic?", "value": "Yes", "kind": "choice", "check": "Chosen for you: check it."}],
            "left": [{"label": "Your photo", "why": "I cannot tell which of your files this field wants. Attach it yourself."},
                     {"label": "Are you willing to relocate?", "why": "Your CV, My details and About you do not settle this. Choose it yourself."}],
            "kept": 1, "boxes": 2, "wants_file": True, "has_files": True, "is_lead": True, "can_learn": True,
            "say": "I filled in 9 fields on careers.northwind.example: 4 from My details, 2 answers drafted from your CV, 2 choices made for you, 1 file attached. I took this to be the form for "
                   "Junior Python Developer at Northwind Systems. 4 of them need your attention (outlined in amber on the page). 2 fields are left for you, "
                   "listed below with the reason. Read everything on the page, then send the form yourself. I never press Submit."})
        monkeypatch.setattr(ui_api.Api, "assistant_watch", lambda self: {"ok": False, "url": "", "sign": "", "empty": 0})
        monkeypatch.setattr(ui_api.Api, "assistant_memory", lambda self: {"count": 3})
        monkeypatch.setattr(ui_api.Api, "assistant_notes_list", lambda self: {"notes": [{"text": "No consulting firms", "when": ""}, {"text": "Remote or Prague only", "when": ""}]})
        ui.js("assistantDialog.show()")
        ui.wait(500)
        ui.js('assistantDialog.ask("Fill in the form")')
        for _ in range(100):
            if not ui.find("assistantDialog").property("busy"):
                break
            ui.wait(30)
        ui.js("talkFlick.contentY = 0")
        shot("38_assistant_fill")
        ui.js("talkFlick.contentY = Math.max(0, talkFlick.contentHeight - talkFlick.height)")
        shot("40_assistant_next")
        # talking: a question about the data, then a request that changes something (asked first)
        monkeypatch.setattr(ui_api.Api, "assistant_talk", lambda self, text, context_job="", chosen_job="", **kw: {
            "ok": True, "action": "say", "say": "Two applications have had no reply for more than two weeks: Harbor Analytics, sent 19 days ago, and Brightpath, sent 16 days ago. "
                                              "Both are past the point where most replies arrive, so a follow-up is due.",
            "rows": [{"id": "app2", "label": "Harbor Analytics · Data Engineer", "sub": "waiting · score 71"},
                     {"id": "app3", "label": "Brightpath · Backend Developer", "sub": "waiting · score 66"}]} if "reply" in text else {
            "ok": True, "action": "confirm", "say": "", "rows": [], "pending": {"name": "mark_applied", "args": {"job": "lead1"}},
            "ask": "Mark Junior Python Developer at Northwind Systems as applied? It moves to Applications as waiting."})
        ui.js("talk.clear(); filledModel.clear(); leftModel.clear(); assistantDialog.last = ({})")
        ui.js('assistantDialog.ask("which applications have had no reply for two weeks?")')
        for _ in range(100):
            if not ui.find("assistantDialog").property("busy"):
                break
            ui.wait(30)
        ui.js('assistantDialog.ask("I sent the Northwind form, mark it applied")')
        for _ in range(100):
            if not ui.find("assistantDialog").property("busy"):
                break
            ui.wait(30)
        shot("44_assistant_talk")
        ui.js("assistantDialog.no()")
        monkeypatch.setattr(ui_api.Api, "assistant_review", lambda self, job_id="": {
            "ok": True, "action": "review", "host": "careers.northwind.example", "job_id": "lead1",
            "say": "I read the form on careers.northwind.example: 11 of 13 fields are filled in, and 3 things look wrong. Tick boxes, files and personal questions are yours to check. I did not send anything.",
            "problems": [{"field": "Phone", "problem": "It is required and still empty."},
                         {"field": "When can you start?", "problem": "It still has a part in [square brackets] to fill in."},
                         {"field": "Why do you want to work at Northwind Systems?", "problem": "It says you led a team, which your CV does not show."}]})
        ui.js("talk.clear(); rowModel.clear()")
        ui.js('assistantDialog.act("review", "", "Review the form before I send it")')
        for _ in range(100):
            if not ui.find("assistantDialog").property("busy"):
                break
            ui.wait(30)
        shot("45_assistant_review")
        ui.js('assistantDialog.page = "details"')
        shot("39_my_details")
        ui.js("detailsFlick.contentY = 500")
        shot("41_my_jobs_and_degrees")
        ui.js("detailsFlick.contentY = Math.max(0, detailsFlick.contentHeight - detailsFlick.height)")
        shot("42_my_salary_and_files")
        ui.js('assistantDialog.page = "answers"')
        shot("43_my_answers")
        ui.js("assistantDialog.tryClose()")
        ui.wait(350)
        details.path().unlink(missing_ok=True)

    try:
        for name, fn in (("welcome", welcome_card), ("main", main_screen), ("new jobs", new_jobs), ("job window", job_window), ("compare", compare),
                         ("letter editor", letter_editor), ("form answers", form_answers), ("applications", applications), ("interview", interview), ("replies", replies),
                         ("filtered and insights", filtered_and_insights), ("options", options), ("assistant", assistant), ("about you", about_you), ("others", others)):
            step(name, fn)
    finally:
        ui.bridge._set_running(False)
        store.save_jobs(saved_jobs)
    print("\npictures:", len(done), "→", OUT)
    assert not failed, failed
    assert not [w for w in ui.warnings if "font" not in w.lower()], ui.warnings
    assert all((OUT / f"{n}.png").stat().st_size > 5000 for n in done)
    assert Path(OUT).is_dir()
