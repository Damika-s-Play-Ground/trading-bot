# trading-bot

Concise multi-strategy paper-trading repo for spot + futures experiments.

## What this repo does
- Runs five spot paper bots under a central adaptive manager.
- Runs a separate futures paper bot.
- Regenerates dashboards for spot, futures, research, glossary, cron health, and roadmap/TODO views.
- Serves a lightweight Flask + Vue dashboard shell for faster live inspection and better UI/UX.
- Stores generated analytics and synced dashboard state in SQLite plus repo-root JSON files.
- Uses Hermes cron scripts outside the repo to schedule recurring runs.

## Recent upgrades
- Spot dashboard moved to a lightweight Flask-served Vue frontend.
- Recent Trades now shows cleaner reason text plus RSI, MACD, moving-average, and volume snapshots when available.
- Bot cards now expand into deeper drill-down panels for stats, live signals, positions, and recent trade reasons.
- Chart hover behavior is now consistent across allocation, equity-curve, and activity charts.
- Equity curve readability improved with cleaner axes, hover states, and gradient fill.
- TODO completion state now persists in the dashboard SQLite store instead of only browser localStorage.
- TODO page now renders a DB-backed roadmap timeline with modal drill-downs, de-duplicated summary rows, and clean upcoming-vs-completed ordering.
- Research queue now syncs into SQLite with analyzer scores, promotion labels, topic tags, suggested actions, and a `/api/research-data` payload.
- Cron health now warns on missed cadence, not just stale status.
- Glossary updated to explain new dashboard/store/cron concepts.
- Candidate scoring, allocation optimizer snapshots, promotion gates, and attribution review are now part of the live paper-trading loop.

## Operations playbook
- `docs/live-trading-operations-playbook.md` — live-trading runbook, incident handling, rollback steps, and cutover checklist.

## Stable entrypoints
These root-level scripts are kept for compatibility:
- `manager.py`
- `bot.py`
- `bot_trend.py`
- `bot_grid.py`
- `bot_momentum.py`
- `bot_deep_mr.py`
- `bot_futures.py`
- `dashboard.py`
- `app.py`
- `futures_dashboard.py`
- `research_page.py`
- `glossary.py`
- `todo.py`
- `run_bot.sh`

They now act as thin wrappers around the organized package under `trading_bot/`.

## Package layout
- `trading_bot/core/` — manager and shared runtime helpers
- `trading_bot/bots/` — spot and futures bot implementations
- `trading_bot/dashboards/` — HTML generators, Flask/Vue dashboard payloads, and shared data-store logic
- `trading_bot/analysis/` — backtests, sweeps, optimizer, data pipeline
- `static/` — dashboard frontend assets (`dashboard-app.js`, `dashboard.css`, vendored Vue runtime)
- `docs/` — concise codebase documentation
- `logs/` — cron/job health logs
- `data/` — SQLite dashboard state and generated analytics cache

## State and generated files
The following remain at repo root so current automation does not break:
- `paper_*.json`
- `manager_state.json`
- `manager_portfolio.json`
- `performance_journal.json`
- `market_data.json`
- `dashboard.html`, `cron.html`, `futures.html`, `research.html`, `glossary.html`, `todo.html`

Persistent dashboard data lives in:
- `data/dashboard.sqlite`

## Install
```bash
./venv/bin/pip install -r requirements.txt
./venv/bin/pip install -r requirements-web.txt
```

## Common commands

### Run the spot/futures logic
```bash
./venv/bin/python3.13 manager.py
./venv/bin/python3.13 bot_futures.py
bash run_bot.sh
```

### Regenerate dashboard pages
```bash
./venv/bin/python3.13 dashboard.py
./venv/bin/python3.13 futures_dashboard.py
./venv/bin/python3.13 research_page.py
./venv/bin/python3.13 glossary.py
./venv/bin/python3.13 todo.py
```

### Run the dashboard backend
```bash
./venv/bin/python3.13 app.py
```

Open:
- `http://127.0.0.1:8008/dashboard`

### One-line local launch in Chrome
```bash
./venv/bin/python3.13 app.py &
open -a "Google Chrome" http://127.0.0.1:8008/dashboard
```

## Useful endpoints
- `/dashboard` — main spot dashboard
- `/futures` — futures dashboard
- `/research` — research page
- `/todo` — roadmap/TODO board
- `/cron` — cron status and history
- `/glossary` — glossary
- `/api/dashboard-data` — live dashboard payload for the Vue UI
- `/api/spot-summary` — compact spot summary JSON
- `/api/todo-data` — roadmap timeline data pulled from SQLite-backed dashboard state
- `/api/todo-state` — synced TODO state overrides
- `/api/research-data` — structured research feed with analyzer scores and promotion labels
- `/api/refresh` — regenerate all pages from the running Flask app
- `/healthz` — simple app health check

## Local smoke-test flow
```bash
./venv/bin/python3.13 -m py_compile app.py trading_bot/dashboards/dashboard_backend.py trading_bot/dashboards/data_store.py trading_bot/dashboards/spot_dashboard.py trading_bot/dashboards/todo_page.py trading_bot/dashboards/glossary.py
./venv/bin/python3.13 dashboard.py
./venv/bin/python3.13 todo.py
./venv/bin/python3.13 glossary.py
node --check static/dashboard-app.js
curl http://127.0.0.1:8008/healthz
```

## Scheduling
Current Hermes cron scripts live outside this repo under `~/.hermes/scripts/` and update local files in this repo.
