#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_bot.dashboards.data_store import load_performance_runs, load_todo_items, sync_all_if_needed, todo_stats
from trading_bot.dashboards.spot_dashboard import (
    BASE_DIR,
    BOT_FILES,
    CRON_JOBS,
    MANAGER_FILE,
    SPOT_OUTPUT,
    REGIME_ICONS,
    _trade_why,
    age_label,
    fetch_prices,
    fmt_money,
    fmt_pct,
    iter_position_rows,
    load_cron_runs,
    load_json,
    parse_time,
)

STATIC_DIR = BASE_DIR / "static"
PAYLOAD_TTL_SECONDS = 20.0
PRICE_TTL_SECONDS = 15.0
INDICATOR_TTL_SECONDS = 900.0

_PRICE_CACHE = {"ts": 0.0, "data": {}}
_INDICATOR_CACHE: dict[str, dict[str, Any]] = {}
_PAYLOAD_CACHE = {"ts": 0.0, "payload": None}

BOT_SIGNAL_HINTS = {
    "dca": "Mean-reversion setup: oversold RSI, MACD confirmation, Bollinger support, healthy volume.",
    "trend": "Trend setup: price above 20/50 MA with bullish MACD histogram and supportive volume.",
    "grid": "Range setup: price rotating inside the active grid bands and filling passive ladder orders.",
    "momentum": "Breakout setup: price above MA, RSI strength, and volume spike above normal activity.",
    "deep_mr": "Extreme mean-reversion setup: deeply oversold RSI with enough volume for a bounce.",
}

