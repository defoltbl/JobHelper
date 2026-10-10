"""Agent 1 — analyze the CV.

Reads the CV (PDF, DOCX or TXT) from data/cv/, then asks the model to produce
a structured "target profile": which job types fit this person's experience,
seniority, skills, and a set of concrete search queries for Agent 2.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import config, llm, vault

SYSTEM = (
    "You are a senior career coach and technical recruiter. You read a person's "
    "CV and determine, realistically, which kinds of roles they should apply to. "
    "Be honest about seniority. Output only valid JSON, no commentary."
)

PROMPT_TEMPLATE = """Analyze this CV and return a JSON object with exactly these keys:

{{
  "summary": "2-3 sentence summary of the candidate",
  "seniority": "junior | mid | senior | lead",
  "years_experience": <number>,   // total work experience in years INCLUDING internships and practical training: add up the months from their dates (e.g. 20 months -> 1.7). Do not count study or personal projects.
  "internships": ["Title - Company, Sep 2025 - Apr 2026 (8 months)", ...],   // every internship / practical training with its dates and length; [] if none
  "target_roles": ["job title 1", "job title 2", ...],   // 3-6 realistic titles
  "adjacent_roles": ["role", ...],   // 3-6 ADJACENT/fallback roles they realistically qualify for given transferable skills, e.g. for a junior dev: "IT Support Specialist", "Help Desk", "QA Tester", "Technical Support Engineer", "Junior Data Analyst"
  "key_skills": ["skill", ...],                            // top 8-12
  "industries": ["industry", ...],
  "search_queries": ["query", ...],   // 8-12 SHORT keyword phrases (1-3 words each) to paste into a job board. Mix core target roles AND adjacent roles above. Use common English titles. NO long parenthetical phrases. Good: "python developer", "it support", "qa tester", "junior developer", "help desk". Bad: "Junior Backend Developer (Python/Kotlin)"
  "strengths": ["..."],
  "gaps": ["honest weaknesses or missing skills for the target roles"]
}}

CV TEXT:
---
{cv_text}
---
Return only the JSON object."""


def read_cv_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if suffix == ".docx":
        import docx

        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = docx.Document(str(path))
        lines: list[str] = []
        for child in doc.element.body.iterchildren():       # in the order of the page: many CVs keep their jobs or skills in a table
            if child.tag.endswith("}p"):
                lines.append(Paragraph(child, doc).text)
            elif child.tag.endswith("}tbl"):
                for row in Table(child, doc).rows:
                    cells = list(dict.fromkeys(cell.text.strip() for cell in row.cells if cell.text.strip()))   # a merged cell is given once
                    if cells:
                        lines.append(" | ".join(cells))
        return "\n".join(lines)
    # txt / md / anything text-like
    return path.read_text(encoding="utf-8", errors="ignore")


CV_TYPES = {".pdf", ".docx", ".txt", ".md"}


def find_cv() -> Path | None:
    """The master CV: the file you chose in the app if it is still there, else the first
    CV file in data/cv/ by name."""
    config.ensure_dirs()
    chosen = str(config.ui_settings().get("master_cv") or "")
    if chosen and Path(chosen).name == chosen:
        path = config.CV_DIR / chosen
        if path.is_file() and path.suffix.lower() in CV_TYPES:
            return path
    candidates = sorted(p for p in config.CV_DIR.iterdir() if p.is_file() and p.suffix.lower() in CV_TYPES)
    return candidates[0] if candidates else None


def remember_cv(name: str) -> None:
    """Note which file in data/cv/ is the master CV (kept with the Options)."""
    data = config.ui_settings()
    data["master_cv"] = Path(str(name)).name
    config.ensure_dirs()
    vault.write_text(config.DATA_DIR / "ui_settings.json", json.dumps(data, ensure_ascii=False, indent=2))


def analyze(cv_path: Path | None = None) -> dict[str, Any]:
    cv_path = cv_path or find_cv()
    if cv_path is None:
        raise FileNotFoundError(
            f"No CV found. Put your CV (PDF/DOCX/TXT) in {config.CV_DIR}"
        )
    cv_text = read_cv_text(cv_path).strip()
    if len(cv_text) < 50:
        raise ValueError(
            f"Could not read meaningful text from {cv_path.name}. "
            "If it's a scanned PDF, export a text-based version."
        )

    profile = llm.ask_json(
        PROMPT_TEMPLATE.format(cv_text=cv_text[:20000]),
        system=SYSTEM,
        tag="agent1_cv",
    )
    if not isinstance(profile, dict):
        raise ValueError("Claude's answer about your CV could not be read. Run the search again.")
    profile["_cv_file"] = cv_path.name
    profile["_cv_sha"] = _sha(cv_path)
    vault.write_text(config.PROFILE_JSON, json.dumps(profile, ensure_ascii=False, indent=2))
    return profile


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_profile(current_only: bool = False) -> dict[str, Any] | None:
    """The saved CV analysis. With current_only, None is returned when it was
    made from a different CV than the one in data/cv now, so an edited CV
    (new dates, new titles) is analysed again instead of scored from old facts."""
    if not config.PROFILE_JSON.exists():
        return None
    try:
        profile = json.loads(vault.read_text(config.PROFILE_JSON))
    except ValueError:
        return None                                  # a damaged file: the CV is analysed again
    if not isinstance(profile, dict):
        return None
    if current_only:
        cv = find_cv()
        if cv is not None and profile.get("_cv_sha") != _sha(cv):
            return None
    return profile
