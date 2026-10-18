"""Agent 4 — the tracking table.

render_all(): (re)build data/applications.xlsx from the job store, one row per
job, with the cover-letter filename and current status.

Email reading now lives in `email_client`; response analysis + status updates
live in Agent 5 (`agent5_responses`).
"""
from __future__ import annotations

from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import config, salary, store

# ── Excel ─────────────────────────────────────────────────────────────────
COLUMNS = [
    ("Job ID", "id", 16),
    ("Title", "title", 30),
    ("Company", "company", 24),
    ("Location", "location", 18),
    ("Match %", "match_score", 9),
    ("Status", "status", 13),
    ("Stages", "stages_path", 34),
    ("Result", "result", 12),
    ("Next Step", "next_step", 24),
    ("Cover Letter", "cover_letter_file", 34),
    ("Tailored CV", "tailored_cv_file", 34),
    ("Salary", "salary", 16),
    ("Source", "source", 10),
    ("Date Found", "date_found", 13),
    ("Date Applied", "date_applied", 13),
    ("Last Update", "last_update", 13),
    ("Match Reason", "match_reason", 40),
    ("Notes", "notes", 40),
    ("URL", "url", 45),
]

# Columns for the NEW-JOBS (leads) file — no interview-progress columns.
NEW_JOB_COLUMNS = [
    ("Job ID", "id", 16),
    ("Title", "title", 32),
    ("Company", "company", 24),
    ("Location", "location", 18),
    ("Match %", "match_score", 9),
    ("Tier", "match_tier", 11),
    ("Status", "status", 13),
    ("Desired Monthly (CZK)", "desired_monthly_czk", 18),
    ("Desired Annual (CZK)", "desired_annual_czk", 18),
    ("Cover Letter", "cover_letter_file", 30),
    ("Tailored CV", "tailored_cv_file", 30),
    ("Salary (posting)", "salary", 16),
    ("Source", "source", 12),
    ("Posted", "date_posted", 12),
    ("Date Found", "date_found", 13),
    ("Match Reason", "match_reason", 44),
    ("URL", "url", 45),
]

STATUS_FILLS = {
    "found": "FFF2CC",
    "letter_ready": "D9E1F2",
    "waiting": "FFE699",
    "interview": "C6E0B4",
    "offer": "A9D08E",
    "rejected": "F4CCCC",
    "on_hold": "E2E2E2",
}

_WRAP = {"match_reason", "notes", "stages_path", "next_step"}



def put(ws, row: int, column: int, value):
    """Write one cell as plain content. What stands in these tables comes from job boards and from emails: a text that
    begins with "=" would be run by Excel as a formula (it can fetch an address or show a false link), so it is stored
    as text; characters a workbook cannot hold are left out; anything that is not a text or a number is written as text."""
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    if value is None:
        value = ""
    elif isinstance(value, bool) or not isinstance(value, (str, int, float)):
        value = str(value)
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub("", value)
    cell = ws.cell(row=row, column=column, value=value)
    if isinstance(value, str) and value.startswith("="):
        cell.data_type = "s"
    return cell


def header_row(ws, columns: list[tuple[str, float]]) -> None:
    """The first row of a sheet in the app's style (white bold words on blue), and each column's width."""
    for c, (label, width) in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=c, value=label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4472C4")
        cell.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(c)].width = width


def _render_sheet(rows: list[dict[str, Any]], columns, path, title: str) -> None:
    config.ensure_dirs()
    wb = Workbook()
    ws = wb.active
    ws.title = title
    currency = salary.asked({"desired_monthly_czk": 1})[1]
    header_row(ws, [(label.replace("(CZK)", f"({currency})"), width) for label, _key, width in columns])

    status_col = next((i for i, (_l, k, _w) in enumerate(columns, start=1) if k == "status"), None)
    for r, job in enumerate(rows, start=2):
        for c, (_label, key, _w) in enumerate(columns, start=1):
            val = job.get(key, "")
            if key in ("desired_monthly_czk", "desired_annual_czk"):      # what is asked for, which may be your own figure
                amount = salary.asked(job)[0]
                val = (amount * (12 if key == "desired_annual_czk" else 1)) or ""
            cell = put(ws, r, c, val)
            cell.alignment = Alignment(vertical="top", wrap_text=key in _WRAP)
            if key == "url" and str(val).lower().startswith(("http://", "https://")):      # a link to a web page, nothing else
                cell.hyperlink = val
                cell.font = Font(color="0563C1", underline="single")
        if status_col:
            fill = STATUS_FILLS.get(job.get("status", ""))
            if fill:
                ws.cell(row=r, column=status_col).fill = PatternFill("solid", fgColor=fill)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(1, len(rows) + 1)}"
    wb.save(str(path))


def render_applications(jobs: list[dict[str, Any]]) -> None:
    """applications.xlsx — jobs you've applied to, with interview progress."""
    rows = [j for j in jobs if j.get("status") in store.APPLICATION_STATUSES]
    rows.sort(key=lambda j: j.get("last_update", ""), reverse=True)
    rows.sort(key=store.application_rank)          # interview, waiting, rejected - same as in the app
    _render_sheet(rows, COLUMNS, config.EXCEL_PATH, "Applications")


def render_new_jobs(jobs: list[dict[str, Any]]) -> None:
    """new_jobs.xlsx — fresh leads from search you haven't applied to yet.

    Hides leads that scored below config.MIN_LEAD_SCORE (clear mismatches);
    unscored leads always show.
    """
    floor = config.MIN_LEAD_SCORE
    rows = [
        j for j in jobs
        if j.get("status") in store.LEAD_STATUSES
        and (j.get("match_score") is None or j.get("match_score") >= floor)
    ]
    rows.sort(key=lambda j: (-(j.get("match_score") or 0), j.get("date_found", "")))
    _render_sheet(rows, NEW_JOB_COLUMNS, config.NEW_JOBS_EXCEL, "New Jobs")


def render_all(jobs: list[dict[str, Any]]) -> None:
    render_applications(jobs)
    render_new_jobs(jobs)



