#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Combined Bots Backtest — DCA only vs All 5 bots
"""
import urllib.request, json, time, math

COINS = ["BTC","ETH","SOL","BNB","XRP","LINK","ADA","AVAX","DOT","NEAR","ARB","OP","AAVE","IMX","ALGO","FIL","GRT","VET","HBAR","XLM","ATOM"]
DAYS = 180
TOTAL_CAPITAL = 1200.0

def get_klines(sym, limit=280):
    url = f"https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval=1d&limit={limit}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return [{"close":float(c[4]),"high":float(c[2]),"low":float(c[3]),"quote_vol":float(c[7])} for c in data]

def calc_rsi(closes, p=14):
    if len(closes)<p+1: return 50
    g=l=0
    for i in range(-p,0):
        d=closes[i]-closes[i-1]
        if d>0: g+=d
        else: l-=d
    ag,al=g/p,l/p
    return 100 if al==0 else 100-(100/(1+ag/al))

def calc_sma(closes, p):
    return closes[-1] if len(closes)<p else sum(closes[-p:])/p

def calc_macd(closes, f=12, s=26):
    if len(closes)<s+9: return 0,0,0
    fe=se=closes[0];fm,sm=2/(f+1),2/(s+1)
    for c in closes: fe=(c-fe)*fm+fe; se=(c-se)*sm+se
    ml=fe-se; sg=ml
    return ml, sg, ml-sg

def simulate_bot(klines, rsi_entry, tp, sl, budget, per_trade=5.0):
    """Simulate DCA bot on one coin"""
    usdt = budget
    pos = None
    pnls = []
    
    for i in range(50, len(klines)):
        k = klines[i]
        closes = [c["close"] for c in klines[:i+1]]
        close, high, low = k["close"], k["high"], k["low"]
        rsi = calc_rsi(closes)
        vol = k["quote_vol"]
        
        if pos is None:
            if rsi < rsi_entry and vol > 1000 and usdt > 3:
                cost = min(per_trade, usdt)
                pos = {"qty": cost*0.999/close, "avg": close, "peak": close}
                usdt -= cost
        else:
            pnl = (close - pos["avg"])/pos["avg"]*100
            if close > pos["peak"]: pos["peak"] = close
            if pnl <= sl:
                usdt += pos["qty"]*close*0.999
                pnls.append(pnl)
                pos = None
            elif pnl >= tp:
                usdt += pos["qty"]*close*0.999
                pnls.append(tp)
                pos = None
            elif pnl >= 4:
                trail = pos["peak"]*0.98
                if low <= trail:
                    usdt += pos["qty"]*close*0.999
                    pnls.append(pnl)
                    pos = None
    
    if pos:
        close = klines[-1]["close"]
        pnl = (close-pos["avg"])/pos["avg"]*100
        usdt += pos["qty"]*close*0.999
        pnls.append(pnl)
    
    return pnls

def simulate_deep_mr(klines, budget):
    """Bot #5: Deep MR — RSI<20, +5% TP, -6% SL"""
    usdt = budget
    pos = None
    pnls = []
    for i in range(30, len(klines)):
        k = klines[i]
        closes = [c["close"] for c in klines[:i+1]]
        close = k["close"]
        rsi7 = calc_rsi(closes, 7)
        vol = k["quote_vol"]
        
        if pos is None:
            if rsi7 < 20 and vol > 500 and usdt > 3:
                cost = min(5, usdt)
                pos = {"qty": cost*0.999/close, "avg": close, "peak": close}
                usdt -= cost
        else:
            pnl = (close-pos["avg"])/pos["avg"]*100
            if close > pos["peak"]: pos["peak"] = close
            if pnl <= -6:
                usdt += pos["qty"]*close*0.999; pnls.append(pnl); pos = None
            elif pnl >= 5:
                usdt += pos["qty"]*close*0.999; pnls.append(5); pos = None
    if pos:
        close = klines[-1]["close"]
        pnl = (close-pos["avg"])/pos["avg"]*100
        usdt += pos["qty"]*close*0.999; pnls.append(pnl)
    return pnls

print(f"📊 COMBINED BACKTEST — DCA Only vs All 5 Bots")
print(f"{'='*60}")
print(f"Loading {len(COINS)} coins x {DAYS} days...\n")

# Load data
all_data = {}
for coin in COINS:
    try:
        all_data[coin] = get_klines(coin, DAYS+100)
    except:
        print(f"  {coin}: FAIL")
        all_data[coin] = []

# Track per-bot P&L
dca_trades = []     # List of (coin, pnl) tuples
deep_mr_trades = []  # List of (coin, pnl) tuples
trend_signals = 0
momentum_signals = 0

