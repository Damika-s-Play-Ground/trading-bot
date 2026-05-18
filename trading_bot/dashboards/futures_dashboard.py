#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""Futures dashboard — compact risk-first view for the paper futures bot."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from trading_bot.core.state_store import load_json_path
from trading_bot.dashboards.shared_ui import build_bar_chart
from trading_bot.dashboards.spot_dashboard import build_shared_style, nav

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
except Exception:
    pass

margin = 300.0
positions = {}
trade_log = []
peak = 300.0

d = load_json_path(PAPER_FILE, {})
margin = d.get("margin", 300.0)
positions = d.get("positions", {})
trade_log = d.get("trade_log", [])
peak = d.get("peak_value", 300.0)

pos_rows = ""
open_rows = []
pnl_rows = []
risk_rows = []
pos_val_total = 0.0
for coin, pos in positions.items():
    price = prices.get(f"{coin}USDT", 0)
    side = 1 if pos["side"] == "LONG" else -1
    entry = float(pos["entry"])
    liq = float(pos["liq_price"])
    pnl_pct = (price - entry) / entry * side * 100 if price > 0 else 0
    pnl_val = float(pos["margin"]) * (pnl_pct / 100) * 3
    pos_val_total += pnl_val
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
    open_rows.append(
        f"<div class='mini-position'><div class='mini-pos-head'><span>{coin}</span><span>{side_badge}</span></div><div class='mini-bar'><div class='mini-bar-fill' style='width:{min(abs(pnl_pct) * 4, 100):.1f}%;background:{color};'></div></div><div class='mini-pos-meta'><span>PnL {pnl_pct:+.2f}%</span><span>Liq {liq_dist:.1f}%</span></div></div>"
    )
    pnl_rows.append({"label": coin, "value": abs(pnl_pct), "color": color, "meta": f"{pnl_val:+.2f} margin P&L"})
    risk_rows.append({"label": coin, "value": liq_dist, "color": "#22c55e" if liq_dist > 10 else "#eab308" if liq_dist > 5 else "#ef4444", "meta": "distance to liquidation"})

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

total = margin + pos_val_total
pnl = total - 300.0

