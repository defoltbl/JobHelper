#!/bin/zsh
# JobHelper — weekly email scan (run by cron). Reads inbox replies, updates
# statuses + the response database, and rebuilds the Excel tables.
# Uses a 10-day lookback so weekly runs overlap and never miss a reply.

PROJECT="/path/to/JobHelper"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

cd "$PROJECT" || exit 1   # SSD must be mounted; if not, abort

LOG="$PROJECT/data/weekly_scan.log"
echo "===== weekly scan $(date '+%Y-%m-%d %H:%M') =====" >> "$LOG"
"$PROJECT/.venv/bin/python" status.py sync --days 10 >> "$LOG" 2>&1
echo "" >> "$LOG"
