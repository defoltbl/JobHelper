"""The interview preparation as Word documents: one for a talk with HR, one for a talk with
someone who does the work (a specialist or the hiring manager).

Built from what interview_prep.generate stored for the job. Both follow the same order: the
company, you, your projects and skills, the questions they may ask you with answers, and the
questions you can ask them. The text the app writes itself follows ASD-STE100 Simplified
Technical English: short sentences, the active voice, common words.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

AUDIENCES = ("hr", "technical")
TITLES = {"hr": "HR", "technical": "Technical"}
COMPANY_NOTE = ("This is only what the posting and the emails say. Before the call, read the company website: "
                "what they make, how big they are, and recent news.")
KIND_TITLES = {"about you": "About you", "technical": "The work itself", "your projects": "Your projects",
               "behavioural": "How you work", "the role and company": "The role and the company", "practical": "Practical questions"}
NOTES = {"hr": "HR people often do not know the technical side of the work. Use plain words. "
               "Tell them what you did, how you work and why you want this job.",
         "technical": "Give exact answers. Name the real tools, methods and numbers. Say clearly what you did not use."}
NEW_PART = "This part is new. Select Make again in the application window to add your projects and skills."
FIXED_REMINDERS = ["Test the call link before the call. Join some minutes early, with the camera on, in a quiet room.",
                   "Have your CV and this sheet open. At the end, ask about the next steps."]


def when_text(event: dict[str, Any] | None) -> str:
    """"Tuesday 13 October 2026, 11:30" from a job's date to remember ('' without one)."""
    try:
        day = date.fromisoformat((event or {}).get("date", "") or "")
    except (TypeError, ValueError):
        return ""
    clock = (event or {}).get("time", "")
    return f"{day:%A} {day.day} {day:%B %Y}" + (f", {clock}" if clock else "")


def file_name(prefix: str, company: str, audience: str = "hr") -> str:
    """"Alex_Beta_Prep_HR.docx" or "Alex_Beta_Prep_Technical.docx"."""
    import re
    short = re.sub(r"[^A-Za-z0-9]+", "", (company or "Company").split(",")[0].title().replace(" ", ""))[:40] or "Company"
    return f"{prefix or 'Candidate'}_{short}_Prep_{TITLES.get(audience, 'HR')}.docx"


def _audience(q: dict[str, Any]) -> str:
    """Older saved preparations have no audience: questions about the work itself go to the specialist."""
    return q.get("audience") or ("technical" if q.get("kind") in ("technical", "your projects") else "hr")


