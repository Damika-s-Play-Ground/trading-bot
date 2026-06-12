from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable

from trading_bot.core.state_store import save_json_path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_ROOT / "data" / "walk_forward_evidence.json"


@dataclass(frozen=True)
class WalkForwardPolicy:
    train_days: int = 120
    test_days: int = 30
    step_days: int = 30
    min_train_trades: int = 60
    min_test_trades: int = 20
    min_total_test_trades_for_promotion: int = 100
    min_dry_run_days: int = 21
    min_dry_run_trades: int = 100
    fee_bps_per_side: float = 10.0
    slippage_bps_per_side: float = 5.0


@dataclass(frozen=True)
class WalkForwardWindow:
    index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str


def parse_day(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def iso_day(value: date) -> str:
    return value.isoformat()


def build_rolling_windows(start: str | date, end: str | date, policy: WalkForwardPolicy) -> list[WalkForwardWindow]:
    start_day = parse_day(start)
    end_day = parse_day(end)
    if start_day >= end_day:
        raise ValueError("start must be before end")
    if min(policy.train_days, policy.test_days, policy.step_days) <= 0:
        raise ValueError("train_days, test_days and step_days must be positive")

    windows: list[WalkForwardWindow] = []
    train_start = start_day
    idx = 1
    while True:
        train_end = train_start + timedelta(days=policy.train_days)
        test_start = train_end
        test_end = test_start + timedelta(days=policy.test_days)
        if test_end > end_day:
            break
        windows.append(
            WalkForwardWindow(
                index=idx,
                train_start=iso_day(train_start),
                train_end=iso_day(train_end),
                test_start=iso_day(test_start),
                test_end=iso_day(test_end),
            )
        )
        idx += 1
        train_start = train_start + timedelta(days=policy.step_days)
    if not windows:
        raise ValueError("date range is too short for the configured train/test windows")
    return windows


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _trade_profit_abs(trade: dict[str, Any], policy: WalkForwardPolicy) -> float:
    """Return net trade PnL after explicit or estimated fee/slippage costs.

    Accepted inputs are intentionally broad so this wrapper can sit around either
    local Python backtests or exported Freqtrade JSON/CSV transforms.
    """
    if trade.get("net_pnl") is not None:
        return _safe_float(trade.get("net_pnl"))

    gross = _safe_float(
        trade.get("profit_abs")
        if trade.get("profit_abs") is not None
        else trade.get("pnl_abs")
        if trade.get("pnl_abs") is not None
        else trade.get("profit")
    )
    explicit_cost = _safe_float(trade.get("fees")) + _safe_float(trade.get("slippage"))
    if explicit_cost:
        return gross - explicit_cost

    stake = _safe_float(trade.get("stake_amount") or trade.get("stake") or trade.get("notional"))
    if stake <= 0:
        return gross
    round_trip_bps = 2 * (policy.fee_bps_per_side + policy.slippage_bps_per_side)
    return gross - (stake * round_trip_bps / 10_000.0)


def _trade_return(trade: dict[str, Any], net_pnl: float) -> float:
    stake = _safe_float(trade.get("stake_amount") or trade.get("stake") or trade.get("notional"))
    if stake > 0:
        return net_pnl / stake
    for key in ("profit_ratio", "profit_pct", "pnl_pct", "return_pct"):
        if trade.get(key) is not None:
            value = _safe_float(trade.get(key))
            return value / 100.0 if abs(value) > 1 else value
    return 0.0

def summarize_trades(
    trades: Iterable[dict[str, Any]],
    *,
    starting_equity: float,
    policy: WalkForwardPolicy,
    benchmark_return_pct: float = 0.0,
) -> dict[str, Any]:
    trade_list = list(trades)
    net_pnls = [_trade_profit_abs(trade, policy) for trade in trade_list]
    returns = [_trade_return(trade, pnl) for trade, pnl in zip(trade_list, net_pnls, strict=False)]
    trade_count = len(net_pnls)
    wins = [pnl for pnl in net_pnls if pnl > 0]
    losses = [pnl for pnl in net_pnls if pnl < 0]
    net_pnl = sum(net_pnls)

    equity = starting_equity
    peak = starting_equity
    max_drawdown = 0.0
    for pnl in net_pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    profit_factor = None
    gross_loss = abs(sum(losses))
    if gross_loss > 0:
        profit_factor = sum(wins) / gross_loss
    elif wins:
        profit_factor = math.inf

    avg_return = mean(returns) if returns else 0.0
    std_return = pstdev(returns) if len(returns) > 1 else 0.0
    downside = [min(0.0, value) for value in returns]
    downside_std = pstdev(downside) if len(downside) > 1 else 0.0

    net_return_pct = (net_pnl / starting_equity * 100.0) if starting_equity else 0.0
    return {
        "net_pnl_after_fees_slippage": round(net_pnl, 6),
        "net_return_pct": round(net_return_pct, 6),
        "max_drawdown_abs": round(max_drawdown, 6),
        "max_drawdown_pct": round((max_drawdown / starting_equity * 100.0) if starting_equity else 0.0, 6),
        "profit_factor": None if profit_factor is None else ("inf" if math.isinf(profit_factor) else round(profit_factor, 6)),
        "win_rate": round((len(wins) / trade_count * 100.0) if trade_count else 0.0, 6),
        "sharpe_per_trade": round((avg_return / std_return) if std_return else 0.0, 6),
        "sortino_per_trade": round((avg_return / downside_std) if downside_std else 0.0, 6),
        "benchmark_return_pct": round(benchmark_return_pct, 6),
        "benchmark_relative_return_pct": round(net_return_pct - benchmark_return_pct, 6),
        "trade_count": trade_count,
    }


def empty_window_evidence(window: WalkForwardWindow, policy: WalkForwardPolicy) -> dict[str, Any]:
    return {
        "window": asdict(window),
        "train": {
            "metrics": summarize_trades([], starting_equity=1000.0, policy=policy),
            "minimum_trade_count": policy.min_train_trades,
            "passed_minimum_trades": False,
        },
        "test": {
            "metrics": summarize_trades([], starting_equity=1000.0, policy=policy),
            "minimum_trade_count": policy.min_test_trades,
            "passed_minimum_trades": False,
        },
    }


def promotion_checklist(policy: WalkForwardPolicy) -> list[dict[str, Any]]:
    return [
        {
            "item": "walk_forward_test_windows_passed",
            "requirement": f"Each test window has >= {policy.min_test_trades} trades and acceptable drawdown / profit-factor evidence.",
        },
        {
            "item": "aggregate_test_sample_size",
            "requirement": f"All test windows together have >= {policy.min_total_test_trades_for_promotion} closed trades.",
        },
        {
            "item": "side_by_side_dry_run",
            "requirement": f"Run candidate beside unchanged control for {policy.min_dry_run_days} days or >= {policy.min_dry_run_trades} candidate trades, whichever gives enough evidence first.",
        },
        {
            "item": "control_not_changed_mid_test",
            "requirement": "Control strategy, pairlist, stake, wallet, exchange, and timeframe stay fixed during the comparison.",
        },
        {
            "item": "candidate_beats_control_after_costs",
            "requirement": "Candidate beats control on net PnL after fees/slippage and does not worsen max drawdown, profit factor, or downside metric materially.",
        },
        {
            "item": "operator_review_required",
            "requirement": "Human review signs off before any VPS/live/testnet promotion; raw backtest PnL alone is never enough.",
        },
    ]


def isolation_requirements() -> dict[str, str]:
    return {
        "database": "One SQLite DB per variant; never share tradesv3.sqlite between control and candidate.",
        "logs": "One logfile per variant with variant name and timestamp in the path.",
        "api_port": "One FreqUI/API port per variant, bound to localhost unless intentionally exposed.",
        "config": "One config JSON per variant; pin strategy class, pairlist, stake, wallet, timeframe, and dry_run_wallet.",
        "dashboard_identity": "Dashboard title, bot_name, Telegram identity, and scoreboard label must clearly show control vs candidate.",
        "data_directory": "One user_data directory or isolated DB/log subpaths per variant to prevent artifact collisions.",
    }



def _trade_day(trade: dict[str, Any]) -> date | None:
    for key in ("close_date", "close_time", "exit_date", "date", "timestamp", "open_date"):
        value = trade.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (int, float)):
            seconds = float(value) / 1000.0 if float(value) > 10_000_000_000 else float(value)
            return datetime.fromtimestamp(seconds, tz=timezone.utc).date()
        try:
            return parse_day(str(value))
        except ValueError:
            continue
    return None


