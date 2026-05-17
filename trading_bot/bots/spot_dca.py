#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Binance Smart DCA + Take-Profit Bot
Paper trading mode (no real money)
"""

import ccxt
import json
import os
import time
import hmac
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from trading_bot.core.bot_runtime import (
    get_available_budget,
    get_blocked_coins,
    get_target_capital,
    new_buys_disabled,
    scale_trade_size,
)

# === CONFIG ===
CONFIG_PATH = Path(__file__).parent / "config.json"
PAPER_FILE = Path(__file__).parent / "paper_state.json"

with open(CONFIG_PATH) as f:
    config = json.load(f)

coins = config["coins"]
dca = config["dca"]
tp_sl = config["tp_sl"]
risk = config["risk"]
filters = config["filters"]

# === BINANCE CLIENT ===
class BinanceClient:
    """Handles API calls to Binance (testnet or live)"""

    def __init__(self, testnet=True):
        self.testnet = testnet
        if testnet:
            # Binance testnet — fake money, real prices
            self.base = "https://testnet.binance.vision"
            self.api_key = os.environ.get("TESTNET_API_KEY", "")
            self.secret = os.environ.get("TESTNET_SECRET", "")
            self.exchange = ccxt.binance({
                "apiKey": self.api_key,
                "secret": self.secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            })
            self.exchange.set_sandbox_mode(True)
        else:
            self.base = "https://api.binance.com"
            self.api_key = os.environ.get("BINANCE_API_KEY", "")
            self.secret = os.environ.get("BINANCE_SECRET", "")
            self.exchange = ccxt.binance({
                "apiKey": self.api_key,
                "secret": self.secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            })
        self.public_only = not self.api_key or not self.secret

    def signed_request(self, endpoint, params=None):
        if params is None:
            params = {}
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        query = urllib.parse.urlencode(sorted(params.items()))
        sig = hmac.new(self.secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"{self.base}{endpoint}?{query}&signature={sig}"
        req = urllib.request.Request(url, headers={"X-MBX-APIKEY": self.api_key})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def get_prices(self):
        """Get current prices for all tracked coins"""
        req = urllib.request.Request(f"{self.base}/api/v3/ticker/price")
        with urllib.request.urlopen(req, timeout=15) as resp:
            all_prices = json.loads(resp.read())
        price_map = {}
        for p in all_prices:
            price_map[p["symbol"]] = float(p["price"])
        result = {}
        for coin in coins:
            sym = f"{coin}USDT"
            if sym in price_map:
                result[coin] = price_map[sym]
        return result

    def get_klines(self, symbol, interval="1h", limit=100):
        """Get OHLCV candles"""
        url = f"{self.base}/api/v3/klines?symbol={symbol}USDT&interval={interval}&limit={limit}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return [[float(x) for x in candle[1:6]] for candle in data]  # [open, high, low, close, volume]

    def get_24h_ticker(self, symbol):
        """Get 24hr ticker for volume check"""
        url = f"{self.base}/api/v3/ticker/24hr?symbol={symbol}USDT"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except:
            return {"quoteVolume": "0"}


# === INDICATORS ===
def calc_rsi(closes, period=14):
    """Calculate RSI from list of close prices"""
    if len(closes) < period + 1:
        return 50
    gains = 0
    losses = 0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_sma(closes, period):
    """Simple Moving Average"""
    if len(closes) < period:
        return closes[-1] if closes else 0
    return sum(closes[-period:]) / period


def calc_ema(closes, period):
    """Exponential Moving Average"""
    if len(closes) < period:
        return closes[-1] if closes else 0
    multiplier = 2 / (period + 1)
    result = closes[0]
    for i in range(1, len(closes)):
        result = (closes[i] - result) * multiplier + result
    return result


def calc_macd(closes, fast=12, slow=26, signal=9):
    """Returns (macd_line, signal_line, histogram)"""
    if len(closes) < slow + signal:
        return 0, 0, 0
    ema_fast = calc_ema(closes[-slow:], fast)
    # Proper EMA chain for MACD
    closes_list = closes[:]
    fast_emas = []
    slow_emas = []
    f_mult = 2 / (fast + 1)
    s_mult = 2 / (slow + 1)
    fe = closes_list[0]
    se = closes_list[0]
    for c in closes_list:
        fe = (c - fe) * f_mult + fe
        se = (c - se) * s_mult + se
        fast_emas.append(fe)
        slow_emas.append(se)
    macd_line = [f - s for f, s in zip(fast_emas, slow_emas)]
    sg_mult = 2 / (signal + 1)
    sg = macd_line[0]
    for m in macd_line:
        sg = (m - sg) * sg_mult + sg
    return macd_line[-1], sg, macd_line[-1] - sg


def calc_bollinger(closes, period=20, std_dev=2):
    """Returns (middle, upper, lower)"""
    if len(closes) < period:
        return closes[-1] if closes else 0, 0, 0
    import math
    recent = closes[-period:]
    sma = sum(recent) / period
    variance = sum((x - sma) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    return sma, sma + std_dev * std, sma - std_dev * std


# === PAPER TRADING STATE ===
class PaperTrading:
    """Simulated portfolio for paper trading"""

    def __init__(self):
        self.initial_balance = config.get("initial_balance", 1200.0)
        self.usdt = self.initial_balance
        self.positions = {}  # coin -> {"qty": float, "avg_price": float, "peak_price": float}
        self.trade_log = []
        self.daily_pnl = 0
        self.peak_value = self.initial_balance
        self.load()

    def load(self):
        if PAPER_FILE.exists():
            with open(PAPER_FILE) as f:
                data = json.load(f)
                self.initial_balance = data.get("initial_balance", self.initial_balance)
                self.usdt = data.get("usdt", self.initial_balance)
                self.positions = data.get("positions", {})
                self.trade_log = data.get("trade_log", [])
                self.daily_pnl = data.get("daily_pnl", 0)
                self.peak_value = data.get("peak_value", self.initial_balance)

    def save(self):
        PAPER_FILE.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "initial_balance": self.initial_balance,
            "usdt": self.usdt,
            "positions": self.positions,
            "trade_log": self.trade_log[-100:],
            "daily_pnl": self.daily_pnl,
            "peak_value": self.peak_value,
            "updated": datetime.now(timezone.utc).isoformat(),
        }
        if hasattr(self, "last_run"):
            state["last_run"] = self.last_run
        with open(PAPER_FILE, "w") as f:
            json.dump(state, f, indent=2)

    def total_value(self, prices):
        val = self.usdt
        for coin, pos in self.positions.items():
            val += pos["qty"] * prices.get(coin, 0)
        return val

    def buy(self, coin, price, usdt_amount):
        """Simulate a buy order"""
        if self.usdt < usdt_amount:
            usdt_amount = self.usdt
        if usdt_amount < 2:
            return False  # Minimum meaningful trade
        qty = usdt_amount / price
        fee = qty * 0.001  # 0.1% Binance spot fee
        net_qty = qty - fee
        self.usdt -= usdt_amount

        if coin in self.positions:
            # DCA into existing position
            pos = self.positions[coin]
            total_cost = (pos["qty"] * pos["avg_price"]) + (net_qty * price)
            pos["qty"] += net_qty
            pos["avg_price"] = total_cost / pos["qty"]
            # Reset peak if we're adding at a lower price
            if price > pos["peak_price"]:
                pos["peak_price"] = price
        else:
            self.positions[coin] = {
                "qty": net_qty,
                "avg_price": price,
                "peak_price": price,
            }

        self.trade_log.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "action": "BUY",
            "coin": coin,
            "price": round(price, 6),
            "qty": round(net_qty, 8),
            "usdt": round(usdt_amount, 2),
            "fee": round(fee * price, 4),
        })
        self.save()
        return True

    def sell(self, coin, price, reason="TP", fraction=1.0):
        """Simulate a sell order. fraction=1.0 sells entire position, 0.5 sells half."""
        if coin not in self.positions:
            return False
        pos = self.positions[coin]
        sell_qty = pos["qty"] * fraction
        proceeds = sell_qty * price
        fee = proceeds * 0.001
        net_proceeds = proceeds - fee
        pnl = net_proceeds - (sell_qty * pos["avg_price"])
        self.usdt += net_proceeds

        self.trade_log.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "action": "SELL",
            "coin": coin,
            "price": round(price, 6),
            "qty": round(sell_qty, 8),
            "usdt": round(net_proceeds, 2),
            "pnl": round(pnl, 2),
            "reason": reason,
        })

        if fraction >= 1.0:
            del self.positions[coin]
        else:
            pos["qty"] -= sell_qty
            # Reset peak on remaining position
            pos["peak_price"] = price
        self.save()
        return True

    def check_tp_sl(self, prices):
        """Check all positions for tiered take-profit and stop-loss"""
        sold = []
        tp_tiers = tp_sl.get("take_profit_tiers", [{"pct": 8.0, "sell_fraction": 1.0}])
        
        for coin in list(self.positions.keys()):
            pos = self.positions[coin]
            price = prices.get(coin, 0)
            if price == 0:
                continue

            pnl_pct = ((price - pos["avg_price"]) / pos["avg_price"]) * 100

            # Update trailing peak
            if price > pos["peak_price"]:
                pos["peak_price"] = price

            # Trailing stop check (on remaining position)
            if tp_sl["trailing_stop"]:
                if pnl_pct >= tp_sl["trailing_activation"]:
                    trail_price = pos["peak_price"] * (1 - tp_sl["trailing_distance"] / 100)
                    if price <= trail_price:
                        self.sell(coin, price, f"Trailing Stop (-{tp_sl['trailing_distance']}% from peak)")
                        sold.append(coin)
                        continue

            # Hard stop loss (always full exit)
            if pnl_pct <= tp_sl["stop_loss_pct"]:
                self.sell(coin, price, f"Stop Loss ({tp_sl['stop_loss_pct']}%)")
                sold.append(coin)
                continue

            # Tiered take-profit: check each tier
            for tier in tp_tiers:
                tier_pct = tier["pct"]
                tier_fraction = tier["sell_fraction"]
                # Check if this tier has already been hit (tracked via pos)
                tier_key = f"tp_tier_{tier_pct}"
                if pos.get(tier_key, False):
                    continue  # Already sold this tier
                if pnl_pct >= tier_pct:
                    self.sell(coin, price, f"TP Tier {tier_pct}% (sold {tier_fraction*100:.0f}%)", fraction=tier_fraction)
                    pos[tier_key] = True  # Mark tier as done
                    if coin not in sold:
                        sold.append(coin)
                    break  # Only hit one tier per check

        return sold


# === MAIN BOT ===
def fetch_fear_greed():
    """Fetch Fear & Greed Index (0-100). Returns None on failure."""
    try:
        req = urllib.request.Request("https://api.alternative.me/fng/?limit=1", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return int(data["data"][0]["value"])
    except:
        return None


def get_coin_weight(coin):
    """Get weight multiplier for a coin based on performance tier"""
    w = config.get("weights", {})
    if not w.get("performance_weighting", False):
        return 1.0
    tier_map = {c: v for v in w["tier1"] for c in w.get("tier1", [])}
    tier_map.update({c: w["tiers"]["tier1_weight"] for c in w.get("tier1", [])})
    tier_map.update({c: w["tiers"]["tier2_weight"] for c in w.get("tier2", [])})
    tier_map.update({c: w["tiers"]["tier3_weight"] for c in w.get("tier3", [])})
    tier_map.update({c: w["tiers"]["tier4_weight"] for c in w.get("tier4", [])})
    return tier_map.get(coin, 1.0)


def run():
    print(f"🤖 Binance Smart DCA Bot — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    client = BinanceClient(testnet=True)
    paper = PaperTrading()
    target_capital = get_target_capital(paper.initial_balance)
    blocked_coins = get_blocked_coins()
    manager_paused_buys = new_buys_disabled()

    print(f"🎯 Target capital: ${target_capital:.2f}")
    if blocked_coins:
        print(f"⛔ Blocked for new exposure: {', '.join(sorted(blocked_coins))}")
    if manager_paused_buys:
        print("🛑 Manager guard active: new buys disabled for this run")

    # Fear & Greed
    fng = fetch_fear_greed()
    if fng is not None:
        fng_icon = "🟢" if fng < 30 else ("🟡" if fng < 55 else "🔴")
        print(f"\n😱 Fear & Greed Index: {fng}/100 {fng_icon}")
        if fng >= filters.get("fear_greed_max", 70):
            print(f"  ⚠ F&G > {filters['fear_greed_max']} — Market too greedy. Skipping buys today.")
            skip_buys = True
        elif fng <= filters.get("fear_greed_boost", 25):
            print(f"  🟢 F&G < {filters['fear_greed_boost']} — Extreme fear! Boosted buy amount.")
            skip_buys = False
            buy_boost = filters.get("fear_greed_boost_multiplier", 1.5)
        else:
            skip_buys = False
            buy_boost = 1.0
    else:
        print(f"\n😱 Fear & Greed: unavailable")
        skip_buys = False
        buy_boost = 1.0

    # 1. Get prices
    prices = client.get_prices()
    print(f"\n📊 Market Prices:")
    for coin in coins[:10]:
        sym = f"{coin}USDT"
        val = prices.get(coin, 0)
        if val > 0:
            print(f"  {coin:>5}: ${val:>8.2f}")

    # 2. Calculate RSI for each coin
    print(f"\n📈 Indicators:")
    signals = []
    for coin in coins:
        price = prices.get(coin, 0)
        if price == 0:
            continue

        try:
            klines = client.get_klines(coin, "1h", 100)
            closes = [k[3] for k in klines]
            rsi14 = calc_rsi(closes, dca["rsi_period"])
            rsi7 = calc_rsi(closes, 7)
            sma50 = calc_sma(closes, 50)
            macd_line, macd_sig, macd_hist = calc_macd(closes)
            bb_mid, bb_up, bb_low = calc_bollinger(closes)
            ticker = client.get_24h_ticker(coin)
            volume = float(ticker.get("quoteVolume", 0))
        except Exception as e:
            continue

        in_uptrend = price > sma50
        oversold = rsi14 < dca["rsi_oversold"]
        has_volume = volume > filters["min_volume_usdt"]
        near_bb_lower = bb_low > 0 and price <= bb_low * 1.03  # Within 3% of BB lower
        macd_bullish = macd_hist > 0  # MACD histogram positive
        holding = coin in paper.positions
        pnl_pct = ((price - paper.positions[coin]["avg_price"]) / paper.positions[coin]["avg_price"] * 100) if holding else 0

        use_trend = filters.get("use_trend_filter", False)
        
        coin_weight = get_coin_weight(coin)
        
        # Display
        rsi_color = "🟢" if rsi14 < 30 else ("🟡" if rsi14 < 50 else "🔴")
        bb_icon = "🟢" if near_bb_lower else ("🟡" if price < bb_mid else "🔴")
        macd_icon = "🟢" if macd_bullish else "🔴"
        wt = f"×{coin_weight:.1f}" if coin_weight != 1.0 else ""
        print(f"  {coin:>5}: RSI={rsi14:5.1f} {rsi_color} | BB={bb_icon} | MACD={macd_icon} | Wt{wt:>5} | Vol=${volume:>12,.0f}")

        # Signal scoring: combine RSI + Bollinger + MACD + Volume
        buy_signal = oversold and has_volume and not holding and coin not in blocked_coins
        if use_trend:
            buy_signal = buy_signal and in_uptrend
        
        if buy_signal:
            # Score: base on RSI depth, bonus for BB + MACD
            score = (50 - rsi14) * 2  # Lower RSI = higher score
            if near_bb_lower:
                score += 30  # Major bonus: near BB lower band
            if macd_bullish:
                score += 20  # Bonus: positive momentum
            if in_uptrend:
                score += 10  # Small bonus: above MA50
            
            signals.append({
                "coin": coin,
                "price": price,
                "rsi": rsi14,
                "score": round(score, 1),
            })

            print(f"    → BUY signal! Score={score:.0f} | RSI={rsi14:.1f} | BB={'near lower' if near_bb_lower else 'mid' } | MACD={'bullish' if macd_bullish else 'bearly'}")

    # 3. Check TP/SL for existing positions
    print(f"\n🔍 Checking positions...")
    if paper.positions:
        for coin, pos in paper.positions.items():
            price = prices.get(coin, 0)
            if price > 0:
                pnl = ((price - pos["avg_price"]) / pos["avg_price"]) * 100
                print(f"  {coin:>5}: {pos['qty']:>8.4f} @ avg ${pos['avg_price']:>8.2f} → ${price:>8.2f} ({pnl:+.2f}%)")
    else:
        print(f"  No open positions.")

    sold = paper.check_tp_sl(prices)
    if sold:
        print(f"\n💰 Sold: {', '.join(sold)}")

    # 4. Find new buys (DCA)
    signals.sort(key=lambda x: -x["score"])
    max_new = min(len(signals), dca["max_positions"] - len(paper.positions))
    default_daily_budget = dca["max_spend_per_day"]
    current_total_value = paper.total_value(prices)
    remaining_budget = get_available_budget(current_total_value, default_daily_budget, target_capital)
    executed_buys = []

    if manager_paused_buys:
        print(f"\n🛒 Manager risk guard — buys skipped.")
    elif skip_buys:
        print(f"\n🛒 Fear & Greed too high — buys skipped.")
    elif signals and max_new > 0 and remaining_budget > 5:
        print(f"\n🛒 Buy signals (top {max_new}):")
        for sig in signals[:max_new]:
            coin = sig["coin"]
            weight = get_coin_weight(coin)
            scaled_trade = scale_trade_size(dca["buy_per_trade"], target_capital, paper.initial_balance)
            boosted_cost = scaled_trade * buy_boost * weight
            cost = min(boosted_cost, remaining_budget / max_new)
            if cost < 3:
                break
            print(f"  BUY {coin}: ${cost:.2f} @ ${sig['price']:.4f} (RSI={sig['rsi']:.1f}, wt={weight:.1f}x)")
            if paper.buy(coin, sig["price"], cost):
                executed_buys.append(coin)
                remaining_budget -= cost
    else:
        print(f"\n🛒 No buy signals today.")

    # 5. Portfolio summary
    total_value = paper.total_value(prices)
    pnl_total = total_value - paper.initial_balance
    pnl_pct = (pnl_total / paper.initial_balance) * 100
    invested = paper.initial_balance - paper.usdt
    positions_value = total_value - paper.usdt

    print(f"\n{'='*50}")
    print(f"📋 Portfolio Summary")
    print(f"  Initial balance:   ${paper.initial_balance:>8.2f}")
    print(f"  USDT available:    ${paper.usdt:>8.2f}")
    print(f"  In positions:      ${positions_value:>8.2f}")
    print(f"  Total value:       ${total_value:>8.2f}")
    print(f"  P&L:               ${pnl_total:>+8.2f} ({pnl_pct:+.2f}%)")
    print(f"  Open positions:    {len(paper.positions)}")
    print(f"{'='*50}")

    # Daily loss check
    if paper.daily_pnl < risk["max_daily_loss_pct"] * paper.initial_balance / 100:
        print(f"⚠️  Daily loss limit hit! Bot paused for the day.")

    # Build last run summary
    last_sold = sold if sold else "none"
    last_buys = ", ".join(executed_buys) if executed_buys else "none"
    fng_text = f"{fng}/100" if fng is not None else "N/A"
    
    paper.last_run = {
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "fng": fng_text,
        "fng_emoji": fng_icon if fng is not None else "—",
        "total_value": round(total_value, 2),
        "pnl_pct": round(pnl_pct, 2),
        "positions_count": len(paper.positions),
        "buys": last_buys,
        "sold": ", ".join(sold) if sold else "none",
        "signals_found": len(signals),
        "skip_buys_reason": "F&G too high" if skip_buys else "",
    }
    paper.save()
    if total_value > paper.peak_value:
        paper.peak_value = total_value
    drawdown = (paper.peak_value - total_value) / paper.peak_value * 100
    if drawdown > abs(risk["max_drawdown_pct"]):
        print(f"⚠️  Max drawdown ({risk['max_drawdown_pct']}%) exceeded! Bot paused.")
    print(f"  Drawdown from peak: {drawdown:.2f}%")


if __name__ == "__main__":
    run()
