#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Backtest: Smart DCA + Take-Profit Strategy
Tests the bot's logic against 6 months of historical OHLCV data.
"""

import urllib.request
import json
import time
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# === CONFIG (matches current bot) ===
COINS = ["BTC","ETH","SOL","BNB","XRP","LINK","ADA","AVAX","DOT","NEAR","ARB","OP","AAVE","IMX","ALGO","FIL","GRT","VET","HBAR","XLM","ATOM"]
INITIAL_BALANCE = 1200.0
MAX_POSITIONS = 8
BUY_PER_TRADE = 5.0
MAX_SPEND_PER_DAY = 40.0
RSI_PERIOD = 14
RSI_OVERSOLD = 30
TAKE_PROFIT_PCT = 8.0
STOP_LOSS_PCT = -10.0
TRAILING_ACTIVATION = 4.0
TRAILING_DISTANCE = 2.0
TREND_MA = 50
MIN_VOLUME = 100000
TRADING_DAYS = 180  # ~6 months

# === HELPERS ===
def get_klines(symbol, interval="1d", limit=200):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}USDT&interval={interval}&limit={limit}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return [{
        "time": int(c[0]),
        "open": float(c[1]),
        "high": float(c[2]),
        "low": float(c[3]),
        "close": float(c[4]),
        "volume": float(c[5]),
        "quote_vol": float(c[7]),
    } for c in data]

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    gains, losses = 0, 0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0: gains += diff
        else: losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0: return 100
    return 100 - (100 / (1 + avg_gain / avg_loss))

def calc_sma(closes, period):
    if len(closes) < period: return closes[-1]
    return sum(closes[-period:]) / period

# === BACKTEST ===
print(f"📊 Backtesting Smart DCA Strategy")
print(f"{'='*55}")
print(f"Period: {TRADING_DAYS} days")
print(f"Initial capital: ${INITIAL_BALANCE}")
print(f"RSI entry: < {RSI_OVERSOLD} | MA filter: {TREND_MA}")
print(f"Take profit: +{TAKE_PROFIT_PCT}% | Stop loss: {STOP_LOSS_PCT}%")
print(f"Trailing: activate at +{TRAILING_ACTIVATION}%, trail {TRAILING_DISTANCE}%")
print(f"Max positions: {MAX_POSITIONS} | ${BUY_PER_TRADE}/trade | ${MAX_SPEND_PER_DAY}/day")
print(f"{'='*55}")

# Store results
results = defaultdict(list)  # coin -> list of trade dicts

for coin in COINS:
    print(f"\n📥 Fetching {coin}...")
    try:
        klines = get_klines(coin, "1d", TRADING_DAYS + 100)
    except:
        print(f"  ⚠ Failed to fetch {coin}, skipping")
        continue

    # Simulate bot
    usdt = INITIAL_BALANCE / len(COINS)  # ~$50 per coin budget
    position = None  # {"qty": float, "avg_price": float, "peak": float}
    trades = []
    daily_spent = 0
    last_day = ""

    for i in range(TREND_MA, len(klines)):
        k = klines[i]
        closes = [c["close"] for c in klines[:i+1]]
        high = k["high"]
        low = k["low"]
        close = k["close"]
        vol = k["quote_vol"]
        day = datetime.fromtimestamp(k["time"]/1000).strftime("%Y-%m-%d")
        
        # Reset daily budget
        if day != last_day:
            daily_spent = 0
            last_day = day

        # Calculate indicators
        rsi = calc_rsi(closes, RSI_PERIOD)
        sma = calc_sma(closes, TREND_MA)
        in_uptrend = close > sma
        oversold = rsi < RSI_OVERSOLD
        has_volume = vol > MIN_VOLUME

        # === CHECK EXISTING POSITION ===
        if position is not None:
            pnl_pct = ((close - position["avg_price"]) / position["avg_price"]) * 100
            
            # Update peak for trailing
            if close > position["peak"]:
                position["peak"] = close

            # Check exits
            exited = False

            # Trailing stop
            if pnl_pct >= TRAILING_ACTIVATION:
                trail_price = position["peak"] * (1 - TRAILING_DISTANCE / 100)
                if low <= trail_price:
                    exit_price = trail_price
                    exit_reason = f"Trailing (-{TRAILING_DISTANCE}% from peak)"
                    # Find actual exit price within day's range
                    if close <= trail_price:
                        exit_price = close
                    else:
                        exit_price = trail_price
                    profit = (exit_price - position["avg_price"]) / position["avg_price"] * 100
                    pnl = (exit_price - position["avg_price"]) * position["qty"]
                    usdt += position["qty"] * exit_price * 0.999  # After 0.1% fee
                    trades.append({"coin": coin, "date": day, "type": "SELL", "reason": exit_reason, "pnl_pct": round(profit, 2), "pnl": round(pnl, 2), "days_held": i - position.get("entry_idx", i)})
                    position = None
                    exited = True

            # Stop loss
            if not exited and low <= position["avg_price"] * (1 + STOP_LOSS_PCT/100):
                exit_price = max(close, position["avg_price"] * (1 + STOP_LOSS_PCT/100))
                profit = (exit_price - position["avg_price"]) / position["avg_price"] * 100
                pnl = (exit_price - position["avg_price"]) * position["qty"]
                usdt += position["qty"] * exit_price * 0.999
                trades.append({"coin": coin, "date": day, "type": "SELL", "reason": f"SL {STOP_LOSS_PCT}%", "pnl_pct": round(profit, 2), "pnl": round(pnl, 2), "days_held": i - position.get("entry_idx", i)})
                position = None
                exited = True

            # Take profit
            if not exited and high >= position["avg_price"] * (1 + TAKE_PROFIT_PCT/100):
                exit_price = position["avg_price"] * (1 + TAKE_PROFIT_PCT/100)
                profit = TAKE_PROFIT_PCT
                pnl = (exit_price - position["avg_price"]) * position["qty"]
                usdt += position["qty"] * exit_price * 0.999
                trades.append({"coin": coin, "date": day, "type": "SELL", "reason": f"TP +{TAKE_PROFIT_PCT}%", "pnl_pct": round(profit, 2), "pnl": round(pnl, 2), "days_held": i - position.get("entry_idx", i)})
                position = None
                exited = True

        # === CHECK BUY SIGNAL ===
        if position is None and usdt > BUY_PER_TRADE and daily_spent < MAX_SPEND_PER_DAY:
            if oversold and in_uptrend and has_volume:
                cost = min(BUY_PER_TRADE, usdt, MAX_SPEND_PER_DAY - daily_spent)
                if cost >= 3:
                    qty = cost / close
                    position = {"qty": qty * 0.999, "avg_price": close, "peak": close, "entry_idx": i}
                    usdt -= cost
                    daily_spent += cost
                    trades.append({"coin": coin, "date": day, "type": "BUY", "reason": f"RSI={rsi:.0f}", "price": round(close, 4), "cost": round(cost, 2)})

    # Close any remaining position at last price
    if position is not None:
        close = klines[-1]["close"]
        pnl = (close - position["avg_price"]) * position["qty"]
        profit = (close - position["avg_price"]) / position["avg_price"] * 100
        usdt += position["qty"] * close * 0.999
        trades.append({"coin": coin, "date": "OPEN", "type": "SELL", "reason": "End of backtest", "pnl_pct": round(profit, 2), "pnl": round(pnl, 2)})
        position = None

    results[coin] = trades
    if trades:
        buys = [t for t in trades if t["type"] == "BUY"]
        sells = [t for t in trades if t["type"] == "SELL"]
        wins = [t for t in sells if t.get("pnl", 0) > 0]
        total_pnl = sum(t.get("pnl", 0) for t in sells)
        print(f"  {coin:>5}: {len(buys)} buys, {len(sells)} sells, {len(wins)} wins, P&L: ${total_pnl:+.2f}")
    else:
        print(f"  {coin:>5}: No trades")

# === GLOBAL SUMMARY ===
all_trades = []
for coin, trades in results.items():
    all_trades.extend(trades)

buys = [t for t in all_trades if t["type"] == "BUY"]
sells = [t for t in all_trades if t["type"] == "SELL"]
wins = [t for t in sells if t.get("pnl", 0) > 0]
losses = [t for t in sells if t.get("pnl", 0) <= 0]

total_pnl = sum(t.get("pnl", 0) for t in sells)
win_rate = (len(wins) / len(sells) * 100) if sells else 0
avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
avg_days = sum(t.get("days_held", 0) for t in sells if "days_held" in t) / len([t for t in sells if "days_held" in t]) if sells else 0

print(f"\n{'='*55}")
print(f"📋 BACKTEST RESULTS — {len(COINS)} coins over 6 months")
print(f"{'='*55}")
print(f"Total trades:      {len(all_trades)} ({len(buys)} buys, {len(sells)} sells)")
print(f"Win rate:          {win_rate:.1f}% ({len(wins)} wins / {len(sells)} total)")
print(f"Total P&L:         ${total_pnl:+.2f}")
print(f"Avg win:           ${avg_win:+.2f}")
print(f"Avg loss:          ${avg_loss:+.2f}")
print(f"Avg days held:     {avg_days:.1f} days")
print(f"Total initial cap: ${sum(INITIAL_BALANCE / len(COINS) for _ in COINS):.2f}")
print(f"Profit factor:     {abs(sum(t['pnl'] for t in wins) / sum(t['pnl'] for t in losses)) if losses else float('inf'):.2f}")
print(f"{'='*55}")

# Top/bottom performers
print(f"\n🏆 Top 5 coins by P&L:")
coin_pnl = {}
for coin, trades in results.items():
    sells_list = [t for t in trades if t["type"] == "SELL"]
    coin_pnl[coin] = sum(t.get("pnl", 0) for t in sells_list)
for coin, pnl in sorted(coin_pnl.items(), key=lambda x: -x[1])[:5]:
    print(f"  {coin:>5}: ${pnl:+.2f}")

print(f"\n❌ Bottom 5 coins by P&L:")
for coin, pnl in sorted(coin_pnl.items(), key=lambda x: x[1])[:5]:
    print(f"  {coin:>5}: ${pnl:+.2f}")

# Monthly breakdown
print(f"\n📅 Monthly P&L:")
monthly = defaultdict(float)
for t in sells:
    if "date" in t and t["date"] != "OPEN":
        month = t["date"][:7]
        monthly[month] += t.get("pnl", 0)
for month, pnl in sorted(monthly.items()):
    print(f"  {month}: ${pnl:+.2f}")

print(f"\n✅ Backtest complete!")
