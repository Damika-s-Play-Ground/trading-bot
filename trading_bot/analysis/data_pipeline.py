#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
#7 — Data Pipeline: Download OHLCV data, calculate indicators, store locally
Also #5 — Add MACD, Bollinger Bands, Volume indicators
"""
import json, urllib.request, time, math
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT
DATA_FILE = BASE / "market_data.json"
COINS = ["BTC","ETH","SOL","BNB","XRP","LINK","ADA","AVAX","DOT","NEAR","ARB","OP","AAVE","IMX","ALGO","FIL","GRT","VET","HBAR","XLM","ATOM"]

def get_klines(symbol, interval="1d", limit=365):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}USDT&interval={interval}&limit={limit}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return [{
        "time": int(c[0]),
        "open": float(c[1]), "high": float(c[2]), "low": float(c[3]),
        "close": float(c[4]), "volume": float(c[5]),
        "quote_vol": float(c[7]),
    } for c in data]

# === INDICATORS ===
def calc_rsi(closes, period=14):
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

def calc_macd(closes, fast=12, slow=26, signal=9):
    """Returns MACD line, signal line, histogram"""
    def ema(data, period):
        multiplier = 2 / (period + 1)
        result = [data[0]]
        for i in range(1, len(data)):
            result.append((data[i] - result[-1]) * multiplier + result[-1])
        return result
    
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line[-1], signal_line[-1], histogram[-1]

def calc_bollinger(closes, period=20, std_dev=2):
    if len(closes) < period:
        return closes[-1], closes[-1], closes[-1]
    recent = closes[-period:]
    sma = sum(recent) / period
    variance = sum((x - sma) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    return sma, sma + std_dev * std, sma - std_dev * std

def calc_volume_ma(volumes, period=20):
    if len(volumes) < period: return sum(volumes) / len(volumes) if volumes else 0
    return sum(volumes[-period:]) / period

# === Build data ===
print(f"📥 Downloading OHLCV data for {len(COINS)} coins (365 days)...")
print()

all_data = {}
for coin in COINS:
    try:
        klines = get_klines(coin, "1d", 400)
        print(f"  {coin:>5}: {len(klines)} candles")
        
        closes = [k["close"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        volumes = [k["quote_vol"] for k in klines]
        
        # Calculate indicators for the last 200 candles
        indicator_data = []
        for i in range(len(klines) - 200, len(klines)):
            if i < 0: continue
            lookback = closes[:i+1]
            lookback_v = volumes[:i+1]
            
            rsi14 = calc_rsi(lookback, 14)
            rsi7 = calc_rsi(lookback, 7)
            macd, macd_sig, macd_hist = calc_macd(lookback)
            bb_mid, bb_up, bb_low = calc_bollinger(lookback)
            vol_ma20 = calc_volume_ma(lookback_v, 20)
            
            indicator_data.append({
                "date": klines[i]["time"],
                "close": klines[i]["close"],
                "high": klines[i]["high"],
                "low": klines[i]["low"],
                "volume": klines[i]["quote_vol"],
                "rsi14": round(rsi14, 2),
                "rsi7": round(rsi7, 2),
                "macd": round(macd, 4),
                "macd_signal": round(macd_sig, 4),
                "macd_hist": round(macd_hist, 4),
                "bb_upper": round(bb_up, 2),
                "bb_middle": round(bb_mid, 2),
                "bb_lower": round(bb_low, 2),
                "bb_width": round((bb_up - bb_low) / bb_mid * 100, 2) if bb_mid else 0,
                "vol_ma20": round(vol_ma20, 2),
                "vol_ratio": round(klines[i]["quote_vol"] / vol_ma20, 2) if vol_ma20 > 0 else 0,
            })
        
        all_data[coin] = indicator_data
        time.sleep(0.1)  # Rate limit
    except Exception as e:
        print(f"  {coin:>5}: ERROR — {e}")

# Save
output = {
    "generated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    "coins": all_data,
}
with open(DATA_FILE, "w") as f:
    json.dump(output, f, indent=1)

print(f"\n💾 Saved: {DATA_FILE}")
print()

# === ANALYSIS ===
# Correlation matrix (last 200 days)
print("📊 Correlation Matrix (last 200 days):")
correlations = {}
for coin1 in COINS[:10]:  # Top 10 for readability
    c1_data = all_data.get(coin1, [])
    c1_closes = [d["close"] for d in c1_data[-200:]]
    if not c1_closes: continue
    
    row = {}
    for coin2 in COINS[:10]:
        if coin1 >= coin2: continue  # Lower triangle only
        c2_data = all_data.get(coin2, [])
        c2_closes = [d["close"] for d in c2_data[-200:]]
        if not c2_closes or len(c1_closes) != len(c2_closes): continue
        
        # Simple Pearson
        n = min(len(c1_closes), len(c2_closes))
        x, y = c1_closes[:n], c2_closes[:n]
        mx, my = sum(x)/n, sum(y)/n
        num = sum((a-mx)*(b-my) for a,b in zip(x,y))
        den = math.sqrt(sum((a-mx)**2 for a in x)) * math.sqrt(sum((b-my)**2 for b in y))
        corr = num / den if den else 0
        row[coin2] = round(corr, 2)
    
    if row:
        correlations[coin1] = row

for c1, pairs in sorted(correlations.items()):
    for c2, corr in sorted(pairs.items(), key=lambda x: -abs(x[1])):
        emoji = "🟢" if abs(corr) < 0.4 else ("🟡" if abs(corr) < 0.7 else "🔴")
        print(f"  {c1:>5} × {c2:>5}: {corr:>+5.2f} {emoji}")

# Current market state summary
print(f"\n📈 Current Market State:")
for coin in COINS:
    data = all_data.get(coin, [])
    if not data: continue
    latest = data[-1]
    rsi = latest["rsi14"]
    bb_width = latest["bb_width"]
    macd = latest["macd_hist"]
    vol = latest["vol_ratio"]
    
    rsi_sig = "🟢" if rsi < 30 else ("🟡" if rsi < 50 else "🔴")
    bb_sig = "🟢" if latest["close"] <= latest["bb_lower"] else ("🟡" if latest["close"] <= latest["bb_middle"] else "🔴")
    macd_sig = "🟢" if macd > 0 else "🔴"
    
    print(f"  {coin:>5}: RSI={rsi:>5.1f} {rsi_sig} | BB={bb_width:>5.1f}% {bb_sig} | MACD={macd:>+7.4f} {macd_sig} | Vol={vol:.1f}x")

print(f"\n✅ Pipeline complete!")