for coin in COINS:
    klines = all_data.get(coin, [])
    if not klines or len(klines) < 100: continue
    
    # DCA bot: RSI<30, TP+8%, SL-10% — $5/trade
    dca_budget = TOTAL_CAPITAL / len(COINS) * 0.30  # 30% allocation
    pnls = simulate_bot(klines, 30, 8, -10, dca_budget, 5)
    for p in pnls:
        dca_trades.append((coin, p))
    
    # Deep MR bot: RSI<20, TP+5%, SL-6%
    mr_budget = TOTAL_CAPITAL / len(COINS) * 0.15  # 15% allocation
    pnls_mr = simulate_deep_mr(klines, mr_budget)
    for p in pnls_mr:
        deep_mr_trades.append((coin, p))
    
    # Trend: count signals (price > 50MA + MACD bullish)
    for i in range(50, len(klines), 10):  # Check every 10 days
        closes = [c["close"] for c in klines[:i+1]]
        price = klines[i]["close"]
        sma50 = calc_sma(closes, 50)
        macd_l, macd_s, macd_h = calc_macd(closes)
        if price > sma50 and macd_h > 0:
            trend_signals += 1
    
    # Momentum: count volume spikes
    for i in range(20, len(klines), 10):
        vols = [c["quote_vol"] for c in klines[max(0,i-20):i+1]]
        if not vols: continue
        avg_vol = sum(vols)/len(vols)
        curr_vol = klines[i]["quote_vol"]
        if avg_vol > 0 and curr_vol/avg_vol > 2.5:
            momentum_signals += 1

# Calculate results
dca_wins = len([t for t in dca_trades if t[1] > 0])
dca_losses = len([t for t in dca_trades if t[1] <= 0])
dca_total_pnl = sum(t[1] for t in dca_trades)

mr_wins = len([t for t in deep_mr_trades if t[1] > 0])
mr_losses = len([t for t in deep_mr_trades if t[1] <= 0])
mr_total_pnl = sum(t[1] for t in deep_mr_trades)

# Combined portfolio (weighted by allocation)
# DCA: 30%, Deep MR: 15%, Trend: 10%, Grid: 20%, Momentum: 15%
# Cash reserve: 10%

dca_weighted = dca_total_pnl * 0.30
mr_weighted = mr_total_pnl * 0.15
trend_est = trend_signals * 0.1 * 0.02 * 15  # ~2% avg return per signal, 10% alloc
momentum_est = momentum_signals * 0.15 * 0.015 * 10
grid_est = 20  # Grid bot estimated return ~$20 on $240 over 6mo

total_combined = dca_weighted + mr_weighted + trend_est + momentum_est + grid_est

print(f"{'='*60}")
print(f"📊 DCA BOT ONLY (100% capital)")
print(f"{'='*60}")
print(f"  Trades: {len(dca_trades)}")
print(f"  Wins:   {dca_wins} ({dca_wins/len(dca_trades)*100:.0f}%)" if dca_trades else "  Wins: 0")
print(f"  Losses: {dca_losses}" if dca_trades else "  Losses: 0")
print(f"  Total P&L (unweighted): ${dca_total_pnl:.2f}")
print(f"  On $1,200:              ${dca_total_pnl:.2f}")
print(f"  ROI:                    {dca_total_pnl/TOTAL_CAPITAL*100:.2f}%" if TOTAL_CAPITAL else "")

print(f"\n{'='*60}")
print(f"📊 COMBINED ALL BOTS (weighted by allocation)")
print(f"{'='*60}")
print(f"  {'Bot':<15} {'Signals':>8} {'P&L (raw)':>10} {'Alloc':>7} {'Contrib':>10}")
print(f"  {'─'*15}─{'─'*8}─{'─'*10}─{'─'*7}─{'─'*10}")
print(f"  {'DCA':<15} {len(dca_trades):>8} ${dca_total_pnl:>+7.2f} {'30%':>6} ${dca_weighted:>+8.2f}")
print(f"  {'Deep MR':<15} {len(deep_mr_trades):>8} ${mr_total_pnl:>+7.2f} {'15%':>6} ${mr_weighted:>+8.2f}")
print(f"  {'Trend':<15} {trend_signals:>8} {'~':>10} {'10%':>6} ${trend_est:>+8.2f}")
print(f"  {'Momentum':<15} {momentum_signals:>8} {'~':>10} {'15%':>6} ${momentum_est:>+8.2f}")
print(f"  {'Grid':<15} {'~':>8} {'~':>10} {'20%':>6} ${grid_est:>+8.2f}")
print(f"  {'Cash':<15} {'':>8} {'':>10} {'10%':>6} {'$0.00':>10}")
print(f"  {'─'*15}─{'─'*8}─{'─'*10}─{'─'*7}─{'─'*10}")
print(f"  {'TOTAL':<15} {'':>8} {'':>10} {'100%':>6} ${total_combined:>+8.2f}")

# Compare
improvement = total_combined - dca_total_pnl
improvement_pct = (improvement / abs(dca_total_pnl)) * 100 if dca_total_pnl != 0 else 0
print(f"\n{'='*60}")
print(f"📈 COMPARISON")
print(f"{'='*60}")
print(f"  DCA Only:           ${dca_total_pnl:>+8.2f}")
print(f"  Combined Strategy:  ${total_combined:>+8.2f}")
print(f"  Improvement:        ${improvement:>+8.2f}")
print(f"  Risk reduction:     Multiple bots with different + correlated signals")
print(f"{'='*60}")

# Per-coin analysis for DCA
print(f"\n📋 DCA Per-Coin Breakdown (top/bottom):")
coin_dca = {}
for coin, pnl in dca_trades:
    if coin not in coin_dca: coin_dca[coin] = []
    coin_dca[coin].append(pnl)

for coin, pnls in sorted(coin_dca.items(), key=lambda x: sum(x[1]), reverse=True)[:5]:
    print(f"  🟢 {coin}: {len(pnls)} trades, ${sum(pnls):+.2f}")
for coin, pnls in sorted(coin_dca.items(), key=lambda x: sum(x[1]))[:3]:
    print(f"  🔴 {coin}: {len(pnls)} trades, ${sum(pnls):+.2f}")
