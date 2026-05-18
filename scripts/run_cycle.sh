#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

mkdir -p "$REPO_ROOT/logs"
LOCK_FILE="$REPO_ROOT/logs/runtime-cycle.lock"
LOG_FILE="$REPO_ROOT/logs/runtime-cycle.log"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] cycle skipped: previous run still active" >> "$LOG_FILE"
  exit 0
fi

run_step() {
  local label="$1"
  shift
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] START $label" >> "$LOG_FILE"
  "$@" >> "$LOG_FILE" 2>&1
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DONE  $label" >> "$LOG_FILE"
}

run_step manager "$REPO_ROOT/venv/bin/python3.13" manager.py
run_step futures "$REPO_ROOT/venv/bin/python3.13" bot_futures.py
run_step dashboard "$REPO_ROOT/venv/bin/python3.13" dashboard.py
run_step futures-dashboard "$REPO_ROOT/venv/bin/python3.13" futures_dashboard.py
run_step research-page "$REPO_ROOT/venv/bin/python3.13" research_page.py
run_step glossary "$REPO_ROOT/venv/bin/python3.13" glossary.py
run_step todo "$REPO_ROOT/venv/bin/python3.13" todo.py
