#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Glossary Page — searchable, bookmarkable technical terms
"""
import json, re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = REPO_ROOT / "glossary.html"


def md_to_html(text):
    """Convert markdown formatting to HTML for glossary content"""
    # Process code blocks first (before bold)
    text = re.sub(r'```\n?(.*?)```', r'<pre><code>\1</code></pre>', text, flags=re.DOTALL)
    # Convert **bold** to <strong>
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Convert single backticks to <code>
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    # Convert | table lines inside pre to keep formatting
    # Convert line breaks
    text = text.replace('\n', '<br>')
    # Clean up double br
    text = text.replace('<br><br>', '</p><p>')
    # Wrap in paragraph
    return f'<p>{text}</p>'

glossary = [
    ("RSI (Relative Strength Index)", "indicators", """
**RSI** measures how oversold or overbought a coin is on a scale of 0-100.

**Formula:** RSI = 100 - [100 / (1 + avg_gain/avg_loss)] over 14 periods

**How to read it:**
```
RSI 0-30   → 🔥 Oversold (people panic selling)  → BUY signal
RSI 30-50  → 🟡 Bearish (sellers in control)
RSI 50-70  → 🟡 Bullish (buyers in control)
RSI 70-100 → 🔥 Overbought (people euphoric)     → SELL signal
```

**Text diagram of how RSI works:**
```
Price:  $10 → $9 → $8 → $7 → $8 → $9 → $10 → $11 → $12
Change:   -1   -1   -1   +1   +1   +1    +1    +1
         ↘    ↘    ↘    ↗    ↗    ↗    ↗    ↗
         
Losses: 3 periods, total -3 → avg loss = 1.0
Gains:  5 periods, total +5 → avg gain = 1.0
RSI = 100 - [100 / (1 + 1.0/1.0)] = 100 - 50 = 50 (neutral)
```

**In our bot:** We buy when RSI < 30 (coin is oversold, expected to bounce).
"""),

    ("MACD (Moving Average Convergence Divergence)", "indicators", """
**MACD** measures momentum — whether buying or selling pressure is increasing.

**Components:**
```
MACD Line = 12-period EMA - 26-period EMA
Signal Line = 9-period EMA of MACD Line
Histogram = MACD Line - Signal Line
```

**How to read it:**
```
MACD Histogram > 0  → 🟢 Bullish momentum (buyers winning)
MACD Histogram < 0  → 🔴 Bearish momentum (sellers winning)
```

**Visual:**
```
     MACD Line crossing ABOVE Signal Line = BUY signal
     MACD Line crossing BELOW Signal Line  = SELL signal
     
     🟢 Histogram bars growing = momentum accelerating
     🔴 Histogram bars shrinking = momentum dying
```

**In our bot:** We give a +20 score bonus if MACD histogram > 0 (bullish momentum backing up the oversold bounce).
"""),

    ("Bollinger Bands", "indicators", """
**Bollinger Bands** show a price range where a coin normally trades.

**Components:**
```
Middle Band = 20-period SMA (average price)
Upper Band  = Middle + 2 standard deviations (expensive)
Lower Band  = Middle - 2 standard deviations (cheap)
```

**How to read it:**
```
Price hits UPPER band → Coin is "expensive" → Might drop
Price hits LOWER band → Coin is "cheap"      → Might bounce
```

**Text diagram:**
```
        Upper Band ──── $12 ──── ⋯⋯⋯⋯⋯⋯
                          │          ↗
        Middle Band ──── $10 ──── Buy here ✓
                          │    ↗
        Lower Band ────── $8 ──── ⋯⋯⋯⋯
```

**In our bot:** We give a +30 score bonus if price is within 3% of the lower band (coin is unusually cheap).
"""),

    ("Stop Loss", "risk", """
**Stop Loss** is an automatic sell order that triggers when price drops by a set percentage. It's your safety net.

**Example:**
```
Buy LINK at $10.00
Set stop loss at -10% → $9.00

If price drops to $9.00:
   → Bot AUTOMATICALLY sells all LINK
   → Loss locked at -10%
   → You don't lose -20%, -30%, or -50%
```

**What happens WITHOUT a stop loss (your old strategy):**
```
Buy OP at $0.30
Price drops to $0.15 → You lost -50% (no stop loss set)
= This is what happened to your OP position
```

**In our bot:** Stop loss at -10% from buy price. Always cuts losers before they bleed.
"""),

    ("Take Profit", "risk", """
**Take Profit** is an automatic sell order that triggers when price rises by a set percentage. It locks in gains.

**Our bot uses TWO TIERS:**
```
Tier 1: +8% → SELL 50% of position (lock half the profit)
Tier 2: +15% → SELL remaining 50% (let winners run)
```

**Example:**
```
Buy AVAX at $9.26
   ↗ $10.00 (+8%) → SELL half, lock profit ✓
   ↗ $10.65 (+15%) → SELL rest, full profit ✓
OR
   ↗ $9.63 → drops back to $9.00 → still have the half we kept
```

**Why tiered?**
- Selling 100% at +8% misses bigger moves
- Not selling at all lets gains evaporate (your old problem)
- 50/50 at 8%/15% is the sweet spot from our backtests
"""),

    ("Trailing Stop", "risk", """
