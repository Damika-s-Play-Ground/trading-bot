#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Parameter sweep: test many strategy combinations to find the best one.
"""
import urllib.request, json, time
from datetime import datetime
from collections import defaultdict

COINS = ["BTC","ETH","SOL","BNB","XRP","LINK","ADA","AVAX","DOT","NEAR","ARB","OP","AAVE","ALGO","FIL","GRT","HBAR","XLM","ATOM"]
DAYS = 200

def get_klines(symbol, interval="1d", limit=250):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}USDT&interval={interval}&limit={limit}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return [{"close": float(c[4]), "high": float(c[2]), "low": float(c[3]), "quote_vol": float(c[7])} for c in data]

def calc_rsi(closes, period):
    if len(closes) < period + 1: return 50
    gains = losses = 0
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

def simulate(klines, budget, rsi_entry, tp, sl, ma_period, trend_filter=True):
    usdt = budget
    pos = None
    trades = []
    budget_per_coin = budget
    buy_size = min(5, budget_per_coin)
    
    for i in range(ma_period, len(klines)):
        k = klines[i]
        closes = [c["close"] for c in klines[:i+1]]
        close, high, low = k["close"], k["high"], k["low"]
        rsi = calc_rsi(closes, 14)
        sma = calc_sma(closes, ma_period)
        
        in_uptrend = close > sma
        oversold = rsi < rsi_entry
        
        # Exit check
        if pos is not None:
            pnl = (close - pos["avg"]) / pos["avg"] * 100
            if close > pos["peak"]: pos["peak"] = close
            
            # Trailing (if pnl > 4%, trail 2%)
            if pnl >= 4:
                trail = pos["peak"] * 0.98
                if low <= trail:
                    exit_p = trail if close <= trail else close
                    profit = (exit_p - pos["avg"]) / pos["avg"] * 100
                    usdt += pos["qty"] * exit_p * 0.999
                    trades.append(profit)
                    pos = None
                    continue
            
            if pnl <= sl:
                exit_p = pos["avg"] * (1 + sl/100)
                usdt += pos["qty"] * exit_p * 0.999
                trades.append(sl)
                pos = None
                continue
            
            if pnl >= tp:
                exit_p = pos["avg"] * (1 + tp/100)
                usdt += pos["qty"] * exit_p * 0.999
                trades.append(tp)
                pos = None
                continue
        
        # Buy check
        if pos is None and usdt > buy_size:
            buy_signal = oversold
            if trend_filter:
                buy_signal = buy_signal and in_uptrend
            
            if buy_signal:
                pos = {"qty": buy_size * 0.999 / close, "avg": close, "peak": close}
                usdt -= buy_size

    if pos is not None:
        close = klines[-1]["close"]
        pnl = (close - pos["avg"]) / pos["avg"] * 100
        usdt += pos["qty"] * close * 0.999
        trades.append(pnl)

    total_pnl = sum(trades)
    wins = len([t for t in trades if t > 0])
    return {
        "trades": len(trades),
        "wins": wins,
        "pnl": round(total_pnl, 2),
        "win_rate": round(wins/len(trades)*100, 1) if trades else 0,
        "avg_trade": round(total_pnl/len(trades), 2) if trades else 0,
    }

# === Test configurations ===
strategies = [
    # (name, rsi_entry, tp%, sl%, ma, trend_filter)
    ("RSI<30 + MA50 trend",   30,  8, -10, 50, True),   # Current
    ("RSI<30 no trend",       30,  8, -10, 50, False),   # Remove trend filter
    ("RSI<40 + MA50 trend",   40,  8, -10, 50, True),    # Looser RSI
    ("RSI<40 no trend",       40,  8, -10, 50, False),   # Looser RSI + no trend
    ("RSI<30 + MA20 trend",   30,  8, -10, 20, True),    # Shorter MA
    ("RSI<40 + MA20 trend",   40,  8, -10, 20, True),    # Looser both
    ("RSI<30 no trend TP5",   30,  5, -10, 50, False),   # Lower TP
    ("RSI<30 no trend TP12",  30, 12, -10, 50, False),   # Higher TP
    ("RSI<30 no trend SL5",   30,  8,  -5, 50, False),   # Tighter SL
    ("RSI<30 no trend SL15",  30,  8, -15, 50, False),   # Looser SL
    ("RSI<40 no trend TP5",   40,  5, -10, 50, False),   # Most trades
    ("Buy anything (DCA)",    99, 99, -99, 1, False),    # Pure DCA baseline
]

print(f"{'Strategy':<38} | {'Trades':>6} | {'Wins':>4} | {'Win%':>5} | {'P&L':>8} | {'Avg':>7}")
print("-" * 85)

results_by_strategy = {}
for name, rsi_entry, tp, sl, ma, trend in strategies:
    all_trades_count = 0
    all_wins = 0
    total_pnl = 0
    coins_with_trades = 0
    
    for coin in COINS:
        try:
            klines = get_klines(coin, "1d", DAYS + 100)
            budget = 1200 / len(COINS)
            r = simulate(klines, budget, rsi_entry, tp, sl, ma, trend)
            all_trades_count += r["trades"]
            all_wins += r["wins"]
            total_pnl += r["pnl"]
            if r["trades"] > 0:
                coins_with_trades += 1
        except:
            pass
    
    avg_per_coin = round(total_pnl / len(COINS), 2) if COINS else 0
    win_rate = round(all_wins / all_trades_count * 100, 1) if all_trades_count else 0
    
    print(f"{name:<38} | {all_trades_count:>6} | {all_wins:>4} | {win_rate:>5.1f}% | ${total_pnl:>+6.2f} | ${avg_per_coin:>+6.2f}")
    results_by_strategy[name] = {"trades": all_trades_count, "pnl": total_pnl, "win_rate": win_rate, "coins": coins_with_trades}

print()
print("✅ Parameter sweep complete!")
print()
print("📌 Best strategies by P&L:")
for name, r in sorted(results_by_strategy.items(), key=lambda x: -x[1]["pnl"])[:5]:
    print(f"  {r['pnl']:>+7.2f} — {name} ({r['trades']} trades, {r['win_rate']}% win rate)")
