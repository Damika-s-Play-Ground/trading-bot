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
from html import escape as _escape_html
from pathlib import Path

from trading_bot.dashboards.data_store import load_performance_runs, sync_all
from trading_bot.dashboards.shared_ui import build_bar_chart, build_donut_chart, build_line_chart_svg

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
        ("todo.html", "🗒 Todo", active == "todo"),
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


def _trade_why(trade, manager_state):
    bot = str(trade.get("bot", ""))
    action = str(trade.get("action", "")).upper()
    reason = str(trade.get("reason", "")).strip()
    regime = str((manager_state or {}).get("regime", "sideways")).replace("_", " ")

    if "BUY" in action or "LONG" in action:
        if bot == "DCA + TP":
            return (
                "Buy logic: RSI was oversold, MACD and Bollinger filters were aligned, volume stayed healthy, "
                f"and the manager allowed a new entry under the current {regime} regime."
            )
        if bot == "Trend Following":
            return (
                "Buy logic: price stayed above the 50MA and 20MA, MACD histogram stayed bullish, "
                "and volume confirmed the trend continuation."
            )
        if bot == "Grid Trading":
            return (
                "Buy logic: price touched a lower grid band inside the active range, so the bot averaged in "
                "with the grid."
            )
        if bot == "Momentum":
            return (
                "Buy logic: volume spiked above normal while price broke out above the moving average, "
                "with RSI confirming momentum strength."
            )
        if bot == "Deep MR":
            return (
                "Buy logic: RSI fell below the extreme-oversold threshold on meaningful volume, which is the "
                "core mean-reversion entry."
            )
        return f"Buy logic: the bot found a valid entry under the current {regime} market conditions."

    reason_lower = reason.lower()
    if any(token in reason_lower for token in ["tp", "take profit", "profit target"]):
        return "Sell logic: take-profit target hit, so the bot locked gains at the strategy target."
    if any(token in reason_lower for token in ["trail", "trailing"]):
        return "Sell logic: the trailing stop fired after price pulled back from its recent peak."
    if any(token in reason_lower for token in ["sl", "stop loss", "loss"]):
        return "Sell logic: the stop-loss guard triggered to cap downside risk."
    if any(token in reason_lower for token in ["trend broken", "below 20ma", "exit ma"]):
        return "Sell logic: the trend filter broke, so the position was exited to avoid riding a failed trend."
    if reason:
        return f"Sell logic: {reason}."
    return f"Sell logic: the bot exited based on its current strategy rules in the {regime} regime."


def build_recent_trades_html(trades, manager_state=None):
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
        why = _trade_why(trade, manager_state)
        reason_text = str(reason).strip() or why
        pnl_html = ""
        if pnl is not None:
            pnl_val = float(pnl or 0.0)
            pnl_class = "green" if pnl_val >= 0 else "red"
            pnl_html = f'<span class="trade-pill {pnl_class}">PnL {fmt_money(pnl_val)}</span>'
        spend_html = f'<span class="trade-pill">{fmt_money(float(usdt))}</span>' if usdt is not None else ""
        rows.append(
            f'<div class="trade-item">'
            f'  <div class="trade-summary">'
            f'    <div class="trade-main">'
            f'      <span class="trade-time">{ts}</span>'
            f'      <span class="trade-bot" style="border-color:{trade["bot_color"]};">{trade["bot"]}</span>'
            f'      <span class="trade-action {action_class}">{action}</span>'
            f'      <span class="trade-coin">{coin}</span>'
            f'    </div>'
            f'    <div class="trade-metrics">'
            f'      <span class="trade-price">@ {fmt_money(price)}</span>'
            f'      {spend_html}{pnl_html}'
            f'    </div>'
            f'  </div>'
            f'  <div class="trade-why">{_escape_html(reason_text)}</div>'
            f'</div>'
        )
    return f'<div class="trade-grid">{"".join(rows)}</div>'


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


