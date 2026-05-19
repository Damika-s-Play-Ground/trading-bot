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

from trading_bot.core.atr_risk import calculate_atr, normalize_position_size, resolve_atr_exit_profile
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
PAPER_FILE = BASE_DIR / "paper_deepmr.json"
CONFIG = {"coins":["BTC","ETH","SOL","BNB","XRP","LINK","ADA","AVAX","DOT","NEAR","ARB","OP","AAVE","IMX","ALGO","FIL","GRT","HBAR","XLM","ATOM"],
    "rsi_entry":20,"rsi_period":7,"take_profit_pct":5.5,"stop_loss_pct":-6.0,
    "trailing_activation":3.0,"trailing_distance":1.5,
    "buy_per_trade":5.0,"max_positions":6,"max_spend_per_day":30.0,"initial_balance":200.0,"min_volume":500,
    "atr_risk": {"period": 14, "risk_per_trade_pct": 0.45, "stop_atr_multiple": 1.8,
        "take_profit_atr_multiple": 2.4, "trailing_activation_atr_multiple": 1.3,
        "trailing_distance_atr_multiple": 0.9, "min_stop_loss_pct": 3.0,
        "max_stop_loss_pct": 8.0, "min_take_profit_pct": 4.0, "max_take_profit_pct": 12.0,
        "min_trailing_activation_pct": 2.0, "max_trailing_activation_pct": 6.0,
        "min_trailing_distance_pct": 1.0, "max_trailing_distance_pct": 3.5,
        "min_position_multiplier": 0.75, "max_position_multiplier": 1.25},
    "order_book_enabled":True,"order_book_limit":20,"order_book_depth_window_pct":1.0,
    "max_spread_pct":0.5,"order_book_max_slippage_pct":0.25,"order_book_min_depth_multiple":8.0,
    "order_book_fail_closed":True}
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


def atr_settings():
    return CONFIG.get("atr_risk", {})


