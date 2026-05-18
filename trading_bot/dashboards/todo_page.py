#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""Interactive roadmap / TODO dashboard generated from the SQLite dashboard store."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_bot.dashboards.data_store import load_todo_items, sync_all_if_needed, todo_stats
from trading_bot.dashboards.shared_ui import build_bar_chart
from trading_bot.dashboards.spot_dashboard import build_shared_style, nav

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = REPO_ROOT / "todo.html"

CATEGORY_COPY = {
    "research": "This stage improves signal quality, ranking confidence, and idea selection before capital gets reassigned.",
    "ops": "This stage hardens the runtime so the system behaves predictably across cron runs, restarts, and production incidents.",
    "risk": "This stage adds explicit safety rails so promotion and capital changes stay constrained by measurable checks.",
    "architecture": "This stage improves the plumbing behind the dashboard and manager so features stay durable instead of becoming one-off hacks.",
    "product": "This stage improves operator usability so decisions are faster, clearer, and easier to audit from the dashboard surface.",
    "done": "This roadmap stage is already completed and now acts as baseline capability for the next phase.",
    "other": "This roadmap stage supports the broader project path and should be reviewed in the context of nearby stages.",
}

NEXT_ACTION_COPY = {
    "open": "Treat this as upcoming work. Review the dependent outputs and implement the smallest production-safe next step.",
    "done": "No action needed unless the implementation has drifted and the summary needs to be revalidated.",
    "note": "Use this as live operating context rather than a build task. It should inform prioritization, not be toggled like feature work.",
}

CATEGORY_ORDER = ["research", "ops", "risk", "architecture", "product", "other", "done"]


def _escape(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )



def _status_label(status: str) -> str:
    return {
        "done": "Completed",
        "open": "Upcoming",
        "note": "Live note",
    }.get(status, status.title())



def _category_chart(items: list[dict[str, Any]]) -> str:
    open_items = [item for item in items if item.get("status") == "open"]
    counts: dict[str, int] = {}
    for item in open_items:
        category = ((item.get("payload") or {}) if isinstance(item.get("payload"), dict) else {}).get("category", "other")
        counts[category] = counts.get(category, 0) + 1
    palette = {
        "research": "#60a5fa",
        "ops": "#22c55e",
        "risk": "#f59e0b",
        "architecture": "#a855f7",
        "product": "#38bdf8",
        "other": "#94a3b8",
        "done": "#64748b",
    }
    rows = [
        {
            "label": category.title(),
            "value": counts[category],
            "color": palette.get(category, "#3b82f6"),
            "meta": f"{counts[category]} upcoming",
        }
        for category in CATEGORY_ORDER
        if counts.get(category)
    ]
    return build_bar_chart(rows, title="Upcoming work by theme", subtitle="What the remaining roadmap is concentrated on", value_suffix="")



def _detail_text(item: dict[str, Any]) -> str:
    payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
    category = payload.get("category", "other")
    status = item.get("status", "open")
    text = str(item.get("text", "")).strip()
    stage = int(item.get("sort_order", 0)) + 1
    base = CATEGORY_COPY.get(category, CATEGORY_COPY["other"])
    next_step = NEXT_ACTION_COPY.get(status, NEXT_ACTION_COPY["open"])
    return f"Stage #{stage}: {text} {base} {next_step}"



