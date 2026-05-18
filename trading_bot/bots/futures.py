#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Futures Paper Trading Bot — isolated from spot bots
"""
import json, urllib.request, time, math
from pathlib import Path
from datetime import datetime, timezone

from trading_bot.core.state_store import load_json_path, save_json_path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT
PAPER_FILE = BASE_DIR / "paper_futures.json"

CONFIG = {
    "coins": ["BTC","ETH","SOL"],
    "leverage": 3,
    "margin_per_trade": 30.0,
    "max_positions": 3,
    "initial_balance": 300.0,
    "take_profit_pct": 5.0,
    "stop_loss_pct": -3.0,
    "min_funding_abs": 0.0001,
}

class PaperFutures:
    def __init__(self):
        self.initial = CONFIG["initial_balance"]
        self.margin = self.initial
        self.positions = {}
        self.trade_log = []
        self.peak_value = self.initial
        self.load()
    
    def load(self):
        d = load_json_path(PAPER_FILE, {})
        self.margin = d.get("margin", self.initial)
        self.positions = d.get("positions", {})
        self.trade_log = d.get("trade_log", [])
        self.peak_value = d.get("peak_value", self.initial)
    
    def save(self):
        save_json_path(PAPER_FILE,{"margin": self.margin, "positions": self.positions,
            "trade_log": self.trade_log[-100:], "peak_value": self.peak_value,
            "updated": datetime.now(timezone.utc).isoformat()})
    
    def total_value(self, prices):
        val = self.margin
        for coin, pos in self.positions.items():
            liq = prices.get(coin, 0)
            side = 1 if pos["side"] == "LONG" else -1
            pnl = (liq - pos["entry"]) / pos["entry"] * pos["qty"] * side
            val += pnl
        return val
    
    def open_long(self, coin, price, margin):
        if self.margin < margin: margin = self.margin
        if margin < 10: return False
        lev = CONFIG["leverage"]
        qty = margin * lev
        liq_price = price * (1 - 1/lev * 0.9)
        self.margin -= margin
        self.positions[coin] = {"side": "LONG", "entry": price, "qty": qty,
            "margin": margin, "liq_price": liq_price, "peak": price,
            "time": datetime.now(timezone.utc).isoformat()}
        self.trade_log.append({"time": datetime.now(timezone.utc).isoformat(),
            "action": "LONG", "coin": coin, "price": round(price, 2),
            "qty": round(qty, 6), "margin": round(margin, 2)})
        self.save(); return True
    
    def open_short(self, coin, price, margin):
        if self.margin < margin: margin = self.margin
        if margin < 10: return False
        lev = CONFIG["leverage"]
        qty = margin * lev
        liq_price = price * (1 + 1/lev * 0.9)
        self.margin -= margin
        self.positions[coin] = {"side": "SHORT", "entry": price, "qty": qty,
            "margin": margin, "liq_price": liq_price, "peak": price,
            "time": datetime.now(timezone.utc).isoformat()}
        self.trade_log.append({"time": datetime.now(timezone.utc).isoformat(),
            "action": "SHORT", "coin": coin, "price": round(price, 2),
            "qty": round(qty, 6), "margin": round(margin, 2)})
        self.save(); return True
    
    def close(self, coin, price, reason="TP"):
        if coin not in self.positions: return False
        pos = self.positions[coin]
        lev = CONFIG["leverage"]
        side = 1 if pos["side"] == "LONG" else -1
        pnl_pct = (price - pos["entry"]) / pos["entry"] * side * 100
        margin_pnl = pos["margin"] * (pnl_pct / 100) * lev
        self.margin += pos["margin"] + margin_pnl
        self.trade_log.append({"time": datetime.now(timezone.utc).isoformat(),
            "action": f"CLOSE_{pos['side']}", "coin": coin, "price": round(price, 2),
            "pnl": round(margin_pnl, 2), "pnl_pct": round(pnl_pct, 1), "reason": reason})
        del self.positions[coin]
        self.save(); return True
    
    def check_exits(self, prices):
        closed = []
        for coin in list(self.positions.keys()):
            pos = self.positions[coin]
            price = prices.get(coin, 0)
            if price == 0: continue
            side = 1 if pos["side"] == "LONG" else -1
            pnl_pct = (price - pos["entry"]) / pos["entry"] * side * 100
            
            if price > pos["peak"]: pos["peak"] = price
            
            # Liquidation check
            if (pos["side"] == "LONG" and price <= pos["liq_price"]) or \
               (pos["side"] == "SHORT" and price >= pos["liq_price"]):
                self.close(coin, price, "LIQUIDATED")
                closed.append(coin); continue
            
            # TP
            if pnl_pct >= CONFIG["take_profit_pct"]:
                self.close(coin, price, f"TP+{CONFIG['take_profit_pct']}%")
                closed.append(coin); continue
            
            # SL
            if pnl_pct <= CONFIG["stop_loss_pct"]:
                self.close(coin, price, f"SL{CONFIG['stop_loss_pct']}%")
                closed.append(coin); continue
            
            # Trailing (aggressive for futures)
            if pnl_pct >= 3:
                trail = pos["peak"] * (1 - 0.01 * side)
                if (pos["side"] == "LONG" and price <= trail) or \
                   (pos["side"] == "SHORT" and price >= trail):
                    self.close(coin, price, "Trail")
                    closed.append(coin)
        return closed

def get_klines(sym, l=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval=1h&limit={l}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return [{"close":float(c[4]),"high":float(c[2]),"low":float(c[3]),"quote_vol":float(c[7])} for c in json.loads(resp.read())]

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
    if len(closes)<p: return closes[-1]
    return sum(closes[-p:])/p

def calc_macd(closes, f=12, s=26):
    if len(closes)<s+9: return 0,0,0
    fe=se=closes[0];fm,sm=2/(f+1),2/(s+1)
    for c in closes: fe=(c-fe)*fm+fe; se=(c-se)*sm+se
    return fe-se, 0, fe-se

def get_prices():
    req = urllib.request.Request("https://api.binance.com/api/v3/ticker/price")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return {p["symbol"]: float(p["price"]) for p in json.loads(resp.read())}

def run():
    print(f"🔵 FUTURES PAPER BOT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*55)
    
    paper = PaperFutures()
    prices = {}
    
    try:
        raw_prices = get_prices()
        for coin in CONFIG["coins"]:
            prices[coin] = raw_prices.get(f"{coin}USDT", 0)
    except:
        print("  Error fetching prices")
        return
    
    signals = []
    for coin in CONFIG["coins"]:
        price = prices.get(coin, 0)
        if price == 0: continue
        holding = coin in paper.positions
        
        try:
            klines = get_klines(coin, 100)
            closes = [k["close"] for k in klines]
            rsi = calc_rsi(closes)
            sma50 = calc_sma(closes, 50)
            sma20 = calc_sma(closes, 20)
            macd_l, _, macd_h = calc_macd(closes)
            vol = klines[-1]["quote_vol"]
        except:
            continue
        
        above_50ma = price > sma50
        trend_up = sma20 > sma50
        macd_bull = macd_h > 0
        
        print(f"  {coin:>5}: ${price:>8.2f} | RSI={rsi:5.1f} | 50MA={'🟢' if above_50ma else '🔴'} | MACD={'🟢' if macd_bull else '🔴'}")
        
        if not holding:
            # LONG signal: uptrend + MACD bullish + RSI > 40 (momentum intact)
            if above_50ma and macd_bull and rsi > 40 and vol > 100000:
                signals.append({"coin": coin, "price": price, "side": "LONG", "score": rsi})
                print(f"    → 🔵 LONG signal! RSI={rsi:.0f}")
            
            # SHORT signal: downtrend + oversold + macd bearish
            if not above_50ma and not macd_bull and rsi < 60:
                signals.append({"coin": coin, "price": price, "side": "SHORT", "score": 100-rsi})
                print(f"    → 🔴 SHORT signal! RSI={rsi:.0f}")
    
    print(f"\n🔍 Checking positions...")
    closed = paper.check_exits(prices)
    if closed: print(f"  Closed: {', '.join(closed)}")
    
    if paper.positions:
        for coin, pos in paper.positions.items():
            p = prices.get(coin, 0)
            side = 1 if pos["side"]=="LONG" else -1
            pnl = (p-pos["entry"])/pos["entry"]*side*100
            liq_dist = abs(p-pos["liq_price"])/pos["entry"]*100
            print(f"  {coin:>5}: {pos['side']:5s} @ ${pos['entry']:>8.2f} → ${p:>8.2f} ({pnl:+.1f}%) | Liq: {liq_dist:.1f}% away")
    
    # Execute
    signals.sort(key=lambda x: -x["score"])
    max_new = min(len(signals), CONFIG["max_positions"] - len(paper.positions))
    if max_new > 0:
        print(f"\n🛒 New positions:")
        for sig in signals[:max_new]:
            margin = min(CONFIG["margin_per_trade"], paper.margin)
            if margin < 10: break
            if sig["side"] == "LONG":
                paper.open_long(sig["coin"], sig["price"], margin)
                print(f"  LONG {sig['coin']}: ${margin:.0f} margin ({CONFIG['leverage']}x)")
            else:
                paper.open_short(sig["coin"], sig["price"], margin)
                print(f"  SHORT {sig['coin']}: ${margin:.0f} margin ({CONFIG['leverage']}x)")
    
    total = paper.total_value(prices)
    pnl = total - paper.initial
    pnl_pct = pnl/paper.initial*100
    
    print(f"\n{'='*55}")
    print(f"📋 Futures Summary")
    print(f"  Margin:     ${paper.initial:.0f} → ${paper.margin:.2f}")
    print(f"  Total val:  ${total:.2f}")
    print(f"  P&L:        ${pnl:+.2f} ({pnl_pct:+.2f}%)")
    print(f"  Leverage:   {CONFIG['leverage']}x")
    print(f"  Positions:  {len(paper.positions)}")
    print(f"  Trades:     {len(paper.trade_log)}")
    print(f"{'='*55}")
    paper.save()

if __name__ == "__main__":
    run()