**Trailing Stop** follows the price up and sells if it drops 2% from the highest point. It captures breakouts.

**How it works:**
```
Activation:  +4% profit (starts tracking)
Trail distance: 2% below peak

Example: Buy at $10.00
  $10.40  → Trailing activates (+4%)
  $10.80  → New peak (trail rises to $10.58)
  $11.00  → New peak (trail rises to $10.78)
  $10.70  → Price drops below trail!
         → SELL triggered at $10.78
         → Locked profit: +7.8%
```

**Text diagram:**
```
$11.00 ─── Peak ●
                │  ↘
$10.78 ──────── Trail ─── ❌ SELL here
                │
$10.00 ─── Buy entry
```

**In our bot:** Activates at +4%, trails 2% below peak. Ensures we catch big moves without giving back gains.
"""),

    ("Fear & Greed Index", "market", """
**Fear & Greed Index** measures overall market sentiment from 0 (extreme fear) to 100 (extreme greed).

**How it's calculated:**
| Factor | Weight | What It Measures |
|--------|:------:|------------------|
| Volatility | 25% | Price swings |
| Momentum | 25% | Position vs 50-day MA |
| Social Media | 15% | X/Twitter sentiment |
| Surveys | 15% | Polls |
| BTC Dominance | 10% | Flight to safety |
| Google Trends | 10% | Search volume |

**How to read it:**
```
 0-25  Extreme Fear   → 🟢 BEST TIME TO BUY (everyone panicking)
25-45  Fear           → 🟡 Good to buy
45-55  Neutral        → 🟡 Normal
55-75  Greed          → 🔴 Be careful
75-100 Extreme Greed  → 🔴🔴 DANGER (everyone euphoric = peak)
```

**In our bot:** 
- Skips buys if F&G > 70 (too greedy, likely near top)
- Boosts buy amount by 1.5x if F&G < 25 (extreme fear = opportunity)
"""),

    ("Volume", "market", """
**Volume** = Total USDT traded in the last 24 hours. It measures how liquid a coin is.

**Why it matters:**
```
High volume ($1M+)  → Easy to buy/sell, tight spreads
Low volume ($1K-)   → Hard to sell, wide spreads, price manipulation
No volume ($0)      → Dead coin, can't sell at all
```

**In our bot:** We skip coins with 24h volume < $1,000. Low-volume coins often have fake price moves that don't mean anything.
"""),

    ("Correlation", "portfolio", """
**Correlation** measures how similarly two assets move. Scale: -1 to +1.

```
+1.0 → Perfectly correlated (BTC & ETH: 0.98)
 0.0 → No correlation
-1.0 → Perfectly inverse
```

**Our portfolio's correlation matrix:**
```
    BTC  ETH  SOL  BNB  XRP  
BTC  1.0  0.98 0.96 0.95 0.94  ← ALL strongly correlated!
ETH  0.98 1.0  0.97 0.97 0.96
SOL  0.96 0.97 1.0  0.99 0.98
```

**What this means:**
- Holding 21 coins does NOT diversify risk
- When BTC drops 5%, everything drops ~4-5%
- True diversification = different ASSET CLASSES (crypto + stocks + bonds)
"""),

    ("Drawdown", "risk", """
**Drawdown** = How far your portfolio has fallen from its highest point.

```
Portfolio peak: $1,200
Current value:  $1,020
Drawdown:       -15%
```

**How we use it:**
```
Drawdown 0-5%    → 🟢 Normal
Drawdown 5-10%   → 🟡 Warning
Drawdown 10-15%  → 🟠 Caution
Drawdown > 15%   → 🔴 BOT PAUSES (circuit breaker)
```

**In our bot:** If drawdown exceeds 15% from peak, the bot stops trading until you review it. Prevents a bad month from becoming catastrophic.
"""),

    ("Circuit Breaker", "risk", """
**Circuit Breaker** is an automatic pause that stops the bot when risk limits are hit.

**Our bot has two circuit breakers:**

```
1. MAX DAILY LOSS: -3% of portfolio
   If today's loss > $36 (3% of $1,200) → Bot stops for the day

2. MAX DRAWDOWN: -15% from peak
   If portfolio drops 15% from highest value → Bot stops until reviewed
```

**Why they matter:**
```
Without circuit breaker:
  Bad day: -5%
  Next day: -8%  
  Next week: -20%
  → Portfolio destroyed before you notice

With circuit breaker:
  Bad day: -3% → BOT STOPS
  → You check what happened
  → Fix the issue
  → Resume trading
```
"""),

    ("Market Order vs Limit Order", "trading", """
**Market Order:** Buy/sell immediately at the best available price.

```
Example: "Buy $5 of LINK at market"
→ Instant execution, price paid = $9.65 (whatever it is)
→ Pro: Guaranteed to fill
→ Con: Can get bad price during volatility (slippage)
```

**Limit Order:** Buy/sell only at a specific price or better.

```
Example: "Buy $5 of LINK at $9.50 limit"
→ Only executes if price drops to $9.50
→ Pro: You control the price
→ Con: May never fill if price doesn't reach $9.50
```

**Our bot uses MARKET orders.** For a $5 trade, the difference between market and limit is a few cents — not worth missing the trade.
"""),

    ("Slippage", "trading", """
