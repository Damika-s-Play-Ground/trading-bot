#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Bot #3 — Grid Trading
Strategy: Sideways-only paper grid with regime hysteresis and fee-aware spacing.
Best for: ➡️ Sideways/ranging markets
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_bot.core.bot_runtime import get_blocked_coins, get_target_capital, new_buys_disabled
from trading_bot.core.order_book_gates import compact_gate_reason, evaluate_entry_gate
from trading_bot.core.state_store import load_json_path, save_json_path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT
PAPER_FILE = BASE_DIR / "paper_grid.json"
MANAGER_STATE_FILE = BASE_DIR / "manager_state.json"
PERFORMANCE_FILE = BASE_DIR / "performance_journal.json"

CONFIG = {
    "coins": ["BTC", "ETH", "SOL", "XRP", "ADA"],
    "grid_levels": 8,
    "grid_spacing_pct": 1.7,
    "buy_per_grid": 5.0,
    "max_positions": 8,
    "initial_balance": 300.0,
    "fee_rate": 0.001,
    "min_round_trip_edge_pct": 0.45,
    "allowed_regimes": ["sideways"],
    "regime_entry_streak": 3,
    "regime_exit_streak": 2,
    "reseed_drift_pct": 4.5,
    "order_book_enabled": True,
    "order_book_limit": 20,
    "order_book_depth_window_pct": 1.0,
    "max_spread_pct": 0.5,
    "order_book_max_slippage_pct": 0.25,
    "order_book_min_depth_multiple": 8.0,
    "order_book_fail_closed": True,
}

CONFIG["initial_balance"] = get_target_capital(CONFIG["initial_balance"])


def order_book_settings() -> dict[str, Any]:
    return {
        "enabled": CONFIG.get("order_book_enabled", True),
        "limit": CONFIG.get("order_book_limit", 20),
        "depth_window_pct": CONFIG.get("order_book_depth_window_pct", 1.0),
        "max_spread_pct": CONFIG.get("max_spread_pct", 0.5),
        "max_slippage_pct": CONFIG.get("order_book_max_slippage_pct", 0.25),
        "min_depth_multiple": CONFIG.get("order_book_min_depth_multiple", 8.0),
        "fail_closed": CONFIG.get("order_book_fail_closed", True),
    }


def _load_json(path: Path, default: Any) -> Any:
    return load_json_path(path, default)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def effective_spacing_pct() -> float:
    fee_floor = CONFIG["fee_rate"] * 2 * 100 + CONFIG["min_round_trip_edge_pct"]
    return max(float(CONFIG["grid_spacing_pct"]), float(fee_floor))


def load_regime_context() -> dict[str, Any]:
    manager_state = _load_json(MANAGER_STATE_FILE, {}) if MANAGER_STATE_FILE.exists() else {}
    journal = _load_json(PERFORMANCE_FILE, {"runs": []}) if PERFORMANCE_FILE.exists() else {"runs": []}
    allowed = {str(item).lower() for item in CONFIG["allowed_regimes"]}
    current = str(manager_state.get("regime") or "unknown").lower()
    runs = journal.get("runs", []) if isinstance(journal, dict) else []
    recent = [str(run.get("regime") or "unknown").lower() for run in runs[-12:] if isinstance(run, dict)]
    if current and (not recent or recent[-1] != current):
        recent.append(current)

    allowed_streak = 0
    blocked_streak = 0
    for regime in reversed(recent):
        if regime in allowed:
            allowed_streak += 1
        else:
            break
    for regime in reversed(recent):
        if regime not in allowed:
            blocked_streak += 1
        else:
            break

    return {
        "current": current,
        "recent": recent,
        "allowed": current in allowed,
        "allowed_streak": allowed_streak,
        "blocked_streak": blocked_streak,
    }


