#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Backtest Bot #2 — Trend Following
"""
import urllib.request, json, time

COINS = ["BTC","ETH","SOL","BNB","XRP","LINK","ADA","AVAX","DOT","NEAR"]
BUDGET = 600.0
DAYS = 200

def get_klines(symbol, limit=300):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}USDT&interval=1d&limit={limit}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return [{"close":float(c[4]),"high":float(c[2]),"low":float(c[3])} for c in data]

def calc_ema(closes, p):
    if len(closes) < p: return closes[-1]
    m=2/(p+1); r=closes[0]
    for c in closes[1:]: r=(c-r)*m+r
    return r

def calc_macd(closes, f=12, s=26, sig=9):
    if len(closes) < s+sig: return 0,0,0
    fe=se=closes[0]
    fas,slas=[],[]
    fm,sm=2/(f+1),2/(s+1)
    for c in closes:
        fe=(c-fe)*fm+fe;se=(c-se)*sm+se
        fas.append(fe);slas.append(se)
    ml=[fa-sl for fa,sl in zip(fas,slas)]
    sgm=2/(sig+1); sg=ml[0]
    for m in ml: sg=(m-sg)*sgm+sg
    return ml[-1],sg,ml[-1]-sg

def calc_sma(closes, p):
    if len(closes)<p: return closes[-1]
    return sum(closes[-p:])/p

print("📊 Backtest Bot #2 — Trend Following")
print(f"  Coins: {len(COINS)} | Budget: ${BUDGET} | Period: {DAYS} days")
print()

bot_trades = 0
bot_wins = 0
bot_pnl = 0.0

for coin in COINS:
    try:
        klines = get_klines(coin, DAYS+100)
    except:
        print(f"  {coin}: FAILED"); continue
    
    usdt = BUDGET / len(COINS)
    pos = None
    coin_trades = 0
    coin_wins = 0
    coin_pnl = 0.0
    
    for i in range(60, len(klines)):
        k = klines[i]
        closes = [c["close"] for c in klines[:i+1]]
        close = k["close"]
        
        sma50 = calc_sma(closes, 50)
        sma20 = calc_sma(closes, 20)
        macd_l, macd_s, macd_h = calc_macd(closes)
        
        in_trend = close > sma50
        macd_bullish = macd_h > 0
        above_20ma = close > sma20
        
        # Exit
        if pos is not None:
            pnl = (close - pos["avg"]) / pos["avg"] * 100
            
            # Trend broken?
            if close < sma20:
                usdt += pos["qty"] * close * 0.999
                if pnl > 0: coin_wins += 1
                coin_pnl += pnl
                coin_trades += 1
                pos = None
                continue
            
            # SL
            if pnl <= -8:
                usdt += pos["qty"] * close * 0.999
                if pnl > 0: coin_wins += 1
                coin_pnl += pnl
                coin_trades += 1
                pos = None
                continue
            
            # TP
            if pnl >= 15:
                usdt += pos["qty"] * close * 0.999
                coin_wins += 1; coin_pnl += 15; coin_trades += 1
                pos = None
                continue
        
        # Entry
        if pos is None and usdt > 5 and in_trend and macd_bullish and above_20ma:
            cost = min(10, usdt)
            pos = {"qty": cost*0.999/close, "avg": close}
            usdt -= cost
    
    if pos:
        close = klines[-1]["close"]
        pnl = (close - pos["avg"])/pos["avg"]*100
        usdt += pos["qty"]*close*0.999
        coin_pnl += pnl
        if coin_trades == 0:
            coin_trades = 1
    
    bot_trades += coin_trades
    bot_wins += coin_wins
    bot_pnl += coin_pnl
    
    wr = f"{coin_wins/coin_trades*100:.0f}%" if coin_trades else "—"
    print(f"  {coin:>5}: {coin_trades} trades | {coin_wins} wins | {wr} | P&L: ${coin_pnl:+.2f}")

wr_total = f"{bot_wins/bot_trades*100:.0f}%" if bot_trades else "—"
print(f"\n{'='*55}")
print(f"📋 Trend Bot Backtest Results")
print(f"  Total trades: {bot_trades}")
print(f"  Total wins:   {bot_wins} ({wr_total})")
print(f"  Total P&L:    ${bot_pnl:+.2f}")
print(f"  ROI:          {bot_pnl/BUDGET*100:+.2f}%")
print(f"{'='*55}")