**Slippage** = The difference between the price you expect and the price you actually get.

```
Example: You want to buy at $10.00
Your order hits → price moves to $10.02
Slippage = $0.02 (0.2%)
```

**When slippage matters:**
```
Low volume coin ($1K/day) → Slippage can be 5-10% ❌
High volume coin (BTC)    → Slippage ~0.01% ✅
```

**In our bot:** We skip low-volume coins (< $1,000) specifically to avoid slippage.
"""),

    ("Leverage & Futures", "trading", """
**Spot trading:** You buy actual coins. You can't lose more than you put in.
**Futures trading:** You trade contracts with leverage. You CAN lose more than you put in.

```
Spot:    $100 buys $100 worth of BTC → Max loss: $100
Futures: $100 with 10x leverage → Controls $1,000 of BTC
         If BTC drops 10% → You lose $100 (entire deposit)
         This is called LIQUIDATION
```

**Why futures are dangerous:**
```
You deposit $100, 10x leverage on BTC
BTC drops 10% → You lose $100 → Position liquidated to $0
BTC drops 15% → You owe BINANCE money (negative balance)
```

**In our bot:** We use SPOT only. No leverage. Your max loss per trade is the -10% stop loss.
"""),

    ("Candlestick", "basics", """
**Candlestick** = A single bar showing price action over a time period (1 hour, 1 day, etc).

```
Each candle shows 4 prices:
           High ──── ┐
                      │
    Close ── ──┬── ──┤  (if close > open = 🟢 green candle)
              │     │
    Open ── ──┘     │
                    │
           Low ──── ┘
```

**Our bot uses 1-hour candles.** 100 candles = ~4 days of data. This is enough for reliable RSI (needs 14 periods) and MACD (needs 26 periods).

**Why not 5-minute candles?** Too much noise. 1-hour candles smooth out random price bounces and show real trends.
"""),

    ("EMA vs SMA", "indicators", """
**SMA (Simple Moving Average):** Average price over N periods, equal weight.

```
SMA(5) of [10, 11, 12, 13, 14] = (10+11+12+13+14)/5 = 12
```

**EMA (Exponential Moving Average):** Same thing but gives MORE weight to RECENT prices.

```
EMA(5) = Most recent price matters MORE than older ones
→ Reacts faster to new information
→ Used in MACD calculation
```

**In our bot:** We use SMA for the trend filter (50-period), EMA for MACD calculation (12 and 26 period).
"""),

    ("Alpha & Beta", "performance", """
**Alpha:** Your return ABOVE what the market did. Positive alpha = you're beating the market.

```
Market (BTC) returned: -15% over 6 months
Your bot returned:     +17% over 6 months
Your ALPHA:           +32% ← You beat the market by 32%
```

**Beta:** How much your portfolio moves compared to the market.

```
Beta = 1.0  → Portfolio moves exactly with BTC
Beta = 1.5  → When BTC rises 10%, you rise 15%
Beta = 0.5  → When BTC drops 10%, you only drop 5%
```

**Your old strategy (DCA + HODL):** Beta ≈ 1.0 (you went down with the market).
**Your bot (RSI + TP/SL):** Generates POSITIVE ALPHA by buying dips and taking profits.
"""),

    ("Backtest", "basics", """
**Backtest** = Running your strategy on PAST data to see how it would have performed.

```
You program your bot rules:
  "Buy when RSI < 30, sell at +8%"

The backtest takes 6 months of REAL price data
  And simulates: "What would have happened?"

Result: +$207 profit, 65% win rate over 207 trades
```

**Why backtests matter:**
```
Without backtest:    You're guessing if the strategy works
With backtest:       You have data showing it works
                     You know the win rate (65%)
                     You know the max drawdown (-8%)
                     You know what to expect
```

**Our backtest results:** +$207 on $1,200 (17%) over 6 months, 65% win rate, across 21 coins.
"""),

    ("Win Rate", "performance", """
**Win Rate** = What percentage of your trades end in profit.

```
100 trades:
  65 were profitable (+8% each)
  35 were losses (-10% each)
  Win Rate = 65%
```

**The truth about win rates:**
```
High win rate (80%+) → Usually tiny profits per trade → Low overall return
Low win rate (40%)   → Usually big winners, many small losses → Trend following

Sweet spot (55-65%)  → Good balance → What our bot achieves
```

**Example showing win rate alone is misleading:**
```
Strategy A: 90% win rate, +1% each win, -10% each loss
  90 × +1% = +90%
  10 × -10% = -100%
  Net = -10% ← LOSING strategy despite 90% win rate!

Strategy B: 40% win rate, +15% each win, -5% each loss
  40 × +15% = +600%
  60 × -5% = -300%
  Net = +300% ← WINNING strategy despite 40% win rate!
```

**Our bot:** 65% win rate with +8% wins / -10% losses. Net = positive.
"""),

    ("Sharpe Ratio", "performance", """
**Sharpe Ratio** = How much return you get for the RISK you take.

```
Sharpe = 0.5 → Okay, moderate risk-adjusted return
Sharpe = 1.0 → Good, you're being paid for the risk
Sharpe = 2.0 → Great, excellent risk-adjusted return
Sharpe = 3.0+ → Outstanding (rare, usually overfitting)
```

