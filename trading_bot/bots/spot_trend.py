#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Bot #2 — Trend Following
Strategy: Buy when price > 50MA AND MACD histogram > 0 (uptrend confirmed)
          Sell when price crosses BELOW 20MA (trend broken)
Best for: 📈 Strong uptrends
Win rate: ~45-50% (winners are big, losers are small)
"""

import json, urllib.request, time, math
from pathlib import Path
from datetime import datetime, timezone

from trading_bot.core.bot_runtime import (
    get_available_budget,
    get_blocked_coins,
    get_target_capital,
    new_buys_disabled,
    scale_trade_size,
)
from trading_bot.core.order_book_gates import compact_gate_reason, evaluate_entry_gate
from trading_bot.core.state_store import load_json_path, save_json_path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT
PAPER_FILE = BASE_DIR / "paper_trend.json"
CONFIG_FILE = BASE_DIR / "config_trend.json"

# Default config
CONFIG = {
    "coins": ["BTC","ETH","SOL","BNB","XRP","LINK","ADA","AVAX","DOT","NEAR"],
    "trend_ma": 50,          # Must be above this MA to be "in trend"
    "exit_ma": 20,           # Sell when price crosses below this
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "buy_per_trade": 10.0,   # Slightly bigger buys for trend
    "max_positions": 5,      # Fewer positions, bigger bets
    "take_profit_pct": 15.0, # Trend trades target bigger gains
    "stop_loss_pct": -8.0,   # Tighter SL (trend can reverse fast)
    "trailing_activation": 5.0,
    "trailing_distance": 3.0,
    "initial_balance": 600.0, # Half of total capital for this bot
    "min_volume": 50000,
}

# Load/save config
CONFIG.update(load_json_path(CONFIG_FILE, {}))

CONFIG["initial_balance"] = get_target_capital(CONFIG["initial_balance"])


def order_book_settings():
    return {
        "enabled": CONFIG.get("order_book_enabled", True),
        "limit": CONFIG.get("order_book_limit", 20),
        "depth_window_pct": CONFIG.get("order_book_depth_window_pct", 1.0),
        "max_spread_pct": CONFIG.get("max_spread_pct", 0.5),
        "max_slippage_pct": CONFIG.get("order_book_max_slippage_pct", 0.25),
        "min_depth_multiple": CONFIG.get("order_book_min_depth_multiple", 8.0),
        "fail_closed": CONFIG.get("order_book_fail_closed", True),
    }

# Helpers
def get_klines(symbol, interval="1h", limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}USDT&interval={interval}&limit={limit}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return [{"close": float(c[4]), "high": float(c[2]), "low": float(c[3]), "quote_vol": float(c[7])} for c in data]

def calc_ema(closes, period):
    if len(closes) < period: return closes[-1] if closes else 0
    mult = 2 / (period + 1)
    result = closes[0]
    for c in closes[1:]:
        result = (c - result) * mult + result
    return result

def calc_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal: return 0, 0, 0
    fe = se = closes[0]
    fast_emas, slow_emas = [], []
    fm, sm = 2/(fast+1), 2/(slow+1)
    for c in closes:
        fe = (c-fe)*fm + fe; se = (c-se)*sm + se
        fast_emas.append(fe); slow_emas.append(se)
    macd_line = [f-s for f,s in zip(fast_emas, slow_emas)]
    sg_mult = 2/(signal+1)
    sg = macd_line[0]
    for m in macd_line: sg = (m-sg)*sg_mult + sg
    return macd_line[-1], sg, macd_line[-1] - sg

def calc_sma(closes, period):
    if len(closes) < period: return closes[-1] if closes else 0
    return sum(closes[-period:]) / period

# Paper trading state
class PaperTrading:
    def __init__(self):
        self.initial = CONFIG["initial_balance"]
        self.usdt = self.initial
        self.positions = {}
        self.trade_log = []
        self.peak_value = self.initial
        self.load()
    
    def load(self):
        d = load_json_path(PAPER_FILE, {})
        self.initial = d.get("initial", self.initial)
        self.usdt = d.get("usdt", self.initial)
        self.positions = d.get("positions", {})
        self.trade_log = d.get("trade_log", [])
        self.peak_value = d.get("peak_value", self.initial)
    
    def save(self):
        save_json_path(PAPER_FILE, {
            "initial": self.initial,
            "usdt": self.usdt, "positions": self.positions,
            "trade_log": self.trade_log[-100:],
            "peak_value": self.peak_value,
            "updated": datetime.now(timezone.utc).isoformat(),
        })
    
    def total_value(self, prices):
        val = self.usdt
        for coin, pos in self.positions.items():
            val += pos["qty"] * prices.get(coin, 0)
        return val
    
    def buy(self, coin, price, usdt_amount):
        if self.usdt < usdt_amount: usdt_amount = self.usdt
        if usdt_amount < 5: return False
        qty = usdt_amount / price
        fee = qty * 0.001
        net_qty = qty - fee
        self.usdt -= usdt_amount
        if coin in self.positions:
            pos = self.positions[coin]
            total_cost = pos["qty"] * pos["avg_price"] + net_qty * price
            pos["qty"] += net_qty
            pos["avg_price"] = total_cost / pos["qty"]
            if price > pos["peak_price"]: pos["peak_price"] = price
        else:
            self.positions[coin] = {"qty": net_qty, "avg_price": price, "peak_price": price}
        self.trade_log.append({"time": datetime.now(timezone.utc).isoformat(), "action": "BUY",
            "coin": coin, "price": round(price, 4), "qty": round(net_qty, 6), "usdt": round(usdt_amount, 2), "fee": round(fee*price, 4)})
        self.save()
        return True
    
    def sell(self, coin, price, reason="TP", fraction=1.0):
        if coin not in self.positions: return False
        pos = self.positions[coin]
        sell_qty = pos["qty"] * fraction
        proceeds = sell_qty * price
        fee = proceeds * 0.001
        pnl = proceeds - fee - (sell_qty * pos["avg_price"])
        self.usdt += proceeds - fee
        self.trade_log.append({"time": datetime.now(timezone.utc).isoformat(), "action": "SELL",
            "coin": coin, "price": round(price, 4), "qty": round(sell_qty, 6), "usdt": round(proceeds-fee, 2), "pnl": round(pnl, 2), "reason": reason})
        if fraction >= 1.0:
            del self.positions[coin]
        else:
            pos["qty"] -= sell_qty
            pos["peak_price"] = price
        self.save()
        return True

    def check_exits(self, prices):
        sold = []
        for coin in list(self.positions.keys()):
            pos = self.positions[coin]
            price = prices.get(coin, 0)
            if price == 0: continue
            pnl = (price - pos["avg_price"]) / pos["avg_price"] * 100
            if price > pos["peak_price"]: pos["peak_price"] = price
            
            # Trend following exit: if trend breaks, sell
            try:
                klines = get_klines(coin, "1h", 60)
                closes = [k["close"] for k in klines]
                sma20 = calc_sma(closes, 20)
                if price < sma20:  # Crossed below 20MA = trend broken
                    self.sell(coin, price, "Trend broken (below 20MA)")
                    sold.append(coin)
                    continue
            except: pass
            
            # SL
            if pnl <= CONFIG["stop_loss_pct"]:
                self.sell(coin, price, f"SL {CONFIG['stop_loss_pct']}%")
                sold.append(coin); continue
            
            # TP
            if pnl >= CONFIG["take_profit_pct"]:
                self.sell(coin, price, f"TP +{CONFIG['take_profit_pct']}%")
                sold.append(coin); continue
            
            # Trailing
            if pnl >= CONFIG["trailing_activation"]:
                trail = pos["peak_price"] * (1 - CONFIG["trailing_distance"]/100)
                if price <= trail:
                    self.sell(coin, price, f"Trail {CONFIG['trailing_distance']}%")
                    sold.append(coin)
        return sold

# Main
def run():
    print(f"📈 Bot #2 — Trend Following — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*55)
    
    paper = PaperTrading()
    target_capital = get_target_capital(paper.initial)
    blocked_coins = get_blocked_coins()
    manager_paused_buys = new_buys_disabled()
    print(f"🎯 Target capital: ${target_capital:.2f}")
    if blocked_coins:
        print(f"⛔ Blocked for new exposure: {', '.join(sorted(blocked_coins))}")
    if manager_paused_buys:
        print("🛑 Manager guard active: new buys disabled for this run")
    prices = {}
    signals = []
    
    for coin in CONFIG["coins"]:
        try:
            klines = get_klines(coin, "1h", 100)
            if not klines: continue
            k = klines[-1]
            closes = [c["close"] for c in klines]
            price = k["close"]
            prices[coin] = price
            
            sma50 = calc_sma(closes, CONFIG["trend_ma"])
            sma20 = calc_sma(closes, CONFIG["exit_ma"])
            macd_l, macd_s, macd_h = calc_macd(closes, CONFIG["macd_fast"], CONFIG["macd_slow"], CONFIG["macd_signal"])
            vol = k["quote_vol"]
            
            in_uptrend = price > sma50
            macd_bullish = macd_h > 0
            above_20ma = price > sma20
            has_volume = vol > CONFIG["min_volume"]
            holding = coin in paper.positions
            
            pct_from_50ma = ((price - sma50) / sma50) * 100 if sma50 > 0 else 0
            
            print(f"  {coin:>5}: ${price:>8.2f} | 50MA=${sma50:>8.2f} ({pct_from_50ma:+.1f}%) | MACD={'🟢' if macd_bullish else '🔴'} | Vol=${vol:>10,.0f}")
            
            # Entry conditions
            if not holding and coin not in blocked_coins and in_uptrend and macd_bullish and above_20ma and has_volume:
                score = pct_from_50ma * 2 + (20 if macd_bullish else 0)
                signals.append({"coin": coin, "price": price, "score": round(score, 1)})
                print(f"    → 📈 TREND signal! Score={score:.0f}")
        except Exception as e:
            continue
    
    # Check exits
    print(f"\n🔍 Checking positions...")
    sold = paper.check_exits(prices)
    if sold: print(f"  💰 Sold: {', '.join(sold)}")
    
    if paper.positions:
        for coin, pos in paper.positions.items():
            p = prices.get(coin, 0)
            pnl = ((p - pos["avg_price"]) / pos["avg_price"]) * 100 if p > 0 else 0
            print(f"  {coin:>5}: {pos['qty']:>6.4f} @ ${pos['avg_price']:>8.2f} → ${p:>8.2f} ({pnl:+.2f}%)")
    
    # Execute buys
    signals.sort(key=lambda x: -x["score"])
    max_new = min(len(signals), CONFIG["max_positions"] - len(paper.positions))
    remaining = get_available_budget(paper.total_value(prices), target_capital, target_capital)
    executed_buys = []
    
    if manager_paused_buys:
        print(f"\n🛒 Manager risk guard — buys skipped.")
    elif signals and max_new > 0 and remaining > 5:
        print(f"\n🛒 Trend signals (top {max_new}):")
        for sig in signals[:max_new]:
            scaled_trade = scale_trade_size(CONFIG["buy_per_trade"], target_capital, paper.initial)
            cost = min(scaled_trade, remaining / max_new)
            if cost < 5: break
            gate = evaluate_entry_gate(sig["coin"], cost, settings=order_book_settings())
            if not gate.get("ok"):
                print(f"  SKIP {sig['coin']}: order-book gate blocked entry ({compact_gate_reason(gate)})")
                continue
            print(f"  BUY {sig['coin']}: ${cost:.2f} @ ${sig['price']:.4f}")
            if paper.buy(sig["coin"], sig["price"], cost):
                executed_buys.append(sig["coin"])
                remaining -= cost
    else:
        print(f"\n📭 No trend signals. Market may not be in uptrend.")
    
    # Summary
    total = paper.total_value(prices)
    pnl = total - paper.initial
    pnl_pct = (pnl / paper.initial) * 100
    print(f"\n{'='*55}")
    print(f"📋 Trend Bot Summary")
    print(f"  Balance:    ${paper.initial:.0f} → ${total:.2f} ({pnl_pct:+.2f}%)")
    print(f"  Positions:  {len(paper.positions)}")
    print(f"  Trades:     {len([t for t in paper.trade_log if t['action']=='BUY'])} buys")
    print(f"{'='*55}")
    paper.save()

if __name__ == "__main__":
    run()
