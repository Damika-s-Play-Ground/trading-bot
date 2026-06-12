from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from trading_bot.core.order_book_gates import _as_float, _parse_side, estimate_market_buy_slippage

BUY_ACTIONS = {"buy", "entry", "grid_buy", "dca_buy"}
EXIT_ACTIONS = {"sell", "exit", "take_profit", "stop_loss", "trailing_stop", "state_save", "save"}

REASON_OK = "ok"
REASON_BUY_DISABLED = "buy_disabled"
REASON_DAILY_LOSS_LOCK = "daily_loss_lock"
REASON_PORTFOLIO_DRAWDOWN_LOCK = "portfolio_drawdown_lock"
REASON_COOLDOWN = "pair_cooldown_active"
REASON_MAX_EXPOSURE = "max_single_coin_exposure"
REASON_EMPTY_BOOK = "empty_order_book"
REASON_STALE_BOOK = "stale_order_book"
REASON_WIDE_SPREAD = "wide_spread"
REASON_HIGH_SLIPPAGE = "high_slippage"
REASON_THIN_DEPTH = "thin_depth"
REASON_INSUFFICIENT_DEPTH = "insufficient_ask_depth"

SKIP_REASON_NAMES = {
    REASON_BUY_DISABLED: "Manager/run-level guard disabled new buys.",
    REASON_DAILY_LOSS_LOCK: "Daily realized-loss circuit breaker is active.",
    REASON_PORTFOLIO_DRAWDOWN_LOCK: "Portfolio drawdown circuit breaker is active.",
    REASON_COOLDOWN: "Pair is still inside its post-loss/per-pair cooldown window.",
    REASON_MAX_EXPOSURE: "Buying would breach the single-coin portfolio exposure cap.",
    REASON_EMPTY_BOOK: "Order book has no usable bid or ask levels.",
    REASON_STALE_BOOK: "Order book snapshot is older than the configured max age, or has no timestamp when age checking is enabled.",
    REASON_WIDE_SPREAD: "Best bid/ask spread exceeds the configured maximum.",
    REASON_HIGH_SLIPPAGE: "Estimated market-buy slippage exceeds the configured maximum.",
    REASON_THIN_DEPTH: "Near-touch ask depth is below the configured multiple of order size.",
    REASON_INSUFFICIENT_DEPTH: "The visible ask book cannot fill the requested notional.",
}


@dataclass(frozen=True)
class ExecutionRiskConfig:
    max_spread_pct: float = 0.5
    max_slippage_pct: float = 0.25
    min_near_touch_depth_multiple: float = 8.0
    near_touch_depth_window_pct: float = 1.0
    max_order_book_age_seconds: float | None = 15.0
    max_daily_loss_pct: float = 3.0
    max_portfolio_drawdown_pct: float = 15.0
    max_single_coin_exposure_pct: float = 22.0
    fail_closed_on_missing_book: bool = True


