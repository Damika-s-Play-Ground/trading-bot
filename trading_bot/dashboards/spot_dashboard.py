#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Spot + Cron dashboard generator for the multi-bot trading system.
Generates:
- dashboard.html
- cron.html
"""

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = REPO_ROOT
SPOT_OUTPUT = BASE_DIR / "dashboard.html"
CRON_OUTPUT = BASE_DIR / "cron.html"
MANAGER_FILE = BASE_DIR / "manager_state.json"
CRON_LOG_FILE = BASE_DIR / "logs" / "cron.json"
RESEARCH_FILE = Path.home() / "Documents" / "ai-crypto-research.md"

BOT_FILES = [
    {"key": "dca", "name": "DCA + TP", "file": "paper_state.json", "color": "#3b82f6", "icon": "📉"},
    {"key": "trend", "name": "Trend Following", "file": "paper_trend.json", "color": "#22c55e", "icon": "📈"},
    {"key": "grid", "name": "Grid Trading", "file": "paper_grid.json", "color": "#eab308", "icon": "➡️"},
    {"key": "momentum", "name": "Momentum", "file": "paper_momentum.json", "color": "#a855f7", "icon": "🚀"},
    {"key": "deep_mr", "name": "Deep MR", "file": "paper_deepmr.json", "color": "#ef4444", "icon": "⚡"},
]

REGIME_ICONS = {
    "bull": "📈 BULL",
    "bear": "📉 BEAR",
    "sideways": "➡️ SIDEWAYS",
    "volatile": "⚡ VOLATILE",
}

CRON_JOBS = {
    "trading-bot": {
        "job_id": "60d9a438c1ec",
        "name": "Trading Bot",
        "schedule": "every 30m",
        "details": "manager + futures + dashboards",
        "deliver": "local",
        "script": "~/.hermes/scripts/trading-bot-run.sh",
        "mode": "script-only (no_agent)",
    },
    "research-scraper": {
        "job_id": "05738e66e59b",
        "name": "Research Scraper",
        "schedule": "every 5m",
        "details": "social + web research",
        "deliver": "local",
        "script": "~/.hermes/scripts/ai-crypto-research-scraper.py",
        "mode": "script-only (no_agent)",
    },
}


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def fetch_prices():
    prices = {}
    try:
        req = urllib.request.Request("https://api.binance.com/api/v3/ticker/price")
        with urllib.request.urlopen(req, timeout=10) as resp:
            for item in json.loads(resp.read()):
                prices[item["symbol"]] = float(item["price"])
    except Exception:
        pass
    return prices


def parse_time(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except Exception:
        return None


def fmt_money(value):
    return f"${value:,.2f}"


def fmt_pct(value):
    return f"{value:+.2f}%"


def age_label(dt):
    if not dt:
        return "unknown"
    age_sec = max(0, int(time.time() - dt.timestamp()))
    if age_sec < 60:
        return f"{age_sec}s ago"
    if age_sec < 3600:
        return f"{age_sec // 60}m ago"
    return f"{age_sec // 3600}h {((age_sec % 3600) // 60)}m ago"


def nav(active):
    items = [
        ("dashboard.html", "📊 Spot", active == "spot"),
        ("futures.html", "🔵 Futures", active == "futures"),
        ("research.html", "🔬 Research", active == "research"),
        ("cron.html", "⏱ Cron", active == "cron"),
        ("glossary.html", "📖 Glossary", active == "glossary"),
    ]
    html = ['<div class="nav">']
    for href, label, is_active in items:
        cls = ' class="active"' if is_active else ''
        html.append(f'    <a href="{href}"{cls}>{label}</a>')
    html.append('</div>')
    return "\n".join(html)


def iter_position_rows(positions, prices):
    rows = []
    if not isinstance(positions, dict):
        return rows
    for coin, pos in positions.items():
        if coin.endswith("_orders"):
            continue
        if isinstance(pos, dict) and pos.get("qty", 0) > 0:
            avg = float(pos.get("avg_price", pos.get("avg", 0.0)) or 0.0)
            qty = float(pos.get("qty", 0.0) or 0.0)
            curr = prices.get(f"{coin}USDT", 0.0)
            rows.append({"coin": coin, "qty": qty, "avg": avg, "current": curr})
        elif isinstance(pos, list):
            for sub in pos:
                if isinstance(sub, dict) and sub.get("qty", 0) > 0 and not sub.get("sold"):
                    avg = float(sub.get("avg_price", sub.get("price", 0.0)) or 0.0)
                    qty = float(sub.get("qty", 0.0) or 0.0)
                    curr = prices.get(f"{coin}USDT", 0.0)
                    rows.append({"coin": coin, "qty": qty, "avg": avg, "current": curr})
    return rows


def load_spot_data(prices, manager_state):
    allocations = manager_state.get("allocation", {})
    performance = manager_state.get("performance", {})
    cards = []
    all_positions = []
    all_trades = []
    total_portfolio = 0.0
    total_positions = 0
    total_trades = 0

    for bot in BOT_FILES:
        state = load_json(BASE_DIR / bot["file"], {})
        usdt = float(state.get("usdt", 0.0) or 0.0)
        positions = state.get("positions", {})
        trade_log = state.get("trade_log", []) if isinstance(state.get("trade_log", []), list) else []
        pos_rows = iter_position_rows(positions, prices)
        pos_val = sum(item["qty"] * item["current"] for item in pos_rows)
        total = usdt + pos_val
        alloc_pct = float(allocations.get(bot["key"], 0.0) or 0.0)
        perf = performance.get(bot["key"], {})
        target_capital = float(perf.get("target_capital", round(1200 * alloc_pct / 100.0, 2)) or 0.0)
        drift_pct = float(perf.get("drift_pct", 0.0) or 0.0)
        bot_pnl = total - target_capital

        total_portfolio += total
        total_positions += len(pos_rows)
        total_trades += len(trade_log)

        for row in pos_rows:
            row["bot"] = bot["name"]
            all_positions.append(row)
        for trade in trade_log:
            if isinstance(trade, dict):
                all_trades.append({"bot": bot["name"], "bot_color": bot["color"], **trade})

        cards.append(
            {
                "bot": bot,
                "usdt": usdt,
                "total": total,
                "positions": pos_rows,
                "positions_count": len(pos_rows),
                "trade_count": len(trade_log),
                "alloc_pct": alloc_pct,
                "target_capital": target_capital,
                "drift_pct": drift_pct,
                "bot_pnl": bot_pnl,
            }
        )

    all_trades.sort(key=lambda item: parse_time(item.get("time")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return {
        "cards": cards,
        "all_positions": all_positions,
        "recent_trades": all_trades[:40],
        "total_portfolio": total_portfolio,
        "total_positions": total_positions,
        "total_trades": total_trades,
    }


def load_cron_runs():
    data = load_json(CRON_LOG_FILE, {"runs": []})
    runs = data.get("runs", []) if isinstance(data, dict) else []
    return runs if isinstance(runs, list) else []


def cron_status(run, max_age_s):
    if not run:
        return ("⚫", "stale", "No runs yet")
    dt = parse_time(run.get("timestamp"))
    if not dt:
        return ("⚫", "stale", "Unknown")
    age_sec = time.time() - dt.timestamp()
    if age_sec > max_age_s:
        return ("🔴", "stale", f"Stale ({int(age_sec // 60)}m ago)")
    status = run.get("status")
    if status == "ok":
        return ("🟢", "ok", f"OK ({int(age_sec // 60)}m ago)")
    if status == "started":
        return ("🟡", "running", f"Triggered {int(age_sec // 60)}m ago")
    return ("🔴", "error", f"Error ({int(age_sec // 60)}m ago)")


def build_recent_trades_html(trades):
    if not trades:
        return '<div class="empty-box">No trades recorded yet. This section should show the latest BUY/SELL actions across all 5 spot bots.</div>'

    rows = []
    for trade in trades:
        dt = parse_time(trade.get("time"))
        ts = dt.astimezone().strftime("%m-%d %H:%M") if dt else "—"
        action = str(trade.get("action", "")).upper()
        coin = trade.get("coin", "—")
        price = float(trade.get("price", 0.0) or 0.0)
        usdt = trade.get("usdt")
        pnl = trade.get("pnl")
        reason = trade.get("reason", "")
        action_class = "trade-buy" if "BUY" in action or "LONG" in action else "trade-sell"
        pnl_html = ""
        if pnl is not None:
            pnl_val = float(pnl or 0.0)
            pnl_class = "green" if pnl_val >= 0 else "red"
            pnl_html = f'<span class="trade-pill {pnl_class}">PnL {fmt_money(pnl_val)}</span>'
        spend_html = f'<span class="trade-pill">{fmt_money(float(usdt))}</span>' if usdt is not None else ""
        reason_html = f'<span class="trade-reason">{reason}</span>' if reason else ""
        rows.append(
            f'<div class="trade-item">'
            f'<span class="trade-time">{ts}</span>'
            f'<span class="trade-bot" style="border-color:{trade["bot_color"]};">{trade["bot"]}</span>'
            f'<span class="trade-action {action_class}">{action}</span>'
            f'<span class="trade-coin">{coin}</span>'
            f'<span class="trade-price">@ {fmt_money(price)}</span>'
            f'{spend_html}{pnl_html}{reason_html}'
            f'</div>'
        )
    return "\n".join(rows)


def build_allocation_rows(cards):
    rows = []
    for item in cards:
        bot = item["bot"]
        drift = item["drift_pct"]
        drift_class = "green" if drift <= 0 else ("yellow" if drift < 15 else "red")
        rows.append(
            f'<div class="alloc-row">'
            f'  <span class="alloc-label">{bot["name"]}</span>'
            f'  <div class="alloc-bar"><div class="alloc-fill" style="width:{item["alloc_pct"]}%;background:{bot["color"]}"></div></div>'
            f'  <span class="alloc-pct">{item["alloc_pct"]:.1f}%</span>'
            f'  <span class="alloc-meta">Current {fmt_money(item["total"])} · Target {fmt_money(item["target_capital"])} · <span class="{drift_class}">Drift {fmt_pct(drift)}</span></span>'
            f'</div>'
        )
    return "\n".join(rows)


def build_bot_cards(cards):
    html = []
    for item in cards:
        bot = item["bot"]
        pnl_class = "green" if item["bot_pnl"] >= 0 else "red"
        pos_id = f'positions-{bot["key"]}'
        html.append(
            f'''
    <div class="bot-card" data-toggle="{pos_id}" style="border-left:4px solid {bot["color"]};">
        <div class="bot-header">
            <span class="bot-icon">{bot["icon"]}</span>
            <span class="bot-name">{bot["name"]}</span>
            <span class="bot-alloc">{item["alloc_pct"]:.1f}%</span>
        </div>
        <div class="bot-stats">
            <div class="bot-stat"><span class="bs-label">Value</span><span class="bs-value">{fmt_money(item["total"])}</span></div>
            <div class="bot-stat"><span class="bs-label">USDT</span><span class="bs-value usdt-cash" data-usdt="{item["usdt"]}">{fmt_money(item["usdt"])}</span></div>
            <div class="bot-stat"><span class="bs-label">Target</span><span class="bs-value">{fmt_money(item["target_capital"])}</span></div>
            <div class="bot-stat"><span class="bs-label">Drift</span><span class="bs-value {"green" if item["drift_pct"] <= 0 else "red"}">{fmt_pct(item["drift_pct"])}</span></div>
            <div class="bot-stat"><span class="bs-label">Trades</span><span class="bs-value">{item["trade_count"]}</span></div>
        </div>
        <div class="bot-positions" id="{pos_id}"></div>
    </div>'''
        )
    return "\n".join(html)


def build_shared_style(active_color="#3b82f6"):
    return f'''
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#0f172a; color:#e2e8f0; padding:24px; }}
        h1 {{ font-size:24px; margin-bottom:4px; }}
        .subtitle {{ color:#94a3b8; font-size:14px; margin-bottom:20px; }}
        .nav {{ display:flex; gap:12px; margin-bottom:24px; flex-wrap:wrap; }}
        .nav a {{ padding:8px 16px; border-radius:8px; background:#1e293b; color:#94a3b8; text-decoration:none; font-size:13px; }}
        .nav a.active {{ background:{active_color}; color:white; }}
        .nav a:hover {{ background:#334155; }}
        .top-row {{ display:grid; grid-template-columns:2fr 1fr 1fr; gap:16px; margin-bottom:20px; }}
        .top-card, .panel, .bot-card, .section-card {{ background:#1e293b; border-radius:12px; padding:18px; }}
        .top-card .label, .section-kicker {{ color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:0.5px; }}
        .top-card .value {{ font-size:28px; font-weight:700; margin-top:4px; }}
        .top-card .sub {{ font-size:13px; margin-top:4px; color:#94a3b8; }}
        .green {{ color:#22c55e; }} .red {{ color:#ef4444; }} .yellow {{ color:#eab308; }}
        .regime-badge {{ display:inline-block; padding:4px 14px; border-radius:20px; font-size:14px; font-weight:600; margin-top:8px; }}
        .regime-bull {{ background:#22c55e22; color:#22c55e; border:1px solid #22c55e44; }}
        .regime-bear {{ background:#ef444422; color:#ef4444; border:1px solid #ef444444; }}
        .regime-sideways {{ background:#eab30822; color:#eab308; border:1px solid #eab30844; }}
        .regime-volatile {{ background:#a855f722; color:#a855f7; border:1px solid #a855f744; }}
        .live-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; background:#22c55e; animation:pulse 2s infinite; margin:0 6px 1px 0; }}
        @keyframes pulse {{ 0%{{opacity:1}}50%{{opacity:0.3}}100%{{opacity:1}} }}
        .alloc-row {{ display:grid; grid-template-columns:170px 1fr 70px minmax(240px, 380px); gap:12px; align-items:center; margin:8px 0; }}
        .alloc-bar {{ height:20px; background:#334155; border-radius:10px; overflow:hidden; }}
        .alloc-fill {{ height:100%; border-radius:10px; }}
        .alloc-pct {{ text-align:right; font-size:13px; font-weight:600; }}
        .alloc-meta {{ color:#94a3b8; font-size:12px; }}
        .bot-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(380px,1fr)); gap:16px; margin-bottom:20px; }}
        .bot-header {{ display:flex; align-items:center; gap:10px; margin-bottom:12px; }}
        .bot-icon {{ font-size:20px; }}
        .bot-name {{ font-weight:600; font-size:14px; flex:1; }}
        .bot-alloc {{ font-size:11px; padding:2px 10px; border-radius:10px; background:#334155; color:#94a3b8; }}
        .bot-stats {{ display:grid; grid-template-columns:repeat(5,1fr); gap:8px; }}
        .bot-stat {{ text-align:center; }}
        .bs-label {{ display:block; color:#64748b; font-size:10px; text-transform:uppercase; }}
        .bs-value {{ font-size:14px; font-weight:600; }}
        .bot-card {{ cursor:pointer; }}
        .bot-positions {{ margin-top:12px; display:none; color:#94a3b8; font-size:12px; }}
        .pos-chip {{ padding:3px 8px; border-radius:5px; background:#334155; font-size:11px; display:inline-block; margin:3px 4px 0 0; }}
        .pos-chip.green {{ background:#22c55e22; color:#22c55e; }}
        .pos-chip.red {{ background:#ef444422; color:#ef4444; }}
        .trade-log-section {{ background:#1e293b; border-radius:12px; padding:18px; max-height:360px; overflow-y:auto; }}
        .trade-item {{ display:flex; align-items:center; flex-wrap:wrap; gap:8px; padding:8px 0; border-bottom:1px solid #33415555; font-size:12px; }}
        .trade-time {{ color:#64748b; width:70px; }}
        .trade-bot {{ padding:2px 8px; border-radius:10px; border:1px solid #334155; background:#0f172a; font-size:11px; }}
        .trade-action {{ font-weight:700; }}
        .trade-buy {{ color:#22c55e; }}
        .trade-sell {{ color:#ef4444; }}
        .trade-pill {{ padding:2px 8px; border-radius:10px; background:#334155; color:#cbd5e1; }}
        .trade-reason {{ color:#64748b; font-size:11px; }}
        .empty-box {{ color:#64748b; text-align:center; padding:22px; font-size:13px; }}
        .mini-note {{ color:#94a3b8; font-size:12px; }}
        .cron-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:16px; margin-bottom:20px; }}
        .cron-job-card {{ background:#1e293b; border-radius:12px; padding:18px; }}
        .cron-job-head {{ display:flex; align-items:center; gap:10px; margin-bottom:10px; }}
        .cron-icon {{ font-size:18px; }}
        .cron-name {{ font-weight:700; font-size:14px; flex:1; }}
        .cron-status {{ font-size:11px; padding:3px 10px; border-radius:10px; }}
        .cron-status-ok {{ background:#22c55e22; color:#22c55e; }}
        .cron-status-error {{ background:#ef444422; color:#ef4444; }}
        .cron-status-running {{ background:#eab30822; color:#eab308; }}
        .cron-status-stale {{ background:#64748b22; color:#94a3b8; }}
        .cron-meta {{ display:grid; grid-template-columns:130px 1fr; gap:8px 12px; font-size:12px; }}
        .cron-meta .k {{ color:#64748b; }}
        table {{ width:100%; border-collapse:collapse; background:#1e293b; border-radius:12px; overflow:hidden; }}
        th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid #334155; font-size:12px; vertical-align:top; }}
        th {{ background:#334155; color:#94a3b8; text-transform:uppercase; font-size:10px; }}
        .steps-list span {{ display:inline-block; margin-right:8px; }}
        .footer-note {{ color:#64748b; font-size:12px; margin-top:10px; }}
        @media (max-width:900px) {{
            .top-row {{ grid-template-columns:1fr; }}
            .alloc-row {{ grid-template-columns:1fr; }}
            .bot-grid {{ grid-template-columns:1fr; }}
            .bot-stats {{ grid-template-columns:repeat(2,1fr); }}
        }}
    '''


def build_spot_page(manager_state, prices, spot_data, cron_runs):
    allocations_html = build_allocation_rows(spot_data["cards"])
    cards_html = build_bot_cards(spot_data["cards"])
    trades_html = build_recent_trades_html(spot_data["recent_trades"])
    all_positions_json = json.dumps(spot_data["all_positions"])
    regime = manager_state.get("regime", "sideways")
    regime_display = REGIME_ICONS.get(regime, "➡️ SIDEWAYS")
    cron_count = len(cron_runs)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="120">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spot Dashboard</title>
    <style>{build_shared_style('#3b82f6')}</style>
</head>
<body>
    <h1>🤖 Multi-Bot Trading System</h1>
    <p class="subtitle">5 spot bots · 1 portfolio · live prices update every 30s</p>
    {nav('spot')}

    <div class="top-row">
        <div class="top-card">
            <div class="label">Total Portfolio <span class="live-dot"></span><span class="green">LIVE</span></div>
            <div class="value" id="total-portfolio-value">{fmt_money(spot_data['total_portfolio'])}</div>
            <div class="sub">All 5 spot bots combined</div>
        </div>
        <div class="top-card">
            <div class="label">Market Regime</div>
            <div class="regime-badge regime-{regime}">{regime_display}</div>
            <div class="sub">Detected from BTC price structure</div>
        </div>
        <div class="top-card">
            <div class="label">Activity</div>
            <div class="value" style="font-size:22px;">{spot_data['total_trades']} trades</div>
            <div class="sub">{spot_data['total_positions']} open positions across 5 bots</div>
        </div>
    </div>

    <div class="section-card" style="margin-bottom:20px;">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
            <strong>📊 Capital Allocation</strong>
            <span class="mini-note">Target ratio + live current capital + drift per bot</span>
        </div>
        {allocations_html}
    </div>

    <div class="section-card" style="margin-bottom:20px;display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;">
        <div>
            <div class="section-kicker">Cron monitoring moved out</div>
            <strong>⏱ Cron logs and job details now live on cron.html</strong>
        </div>
        <div class="mini-note">{cron_count} log entries available · open the Cron tab for schedules, file freshness, and run history</div>
    </div>

    <div class="bot-grid">
        {cards_html}
    </div>

    <div class="trade-log-section">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
            <strong>🔄 Recent Trades</strong>
            <span class="mini-note">Shows the latest BUY/SELL actions across all 5 spot bots</span>
        </div>
        {trades_html}
    </div>

    <script>
    const allPositions = {all_positions_json};

    function renderPositions() {{
        const grouped = {{}};
        allPositions.forEach(p => {{
            if (!grouped[p.bot]) grouped[p.bot] = [];
            grouped[p.bot].push(p);
        }});
        const botKeyMap = {{
            'DCA + TP': 'positions-dca',
            'Trend Following': 'positions-trend',
            'Grid Trading': 'positions-grid',
            'Momentum': 'positions-momentum',
            'Deep MR': 'positions-deep_mr',
        }};
        Object.entries(botKeyMap).forEach(([name, id]) => {{
            const el = document.getElementById(id);
            if (!el) return;
            const rows = grouped[name] || [];
            if (!rows.length) {{
                el.innerHTML = '<span class="empty-box" style="padding:0;">No positions</span>';
                return;
            }}
            el.innerHTML = rows.map(p => {{
                const pct = p.avg > 0 ? ((p.current - p.avg) / p.avg * 100) : 0;
                const cls = pct >= 0 ? 'green' : 'red';
                return `<span class="pos-chip ${{cls}}">${{p.coin}} ${{pct.toFixed(1)}}%</span>`;
            }}).join('');
        }});
    }}

    async function updateLivePrices() {{
        try {{
            const resp = await fetch('https://api.binance.com/api/v3/ticker/price');
            const data = await resp.json();
            const prices = {{}};
            data.forEach(p => prices[p.symbol] = parseFloat(p.price));
            let livePosVal = 0;
            allPositions.forEach(p => {{
                p.current = prices[p.coin + 'USDT'] || 0;
                livePosVal += p.qty * p.current;
            }});
            renderPositions();
            let totalCash = 0;
            document.querySelectorAll('.usdt-cash').forEach(el => {{ totalCash += parseFloat(el.dataset.usdt || 0); }});
            const totalEl = document.getElementById('total-portfolio-value');
            if (totalEl) totalEl.textContent = '$' + (livePosVal + totalCash).toFixed(2);
        }} catch (e) {{
            console.log('live update failed', e);
        }}
    }}

    window.addEventListener('load', () => {{
        renderPositions();
        updateLivePrices();
        setInterval(updateLivePrices, 30000);
        document.querySelectorAll('.bot-card').forEach(card => {{
            card.addEventListener('click', () => {{
                const target = document.getElementById(card.dataset.toggle);
                if (!target) return;
                target.style.display = (!target.style.display || target.style.display === 'none') ? 'block' : 'none';
            }});
        }});
    }});
    </script>
</body>
</html>'''
    SPOT_OUTPUT.write_text(html)


def build_cron_job_cards(runs):
    latest_by_job = {}
    for run in runs:
        job = run.get("job")
        if job and job not in latest_by_job:
            latest_by_job[job] = run

    research_file_dt = None
    if RESEARCH_FILE.exists():
        research_file_dt = datetime.fromtimestamp(RESEARCH_FILE.stat().st_mtime, tz=timezone.utc)

    cards = []
    for job_key, meta in CRON_JOBS.items():
        run = latest_by_job.get(job_key)
        max_age = 1800 if job_key == "trading-bot" else 600
        icon, css, label = cron_status(run, max_age)
        rows = [
            ("Job ID", meta["job_id"]),
            ("Schedule", meta["schedule"]),
            ("Mode", meta["mode"]),
            ("Delivery", meta["deliver"]),
            ("Script", meta["script"]),
            ("Purpose", meta["details"]),
        ]
        if run:
            dt = parse_time(run.get("timestamp"))
            rows.append(("Last log", f"{dt.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z') if dt else run.get('timestamp', '—')} ({age_label(dt)})"))
            rows.append(("Logged status", str(run.get("status", "—"))))
            if run.get("error"):
                rows.append(("Error", str(run.get("error"))))
        else:
            rows.append(("Last log", "No log entries yet"))

        if job_key == "research-scraper":
            if research_file_dt:
                rows.append(("Research file", f"{RESEARCH_FILE} · updated {age_label(research_file_dt)}"))
            else:
                rows.append(("Research file", f"Missing: {RESEARCH_FILE}"))

        meta_html = ''.join([f'<div class="k">{k}</div><div>{v}</div>' for k, v in rows])
        cards.append(
            f'''
        <div class="cron-job-card">
            <div class="cron-job-head">
                <span class="cron-icon">{icon}</span>
                <span class="cron-name">{meta['name']}</span>
                <span class="cron-status cron-status-{css}">{label}</span>
            </div>
            <div class="cron-meta">{meta_html}</div>
        </div>'''
        )
    return "\n".join(cards)


def build_cron_history_rows(runs):
    if not runs:
        return '<tr><td colspan="6" class="empty-box">No cron runs logged yet.</td></tr>'
    rows = []
    for run in runs[:80]:
        dt = parse_time(run.get("timestamp"))
        ts = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S") if dt else (run.get("timestamp_local") or run.get("timestamp") or "—")
        job = run.get("job", "—")
        status = run.get("status", "—")
        status_class = "green" if status == "ok" else ("yellow" if status == "started" else "red")
        duration_ms = run.get("duration_ms")
        duration = f"{(duration_ms / 1000):.1f}s" if isinstance(duration_ms, (int, float)) else "—"
        steps = run.get("steps", {})
        step_html = []
        for name, step in steps.items():
            step_status = step.get("status", "—")
            step_class = "green" if step_status == "ok" else ("yellow" if step_status == "started" else "red")
            step_html.append(f'<span class="{step_class}">{name}:{step_status}</span>')
        if not step_html:
            step_html = ['<span class="mini-note">—</span>']
        error = run.get("error", "") or run.get("last_delivery_error", "") or "—"
        rows.append(
            f'<tr>'
            f'<td>{ts}</td>'
            f'<td>{job}</td>'
            f'<td class="{status_class}">{status}</td>'
            f'<td>{duration}</td>'
            f'<td class="steps-list">{" ".join(step_html)}</td>'
            f'<td>{error}</td>'
            f'</tr>'
        )
    return "\n".join(rows)


def build_cron_page(runs):
    cards_html = build_cron_job_cards(runs)
    rows_html = build_cron_history_rows(runs)
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="120">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cron Dashboard</title>
    <style>{build_shared_style('#0ea5e9')}</style>
</head>
<body>
    <h1>⏱ Cron Jobs Monitor</h1>
    <p class="subtitle">Job schedules, freshness, research-file activity, and run history</p>
    {nav('cron')}

    <div class="cron-grid">
        {cards_html}
    </div>

    <div class="section-card">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:12px;flex-wrap:wrap;">
            <strong>📜 Run History</strong>
            <span class="mini-note">Source: {CRON_LOG_FILE}</span>
        </div>
        <table>
            <thead>
                <tr><th>Time</th><th>Job</th><th>Status</th><th>Duration</th><th>Steps</th><th>Error</th></tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        <div class="footer-note">
            Research scraper health is judged by both cron logs and the freshness of {RESEARCH_FILE}.
            A “started” status means the scheduler fired; the file timestamp tells you whether the research output actually refreshed.
        </div>
    </div>
</body>
</html>'''
    CRON_OUTPUT.write_text(html)


def main():
    manager_state = load_json(MANAGER_FILE, {})
    prices = fetch_prices()
    spot_data = load_spot_data(prices, manager_state)
    cron_runs = load_cron_runs()
    build_spot_page(manager_state, prices, spot_data, cron_runs)
    build_cron_page(cron_runs)
    regime = manager_state.get("regime", "sideways")
    print(f"✅ Dashboards generated: {SPOT_OUTPUT} and {CRON_OUTPUT}")
    print(f"   Spot portfolio: {fmt_money(spot_data['total_portfolio'])} · regime: {regime} · cron logs: {len(cron_runs)}")


if __name__ == "__main__":
    main()
