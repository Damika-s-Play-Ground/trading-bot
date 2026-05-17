#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Bot #3 — Grid Trading
Strategy: Place N buy/sell orders in a price range, profit from every bounce
Best for: ➡️ Sideways/ranging markets
"""

import json, urllib.request, time
from pathlib import Path
from datetime import datetime, timezone
import math

from trading_bot.core.bot_runtime import get_blocked_coins, get_target_capital, new_buys_disabled

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT
PAPER_FILE = BASE_DIR / "paper_grid.json"

CONFIG = {
    "coins": ["BTC","ETH","SOL","XRP","ADA"],
    "grid_levels": 8,
    "grid_spacing_pct": 1.7,
    "range_buffer_pct": 15,     # Range is current_price ± this %
    "buy_per_grid": 5.0,        # USDT per grid level
    "max_positions": 8,
    "stop_loss_pct": -12,
    "initial_balance": 300.0,
    "min_volume": 10000,
}

CONFIG["initial_balance"] = get_target_capital(CONFIG["initial_balance"])

class PaperGrid:
    def __init__(self):
        self.initial = CONFIG["initial_balance"]
        self.usdt = self.initial
        self.positions = {}  # coin -> list of grid orders
        self.trade_log = []
        self.load()
    
    def load(self):
        if PAPER_FILE.exists():
            with open(PAPER_FILE) as f:
                d = json.load(f)
                self.initial = d.get("initial", self.initial)
                self.usdt = d.get("usdt", self.initial)
                self.positions = d.get("positions", {})
                self.trade_log = d.get("trade_log", [])
    
    def save(self):
        with open(PAPER_FILE, "w") as f:
            json.dump({"initial": self.initial, "usdt": self.usdt, "positions": self.positions,
                "trade_log": self.trade_log[-100:], "updated": datetime.now(timezone.utc).isoformat()}, f, indent=2)
    
    def setup_grids(self, prices):
        """Initialize grid for each coin if not already set up"""
        for coin in CONFIG["coins"]:
            if coin in self.positions and self.positions[coin]:
                continue  # Grid already set
            price = prices.get(coin, 0)
            if price == 0: continue
            self.positions[coin] = []
    
    def check_grid(self, coin, price, can_open_new_positions=True):
        """Check if any grid orders should fill"""
        trades_this_run = []
        if coin not in self.positions: return trades_this_run
        grid_orders = self.positions.get(f"{coin}_orders", [])
        if not grid_orders:
            # Create grid
            mid = price
            spacing = CONFIG["grid_spacing_pct"] / 100
            grid_orders = []
            for i in range(1, CONFIG["grid_levels"] + 1):
                buy_px = mid * (1 - spacing * i)
                sell_px = mid * (1 + spacing * i)
                grid_orders.append({"type": "BUY", "price": buy_px, "executed": False, "qty": CONFIG["buy_per_grid"] / buy_px * 0.999, "usdt": CONFIG["buy_per_grid"]})
                grid_orders.append({"type": "SELL", "price": sell_px, "executed": False, "qty": 0, "usdt": 0})
            self.positions[f"{coin}_orders"] = grid_orders
            self.positions[coin] = []
        
        for order in grid_orders:
            if order["executed"]: continue
            if order["type"] == "BUY" and can_open_new_positions and price <= order["price"] and self.usdt >= order["usdt"]:
                order["executed"] = True
                self.usdt -= order["usdt"]
                pos = {"qty": order["qty"], "avg_price": order["price"], "peak_price": order["price"], "sell_order": order}
                self.positions[coin].append(pos)
                self.trade_log.append({"time": datetime.now(timezone.utc).isoformat(), "action": "GRID_BUY",
                    "coin": coin, "price": round(order["price"], 4), "qty": round(order["qty"], 6), "usdt": round(order["usdt"], 2)})
                trades_this_run.append(f"BUY {coin} @ ${order['price']:.4f}")
            elif order["type"] == "SELL" and price >= order["price"]:
                # Check if we have a matching buy to sell
                for pos in self.positions[coin]:
                    if pos.get("sell_order") and pos["sell_order"] == order and not pos.get("sold"):
                        pos["sold"] = True
                        proceeds = pos["qty"] * price
                        fee = proceeds * 0.001
                        self.usdt += proceeds - fee
                        pnl = proceeds - fee - (pos["qty"] * pos["avg_price"])
                        self.trade_log.append({"time": datetime.now(timezone.utc).isoformat(), "action": "GRID_SELL",
                            "coin": coin, "price": round(price, 4), "qty": round(pos["qty"], 6), "pnl": round(pnl, 2), "usdt": round(proceeds-fee, 2)})
                        order["executed"] = True
                        trades_this_run.append(f"SELL {coin} @ ${price:.4f} (PnL: ${pnl:.2f})")
                        break
        
        self.save()
        return trades_this_run

def run():
    print(f"➡️ Bot #3 — Grid Trading — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*55)
    
    # Get prices
    paper = PaperGrid()
    target_capital = get_target_capital(paper.initial)
    blocked_coins = get_blocked_coins()
    manager_paused_buys = new_buys_disabled()
    print(f"🎯 Target capital: ${target_capital:.2f}")
    if blocked_coins:
        print(f"⛔ Blocked for new exposure: {', '.join(sorted(blocked_coins))}")
    if manager_paused_buys:
        print("🛑 Manager guard active: new buys disabled for this run")
    prices = {}
    try:
        req = urllib.request.Request("https://api.binance.com/api/v3/ticker/price")
        with urllib.request.urlopen(req, timeout=10) as resp:
            all_p = json.loads(resp.read())
            pmap = {p["symbol"]: float(p["price"]) for p in all_p}
        for coin in CONFIG["coins"]:
            p = pmap.get(f"{coin}USDT", 0)
            if p: prices[coin] = p
            print(f"  {coin:>5}: ${p:>8.2f}")
    except Exception as e:
        print(f"  Error: {e}")
        return
    
    # Setup grids
    for coin in CONFIG["coins"]:
        p = prices.get(coin, 0)
        if p == 0: continue
        if coin in blocked_coins or manager_paused_buys:
            continue
        key = f"{coin}_orders"
        if key not in paper.positions or not paper.positions[key]:
            spacing = CONFIG["grid_spacing_pct"] / 100
            orders = []
            for i in range(1, CONFIG["grid_levels"] + 1):
                buy_px = round(p * (1 - spacing * i), 8)
                sell_px = round(p * (1 + spacing * i), 8)
                qty = CONFIG["buy_per_grid"] / buy_px * 0.999
                orders.append({"type": "BUY", "price": buy_px, "executed": False, "qty": qty, "usdt": CONFIG["buy_per_grid"]})
                orders.append({"type": "SELL", "price": sell_px, "executed": False, "qty": 0, "usdt": 0})
            paper.positions[key] = orders
            paper.positions[coin] = []
            print(f"  📐 Grid set for {coin}: {CONFIG['grid_levels']} levels, {CONFIG['grid_spacing_pct']}% spacing")
            print(f"     Range: ${p*(1-spacing):.4f} - ${p*(1+spacing):.4f}")
    
    # Check fills
    print(f"\n🔍 Checking grid fills...")
    all_trades = []
    for coin in CONFIG["coins"]:
        p = prices.get(coin, 0)
        if p == 0: continue
        bot_total = paper.usdt + sum(
            pos["qty"] * prices.get(coin_name, 0)
            for coin_name in CONFIG["coins"]
            for pos in paper.positions.get(coin_name, [])
            if not pos.get("sold")
        )
        can_open_new_positions = (not manager_paused_buys) and coin not in blocked_coins and bot_total < target_capital
        trades = paper.check_grid(coin, p, can_open_new_positions=can_open_new_positions)
        all_trades.extend(trades)
    
    for t in all_trades:
        print(f"  ⚡ {t}")
    if not all_trades:
        print(f"  No fills this run.")
    
    # Summary
    total = paper.usdt
    for coin in CONFIG["coins"]:
        for pos in paper.positions.get(coin, []):
            if not pos.get("sold"):
                total += pos["qty"] * prices.get(coin, 0)
    
    pnl = total - paper.initial
    pnl_pct = (pnl / paper.initial) * 100
    grid_positions = sum(1 for c in CONFIG["coins"] for p in paper.positions.get(c, []) if not p.get("sold"))
    
    print(f"\n{'='*55}")
    print(f"📋 Grid Bot Summary")
    print(f"  Balance:  ${paper.initial:.0f} → ${total:.2f} ({pnl_pct:+.2f}%)")
    print(f"  USDT:     ${paper.usdt:.2f}")
    print(f"  Grid pos: {grid_positions}")
    print(f"  Trades:   {len([t for t in paper.trade_log])}")
    print(f"{'='*55}")
    paper.save()

if __name__ == "__main__":
    run()
