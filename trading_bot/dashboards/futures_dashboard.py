#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Futures Dashboard — separate page for futures paper trading
"""
import json, urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT
OUTPUT = BASE_DIR / "futures.html"
PAPER_FILE = BASE_DIR / "paper_futures.json"

prices = {}
try:
    req = urllib.request.Request("https://api.binance.com/api/v3/ticker/price")
    with urllib.request.urlopen(req, timeout=10) as resp:
        for p in json.loads(resp.read()):
            prices[p["symbol"]] = float(p["price"])
except: pass

margin = 300.0
positions = {}
trade_log = []
peak = 300.0

if PAPER_FILE.exists():
    with open(PAPER_FILE) as f:
        d = json.load(f)
        margin = d.get("margin", 300.0)
        positions = d.get("positions", {})
        trade_log = d.get("trade_log", [])
        peak = d.get("peak_value", 300.0)

# Calculate values
pos_val = 0
pos_rows = ""
for coin, pos in positions.items():
    price = prices.get(f"{coin}USDT", 0)
    side = 1 if pos["side"] == "LONG" else -1
    entry = pos["entry"]
    liq = pos["liq_price"]
    pnl_pct = (price - entry) / entry * side * 100 if price > 0 else 0
    pnl_val = pos["margin"] * (pnl_pct / 100) * 3  # 3x leverage
    pos_val += pnl_val
    liq_dist = abs(price - liq) / entry * 100 if price > 0 else 0
    color = "#22c55e" if pnl_pct >= 0 else "#ef4444"
    side_badge = "🟢 LONG" if pos["side"] == "LONG" else "🔴 SHORT"
    pos_rows += f"""
    <tr>
        <td>{coin}</td>
        <td>{side_badge}</td>
        <td>${entry:.2f}</td>
        <td>${price:.2f}</td>
        <td>${pos['margin']:.2f}</td>
        <td>3x</td>
        <td style="color:{color}">{pnl_pct:+.2f}%</td>
        <td style="color:{color}">${pnl_val:+.2f}</td>
        <td style="color:{'#ef4444' if liq_dist < 5 else '#eab308' if liq_dist < 10 else '#22c55e'}">{liq_dist:.1f}%</td>
    </tr>"""

total = margin + pos_val
pnl = total - 300.0

# Trade log HTML
trade_rows_html = ""
if trade_log:
    for t in trade_log[-30:][::-1]:
        pnl_color = "#22c55e" if t.get("pnl", 0) > 0 else "#ef4444"
        pnl_str = f"${t['pnl']:.2f}" if "pnl" in t else ""
        reason = t.get("reason", "")
        trade_rows_html += f'<div class="trade-item">'
        trade_rows_html += f'<span style="color:{pnl_color}">{t["action"]}</span>'
        trade_rows_html += f'<span>{t["coin"]}</span>'
        trade_rows_html += f'<span>${t.get("price", 0):.2f}</span>'
        trade_rows_html += f'<span style="color:{pnl_color}">{pnl_str}</span>'
        trade_rows_html += f'<span style="color:#64748b;font-size:11px">{reason}</span>'
        trade_rows_html += f'</div>'
else:
    trade_rows_html = '<p style="color:#64748b;text-align:center;">No trades yet</p>'
drawdown = (peak - total) / peak * 100 if peak > 0 else 0
trades_buys = len([t for t in trade_log if "LONG" in t["action"] or "SHORT" in t["action"]])
trades_sells = len([t for t in trade_log if "CLOSE" in t["action"]])
wins = len([t for t in trade_log if t.get("pnl", 0) > 0])

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="120">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Futures Dashboard</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
               background:#0f172a; color:#e2e8f0; padding:24px; }}
        h1 {{ font-size:24px; margin-bottom:4px; }}
        .subtitle {{ color:#94a3b8; font-size:14px; margin-bottom:20px; }}
        .nav {{ display:flex; gap:12px; margin-bottom:24px; }}
        .nav a {{ padding:8px 16px; border-radius:8px; background:#1e293b; color:#94a3b8;
                 text-decoration:none; font-size:13px; }}
        .nav a.active {{ background:#a855f7; color:white; }}
        .nav a:hover {{ background:#334155; }}
        .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin-bottom:24px; }}
        .card {{ background:#1e293b; border-radius:12px; padding:20px; }}
        .card .label {{ color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:0.5px; }}
        .card .value {{ font-size:26px; font-weight:700; margin-top:2px; }}
        .card .sub {{ font-size:12px; margin-top:4px; }}
        .green {{ color:#22c55e; }} .red {{ color:#ef4444; }} .yellow {{ color:#eab308; }}
        .warning {{ color:#a855f7; }}
        h2 {{ font-size:18px; margin:24px 0 12px; }}
        table {{ width:100%; border-collapse:collapse; background:#1e293b; border-radius:12px; overflow:hidden; }}
        th,td {{ padding:10px 14px; text-align:left; border-bottom:1px solid #334155; font-size:13px; }}
        th {{ background:#334155; color:#94a3b8; font-weight:600; text-transform:uppercase; font-size:11px; }}
        .trade-log {{ max-height:300px; overflow-y:auto; background:#1e293b; border-radius:12px; padding:14px; }}
        .trade-item {{ display:flex; gap:10px; padding:4px 0; font-size:12px; border-bottom:1px solid #33415555; }}
        .leverage-warn {{ background:#a855f722; border:1px solid #a855f744; border-radius:8px; padding:12px 16px; margin-bottom:20px; font-size:13px; }}
    </style>
</head>
<body>
    <div class="nav">
        <a href="dashboard.html">📊 Spot</a>
        <a href="futures.html" class="active">🔵 Futures</a>
        <a href="research.html">🔬 Research</a>
        <a href="cron.html">⏱ Cron</a>
        <a href="glossary.html">📖 Glossary</a>
    </div>
    
    <h1>🔵 Futures Paper Trading</h1>
    <p class="subtitle">3x leverage · 3 coin pairs · paper only</p>

    <div class="leverage-warn">
        ⚠️ <strong>Futures risk warning:</strong> Leverage multiplies both gains AND losses. 
        At 3x leverage, a -3% move = -9% to your margin. 
        Liquidation happens at ~33% price move against you.
    </div>

    <div class="grid">
        <div class="card"><div class="label">Total Equity</div>
            <div class="value {'green' if pnl>=0 else 'red'}">${total:.2f}</div>
            <div class="sub">P&L: ${pnl:+.2f}</div></div>
        <div class="card"><div class="label">Free Margin</div>
            <div class="value">${margin:.2f}</div>
            <div class="sub">{margin/300*100:.0f}% available</div></div>
        <div class="card"><div class="label">Open Positions</div>
            <div class="value">{len(positions)}</div>
            <div class="sub">Max: {3}</div></div>
        <div class="card"><div class="label">Trades</div>
            <div class="value">{len(trade_log)}</div>
            <div class="sub">{wins} wins / {trades_sells} closed</div></div>
        <div class="card"><div class="label">Leverage</div>
            <div class="value warning">3x</div>
            <div class="sub">Fixed</div></div>
        <div class="card"><div class="label">Drawdown</div>
            <div class="value {'green' if drawdown<5 else 'yellow' if drawdown<10 else 'red'}">{drawdown:.1f}%</div>
            <div class="sub">From peak: ${peak:.2f}</div></div>
    </div>

    <h2>📊 Open Positions</h2>
    <table>
        <tr><th>Coin</th><th>Side</th><th>Entry</th><th>Current</th><th>Margin</th><th>Lev</th><th>P&L%</th><th>P&L $</th><th>To Liq</th></tr>
        {pos_rows if pos_rows else '<tr><td colspan="9" style="text-align:center;color:#64748b;">No open positions</td></tr>'}
    </table>

    <h2>📜 Trade History</h2>
    <div class="trade-log">
        {trade_rows_html}
    </div>

    <p style="color:#64748b;font-size:11px;margin-top:24px;">
        Page auto-refreshes every 2 minutes. Live prices update on reload.
    </p>
</body>
</html>"""

with open(OUTPUT, "w") as f:
    f.write(html)

print(f"✅ Futures dashboard generated: {OUTPUT}")
