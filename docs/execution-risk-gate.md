# Shared execution/risk gate

This module is the reusable pre-execution guard for Binance/custom spot bots:

- `trading_bot.core.execution_risk_gate.ExecutionRiskConfig`
- `trading_bot.core.execution_risk_gate.ExecutionRiskState`
- `trading_bot.core.execution_risk_gate.evaluate_execution_gate(...)`

It returns a `GateDecision` with:

- `allowed` / `ok`: boolean allow/deny
- `reason`: first dashboard-ready reason name
- `reasons`: all machine-readable reason names
- `metrics`: spread, slippage, depth, exposure, projected exposure, and order-book age details

Sell/exit/state-save actions intentionally bypass buy-only locks. This keeps risk reduction and state persistence working even when new buys are disabled.

## Dashboard/scoreboard skip reason names

| Reason | Meaning |
| --- | --- |
| `buy_disabled` | Manager/run-level guard disabled new buys. Exits and state saves still pass. |
| `daily_loss_lock` | Daily realized-loss circuit breaker is active. |
| `portfolio_drawdown_lock` | Portfolio drawdown circuit breaker is active. |
| `pair_cooldown_active` | Pair is inside its configured cooldown window. |
| `max_single_coin_exposure` | Buying would breach the projected single-coin portfolio exposure cap. |
| `empty_order_book` | Book has no usable bid or ask levels. |
| `stale_order_book` | Book snapshot or trusted fetch timestamp is older than `max_order_book_age_seconds`. |
| `unverifiable_order_book` | Book has no exchange timestamp and no explicit trusted fetch timestamp, so age cannot be verified. |
| `wide_spread` | Best bid/ask spread exceeds `max_spread_pct`. |
| `high_slippage` | Estimated market-buy slippage exceeds `max_slippage_pct`. |
| `thin_depth` | Near-touch ask depth is below `min_near_touch_depth_multiple × order size`. |
| `insufficient_ask_depth` | Visible ask depth cannot fill the requested notional. |

## Freqtrade equivalent design notes

Freqtrade equivalents should map as follows:

- Spread/slippage/depth/stale-book checks: `confirm_trade_entry()` using exchange order book data, returning `False` and logging the same reason string.
- Per-pair cooldown: Freqtrade PairLocks or a custom protection plugin.
- Daily loss and portfolio drawdown locks: Freqtrade protection (`StoplossGuard`, `MaxDrawdown`) or a custom protection that locks all pairs for entries only.
- Max single-coin exposure: custom `confirm_trade_entry()` check against open trades, wallet exposure, and projected trade size.
- Exit/state persistence bypass: do not block `confirm_trade_exit()` or DB persistence when entry protections are active.

Keep Freqtrade bots in dry-run while validating this mapping. Do not enable live trading from these notes alone.

## Live trading guardrail

This repository change adds a reusable deterministic gate and tests. It does not enable live trading. Any mainnet path still needs Binance testnet or dry-run verification with fees/slippage enabled before promotion.
