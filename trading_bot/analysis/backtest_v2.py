#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Backtest v2 — tests all the new features (tiered TP, coin weighting, F&G filter)
"""
import urllib.request, json, time, math
from collections import defaultdict

COINS = ["BTC","ETH","SOL","BNB","XRP","LINK","ADA","AVAX","DOT","NEAR","ARB","OP","AAVE","IMX","ALGO","FIL","GRT","VET","HBAR","XLM","ATOM"]
WEIGHTS = {"NEAR": 2.0, "BTC": 2.0, "ALGO": 1.5, "ATOM": 1.5, "HBAR": 1.5, "BNB": 1.5, "LINK": 1.5,
           "OP": 0.5, "ADA": 0.5, "ARB": 0.5, "AAVE": 0.5, "VET": 0.5}
DEFAULT_WEIGHT = 1.0

def get_klines(symbol, interval="1d", limit=365):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}USDT&interval={interval}&limit={limit}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return [{"close": float(c[4]), "high": float(c[2]), "low": float(c[3]), "quote_vol": float(c[7])} for c in data]

def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return 50
    gains = losses = 0
    for i in range(-period, 0):
        diff = closes[i] - closes[i-1]
        if diff > 0: gains += diff
        else: losses -= diff
    ag = gains/period; al = losses/period
    if al == 0: return 100
    return 100 - (100/(1+ag/al))

def calc_sma(closes, p):
    if len(closes) < p: return closes[-1]
    return sum(closes[-p:])/p

def get_fg():
    try:
        req = urllib.request.Request("https://api.alternative.me/fng/?limit=500", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        # Map timestamps to values
        fg_map = {}
        for d in data["data"]:
            fg_map[int(d["timestamp"])] = int(d["value"])
        return fg_map
    except:
        return {}

# Test 3 strategies
strategies = [
    ("Baseline (RSI30, no trend, 8% TP)", lambda rsi, price, sma, fg: rsi < 30, False, [(8, 1.0)], False),
    ("+ Tiered TP + Weighting", lambda rsi, price, sma, fg: rsi < 30, True, [(8, 0.5), (15, 0.5)], False),
    ("+ F&G filter", lambda rsi, price, sma, fg: rsi < 30 and (fg < 70 if fg else True), True, [(8, 0.5), (15, 0.5)], True),
]

fg_map = get_fg()
print(f"📊 Backtest v2 — New Features\n")

for name, entry_cond, use_weights, tp_tiers, use_fg in strategies:
    total_trades = 0
    total_wins = 0
    total_pnl = 0.0
    budget = 1200.0
    days_active = 0
    
    for coin in COINS:
        try:
            klines = get_klines(coin, "1d", 300)
        except:
            continue
        
        usdt = budget / len(COINS)
        pos = None
        coin_trades = 0
        coin_wins = 0
        coin_pnl = 0
        tier_hit = set()
        
        for i in range(60, len(klines)):
            k = klines[i]
            closes = [c["close"] for c in klines[:i+1]]
            close = k["close"]
            rsi = calc_rsi(closes)
            sma = calc_sma(closes, 50)
            
            # Get F&G for this day
            ts = int(k["time"]/1000) if "time" in k else 0
            fg_val = fg_map.get(ts, None)
            # Approximate by using nearest available
            if fg_val is None and ts:
                nearest = min(fg_map.keys(), key=lambda x: abs(x - ts))
                fg_val = fg_map.get(nearest, 50)
            
            # Exit
            if pos is not None:
                pnl = (close - pos["avg"]) / pos["avg"] * 100
                if close > pos["peak"]: pos["peak"] = close
                
                # Stop loss
                if pnl <= -10:
                    usdt += pos["qty"] * close * 0.999
                    if pnl > 0: coin_wins += 1
                    coin_pnl += pnl
                    coin_trades += 1
                    pos = None
                    tier_hit = set()
                    continue
                
                # TP tiers
                for tp_pct, tp_frac in tp_tiers:
                    tier_key = f"t{tp_pct}"
                    if tier_key not in tier_hit and pnl >= tp_pct:
                        sell_qty = pos["qty"] * tp_frac
                        usdt += sell_qty * close * 0.999
                        if tp_frac < 1.0:
                            pos["qty"] -= sell_qty
                            pos["peak"] = close
                        else:
                            pos = None
                        tier_hit.add(tier_key)
                        coin_trades += 1
                        coin_wins += 1
                        break
                        
                # Trailing
                if pos and pnl >= 4:
                    trail = pos["peak"] * 0.98
                    if close <= trail:
                        usdt += pos["qty"] * close * 0.999
                        coin_trades += 1
                        coin_pnl += (close - pos["avg"]) / pos["avg"] * 100
                        pos = None
                        tier_hit = set()
            
            # Entry
            if pos is None and usdt > 3:
                weight = WEIGHTS.get(coin, DEFAULT_WEIGHT) if use_weights else 1.0
                cost = min(5 * weight, usdt)
                if cost >= 3 and entry_cond(rsi, close, sma, fg_val):
                    pos = {"qty": cost * 0.999 / close, "avg": close, "peak": close}
                    usdt -= cost
                    days_active += 1
        
        if pos:
            close = klines[-1]["close"]
            pnl = (close - pos["avg"]) / pos["avg"] * 100
            usdt += pos["qty"] * close * 0.999
            coin_pnl += pnl
            if coin_trades == 0:
                coin_trades = 1
        
        total_trades += coin_trades
        total_wins += coin_wins
        total_pnl += coin_pnl
    
    print(f"{'─'*55}")
    print(f"📌 {name}")
    print(f"  Trades: {total_trades} | Wins: {total_wins} | Win%: {total_wins/max(total_trades,1)*100:.0f}% | P&L: ${total_pnl:+.2f}")

print(f"\n{'='*55}")
print(f"✅ Backtest v2 complete!")