def build_bot_cards(cards, total_portfolio):
    html = []
    for item in cards:
        bot = item["bot"]
        pos_id = f'positions-{bot["key"]}'
        contribution_pct = (item["total"] / total_portfolio * 100) if total_portfolio else 0.0
        html.append(
            f'''    <div class="bot-card" data-toggle="{pos_id}" data-bot-key="{bot["key"]}" data-bot-name="{bot["name"]}" data-bot-cash="{item["usdt"]}" style="border-left:4px solid {bot["color"]};">
        <div class="bot-header">
            <span class="bot-icon">{bot["icon"]}</span>
            <span class="bot-name">{bot["name"]}</span>
            <span class="bot-alloc">{item["alloc_pct"]:.1f}%</span>
        </div>
        <div class="bot-stats">
            <div class="bot-stat"><span class="bs-label">Value</span><span class="bs-value" data-bot-total="{bot["key"]}">{fmt_money(item["total"])}</span></div>
            <div class="bot-stat"><span class="bs-label">USDT</span><span class="bs-value usdt-cash" data-usdt="{item["usdt"]}">{fmt_money(item["usdt"])}</span></div>
            <div class="bot-stat"><span class="bs-label">Target</span><span class="bs-value">{fmt_money(item["target_capital"])}</span></div>
            <div class="bot-stat"><span class="bs-label">Drift</span><span class="bs-value {"green" if item["drift_pct"] <= 0 else "red"}">{fmt_pct(item["drift_pct"])}</span></div>
            <div class="bot-stat"><span class="bs-label">Trades</span><span class="bs-value">{item["trade_count"]}</span></div>
            <div class="bot-stat"><span class="bs-label">Portfolio</span><span class="bs-value" data-bot-contribution-pct="{bot["key"]}">{contribution_pct:.1f}%</span><span class="bs-sub" data-bot-contribution-amt="{bot["key"]}">{fmt_money(item["total"])}</span></div>
        </div>
        <div class="bot-positions" id="{pos_id}"></div>
    </div>'''
        )
    return "\n".join(html)


def build_dashboard_insights(cards, performance_runs):
    if not cards:
        return ""

    total_value = sum(item["total"] for item in cards)
    allocation_segments = [
        {"label": item["bot"]["name"], "value": item["total"], "color": item["bot"]["color"]}
        for item in cards
    ]
    equity_values = [float(run.get("portfolio_total", 0) or 0) for run in performance_runs]
    equity_labels = []
    for run in performance_runs:
        ts = parse_time(run.get("timestamp"))
        equity_labels.append(ts.astimezone().strftime("%m-%d %H:%M") if ts else "")
    activity_rows = [
        {"label": item["bot"]["name"], "value": item["trade_count"], "color": item["bot"]["color"], "meta": f"{item['positions_count']} open positions"}
        for item in cards
    ]
    chart_parts = [
        build_donut_chart(allocation_segments, title="Portfolio allocation", center_value=fmt_money(total_value), center_label="live value", subtitle="Current capital split by bot"),
        build_line_chart_svg(equity_values, labels=equity_labels, title="Equity curve", subtitle="Historical portfolio totals from the performance journal", color="#60a5fa"),
        build_bar_chart(activity_rows, title="Bot activity", subtitle="Trades and open-position footprint per bot", value_suffix=" trades"),
    ]
    return f'<div class="analytics-grid">{"".join(chart_parts)}</div>'


