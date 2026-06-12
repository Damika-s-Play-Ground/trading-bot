# Walk-forward validation and dry-run promotion gate

This is the promotion rule for trading-bot strategy changes:

> Do not promote a strategy, pairlist, or parameter change from raw backtest PnL alone.

A candidate must pass rolling walk-forward evidence first, then run side by side against an unchanged dry-run control before it is promoted.

## Default rolling windows

Use the wrapper:

```bash
./venv/bin/python3.13 walk_forward_validation.py \
  --start 2025-01-01 \
  --end 2026-06-01 \
  --min-train-trades 60 \
  --min-test-trades 20 \
  --min-total-test-trades 100 \
  --output data/walk_forward_evidence.json
```

To populate the windows from closed-trade output instead of writing an empty template, pass a JSON file containing a top-level list, a common Freqtrade-style `trades` / `strategy.<name>.trades` object, or this bot's `paper_*.json` shape with `trade_log` SELL rows:

```bash
./venv/bin/python3.13 walk_forward_validation.py \
  --start 2025-01-01 \
  --end 2026-06-01 \
  --trades-json data/closed_trades_candidate.json \
  --starting-equity 1000 \
  --min-train-trades 60 \
  --min-test-trades 20 \
  --min-total-test-trades 100 \
  --output data/walk_forward_evidence.json
```

The wrapper then filters trades into each train/test window by `close_date`, `close_time`, `exit_date`, `date`, `timestamp`, or `open_date`, calculates the required metrics, and writes a `promotion_gate_summary` showing whether the candidate is eligible for side-by-side dry-run. For `paper_*.json` trade logs, only closed SELL/EXIT/CLOSE rows are treated as evidence; BUY rows are ignored.

Default policy:

- Train window: 120 days.
- Test window: 30 days immediately after the train window.
- Step: 30 days, so each new window rolls forward one test period.
- Minimum train trades: 60.
- Minimum test trades: 20 per window.
- Minimum aggregate test trades before promotion review: 100.
- Fee model: 0.10% per side by default.
- Slippage model: 0.05% per side by default.

For Freqtrade, this maps to repeated backtests with timeranges matching each generated train and test slice. The train slice is where parameters are selected. The test slice is where those selected parameters are judged without another tuning pass.

## Evidence JSON required per window

Each window in `data/walk_forward_evidence.json` must keep separate `train` and `test` sections. Both sections include `minimum_trade_count`, `passed_minimum_trades`, and a `metrics` object with these fields:

- `net_pnl_after_fees_slippage`
- `net_return_pct`
- `max_drawdown_abs`
- `max_drawdown_pct`
- `profit_factor`
- `win_rate`
- `sharpe_per_trade`
- `sortino_per_trade`
- `benchmark_return_pct`
- `benchmark_relative_return_pct`
- `trade_count`

Top-level promotion fields:

- `status`: `template_no_backtest_results_loaded`, `insufficient_walk_forward_evidence`, or `eligible_for_side_by_side_dry_run`.
- `promotion_gate_summary.train_windows_passed_min_trades`: all train windows met the train sample-size rule.
- `promotion_gate_summary.test_windows_passed_min_trades`: all test windows met the out-of-sample sample-size rule.
- `promotion_gate_summary.aggregate_test_trades`: total closed trades across all test windows.
- `promotion_gate_summary.minimum_aggregate_test_trades`: aggregate closed-trade threshold.
- `promotion_gate_summary.aggregate_test_trades_passed`: aggregate sample-size decision.

The benchmark should be the simplest relevant comparison for the same timerange, usually BTC/USDT buy-and-hold or the unchanged production/control strategy. If the candidate only wins against zero but loses badly against the control, it is not promoted.

## Promotion checklist

Before a candidate moves into a VPS/testnet/live slot:

1. Every test window has at least 20 trades unless the operator explicitly waives it for a slow strategy.
2. All test windows together have at least 100 closed trades.
3. Candidate net PnL is calculated after fees and slippage.
4. Candidate does not materially worsen max drawdown.
5. Candidate does not materially worsen profit factor.
6. Candidate does not materially worsen Sharpe/Sortino or downside metric.
7. Candidate return is compared against the benchmark/control return.
8. Candidate then runs side by side against the unchanged control for 2-3 weeks, or until at least 100 candidate trades close.
9. The control is not changed during the dry-run comparison.
10. Human review signs off before promotion.

## Side-by-side dry-run gate

Run the candidate and unchanged control at the same time with:

- Same exchange mode.
- Same timerange start date.
- Same pairlist unless the pairlist is the thing being tested.
- Same stake size.
- Same dry-run wallet.
- Same max open trades.
- Same timeframe.
- Separate DB, logs, API port, config, and dashboard identity.

Promotion requires one of these evidence thresholds:

- 21 calendar days of side-by-side dry-run evidence, or
- 100 closed candidate trades with enough matching control activity to compare.

Do not compare a static-pair control against a dynamic-pair candidate as if they were identical. If the pairlist differs, label the experiment as pairlist + strategy behavior, not pure strategy improvement.

## Isolation requirements

Each variant must have its own:

- Database: separate SQLite DB file.
- Logs: separate logfile path.
- API port: separate FreqUI/API port.
- Config: separate JSON config file.
- Dashboard identity: explicit title/label showing control or candidate.
- Data directory or artifact paths: no shared write targets for backtest, hyperopt, or runtime state.

Suggested dry-run identity pattern:

| Variant | Role | Port | DB | Log | Dashboard label |
| --- | --- | ---: | --- | --- | --- |
| `nfi_x7_control` | unchanged control | 8081 | `tradesv3_control.sqlite` | `logs/control.log` | `CONTROL NFI X7` |
| `nfi_x7_candidate_stale_profit` | candidate | 8082 | `tradesv3_candidate.sqlite` | `logs/candidate.log` | `CANDIDATE StaleProfit72h12` |

## How to use this with existing tools

1. Run the normal optimizer or Freqtrade backtest on the train slice.
2. Freeze the selected parameters.
3. Run the frozen candidate on the matching test slice.
4. Convert the train and test trades into the wrapper's metric fields.
5. Repeat for every generated window.
6. Only after the window evidence is acceptable, start side-by-side dry-run.
7. Keep the unchanged control alive until the promotion decision is made.

The wrapper creates the policy, rolling windows, populated metrics from a closed-trades JSON input, metric schema, checklist, and isolation requirements. Use an empty template only to document the expected shape; promotion remains blocked until `--trades-json` or another adapter supplies real closed-trade results.
