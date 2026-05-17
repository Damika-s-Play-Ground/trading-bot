# Codebase map

## Runtime flow
1. `manager.py` orchestrates five spot bots.
2. Each bot reads/writes its own paper state JSON at repo root.
3. `bot_futures.py` manages the futures paper account.
4. Dashboard generators read JSON state and write HTML files at repo root.
5. Hermes cron scripts call the wrappers, then append run status to `logs/cron.json`.

## Directories

### `trading_bot/core/`
- `manager.py`: adaptive allocator, regime detection, throttling, rebalancing, portfolio journaling.
- `bot_runtime.py`: shared env-driven budget/capital helper functions.

### `trading_bot/bots/`
- `spot_dca.py`: DCA + take-profit spot strategy.
- `spot_trend.py`: trend-following spot strategy.
- `spot_grid.py`: grid strategy.
- `spot_momentum.py`: momentum strategy.
- `spot_deep_mr.py`: deep mean-reversion strategy.
- `futures.py`: futures paper-trading strategy.

### `trading_bot/dashboards/`
- `spot_dashboard.py`: spot + cron dashboard generator.
- `futures_dashboard.py`: futures dashboard generator.
- `research_page.py`: converts research markdown into HTML.
- `glossary.py`: glossary page generator.

### `trading_bot/analysis/`
Research and experimentation scripts: backtests, parameter sweep, optimizer, and market data pipeline.

## Compatibility rule
Root filenames are intentionally preserved as wrappers because cron jobs and local habits already depend on them.

## Important repo-root data files
- `config.json`: main spot bot config.
- `paper_state.json`, `paper_trend.json`, `paper_grid.json`, `paper_momentum.json`, `paper_deepmr.json`: spot bot states.
- `paper_futures.json`: futures bot state.
- `manager_state.json`, `manager_portfolio.json`, `performance_journal.json`: manager outputs.
- `logs/cron.json`: cron monitor data source.
