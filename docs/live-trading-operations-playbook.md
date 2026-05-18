# Live Trading Operations Playbook

This playbook is the operating reference for moving from paper-first management to controlled live procedures.

## 1. Operating modes

- paper_only
  - `config.json` keeps `"mode": "paper"`
  - manager, bots, and dashboards keep updating state with zero live orders
- shadow_live_only
  - live readiness gates are close but not all green
  - continue paper execution, compare paper decisions against intended live rules
- controlled_live_ready
  - promotion gates pass
  - live cutover still requires a human decision plus exchange/API checks

## 2. Preflight before any live cutover

Run from repo root:

```bash
./venv/bin/python3.13 candidate_scorer.py
./venv/bin/python3.13 allocation_optimizer.py
./venv/bin/python3.13 promotion_report.py
./venv/bin/python3.13 -m trading_bot.core.manager
./venv/bin/python3.13 dashboard.py
```

Required checks:

1. `data/live_promotion_report.json` status must be `controlled_live_ready`
2. `manager_state.json` must show:
   - `portfolio_risk.drawdown_breaker = false`
   - `portfolio_risk.stress_breaker = false`
   - `promotion_readiness.failed_gates = 0`
3. `dashboard.html` and `todo.html` regenerate without errors
4. Cron page must show recent manager success
5. Exchange credentials must be verified manually before any live mode change

## 3. Normal operating loop

Every cycle should produce these artifacts:

- `manager_state.json`
- `performance_journal.json`
- `data/allocation_optimizer_snapshot.json`
- `data/live_promotion_report.json`
- `dashboard.html`
- `todo.html`

Operator review checklist:

- Check promotion status on dashboard / manager state
- Check attribution review section for bot share, recent trade PnL, and regime shifts
- Check roadmap page after major changes so completed items remain synced
- Check cron page for recent errors before trusting dashboards

## 4. Incident handling

### A. Manager run failed

1. Re-run locally:

```bash
./venv/bin/python3.13 -m trading_bot.core.manager
```

2. If manager fails, inspect:

```bash
git status --short
./venv/bin/python3.13 promotion_report.py
./venv/bin/python3.13 dashboard.py
```

3. If caused by dashboard generation only, restore dashboard output separately:

```bash
./venv/bin/python3.13 dashboard.py
```

### B. Promotion status regresses

1. Open `data/live_promotion_report.json`
2. Read failed gates and next actions
3. Do not enable live mode until all failed gates are cleared
4. Keep `config.json` in paper mode while debugging

### C. Risk breaker trips

1. Confirm in `manager_state.json`:
   - `portfolio_risk.drawdown_breaker`
   - `portfolio_risk.stress_breaker`
2. Treat as no-new-risk condition
3. Re-run manager only after reviewing open positions and recent journal entries
4. If needed, revert recent non-doc code changes before the next cron tick

### D. Dashboard / roadmap mismatch

Resync store and regenerate pages:

```bash
./venv/bin/python3.13 - <<'PY'
from trading_bot.dashboards.data_store import sync_all
print(sync_all())
PY
./venv/bin/python3.13 dashboard.py
```

## 5. Rollback steps

### Soft rollback (recommended first)

Use when code is correct but readiness or outputs are questionable.

1. Keep `config.json` in paper mode
2. Re-run:

```bash
./venv/bin/python3.13 promotion_report.py
./venv/bin/python3.13 -m trading_bot.core.manager
```

3. Verify promotion status returns to `paper_only` or `shadow_live_only` if expected

### Code rollback

Use when a recent code change breaks manager, dashboards, or scoring.

```bash
git log --oneline -5
git revert <commit>
git push
```

After revert:

```bash
./venv/bin/python3.13 -m trading_bot.core.manager
./venv/bin/python3.13 dashboard.py
```

### State rollback

Only if runtime JSON became corrupted or obviously invalid.

1. Stop making new edits
2. Back up current state files
3. Restore the last known good copies of:
   - `manager_state.json`
   - `manager_portfolio.json`
   - `performance_journal.json`
   - `paper_*.json`
4. Re-run manager and dashboard generation

## 6. Live mode cutover notes

When you do decide to move beyond paper:

1. create a dedicated live config snapshot first
2. keep paper cron running in parallel for comparison during the first phase
3. use the promotion gates as blocking conditions, not suggestions
4. size down the first live allocation window
5. do not combine code changes and live cutover in the same session

## 7. Fast command reference

```bash
# refresh intelligence inputs
./venv/bin/python3.13 candidate_scorer.py
./venv/bin/python3.13 allocation_optimizer.py
./venv/bin/python3.13 promotion_report.py

# run manager and rebuild dashboards
./venv/bin/python3.13 -m trading_bot.core.manager
./venv/bin/python3.13 dashboard.py

# verify roadmap sync
./venv/bin/python3.13 - <<'PY'
from trading_bot.dashboards.data_store import sync_all, load_todo_items
print(sync_all())
print(load_todo_items()[:5])
PY
```
