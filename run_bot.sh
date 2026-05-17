#!/bin/bash
set -euo pipefail

cd /Users/damikaanupama/trading-bot

# Optional local secrets/config for manual runs.
# Keep this file untracked.
if [ -f .env.local ]; then
  set -a
  . ./.env.local
  set +a
fi

echo "=== SPOT BOTS (Manager) ==="
./venv/bin/python3.13 manager.py 2>&1

echo ""
echo "=== FUTURES BOT ==="
./venv/bin/python3.13 bot_futures.py 2>&1

echo ""
echo "=== REGENERATE DASHBOARDS ==="
./venv/bin/python3.13 dashboard.py 2>&1 | tail -1
./venv/bin/python3.13 futures_dashboard.py 2>&1 | tail -1
./venv/bin/python3.13 research_page.py 2>&1 | tail -1
