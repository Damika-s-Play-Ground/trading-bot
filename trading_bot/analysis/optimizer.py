#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Deep Parameter Optimizer
Tests 1000s of combinations to find optimal bot settings.
"""
import json, urllib.request, time, math, itertools
from collections import defaultdict

COINS = ["BTC","ETH","SOL","BNB","XRP","LINK","ADA","AVAX","DOT","NEAR","ARB","OP","AAVE","IMX","ALGO","FIL","GRT","VET","HBAR","XLM","ATOM"]
WEIGHTS = {"NEAR":2.0,"BTC":2.0,"ALGO":1.5,"ATOM":1.5,"HBAR":1.5,"BNB":1.5,"LINK":1.5,"OP":0.5,"ADA":0.5,"ARB":0.5,"AAVE":0.5,"VET":0.5}

DAYS = 200
BUDGET = 1200.0
BUY_BASE = 5.0

def get_klines(symbol, limit=300):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}USDT&interval=1d&limit={limit}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return [{"close":float(c[4]),"high":float(c[2]),"low":float(c[3]),"quote_vol":float(c[7])} for c in data]

def calc_rsi(closes, p):
    if len(closes) < p+1: return 50
    g=l=0
    for i in range(-p,0):
        d=closes[i]-closes[i-1]
        if d>0: g+=d
        else: l-=d
    ag,al=g/p,l/p
    if al==0: return 100
    return 100-(100/(1+ag/al))

def run_backtest(klines, rsi_entry, tp1_pct, tp1_frac, tp2_pct, sl_pct, trail_act, trail_dist, vol_min, use_weights, budget):
    usdt = budget
    pos = None
    trades_pnl = []
    tier_hit = set()
    
    for i in range(60, len(klines)):
        k = klines[i]
        closes_l = [c["close"] for c in klines[:i+1]]
        close, high, low = k["close"], k["high"], k["low"]
        
        # Entry
        if pos is None:
            rsi = calc_rsi(closes_l, 14)
            vol = k["quote_vol"]
            if rsi < rsi_entry and vol >= vol_min and usdt > 3:
                cost = min(BUY_BASE, usdt)
                pos = {"qty": cost*0.999/close, "avg": close, "peak": close}
                usdt -= cost
                tier_hit = set()
        # Exit
        else:
            pnl = (close - pos["avg"]) / pos["avg"] * 100
            if close > pos["peak"]: pos["peak"] = close
            
            # SL
            if pnl <= sl_pct:
                usdt += pos["qty"] * close * 0.999
                trades_pnl.append(pnl)
                pos = None
                continue
            
            # Trailing
            if pnl >= trail_act:
                trail = pos["peak"] * (1 - trail_dist/100)
                if low <= trail:
                    exit_p = trail if close <= trail else close
                    p = (exit_p - pos["avg"]) / pos["avg"] * 100
                    usdt += pos["qty"] * exit_p * 0.999
                    trades_pnl.append(p)
                    pos = None
                    continue
            
            # TP tiers
            if "tp1" not in tier_hit and pnl >= tp1_pct:
                sell_qty = pos["qty"] * tp1_frac
                usdt += sell_qty * close * 0.999
                pos["qty"] -= sell_qty
                tier_hit.add("tp1")
            if "tp2" not in tier_hit and pnl >= tp2_pct:
                usdt += pos["qty"] * close * 0.999
                pos["qty"] = 0
                tier_hit.add("tp2")
                trades_pnl.append(tp2_pct)
                pos = None
    
    if pos:
        close = klines[-1]["close"]
        pnl = (close - pos["avg"])/pos["avg"]*100
        usdt += pos["qty"]*close*0.999
        trades_pnl.append(pnl)
    
    return trades_pnl

# Download all coin data
print("📥 Downloading data...")
data = {}
for coin in COINS:
    try:
        data[coin] = get_klines(coin, DAYS+100)
        print(f"  {coin}: {len(data[coin])} candles")
        time.sleep(0.1)
    except:
        print(f"  {coin}: FAILED")

# Test grid
rsi_values = [20, 25, 30, 35, 40]
tp1_values = [5, 8, 10, 12]
tp2_values = [10, 12, 15, 20]
sl_values = [-5, -8, -10, -12, -15]
trail_act_values = [3, 4, 5]
trail_dist_values = [1, 2, 3]
vol_values = [0, 1000, 10000]

total_combos = len(rsi_values)*len(tp1_values)*len(tp2_values)*len(sl_values)*len(trail_act_values)*len(trail_dist_values)*len(vol_values)
total_combos *= 2  # weights on/off

print(f"\n🧪 Testing {total_combos:,} parameter combinations across {len(COINS)} coins...")
print(f"   Estimated time: {total_combos * len(COINS) * 0.01:.0f}s\n")

results = []
count = 0

for rsi_entry, tp1, tp2, sl, ta, td, vm, use_w in itertools.product(
    rsi_values, tp1_values, tp2_values, sl_values, trail_act_values, trail_dist_values, vol_values, [False, True]):

    if tp2 <= tp1: continue  # tier 2 must be higher than tier 1
    count += 1

    total_trades = 0
    total_wins = 0
    all_pnls = []
    
    for coin in COINS:
        klines = data.get(coin, [])
        if not klines: continue
        
        budget = (BUDGET / len(COINS)) * WEIGHTS.get(coin, 1.0) if use_w else (BUDGET / len(COINS))
        pnls = run_backtest(klines, rsi_entry, tp1, 0.5, tp2, sl, ta, td, vm, use_w, budget)
        all_pnls.extend(pnls)
    
    if not all_pnls:
        continue
    
    num_wins = sum(1 for p in all_pnls if p > 0)
    total_pnl = sum(all_pnls)
    win_rate = num_wins / len(all_pnls) * 100 if all_pnls else 0
    avg_pnl = total_pnl / len(all_pnls) if all_pnls else 0
    
    # Sharpe-like metric
    if len(all_pnls) > 1:
        mean_pnl = sum(all_pnls)/len(all_pnls)
        variance = sum((p-mean_pnl)**2 for p in all_pnls)/len(all_pnls)
        sharpe = (mean_pnl / math.sqrt(variance)) if variance > 0 else 0
    else:
        sharpe = 0
    
    # Composite score: P&L + win rate bonus + sharpe bonus
    score = total_pnl * 0.5 + win_rate * 0.3 + sharpe * 50
    
    results.append({
        "rsi": rsi_entry, "tp1": tp1, "tp2": tp2, "sl": sl,
        "trail_act": ta, "trail_dist": td, "vol": vm, "weights": use_w,
        "trades": len(all_pnls), "wins": num_wins, 
        "win_rate": round(win_rate, 1),
        "pnl": round(total_pnl, 2),
        "avg_trade": round(avg_pnl, 2),
        "sharpe": round(sharpe, 3),
        "score": round(score, 1),
    })
    
    if count % 100 == 0:
        print(f"  {count}/{total_combos} tested ({count/total_combos*100:.0f}%)")

# Rank
results.sort(key=lambda r: -r["score"])

print(f"\n{'='*80}")
print(f"🏆 TOP 10 BEST PARAMETER SETS (by composite score)")
print(f"{'='*80}")
print(f"{'Rank':>4} | {'RSI':>3} | {'TP1':>3} | {'TP2':>3} | {'SL':>4} | {'TrAct':>5} | {'TrDst':>5} | {'Vol':>4} | {'Wt':>2} | {'Trades':>6} | {'Win%':>5} | {'P&L':>8} | {'Sharpe':>7} | {'Score':>6}")
print(f"{'─'*4}─┼{'─'*3}─┼{'─'*3}─┼{'─'*3}─┼{'─'*4}─┼{'─'*5}─┼{'─'*5}─┼{'─'*4}─┼{'─'*2}─┼{'─'*6}─┼{'─'*5}─┼{'─'*8}─┼{'─'*7}─┼{'─'*6}")

for i, r in enumerate(results[:15]):
    wt = "✓" if r["weights"] else "✗"
    print(f"{i+1:>4} | {r['rsi']:>3} | {r['tp1']:>3} | {r['tp2']:>3} | {r['sl']:>4} | {r['trail_act']:>5} | {r['trail_dist']:>5} | {r['vol']:>4} | {wt:>2} | {r['trades']:>6} | {r['win_rate']:>5.1f} | ${r['pnl']:>+7.2f} | {r['sharpe']:>7.3f} | {r['score']:>6.1f}")

# Best config
best = results[0]
print(f"\n{'='*80}")
print(f"✅ OPTIMAL CONFIGURATION")
print(f"{'='*80}")
print(f"  RSI Entry:      < {best['rsi']}")
print(f"  TP Tier 1:      +{best['tp1']}% (sell 50%)")
print(f"  TP Tier 2:      +{best['tp2']}% (sell rest)")
print(f"  Stop Loss:      {best['sl']}%")
print(f"  Trail Activate: +{best['trail_act']}%")
print(f"  Trail Distance: {best['trail_dist']}%")
print(f"  Min Volume:     ${best['vol']}")
print(f"  Coin Weights:   {'ON' if best['weights'] else 'OFF'}")
print(f"  Trades:         {best['trades']}")
print(f"  Win Rate:       {best['win_rate']}%")
print(f"  Total P&L:      ${best['pnl']}")
print(f"  Sharpe:         {best['sharpe']}")

# Compare: our current settings
current = [r for r in results if r["rsi"]==30 and r["tp1"]==8 and r["tp2"]==15 and r["sl"]==-10 and r["trail_act"]==4 and r["trail_dist"]==2 and r["vol"]==1000 and r["weights"]==True]
if current:
    c = current[0]
    print(f"\n{'='*80}")
    print(f"📊 COMPARISON: Current Settings vs Optimal")
    print(f"{'='*80}")
    print(f"  {'Metric':<20} | {'Current':>12} | {'Optimal':>12} | {'Delta':>10}")
    print(f"  {'─'*20}─┼{'─'*12}─┼{'─'*12}─┼{'─'*10}")
    delta_pnl = best["pnl"] - c["pnl"]
    delta_win = best["win_rate"] - c["win_rate"]
    print(f"  {'P&L':<20} | ${c['pnl']:>+9.2f} | ${best['pnl']:>+9.2f} | ${delta_pnl:>+8.2f}")
    print(f"  {'Win Rate':<20} | {c['win_rate']:>10.1f}% | {best['win_rate']:>10.1f}% | {delta_win:>+9.1f}%")
    print(f"  {'Trades':<20} | {c['trades']:>10} | {best['trades']:>10} | {best['trades']-c['trades']:>+9}")
    print(f"  {'Sharpe':<20} | {c['sharpe']:>10.3f} | {best['sharpe']:>10.3f} | {best['sharpe']-c['sharpe']:>+9.3f}")

# Save results
with open("/Users/damikaanupama/trading-bot/optimizer_results.json", "w") as f:
    json.dump({"best": best, "top_15": results[:15], "all_count": len(results)}, f, indent=2)

print(f"\n💾 Results saved to ~/trading-bot/optimizer_results.json")
print(f"✅ Optimizer complete! Tested {len(results)} valid combinations.")