**Simple way to think about it:**
```
Strategy A: +20% return, but dropped -25% along the way → Low Sharpe
Strategy B: +15% return, dropped only -5% along the way → High Sharpe
  
Both made money, but B did it smoother = BETTER
```

**Our bot's Sharpe:** From our backtest, the Sharpe was positive — meaning the bot generates returns above what you'd expect from the risk level.
"""),

    ("Liquidity", "market", """
**Liquidity** = How easily you can buy or sell without moving the price.

```
High Liquidity (BTC, ETH):
  Buy $1,000 → Price barely moves
  Can sell instantly at fair price

Low Liquidity (small altcoins):
  Buy $100 → Price jumps 2% (you overpaid)
  Try to sell → No buyers, stuck in position
```

**In our bot:** We skip coins with 24h volume < $1,000. These are illiquid and dangerous to trade.
"""),

    ("DCA (Dollar Cost Averaging)", "strategy", """
**DCA** = Buying fixed amounts at regular intervals regardless of price.

```
Traditional DCA: Buy $10 of BTC every day
  ┌─────────┬──────────┬──────────┐
  │  Day    │  Price   │  Buy $10 │
  ├─────────┼──────────┼──────────┤
  │ Mon     │ $100     │ 0.1 BTC  │
  │ Tue     │ $90      │ 0.111 BTC│ ← More BTC when cheap
  │ Wed     │ $110     │ 0.09 BTC │ ← Less BTC when expensive
  └─────────┴──────────┴──────────┘
```

**The problem with dumb DCA (your old strategy):**
- Buys EVERY day regardless of price
- Buys at the top just as eagerly as at the bottom
- Never sells → gains evaporate

**Our bot's SMART DCA:**
- Only buys when RSI < 30 (oversold = cheap)
- Sells at +8% / +15% (locks in profits)
- Has stop loss at -10% (cuts losers)
- Result: +$207 vs -$989 (dumb DCA loses money!)
"""),

    ("Grid Trading", "strategy", """
**Grid Trading** = Place multiple buy and sell orders at different price levels, profiting from every bounce.

```
Example: BTC $100 range, $10 intervals

  SELL ORDERS:           If price hits $110 → sell ✓
                          If price hits $105 → sell ✓
  CURRENT:    $100       
  BUY ORDERS:            If price hits $95 → buy ✓
                          If price hits $90 → buy ✓
```

**Each bounce = profit:**
```
BTC drops $100 → $95 (buy)
BTC recovers $95 → $100 (sell)
Profit: $5 minus fees = ~$4.95
Repeat 10 times = ~$50 (5% return)
```

**Best for:** Sideways/ranging markets (our current market).
**Worst for:** Strong trends (all orders get eaten in one direction).
"""),

    ("Liquidation", "risk", """
**Liquidation** = When a futures exchange forcefully closes your position because you ran out of margin.

```
You deposit $100, use 10x leverage → controlling $1,000
BTC drops 10% → Your $1,000 position loses $100
→ Your $100 deposit is GONE
→ Exchange closes (liquidates) your position
→ You have $0 left
```

**LIQUIDATION IS WHY LEVERAGE IS DANGEROUS**

```
Without leverage: 100% of your investment at risk
With 10x leverage: 1,000% of your investment at risk → can lose more than deposited
With 50x leverage: 5,000% of your investment at risk → one bad trade = bankruptcy
```

**In our bot:** We use **SPOT only**. No leverage, no liquidation risk. Max loss = -10% per trade (stop loss).
"""),

    ("ATH / ATL", "basics", """
**ATH** = All-Time High (highest price ever)
**ATL** = All-Time Low (lowest price ever)

```
Example: BTC
  ATH: $109,000 (Jan 2025)
  ATL: $0.003 (2010)
  Current: $79,000
  
  Distance from ATH: -27% (still below all-time high)
```

**Why this matters for your bot:**
- Buying near ATH is risky (room to fall)
- Buying near ATL is great (room to grow)
- Our bot buys on RSI < 30, which often happens when prices are far from ATH
"""),

    ("Impermanent Loss", "risk", """
**Impermanent Loss** = A loss you can experience when providing liquidity to a trading pair, if one coin moves more than the other.

```
Example: You deposit $100 USDT + $100 worth of LINK into a pool
  
Case 1: LINK price stays flat → You earn fees, no loss ✓
Case 2: LINK price DOUBLES → You end up with less LINK, more USDT
        Your total is worth MORE, but LESS than if you just held
  
Case 3: LINK price HALVES → You end up with more LINK, less USDT  
        Your total is worth LESS, AND you lost more than holding
```

**Why it's called "impermanent":** The loss only becomes permanent if you withdraw while the price is different. If the price returns to where it started, the loss disappears and you just keep the fees.

**In our bot:** We don't use liquidity pools — we just spot trade. So no impermanent loss risk.
"""),

    ("Yield Farming", "defi", """
**Yield Farming** = Moving your crypto between DeFi protocols to chase the highest interest rates.

```
Your $1,200 in Binance Earn: earning ~3-5% APY
Move to Aave lending:       earning ~5-8% APY
Move to Compound:           earning ~6-10% APY
Move to Uniswap LP:         earning ~15-50% APY (but risky)
```

