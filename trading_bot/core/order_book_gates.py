from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

BINANCE_PUBLIC_BASE = "https://api.binance.com"
DEFAULT_SETTINGS = {
    "enabled": True,
    "limit": 20,
    "depth_window_pct": 1.0,
    "max_spread_pct": 0.5,
    "max_slippage_pct": 0.25,
    "min_depth_multiple": 8.0,
    "fail_closed": True,
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def merged_settings(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    if isinstance(overrides, dict):
        for key, value in overrides.items():
            if value is not None:
                settings[key] = value
    settings["enabled"] = bool(settings.get("enabled", True))
    settings["limit"] = max(5, min(int(settings.get("limit", 20) or 20), 1000))
    settings["depth_window_pct"] = max(_as_float(settings.get("depth_window_pct"), 1.0), 0.05)
    settings["max_spread_pct"] = max(_as_float(settings.get("max_spread_pct"), 0.5), 0.0)
    settings["max_slippage_pct"] = max(_as_float(settings.get("max_slippage_pct"), 0.25), 0.0)
    settings["min_depth_multiple"] = max(_as_float(settings.get("min_depth_multiple"), 8.0), 0.0)
    settings["fail_closed"] = bool(settings.get("fail_closed", True))
    return settings


def fetch_order_book(symbol: str, limit: int = 20, base_url: str = BINANCE_PUBLIC_BASE) -> dict[str, Any]:
    query = urllib.parse.urlencode({"symbol": f"{symbol}USDT", "limit": limit})
    url = f"{base_url}/api/v3/depth?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "trading-bot-order-book-gate/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _parse_side(levels: Any) -> list[tuple[float, float]]:
    parsed: list[tuple[float, float]] = []
    for level in levels or []:
        if not isinstance(level, (list, tuple)) or len(level) < 2:
            continue
        price = _as_float(level[0])
        qty = _as_float(level[1])
        if price > 0 and qty > 0:
            parsed.append((price, qty))
    return parsed


def _depth_within_window(levels: list[tuple[float, float]], mid_price: float, window_pct: float, side: str) -> float:
    if mid_price <= 0:
        return 0.0
    window = window_pct / 100.0
    total = 0.0
    for price, qty in levels:
        if side == "asks":
            if price > mid_price * (1 + window):
                continue
        else:
            if price < mid_price * (1 - window):
                continue
        total += price * qty
    return total


def estimate_market_buy_slippage(asks: list[tuple[float, float]], trade_notional_usdt: float) -> dict[str, Any]:
    if not asks or trade_notional_usdt <= 0:
        return {
            "filled": False,
            "filled_notional_usdt": 0.0,
            "filled_qty": 0.0,
            "avg_price": 0.0,
            "best_ask": 0.0,
            "slippage_pct": 0.0,
        }

    best_ask = asks[0][0]
    remaining = trade_notional_usdt
    spent = 0.0
    qty_filled = 0.0
    for price, qty in asks:
        level_notional = price * qty
        take_notional = min(level_notional, remaining)
        if take_notional <= 0:
            continue
        take_qty = take_notional / price
        spent += take_notional
        qty_filled += take_qty
        remaining -= take_notional
        if remaining <= 1e-9:
            break

    avg_price = spent / qty_filled if qty_filled > 0 else 0.0
    slippage_pct = ((avg_price - best_ask) / best_ask * 100.0) if best_ask > 0 and avg_price > 0 else 0.0
    return {
        "filled": remaining <= 1e-9,
        "filled_notional_usdt": round(spent, 8),
        "filled_qty": round(qty_filled, 12),
        "avg_price": round(avg_price, 12),
        "best_ask": round(best_ask, 12),
        "slippage_pct": round(slippage_pct, 6),
    }


def evaluate_entry_gate_from_book(symbol: str, order_book: dict[str, Any], trade_notional_usdt: float, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = merged_settings(settings)
    if not cfg["enabled"]:
        return {"ok": True, "symbol": symbol, "trade_notional_usdt": round(trade_notional_usdt, 4), "reasons": [], "settings": cfg, "disabled": True}

    bids = _parse_side(order_book.get("bids"))
    asks = _parse_side(order_book.get("asks"))
    if not bids or not asks:
        return {
            "ok": False,
            "symbol": symbol,
            "trade_notional_usdt": round(trade_notional_usdt, 4),
            "reasons": ["empty_order_book"],
            "settings": cfg,
        }

    best_bid = bids[0][0]
    best_ask = asks[0][0]
    mid_price = (best_bid + best_ask) / 2.0 if best_bid > 0 and best_ask > 0 else 0.0
    spread_pct = ((best_ask - best_bid) / mid_price * 100.0) if mid_price > 0 else 0.0
    buy_fill = estimate_market_buy_slippage(asks, trade_notional_usdt)
    ask_depth_usdt = _depth_within_window(asks, mid_price, cfg["depth_window_pct"], side="asks")
    bid_depth_usdt = _depth_within_window(bids, mid_price, cfg["depth_window_pct"], side="bids")
    depth_multiple = (ask_depth_usdt / trade_notional_usdt) if trade_notional_usdt > 0 else 0.0

    reasons: list[str] = []
    if spread_pct > cfg["max_spread_pct"]:
        reasons.append("wide_spread")
    if not buy_fill["filled"]:
        reasons.append("insufficient_ask_depth")
    if buy_fill["slippage_pct"] > cfg["max_slippage_pct"]:
        reasons.append("high_slippage")
    if depth_multiple < cfg["min_depth_multiple"]:
        reasons.append("thin_depth")

    return {
        "ok": not reasons,
        "symbol": symbol,
        "trade_notional_usdt": round(trade_notional_usdt, 4),
        "best_bid": round(best_bid, 12),
        "best_ask": round(best_ask, 12),
        "mid_price": round(mid_price, 12),
        "spread_pct": round(spread_pct, 6),
        "slippage_pct": buy_fill["slippage_pct"],
        "avg_fill_price": buy_fill["avg_price"],
        "filled": buy_fill["filled"],
        "ask_depth_usdt": round(ask_depth_usdt, 4),
        "bid_depth_usdt": round(bid_depth_usdt, 4),
        "depth_multiple": round(depth_multiple, 4),
        "reasons": reasons,
        "settings": cfg,
    }


def evaluate_entry_gate(symbol: str, trade_notional_usdt: float, settings: dict[str, Any] | None = None, base_url: str = BINANCE_PUBLIC_BASE) -> dict[str, Any]:
    cfg = merged_settings(settings)
    if not cfg["enabled"]:
        return {"ok": True, "symbol": symbol, "trade_notional_usdt": round(trade_notional_usdt, 4), "reasons": [], "settings": cfg, "disabled": True}
    try:
        order_book = fetch_order_book(symbol, limit=cfg["limit"], base_url=base_url)
        return evaluate_entry_gate_from_book(symbol, order_book, trade_notional_usdt, cfg)
    except Exception as exc:
        if cfg["fail_closed"]:
            return {
                "ok": False,
                "symbol": symbol,
                "trade_notional_usdt": round(trade_notional_usdt, 4),
                "reasons": ["order_book_unavailable"],
                "error": str(exc),
                "settings": cfg,
            }
        return {
            "ok": True,
            "symbol": symbol,
            "trade_notional_usdt": round(trade_notional_usdt, 4),
            "reasons": [],
            "warning": str(exc),
            "settings": cfg,
        }


def compact_gate_reason(gate: dict[str, Any]) -> str:
    reasons = gate.get("reasons") or []
    metrics = []
    if gate.get("spread_pct") is not None:
        metrics.append(f"spread={_as_float(gate.get('spread_pct')):.3f}%")
    if gate.get("slippage_pct") is not None:
        metrics.append(f"slippage={_as_float(gate.get('slippage_pct')):.3f}%")
    if gate.get("depth_multiple") is not None:
        metrics.append(f"depth×={_as_float(gate.get('depth_multiple')):.2f}")
    prefix = ", ".join(reasons) if reasons else "ok"
    suffix = " | " + ", ".join(metrics) if metrics else ""
    return prefix + suffix