def build_shared_style(active_color="#3b82f6"):
    style = '''
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#0f172a; color:#e2e8f0; padding:24px; }}
        h1 {{ font-size:24px; margin-bottom:4px; }}
        .subtitle {{ color:#94a3b8; font-size:14px; margin-bottom:20px; }}
        .nav {{ display:flex; gap:12px; margin-bottom:24px; flex-wrap:wrap; }}
        .nav a {{ padding:8px 16px; border-radius:8px; background:#1e293b; color:#94a3b8; text-decoration:none; font-size:13px; }}
        .nav a.active { background:__ACTIVE_COLOR__; color:white; }
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
        .bot-stats { display:grid; grid-template-columns:repeat(6,1fr); gap:8px; }
        .bot-stat { text-align:center; min-width:0; }
        .bs-label { display:block; color:#64748b; font-size:10px; text-transform:uppercase; }
        .bs-value { display:block; font-size:14px; font-weight:600; font-variant-numeric:tabular-nums; }
        .bs-sub { display:block; color:#64748b; font-size:11px; margin-top:3px; font-variant-numeric:tabular-nums; }
        .bot-card { cursor:pointer; transition:transform .18s ease, border-color .18s ease, box-shadow .18s ease; }
        .bot-card:hover { transform:translateY(-1px); box-shadow:0 12px 26px rgba(15,23,42,.24); }
        .bot-positions { margin-top:14px; display:none; color:#94a3b8; font-size:12px; gap:10px; }
        .position-row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:10px 14px; align-items:center; background:#0f172a; border:1px solid #334155; border-radius:12px; padding:12px; margin-bottom:10px; }
        .position-main { display:flex; flex-wrap:wrap; align-items:center; gap:8px; min-width:0; }
        .position-coin { font-weight:700; color:#e2e8f0; }
        .position-pnl { font-size:11px; font-weight:700; }
        .position-meta { color:#94a3b8; font-size:11px; }
        .position-value { font-weight:700; color:#f8fafc; font-variant-numeric:tabular-nums; }
        .position-share { color:#64748b; font-size:11px; text-align:right; font-variant-numeric:tabular-nums; }
        .trade-log-section { background:#1e293b; border-radius:16px; padding:18px; max-height:560px; overflow-y:auto; border:1px solid #334155; box-shadow:0 12px 30px rgba(15,23,42,.20); }
        .trade-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:12px; }
        .trade-item { display:flex; flex-direction:column; gap:10px; padding:14px; border:1px solid #334155; border-radius:14px; background:#111827; font-size:12px; min-width:0; }
        .trade-summary { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; flex-wrap:wrap; }
        .trade-main { display:flex; align-items:center; flex-wrap:wrap; gap:8px 10px; min-width:0; }
        .trade-metrics { display:flex; align-items:center; justify-content:flex-end; flex-wrap:wrap; gap:8px; }
        .trade-time { color:#64748b; min-width:74px; font-variant-numeric:tabular-nums; }
        .trade-bot { padding:2px 8px; border-radius:10px; border:1px solid #334155; background:#0f172a; font-size:11px; }
        .trade-action { font-weight:700; }
        .trade-buy { color:#22c55e; }
        .trade-sell { color:#ef4444; }
        .trade-pill { padding:3px 8px; border-radius:10px; background:#334155; color:#cbd5e1; white-space:nowrap; }
        .trade-price { color:#e2e8f0; font-weight:600; white-space:nowrap; }
        .trade-why { color:#cbd5e1; font-size:11px; line-height:1.6; width:100%; background:#0f172a; border:1px solid #243244; border-left:3px solid #334155; border-radius:10px; padding:10px 12px; }
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
        .analytics-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; margin-bottom:20px; }}
        .chart-card { background:#1e293b; border-radius:16px; padding:18px; border:1px solid #334155; box-shadow:0 12px 30px rgba(15,23,42,.24); position:relative; overflow:hidden; transition:transform .18s ease, border-color .18s ease, box-shadow .18s ease; }
        .chart-card:hover { transform:translateY(-1px); border-color:#475569; box-shadow:0 18px 34px rgba(15,23,42,.28); }
        .chart-head { display:flex; justify-content:space-between; align-items:flex-end; gap:12px; margin-bottom:12px; flex-wrap:wrap; }
        .chart-head strong { font-size:14px; }
        .chart-stats { display:flex; justify-content:flex-end; flex-wrap:wrap; gap:8px; }
        .chart-stat { padding:6px 10px; border-radius:999px; border:1px solid #334155; background:#0f172a; color:#94a3b8; font-size:11px; font-variant-numeric:tabular-nums; }
        .chart-svg { width:100%; height:230px; display:block; background:linear-gradient(180deg,#0f172a 0%, #111827 100%); border-radius:14px; overflow:hidden; }
        .donut-card { display:flex; flex-direction:column; }
        .donut-wrap { display:grid; grid-template-columns:180px 1fr; gap:14px; align-items:center; }
        .donut { width:180px; height:180px; padding:16px; display:grid; place-items:center; position:relative; transition:transform .18s ease, box-shadow .18s ease; }
        .donut-card:hover .donut { transform:scale(1.02); box-shadow:0 14px 30px rgba(15,23,42,.30); }
        .donut::after { content:''; position:absolute; inset:26px; border-radius:50%; background:#0f172a; box-shadow:inset 0 0 0 1px #334155; }
        .donut-svg { width:180px; height:180px; overflow:visible; }
        .donut-inner { position:relative; z-index:1; text-align:center; }
        .donut-value { font-size:18px; font-weight:800; line-height:1.1; }
        .donut-label { font-size:11px; color:#94a3b8; margin-top:2px; text-transform:uppercase; letter-spacing:.6px; }
        .donut-legend { display:flex; flex-direction:column; gap:8px; }
        .legend-row { display:grid; grid-template-columns:14px 1fr auto; gap:8px; align-items:center; font-size:12px; color:#cbd5e1; padding:8px 10px; border-radius:12px; border:1px solid transparent; cursor:pointer; transition:transform .18s ease, border-color .18s ease, background .18s ease; }
        .legend-row:hover { transform:translateX(4px); border-color:#334155; background:#0f172a; }
        .legend-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
        .legend-val { color:#94a3b8; font-variant-numeric:tabular-nums; }
        .legend-meta { display:flex; align-items:center; gap:10px; justify-content:flex-end; }
        .legend-share { color:#64748b; font-size:11px; font-variant-numeric:tabular-nums; }
        .bar-chart { display:flex; flex-direction:column; gap:12px; }
        .bar-row { padding:10px 12px; border-radius:14px; border:1px solid transparent; transition:transform .18s ease, border-color .18s ease, background .18s ease; }
        .bar-row:hover { transform:translateY(-1px); border-color:#334155; background:#0f172a; }
        .bar-row-head { display:flex; justify-content:space-between; gap:12px; font-size:12px; margin-bottom:6px; }
        .bar-value { color:#94a3b8; font-variant-numeric:tabular-nums; }
        .bar-track { height:10px; background:#0f172a; border-radius:999px; overflow:hidden; box-shadow:inset 0 0 0 1px #334155; }
        .bar-fill { height:100%; border-radius:999px; transition:filter .18s ease, transform .18s ease; transform-origin:left center; }
        .bar-row:hover .bar-fill { filter:brightness(1.08); transform:scaleY(1.25); }
        .bar-meta { color:#64748b; font-size:11px; margin-top:5px; }
        .section-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:12px; }
        .search-input { width:min(360px,100%); background:#0f172a; border:1px solid #334155; color:#e2e8f0; padding:10px 12px; border-radius:12px; font-size:13px; outline:none; }
        .search-input:focus { border-color:#60a5fa; box-shadow:0 0 0 3px rgba(59,130,246,.16); }
        .chip-row {{ display:flex; flex-wrap:wrap; gap:8px; }}
        .chip { padding:7px 11px; border-radius:999px; border:1px solid #334155; background:#0f172a; color:#cbd5e1; font-size:12px; cursor:pointer; user-select:none; }
        .chip.active { background:#3b82f622; border-color:#3b82f655; color:#93c5fd; }
        .chip:hover { border-color:#475569; }
        .muted { color:#94a3b8; }
        .chart-gridline { stroke:#334155; stroke-width:1; stroke-dasharray:4 6; opacity:.75; }
        .chart-axis-label { fill:#64748b; font-size:10px; }
        .chart-line { filter:drop-shadow(0 0 8px rgba(96,165,250,.18)); }
        .chart-area { transition:opacity .18s ease; }
        .chart-card:hover .chart-area { opacity:.72; }
        .chart-guide { stroke:#94a3b8; stroke-width:1; stroke-dasharray:4 5; opacity:0; transition:opacity .18s ease; }
        .chart-point-group { cursor:pointer; outline:none; }
        .chart-point { transition:transform .18s ease, filter .18s ease; transform-origin:center; }
        .chart-point-latest { filter:drop-shadow(0 0 10px rgba(255,255,255,.24)); }
        .chart-point-extreme { stroke:#e2e8f0; stroke-width:2.4; }
        .chart-point-group:hover .chart-point, .chart-point-group:focus .chart-point { transform:scale(1.55); filter:drop-shadow(0 0 12px rgba(255,255,255,.30)); }
        .chart-point-group:hover .chart-guide, .chart-point-group:focus .chart-guide { opacity:.95; }
        .chart-latest-tag { pointer-events:none; }
        .donut-segment { transition:transform .18s ease, stroke-width .18s ease, filter .18s ease, opacity .18s ease; transform-origin:center; }
        .donut-segment-group { cursor:pointer; outline:none; }
        .donut-segment-group:hover .donut-segment, .donut-segment-group:focus .donut-segment { stroke-width:22; filter:drop-shadow(0 0 10px rgba(255,255,255,.24)); opacity:1; }
        .chart-tooltip { position:fixed; z-index:9999; pointer-events:none; max-width:280px; padding:9px 11px; border-radius:10px; background:rgba(15,23,42,.96); color:#e2e8f0; border:1px solid #334155; box-shadow:0 12px 26px rgba(15,23,42,.30); font-size:11px; line-height:1.45; opacity:0; transform:translate(-9999px,-9999px); transition:opacity .12s ease; }
        .chart-tooltip.visible { opacity:1; }
        @media (max-width:900px) {
            body { padding:16px; }
            .top-row { grid-template-columns:1fr; }
            .alloc-row { grid-template-columns:1fr; }
            .bot-grid { grid-template-columns:1fr; }
            .bot-stats { grid-template-columns:repeat(2,1fr); }
            .position-row { grid-template-columns:1fr; }
            .position-value, .position-share { justify-self:flex-start; text-align:left; }
            .donut-wrap { grid-template-columns:1fr; justify-items:center; }
            .donut-legend { width:100%; }
            .chart-svg { height:200px; }
            .trade-grid { grid-template-columns:1fr; }
        }
        @media (max-width:600px) {
            .nav { gap:8px; }
            .nav a { width:calc(50% - 4px); text-align:center; }
            .bot-stats { grid-template-columns:1fr 1fr; gap:10px; }
            .top-card, .panel, .bot-card, .section-card, .chart-card { padding:16px; }
            .trade-log-section { padding:14px; }
            .trade-time { min-width:0; }
            .trade-summary, .trade-main, .trade-metrics { gap:6px 8px; }
            .trade-metrics { justify-content:flex-start; }
            .trade-pill, .trade-bot { font-size:10px; }
            .trade-why { padding:9px 10px; }
        }
    '''
    return style.replace('__ACTIVE_COLOR__', active_color).replace('{{', '{').replace('}}', '}')


