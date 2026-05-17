# trading-bot

Concise multi-strategy paper-trading repo for spot + futures experiments.

## What this repo does
- Runs five spot paper bots under a central adaptive manager.
- Runs a separate futures paper bot.
- Regenerates HTML dashboards for spot, futures, research, glossary, and cron health.
- Stores local state in JSON files at the repo root.
- Uses Hermes cron scripts outside the repo to schedule recurring runs.

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
- `futures_dashboard.py`
- `research_page.py`
- `glossary.py`
- `run_bot.sh`

They now act as thin wrappers around the organized package under `trading_bot/`.

## Package layout
- `trading_bot/core/` — manager and shared runtime helpers
- `trading_bot/bots/` — spot and futures bot implementations
- `trading_bot/dashboards/` — HTML generators
- `trading_bot/analysis/` — backtests, sweeps, optimizer, data pipeline
- `docs/` — concise codebase documentation
- `logs/` — cron/job health logs

## State and generated files
The following remain at repo root so current automation does not break:
- `paper_*.json`
- `manager_state.json`
- `manager_portfolio.json`
- `performance_journal.json`
- `market_data.json`
- `dashboard.html`, `cron.html`, `futures.html`, `research.html`, `glossary.html`

## Run
```bash
./venv/bin/python3.13 manager.py
./venv/bin/python3.13 bot_futures.py
./venv/bin/python3.13 dashboard.py
bash run_bot.sh
```

## Scheduling
Current Hermes cron scripts live outside this repo under `~/.hermes/scripts/` and update local files in this repo.
