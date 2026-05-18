#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template_string, request, send_from_directory

from trading_bot.config.settings import APP_HOST, APP_PORT, BUILD_ON_START
from trading_bot.dashboards.dashboard_backend import dashboard_payload
from trading_bot.dashboards.data_store import (
    create_todo_item,
    load_research_items,
    load_research_state_overrides,
    load_todo_items,
    load_todo_state_overrides,
    save_research_state,
    save_todo_state,
    sync_all_if_needed,
    todo_stats,
)
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

TODO_CATEGORY_COPY = {
    "research": "This stage improves signal quality, ranking confidence, and idea selection before capital gets reassigned.",
    "ops": "This stage hardens the runtime so the system behaves predictably across cron runs, restarts, and production incidents.",
    "risk": "This stage adds explicit safety rails so promotion and capital changes stay constrained by measurable checks.",
    "architecture": "This stage improves the plumbing behind the dashboard and manager so features stay durable instead of becoming one-off hacks.",
    "product": "This stage improves operator usability so decisions are faster, clearer, and easier to audit from the dashboard surface.",
    "done": "This roadmap stage is already completed and now acts as baseline capability for the next phase.",
    "other": "This roadmap stage supports the broader project path and should be reviewed in the context of nearby stages.",
}

TODO_NEXT_ACTION_COPY = {
    "open": "Treat this as upcoming work. Review the dependent outputs and implement the smallest production-safe next step.",
    "done": "No action needed unless the implementation has drifted and the summary needs to be revalidated.",
}

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


@app.get("/api/research-state")
def api_research_state_get():
    return jsonify({"items": load_research_state_overrides()})


@app.get("/api/research-data")
def api_research_data():
    sync_all_if_needed(min_interval=5.0)
    items = load_research_items(limit=300)
    review_counts: dict[str, int] = {"promoted": 0, "shortlisted": 0, "raw": 0, "rejected": 0}
    platform_counts: dict[str, int] = {}
    for item in items:
        review_key = str(item.get("review_status", "raw") or "raw")
        review_counts[review_key] = review_counts.get(review_key, 0) + 1
        platform = str(item.get("platform", "Source") or "Source")
        platform_counts[platform] = platform_counts.get(platform, 0) + 1
    return jsonify(
        {
            "summary": {
                "total": len(items),
                "promoted": review_counts.get("promoted", 0),
                "shortlisted": review_counts.get("shortlisted", 0),
                "raw": review_counts.get("raw", 0),
                "rejected": review_counts.get("rejected", 0),
                "platform_counts": platform_counts,
            },
            "items": items,
        }
    )


@app.get("/api/todo-data")
def api_todo_data():
    sync_all_if_needed(min_interval=5.0)
    items = load_todo_items()
    payload_items = []
    for item in items:
        payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
        category = str(payload.get("category", "other"))
        status = str(item.get("status", "open"))
        stage_number = int(item.get("sort_order", 0)) + 1
        detail = (
            f"Stage #{stage_number}: {str(item.get('text', '')).strip()} "
            f"{TODO_CATEGORY_COPY.get(category, TODO_CATEGORY_COPY['other'])} "
            f"{TODO_NEXT_ACTION_COPY.get(status, TODO_NEXT_ACTION_COPY['open'])}"
        )
        payload_items.append(
            {
                "item_key": str(item.get("item_key", "")),
                "stage_number": stage_number,
                "sort_order": int(item.get("sort_order", 0)),
                "text": str(item.get("text", "")).strip(),
                "notes": str(item.get("notes", "") or "").strip(),
                "status": status,
                "base_status": str(item.get("base_status", item.get("status", "open"))),
                "section": str(item.get("section", "")),
                "category": category,
                "source_file": Path(str(item.get("source_file") or "")).name or "runtime_state.json",
                "detail": detail,
                "status_label": {
                    "done": "Completed",
                    "open": "Upcoming",
                }.get(status, status.title()),
                "can_toggle": str(item.get("base_status", item.get("status", "open"))) == "open",
                "is_custom": bool(payload.get("is_custom")),
            }
        )
    return jsonify({"stats": todo_stats(items), "items": payload_items})


@app.post("/api/todo-items")
def api_todo_items_post():
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()
    notes = str(payload.get("notes", "") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "title is required"}), 400
    try:
        item = create_todo_item(title=title, notes=notes, source="dashboard")
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "item": item})


@app.post("/api/todo-state")
def api_todo_state_post():
    payload = request.get_json(silent=True) or {}
    item_key = str(payload.get("item_key", "")).strip()
    status = str(payload.get("status", "open")).strip().lower()
    if not item_key:
        return jsonify({"ok": False, "error": "item_key is required"}), 400
    saved = save_todo_state(item_key=item_key, status=status, source="dashboard")
    return jsonify({"ok": True, "item": saved})


@app.post("/api/research-state")
def api_research_state_post():
    payload = request.get_json(silent=True) or {}
    item_key = str(payload.get("item_key", "")).strip()
    status = str(payload.get("status", "open")).strip().lower()
    if not item_key:
        return jsonify({"ok": False, "error": "item_key is required"}), 400
    saved = save_research_state(item_key=item_key, status=status, source="dashboard")
    return jsonify({"ok": True, "item": saved})


@app.post("/api/refresh")
def api_refresh():
    if not _is_local_request():
        abort(403)
    results = build_all_pages()
    ok = all(item["ok"] for item in results)
    return jsonify({"ok": ok, "results": results})


@app.get("/dashboard")
def serve_dashboard():
    payload = json.dumps(dashboard_payload())
    return render_template_string(
        """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Trading Dashboard</title>
  <link rel=\"stylesheet\" href=\"/static/dashboard.css\" />
</head>
<body>
  <div id=\"app\">Loading dashboard…</div>
  <script>window.__DASHBOARD_BOOTSTRAP__ = {{ payload | safe }};</script>
  <script src=\"/static/vendor/vue.global.prod.js\"></script>
  <script src=\"/static/dashboard-app.js\"></script>
</body>
</html>
        """,
        payload=payload,
    )


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
    if BUILD_ON_START:
        build_all_pages()
    app.run(host=APP_HOST, port=APP_PORT, debug=False)
