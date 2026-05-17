#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Adaptive Multi-Bot Manager
- One true manager-controlled paper portfolio ($1,200 target)
- One-time legacy state migration / normalization
- Regime-aware adaptive allocation
- Per-bot performance journaling
- Allocation drift reporting and auto-throttling
- Portfolio circuit breakers using equity drawdown + realized/unrealized stress
"""

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT
CAPITAL = 1200.0
MIGRATION_VERSION = 1
MAX_SINGLE_COIN_EXPOSURE_PCT = 22.0
MAX_PORTFOLIO_DRAWDOWN_PCT = 15.0
MAX_STRESS_LOSS_PCT = 12.0
BOT_COOLDOWN_HOURS = 6
BOT_DRIFT_THROTTLE_PCT = 15.0
REBALANCE_MIN_TRANSFER_USDT = 5.0
REBALANCE_MIN_USDT_BUFFER = 10.0
BOT_SEQUENCE = ["dca", "trend", "grid", "momentum", "deep_mr"]

MANAGER_STATE_FILE = BASE_DIR / "manager_state.json"
PORTFOLIO_STATE_FILE = BASE_DIR / "manager_portfolio.json"
PERFORMANCE_JOURNAL_FILE = BASE_DIR / "performance_journal.json"

BOT_LABELS = {
    "dca": "Bot #1 - DCA",
    "trend": "Bot #2 - Trend",
    "grid": "Bot #3 - Grid",
    "momentum": "Bot #4 - Momentum",
    "deep_mr": "Bot #5 - Deep MR",
}

BOT_SCRIPTS = {
    "dca": "bot.py",
    "trend": "bot_trend.py",
    "grid": "bot_grid.py",
    "momentum": "bot_momentum.py",
    "deep_mr": "bot_deep_mr.py",
}

PAPER_FILES = {
    "dca": "paper_state.json",
    "trend": "paper_trend.json",
    "grid": "paper_grid.json",
    "momentum": "paper_momentum.json",
    "deep_mr": "paper_deepmr.json",
}

BASE_ALLOCATIONS = {
    "bull": {
        "dca": {"pct": 15, "reason": "Fewer dips to buy"},
        "trend": {"pct": 35, "reason": "Best environment for trend"},
        "grid": {"pct": 10, "reason": "Not ideal in strong trend"},
        "momentum": {"pct": 25, "reason": "Breakouts work in bull"},
        "deep_mr": {"pct": 15, "reason": "Reserve for pullbacks"},
    },
    "bear": {
        "dca": {"pct": 40, "reason": "Buy the dip"},
        "trend": {"pct": 5, "reason": "Trend follow struggles"},
        "grid": {"pct": 15, "reason": "Range pockets only"},
        "momentum": {"pct": 10, "reason": "Fakeouts common"},
        "deep_mr": {"pct": 30, "reason": "Panic selling opportunities"},
    },
    "sideways": {
        "dca": {"pct": 25, "reason": "Catch mean reversion"},
        "trend": {"pct": 15, "reason": "Breakout attempts"},
        "grid": {"pct": 35, "reason": "Best regime for grid"},
        "momentum": {"pct": 15, "reason": "Some rotation moves"},
        "deep_mr": {"pct": 10, "reason": "Few extreme dislocations"},
    },
    "volatile": {
        "dca": {"pct": 20, "reason": "Big dips available"},
        "trend": {"pct": 10, "reason": "False breaks likely"},
        "grid": {"pct": 20, "reason": "Wide grids can work"},
        "momentum": {"pct": 15, "reason": "Fast rotations possible"},
        "deep_mr": {"pct": 35, "reason": "Best for sharp oversold snaps"},
    },
}


def load_json(path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def detect_regime():
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=60"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        closes = [float(c[4]) for c in data]
        vols = [float(c[5]) for c in data]
        price = closes[-1]
        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sma20
        avg_vol = sum(vols[-20:]) / 20
        curr_vol = vols[-1]
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1
        atr = max(closes[-14:]) - min(closes[-14:])
        vol_pct = atr / price * 100 if price > 0 else 0

        if vol_pct > 5:
            regime = "volatile"
        elif price > sma50 and price > sma20 and sma20 > sma50:
            regime = "bull"
        elif price < sma50 and price < sma20 and sma20 < sma50:
            regime = "bear"
        else:
            regime = "sideways"
        return regime, {"price": price, "sma50": sma50, "vol_ratio": vol_ratio, "vol_pct": vol_pct}
    except Exception:
        return "sideways", {}


def fetch_price_map():
    req = urllib.request.Request("https://api.binance.com/api/v3/ticker/price")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return {item["symbol"]: float(item["price"]) for item in data}


def load_all_states():
    return {key: load_json(BASE_DIR / filename, {}) for key, filename in PAPER_FILES.items()}


def parse_time(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def iter_spot_positions(state):
    positions = state.get("positions", {})
    if not isinstance(positions, dict):
        return
    for coin, pos in positions.items():
        if coin.endswith("_orders"):
            continue
        if isinstance(pos, dict) and "qty" in pos:
            yield coin, pos
        elif isinstance(pos, list):
            for item in pos:
                if isinstance(item, dict) and not item.get("sold"):
                    yield coin, item


def iter_grid_orders(state):
    positions = state.get("positions", {})
    if not isinstance(positions, dict):
        return
    for coin, pos in positions.items():
        if coin.endswith("_orders") and isinstance(pos, list):
            yield coin, pos


def position_value_and_coin_map(state, prices):
    total = 0.0
    coin_values = {}
    for coin, pos in iter_spot_positions(state):
        px = prices.get(f"{coin}USDT", 0.0)
        if px <= 0:
            continue
        value = float(pos.get("qty", 0.0)) * px
        total += value
        coin_values[coin] = coin_values.get(coin, 0.0) + value
    return total, coin_values


def unrealized_pnl_from_state(state, prices):
    total = 0.0
    for coin, pos in iter_spot_positions(state):
        px = prices.get(f"{coin}USDT", 0.0)
        if px <= 0:
            continue
        qty = float(pos.get("qty", 0.0))
        avg = float(pos.get("avg_price", 0.0))
        total += (px - avg) * qty
    return total


def total_value_from_state(state, prices):
    usdt = float(state.get("usdt", 0.0))
    pos_total, _ = position_value_and_coin_map(state, prices)
    return usdt + pos_total


def recent_sell_trades(state, limit=20):
    trades = state.get("trade_log", [])
    sells = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        action = str(trade.get("action", "")).upper()
        if "SELL" in action and "pnl" in trade:
            sells.append(trade)
    return sells[-limit:]


def consecutive_losses(sells):
    count = 0
    for trade in reversed(sells):
        pnl = float(trade.get("pnl", 0.0))
        if pnl < 0:
            count += 1
        else:
            break
    return count


def current_initial_for_state(state, total_value):
    initial = state.get("initial_balance", state.get("initial"))
    if initial is None:
        return max(total_value, 1.0)
    try:
        initial = float(initial)
    except Exception:
        initial = max(total_value, 1.0)
    return max(initial, 1.0)


def scale_numeric(value, factor):
    try:
        return float(value) * factor
    except Exception:
        return value


def scale_trade_log(trades, factor):
    scaled = []
    for trade in trades:
        if not isinstance(trade, dict):
            scaled.append(trade)
            continue
        item = dict(trade)
        for key in ["qty", "usdt", "pnl", "fee", "margin"]:
            if key in item:
                item[key] = round(scale_numeric(item[key], factor), 10)
        scaled.append(item)
    return scaled


def scale_state(state, factor, bot_key):
    scaled = json.loads(json.dumps(state))
    if "usdt" in scaled:
        scaled["usdt"] = round(scale_numeric(scaled.get("usdt", 0.0), factor), 10)
    if "daily_pnl" in scaled:
        scaled["daily_pnl"] = round(scale_numeric(scaled.get("daily_pnl", 0.0), factor), 10)
    if "peak_value" in scaled:
        scaled["peak_value"] = round(scale_numeric(scaled.get("peak_value", 0.0), factor), 10)
    if "initial_balance" in scaled:
        scaled["initial_balance"] = round(scale_numeric(scaled.get("initial_balance", 0.0), factor), 10)
    if "initial" in scaled:
        scaled["initial"] = round(scale_numeric(scaled.get("initial", 0.0), factor), 10)

    positions = scaled.get("positions", {})
    if isinstance(positions, dict):
        for coin, pos in positions.items():
            if coin.endswith("_orders") and isinstance(pos, list):
                for order in pos:
                    if not isinstance(order, dict):
                        continue
                    if "qty" in order:
                        order["qty"] = round(scale_numeric(order.get("qty", 0.0), factor), 12)
                    if "usdt" in order:
                        order["usdt"] = round(scale_numeric(order.get("usdt", 0.0), factor), 10)
                continue
            if isinstance(pos, dict) and "qty" in pos:
                pos["qty"] = round(scale_numeric(pos.get("qty", 0.0), factor), 12)
            elif isinstance(pos, list):
                for item in pos:
                    if isinstance(item, dict) and "qty" in item:
                        item["qty"] = round(scale_numeric(item.get("qty", 0.0), factor), 12)

    scaled["trade_log"] = scale_trade_log(scaled.get("trade_log", []), factor)
    scaled["updated"] = datetime.now(timezone.utc).isoformat()
    scaled["manager_migration_version"] = MIGRATION_VERSION
    scaled["manager_bot_key"] = bot_key
    return scaled


def ensure_state_initial_fields(states, prices):
    for bot_key, state in states.items():
        total = total_value_from_state(state, prices)
        initial = current_initial_for_state(state, total)
        if bot_key == "dca":
            state["initial_balance"] = round(initial, 10)
        else:
            state["initial"] = round(initial, 10)


def state_initial_key(bot_key):
    return "initial_balance" if bot_key == "dca" else "initial"


def apply_capital_delta(bot_key, state, delta, prices):
    if abs(delta) < 1e-9:
        return

    initial_key = state_initial_key(bot_key)
    current_total_before = total_value_from_state(state, prices)
    current_initial = current_initial_for_state(state, current_total_before)
    current_peak = float(state.get("peak_value", max(current_total_before, current_initial, 1.0)))

    state["usdt"] = round(max(0.0, float(state.get("usdt", 0.0)) + delta), 10)
    state[initial_key] = round(max(1.0, current_initial + delta), 10)

    current_total_after = total_value_from_state(state, prices)
    adjusted_peak = max(1.0, current_total_after, current_peak + delta)
    state["peak_value"] = round(adjusted_peak, 10)
    state["updated"] = datetime.now(timezone.utc).isoformat()

    last_run = state.get("last_run")
    if isinstance(last_run, dict):
        last_run["total_value"] = round(current_total_after, 2)
        initial_after = float(state.get(initial_key, current_total_after))
        if initial_after > 0:
            last_run["pnl_pct"] = round((current_total_after - initial_after) / initial_after * 100.0, 2)


def perform_cash_rebalance(states, prices, metrics):
    donors = []
    recipients = []

    for bot_key in BOT_SEQUENCE:
        state = states.get(bot_key, {})
        current_total = float(metrics[bot_key].get("current_total", 0.0))
        target_capital = float(metrics[bot_key].get("target_capital", 0.0))
        usdt = float(state.get("usdt", 0.0))

        excess = max(0.0, current_total - target_capital)
        shortfall = max(0.0, target_capital - current_total)
        movable_cash = max(0.0, min(excess, usdt - REBALANCE_MIN_USDT_BUFFER))

        if movable_cash >= REBALANCE_MIN_TRANSFER_USDT:
            donors.append({"bot_key": bot_key, "available": movable_cash})
        if shortfall >= REBALANCE_MIN_TRANSFER_USDT:
            recipients.append({"bot_key": bot_key, "remaining": shortfall})

    if not donors or not recipients:
        return None

    donors.sort(key=lambda item: item["available"], reverse=True)
    recipients.sort(key=lambda item: item["remaining"], reverse=True)

    transfers = []
    touched = set()
    for donor in donors:
        donor_key = donor["bot_key"]
        available = donor["available"]
        for recipient in recipients:
            recipient_key = recipient["bot_key"]
            if donor_key == recipient_key:
                continue
            needed = recipient["remaining"]
            if available < REBALANCE_MIN_TRANSFER_USDT or needed < REBALANCE_MIN_TRANSFER_USDT:
                continue

            amount = round(min(available, needed), 2)
            if amount < REBALANCE_MIN_TRANSFER_USDT:
                continue

            apply_capital_delta(donor_key, states[donor_key], -amount, prices)
            apply_capital_delta(recipient_key, states[recipient_key], amount, prices)
            available -= amount
            recipient["remaining"] -= amount
            touched.update({donor_key, recipient_key})
            transfers.append({"from": donor_key, "to": recipient_key, "amount": amount})

    if not transfers:
        return None

    for bot_key in touched:
        save_json(BASE_DIR / PAPER_FILES[bot_key], states[bot_key])

    totals_after = {bot_key: round(total_value_from_state(states.get(bot_key, {}), prices), 2) for bot_key in BOT_SEQUENCE}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_transferred": round(sum(item["amount"] for item in transfers), 2),
        "transfers": transfers,
        "totals_after": totals_after,
    }


def migrate_legacy_states_if_needed(states, prices):
    portfolio_state = load_json(PORTFOLIO_STATE_FILE, {})
    if portfolio_state.get("migration_version") == MIGRATION_VERSION:
        ensure_state_initial_fields(states, prices)
        return states, None

    pre_totals = {bot_key: total_value_from_state(state, prices) for bot_key, state in states.items()}
    spot_total = sum(pre_totals.values())
    if spot_total <= 0:
        portfolio_state.update({
            "migration_version": MIGRATION_VERSION,
            "migration": {"completed_at": datetime.now(timezone.utc).isoformat(), "scale_factor": 1.0, "from_total": 0.0, "target_total": CAPITAL},
            "total_capital": CAPITAL,
            "peak_total_value": CAPITAL,
        })
        save_json(PORTFOLIO_STATE_FILE, portfolio_state)
        ensure_state_initial_fields(states, prices)
        return states, {"spot_total_before": 0.0, "spot_total_after": 0.0, "scale_factor": 1.0, "per_bot_before": pre_totals, "per_bot_after": pre_totals}

    factor = CAPITAL / spot_total
    scaled_states = {}
    for bot_key, state in states.items():
        scaled = scale_state(state, factor, bot_key)
        scaled_states[bot_key] = scaled

    post_totals = {bot_key: total_value_from_state(state, prices) for bot_key, state in scaled_states.items()}
    ensure_state_initial_fields(scaled_states, prices)
    for bot_key, state in scaled_states.items():
        save_json(BASE_DIR / PAPER_FILES[bot_key], state)

    portfolio_state.update({
        "migration_version": MIGRATION_VERSION,
        "total_capital": CAPITAL,
        "peak_total_value": CAPITAL,
        "migration": {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "scale_factor": round(factor, 8),
            "from_total": round(spot_total, 2),
            "target_total": CAPITAL,
            "per_bot_before": {k: round(v, 2) for k, v in pre_totals.items()},
            "per_bot_after": {k: round(v, 2) for k, v in post_totals.items()},
        },
    })
    save_json(PORTFOLIO_STATE_FILE, portfolio_state)
    report = {
        "spot_total_before": round(spot_total, 2),
        "spot_total_after": round(sum(post_totals.values()), 2),
        "scale_factor": round(factor, 8),
        "per_bot_before": {k: round(v, 2) for k, v in pre_totals.items()},
        "per_bot_after": {k: round(v, 2) for k, v in post_totals.items()},
    }
    return scaled_states, report


def performance_multiplier(bot_key, state, prices):
    total_value = total_value_from_state(state, prices)
    initial = current_initial_for_state(state, total_value)
    sells = recent_sell_trades(state, limit=20)
    realized = sum(float(t.get("pnl", 0.0)) for t in sells)
    wins = sum(1 for t in sells if float(t.get("pnl", 0.0)) > 0)
    losses_abs = abs(sum(min(float(t.get("pnl", 0.0)), 0.0) for t in sells))
    gains = sum(max(float(t.get("pnl", 0.0)), 0.0) for t in sells)
    sell_count = len(sells)
    win_rate = wins / sell_count if sell_count else None
    profit_factor = gains / losses_abs if losses_abs > 0 else (2.0 if gains > 0 else 1.0)
    expectancy = realized / sell_count if sell_count else 0.0
    loss_streak = consecutive_losses(sells)
    total_return_pct = ((total_value - initial) / initial * 100.0) if initial > 0 else 0.0
    peak = float(state.get("peak_value", max(initial, total_value, 1.0)))
    drawdown_pct = ((peak - total_value) / peak * 100.0) if peak > 0 else 0.0
    unrealized = unrealized_pnl_from_state(state, prices)

    multiplier = 1.0
    if sell_count >= 5:
        if win_rate is not None:
            if win_rate >= 0.60:
                multiplier += 0.12
            elif win_rate <= 0.40:
                multiplier -= 0.12
        if profit_factor >= 1.50:
            multiplier += 0.13
        elif profit_factor <= 0.90:
            multiplier -= 0.13
        if expectancy > 0:
            multiplier += 0.10
        elif expectancy < 0:
            multiplier -= 0.10

    if total_return_pct >= 5:
        multiplier += 0.05
    elif total_return_pct <= -5:
        multiplier -= 0.05
    if loss_streak >= 3:
        multiplier -= 0.18
    if drawdown_pct >= 10:
        multiplier -= 0.10
    if unrealized < 0 and initial > 0 and abs(unrealized) / initial >= 0.08:
        multiplier -= 0.05

    multiplier = max(0.65, min(1.35, multiplier))
    return multiplier, {
        "sell_count": sell_count,
        "win_rate": round(win_rate * 100, 1) if win_rate is not None else None,
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "realized_pnl_recent": round(realized, 2),
        "loss_streak": loss_streak,
        "total_return_pct": round(total_return_pct, 2),
        "drawdown_pct": round(drawdown_pct, 2),
        "unrealized_pnl": round(unrealized, 2),
        "multiplier": round(multiplier, 3),
        "target_capital": 0.0,
        "current_total": round(total_value, 2),
        "initial_capital": round(initial, 2),
    }


def build_adaptive_allocation(regime, states, prices):
    base = BASE_ALLOCATIONS.get(regime, BASE_ALLOCATIONS["sideways"])
    raw = {}
    metrics = {}
    for bot_key in BOT_SEQUENCE:
        mult, perf = performance_multiplier(bot_key, states.get(bot_key, {}), prices)
        raw[bot_key] = base[bot_key]["pct"] * mult
        metrics[bot_key] = perf

    total_raw = sum(raw.values()) or 1.0
    allocation = {}
    for bot_key in BOT_SEQUENCE:
        pct = raw[bot_key] / total_raw * 100.0
        target_capital = CAPITAL * pct / 100.0
        current_total = metrics[bot_key]["current_total"]
        drift_abs = current_total - target_capital
        drift_pct = (drift_abs / target_capital * 100.0) if target_capital > 0 else 0.0
        allocation[bot_key] = {
            "pct": round(pct, 1),
            "base_pct": base[bot_key]["pct"],
            "reason": base[bot_key]["reason"],
            "multiplier": metrics[bot_key]["multiplier"],
        }
        metrics[bot_key]["target_capital"] = round(target_capital, 2)
        metrics[bot_key]["drift_abs"] = round(drift_abs, 2)
        metrics[bot_key]["drift_pct"] = round(drift_pct, 2)
        metrics[bot_key]["overweight"] = drift_pct >= BOT_DRIFT_THROTTLE_PCT
    return allocation, metrics


def portfolio_status(states, prices):
    totals = {}
    aggregate_coin_values = {}
    total_value = 0.0
    unrealized_total = 0.0
    realized_recent_total = 0.0

    for bot_key, state in states.items():
        bot_total = total_value_from_state(state, prices)
        totals[bot_key] = round(bot_total, 2)
        total_value += bot_total
        unrealized_total += unrealized_pnl_from_state(state, prices)
        realized_recent_total += sum(float(t.get("pnl", 0.0)) for t in recent_sell_trades(state, limit=20))
        _, coin_map = position_value_and_coin_map(state, prices)
        for coin, value in coin_map.items():
            aggregate_coin_values[coin] = aggregate_coin_values.get(coin, 0.0) + value

    exposure_pct = {}
    if total_value > 0:
        for coin, value in aggregate_coin_values.items():
            exposure_pct[coin] = round(value / total_value * 100.0, 2)

    combined_loss_amount = max(0.0, -min(realized_recent_total, 0.0)) + max(0.0, -min(unrealized_total, 0.0))
    combined_loss_pct = combined_loss_amount / CAPITAL * 100.0 if CAPITAL > 0 else 0.0
    return {
        "total_value": round(total_value, 2),
        "bot_totals": totals,
        "coin_values": aggregate_coin_values,
        "coin_exposure_pct": exposure_pct,
        "unrealized_pnl": round(unrealized_total, 2),
        "realized_pnl_recent": round(realized_recent_total, 2),
        "combined_loss_pct": round(combined_loss_pct, 2),
    }


def load_manager_state():
    return load_json(MANAGER_STATE_FILE, {})


def load_portfolio_state():
    return load_json(PORTFOLIO_STATE_FILE, {"total_capital": CAPITAL, "peak_total_value": CAPITAL})


def portfolio_drawdown(total_value):
    portfolio_state = load_portfolio_state()
    prev_peak = float(portfolio_state.get("peak_total_value", CAPITAL))
    peak = max(prev_peak, total_value, CAPITAL)
    drawdown = (peak - total_value) / peak * 100.0 if peak > 0 else 0.0
    return peak, round(drawdown, 2)


def blocked_coins_from_portfolio(portfolio):
    return sorted([coin for coin, pct in portfolio["coin_exposure_pct"].items() if pct >= MAX_SINGLE_COIN_EXPOSURE_PCT])


def bot_in_cooldown(state, metrics):
    if metrics.get("loss_streak", 0) < 3:
        return False, ""
    sells = recent_sell_trades(state, limit=5)
    if not sells:
        return False, ""
    last_time = parse_time(sells[-1].get("time"))
    if not last_time:
        return True, "loss streak"
    now = datetime.now(timezone.utc)
    if now - last_time <= timedelta(hours=BOT_COOLDOWN_HOURS):
        return True, f"{metrics['loss_streak']} consecutive losses"
    return False, ""


def bot_pause_reason(bot_key, metrics, portfolio, drawdown_pct):
    reasons = []
    bot_pause, pause_reason = bot_in_cooldown(load_all_states().get(bot_key, {}), metrics)
    if bot_pause:
        reasons.append(pause_reason)
    if metrics.get("overweight"):
        reasons.append(f"allocation drift +{metrics['drift_pct']:.1f}%")
    if drawdown_pct >= MAX_PORTFOLIO_DRAWDOWN_PCT:
        reasons.append(f"equity drawdown {drawdown_pct:.2f}%")
    if portfolio.get("combined_loss_pct", 0.0) >= MAX_STRESS_LOSS_PCT:
        reasons.append(f"stress loss {portfolio['combined_loss_pct']:.2f}%")
    return (len(reasons) > 0), "; ".join(reasons)


def run_child(bot_key, allocation, blocked_coins, disable_new_buys, pause_reason):
    script = BASE_DIR / BOT_SCRIPTS[bot_key]
    env = os.environ.copy()
    env["BOT_CAPITAL"] = str(round(CAPITAL * allocation[bot_key]["pct"] / 100.0, 2))
    env["BLOCKED_COINS"] = ",".join(blocked_coins)
    env["BOT_DISABLE_NEW_BUYS"] = "1" if disable_new_buys else "0"
    if pause_reason:
        env["BOT_PAUSE_REASON"] = pause_reason

    result = subprocess.run(
        [str(BASE_DIR / "venv" / "bin" / "python3.13"), str(script)],
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
    )
    lines = result.stdout.splitlines()
    summary = [
        line for line in lines
        if "Summary" in line
        or "Balance:" in line
        or "Positions:" in line
        or "P&L:" in line
        or "Total value:" in line
        or "Drawdown from peak:" in line
    ]
    return result.returncode, "\n".join(summary[-8:]) if summary else result.stdout[-1000:]


def append_performance_journal(regime, allocation, metrics, portfolio, migration_report, rebalance_report):
    journal = load_json(PERFORMANCE_JOURNAL_FILE, {"runs": []})
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regime": regime,
        "portfolio_total": portfolio["total_value"],
        "unrealized_pnl": portfolio["unrealized_pnl"],
        "realized_pnl_recent": portfolio["realized_pnl_recent"],
        "combined_loss_pct": portfolio["combined_loss_pct"],
        "migration": migration_report,
        "cash_rebalance": rebalance_report,
        "bots": {
            bot_key: {
                "target_capital": metrics[bot_key]["target_capital"],
                "current_total": metrics[bot_key]["current_total"],
                "drift_abs": metrics[bot_key]["drift_abs"],
                "drift_pct": metrics[bot_key]["drift_pct"],
                "win_rate": metrics[bot_key]["win_rate"],
                "profit_factor": metrics[bot_key]["profit_factor"],
                "expectancy": metrics[bot_key]["expectancy"],
                "drawdown_pct": metrics[bot_key]["drawdown_pct"],
                "allocation_pct": allocation[bot_key]["pct"],
            }
            for bot_key in BOT_SEQUENCE
        },
    }
    journal["runs"] = (journal.get("runs", []) + [entry])[-300:]
    save_json(PERFORMANCE_JOURNAL_FILE, journal)


def print_allocation_table(regime, allocation, metrics):
    print(f"\n💰 Adaptive Capital Allocation (${CAPITAL:.0f} total) — regime: {regime.upper()}")
    print(f"  {'Bot':<20} {'Base':>6} {'Adj':>6} {'Target':>9} {'Current':>9} {'Drift':>8}")
    print(f"  {'─'*20} {'─'*6} {'─'*6} {'─'*9} {'─'*9} {'─'*8}")
    for bot_key in BOT_SEQUENCE:
        perf = metrics[bot_key]
        drift = f"{perf['drift_pct']:+.1f}%"
        print(
            f"  {BOT_LABELS[bot_key]:<20} "
            f"{allocation[bot_key]['base_pct']:>5.1f}% "
            f"{allocation[bot_key]['pct']:>5.1f}% "
            f"${perf['target_capital']:>8.2f} "
            f"${perf['current_total']:>8.2f} "
            f"{drift:>8}"
        )


def print_migration_report(report):
    if not report:
        return
    print("\n🔄 Legacy paper-state rebalance")
    print(f"  Before: ${report['spot_total_before']:.2f}")
    print(f"  After:  ${report['spot_total_after']:.2f}")
    print(f"  Scale:  {report['scale_factor']:.6f}x")
    for bot_key in BOT_SEQUENCE:
        before = report['per_bot_before'].get(bot_key, 0.0)
        after = report['per_bot_after'].get(bot_key, 0.0)
        print(f"  {BOT_LABELS[bot_key]:<20} ${before:>8.2f} -> ${after:>8.2f}")


def print_rebalance_report(report):
    if not report:
        return
    print("\n🔁 Active cash rebalance")
    print(f"  Total transferred: ${report['total_transferred']:.2f}")
    for transfer in report.get("transfers", []):
        print(
            f"  {BOT_LABELS[transfer['from']]:<20} -> "
            f"{BOT_LABELS[transfer['to']]:<20} ${transfer['amount']:.2f}"
        )


def main():
    print("=" * 72)
    print(f"🧠 ADAPTIVE MULTI-BOT MANAGER — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    regime, regime_data = detect_regime()
    print(f"\n📊 Market Regime: {regime.upper()}")
    if regime_data:
        print(f"     BTC: ${regime_data.get('price', 0):.2f} | 50MA: ${regime_data.get('sma50', 0):.2f}")
        print(f"     Vol Ratio: {regime_data.get('vol_ratio', 0):.1f}x | Volatility: {regime_data.get('vol_pct', 0):.1f}%")

    prices = fetch_price_map()
    states = load_all_states()
    states, migration_report = migrate_legacy_states_if_needed(states, prices)
    if migration_report:
        print_migration_report(migration_report)

    prices = fetch_price_map()
    states = load_all_states()
    allocation, metrics = build_adaptive_allocation(regime, states, prices)

    rebalance_report = perform_cash_rebalance(states, prices, metrics)
    if rebalance_report:
        print_rebalance_report(rebalance_report)
        prices = fetch_price_map()
        states = load_all_states()
        allocation, metrics = build_adaptive_allocation(regime, states, prices)

    print_allocation_table(regime, allocation, metrics)

    initial_portfolio = portfolio_status(states, prices)
    peak_total, current_dd = portfolio_drawdown(initial_portfolio["total_value"])
    blocked = blocked_coins_from_portfolio(initial_portfolio)
    stress_pause = initial_portfolio["combined_loss_pct"] >= MAX_STRESS_LOSS_PCT
    drawdown_pause = current_dd >= MAX_PORTFOLIO_DRAWDOWN_PCT

    print("\n🛡 Portfolio Risk")
    print(f"  Total value:      ${initial_portfolio['total_value']:.2f}")
    print(f"  Peak value:       ${peak_total:.2f}")
    print(f"  Equity drawdown:  {current_dd:.2f}%")
    print(f"  Recent realized:  ${initial_portfolio['realized_pnl_recent']:.2f}")
    print(f"  Unrealized P&L:   ${initial_portfolio['unrealized_pnl']:.2f}")
    print(f"  Stress loss:      {initial_portfolio['combined_loss_pct']:.2f}%")
    print(f"  Coin cap:         {MAX_SINGLE_COIN_EXPOSURE_PCT:.1f}%")
    print(f"  Blocked coins:    {', '.join(blocked) if blocked else 'none'}")
    if drawdown_pause:
        print(f"  ⚠ Equity circuit breaker active above {MAX_PORTFOLIO_DRAWDOWN_PCT:.1f}% drawdown")
    if stress_pause:
        print(f"  ⚠ Stress circuit breaker active above {MAX_STRESS_LOSS_PCT:.1f}% combined loss")

    print("\n" + "=" * 72)
    print("🤖 Running spot bots...")
    print("=" * 72)

    for bot_key in BOT_SEQUENCE:
        states = load_all_states()
        prices = fetch_price_map()
        portfolio = portfolio_status(states, prices)
        blocked = blocked_coins_from_portfolio(portfolio)
        peak_total, current_dd = portfolio_drawdown(portfolio["total_value"])
        disable_new_buys, pause_reason = bot_pause_reason(bot_key, metrics[bot_key], portfolio, current_dd)

        print(f"\n📊 {BOT_LABELS[bot_key]}")
        print(f"  Target capital: ${metrics[bot_key]['target_capital']:.2f}")
        print(f"  Current total:  ${metrics[bot_key]['current_total']:.2f}")
        print(f"  Drift:          {metrics[bot_key]['drift_pct']:+.2f}%")
        if blocked:
            print(f"  Exposure blocks: {', '.join(blocked)}")
        if disable_new_buys:
            print(f"  ⚠ New buys paused: {pause_reason}")

        code, summary = run_child(bot_key, allocation, blocked, disable_new_buys, pause_reason)
        if code != 0:
            print(f"  ⚠ Bot exited with code {code}")
        if summary:
            print(summary)

    final_states = load_all_states()
    final_prices = fetch_price_map()
    final_portfolio = portfolio_status(final_states, final_prices)
    peak_total, final_dd = portfolio_drawdown(final_portfolio["total_value"])

    print("\n📏 Allocation Drift")
    for bot_key in BOT_SEQUENCE:
        current_total = total_value_from_state(final_states.get(bot_key, {}), final_prices)
        target = metrics[bot_key]["target_capital"]
        drift_abs = current_total - target
        drift_pct = (drift_abs / target * 100.0) if target > 0 else 0.0
        print(f"  {BOT_LABELS[bot_key]:<20} current=${current_total:>8.2f} target=${target:>8.2f} drift={drift_pct:+.2f}%")
        metrics[bot_key]["current_total"] = round(current_total, 2)
        metrics[bot_key]["drift_abs"] = round(drift_abs, 2)
        metrics[bot_key]["drift_pct"] = round(drift_pct, 2)
        metrics[bot_key]["overweight"] = drift_pct >= BOT_DRIFT_THROTTLE_PCT

    portfolio_state = load_portfolio_state()
    portfolio_state["total_capital"] = CAPITAL
    portfolio_state["peak_total_value"] = round(max(float(portfolio_state.get("peak_total_value", CAPITAL)), final_portfolio["total_value"], CAPITAL), 2)
    portfolio_state["updated"] = datetime.now(timezone.utc).isoformat()
    save_json(PORTFOLIO_STATE_FILE, portfolio_state)

    append_performance_journal(regime, allocation, metrics, final_portfolio, migration_report, rebalance_report)

    print("\n" + "=" * 72)
    print("📋 UNIFIED PORTFOLIO SUMMARY")
    print("=" * 72)
    for bot_key in BOT_SEQUENCE:
        print(f"  {BOT_LABELS[bot_key]:<20} ${metrics[bot_key]['current_total']:>8.2f}")
    print(f"  {'─'*31}")
    print(f"  {'TOTAL':<20} ${final_portfolio['total_value']:>8.2f}")
    print(f"  Drawdown from peak: {final_dd:.2f}%")

    manager_state = {
        "regime": regime,
        "allocation": {key: value["pct"] for key, value in allocation.items()},
        "allocation_base": {key: value["base_pct"] for key, value in allocation.items()},
        "performance": metrics,
        "blocked_coins": blocked_coins_from_portfolio(final_portfolio),
        "portfolio_total_value": round(final_portfolio["total_value"], 2),
        "peak_total_value": round(portfolio_state["peak_total_value"], 2),
        "portfolio_drawdown_pct": final_dd,
        "coin_exposure_pct": final_portfolio["coin_exposure_pct"],
        "allocation_drift": {key: metrics[key]["drift_pct"] for key in BOT_SEQUENCE},
        "portfolio_risk": {
            "recent_realized_pnl": final_portfolio["realized_pnl_recent"],
            "unrealized_pnl": final_portfolio["unrealized_pnl"],
            "combined_loss_pct": final_portfolio["combined_loss_pct"],
            "drawdown_breaker": final_dd >= MAX_PORTFOLIO_DRAWDOWN_PCT,
            "stress_breaker": final_portfolio["combined_loss_pct"] >= MAX_STRESS_LOSS_PCT,
        },
        "cash_rebalance": rebalance_report,
        "migration": load_portfolio_state().get("migration", {}),
        "performance_journal_file": str(PERFORMANCE_JOURNAL_FILE),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    save_json(MANAGER_STATE_FILE, manager_state)

    try:
        subprocess.run(
            [str(BASE_DIR / "venv" / "bin" / "python3.13"), str(BASE_DIR / "dashboard.py")],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        pass

    print("\n✅ Adaptive manager run complete!")


if __name__ == "__main__":
    main()