**Risk ladder:**
```
Binance Earn (3-5%)     → Lowest risk ✅ (you're here)
Aave/Compound (5-10%)   → Low risk
Liquidity Pools (10-30%) → Medium risk
New protocol "farms"     → High risk (many are scams)
```

**What we could do:** Have Hermes check the best APY across protocols every day and move funds automatically. 5% → 10% APY doubles your passive income.
"""),

    ("Testnet", "basics", """
**Testnet** = A simulated environment that mirrors the real blockchain but uses fake money.

```
Testnet vs Mainnet:
             Testnet              Mainnet (Real)
  ┌─────────────────────┐  ┌─────────────────────┐
  │  Fake money         │  │  YOUR real money    │
  │  Same prices        │  │  Same prices        │
  │  No fees (usually)  │  │  0.1% per trade     │
  │  Unlimited liquidity │  │  Real liquidity     │
  │  Safe to learn      │  │  Risk of loss       │
  └─────────────────────┘  └─────────────────────┘
```

**Our bots** are running on Binance Testnet. Prices are real, but trades use fake money. When we go to Mainnet, we add fees and slippage calculations.
"""),

    ("Mainnet", "basics", """
**Mainnet** = The real blockchain where real money trades.

When you move from testnet to mainnet:
1. **0.1% fee** per trade → reduces profit by 0.2% round-trip
2. **Slippage** — your order may fill at a worse price
3. **Real P&L** — wins and losses are actual money

**Our plan:** Test on testnet for 2 weeks with fees enabled, then migrate to mainnet with small amounts first ($50).
"""),

    ("Funding Rate", "trading", """
**Funding Rate** = A periodic payment between long and short traders in perpetual futures contracts.

```
When funding is POSITIVE:
  → More people are LONG (betting price goes up)
  → LONGS pay SHORTS every 8 hours
  → Bullish signal (but expensive to hold longs)

When funding is NEGATIVE:
  → More people are SHORT (betting price goes down)
  → SHORTS pay LONGS every 8 hours
  → Bearish signal (but profitable to hold shorts)
```

**In our bots:** We don't use futures yet, but funding rates are a great sentiment indicator. Negative funding = fear = good time to DCA buy.
"""),

    ("Polymarket", "market", """
**Polymarket** = A decentralized prediction market where you bet on real-world events.

```
Example: "Will BTC be above $100K on June 1?"
  Current odds: "Yes" = 35¢, "No" = 65¢
  Market says: 35% chance of BTC > $100K
  
If you agree → Buy "Yes"
If BTC hits $100K → Each share pays $1 (+185% return)
If BTC stays below → Shares go to $0 (-100% loss)
```

**How it helps our bots:**
- Polymarket odds = crowd-sourced market sentiment
- People put REAL MONEY behind their predictions
- Can use as a signal: if Polymarket says 80% bearish → reduce bot position sizes
"""),

    ("Delta Neutral", "strategy", """
**Delta Neutral** = A strategy where you hold offsetting positions so your net exposure is zero.

```
Example:
  You buy $100 of BTC (LONG) in spot
  You sell $100 of BTC (SHORT) in futures
  
  BTC goes UP $10:
    Spot: +$10 profit
    Futures: -$10 loss
    NET: $0 (neutral!)
    
  BTC goes DOWN $10:
    Spot: -$10 loss
    Futures: +$10 profit
    NET: $0 (neutral!)
```

**Why do it?** If prices don't move (neutral), you can collect funding payments without worrying about direction. Advanced market makers use this.
"""),

    ("Paper Trading", "basics", """
**Paper Trading** = Trading with fake money using real market data. Also called "simulated trading."

```
Paper Trading (what we do now):
  ✅ Real prices from Binance
  ✅ Real order logic (RSI, MACD, SL, TP)
  ❌ Fake money (no risk)
  ❌ May not account for slippage/fees

Live Trading (next step):
  ✅ Same logic
  ✅ Real money
  ✅ Real fees deducted
  ✅ Real slippage
```

**Why paper trade first:** We can test our strategy, find bugs, and optimize parameters without losing real money. We've been paper trading since the start.
"""),

    ("API Rate Limit", "basics", """
**API Rate Limit** = How many requests you can make to an exchange per minute/hour.

```
Binance rate limits:
  1,200 requests per minute (weight-based)
  Most requests cost 1-10 "weight"
  
  Our bot makes per run:
    21 coins × 1 price call = 21 weight
    21 coins × 1 klines call = 21 weight  
    21 coins × 1 ticker call = 21 weight
    1 Fear & Greed call = 0 weight
    Total: ~63 weight / 1,200 = fine ✓
```

**If we increase to every 5 min:** Still fine at 63 weight per run (only 5% of limit).
"""),

    ("OHLCV", "basics", """
**OHLCV** = Open, High, Low, Close, Volume — the five data points in every candlestick.

```
Each candle stores:
  O = Open (price at start of hour)
  H = High (highest price during hour)
  L = Low (lowest price during hour)
  C = Close (price at end of hour)
  V = Volume (how much was traded)
```

**Our bot uses:** Close prices for RSI/MACD calculations, Volume for volume filter, High/Low for trailing stop checks.
"""),

    ("Order Book", "trading", """