def _todo_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
    stats = todo_stats(items)
    ordered_items: list[dict[str, Any]] = []
    for item in items:
        payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
        category = payload.get("category", "other")
        source_name = Path(str(item.get("source_file") or "")).name or "dashboard.sqlite"
        stage_number = int(item.get("sort_order", 0)) + 1
        ordered_items.append(
            {
                "item_key": str(item.get("item_key", "")),
                "stage_number": stage_number,
                "sort_order": int(item.get("sort_order", 0)),
                "text": str(item.get("text", "")).strip(),
                "notes": str(item.get("notes", "") or "").strip(),
                "status": str(item.get("status", "open")),
                "base_status": str(item.get("base_status", item.get("status", "open"))),
                "section": str(item.get("section", "")),
                "category": category,
                "source_file": source_name,
                "detail": _detail_text(item),
                "status_label": _status_label(str(item.get("status", "open"))),
                "can_toggle": str(item.get("base_status", item.get("status", "open"))) == "open",
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "items": ordered_items,
    }



def build_todo_page() -> None:
    sync_all_if_needed(min_interval=5.0)
    items = load_todo_items()
    payload = _todo_payload(items)
    stats = payload["stats"]
    open_items = [item for item in payload["items"] if item["status"] == "open"]
    focus = open_items[0] if open_items else None
    focus_text = focus["text"] if focus else "Nothing queued — the current roadmap is clear."
    focus_badge = f"Stage #{focus['stage_number']} is next" if focus else "All clear"
    categories_html = _category_chart(items)
    initial_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    done = int(stats.get("done", 0))
    open_count = int(stats.get("open", 0))
    notes = int(stats.get("notes", 0))
    total = int(stats.get("total", 0))
    pct = float(stats.get("completion_pct", 0.0))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="120">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project Roadmap / TODO</title>
    <style>
        {build_shared_style('#22c55e')}
        .hero {{ display:grid; grid-template-columns:1.25fr .95fr; gap:16px; margin-bottom:18px; align-items:stretch; }}
        .hero-card, .surface-card, .timeline-shell {{ background:#1e293b; border:1px solid #334155; border-radius:18px; padding:18px; box-shadow:0 12px 30px rgba(15,23,42,.24); }}
        .hero-card h2 {{ font-size:26px; margin-bottom:6px; }}
        .hero-card p {{ color:#94a3b8; line-height:1.68; }}
        .focus-box {{ margin-top:14px; padding:16px 18px; background:#0f172a; border:1px solid #334155; border-radius:16px; }}
        .focus-label {{ color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:.7px; margin-bottom:6px; }}
        .focus-text {{ font-size:14px; line-height:1.7; color:#e2e8f0; }}
        .legend {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }}
        .legend-pill {{ padding:6px 10px; border-radius:999px; background:#0f172a; border:1px solid #334155; color:#94a3b8; font-size:11px; }}
        .stats-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin:18px 0; }}
        .stat-card {{ background:#1e293b; border-radius:14px; padding:16px 18px; border:1px solid #334155; }}
        .stat-card .label {{ color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:.6px; }}
        .stat-card .value {{ font-size:28px; font-weight:800; margin-top:4px; font-variant-numeric:tabular-nums; }}
        .stat-card .sub {{ color:#64748b; font-size:12px; margin-top:4px; }}
        .progress-meta-card {{ display:flex; flex-direction:column; gap:14px; }}
        .progress-card {{ display:flex; flex-direction:column; gap:16px; height:100%; }}
        .progress-card-head {{ display:flex; justify-content:space-between; gap:10px; align-items:flex-start; flex-wrap:wrap; }}
        .progress-card-head strong {{ font-size:14px; }}
        .progress-note {{ color:#94a3b8; font-size:12px; line-height:1.55; max-width:300px; }}
        .progress-donut-shell {{ display:grid; grid-template-columns:minmax(0, 220px) minmax(0, 1fr); gap:18px; align-items:center; }}
        .progress-donut {{ width:220px; height:220px; padding:18px; display:grid; place-items:center; position:relative; margin:0 auto; }}
        .progress-donut::after {{ content:''; position:absolute; inset:34px; border-radius:50%; background:#0f172a; box-shadow:inset 0 0 0 1px #334155; }}
        .progress-svg {{ width:220px; height:220px; overflow:visible; display:block; }}
        .progress-arc {{ fill:none; stroke-width:18; stroke-linecap:round; transform:rotate(-90deg); transform-origin:50% 50%; transition:stroke-dasharray .28s ease, stroke-dashoffset .28s ease; }}
        .progress-center {{ position:absolute; inset:0; display:grid; place-items:center; z-index:1; text-align:center; pointer-events:none; }}
        .progress-center strong {{ display:block; font-size:24px; line-height:1.1; color:#e2e8f0; }}
        .progress-center span {{ display:block; margin-top:4px; color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:.7px; }}
        .progress-legend {{ display:flex; flex-direction:column; gap:10px; }}
        .progress-row {{ display:grid; grid-template-columns:14px 1fr auto; gap:10px; align-items:center; padding:10px 12px; border-radius:14px; background:#0f172a; border:1px solid #334155; }}
        .progress-row .dot {{ width:14px; height:14px; border-radius:999px; display:inline-block; }}
        .progress-row .meta {{ display:flex; gap:10px; align-items:baseline; color:#94a3b8; font-size:12px; }}
        .progress-row .meta strong {{ color:#e2e8f0; font-size:14px; }}
        .progress-bar-wrap {{ background:#1e293b; border:1px solid #334155; border-radius:16px; padding:16px 18px; margin-bottom:18px; }}
        .progress-head {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; align-items:center; margin-bottom:10px; }}
        .progress-head strong {{ font-size:14px; }}
        .progress-head .mini-note {{ font-size:12px; color:#94a3b8; }}
        .progress-track {{ height:10px; background:#0f172a; border-radius:999px; overflow:hidden; box-shadow:inset 0 0 0 1px #334155; }}
        .progress-fill {{ height:100%; width:{pct:.1f}%; background:linear-gradient(90deg,#22c55e,#60a5fa); border-radius:999px; transition:width .28s ease; }}
        .insight-grid {{ display:grid; grid-template-columns:1.15fr .85fr; gap:16px; margin-bottom:18px; align-items:stretch; }}
        .chart-card .chart-head {{ align-items:flex-start; }}
        .surface-card h3 {{ margin:0 0 8px; font-size:15px; }}
        .surface-card p {{ margin:0; color:#94a3b8; line-height:1.7; font-size:13px; }}
        .surface-list {{ display:grid; gap:10px; margin-top:12px; }}
        .surface-list-item {{ padding:12px 14px; background:#0f172a; border:1px solid #334155; border-radius:14px; color:#cbd5e1; font-size:13px; line-height:1.65; }}
        .timeline-shell {{ margin-bottom:18px; }}
        .toolbar {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; align-items:center; margin-bottom:14px; }}
        .toolbar-left {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
        .search-input {{ width:min(380px,100%); background:#0f172a; border:1px solid #334155; color:#e2e8f0; padding:11px 12px; border-radius:12px; font-size:13px; outline:none; }}
        .search-input:focus {{ border-color:#22c55e; box-shadow:0 0 0 3px rgba(34,197,94,.14); }}
        .chip-row {{ display:flex; flex-wrap:wrap; gap:8px; }}
        .chip {{ padding:8px 12px; border-radius:999px; background:#0f172a; border:1px solid #334155; color:#cbd5e1; font-size:12px; cursor:pointer; user-select:none; }}
        .chip.active {{ background:#22c55e22; border-color:#22c55e55; color:#86efac; }}
        .chip:hover {{ border-color:#475569; }}
        .timeline {{ position:relative; display:grid; gap:16px; }}
        .timeline::before {{ content:''; position:absolute; top:4px; bottom:4px; left:26px; width:2px; background:linear-gradient(180deg,#22c55e55,#334155); border-radius:999px; }}
        .timeline-group {{ display:grid; gap:12px; }}
        .timeline-group-head {{ display:flex; justify-content:space-between; gap:10px; align-items:center; padding-left:54px; margin-top:4px; }}
        .timeline-group-head strong {{ font-size:14px; }}
        .timeline-group-head span {{ color:#94a3b8; font-size:12px; }}
        .timeline-item {{ position:relative; width:100%; text-align:left; border:none; cursor:pointer; background:transparent; padding:0 0 0 54px; }}
        .timeline-item:focus-visible .timeline-card {{ outline:2px solid #60a5fa; outline-offset:2px; }}
        .timeline-marker {{ position:absolute; left:16px; top:18px; width:20px; height:20px; border-radius:999px; border:3px solid #0f172a; box-shadow:0 0 0 1px #334155; background:#60a5fa; z-index:1; }}
        .timeline-item[data-status="done"] .timeline-marker {{ background:#22c55e; }}
        .timeline-item[data-status="note"] .timeline-marker {{ background:#94a3b8; }}
        .timeline-card {{ background:#0f172a; border:1px solid #334155; border-radius:18px; padding:14px 16px; transition:transform .15s ease, border-color .15s ease, background .15s ease, opacity .15s ease; }}
        .timeline-item:hover .timeline-card {{ transform:translateY(-1px); border-color:#475569; background:#101b31; }}
        .timeline-item[data-status="done"] .timeline-card {{ opacity:.78; }}
        .timeline-head {{ display:flex; justify-content:space-between; gap:10px; align-items:flex-start; margin-bottom:10px; }}
        .timeline-title-wrap {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
        .timeline-stage {{ display:inline-flex; align-items:center; justify-content:center; min-width:44px; height:26px; padding:0 10px; border-radius:999px; background:#22c55e22; color:#86efac; font-weight:800; font-size:11px; }}
        .timeline-pill {{ font-size:11px; padding:4px 9px; border-radius:999px; border:1px solid #334155; color:#cbd5e1; background:#111827; }}
        .timeline-pill.status-open {{ color:#93c5fd; background:#3b82f61a; border-color:#3b82f644; }}
        .timeline-pill.status-done {{ color:#86efac; background:#22c55e1a; border-color:#22c55e44; }}
        .timeline-pill.status-note {{ color:#cbd5e1; background:#334155; border-color:#475569; }}
        .timeline-text {{ color:#e2e8f0; font-size:14px; line-height:1.7; margin-bottom:10px; }}
        .timeline-sub {{ color:#94a3b8; font-size:12px; line-height:1.6; margin-bottom:12px; }}
        .timeline-meta {{ display:flex; gap:10px 14px; flex-wrap:wrap; color:#64748b; font-size:11px; }}
        .empty-state {{ text-align:center; color:#64748b; padding:28px 14px; font-size:13px; background:#0f172a; border:1px dashed #334155; border-radius:16px; }}
        .modal-backdrop {{ position:fixed; inset:0; background:rgba(2,6,23,.72); backdrop-filter:blur(8px); display:none; align-items:center; justify-content:center; padding:18px; z-index:9999; }}
        .modal-backdrop.open {{ display:flex; }}
        .modal-card {{ width:min(760px, 100%); max-height:min(86vh, 860px); overflow:auto; background:#0f172a; border:1px solid #334155; border-radius:24px; box-shadow:0 24px 80px rgba(2,6,23,.55); padding:20px; }}
        .modal-head {{ display:flex; justify-content:space-between; gap:14px; align-items:flex-start; margin-bottom:16px; }}
        .modal-head h3 {{ margin:0; font-size:22px; line-height:1.25; }}
        .modal-close {{ border:none; background:#111827; color:#cbd5e1; width:38px; height:38px; border-radius:999px; cursor:pointer; font-size:18px; border:1px solid #334155; }}
        .modal-close:hover {{ border-color:#475569; }}
        .modal-pills {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }}
        .modal-body {{ display:grid; gap:16px; }}
        .modal-panel {{ background:#111827; border:1px solid #1f2937; border-radius:18px; padding:16px; }}
        .modal-panel h4 {{ margin:0 0 8px; font-size:13px; color:#e2e8f0; }}
        .modal-panel p {{ margin:0; color:#cbd5e1; line-height:1.72; font-size:14px; }}
        .modal-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }}
        .modal-kv {{ background:#0b1220; border:1px solid #1f2937; border-radius:14px; padding:12px; }}
        .modal-kv .k {{ color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:.6px; }}
        .modal-kv .v {{ color:#e2e8f0; font-size:14px; margin-top:6px; line-height:1.45; }}
        .modal-actions {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; align-items:center; padding-top:4px; }}
        .action-btn {{ border:none; border-radius:12px; padding:11px 14px; cursor:pointer; font-size:13px; font-weight:700; }}
        .action-primary {{ background:#22c55e; color:#052e16; }}
        .action-secondary {{ background:#111827; color:#cbd5e1; border:1px solid #334155; }}
        .modal-footnote {{ color:#64748b; font-size:12px; }}
        @media (max-width: 980px) {{
            .hero, .insight-grid, .progress-donut-shell {{ grid-template-columns:1fr; }}
            .progress-note {{ max-width:none; }}
        }}
        @media (max-width: 640px) {{
            .nav a {{ width:100%; text-align:center; }}
            .search-input {{ width:100%; }}
            .timeline-item {{ padding-left:46px; }}
            .timeline-group-head {{ padding-left:46px; }}
            .timeline::before {{ left:22px; }}
            .timeline-marker {{ left:12px; }}
            .modal-card {{ padding:16px; border-radius:20px; }}
            .progress-donut, .progress-svg {{ width:200px; height:200px; }}
        }}
    </style>
    <script>
    const INITIAL_TODO_DATA = {initial_json};
    const CATEGORY_ORDER = {json.dumps(CATEGORY_ORDER)};
    const STATUS_ORDER = {{ open: 0, note: 1, done: 2 }};
    const state = {{
        allItems: [],
        search: '',
        status: 'all',
        category: 'all',
        modalKey: null,
    }};

    function escapeHtml(value) {{
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }}

    function sortedItems(items) {{
        return [...items].sort((a, b) => {{
            const left = STATUS_ORDER[a.status] ?? 99;
            const right = STATUS_ORDER[b.status] ?? 99;
            if (left !== right) return left - right;
            return Number(a.stage_number || 0) - Number(b.stage_number || 0);
        }});
    }}

    function currentStats(items) {{
        const total = items.length;
        const done = items.filter((item) => item.status === 'done').length;
        const open = items.filter((item) => item.status === 'open').length;
        const notes = items.filter((item) => item.status === 'note').length;
        return {{ total, done, open, notes, completion_pct: total ? (done / total) * 100 : 0 }};
    }}

    function filteredItems() {{
        const query = state.search.trim().toLowerCase();
        return sortedItems(state.allItems).filter((item) => {{
            const matchStatus = state.status === 'all' || item.status === state.status;
            const matchCategory = state.category === 'all' || item.category === state.category;
            const blob = [
                item.text,
                item.detail,
                item.category,
                item.section,
                item.source_file,
                `stage ${{item.stage_number}}`,
                `#${{item.stage_number}}`,
            ].join(' ').toLowerCase();
            const matchSearch = !query || blob.includes(query);
            return matchStatus && matchCategory && matchSearch;
        }});
    }}

    function setChipGroupActive(groupName, value) {{
        document.querySelectorAll(`[data-chip-group="${{groupName}}"] .chip`).forEach((chip) => {{
            chip.classList.toggle('active', chip.dataset.value === value);
        }});
    }}

    function renderCategoryChips() {{
        const holder = document.getElementById('category-chip-row');
        if (!holder) return;
        const counts = new Map();
        state.allItems.forEach((item) => counts.set(item.category, (counts.get(item.category) || 0) + 1));
        const categories = CATEGORY_ORDER.filter((key) => counts.has(key));
        holder.innerHTML = [
            `<span class="chip ${{state.category === 'all' ? 'active' : ''}}" data-value="all">All themes</span>`,
            ...categories.map((category) => `<span class="chip ${{state.category === category ? 'active' : ''}}" data-value="${{escapeHtml(category)}}">${{escapeHtml(category.charAt(0).toUpperCase() + category.slice(1))}}</span>`),
        ].join('');
    }}

    function updateProgressDonut(stats) {{
        const circumference = 2 * Math.PI * 56;
        const segments = [
            {{ id: 'progress-arc-done', value: stats.done }},
            {{ id: 'progress-arc-open', value: stats.open }},
            {{ id: 'progress-arc-note', value: stats.notes }},
        ];
        const total = Math.max(stats.total, 1);
        let cursor = 0;
        segments.forEach((segment) => {{
            const circle = document.getElementById(segment.id);
            if (!circle) return;
            const dash = Math.max((segment.value / total) * circumference, segment.value > 0 ? 0.0001 : 0);
            const gap = Math.max(circumference - dash, 0);
            circle.setAttribute('stroke-dasharray', `${{dash}} ${{gap}}`);
            circle.setAttribute('stroke-dashoffset', `${{-cursor}}`);
            cursor += dash;
        }});
        const setText = (id, value) => {{ const el = document.getElementById(id); if (el) el.textContent = value; }};
        setText('progress-center-value', `${{Math.round(stats.completion_pct)}}%`);
        setText('progress-center-label', stats.done ? 'complete' : 'starting');
        setText('progress-done-count', String(stats.done));
        setText('progress-open-count', String(stats.open));
        setText('progress-note-count', String(stats.notes));
    }}

    function updateSummary() {{
        const stats = currentStats(state.allItems);
        const setText = (id, value) => {{ const el = document.getElementById(id); if (el) el.textContent = value; }};
        setText('stat-total', String(stats.total));
        setText('stat-done', String(stats.done));
        setText('stat-open', String(stats.open));
        setText('stat-notes', String(stats.notes));
        setText('progress-text', `${{stats.done}}/${{stats.total}} complete`);
        const progressFill = document.getElementById('progress-fill');
        if (progressFill) progressFill.style.width = `${{Math.max(0, Math.min(stats.completion_pct, 100)).toFixed(1)}}%`;
        updateProgressDonut(stats);
        const focus = sortedItems(state.allItems).find((item) => item.status === 'open');
        setText('focus-text', focus ? focus.text : 'Nothing queued — the current roadmap is clear.');
        setText('focus-badge', focus ? `Stage #${{focus.stage_number}} is next` : 'All clear');
    }}

    function groupMarkup(title, subtitle, items) {{
        if (!items.length) return '';
        return `
            <section class="timeline-group">
                <div class="timeline-group-head">
                    <strong>${{escapeHtml(title)}}</strong>
                    <span>${{escapeHtml(subtitle)}}</span>
                </div>
                ${{items.map((item) => itemMarkup(item)).join('')}}
            </section>
        `;
    }}

    function itemMarkup(item) {{
        const teaser = item.detail || item.text;
        return `
            <button class="timeline-item" type="button" data-key="${{escapeHtml(item.item_key)}}" data-status="${{escapeHtml(item.status)}}">
                <span class="timeline-marker" aria-hidden="true"></span>
                <div class="timeline-card">
                    <div class="timeline-head">
                        <div class="timeline-title-wrap">
                            <span class="timeline-stage">#${{escapeHtml(item.stage_number)}}</span>
                            <span class="timeline-pill status-${{escapeHtml(item.status)}}">${{escapeHtml(item.status_label)}}</span>
                            <span class="timeline-pill">${{escapeHtml(item.category.charAt(0).toUpperCase() + item.category.slice(1))}}</span>
                        </div>
                        <span class="timeline-pill">${{escapeHtml(item.source_file)}}</span>
                    </div>
                    <div class="timeline-text">${{escapeHtml(item.text)}}</div>
                    <div class="timeline-sub">${{escapeHtml(teaser)}}</div>
                    <div class="timeline-meta">
                        <span>Stage ${{escapeHtml(item.stage_number)}}</span>
                        <span>Section: ${{escapeHtml(item.section)}}</span>
                        <span>${{item.can_toggle ? 'Stored in DB-backed dashboard state' : 'Locked from source summary as completed'}}</span>
                    </div>
                </div>
            </button>
        `;
    }}

    function renderTimeline() {{
        const holder = document.getElementById('todo-timeline');
        const empty = document.getElementById('todo-empty');
        if (!holder || !empty) return;
        const items = filteredItems();
        if (!items.length) {{
            holder.innerHTML = '';
            empty.style.display = 'block';
            return;
        }}
        empty.style.display = 'none';
        const upcoming = items.filter((item) => item.status === 'open');
        const notes = items.filter((item) => item.status === 'note');
        const done = items.filter((item) => item.status === 'done');
        holder.innerHTML = [
            groupMarkup('Upcoming work', `${{upcoming.length}} items still to complete`, upcoming),
            groupMarkup('Live notes', `${{notes.length}} context items`, notes),
            groupMarkup('Completed work', `${{done.length}} shipped stages`, done),
        ].filter(Boolean).join('');
    }}

    function renderAll() {{
        renderCategoryChips();
        setChipGroupActive('status', state.status);
        updateSummary();
        renderTimeline();
        if (state.modalKey) openModal(state.modalKey, false);
    }}

    async function persistTaskState(itemKey, status) {{
        if (!window.location.origin.startsWith('http')) return;
        try {{
            await fetch('/api/todo-state', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ item_key: itemKey, status }}),
            }});
        }} catch (error) {{
            console.log('todo state sync failed', error);
        }}
    }}

    async function toggleTask(itemKey) {{
        const target = state.allItems.find((item) => item.item_key === itemKey);
        if (!target || !target.can_toggle) return;
        const nextStatus = target.status === 'done' ? 'open' : 'done';
        state.allItems = state.allItems.map((item) => item.item_key === itemKey ? {{ ...item, status: nextStatus, status_label: nextStatus === 'done' ? 'Completed' : 'Upcoming' }} : item);
        renderAll();
        await persistTaskState(itemKey, nextStatus);
    }}

    function openModal(itemKey, scrollIntoView = true) {{
        const item = state.allItems.find((entry) => entry.item_key === itemKey);
        const modal = document.getElementById('todo-modal');
        if (!item || !modal) return;
        state.modalKey = itemKey;
        const setText = (id, value) => {{ const el = document.getElementById(id); if (el) el.textContent = value; }};
        setText('modal-title', item.text);
        setText('modal-stage', `#${{item.stage_number}}`);
        setText('modal-status', item.status_label);
        setText('modal-category', item.category.charAt(0).toUpperCase() + item.category.slice(1));
        setText('modal-detail', item.detail);
        setText('modal-next', item.status === 'done'
            ? 'This stage is already resolved. Only revisit it if the implementation drifted or the roadmap source needs correction.'
            : item.status === 'note'
                ? 'Keep this as operating context while prioritizing upcoming roadmap items.'
                : 'Use this as the next actionable roadmap stage and complete the smallest safe implementation slice first.');
        setText('modal-source', item.source_file);
        setText('modal-section', item.section);
        setText('modal-stage-kv', String(item.stage_number));
        setText('modal-db', item.can_toggle ? 'Toggle synced through SQLite-backed dashboard state' : 'Locked by source summary');
        const toggleBtn = document.getElementById('modal-toggle-btn');
        if (toggleBtn) {{
            toggleBtn.style.display = item.can_toggle ? '' : 'none';
            toggleBtn.textContent = item.status === 'done' ? 'Move back to upcoming' : 'Mark as completed';
            toggleBtn.dataset.key = item.item_key;
        }}
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
        if (scrollIntoView) modal.querySelector('.modal-card')?.scrollTo({{ top: 0, behavior: 'instant' }});
    }}

    function closeModal() {{
        const modal = document.getElementById('todo-modal');
        if (!modal) return;
        modal.classList.remove('open');
        document.body.style.overflow = '';
        state.modalKey = null;
    }}

    async function hydrateFromApi() {{
        if (!window.location.origin.startsWith('http')) return;
        try {{
            const response = await fetch('/api/todo-data', {{ cache: 'no-store' }});
            const payload = await response.json();
            state.allItems = Array.isArray(payload?.items) ? payload.items : [];
            renderAll();
        }} catch (error) {{
            console.log('todo data hydrate failed', error);
        }}
    }}

    function clearFilters() {{
        state.search = '';
        state.status = 'all';
        state.category = 'all';
        const search = document.getElementById('todo-search');
        if (search) search.value = '';
        renderAll();
    }}

    window.addEventListener('DOMContentLoaded', async () => {{
        state.allItems = Array.isArray(INITIAL_TODO_DATA.items) ? INITIAL_TODO_DATA.items : [];
        renderAll();

        document.getElementById('todo-search')?.addEventListener('input', (event) => {{
            state.search = event.target.value || '';
            renderTimeline();
        }});

        document.querySelector('[data-chip-group="status"]')?.addEventListener('click', (event) => {{
            const chip = event.target.closest('.chip');
            if (!chip) return;
            state.status = chip.dataset.value || 'all';
            renderAll();
        }});

        document.getElementById('category-chip-row')?.addEventListener('click', (event) => {{
            const chip = event.target.closest('.chip');
            if (!chip) return;
            state.category = chip.dataset.value || 'all';
            renderAll();
        }});

        document.getElementById('todo-timeline')?.addEventListener('click', (event) => {{
            const item = event.target.closest('.timeline-item');
            if (!item) return;
            openModal(item.dataset.key || '');
        }});

        document.getElementById('modal-close-btn')?.addEventListener('click', closeModal);
        document.getElementById('todo-modal')?.addEventListener('click', (event) => {{
            if (event.target.id === 'todo-modal') closeModal();
        }});
        document.getElementById('modal-toggle-btn')?.addEventListener('click', async (event) => {{
            const itemKey = event.currentTarget.dataset.key || '';
            if (!itemKey) return;
            await toggleTask(itemKey);
            openModal(itemKey, false);
        }});
        document.getElementById('reset-filters-btn')?.addEventListener('click', clearFilters);
        window.addEventListener('keydown', (event) => {{
            if (event.key === 'Escape') closeModal();
        }});

        await hydrateFromApi();
    }});
    </script>
</head>
<body>
    <div class="page-shell">
    <div class="page-header">
        <h1>🗒 Project Roadmap / TODO</h1>
        <p class="subtitle">A database-backed roadmap timeline with completion sync, cleaner priority ordering, and drill-down detail for every stage.</p>
    </div>
    {nav('todo')}

    <div class="hero">
        <div class="hero-card">
            <h2>Stage the roadmap like an operator, not a checklist</h2>
            <p>
                The TODO page now reads from the dashboard database, keeps duplicate summary rows out of the timeline,
                pushes unfinished stages to the top, and opens every roadmap item in a detail modal so you can understand
                why it matters before touching the code.
            </p>
            <div class="focus-box">
                <div class="focus-label">Current focus</div>
                <div class="focus-text" id="focus-text">{_escape(focus_text)}</div>
            </div>
            <div class="legend">
                <span class="legend-pill">Timeline layout</span>
                <span class="legend-pill">Modal drill-downs</span>
                <span class="legend-pill">SQLite-backed state</span>
                <span class="legend-pill" id="focus-badge">{_escape(focus_badge)}</span>
            </div>
        </div>
        <div class="surface-card progress-card">
            <div class="progress-card-head">
                <div>
                    <strong>Roadmap progress</strong>
                    <div class="mini-note">Quick snapshot of the live roadmap state</div>
                </div>
                <div class="progress-note">The pie chart was rebuilt with a fixed donut shell so the progress arcs stay centered and legible while counts update.</div>
            </div>
            <div class="progress-donut-shell">
                <div class="progress-donut">
                    <svg class="progress-svg" viewBox="0 0 160 160" role="img" aria-label="Roadmap progress">
                        <circle cx="80" cy="80" r="56" fill="none" stroke="#243244" stroke-width="18"></circle>
                        <circle id="progress-arc-done" class="progress-arc" cx="80" cy="80" r="56" stroke="#22c55e"></circle>
                        <circle id="progress-arc-open" class="progress-arc" cx="80" cy="80" r="56" stroke="#60a5fa"></circle>
                        <circle id="progress-arc-note" class="progress-arc" cx="80" cy="80" r="56" stroke="#94a3b8"></circle>
                    </svg>
                    <div class="progress-center">
                        <div>
                            <strong id="progress-center-value">{pct:.0f}%</strong>
                            <span id="progress-center-label">{'complete' if done else 'starting'}</span>
                        </div>
                    </div>
                </div>
                <div class="progress-legend">
                    <div class="progress-row">
                        <span class="dot" style="background:#22c55e"></span>
                        <span>Completed</span>
                        <span class="meta"><strong id="progress-done-count">{done}</strong><span>done</span></span>
                    </div>
                    <div class="progress-row">
                        <span class="dot" style="background:#60a5fa"></span>
                        <span>Upcoming</span>
                        <span class="meta"><strong id="progress-open-count">{open_count}</strong><span>open</span></span>
                    </div>
                    <div class="progress-row">
                        <span class="dot" style="background:#94a3b8"></span>
                        <span>Live notes</span>
                        <span class="meta"><strong id="progress-note-count">{notes}</strong><span>notes</span></span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="stats-grid">
        <div class="stat-card"><div class="label">Total</div><div class="value" id="stat-total">{total}</div><div class="sub">roadmap items in the current store</div></div>
        <div class="stat-card"><div class="label">Done</div><div class="value" id="stat-done">{done}</div><div class="sub">completed items pushed to the bottom</div></div>
        <div class="stat-card"><div class="label">Upcoming</div><div class="value" id="stat-open">{open_count}</div><div class="sub">next stages waiting for action</div></div>
        <div class="stat-card"><div class="label">Notes</div><div class="value" id="stat-notes">{notes}</div><div class="sub">live context items for the operator</div></div>
    </div>

    <div class="progress-bar-wrap">
        <div class="progress-head">
            <strong>Completion</strong>
            <div class="mini-note"><span id="progress-text">{done}/{total} complete</span> · synced through the dashboard store</div>
        </div>
        <div class="progress-track"><div class="progress-fill" id="progress-fill"></div></div>
    </div>

    <div class="insight-grid">
        {categories_html}
        <div class="surface-card">
            <h3>How to use this page</h3>
            <p>This layout is optimized for quickly processing what comes next, while still preserving deeper context on click.</p>
            <div class="surface-list">
                <div class="surface-list-item">Upcoming items stay at the top and preserve stage order so the next move is obvious.</div>
                <div class="surface-list-item">Completed stages are automatically pushed down, reducing scan noise during execution.</div>
                <div class="surface-list-item">Each roadmap card opens a modal with more detail and a status toggle when the item is not locked as source-complete.</div>
            </div>
        </div>
    </div>

    <div class="timeline-shell">
        <div class="toolbar">
            <div class="toolbar-left">
                <input id="todo-search" class="search-input" placeholder="Search stage numbers, roadmap text, categories, sections, or sources..." />
                <button class="chip" id="reset-filters-btn" type="button">Reset filters</button>
            </div>
            <div class="chip-row" data-chip-group="status">
                <span class="chip active" data-value="all">All</span>
                <span class="chip" data-value="open">Upcoming</span>
                <span class="chip" data-value="note">Notes</span>
                <span class="chip" data-value="done">Completed</span>
            </div>
        </div>
        <div class="toolbar">
            <div class="chip-row" id="category-chip-row" data-chip-group="category"></div>
        </div>
        <div class="timeline" id="todo-timeline"></div>
        <div class="empty-state" id="todo-empty" style="display:none;">No roadmap items matched the current filters.</div>
    </div>

    <p class="footer-note" style="color:#64748b;font-size:12px;margin-top:10px;">
        Source: {REPO_ROOT / 'data' / 'dashboard.sqlite'} · page shell generated locally, roadmap data loaded from the dashboard store.
    </p>
    </div>

    <div class="modal-backdrop" id="todo-modal" aria-hidden="true">
        <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title">
            <div class="modal-head">
                <div>
                    <h3 id="modal-title">Roadmap item</h3>
                    <div class="modal-pills">
                        <span class="timeline-stage" id="modal-stage">#0</span>
                        <span class="timeline-pill" id="modal-status">Upcoming</span>
                        <span class="timeline-pill" id="modal-category">Product</span>
                    </div>
                </div>
                <button class="modal-close" id="modal-close-btn" type="button" aria-label="Close">×</button>
            </div>
            <div class="modal-body">
                <div class="modal-panel">
                    <h4>What this stage means</h4>
                    <p id="modal-detail"></p>
                </div>
                <div class="modal-panel">
                    <h4>Operator next step</h4>
                    <p id="modal-next"></p>
                </div>
                <div class="modal-grid">
                    <div class="modal-kv"><div class="k">Source</div><div class="v" id="modal-source"></div></div>
                    <div class="modal-kv"><div class="k">Section</div><div class="v" id="modal-section"></div></div>
                    <div class="modal-kv"><div class="k">Stage number</div><div class="v" id="modal-stage-kv"></div></div>
                    <div class="modal-kv"><div class="k">State persistence</div><div class="v" id="modal-db"></div></div>
                </div>
                <div class="modal-actions">
                    <div class="modal-footnote">Completion changes are stored in the dashboard SQLite flow so the roadmap stays consistent across refreshes.</div>
                    <div style="display:flex; gap:10px; flex-wrap:wrap;">
                        <button class="action-btn action-secondary" type="button" onclick="closeModal()">Close</button>
                        <button class="action-btn action-primary" id="modal-toggle-btn" type="button">Mark as completed</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""
    OUTPUT.write_text(html)
    print(f"✅ Roadmap page generated: {OUTPUT}")



def main() -> None:
    build_todo_page()


if __name__ == "__main__":
    main()
