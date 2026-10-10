"""JobHelper: a job application assistant built on the Claude Agent SDK (it runs on a Claude subscription).

Agent 1  agent1_cv         : read the CV, produce a target job profile and search queries
Agent 2  agent2_search     : find jobs on job boards, company career sites and search APIs
Agent 3  agent3_letters    : score each job against the CV, write cover letters and adapted CVs
Agent 4  agent4_tracker    : build and update the Excel tables
Agent 5  agent5_responses  : read replies in the mailbox (read-only) and file them to applications
The assistant (assistant, form_fill, api_assistant, api_talk) fills in application forms in the
browser and answers requests in the window. docs/CODE.md describes the whole structure.
"""

__version__ = "0.1.0"