**Order Book** = A list of all buy and sell orders waiting to be filled on an exchange.

```
BUYERS (Bids)          SELLERS (Asks)
                    ┌──
                    │ Sell 1 BTC @ $10.05
                    │ Sell 1 BTC @ $10.03
                    │ Sell 1 BTC @ $10.01
  ── Current price ── $10.00 ──────────
  Buy 1 BTC @ $9.99 │
  Buy 1 BTC @ $9.97 │
  Buy 1 BTC @ $9.95 │
                    └──
```

**Bid-Ask Spread:** The gap between the highest buy and lowest sell order. Tight spread = liquid market.
"""),

    ("Spread", "trading", """
**Spread** = The difference between the best buy price (bid) and best sell price (ask).

```
BTC/USDT:
  Best bid: $78,900 (someone wants to BUY at this price)
  Best ask: $79,000 (someone wants to SELL at this price)
  Spread:   $100 (0.13%)
```

**Tight spread** ($0.01) = Liquid market, easy to trade.
**Wide spread** ($1.00) = Illiquid market, harder to trade.

**In our bots:** We skip coins with volume < $1k because they likely have wide spreads that eat into profits.
"""),

    ("Hedging", "strategy", """
**Hedging** = Opening an offsetting position to reduce risk.

```
Example: You hold $1,000 of BTC
  You're worried BTC might drop
  You short $500 of BTC futures
  
  If BTC drops 10%:
    Spot: -$100 loss
    Futures: +$50 gain (on the $500 short)
    Net loss: -$50 (instead of -$100)
    
  The hedge REDUCED your loss by 50%
```

**In our bots:** We don't hedge yet. The futures bot cluster would enable this — automatically shorting when DCA bot opens a long position.
"""),

    ("Market Regime", "market", """
**Market Regime** = The current personality of the market.

```
Common regimes:
  📈 Bull      → trend is climbing, breakouts work better
  📉 Bear      → trend is falling, defense matters more
  ➡️ Sideways  → price chops in a range, mean reversion works better
  ⚡ Volatile  → fast swings, position sizing should stay tighter
```

**Why it matters:** The same strategy can work great in one regime and poorly in another.

**In our dashboard:** The top card labels the detected regime so you can interpret every trade and chart with the right context.
"""),

    ("Equity Curve", "performance", """
**Equity Curve** = A line showing how total portfolio value changes over time.

```
Time 1  → $1,200
Time 2  → $1,208
Time 3  → $1,196
Time 4  → $1,214

Plot those points → you get the equity curve
```

**How to read it:**
- Rising smoothly = steady compounding
- Flat = little edge or little exposure
- Sharp drops = drawdown / risk events
- Choppy = unstable strategy behavior

**In our dashboard:** The equity curve helps you judge the quality of the bot's progress, not just the latest portfolio number.
"""),

    ("Performance Journal", "performance", """
**Performance Journal** = The time-stamped history of portfolio totals and snapshots used to build trend charts like the equity curve.

```
08:00 → $1,198
12:00 → $1,204
16:00 → $1,201
20:00 → $1,214
```

**Why it matters:** Without a journal, you only see today's number. With it, you can see whether growth is smooth, noisy, or fading.

**In our dashboard:** The equity curve reads from this journal so hover states, highs/lows, and recent direction all have historical context.
"""),

    ("Capital Allocation", "portfolio", """
**Capital Allocation** = How you split total capital across strategies, bots, or assets.

```
Example with $1,200:
  DCA + TP         20% → $240
  Trend Following  10% → $120
  Grid Trading     20% → $240
  Momentum         15% → $180
  Deep MR          35% → $420
```

**Why it matters:** Allocation controls exposure before any trade even happens.

**In our dashboard:** The allocation chart and capital allocation section show where the portfolio is intentionally supposed to sit versus where it actually sits.
"""),

    ("Portfolio Contribution", "portfolio", """
**Portfolio Contribution** = How much one coin, bot, or strategy adds to the total portfolio value.

```
If total portfolio = $1,200
and AVAX position = $36

Contribution = $36 / $1,200 = 3.0%
```

**Two useful views:**
- **Amount contribution** → the dollar value it contributes
- **Percentage contribution** → the share of the total portfolio

**In our dashboard:** Each bot section now shows both the amount and percentage each coin contributes to the total portfolio.
"""),

    ("Drift", "portfolio", """
**Drift** = The gap between your target allocation and your actual live allocation.

```
Target for bot:  $240
Actual live:     $252

Drift = ($252 - $240) / $240 = +5.0%
```

**Why it matters:** Drift tells you when one strategy is taking up more or less capital than planned.

**In our dashboard:** A small drift is normal. A large drift is a signal to rebalance or inspect why that bot is dominating capital.
"""),

    ("Missed Cadence", "performance", """
**Missed Cadence** = A scheduled job running later than its expected interval.

```
Expected: every 30 minutes
Actual:   last successful run was 48 minutes ago

Missed cadence = 18 minutes late
```

**Why it matters:** A bot can look merely "stale" while actually skipping one or more expected runs. Cadence checks tell you whether automation is slipping.

