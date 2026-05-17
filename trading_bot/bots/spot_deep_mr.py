#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Bot #5 — Deep Mean Reversion
Strategy: Buy when RSI < 20 (extreme oversold), sell at +5% (quick scalps)
          Tighter SL at -6%, no trend filter (catches flash crashes)
Best for: 📊 High volatility / flash crashes
"""
import json, urllib.request, time
from pathlib import Path
from datetime import datetime, timezone

from trading_bot.core.bot_runtime import (
    get_available_budget,
    get_blocked_coins,
    get_target_capital,
    new_buys_disabled,
    scale_trade_size,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT
PAPER_FILE = BASE_DIR / "paper_deepmr.json"
CONFIG = {"coins":["BTC","ETH","SOL","BNB","XRP","LINK","ADA","AVAX","DOT","NEAR","ARB","OP","AAVE","IMX","ALGO","FIL","GRT","HBAR","XLM","ATOM"],
    "rsi_entry":20,"rsi_period":7,"take_profit_pct":5.5,"stop_loss_pct":-6.0,
    "trailing_activation":3.0,"trailing_distance":1.5,
    "buy_per_trade":5.0,"max_positions":6,"max_spend_per_day":30.0,"initial_balance":200.0,"min_volume":500}
CONFIG["initial_balance"] = get_target_capital(CONFIG["initial_balance"])

def get_klines(s,l=100):
    url=f"https://api.binance.com/api/v3/klines?symbol={s}USDT&interval=1h&limit={l}"
    req=urllib.request.Request(url)
    with urllib.request.urlopen(req,timeout=15)as r:
        return[{"close":float(c[4]),"high":float(c[2]),"low":float(c[3]),"quote_vol":float(c[7])}for c in json.loads(r.read())]

def calc_rsi(closes,p=7):
    if len(closes)<p+1:return 50
    g=l=0
    for i in range(-p,0):
        d=closes[i]-closes[i-1]
        if d>0:g+=d
        else:l-=d
    ag,al=g/p,l/p
    if al==0:return 100
    return 100-(100/(1+ag/al))

class PaperDMR:
    def __init__(self):
        self.initial=CONFIG["initial_balance"];self.usdt=self.initial
        self.positions={};self.trade_log=[];self.load()
    def load(self):
        if PAPER_FILE.exists():
            with open(PAPER_FILE)as f:d=json.load(f)
            self.initial=d.get("initial",self.initial)
            self.usdt=d.get("usdt",self.initial);self.positions=d.get("positions",{})
            self.trade_log=d.get("trade_log",[])
    def save(self):
        with open(PAPER_FILE,"w")as f:json.dump({"initial":self.initial,"usdt":self.usdt,"positions":self.positions,
            "trade_log":self.trade_log[-100:],"updated":datetime.now(timezone.utc).isoformat()},f,indent=2)
    def total_value(self,p):
        v=self.usdt
        for c,pos in self.positions.items():v+=pos["qty"]*p.get(c,0)
        return v
    def buy(self,c,p,u):
        if self.usdt<u:u=self.usdt
        if u<3:return False
        q=u/p*0.999;self.usdt-=u
        if c in self.positions:
            pos=self.positions[c];tc=pos["qty"]*pos["avg_price"]+q*p
            pos["qty"]+=q;pos["avg_price"]=tc/pos["qty"]
            if p>pos["peak"]:pos["peak"]=p
        else:self.positions[c]={"qty":q,"avg_price":p,"peak":p}
        self.trade_log.append({"time":datetime.now(timezone.utc).isoformat(),"action":"BUY","coin":c,"price":round(p,4),"qty":round(q,6),"usdt":round(u,2)})
        self.save();return True
    def sell(self,c,p,r="TP",f=1.0):
        if c not in self.positions:return False
        pos=self.positions[c];sq=pos["qty"]*f;pp=sq*p;fee=pp*0.001;pnl=pp-fee-(sq*pos["avg_price"])
        self.usdt+=pp-fee
        self.trade_log.append({"time":datetime.now(timezone.utc).isoformat(),"action":"SELL","coin":c,"price":round(p,4),"qty":round(sq,6),"pnl":round(pnl,2),"reason":r})
        if f>=1.0:del self.positions[c]
        else:pos["qty"]-=sq;pos["peak"]=p
        self.save();return True
    def check_exits(self,prices):
        sold=[]
        for c in list(self.positions.keys()):
            pos=self.positions[c];p=prices.get(c,0)
            if p==0:continue
            pnl=(p-pos["avg_price"])/pos["avg_price"]*100
            if p>pos["peak"]:pos["peak"]=p
            if pnl<=CONFIG["stop_loss_pct"]:self.sell(c,p,f"SL{CONFIG['stop_loss_pct']}%");sold.append(c);continue
            if pnl>=CONFIG["take_profit_pct"]:self.sell(c,p,f"TP+{CONFIG['take_profit_pct']}%");sold.append(c);continue
            if pnl>=CONFIG["trailing_activation"]:
                trail=pos["peak"]*(1-CONFIG["trailing_distance"]/100)
                if p<=trail:self.sell(c,p,"Trail");sold.append(c)
        return sold

def run():
    print(f"⚡ Bot #5 — Deep Mean Reversion — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*55)
    paper=PaperDMR();prices={};signals=[]
    target_capital = get_target_capital(paper.initial)
    blocked_coins = get_blocked_coins()
    manager_paused_buys = new_buys_disabled()
    print(f"🎯 Target capital: ${target_capital:.2f}")
    if blocked_coins:
        print(f"⛔ Blocked for new exposure: {', '.join(sorted(blocked_coins))}")
    if manager_paused_buys:
        print("🛑 Manager guard active: new buys disabled for this run")
    
    for coin in CONFIG["coins"]:
        try:
            klines=get_klines(coin,100)
            if not klines:continue
            closes=[c["close"]for c in klines];price=klines[-1]["close"];prices[coin]=price
            rsi=calc_rsi(closes,CONFIG["rsi_period"])
            vol=klines[-1]["quote_vol"]
            deep_oversold=rsi<CONFIG["rsi_entry"]
            has_vol=vol>CONFIG["min_volume"]
            holding=coin in paper.positions
            
            rsi_c="🟢"if rsi<20 else("🟡"if rsi<35 else"🔴")
            print(f"  {coin:>5}: ${price:>8.2f} | RSI={rsi:5.1f} {rsi_c} | Vol=${vol:>10,.0f}")
            
            if not holding and coin not in blocked_coins and deep_oversold and has_vol:
                score=(CONFIG["rsi_entry"]-rsi)*3
                signals.append({"coin":coin,"price":price,"score":round(score,1),"rsi":rsi})
                print(f"    → ⚡ DEEP OVERSOLD! RSI={rsi:.1f}")
        except:continue
    
    print(f"\n🔍 Checking exits...")
    sold=paper.check_exits(prices)
    if sold:print(f"  💰 Sold: {', '.join(sold)}")
    
    if paper.positions:
        for c,p in paper.positions.items():
            pr=prices.get(c,0);pnl=((pr-p["avg_price"])/p["avg_price"])*100 if pr>0 else 0
            print(f"  {c:>5}: {p['qty']:>6.4f} @ ${p['avg_price']:>8.2f} → ${pr:>8.2f} ({pnl:+.2f}%)")
    
    signals.sort(key=lambda x:-x["score"])
    max_new=min(len(signals),CONFIG["max_positions"]-len(paper.positions))
    remaining_budget = get_available_budget(paper.total_value(prices), CONFIG["max_spend_per_day"], target_capital)
    
    if manager_paused_buys:
        print(f"\n🛒 Manager risk guard — buys skipped.")
    elif signals and max_new>0 and remaining_budget>3:
        print(f"\n🛒 Deep MR signals:")
        for sig in signals[:max_new]:
            scaled_trade = scale_trade_size(CONFIG["buy_per_trade"], target_capital, paper.initial)
            cost=min(scaled_trade, remaining_budget/max_new)
            if cost<3:break
            print(f"  BUY {sig['coin']}: ${cost:.2f} @ ${sig['price']:.4f} (RSI={sig['rsi']:.1f})")
            if paper.buy(sig["coin"],sig["price"],cost):
                remaining_budget -= cost
    else:print(f"\n📭 No deep oversold signals.")
    
    total=paper.total_value(prices);pnl=total-paper.initial;pnlp=pnl/paper.initial*100
    print(f"\n{'='*55}")
    print(f"📋 Deep MR Summary")
    print(f"  Balance: ${paper.initial:.0f} → ${total:.2f} ({pnlp:+.2f}%)")
    print(f"  Positions: {len(paper.positions)}")
    print(f"{'='*55}")
    paper.save()

if __name__=="__main__":
    run()