@dataclass(frozen=True)
class ExecutionRiskState:
    buy_disabled: bool = False
    daily_loss_pct: float = 0.0
    portfolio_drawdown_pct: float = 0.0
    portfolio_total_value_usdt: float = 0.0
    coin_exposure_pct: Mapping[str, float] = field(default_factory=dict)
    cooldown_pairs: Iterable[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    action: str
    symbol: str
    reasons: tuple[str, ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.allowed

    @property
    def reason(self) -> str:
        return self.reasons[0] if self.reasons else REASON_OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "ok": self.allowed,
            "action": self.action,
            "symbol": self.symbol,
            "reason": self.reason,
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
        }


def _now_ts(now: datetime | None = None) -> float:
    dt = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _book_timestamp_seconds(order_book: Mapping[str, Any]) -> float | None:
    for key in ("timestamp", "time", "event_time", "E", "lastUpdateTime", "updated_at"):
        if key not in order_book:
            continue
        raw = order_book.get(key)
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except ValueError:
                raw = _as_float(raw, 0.0)
        value = _as_float(raw, 0.0)
        if value <= 0:
            continue
        return value / 1000.0 if value > 10_000_000_000 else value
    return None


def _depth_within_window(levels: list[tuple[float, float]], mid_price: float, window_pct: float, side: str) -> float:
    if mid_price <= 0:
        return 0.0
    window = window_pct / 100.0
    total = 0.0
    for price, qty in levels:
        if side == "asks" and price <= mid_price * (1 + window):
            total += price * qty
        elif side == "bids" and price >= mid_price * (1 - window):
            total += price * qty
    return total


def evaluate_order_book_gate(
    symbol: str,
    order_book: Mapping[str, Any] | None,
    trade_notional_usdt: float,
    config: ExecutionRiskConfig,
    *,
    now: datetime | None = None,
) -> tuple[list[str], dict[str, Any]]:
    metrics: dict[str, Any] = {"trade_notional_usdt": round(float(trade_notional_usdt), 4)}
    if not order_book:
        return ([REASON_EMPTY_BOOK] if config.fail_closed_on_missing_book else []), metrics

    ts = _book_timestamp_seconds(order_book)
    if config.max_order_book_age_seconds is not None:
        if ts is None:
            metrics["order_book_age_seconds"] = None
            return [REASON_STALE_BOOK], metrics
        age = max(0.0, _now_ts(now) - ts)
        metrics["order_book_age_seconds"] = round(age, 3)
        if age > config.max_order_book_age_seconds:
            return [REASON_STALE_BOOK], metrics

    bids = _parse_side(order_book.get("bids"))
    asks = _parse_side(order_book.get("asks"))
    if not bids or not asks:
        return [REASON_EMPTY_BOOK], metrics

    best_bid = bids[0][0]
    best_ask = asks[0][0]
    mid_price = (best_bid + best_ask) / 2.0 if best_bid > 0 and best_ask > 0 else 0.0
    spread_pct = ((best_ask - best_bid) / mid_price * 100.0) if mid_price > 0 else 0.0
    fill = estimate_market_buy_slippage(asks, trade_notional_usdt)
    ask_depth_usdt = _depth_within_window(asks, mid_price, config.near_touch_depth_window_pct, "asks")
    bid_depth_usdt = _depth_within_window(bids, mid_price, config.near_touch_depth_window_pct, "bids")
    depth_multiple = ask_depth_usdt / trade_notional_usdt if trade_notional_usdt > 0 else 0.0
    metrics.update(
        {
            "best_bid": round(best_bid, 12),
            "best_ask": round(best_ask, 12),
            "mid_price": round(mid_price, 12),
            "spread_pct": round(spread_pct, 6),
            "slippage_pct": fill["slippage_pct"],
            "avg_fill_price": fill["avg_price"],
            "filled": fill["filled"],
            "ask_depth_usdt": round(ask_depth_usdt, 4),
            "bid_depth_usdt": round(bid_depth_usdt, 4),
            "depth_multiple": round(depth_multiple, 4),
        }
    )

    reasons: list[str] = []
    if spread_pct > config.max_spread_pct:
        reasons.append(REASON_WIDE_SPREAD)
    if not fill["filled"]:
        reasons.append(REASON_INSUFFICIENT_DEPTH)
    if fill["slippage_pct"] > config.max_slippage_pct:
        reasons.append(REASON_HIGH_SLIPPAGE)
    if depth_multiple < config.min_near_touch_depth_multiple:
        reasons.append(REASON_THIN_DEPTH)
    return reasons, metrics


def evaluate_execution_gate(
    *,
    action: str,
    symbol: str,
    trade_notional_usdt: float = 0.0,
    order_book: Mapping[str, Any] | None = None,
    config: ExecutionRiskConfig | None = None,
    state: ExecutionRiskState | None = None,
    now: datetime | None = None,
) -> GateDecision:
    """Return allow/deny for a proposed execution action.

    Sell/exit/state-save actions bypass buy-only locks so the bot can reduce risk
    and persist state even while entries are disabled.
    """
    cfg = config or ExecutionRiskConfig()
    st = state or ExecutionRiskState()
    normalized_action = action.lower().strip()
    normalized_symbol = symbol.upper().replace("/USDT", "").replace("USDT", "")

    if normalized_action in EXIT_ACTIONS or normalized_action not in BUY_ACTIONS:
        return GateDecision(True, normalized_action, normalized_symbol, metrics={"bypass": "non_buy_action"})

    reasons: list[str] = []
    metrics: dict[str, Any] = {}
    if st.buy_disabled:
        reasons.append(REASON_BUY_DISABLED)
    if st.daily_loss_pct >= cfg.max_daily_loss_pct:
        reasons.append(REASON_DAILY_LOSS_LOCK)
    if st.portfolio_drawdown_pct >= cfg.max_portfolio_drawdown_pct:
        reasons.append(REASON_PORTFOLIO_DRAWDOWN_LOCK)
    if normalized_symbol in {str(pair).upper().replace("/USDT", "").replace("USDT", "") for pair in st.cooldown_pairs}:
        reasons.append(REASON_COOLDOWN)

    current_exposure = _as_float(st.coin_exposure_pct.get(normalized_symbol, 0.0), 0.0)
    projected_exposure = current_exposure
    if st.portfolio_total_value_usdt > 0 and trade_notional_usdt > 0:
        projected_exposure = current_exposure + (trade_notional_usdt / st.portfolio_total_value_usdt * 100.0)
    metrics["current_coin_exposure_pct"] = round(current_exposure, 6)
    metrics["projected_coin_exposure_pct"] = round(projected_exposure, 6)
    if projected_exposure >= cfg.max_single_coin_exposure_pct:
        reasons.append(REASON_MAX_EXPOSURE)

    book_reasons, book_metrics = evaluate_order_book_gate(normalized_symbol, order_book, trade_notional_usdt, cfg, now=now)
    reasons.extend(book_reasons)
    metrics.update(book_metrics)
    unique_reasons = tuple(dict.fromkeys(reasons))
    return GateDecision(not unique_reasons, normalized_action, normalized_symbol, unique_reasons, metrics)


def compact_execution_gate_reason(decision: GateDecision | Mapping[str, Any]) -> str:
    data = decision.to_dict() if isinstance(decision, GateDecision) else dict(decision)
    reasons = data.get("reasons") or []
    metrics = data.get("metrics") or {}
    parts = []
    for key, label in (
        ("spread_pct", "spread"),
        ("slippage_pct", "slippage"),
        ("depth_multiple", "depth×"),
        ("order_book_age_seconds", "book_age"),
        ("projected_coin_exposure_pct", "projected_exposure"),
    ):
        if key in metrics and metrics.get(key) is not None:
            suffix = "%" if key in {"spread_pct", "slippage_pct", "projected_coin_exposure_pct"} else ("s" if key == "order_book_age_seconds" else "")
            parts.append(f"{label}={_as_float(metrics.get(key)):.3f}{suffix}")
    prefix = ", ".join(reasons) if reasons else REASON_OK
    return prefix + (" | " + ", ".join(parts) if parts else "")