overall_chart = build_bar_chart(
    pnl_rows,
    title="Position momentum",
    subtitle="Absolute P&L movement by open position",
    value_suffix="%",
)
risk_chart = build_bar_chart(
    risk_rows,
    title="Liquidation buffer",
    subtitle="Distance from liquidation for each open position",
    value_suffix="%",
)
closest_liq_pct = min(
    (
        abs(prices.get(f"{coin}USDT", 0) - float(pos["liq_price"])) / float(pos["entry"]) * 100
        if prices.get(f"{coin}USDT", 0)
        else 0
    )
    for coin, pos in positions.items()
) if positions else 0

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="120">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Futures Dashboard</title>
    <style>
        {build_shared_style('#a855f7')}
        .hero {{ display:grid; grid-template-columns:1.35fr .95fr; gap:16px; margin-bottom:18px; }}
        .hero-card, .card, .panel {{ background:#1e293b; border:1px solid #334155; border-radius:18px; padding:18px; box-shadow:0 12px 30px rgba(15,23,42,.24); }}
        .hero-card h2 {{ font-size:26px; margin-bottom:6px; }}
        .hero-card p {{ color:#94a3b8; line-height:1.65; }}
        .warning-box {{ background:#a855f722; border:1px solid #a855f744; border-radius:16px; padding:14px 16px; margin-top:14px; font-size:13px; line-height:1.6; }}
        .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin-bottom:18px; }}
        .card .label {{ color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:.6px; }}
        .card .value {{ font-size:28px; font-weight:800; margin-top:4px; font-variant-numeric:tabular-nums; }}
        .card .sub {{ color:#94a3b8; font-size:12px; margin-top:4px; }}
        .green {{ color:#22c55e; }} .red {{ color:#ef4444; }} .yellow {{ color:#eab308; }}
        .warning {{ color:#a855f7; }}
        .chart-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:18px; }}
        .section-head {{ display:flex; justify-content:space-between; gap:12px; align-items:center; margin:4px 0 12px; flex-wrap:wrap; }}
        .mini-note {{ color:#94a3b8; font-size:12px; }}
        .mini-positions {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }}
        .mini-position {{ background:#0f172a; border:1px solid #334155; border-radius:14px; padding:12px; }}
        .mini-pos-head {{ display:flex; justify-content:space-between; gap:10px; font-size:12px; margin-bottom:8px; color:#cbd5e1; }}
        .mini-bar {{ height:8px; background:#0b1220; border-radius:999px; overflow:hidden; box-shadow:inset 0 0 0 1px #334155; }}
        .mini-bar-fill {{ height:100%; border-radius:999px; }}
        .mini-pos-meta {{ display:flex; justify-content:space-between; gap:8px; margin-top:7px; color:#64748b; font-size:11px; }}
        table {{ width:100%; border-collapse:collapse; background:#1e293b; border-radius:16px; overflow:hidden; }}
        th,td {{ padding:10px 12px; text-align:left; border-bottom:1px solid #334155; font-size:12px; vertical-align:top; }}
        th {{ background:#334155; color:#94a3b8; font-weight:700; text-transform:uppercase; font-size:10px; letter-spacing:.5px; }}
        .trade-log {{ max-height:320px; overflow-y:auto; background:#1e293b; border:1px solid #334155; border-radius:16px; padding:14px; }}
        .trade-item {{ display:flex; gap:10px; padding:7px 0; font-size:12px; border-bottom:1px solid #33415555; flex-wrap:wrap; }}
        .stats-note {{ color:#64748b; font-size:12px; }}
        @media (max-width: 900px) {{
            .hero {{ grid-template-columns:1fr; }}
            .chart-grid {{ grid-template-columns:1fr; }}
        }}
        @media (max-width: 640px) {{
            .nav a {{ width:100%; text-align:center; }}
        }}
    </style>
</head>
<body>
    <div class="page-shell">
    <div class="page-header">
        <h1>🔵 Futures Paper Trading</h1>
        <p class="subtitle">3x leverage · paper only · risk-first overview of open positions and liquidation buffers</p>
    </div>
    {nav('futures')}

    <div class="hero">
        <div class="hero-card">
            <h2>Know the downside before the upside</h2>
            <p>
                Futures can create outsized gains, but they also turn small market moves into margin pressure fast.
                This page keeps the risk information front and center so you can see liquidation distance and overall
                exposure at a glance.
            </p>
            <div class="warning-box">
                ⚠️ <strong>Risk warning:</strong> at 3x leverage, a roughly -3% market move is already close to a -9% hit
                on margin. The bot is paper only and should stay that way until the strategy is proven.
            </div>
        </div>
        <div class="card">
            <div class="label">Open positions</div>
            <div class="value">{len(positions)}</div>
            <div class="sub">max 3 in the current config</div>
            <div style="margin-top:14px;">{''.join(open_rows) if open_rows else '<div class="empty-box">No open positions</div>'}</div>
        </div>
    </div>

    <div class="grid">
        <div class="card"><div class="label">Total Equity</div>
            <div class="value {'green' if pnl>=0 else 'red'}">${total:.2f}</div>
            <div class="sub">P&L: ${pnl:+.2f}</div></div>
        <div class="card"><div class="label">Free Margin</div>
            <div class="value">${margin:.2f}</div>
            <div class="sub">{margin/300*100:.0f}% available</div></div>
        <div class="card"><div class="label">Trades</div>
            <div class="value">{len(trade_log)}</div>
            <div class="sub">history of opens and closes</div></div>
        <div class="card"><div class="label">Leverage</div>
            <div class="value warning">3x</div>
            <div class="sub">fixed sizing</div></div>
        <div class="card"><div class="label">Drawdown</div>
            <div class="value {'green' if ((peak-total)/peak*100)<5 else 'yellow' if ((peak-total)/peak*100)<10 else 'red'}">{((peak-total)/peak*100):.1f}%</div>
            <div class="sub">from peak ${peak:.2f}</div></div>
        <div class="card"><div class="label">Liquidation buffer</div>
            <div class="value {'green' if len(positions) else 'yellow'}">{closest_liq_pct:.1f}%</div>
            <div class="sub">closest position to liquidation</div></div>
    </div>

    <div class="chart-grid">
        {overall_chart}
        {risk_chart}
    </div>

    <div class="panel">
        <div class="section-head">
            <strong>📊 Open Positions</strong>
            <span class="stats-note">Entry / current / P&L / liquidation distance</span>
        </div>
        <table>
            <tr><th>Coin</th><th>Side</th><th>Entry</th><th>Current</th><th>Margin</th><th>Lev</th><th>P&L%</th><th>P&L $</th><th>To Liq</th></tr>
            {pos_rows if pos_rows else '<tr><td colspan="9" style="text-align:center;color:#64748b;">No open positions</td></tr>'}
        </table>
    </div>

    <div class="panel" style="margin-top:18px;">
        <div class="section-head">
            <strong>📜 Trade History</strong>
            <span class="stats-note">Most recent actions</span>
        </div>
        <div class="trade-log">
            {trade_rows_html}
        </div>
    </div>

    <p class="stats-note" style="margin-top:16px;">Page auto-refreshes every 2 minutes. Prices update when the file regenerates.</p>
    </div>
</body>
</html>"""

with open(OUTPUT, "w") as f:
    f.write(html)

print(f"✅ Futures dashboard generated: {OUTPUT}")