class PaperGrid:
    def __init__(self):
        self.initial = CONFIG["initial_balance"]
        self.usdt = self.initial
        self.positions: dict[str, list[dict[str, Any]]] = {}
        self.trade_log: list[dict[str, Any]] = []
        self.meta: dict[str, Any] = {"coins": {}}
        self.load()

    def load(self) -> None:
        data = load_json_path(PAPER_FILE, {})
        self.initial = data.get("initial", self.initial)
        self.usdt = data.get("usdt", self.initial)
        raw_positions = data.get("positions", {}) if isinstance(data.get("positions"), dict) else {}
        self.positions = {
            coin: [pos for pos in entries if isinstance(pos, dict)]
            for coin, entries in raw_positions.items()
            if coin in CONFIG["coins"] and isinstance(entries, list)
        }
        self.trade_log = [entry for entry in data.get("trade_log", []) if isinstance(entry, dict)]
        self.meta = data.get("meta", {"coins": {}}) if isinstance(data.get("meta"), dict) else {"coins": {}}
        self.meta.setdefault("coins", {})
        for coin in CONFIG["coins"]:
            self.positions.setdefault(coin, [])
            self._coin_state(coin)

    def save(self) -> None:
        save_json_path(PAPER_FILE, {
            "initial": self.initial,
            "usdt": self.usdt,
            "positions": self.positions,
            "trade_log": self.trade_log[-200:],
            "meta": self.meta,
            "updated": _now_iso(),
        })

    def _coin_state(self, coin: str) -> dict[str, Any]:
        coins = self.meta.setdefault("coins", {})
        state = coins.setdefault(
            coin,
            {
                "anchor_price": 0.0,
                "spacing_pct": effective_spacing_pct(),
                "armed": False,
                "last_regime": "unknown",
                "allowed_streak": 0,
                "blocked_streak": 0,
                "last_reseed_at": "",
            },
        )
        return state

    def open_positions(self, coin: str) -> list[dict[str, Any]]:
        return [pos for pos in self.positions.get(coin, []) if not pos.get("closed_at")]

    def mark_regime_gate(self, coin: str, price: float, regime: dict[str, Any], spacing_pct: float) -> dict[str, Any]:
        state = self._coin_state(coin)
        previously_armed = bool(state.get("armed"))
        if previously_armed:
            armed = int(regime.get("blocked_streak", 0)) < int(CONFIG["regime_exit_streak"])
        else:
            armed = bool(regime.get("allowed")) and int(regime.get("allowed_streak", 0)) >= int(CONFIG["regime_entry_streak"])
        state.update(
            {
                "armed": armed,
                "spacing_pct": spacing_pct,
                "last_regime": regime.get("current", "unknown"),
                "allowed_streak": int(regime.get("allowed_streak", 0)),
                "blocked_streak": int(regime.get("blocked_streak", 0)),
            }
        )
        if (not state.get("anchor_price")) or (armed and not previously_armed and not self.open_positions(coin)):
            state["anchor_price"] = price
            state["last_reseed_at"] = _now_iso()
        return state

    def maybe_reseed(self, coin: str, price: float) -> None:
        state = self._coin_state(coin)
        if self.open_positions(coin):
            return
        anchor = float(state.get("anchor_price") or 0.0)
        spacing_pct = float(state.get("spacing_pct") or effective_spacing_pct())
        if anchor <= 0:
            state["anchor_price"] = price
            state["last_reseed_at"] = _now_iso()
            return
        drift_pct = abs(price - anchor) / anchor * 100 if anchor else 0.0
        trigger_pct = max(float(CONFIG["reseed_drift_pct"]), spacing_pct * 2.0)
        if drift_pct >= trigger_pct:
            state["anchor_price"] = price
            state["last_reseed_at"] = _now_iso()

    def portfolio_value(self, prices: dict[str, float]) -> float:
        total = self.usdt
        for coin in CONFIG["coins"]:
            total += sum(pos["qty"] * prices.get(coin, 0.0) for pos in self.open_positions(coin))
        return total

    def check_grid(self, coin: str, price: float, regime: dict[str, Any], can_open_new_positions: bool = True) -> list[str]:
        trades_this_run: list[str] = []
        spacing_pct = effective_spacing_pct()
        state = self.mark_regime_gate(coin, price, regime, spacing_pct)
        self.maybe_reseed(coin, price)
        anchor = float(state.get("anchor_price") or price)
        spacing = spacing_pct / 100.0
        fee_rate = float(CONFIG["fee_rate"])

        active_positions = self.open_positions(coin)

        # Exit profitable filled levels first.
        remaining_positions: list[dict[str, Any]] = []
        for position in active_positions:
            target_price = float(position.get("target_price") or 0.0)
            if target_price and price >= target_price:
                proceeds = float(position["qty"]) * price
                fee = proceeds * fee_rate
                self.usdt += proceeds - fee
                cost_basis = float(position["qty"]) * float(position["avg_price"])
                pnl = proceeds - fee - cost_basis
                position["closed_at"] = _now_iso()
                position["exit_price"] = round(price, 8)
                position["pnl"] = round(pnl, 6)
                self.trade_log.append(
                    {
                        "time": position["closed_at"],
                        "action": "GRID_SELL",
                        "coin": coin,
                        "price": round(price, 8),
                        "qty": round(float(position["qty"]), 8),
                        "pnl": round(pnl, 4),
                        "usdt": round(proceeds - fee, 4),
                        "reason": f"grid take-profit on level {position.get('level')} at {spacing_pct:.2f}% spacing",
                    }
                )
                trades_this_run.append(f"SELL {coin} L{position.get('level')} @ ${price:.4f} (PnL: ${pnl:.2f})")
            else:
                remaining_positions.append(position)
        self.positions[coin] = remaining_positions
        active_positions = remaining_positions

        if not can_open_new_positions or not state.get("armed"):
            return trades_this_run

        filled_levels = {int(pos.get("level", 0)) for pos in active_positions}
        for level in range(1, int(CONFIG["grid_levels"]) + 1):
            if level in filled_levels:
                continue
            if len(active_positions) >= int(CONFIG["max_positions"]):
                break
            buy_price = round(anchor * (1 - spacing * level), 8)
            if price > buy_price or self.usdt < float(CONFIG["buy_per_grid"]):
                continue
            gate = evaluate_entry_gate(coin, float(CONFIG["buy_per_grid"]), settings=order_book_settings())
            if not gate.get("ok"):
                trades_this_run.append(f"SKIP {coin} L{level} ({compact_gate_reason(gate)})")
                continue
            gross_qty = float(CONFIG["buy_per_grid"]) / max(buy_price, 1e-9)
            qty = gross_qty * (1 - fee_rate)
            target_price = round(buy_price * (1 + spacing), 8)
            opened_at = _now_iso()
            self.usdt -= float(CONFIG["buy_per_grid"])
            position = {
                "level": level,
                "qty": qty,
                "avg_price": buy_price,
                "target_price": target_price,
                "opened_at": opened_at,
                "anchor_price": anchor,
            }
            active_positions.append(position)
            self.positions[coin] = active_positions
            self.trade_log.append(
                {
                    "time": opened_at,
                    "action": "GRID_BUY",
                    "coin": coin,
                    "price": buy_price,
                    "qty": round(qty, 8),
                    "usdt": round(float(CONFIG["buy_per_grid"]), 4),
                    "reason": f"grid level {level} armed after {regime.get('allowed_streak', 0)} sideways samples; spacing {spacing_pct:.2f}%",
                }
            )
            trades_this_run.append(f"BUY {coin} L{level} @ ${buy_price:.4f}")
            filled_levels.add(level)

        return trades_this_run