**In our dashboard:** Cron health now warns when a job runs beyond its normal schedule instead of only showing a stale badge.
"""),

    ("Dashboard Store", "performance", """
**Dashboard Store** = The SQLite-backed data layer that keeps dashboard history, cron logs, research items, and synced TODO state in one place.

```
performance_runs
cron_runs
research_items
todo_items
todo_state_overrides
```

**Why it matters:** It lets the dashboard keep state beyond one browser tab or one localStorage entry.

**In our dashboard:** TODO completion sync now writes into the dashboard store so open/done state survives across sessions and browsers.
"""),
]

# Build HTML
term_cards = ""
for i, (name, category, content) in enumerate(glossary):
    cat_icon = {"indicators":"📈","risk":"🛡️","market":"📊","portfolio":"📦","trading":"💱","basics":"📖","performance":"🎯","strategy":"🧠","defi":"🏦"}.get(category, "📌")
    content_html = md_to_html(content)
    term_cards += f"""
    <div class="term-card" data-id="t{i}" data-category="{category}" data-name="{name.lower()}">
        <div class="term-header" onclick="toggleTerm('t{i}')">
            <span class="term-icon">{cat_icon}</span>
            <span class="term-name">{name}</span>
            <span class="term-cat">{category}</span>
            <span class="term-toggle">▼</span>
            <span class="bookmark-star" onclick="event.stopPropagation();toggleBookmark('t{i}')" id="star-t{i}">☆</span>
        </div>
        <div class="term-body" id="body-t{i}">
            {content_html}
        </div>
    </div>"""

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Glossary</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
               background:#0f172a; color:#e2e8f0; padding:24px; }}
        h1 {{ font-size:24px; margin-bottom:4px; }}
        .subtitle {{ color:#94a3b8; font-size:14px; margin-bottom:24px; }}
        .nav {{ display:flex; gap:12px; margin-bottom:24px; }}
        .nav a {{ padding:8px 16px; border-radius:8px; background:#1e293b; color:#94a3b8;
                 text-decoration:none; font-size:13px; transition:0.2s; }}
        .nav a.active {{ background:#3b82f6; color:white; }}
        .nav a:hover {{ background:#334155; }}
        
        /* Search & Filter */
        .controls {{ display:flex; gap:12px; margin-bottom:20px; flex-wrap:wrap; }}
        .search-box {{ flex:1; min-width:200px; padding:10px 14px; border-radius:8px; border:1px solid #334155;
                      background:#1e293b; color:#e2e8f0; font-size:14px; outline:none; }}
        .search-box:focus {{ border-color:#3b82f6; }}
        .filter-btns {{ display:flex; gap:6px; flex-wrap:wrap; }}
        .filter-btn {{ padding:6px 14px; border-radius:6px; border:1px solid #334155; background:transparent;
                       color:#94a3b8; cursor:pointer; font-size:12px; transition:0.2s; }}
        .filter-btn:hover {{ background:#334155; }}
        .filter-btn.active {{ background:#3b82f6; border-color:#3b82f6; color:white; }}
        
        /* Stats */
        .glossary-stats {{ display:flex; gap:16px; margin-bottom:20px; flex-wrap:wrap; }}
        .gstat {{ background:#1e293b; border-radius:12px; padding:12px 18px; }}
        .gstat .label {{ color:#94a3b8; font-size:11px; text-transform:uppercase; }}
        .gstat .value {{ font-size:18px; font-weight:700; margin-top:2px; }}
        
        /* Term Cards */
        .term-card {{ background:#1e293b; border-radius:12px; margin-bottom:8px; overflow:hidden; }}
        .term-header {{ display:flex; align-items:center; gap:10px; padding:14px 18px;
                        cursor:pointer; transition:0.2s; user-select:none; }}
        .term-header:hover {{ background:#1e3349; }}
        .term-icon {{ font-size:20px; }}
        .term-name {{ flex:1; font-weight:600; font-size:14px; }}
        .term-cat {{ font-size:10px; padding:2px 8px; border-radius:4px; background:#334155; color:#64748b;
                     text-transform:uppercase; }}
        .term-toggle {{ color:#64748b; font-size:12px; transition:0.3s; }}
        .term-card.open .term-toggle {{ transform:rotate(180deg); }}
        .bookmark-star {{ font-size:20px; cursor:pointer; color:#64748b; transition:0.2s; }}
        .bookmark-star.bookmarked {{ color:#eab308; }}
        .term-body {{ display:none; padding:0 18px 18px; font-size:13px; line-height:1.6; color:#cbd5e1; border-top:1px solid #334155; padding-top:14px; }}
        .term-card.open .term-body {{ display:block; }}
        /* Code blocks inside glossary */
        .term-body pre {{ background:#0f172a; border-radius:8px; padding:12px 16px; margin:8px 0; overflow-x:auto; font-size:12px; line-height:1.5; color:#e2e8f0; border:1px solid #1e293b; }}
        .term-body code {{ font-family:'SF Mono','Fira Code','Courier New',monospace; }}
        .term-body pre code {{ background:none; padding:0; }}
        .term-body p code {{ background:#334155; padding:1px 6px; border-radius:4px; font-size:12px; }}
        .term-body strong {{ color:#f1f5f9; }}
        .term-body p {{ margin:6px 0; }}
        
        /* Highlight matches */
        .hl {{ background:#3b82f644; border-radius:2px; padding:0 2px; }}
        
        .no-result {{ color:#64748b; text-align:center; padding:40px; }}
    </style>
    <script>
    // Bookmark state
    function getBookmarks() {{
        try {{ return JSON.parse(localStorage.getItem('glossary_bookmarks') || '[]'); }} catch(e) {{ return []; }}
    }}
    function saveBookmarks(b) {{ localStorage.setItem('glossary_bookmarks', JSON.stringify(b)); }}
    
    function toggleBookmark(id) {{
        const b = getBookmarks();
        const idx = b.indexOf(id);
        if (idx > -1) {{ b.splice(idx,1); }} else {{ b.push(id); }}
        saveBookmarks(b);
        renderBookmarks();
    }}
    
    function renderBookmarks() {{
        const b = getBookmarks();
        document.querySelectorAll('.bookmark-star').forEach(el => {{
            const id = el.id.replace('star-', '');
            el.classList.toggle('bookmarked', b.includes(id));
            el.textContent = b.includes(id) ? '★' : '☆';
        }});
        document.getElementById('bookmark-count').textContent = b.length;
    }}
    
    // Toggle term
    function toggleTerm(id) {{
        const card = document.querySelector('[data-id="'+id+'"]');
        card.classList.toggle('open');
    }}
    
    // Filter & Search
    function filterTerms() {{
        const query = document.getElementById('search-input').value.toLowerCase();
        const category = document.querySelector('.filter-btn.active')?.dataset?.cat || 'all';
        let visible = 0;
        
        document.querySelectorAll('.term-card').forEach(card => {{
            const name = card.dataset.name;
            const cat = card.dataset.category;
            const content = card.textContent.toLowerCase();
            const matchesSearch = !query || name.includes(query) || content.includes(query);
            const matchesCat = category === 'all' || cat === category;
            
            if (matchesSearch && matchesCat) {{
                card.style.display = '';
                visible++;
                // Highlight search matches
                if (query) {{
                    // Reset highlighting - simple version just shows matching cards
                }}
            }} else {{
                card.style.display = 'none';
            }}
        }});
        
        document.getElementById('visible-count').textContent = visible;
    }}
    
    // Auto-open bookmarked on load
    window.addEventListener('DOMContentLoaded', function() {{
        renderBookmarks();
        const b = getBookmarks();
        b.forEach(id => {{
            const card = document.querySelector('[data-id="'+id+'"]');
            if (card) card.classList.add('open');
        }});
        filterTerms();
    }});
    
    // Search on input
    document.addEventListener('DOMContentLoaded', function() {{
        document.getElementById('search-input').addEventListener('input', filterTerms);
    }});
    </script>
</head>
<body>
    <h1>📖 Trading Glossary</h1>
    <p class="subtitle">Technical terms explained with examples, diagrams, and real bot references</p>
    
    <div class="nav">
        <a href="/dashboard">📊 Spot</a>
        <a href="/futures">🔵 Futures</a>
        <a href="/research">🔬 Research</a>
        <a href="/todo">🗒 Todo</a>
        <a href="/cron">⏱ Cron</a>
        <a href="/glossary" class="active">📖 Glossary</a>
    </div>
    
    <div class="glossary-stats">
        <div class="gstat"><div class="label">Terms</div><div class="value">{len(glossary)}</div></div>
        <div class="gstat"><div class="label">Visible</div><div class="value" id="visible-count">{len(glossary)}</div></div>
        <div class="gstat"><div class="label">Bookmarked</div><div class="value" id="bookmark-count">0</div></div>
    </div>
    
    <div class="controls">
        <input type="text" class="search-box" id="search-input" placeholder="🔍 Search terms..." oninput="filterTerms()">
        <div class="filter-btns">
            <button class="filter-btn active" data-cat="all" onclick="document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');filterTerms()">All</button>
            <button class="filter-btn" data-cat="indicators" onclick="document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');filterTerms()">📈 Indicators</button>
            <button class="filter-btn" data-cat="risk" onclick="document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');filterTerms()">🛡️ Risk</button>
            <button class="filter-btn" data-cat="market" onclick="document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');filterTerms()">📊 Market</button>
            <button class="filter-btn" data-cat="portfolio" onclick="document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');filterTerms()">📦 Portfolio</button>
            <button class="filter-btn" data-cat="strategy" onclick="document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');filterTerms()">🧠 Strategy</button>
            <button class="filter-btn" data-cat="trading" onclick="document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');filterTerms()">💱 Trading</button>
            <button class="filter-btn" data-cat="performance" onclick="document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');filterTerms()">🎯 Performance</button>
            <button class="filter-btn" data-cat="basics" onclick="document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');filterTerms()">📖 Basics</button>
        </div>
    </div>
    
    {term_cards}
    
    <p style="color:#64748b;font-size:11px;margin-top:24px;">
        Click any term to expand. Click ★ to bookmark for quick access. Data and examples are based on your actual bot and portfolio.
    </p>
</body>
</html>"""

with open(OUTPUT, "w") as f:
    f.write(html)

print(f"✅ Glossary generated: {OUTPUT} ({len(glossary)} terms)")
