#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, request, send_from_directory

from trading_bot.dashboards.dashboard_backend import dashboard_payload
from trading_bot.dashboards.data_store import load_todo_state_overrides, save_todo_state
from trading_bot.dashboards.spot_dashboard import MANAGER_FILE, fetch_prices, load_cron_runs, load_json, load_spot_data

REPO_ROOT = Path(__file__).resolve().parent
STATIC_DIR = REPO_ROOT / "static"
PAGES = {
    "dashboard.html",
    "cron.html",
    "futures.html",
    "research.html",
    "todo.html",
    "glossary.html",
}
ROUTE_MAP = {
    "dashboard": "dashboard.html",
    "futures": "futures.html",
    "research": "research.html",
    "todo": "todo.html",
    "cron": "cron.html",
    "glossary": "glossary.html",
}
BUILD_SCRIPTS = [
    "dashboard.py",
    "futures_dashboard.py",
    "research_page.py",
    "glossary.py",
    "todo.py",
]

app = Flask(__name__)


def build_all_pages() -> list[dict]:
    results = []
    for script_name in BUILD_SCRIPTS:
        script_path = REPO_ROOT / script_name
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            results.append(
                {
                    "script": script_name,
                    "ok": proc.returncode == 0,
                    "stdout": proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "",
                    "stderr": proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "",
                }
            )
        except subprocess.TimeoutExpired:
            results.append(
                {
                    "script": script_name,
                    "ok": False,
                    "stdout": "",
                    "stderr": "timed out after 120s",
                }
            )
    return results


def spot_summary() -> dict:
    manager_state = load_json(MANAGER_FILE, {})
    prices = fetch_prices()
    spot_data = load_spot_data(prices, manager_state)
    cards = []
    total = spot_data["total_portfolio"] or 0.0
    for item in spot_data["cards"]:
        cards.append(
            {
                "bot": item["bot"]["name"],
                "value": round(item["total"], 2),
                "usdt": round(item["usdt"], 2),
                "target": round(item["target_capital"], 2),
                "drift_pct": round(item["drift_pct"], 2),
                "trade_count": item["trade_count"],
                "positions_count": item["positions_count"],
                "portfolio_pct": round((item["total"] / total * 100), 2) if total else 0.0,
            }
        )
    return {
        "total_portfolio": round(total, 2),
        "total_positions": spot_data["total_positions"],
        "total_trades": spot_data["total_trades"],
        "regime": manager_state.get("regime", "sideways"),
        "bots": cards,
        "recent_trades": spot_data["recent_trades"][:10],
        "cron_runs": len(load_cron_runs()),
    }


def _is_local_request() -> bool:
    remote = (request.remote_addr or "").strip()
    return remote in {"127.0.0.1", "::1", "localhost"}


@app.get("/")
def home():
    return redirect("/dashboard")


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "repo": str(REPO_ROOT)})


@app.get("/api/spot-summary")
def api_spot_summary():
    return jsonify(spot_summary())


@app.get("/api/dashboard-data")
def api_dashboard_data():
    return jsonify(dashboard_payload())


@app.get("/api/todo-state")
def api_todo_state_get():
    return jsonify({"items": load_todo_state_overrides()})


@app.post("/api/todo-state")
def api_todo_state_post():
    payload = request.get_json(silent=True) or {}
    item_key = str(payload.get("item_key", "")).strip()
    status = str(payload.get("status", "open")).strip().lower()
    if not item_key:
        return jsonify({"ok": False, "error": "item_key is required"}), 400
    saved = save_todo_state(item_key=item_key, status=status, source="dashboard")
    return jsonify({"ok": True, "item": saved})


@app.post("/api/refresh")
def api_refresh():
    if not _is_local_request():
        abort(403)
    results = build_all_pages()
    ok = all(item["ok"] for item in results)
    return jsonify({"ok": ok, "results": results})


@app.get("/api/refresh")
def api_refresh_get():
    abort(405)


@app.get("/static/<path:filename>")
def serve_static(filename: str):
    return send_from_directory(STATIC_DIR, filename)


@app.get("/<page_name>")
def serve_clean_page(page_name: str):
    if page_name in ROUTE_MAP:
        return send_from_directory(REPO_ROOT, ROUTE_MAP[page_name])
    if page_name in PAGES:
        clean = page_name[:-5] if page_name.endswith('.html') else 'dashboard'
        return redirect(f"/{clean}")
    return redirect("/dashboard")


@app.get("/<path:page>")
def serve_page(page: str):
    if page in PAGES:
        clean = page[:-5] if page.endswith('.html') else 'dashboard'
        return redirect(f"/{clean}")
    return redirect("/dashboard")


if __name__ == "__main__":
    build_on_start = os.getenv("BUILD_ON_START", "1") == "1"
    if build_on_start:
        build_all_pages()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8008"))
    app.run(host=host, port=port, debug=False)