def build_risk_profile(price, klines):
    atr_value = calculate_atr(klines, period=atr_settings().get("period", 14))
    return resolve_atr_exit_profile(
        price=price,
        atr_value=atr_value,
        settings=atr_settings(),
        fixed_stop_loss_pct=CONFIG["stop_loss_pct"],
        fixed_take_profit_pct=CONFIG["take_profit_pct"],
        fixed_trailing_activation_pct=CONFIG["trailing_activation"],
        fixed_trailing_distance_pct=CONFIG["trailing_distance"],
    )


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
        d=load_json_path(PAPER_FILE,{})
        self.initial=d.get("initial",self.initial)
        self.usdt=d.get("usdt",self.initial);self.positions=d.get("positions",{})
        self.trade_log=d.get("trade_log",[])
    def save(self):
        save_json_path(PAPER_FILE,{"initial":self.initial,"usdt":self.usdt,"positions":self.positions,
            "trade_log":self.trade_log[-100:],"updated":datetime.now(timezone.utc).isoformat()})
    def total_value(self,p):
        v=self.usdt
        for c,pos in self.positions.items():v+=pos["qty"]*p.get(c,0)
        return v
    def buy(self,c,p,u,risk_profile=None):
        if self.usdt<u:u=self.usdt
        if u<3:return False
        q=u/p*0.999;self.usdt-=u
        if c in self.positions:
            pos=self.positions[c];tc=pos["qty"]*pos["avg_price"]+q*p
            pos["qty"]+=q;pos["avg_price"]=tc/pos["qty"]
            if p>pos["peak"]:pos["peak"]=p
            if risk_profile:pos["risk_profile"]=risk_profile
        else:self.positions[c]={"qty":q,"avg_price":p,"peak":p,"risk_profile":risk_profile or {}}
        self.trade_log.append({"time":datetime.now(timezone.utc).isoformat(),"action":"BUY","coin":c,"price":round(p,4),"qty":round(q,6),"usdt":round(u,2),"atr_pct":round((risk_profile or {}).get("atr_pct",0.0),4)})
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
            profile=pos.get("risk_profile") or build_risk_profile(pos["avg_price"], [{"high": pos["avg_price"], "low": pos["avg_price"], "close": pos["avg_price"]}])
            if pnl<=profile["stop_loss_pct"]:self.sell(c,p,f"SL{profile['stop_loss_pct']:.2f}%");sold.append(c);continue
            if pnl>=profile["take_profit_pct"]:self.sell(c,p,f"TP+{profile['take_profit_pct']:.2f}%");sold.append(c);continue
            if pnl>=profile["trailing_activation_pct"]:
                trail=pos["peak"]*(1-profile["trailing_distance_pct"]/100)
                if p<=trail:self.sell(c,p,f"Trail {profile['trailing_distance_pct']:.2f}%");sold.append(c)
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
            risk_profile=build_risk_profile(price, klines)
            
            rsi_c="🟢"if rsi<20 else("🟡"if rsi<35 else"🔴")
            print(f"  {coin:>5}: ${price:>8.2f} | RSI={rsi:5.1f} {rsi_c} | ATR={risk_profile['atr_pct']:.2f}% | Vol=${vol:>10,.0f}")
            
            if not holding and coin not in blocked_coins and deep_oversold and has_vol:
                score=(CONFIG["rsi_entry"]-rsi)*3
                signals.append({"coin":coin,"price":price,"score":round(score,1),"rsi":rsi,"risk_profile":risk_profile})
                print(f"    → ⚡ DEEP OVERSOLD! RSI={rsi:.1f}")
        except:continue
    
    print(f"\n🔍 Checking exits...")
    sold=paper.check_exits(prices)
    if sold:print(f"  💰 Sold: {', '.join(sold)}")
    
    if paper.positions:
        for c,p in paper.positions.items():
            pr=prices.get(c,0);pnl=((pr-p["avg_price"])/p["avg_price"])*100 if pr>0 else 0
            rp=p.get("risk_profile",{})
            print(f"  {c:>5}: {p['qty']:>6.4f} @ ${p['avg_price']:>8.2f} → ${pr:>8.2f} ({pnl:+.2f}%) | SL {rp.get('stop_loss_pct', CONFIG['stop_loss_pct']):.2f}% | TP {rp.get('take_profit_pct', CONFIG['take_profit_pct']):.2f}%")
    
    signals.sort(key=lambda x:-x["score"])
    max_new=min(len(signals),CONFIG["max_positions"]-len(paper.positions))
    remaining_budget = get_available_budget(paper.total_value(prices), CONFIG["max_spend_per_day"], target_capital)
    
    if manager_paused_buys:
        print(f"\n🛒 Manager risk guard — buys skipped.")
    elif signals and max_new>0 and remaining_budget>3:
        print(f"\n🛒 Deep MR signals:")
        for sig in signals[:max_new]:
            scaled_trade = scale_trade_size(CONFIG["buy_per_trade"], target_capital, paper.initial)
            sized_trade = normalize_position_size(
                target_capital=target_capital,
                base_notional=scaled_trade,
                atr_pct_value=sig["risk_profile"]["atr_pct"],
                settings=atr_settings(),
            )
            cost=min(sized_trade, remaining_budget/max_new)
            if cost<3:break
            gate = evaluate_entry_gate(sig["coin"], cost, settings=order_book_settings())
            if not gate.get("ok"):
                print(f"  SKIP {sig['coin']}: order-book gate blocked entry ({compact_gate_reason(gate)})")
                continue
            print(f"  BUY {sig['coin']}: ${cost:.2f} @ ${sig['price']:.4f} (RSI={sig['rsi']:.1f}, ATR={sig['risk_profile']['atr_pct']:.2f}%, SL={sig['risk_profile']['stop_loss_pct']:.2f}%, TP={sig['risk_profile']['take_profit_pct']:.2f}%)")
            if paper.buy(sig["coin"],sig["price"],cost,risk_profile=sig["risk_profile"]):
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