def build_spot_page(manager_state, prices, spot_data, cron_runs):
    allocations_html = build_allocation_rows(spot_data["cards"])
    cards_html = build_bot_cards(spot_data["cards"], spot_data["total_portfolio"])
    trades_html = build_recent_trades_html(spot_data["recent_trades"], manager_state)
    all_positions_json = json.dumps(spot_data["all_positions"])
    regime = manager_state.get("regime", "sideways")
    regime_display = REGIME_ICONS.get(regime, "➡️ SIDEWAYS")
    cron_count = len(cron_runs)
    performance_runs = load_performance_runs(40)
    insights_html = build_dashboard_insights(spot_data["cards"], performance_runs)

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

    <div class="section-card" style="margin-bottom:20px;padding:14px 18px;">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;">
            <div>
                <div class="section-kicker">Lightweight Flask dashboard</div>
                <div class="mini-note">Served fast from app.py with static pages + JSON endpoints for refresh actions.</div>
            </div>
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                <button id="dashboard-refresh-btn" style="border:1px solid #334155;background:#0f172a;color:#e2e8f0;border-radius:10px;padding:8px 12px;cursor:pointer;font-size:12px;">Refresh generated pages</button>
                <span class="mini-note" id="dashboard-refresh-status">Live price polling active</span>
            </div>
        </div>
    </div>

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

    {insights_html}

    <div class="section-card" style="margin-bottom:20px;">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
            <strong>📊 Capital Allocation</strong>
            <span class="mini-note">Target ratio + live current capital + drift per bot</span>
        </div>
        {allocations_html}
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

    function getTotalCash() {{
        let totalCash = 0;
        document.querySelectorAll('.usdt-cash').forEach(cashEl => {{ totalCash += parseFloat(cashEl.dataset.usdt || 0); }});
        return totalCash;
    }}

    function renderBotContributionTotals(totalPortfolioValue) {{
        const botTotals = {{}};
        document.querySelectorAll('.bot-card').forEach(card => {{
            botTotals[card.dataset.botName] = parseFloat(card.dataset.botCash || 0);
        }});
        allPositions.forEach(position => {{
            botTotals[position.bot] = (botTotals[position.bot] || 0) + ((position.current || 0) * (position.qty || 0));
        }});
        document.querySelectorAll('.bot-card').forEach(card => {{
            const botTotal = botTotals[card.dataset.botName] || 0;
            const pct = totalPortfolioValue > 0 ? (botTotal / totalPortfolioValue * 100) : 0;
            const totalEl = card.querySelector('[data-bot-total]');
            const pctEl = card.querySelector('[data-bot-contribution-pct]');
            const amtEl = card.querySelector('[data-bot-contribution-amt]');
            if (totalEl) totalEl.textContent = '$' + botTotal.toFixed(2);
            if (pctEl) pctEl.textContent = pct.toFixed(1) + '%';
            if (amtEl) amtEl.textContent = '$' + botTotal.toFixed(2);
        }});
    }}

    function renderPositions() {{
        const grouped = {{}};
        allPositions.forEach(p => {{
            if (!grouped[p.bot]) grouped[p.bot] = [];
            grouped[p.bot].push(p);
        }});
        const totalPortfolioValue = allPositions.reduce((sum, position) => sum + ((position.current || 0) * (position.qty || 0)), 0) + getTotalCash();
        renderBotContributionTotals(totalPortfolioValue);
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
                const value = (p.current || 0) * (p.qty || 0);
                const share = totalPortfolioValue > 0 ? (value / totalPortfolioValue * 100) : 0;
                return `<div class="position-row"><div class="position-main"><span class="position-coin">${{p.coin}}</span><span class="position-pnl ${{cls}}">${{pct.toFixed(1)}}%</span><span class="position-meta">Avg $${{p.avg.toFixed(4)}} · Qty ${{p.qty.toFixed(4)}}</span></div><div><div class="position-value">$${{value.toFixed(2)}}</div><div class="position-share">Contributes $${{value.toFixed(2)}} · ${{share.toFixed(2)}}% of portfolio</div></div></div>`;
            }}).join('');
        }});
    }}

    function setupChartTooltips() {{
        const tooltip = document.createElement('div');
        tooltip.className = 'chart-tooltip';
        document.body.appendChild(tooltip);

        const moveTooltip = (event, explicitX, explicitY) => {{
            const x = explicitX ?? event?.clientX ?? 0;
            const y = explicitY ?? event?.clientY ?? 0;
            tooltip.style.transform = `translate(${{x + 14}}px, ${{y + 16}}px)`;
        }};

        document.querySelectorAll('[data-tooltip]').forEach(node => {{
            const show = (event) => {{
                tooltip.textContent = node.dataset.tooltip || '';
                tooltip.classList.add('visible');
                if (event?.type === 'focus') {{
                    const rect = node.getBoundingClientRect();
                    moveTooltip(null, rect.left + rect.width / 2, rect.top + 12);
                    return;
                }}
                moveTooltip(event);
            }};
            node.addEventListener('mouseenter', show);
            node.addEventListener('mousemove', moveTooltip);
            node.addEventListener('focus', show);
            node.addEventListener('blur', () => tooltip.classList.remove('visible'));
            node.addEventListener('mouseleave', () => tooltip.classList.remove('visible'));
        }});
    }}

    async function triggerDashboardRefresh() {{
        const statusEl = document.getElementById('dashboard-refresh-status');
        const btn = document.getElementById('dashboard-refresh-btn');
        if (!statusEl || !btn || !window.location.origin.startsWith('http')) return;
        btn.disabled = true;
        statusEl.textContent = 'Refreshing generated pages…';
        try {{
            const resp = await fetch('/api/refresh', {{ method: 'POST' }});
            const payload = await resp.json();
            statusEl.textContent = payload?.ok ? 'Refresh complete. Reload page to pull regenerated HTML.' : 'Refresh failed. Check terminal logs.';
        }} catch (error) {{
            console.log('dashboard refresh failed', error);
            statusEl.textContent = 'Refresh request failed.';
        }} finally {{
            btn.disabled = false;
        }}
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
            const totalEl = document.getElementById('total-portfolio-value');
            if (totalEl) totalEl.textContent = '$' + (livePosVal + getTotalCash()).toFixed(2);
        }} catch (e) {{
            console.log('live update failed', e);
        }}
    }}

    window.addEventListener('load', () => {{
        renderPositions();
        setupChartTooltips();
        updateLivePrices();
        setInterval(updateLivePrices, 30000);
        document.getElementById('dashboard-refresh-btn')?.addEventListener('click', triggerDashboardRefresh);
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
        max_age = 2700 if job_key == "trading-bot" else 600
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
    sync_all()
    manager_state = load_json(MANAGER_FILE, {})
    prices = fetch_prices()
    spot_data = load_spot_data(prices, manager_state)
    cron_runs = load_cron_runs()
    build_spot_page(manager_state, prices, spot_data, cron_runs)
    build_cron_page(cron_runs)
    from trading_bot.dashboards.todo_page import build_todo_page
    build_todo_page()
    regime = manager_state.get("regime", "sideways")
    print(f"✅ Dashboards generated: {SPOT_OUTPUT}, {CRON_OUTPUT}, and {REPO_ROOT / 'todo.html'}")
    print(f"   Spot portfolio: {fmt_money(spot_data['total_portfolio'])} · regime: {regime} · cron logs: {len(cron_runs)}")


if __name__ == "__main__":
    main()
