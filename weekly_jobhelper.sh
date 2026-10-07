#!/bin/zsh
# JobHelper — weekly automation (run by launchd). Does BOTH:
#   1. Job search  : run.py  (search Prague ≤10 days, score, letters + tailored CVs, prune applied)
#   2. Email scan  : status.py sync  (classify replies, update statuses, rejection DB, reports)
# Search runs first (finds new leads); then email analysis updates applications.

PROJECT="/path/to/JobHelper"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

cd "$PROJECT" || exit 1   # SSD must be mounted; if not, abort

LOG="$PROJECT/data/weekly_jobhelper.log"
PY="$PROJECT/.venv/bin/python"

echo "===== weekly JobHelper $(date '+%Y-%m-%d %H:%M') =====" >> "$LOG"

echo "--- job search ---" >> "$LOG"
"$PY" run.py --reuse-profile >> "$LOG" 2>&1

echo "--- email analysis ---" >> "$LOG"
"$PY" status.py sync --days 10 --summary >> "$LOG" 2>&1

echo "" >> "$LOG"
