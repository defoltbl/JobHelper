"""The interview preparation as a Word document: one sheet to read before the call.

Built from what interview_prep.generate stored for the job. The layout follows a
sheet the user wrote by hand: a title, what to expect, the company, the role, your
fit, the honest gap, the key question, the opening pitch, likely questions with
answers, concepts to be able to explain, questions to ask, and reminders.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

COMPANY_NOTE = ("Only what the posting and their emails say. Before the call, look at their website: what they build, "
                "how big they are, recent news.")
KIND_TITLES = {"about you": "About you", "technical": "Technical questions", "your projects": "Your projects",
               "behavioural": "How you work", "the role and company": "The role and the company", "practical": "Practical questions"}


def when_text(event: dict[str, Any] | None) -> str:
    """"Tuesday 13 October 2026, 11:30" from a job's date to remember ('' without one)."""
    try:
        day = date.fromisoformat((event or {}).get("date", ""))
    except ValueError:
        return ""
    clock = (event or {}).get("time", "")
    return f"{day:%A} {day.day} {day:%B %Y}" + (f", {clock}" if clock else "")


def file_name(prefix: str, company: str) -> str:
    import re
    short = re.sub(r"[^A-Za-z0-9]+", "", (company or "Company").split(",")[0].title().replace(" ", ""))[:40] or "Company"
    return f"{prefix or 'Candidate'}_{short}_Prep.docx"


def build(job: dict[str, Any], prep: dict[str, Any], out_path: Path, contact: str = "") -> Path:
    """Write the document. Sections with nothing in them are left out."""
    import docx
    from docx.shared import Pt, Cm

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
        para(text, 13, bold=True, after=4, before=10).paragraph_format.keep_with_next = True

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
            para(f"Check before you say it: this mentions {check}, which is not in your CV.", size=9.5, italic=True, after=4)

    company, role = job.get("company") or "The company", job.get("title") or "the role"
    para(f"{company} – Interview Prep", 17, bold=True, after=2)
    para(role, 11, after=1)
    when = when_text(job.get("event"))
    line = " · ".join(x for x in (when, (job.get("event") or {}).get("note", ""), f"with {contact}" if contact else "") if x)
    if line:
        para(line, 10, after=6)
    if prep.get("summary"):
        para(prep["summary"], after=8)

    if prep.get("company"):
        heading(f"About {company} (if they ask what you know)")
        bullets(prep["company"])
        if prep.get("company_say"):
            para(f"Say it in your own words: “{prep['company_say']}”", italic=True, before=4)
        para(COMPANY_NOTE, size=9.5, italic=True)
    if prep.get("role"):
        heading("The role – what the work actually is")
        bullets(prep["role"])
        if prep.get("role_plain"):
            para(f"In plain terms: {prep['role_plain']}", before=4)
    if prep.get("fit"):
        heading("Your fit – lead with these")
        bullets(prep["fit"])
    if prep.get("experience"):
        heading("Your work experience, told for this role")
        para("How to talk about each job here. The stories use only your CV and what you wrote in Options under "
             "“More about your work”.", after=4)
        for e in prep["experience"]:
            para(e["job"], 11, bold=True, after=2, before=6).paragraph_format.keep_with_next = True
            para(f"“{e['story']}”", after=3)
            if e.get("gained"):
                para("What it gave you for this role:", bold=True, after=1)
                bullets(e["gained"])
            if e.get("if_true"):
                para("Ask yourself, and add it only if it is true:", bold=True, after=1, before=3)
                bullets(e["if_true"])
            if e.get("thin"):
                para(f"Thin spot: {e['thin']} Write the real details in Options → About you → More about your work, "
                     "then prepare again.", size=9.5, italic=True, before=2)
    if prep.get("gap"):
        para("The honest gap (own it, don't hide it)", 11, bold=True, after=2, before=8)
        para(prep["gap"])
    key = prep.get("key_question") or {}
    if key.get("question") and key.get("answer"):
        heading(f"The key question: “{key['question']}”")
        para("They will almost certainly ask this. Answer it calmly, as a deliberate choice.", after=3)
        para(f"“{key['answer']}”")
    if prep.get("pitch"):
        heading("Your opening pitch (about 45 seconds)")
        para(f"“{prep['pitch']}”")

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for q in prep.get("questions") or []:
        by_kind.setdefault(q.get("kind", "about you"), []).append(q)
    for kind, title in KIND_TITLES.items():
        if by_kind.get(kind):
            heading(title)
            for q in by_kind[kind]:
                qa(q["question"], q["answer"], q.get("check", ""))
    if prep.get("concepts"):
        heading("Concepts to be able to explain")
        para("Enough to speak sensibly about each. If one comes up that you do not know, say so and ask.", after=3)
        bullets(f"{c['term']}: {c['meaning']}" for c in prep["concepts"])
    if prep.get("revise"):
        heading("Worth revising before the call")
        bullets(prep["revise"])
    if prep.get("ask_them"):
        heading("Questions to ask them")
        bullets(prep["ask_them"])
    reminders = list(prep.get("reminders") or []) + ["Test the call link beforehand and join a few minutes early: camera on, quiet room.",
                                                     "Have your CV and this sheet open. End by asking about the next steps."]
    heading("Practical reminders")
    bullets(reminders)
    for check in prep.get("checks") or []:
        para(f"Check: {check}", size=9.5, italic=True)
    para(f"Made by JobHelper on {prep.get('made') or date.today().isoformat()} from your CV and the posting. "
         "Read it critically: it is a starting point, not a script.", size=9, italic=True, before=10)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
