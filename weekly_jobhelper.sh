#!/bin/zsh
# JobHelper: the weekly run (started by the LaunchAgent the app's Weekly run card installs).
#   1. Job search : run.py           (search, score, write letters and adapted CVs)
#   2. Email scan : status.py sync   (read replies, update statuses, show the week's summary as one notification)
# Both use the Options saved in the app. Nothing here is specific to one computer:
# the project folder is wherever this file is, and Python is the project's own .venv.

PROJECT="${0:A:h}"                       # the folder this script is in
# launchd starts with a short PATH: add the usual places for the Claude CLI and Homebrew
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

cd "$PROJECT" || exit 1                  # e.g. an external disk that is not connected

PY="$PROJECT/.venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3)"
mkdir -p "$PROJECT/data"
LOG="$PROJECT/data/weekly_jobhelper.log"

if [[ -z "$PY" ]]; then
    echo "===== weekly JobHelper $(date '+%Y-%m-%d %H:%M'): no Python found (expected $PROJECT/.venv) =====" >> "$LOG"
    exit 1
fi

echo "===== weekly JobHelper $(date '+%Y-%m-%d %H:%M') =====" >> "$LOG"

echo "--- job search ---" >> "$LOG"
"$PY" run.py --reuse-profile >> "$LOG" 2>&1

echo "--- email analysis ---" >> "$LOG"
"$PY" status.py sync --summary >> "$LOG" 2>&1

echo "" >> "$LOG"
