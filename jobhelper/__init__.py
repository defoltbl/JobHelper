"""JobHelper — a 4-agent job application assistant built on the Claude Agent SDK.

Agent 1  analyze_cv      : read the CV, produce a target job profile + search queries
Agent 2  search_jobs     : find jobs (Adzuna API for Prague, + assisted search)
Agent 3  write_letters   : score each job vs the CV, write cover letters, save to disk
Agent 4  tracker         : build/update the Excel table; classify email replies
"""

__version__ = "0.1.0"
