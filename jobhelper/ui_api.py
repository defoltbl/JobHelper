"""The window's back end, as one object: the facade `Api`.

The Qt bridge (`qt_bridge.Bridge`), the command line (`status.py`) and the tests talk to `Api`.
`Api` does no work itself. It builds the services, each with one area of the app, gives them the
small shared objects of `api_core`, and hands each call to the service that owns it. A service
that needs another one asks through `Api`, never directly: so the services do not know each other.
"""
from __future__ import annotations

from .api_assistant import AssistantService
from .api_core import CvSource, Desktop, JobEditor
from .api_documents import DocumentsService
from .api_insights import InsightsService
from .api_interview import InterviewService
from .api_jobs import JobsService
from .api_letters import LettersService
from .api_options import OptionsService
from .api_replies import RepliesService
from .api_system import SystemService
from .api_talk import TalkService


class _Via:
    """A method of the facade that hands the call to one of its services."""

    def __init__(self, service: str) -> None:
        self._service = service

    def __set_name__(self, owner, name: str) -> None:
        self._name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return getattr(getattr(obj, self._service), self._name)


class Api:
    """One object for the window; every call goes to the service that owns it."""

    def __init__(self) -> None:
        self._desktop, self._cv, self._editor = Desktop(), CvSource(), JobEditor()
        parts = (self, self._editor, self._cv, self._desktop)
        self._system = SystemService(*parts)
        self._settings = OptionsService(*parts)
        self._joblist = JobsService(*parts)
        self._documents = DocumentsService(*parts)
        self._replies = RepliesService(*parts)
        self._insights = InsightsService(*parts)
        self._interview = InterviewService(*parts)
        self._letters = LettersService(*parts)
        self._assistant = AssistantService(*parts)
        self._talk = TalkService(*parts)

    @property
    def live(self):
        """The job list of the search or scan in progress (None between runs); set by the bridge."""
        return self._editor.live

    @live.setter
    def live(self, jobs) -> None:
        self._editor.live = jobs

    @property
    def editor(self) -> JobEditor:
        """Changes saved jobs by hand, and the same job in a run in progress."""
        return self._editor

    def cv_text(self) -> str:
        """The master CV as text (empty when there is none)."""
        return self._cv.text()

    # ── The app itself: connections, usage, problems, backups (SystemService) ──
    connections = _Via("_system")
    notification_permission = _Via("_system")
    open_notification_settings = _Via("_system")
    test_notification = _Via("_system")
    usage_info = _Via("_system")
    self_check = _Via("_system")
    changelog = _Via("_system")
    limits = _Via("_system")
    USAGE_NAMES = _Via("_system")
    usage_overview = _Via("_system")
    trouble_log = _Via("_system")
    show_trouble_log = _Via("_system")
    backup_all = _Via("_system")
    backup_check = _Via("_system")
    backup_export = _Via("_system")
    fix_problem = _Via("_system")
    widget_update = _Via("_system")
    repair_statuses = _Via("_system")
    restore_data = _Via("_system")

    # ── Options and the career-site list (OptionsService) ──
    followup_days = _Via("_settings")
    profession_fields = _Via("_settings")
    currencies = _Via("_settings")
    country_of = _Via("_settings")
    countries = _Via("_settings")
    remote_choices = _Via("_settings")
    last_run = _Via("_settings")
    note_run = _Via("_settings")
    options = _Via("_settings")
    OPTION_NUMBERS = _Via("_settings")
    OPTION_LISTS = _Via("_settings")
    OPTION_TEXTS = _Via("_settings")
    MAX_LIST = _Via("_settings")
    MAX_WORD = _Via("_settings")
    MAX_COMPANY_NAME = _Via("_settings")
    about_you = _Via("_settings")
    save_about_you = _Via("_settings")
    start_preview = _Via("_settings")
    MAX_PAY_ROLE = _Via("_settings")
    MAX_SALARY = _Via("_settings")
    MAX_PAY_ROWS = _Via("_settings")
    pay_problem = _Via("_settings")
    pay_key = _Via("_settings")
    own_figure = _Via("_settings")
    work_notes_size = _Via("_settings")
    MODELS = _Via("_settings")
    SOURCES = _Via("_settings")
    check_options = _Via("_settings")
    save_options = _Via("_settings")
    companies = _Via("_settings")
    save_companies = _Via("_settings")

    # ── The lists, one job, hand edits, small actions (JobsService) ──
    show_in_folder = _Via("_joblist")
    counts = _Via("_joblist")
    leads = _Via("_joblist")
    applications = _Via("_joblist")
    job_detail = _Via("_joblist")
    set_status = _Via("_joblist")
    set_apply_date = _Via("_joblist")
    save_company_notes = _Via("_joblist")
    merge_jobs = _Via("_joblist")
    keep_separate = _Via("_joblist")
    apply_job = _Via("_joblist")
    APPLY_STEPS = _Via("_joblist")
    apply_step = _Via("_joblist")
    open_doc = _Via("_joblist")
    open_excel = _Via("_joblist")
    open_url = _Via("_joblist")
    note_opened = _Via("_joblist")
    recently_opened = _Via("_joblist")
    OPENED_FOR = _Via("_joblist")

    # ── Scores and documents (DocumentsService) ──
    rescore_ids = _Via("_documents")
    rescore_plan = _Via("_documents")
    rescore_one = _Via("_documents")
    can_write_documents = _Via("_documents")
    write_documents = _Via("_documents")
    score_anyway = _Via("_documents")
    MIN_PASTED = _Via("_documents")
    MAX_PASTED = _Via("_documents")
    threshold = _Via("_documents")
    stale_docs = _Via("_documents")
    score_before = _Via("_documents")
    stale_docs_list = _Via("_documents")
    shelve_all_docs = _Via("_documents")
    set_description = _Via("_documents")
    reread_posting = _Via("_documents")
    SHELF = _Via("_documents")
    UNDO_DAYS = _Via("_documents")
    shelve_docs = _Via("_documents")
    shelved = _Via("_documents")
    unshelve_docs = _Via("_documents")
    SHELF_DAYS = _Via("_documents")
    SHELF_MAX_DAYS = _Via("_documents")
    shelf_status = _Via("_documents")
    tidy_shelf = _Via("_documents")
    last_shelved = _Via("_documents")
    unshelve_last = _Via("_documents")
    dismiss_job = _Via("_documents")
    restore_job = _Via("_documents")
    dismissed = _Via("_documents")

    # ── Replies from companies (RepliesService) ──
    add_reply = _Via("_replies")
    followup_draft = _Via("_replies")
    mark_followed_up = _Via("_replies")
    responses = _Via("_replies")
    filing_targets = _Via("_replies")
    refile_response = _Via("_replies")
    response_detail = _Via("_replies")
    analytics = _Via("_replies")

    # ── Insights, the last week, what a search left out (InsightsService) ──
    week_summary = _Via("_insights")
    filtered_out = _Via("_insights")
    bring_back = _Via("_insights")
    open_filtered = _Via("_insights")
    comparable = _Via("_insights")
    cv_compare = _Via("_insights")
    insights = _Via("_insights")
    read_ahead = _Via("_insights")

    # ── Interviews, dates, form answers (InterviewService) ──
    set_event = _Via("_interview")
    clear_event = _Via("_interview")
    upcoming = _Via("_interview")
    due_reminders = _Via("_interview")
    export_event = _Via("_interview")
    thanks_draft = _Via("_interview")
    mark_thanked = _Via("_interview")
    form_answers = _Via("_interview")
    check_questions = _Via("_interview")
    make_form_answers = _Via("_interview")
    save_form_answers = _Via("_interview")
    interview_prep = _Via("_interview")
    make_interview_prep = _Via("_interview")
    prep_parts = _Via("_interview")
    save_prep_parts = _Via("_interview")
    prep_document = _Via("_interview")
    prep_text = _Via("_interview")

    # ── Letters and PDFs (LettersService) ──
    letter_path = _Via("_letters")
    editable_letter = _Via("_letters")
    old_format_letter = _Via("_letters")
    letter_for_edit = _Via("_letters")
    save_letter = _Via("_letters")
    rewrite_paragraph = _Via("_letters")
    can_combine = _Via("_letters")
    combined_pdf = _Via("_letters")
    my_letters = _Via("_letters")
    open_my_letters = _Via("_letters")

    # ── The assistant: forms in the browser (AssistantService) ──
    my_details = _Via("_assistant")
    assistant_cv_lists = _Via("_assistant")
    my_answers = _Via("_assistant")
    save_my_answer = _Via("_assistant")
    delete_my_answer = _Via("_assistant")
    draft_my_answer = _Via("_assistant")
    check_my_details = _Via("_assistant")
    save_my_details = _Via("_assistant")
    assistant_jobs = _Via("_assistant")
    assistant_ask = _Via("_assistant")
    assistant_open_form = _Via("_assistant")
    assistant_files = _Via("_assistant")
    assistant_watch = _Via("_assistant")
    assistant_learn = _Via("_assistant")
    assistant_memory = _Via("_assistant")
    assistant_forget = _Via("_assistant")
    assistant_review = _Via("_assistant")
    assistant_fill = _Via("_assistant")

    # ── The assistant: free requests, notes, practice (TalkService) ──
    assistant_new_talk = _Via("_talk")
    assistant_talk = _Via("_talk")
    assistant_judge_page = _Via("_talk")
    assistant_confirm = _Via("_talk")
    assistant_undo = _Via("_talk")
    assistant_practice = _Via("_talk")
    assistant_practice_answer = _Via("_talk")
    assistant_notes_list = _Via("_talk")
    assistant_forget_note = _Via("_talk")
    assistant_briefing = _Via("_talk")
    assistant_nudge_done = _Via("_talk")
    browser = _Via("_talk")
    assistant_browser = _Via("_talk")
    assistant_set_browser = _Via("_talk")
    assistant_watching = _Via("_talk")
    assistant_set_watch = _Via("_talk")
    assistant_notice = _Via("_talk")
    facts = _Via("_talk")
    pay = _Via("_talk")
