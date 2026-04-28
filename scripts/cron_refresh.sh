#!/usr/bin/env bash
# Daily KRX foreign-ownership snapshot refresh.
# Suggested cron line (18:30 KST Mon-Fri, after KRX close + EOD data publish):
#
#   30 18 * * 1-5 /home/user/Korean_stock/scripts/cron_refresh.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

mkdir -p data
LOG="data/refresh.log"

# Activate venv if present, else fall back to system python.
if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
else
  PY=python3
fi

{
  echo "==== $(date -Iseconds) starting refresh ===="
  "$PY" -m kstock.refresh
  echo "==== $(date -Iseconds) refresh OK ===="
} >> "$LOG" 2>&1