BOT_WATCHLISTS = {
    "dca": ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT", "MATIC", "NEAR", "ARB", "OP", "ATOM", "INJ", "RNDR", "FET", "GRT", "IMX"],
    "trend": ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "ADA", "AVAX", "DOT", "NEAR"],
    "grid": ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK"],
    "momentum": ["BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "ADA", "AVAX", "DOT", "NEAR", "ARB", "OP"],
    "deep_mr": ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT", "NEAR"],
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def _calc_sma(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return values[-1]
    return sum(values[-period:]) / period


def _calc_ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return values[-1]
    multiplier = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = (value - result) * multiplier + result
    return result


def _calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    gains = 0.0
    losses = 0.0
    for idx in range(-period, 0):
        diff = closes[idx] - closes[idx - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _calc_macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float]:
    if len(closes) < slow + signal:
        return 0.0, 0.0, 0.0
    fast_emas: list[float] = []
    slow_emas: list[float] = []
    fast_mult = 2 / (fast + 1)
    slow_mult = 2 / (slow + 1)
    fast_ema = closes[0]
    slow_ema = closes[0]
    for close in closes:
        fast_ema = (close - fast_ema) * fast_mult + fast_ema
        slow_ema = (close - slow_ema) * slow_mult + slow_ema
        fast_emas.append(fast_ema)
        slow_emas.append(slow_ema)
    macd_line_series = [f - s for f, s in zip(fast_emas, slow_emas)]
    signal_mult = 2 / (signal + 1)
    signal_ema = macd_line_series[0]
    for point in macd_line_series:
        signal_ema = (point - signal_ema) * signal_mult + signal_ema
    macd_line = macd_line_series[-1]
    histogram = macd_line - signal_ema
    return macd_line, signal_ema, histogram


def _fetch_klines(symbol: str, interval: str = "1h", limit: int = 120) -> list[dict[str, float]]:
    qs = urllib.parse.urlencode({"symbol": f"{symbol}USDT", "interval": interval, "limit": limit})
    url = f"https://api.binance.com/api/v3/klines?{qs}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=12) as response:
        payload = json.loads(response.read())
    return [
        {
            "open": _safe_float(row[1]),
            "high": _safe_float(row[2]),
            "low": _safe_float(row[3]),
            "close": _safe_float(row[4]),
            "volume": _safe_float(row[7]),
        }
        for row in payload
    ]


def _indicator_snapshot(symbol: str, cache: dict[str, Any]) -> dict[str, Any] | None:
    now = time.time()
    if symbol in cache:
        return cache[symbol]
    cached = _INDICATOR_CACHE.get(symbol)
    if cached and (now - float(cached.get("ts") or 0.0)) < INDICATOR_TTL_SECONDS:
        cache[symbol] = cached.get("payload")
        return cache[symbol]
    try:
        klines = _fetch_klines(symbol)
        closes = [row["close"] for row in klines]
        volumes = [row["volume"] for row in klines]
        price = closes[-1] if closes else 0.0
        rsi = _calc_rsi(closes)
        sma20 = _calc_sma(closes, 20)
        sma50 = _calc_sma(closes, 50)
        macd_line, signal_line, histogram = _calc_macd(closes)
        curr_vol = volumes[-1] if volumes else 0.0
        avg_vol = sum(volumes[-20:]) / max(len(volumes[-20:]), 1)
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 0.0
        upper_gap = ((price - sma20) / sma20 * 100) if sma20 else 0.0
        snapshot = {
            "symbol": symbol,
            "price": round(price, 6),
            "rsi": round(rsi, 2),
            "macd": round(macd_line, 6),
            "macd_signal": round(signal_line, 6),
            "macd_hist": round(histogram, 6),
            "ma20": round(sma20, 6),
            "ma50": round(sma50, 6),
            "volume": round(curr_vol, 2),
            "volume_avg20": round(avg_vol, 2),
            "volume_ratio": round(vol_ratio, 2),
            "price_vs_ma20_pct": round(upper_gap, 2),
            "trend": "above-ma" if price >= sma20 else "below-ma",
            "macd_bias": "bullish" if histogram >= 0 else "bearish",
        }
    except Exception:
        snapshot = cached.get("payload") if cached else None
    _INDICATOR_CACHE[symbol] = {"ts": now, "payload": snapshot}
    cache[symbol] = snapshot
    return snapshot


def _cached_prices() -> dict[str, float]:
    now = time.time()
    if _PRICE_CACHE.get("data") and (now - float(_PRICE_CACHE.get("ts") or 0.0)) < PRICE_TTL_SECONDS:
        return dict(_PRICE_CACHE["data"])
    prices = fetch_prices()
    _PRICE_CACHE["ts"] = now
    _PRICE_CACHE["data"] = dict(prices)
    return prices


def _schedule_minutes(schedule: str) -> int:
    normalized = (schedule or "").strip().lower()
    if normalized.startswith("every "):
        body = normalized[6:]
        if body.endswith("m"):
            return max(1, int(body[:-1]))
        if body.endswith("h"):
            return max(1, int(body[:-1])) * 60
    return 0


def _cron_summary(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[str(run.get("job", "unknown"))].append(run)
    output = []
    for job_key, meta in CRON_JOBS.items():
        job_runs = sorted(grouped.get(job_key, []), key=lambda item: parse_time(item.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        latest = job_runs[0] if job_runs else None
        latest_dt = parse_time(latest.get("timestamp")) if latest else None
        cadence_minutes = _schedule_minutes(meta.get("schedule", ""))
        age_minutes = max(0.0, (time.time() - latest_dt.timestamp()) / 60.0) if latest_dt else None
        status = latest.get("status", "stale") if latest else "stale"
        severity = "ok" if status == "ok" else ("warning" if status == "started" else "error")
        message = "No runs logged yet"
        missed_runs = 0
        if latest_dt:
            message = f"Last run {age_label(latest_dt)}"
            if cadence_minutes:
                missed_runs = max(0, int(math.floor(max(age_minutes - cadence_minutes, 0) / cadence_minutes))) if age_minutes is not None else 0
                if age_minutes is not None and age_minutes > cadence_minutes * 1.35:
                    severity = "warning" if status == "ok" else "error"
                    message = f"Missed expected cadence by {age_minutes - cadence_minutes:.0f}m"
                if age_minutes is not None and age_minutes > cadence_minutes * 2.2:
                    severity = "error"
                    message = f"Multiple cadence misses ({missed_runs + 1} intervals late)"
            if status == "error":
                severity = "error"
                message = latest.get("error") or message
        output.append(
            {
                "job_key": job_key,
                "name": meta.get("name", job_key),
                "schedule": meta.get("schedule", "—"),
                "details": meta.get("details", ""),
                "mode": meta.get("mode", ""),
                "job_id": meta.get("job_id", ""),
                "latest_status": status,
                "severity": severity,
                "message": message,
                "age_minutes": round(age_minutes, 1) if age_minutes is not None else None,
                "expected_minutes": cadence_minutes,
                "missed_runs": missed_runs,
                "last_run_at": latest.get("timestamp") if latest else "",
                "last_error": latest.get("error", "") if latest else "",
                "run_count": len(job_runs),
            }
        )
    return output


def _bot_payload(manager_state: dict[str, Any], prices: dict[str, float], indicator_cache: dict[str, Any]) -> list[dict[str, Any]]:
    allocations = manager_state.get("allocation", {})
    performance = manager_state.get("performance", {})
    portfolio_total = 0.0
    cards: list[dict[str, Any]] = []
    for bot in BOT_FILES:
        state = load_json(BASE_DIR / bot["file"], {})
        positions = iter_position_rows(state.get("positions", {}), prices)
        usdt = _safe_float(state.get("usdt"))
        positions_value = sum(_safe_float(row.get("qty")) * _safe_float(row.get("current")) for row in positions)
        total = usdt + positions_value
        portfolio_total += total
        trade_log = [item for item in state.get("trade_log", []) if isinstance(item, dict)]
        trade_log.sort(key=lambda item: parse_time(item.get("time")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        perf = performance.get(bot["key"], {}) if isinstance(performance.get(bot["key"], {}), dict) else {}
        last_trade = trade_log[0] if trade_log else {}
        touched_symbols = []
        for row in positions:
            coin = str(row.get("coin", "")).upper()
            if coin and coin not in touched_symbols:
                touched_symbols.append(coin)
        for trade in trade_log[:3]:
            coin = str(trade.get("coin", "")).upper()
            if coin and coin not in touched_symbols:
                touched_symbols.append(coin)
        for coin in BOT_WATCHLISTS.get(bot["key"], []):
            if len(touched_symbols) >= 4:
                break
            if coin not in touched_symbols:
                touched_symbols.append(coin)
        signal_snapshots = [snapshot for coin in touched_symbols[:4] if (snapshot := _indicator_snapshot(coin, indicator_cache))]
        cards.append(
            {
                "key": bot["key"],
                "name": bot["name"],
                "icon": bot["icon"],
                "color": bot["color"],
                "allocation_pct": round(_safe_float(allocations.get(bot["key"])), 2),
                "value": round(total, 2),
                "total_value": round(total, 2),
                "usdt": round(usdt, 2),
                "positions_value": round(positions_value, 2),
                "positions_count": len(positions),
                "position_count": len(positions),
                "trade_count": len(trade_log),
                "trades_24h": len([
                    item
                    for item in trade_log
                    if ((trade_ts := parse_time(item.get("time"))) is not None)
                    and (datetime.now(timezone.utc) - trade_ts).total_seconds() <= 86400
                ]),
                "target_capital": round(_safe_float(perf.get("target_capital", total)), 2),
                "drift_pct": round(_safe_float(perf.get("drift_pct")), 2),
                "win_rate": perf.get("win_rate"),
                "profit_factor": perf.get("profit_factor"),
                "expectancy": perf.get("expectancy"),
                "total_return_pct": perf.get("total_return_pct"),
                "drawdown_pct": perf.get("drawdown_pct"),
                "realized_pnl_recent": perf.get("realized_pnl_recent"),
                "unrealized_pnl": perf.get("unrealized_pnl"),
                "portfolio_pct": 0.0,
                "portfolio_share": 0.0,
                "positions": sorted(
                    [
                        {
                            "coin": row["coin"],
                            "qty": round(_safe_float(row["qty"]), 6),
                            "avg": round(_safe_float(row["avg"]), 6),
                            "current": round(_safe_float(row["current"]), 6),
                            "value": round(_safe_float(row["qty"]) * _safe_float(row["current"]), 2),
                            "pnl_pct": round(((_safe_float(row["current"]) - _safe_float(row["avg"])) / _safe_float(row["avg"]) * 100) if _safe_float(row["avg"]) else 0.0, 2),
                        }
                        for row in positions
                    ],
                    key=lambda item: _safe_float(item.get("value")),
                    reverse=True,
                ),
                "last_trade": {
                    "time": last_trade.get("time", ""),
                    "action": last_trade.get("action", ""),
                    "coin": last_trade.get("coin", ""),
                    "price": round(_safe_float(last_trade.get("price")), 6),
                    "qty": round(_safe_float(last_trade.get("qty")), 6),
                    "usdt": round(_safe_float(last_trade.get("usdt")), 2),
                    "pnl": last_trade.get("pnl"),
                    "reason": (str(last_trade.get("reason", "")).strip() or _trade_why({**last_trade, "bot": bot["name"]}, manager_state)).replace("Buy logic: ", "").replace("Sell logic: ", ""),
                },
                "recent_trade_reasons": [
                    {
                        "time": item.get("time", ""),
                        "action": item.get("action", ""),
                        "coin": item.get("coin", ""),
                        "reason": (str(item.get("reason", "")).strip() or _trade_why({**item, "bot": bot["name"]}, manager_state)).replace("Buy logic: ", "").replace("Sell logic: ", ""),
                    }
                    for item in trade_log[:3]
                ],
                "signal_hint": BOT_SIGNAL_HINTS.get(bot["key"], ""),
                "signal_snapshots": signal_snapshots,
                "last_run": state.get("last_run", {}),
            }
        )
    for card in cards:
        share = round((card["value"] / portfolio_total * 100), 2) if portfolio_total else 0.0
        card["portfolio_pct"] = share
        card["portfolio_share"] = share
    return cards


def _recent_trades_payload(cards: list[dict[str, Any]], manager_state: dict[str, Any], indicator_cache: dict[str, Any]) -> list[dict[str, Any]]:
    recent = []
    color_by_name = {bot["name"]: bot["color"] for bot in BOT_FILES}
    for card in cards:
        name = card["name"]
        state = load_json(BASE_DIR / next(bot["file"] for bot in BOT_FILES if bot["name"] == name), {})
        for trade in state.get("trade_log", []) if isinstance(state.get("trade_log", []), list) else []:
            if not isinstance(trade, dict):
                continue
            symbol = str(trade.get("coin", "")).upper()
            snapshot = _indicator_snapshot(symbol, indicator_cache) if symbol else None
            reason_text = (str(trade.get("reason", "")).strip() or _trade_why({**trade, "bot": name}, manager_state)).replace("Buy logic: ", "").replace("Sell logic: ", "")
            recent.append(
                {
                    "time": trade.get("time", ""),
                    "action": str(trade.get("action", "")).upper(),
                    "coin": symbol,
                    "bot": name,
                    "bot_color": color_by_name.get(name, "#334155"),
                    "price": round(_safe_float(trade.get("price")), 6),
                    "qty": round(_safe_float(trade.get("qty")), 6),
                    "usdt": round(_safe_float(trade.get("usdt")), 2),
                    "pnl": trade.get("pnl"),
                    "reason": reason_text,
                    "indicators": snapshot,
                }
            )
    recent.sort(key=lambda item: parse_time(item.get("time")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return recent[:18]


def _chart_payload(cards: list[dict[str, Any]], performance_runs: list[dict[str, Any]]) -> dict[str, Any]:
    equity_points = []
    for run in performance_runs[-180:]:
        ts = parse_time(run.get("timestamp"))
        local_label = ts.astimezone().strftime("%m-%d %H:%M") if ts else ""
        equity_points.append(
            {
                "label": local_label,
                "display_label": local_label,
                "timestamp": run.get("timestamp") or "",
                "value": round(_safe_float(run.get("portfolio_total")), 2),
                "regime": run.get("regime", ""),
                "unrealized_pnl": round(_safe_float(run.get("unrealized_pnl")), 2),
                "realized_pnl_recent": round(_safe_float(run.get("realized_pnl_recent")), 2),
                "combined_loss_pct": round(_safe_float(run.get("combined_loss_pct")), 2),
            }
        )
    return {
        "allocation": [
            {"label": card["name"], "value": card["value"], "color": card["color"], "share": card["portfolio_pct"]}
            for card in cards
        ],
        "activity": [
            {"label": card["name"], "value": card["trade_count"], "color": card["color"], "meta": f"{card['positions_count']} open positions"}
            for card in cards
        ],
        "equity": equity_points,
    }


def _attribution_payload(
    cards: list[dict[str, Any]],
    performance_runs: list[dict[str, Any]],
    recent_trades: list[dict[str, Any]],
    manager_state: dict[str, Any],
) -> dict[str, Any]:
    perf = manager_state.get("performance", {}) if isinstance(manager_state.get("performance"), dict) else {}
    bot_rows = []
    for card in sorted(cards, key=lambda item: _safe_float(item.get("value")), reverse=True):
        metrics = perf.get(card["key"], {}) if isinstance(perf.get(card["key"]), dict) else {}
        bot_rows.append(
            {
                "key": card["key"],
                "name": card["name"],
                "value": round(_safe_float(card.get("value")), 2),
                "portfolio_pct": round(_safe_float(card.get("portfolio_pct")), 2),
                "unrealized_pnl": round(_safe_float(metrics.get("unrealized_pnl")), 2),
                "realized_recent": round(_safe_float(metrics.get("realized_pnl_recent")), 2),
                "drawdown_pct": round(_safe_float(metrics.get("drawdown_pct")), 2),
                "combined_multiplier": round(_safe_float(metrics.get("combined_multiplier", metrics.get("multiplier", 1.0))), 3),
                "optimizer_bias": metrics.get("optimizer_bias", "hold"),
            }
        )

    trade_groups: dict[str, dict[str, Any]] = {}
    for trade in recent_trades:
        bot_name = str(trade.get("bot") or "Unknown")
        item = trade_groups.setdefault(bot_name, {"bot": bot_name, "count": 0, "sell_count": 0, "buy_count": 0, "pnl": 0.0, "notional": 0.0})
        action = str(trade.get("action") or "").upper()
        item["count"] += 1
        item["pnl"] += _safe_float(trade.get("pnl"))
        item["notional"] += _safe_float(trade.get("usdt"))
        if "SELL" in action:
            item["sell_count"] += 1
        else:
            item["buy_count"] += 1
    trade_rows = sorted(trade_groups.values(), key=lambda item: (item["pnl"], item["count"]), reverse=True)
    for item in trade_rows:
        item["pnl"] = round(item["pnl"], 2)
        item["notional"] = round(item["notional"], 2)

    regime_counts: dict[str, int] = {}
    transitions = []
    previous = None
    recent_runs = performance_runs[-30:]
    for run in recent_runs:
        regime = str(run.get("regime") or "sideways")
        regime_counts[regime] = regime_counts.get(regime, 0) + 1
        if previous and previous != regime:
            transitions.append({
                "from": previous,
                "to": regime,
                "timestamp": run.get("timestamp") or "",
            })
        previous = regime

    promotion = manager_state.get("promotion_readiness", {}) if isinstance(manager_state.get("promotion_readiness"), dict) else {}
    return {
        "bot_contribution": bot_rows,
        "trade_attribution": trade_rows,
        "regime_review": {
            "current": manager_state.get("regime", "sideways"),
            "counts": regime_counts,
            "transitions": transitions[-6:],
            "latest_status": promotion.get("status", "paper_only"),
            "failed_gates": promotion.get("summary", {}).get("failed_gates", 0),
            "samples": len(recent_runs),
        },
    }


def dashboard_payload() -> dict[str, Any]:
    now = time.time()
    cached_payload = _PAYLOAD_CACHE.get("payload")
    if cached_payload is not None and (now - float(_PAYLOAD_CACHE.get("ts") or 0.0)) < PAYLOAD_TTL_SECONDS:
        return cached_payload
    sync_all_if_needed(min_interval=5.0)
    manager_state = load_json(MANAGER_FILE, {})
    prices = _cached_prices()
    indicator_cache: dict[str, Any] = {}
    cards = _bot_payload(manager_state, prices, indicator_cache)
    performance_runs = load_performance_runs(80)
    cron_runs = load_cron_runs()
    recent_trades = _recent_trades_payload(cards, manager_state, indicator_cache)
    portfolio_total = round(sum(card["value"] for card in cards), 2)
    todo_items = load_todo_items()
    todo_summary = todo_stats(todo_items)
    latest_run = performance_runs[-1] if performance_runs else {}
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regime": manager_state.get("regime", "sideways"),
        "regime_label": REGIME_ICONS.get(manager_state.get("regime", "sideways"), "➡️ SIDEWAYS"),
        "summary": {
            "portfolio_total": portfolio_total,
            "portfolio_drawdown_pct": round(_safe_float(manager_state.get("portfolio_drawdown_pct")), 2),
            "peak_total_value": round(_safe_float(manager_state.get("peak_total_value")), 2),
            "positions_total": sum(card["positions_count"] for card in cards),
            "trades_total": sum(card["trade_count"] for card in cards),
            "bots_total": len(cards),
            "todo_open": todo_summary.get("open", 0),
            "todo_done": todo_summary.get("done", 0),
            "realized_pnl_recent": round(_safe_float(manager_state.get("portfolio_risk", {}).get("recent_realized_pnl")), 2),
            "unrealized_pnl": round(_safe_float(manager_state.get("portfolio_risk", {}).get("unrealized_pnl")), 2),
            "combined_loss_pct": round(_safe_float(manager_state.get("portfolio_risk", {}).get("combined_loss_pct")), 2),
            "latest_equity": round(_safe_float(latest_run.get("portfolio_total", portfolio_total)), 2),
        },
        "charts": _chart_payload(cards, performance_runs),
        "analytics": _attribution_payload(cards, performance_runs, recent_trades, manager_state),
        "bots": cards,
        "recent_trades": recent_trades,
        "cron": _cron_summary(cron_runs),
        "todo": {
            "stats": todo_summary,
            "items": [
                {
                    "item_key": item.get("item_key"),
                    "text": item.get("text"),
                    "status": item.get("status"),
                    "base_status": item.get("base_status"),
                    "section": item.get("section"),
                    "category": (item.get("payload") or {}).get("category", "other"),
                    "sort_order": item.get("sort_order"),
                }
                for item in todo_items
            ],
        },
    }
    _PAYLOAD_CACHE["ts"] = now
    _PAYLOAD_CACHE["payload"] = payload
    return payload


def build_dashboard_shell() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    html = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Trading Dashboard</title>
  <link rel=\"stylesheet\" href=\"/static/dashboard.css\" />
</head>
<body>
  <div id=\"app\">Loading dashboard…</div>
  <script src=\"/static/vendor/vue.global.prod.js\"></script>
  <script src=\"/static/dashboard-app.js\"></script>
</body>
</html>
"""
    Path(SPOT_OUTPUT).write_text(html)