def run() -> None:
    print(f"➡️ Bot #3 — Grid Trading — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    paper = PaperGrid()
    target_capital = get_target_capital(paper.initial)
    blocked_coins = get_blocked_coins()
    manager_paused_buys = new_buys_disabled()
    regime = load_regime_context()
    spacing_pct = effective_spacing_pct()

    print(f"🎯 Target capital: ${target_capital:.2f}")
    print(
        f"🧭 Regime gate: {regime['current']} · sideways streak {regime['allowed_streak']} · "
        f"non-sideways streak {regime['blocked_streak']} · spacing floor {spacing_pct:.2f}%"
    )
    if blocked_coins:
        print(f"⛔ Blocked for new exposure: {', '.join(sorted(blocked_coins))}")
    if manager_paused_buys:
        print("🛑 Manager guard active: new buys disabled for this run")

    prices: dict[str, float] = {}
    try:
        req = urllib.request.Request("https://api.binance.com/api/v3/ticker/price")
        with urllib.request.urlopen(req, timeout=10) as resp:
            all_prices = json.loads(resp.read())
        pmap = {item["symbol"]: float(item["price"]) for item in all_prices}
        for coin in CONFIG["coins"]:
            price = pmap.get(f"{coin}USDT", 0.0)
            if price:
                prices[coin] = price
            print(f"  {coin:>5}: ${price:>8.2f}")
    except Exception as error:
        print(f"  Error: {error}")
        return

    print("\n🔍 Checking grid fills...")
    all_trades: list[str] = []
    armed_coins: list[str] = []
    for coin in CONFIG["coins"]:
        price = prices.get(coin, 0.0)
        if not price:
            continue
        state = paper._coin_state(coin)
        if state.get("armed"):
            armed_coins.append(coin)
        bot_total = paper.portfolio_value(prices)
        can_open_new_positions = (not manager_paused_buys) and coin not in blocked_coins and bot_total < target_capital
        trades = paper.check_grid(coin, price, regime, can_open_new_positions=can_open_new_positions)
        all_trades.extend(trades)
        latest_state = paper._coin_state(coin)
        if latest_state.get("armed") and coin not in armed_coins:
            armed_coins.append(coin)
        if not latest_state.get("armed") and not paper.open_positions(coin):
            print(f"  ⏸ {coin}: waiting for sideways hysteresis ({regime['allowed_streak']}/{CONFIG['regime_entry_streak']})")

    for trade in all_trades:
        print(f"  ⚡ {trade}")
    if not all_trades:
        print("  No fills this run.")

    total = paper.portfolio_value(prices)
    pnl = total - paper.initial
    pnl_pct = (pnl / paper.initial) * 100 if paper.initial else 0.0
    grid_positions = sum(len(paper.open_positions(coin)) for coin in CONFIG["coins"])

    print(f"\n{'=' * 55}")
    print("📋 Grid Bot Summary")
    print(f"  Balance:  ${paper.initial:.0f} → ${total:.2f} ({pnl_pct:+.2f}%)")
    print(f"  USDT:     ${paper.usdt:.2f}")
    print(f"  Grid pos: {grid_positions}")
    print(f"  Trades:   {len(paper.trade_log)}")
    print(f"  Armed:    {', '.join(sorted(set(armed_coins))) if armed_coins else 'none'}")
    print(f"{'=' * 55}")
    paper.save()


if __name__ == "__main__":
    run()