def build(job: dict[str, Any], prep: dict[str, Any], out_path: Path, contact: str = "", audience: str = "hr") -> Path:
    """Write the document for one audience ("hr" or "technical"). A part with nothing in it is left out."""
    import docx
    from docx.shared import Pt, Cm

    from . import interview_prep
    audience = audience if audience in AUDIENCES else "hr"
    hr = audience == "hr"
    doc = docx.Document()
    for section in doc.sections:
        section.left_margin = section.right_margin = Cm(2.0)
        section.top_margin = section.bottom_margin = Cm(1.8)
    base = doc.styles["Normal"]
    base.font.name, base.font.size = "Calibri", Pt(10.5)

    def para(text: str, size: float = 10.5, bold: bool = False, italic: bool = False, after: float = 6, before: float = 0):
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold, run.italic, run.font.size = bold, italic, Pt(size)
        p.paragraph_format.space_after, p.paragraph_format.space_before = Pt(after), Pt(before)
        return p

    def heading(text: str):
        para(text, 14, bold=True, after=4, before=12).paragraph_format.keep_with_next = True

    def subheading(text: str):
        para(text, 11, bold=True, after=2, before=6).paragraph_format.keep_with_next = True

    def bullets(items):
        for item in items:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(str(item)).font.size = Pt(10.5)
            p.paragraph_format.space_after = Pt(2)

    def qa(question: str, answer: str, check: str = ""):
        q = para(question, bold=True, after=1, before=4)
        q.paragraph_format.keep_with_next = True
        para(answer, after=2)
        if check:
            para(f"Check this answer before you say it. It mentions {check}. Your CV does not show this.", size=9.5, italic=True, after=4)

    company, role = job.get("company") or "The company", job.get("title") or "the role"
    para(f"{company} – Interview preparation: {TITLES[audience]}", 17, bold=True, after=2)
    para(role, 11, after=1)
    line = " · ".join(x for x in (when_text(job.get("event")), (job.get("event") or {}).get("note", ""),
                                  f"with {contact}" if contact else "") if x)
    if line:
        para(line, 10, after=6)
    para("For a talk with HR or a recruiter." if hr else "For a talk with a specialist or the hiring manager.",
         size=10, italic=True, after=4)
    if prep.get("summary"):
        para(prep["summary"], after=8)

    # 1. the company
    if prep.get("company") or prep.get("role"):
        heading("1. About the company")
        if prep.get("company"):
            bullets(prep["company"])
            if hr and prep.get("company_say"):
                para(f"Say it in your own words: “{prep['company_say']}”", italic=True, before=4)
            para(COMPANY_NOTE, size=9.5, italic=True)
        if prep.get("role"):
            subheading("The role: what the work is")
            if hr and prep.get("role_plain"):
                para(prep["role_plain"])
            else:
                bullets(prep["role"])
                if prep.get("role_plain"):
                    para(f"In plain words: {prep['role_plain']}", before=4)

    # 2. you
    heading("2. About you")
    if prep.get("pitch"):
        subheading("Your opening pitch (about 45 seconds)")
        para(f"“{prep['pitch']}”")
    if prep.get("fit"):
        subheading("What to lead with")
        bullets(prep["fit"])
    if prep.get("experience"):
        subheading("Your work experience" + (", in plain words" if hr else ", told for this role"))
        para("These stories use only your CV and your text in Options under “More about your work”.", size=9.5, italic=True, after=4)
        for e in prep["experience"]:
            para(e["job"], 11, bold=True, after=2, before=6).paragraph_format.keep_with_next = True
            if hr:
                para(f"“{e.get('plain') or e['story']}”", after=3)
                continue
            para(f"“{e['story']}”", after=3)
            if e.get("gained"):
                para("What it gave you for this role:", bold=True, after=1)
                bullets(e["gained"])
            if e.get("typical"):
                para("What people in this type of job usually do. This is general information about the role, not your record:",
                     bold=True, after=1, before=3)
                bullets(e["typical"])
            if e.get("if_true"):
                para("Ask yourself these questions. Add a point only if it is true:", bold=True, after=1, before=3)
                bullets(e["if_true"])
            if e.get("thin"):
                para(f"Your CV says little here: {e['thin']} Write the real details in Options > About you > More about your work. "
                     "Then make the preparation again.", size=9.5, italic=True, before=2)
    key = prep.get("key_question") or {}
    if key.get("question") and key.get("answer"):
        subheading(f"The key question: “{key['question']}”")
        para("They will almost certainly ask this. Answer calmly, as a decision you made.", after=3)
        para(f"“{key['answer']}”")
    if prep.get("gap"):
        subheading("The honest gap. Say it openly; do not hide it.")
        para(prep["gap"])

    # 3. projects and skills
    heading("3. Your projects and skills")
    if not prep.get("projects") and not prep.get("skills"):
        para(NEW_PART, size=9.5, italic=True)
    for pr in prep.get("projects") or []:
        para(pr["name"], 11, bold=True, after=2, before=6).paragraph_format.keep_with_next = True
        para(f"“{(pr.get('plain') or pr['what']) if hr else pr['what']}”", after=3)
        if not hr and pr.get("tools"):
            para(f"Tools: {', '.join(pr['tools'])}", size=10, after=3)
    if prep.get("skills"):
        subheading("Your skills for this role, and where your CV shows them")
        bullets(f"{sk['skill']}: {sk['proof']}" for sk in prep["skills"])

    # 4. what they may ask
    asked = [q for q in prep.get("questions") or [] if _audience(q) == audience]
    if asked:
        heading("4. Questions " + ("HR may ask you" if hr else "a specialist may ask you"))
        para(NOTES[audience], size=9.5, italic=True, after=3)
        for q in sorted(asked, key=lambda q: list(KIND_TITLES).index(q.get("kind", "about you")) if q.get("kind") in KIND_TITLES else 0):
            qa(q["question"], q["answer"], q.get("check", ""))
    if not hr:
        if prep.get("concepts"):
            subheading("Concepts to explain")
            para("Know enough to talk about each one. If you do not know a term, say so and ask.", after=3)
            bullets(f"{c['term']}: {c['meaning']}" for c in prep["concepts"])
        if prep.get("revise"):
            subheading("Topics to revise before the call")
            bullets(prep["revise"])

    # 5. what you can ask
    yours = prep.get("ask_hr" if hr else "ask_technical") or []
    if not yours and not (prep.get("ask_hr") or prep.get("ask_technical")):
        yours = prep.get("ask_them") or []                   # older preparations: one mixed list
    if hr:
        yours = interview_prep.with_next_steps(yours)
    if yours:
        heading("5. Questions you can ask " + ("HR" if hr else "them"))
        bullets(yours)

    heading("Before the call")
    bullets(list(prep.get("reminders") or []) + FIXED_REMINDERS)
    for check in prep.get("checks") or []:
        para(f"Check: {check}", size=9.5, italic=True)
    para(f"JobHelper made this sheet on {prep.get('made') or date.today().isoformat()} from your CV and the posting. "
         "Read it carefully. It is a start, not a script.", size=9, italic=True, before=10)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