def _trades_between(trades: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    start_day = parse_day(start)
    end_day = parse_day(end)
    selected = []
    for trade in trades:
        day = _trade_day(trade)
        if day is not None and start_day <= day < end_day:
            selected.append(trade)
    return selected


def _window_section(
    trades: list[dict[str, Any]],
    *,
    starting_equity: float,
    policy: WalkForwardPolicy,
    minimum_trade_count: int,
    benchmark_return_pct: float = 0.0,
) -> dict[str, Any]:
    metrics = summarize_trades(
        trades,
        starting_equity=starting_equity,
        policy=policy,
        benchmark_return_pct=benchmark_return_pct,
    )
    return {
        "metrics": metrics,
        "minimum_trade_count": minimum_trade_count,
        "passed_minimum_trades": metrics["trade_count"] >= minimum_trade_count,
    }


def _promotion_gate_summary(windows: list[dict[str, Any]], policy: WalkForwardPolicy) -> dict[str, Any]:
    total_test_trades = sum(int(window["test"]["metrics"]["trade_count"]) for window in windows)
    train_windows_passed = all(window["train"]["passed_minimum_trades"] for window in windows)
    test_windows_passed = all(window["test"]["passed_minimum_trades"] for window in windows)
    aggregate_passed = total_test_trades >= policy.min_total_test_trades_for_promotion
    eligible = train_windows_passed and test_windows_passed and aggregate_passed
    return {
        "status": "eligible_for_side_by_side_dry_run" if eligible else "insufficient_walk_forward_evidence",
        "train_windows_passed_min_trades": train_windows_passed,
        "test_windows_passed_min_trades": test_windows_passed,
        "aggregate_test_trades": total_test_trades,
        "minimum_aggregate_test_trades": policy.min_total_test_trades_for_promotion,
        "aggregate_test_trades_passed": aggregate_passed,
        "next_gate": f"Side-by-side dry-run for {policy.min_dry_run_days} days or {policy.min_dry_run_trades} candidate trades" if eligible else "Add more out-of-sample trades before dry-run promotion review",
    }


def extract_trades(payload: Any) -> list[dict[str, Any]]:
    """Extract a flat trade list from common local/Freqtrade-style JSON shapes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("trades", "trade_list", "closed_trades", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    trade_log = payload.get("trade_log")
    if isinstance(trade_log, list):
        closed_trades = []
        for item in trade_log:
            if not isinstance(item, dict) or str(item.get("action", "")).upper() not in {"SELL", "EXIT", "CLOSE"}:
                continue
            trade = dict(item)
            if trade.get("net_pnl") is None and trade.get("pnl") is not None:
                trade["net_pnl"] = trade.get("pnl")
            if trade.get("close_date") is None and trade.get("time") is not None:
                trade["close_date"] = trade.get("time")
            if trade.get("stake_amount") is None and trade.get("usdt") is not None:
                trade["stake_amount"] = trade.get("usdt")
            closed_trades.append(trade)
        return closed_trades
    strategy = payload.get("strategy")
    if isinstance(strategy, dict):
        for strategy_payload in strategy.values():
            trades = extract_trades(strategy_payload)
            if trades:
                return trades
    return []


def build_evidence_from_trades(
    trades: list[dict[str, Any]],
    *,
    start: str,
    end: str,
    policy: WalkForwardPolicy,
    starting_equity: float = 1000.0,
) -> dict[str, Any]:
    windows = []
    for window in build_rolling_windows(start, end, policy):
        train_trades = _trades_between(trades, window.train_start, window.train_end)
        test_trades = _trades_between(trades, window.test_start, window.test_end)
        windows.append(
            {
                "window": asdict(window),
                "train": _window_section(
                    train_trades,
                    starting_equity=starting_equity,
                    policy=policy,
                    minimum_trade_count=policy.min_train_trades,
                ),
                "test": _window_section(
                    test_trades,
                    starting_equity=starting_equity,
                    policy=policy,
                    minimum_trade_count=policy.min_test_trades,
                ),
            }
        )
    gate_summary = _promotion_gate_summary(windows, policy)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": gate_summary["status"],
        "rule": "Do not promote any strategy or parameter change from raw backtest PnL alone.",
        "policy": asdict(policy),
        "windows": windows,
        "promotion_gate_summary": gate_summary,
        "promotion_checklist": promotion_checklist(policy),
        "isolation_requirements": isolation_requirements(),
    }

def build_empty_evidence(start: str, end: str, policy: WalkForwardPolicy) -> dict[str, Any]:
    windows = [empty_window_evidence(window, policy) for window in build_rolling_windows(start, end, policy)]
    gate_summary = _promotion_gate_summary(windows, policy)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "template_no_backtest_results_loaded",
        "rule": "Do not promote any strategy or parameter change from raw backtest PnL alone.",
        "policy": asdict(policy),
        "windows": windows,
        "promotion_gate_summary": gate_summary,
        "promotion_checklist": promotion_checklist(policy),
        "isolation_requirements": isolation_requirements(),
        "notes": [
            "Fill each train/test metrics object from the existing backtest, optimizer, or Freqtrade backtesting output for that exact timerange, or pass --trades-json to populate from closed trades.",
            "Then run the candidate and unchanged control side by side in dry-run before promotion.",
        ],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate walk-forward validation evidence template and promotion gate.")
    parser.add_argument("--start", required=True, help="First train-window day, e.g. 2025-01-01")
    parser.add_argument("--end", required=True, help="Exclusive end day, e.g. 2026-06-01")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Evidence JSON output path")
    parser.add_argument("--train-days", type=int, default=WalkForwardPolicy.train_days)
    parser.add_argument("--test-days", type=int, default=WalkForwardPolicy.test_days)
    parser.add_argument("--step-days", type=int, default=WalkForwardPolicy.step_days)
    parser.add_argument("--min-train-trades", type=int, default=WalkForwardPolicy.min_train_trades)
    parser.add_argument("--min-test-trades", type=int, default=WalkForwardPolicy.min_test_trades)
    parser.add_argument(
        "--min-total-test-trades",
        type=int,
        default=WalkForwardPolicy.min_total_test_trades_for_promotion,
        help="Minimum aggregate out-of-sample test trades required before promotion eligibility",
    )
    parser.add_argument("--trades-json", help="Optional closed-trades JSON to populate window metrics instead of writing an empty template")
    parser.add_argument("--starting-equity", type=float, default=1000.0, help="Starting equity used for return/drawdown percentages")
    args = parser.parse_args(argv)

    policy = WalkForwardPolicy(
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
        min_train_trades=args.min_train_trades,
        min_test_trades=args.min_test_trades,
        min_total_test_trades_for_promotion=args.min_total_test_trades,
    )
    if args.trades_json:
        payload = json.loads(Path(args.trades_json).read_text())
        trades = extract_trades(payload)
        evidence = build_evidence_from_trades(
            trades,
            start=args.start,
            end=args.end,
            policy=policy,
            starting_equity=args.starting_equity,
        )
    else:
        evidence = build_empty_evidence(args.start, args.end, policy)
    output = Path(args.output)
    save_json_path(output, evidence)
    print(f"Walk-forward evidence saved: {output}")
    print(f"Windows: {len(evidence['windows'])}")
    print(f"Status: {evidence['status']}")
    print("Promotion rule: raw backtest PnL alone is not sufficient.")


if __name__ == "__main__":
    main()
