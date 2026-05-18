#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""Timeline-style roadmap / TODO dashboard backed by the shared runtime data store."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_bot.dashboards.data_store import load_todo_items, sync_all_if_needed, todo_stats
from trading_bot.dashboards.spot_dashboard import build_shared_style, nav

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = REPO_ROOT / "todo.html"

STATUS_COPY = {
    "open": "Treat this as upcoming work. Execute the smallest safe next step after checking dependencies and current runtime state.",
    "done": "This item is already complete. Re-open it only if the implementation has drifted or the roadmap summary is stale.",
}

SOURCE_COPY = {
    "roadmap_summary.yml": "Synced from the roadmap summary file.",
    "runtime_state.json": "User-added todo stored in the shared runtime data store.",
}


def _escape(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _status_label(status: str) -> str:
    return {"done": "Completed", "open": "Upcoming"}.get(status, status.title())


def _detail_text(item: dict[str, Any]) -> str:
    status = str(item.get("status") or "open")
    notes = str(item.get("notes") or "").strip()
    source_name = Path(str(item.get("source_file") or "runtime_state.json")).name or "runtime_state.json"
    source_copy = SOURCE_COPY.get(source_name, "Stored in the dashboard data store.")
    parts = [f"Stage #{int(item.get('sort_order', 0)) + 1}", source_copy, STATUS_COPY.get(status, STATUS_COPY["open"])]
    if notes:
        parts.insert(1, notes)
    return " ".join(part for part in parts if part)


def _payload_item(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status") or "open")
    sort_order = int(item.get("sort_order", 0))
    source_name = Path(str(item.get("source_file") or "runtime_state.json")).name or "runtime_state.json"
    return {
        "item_key": str(item.get("item_key", "")),
        "stage_number": sort_order + 1,
        "sort_order": sort_order,
        "text": str(item.get("text", "")).strip(),
        "notes": str(item.get("notes", "") or "").strip(),
        "status": status,
        "base_status": str(item.get("base_status", status)),
        "status_label": _status_label(status),
        "can_toggle": str(item.get("base_status", status)) == "open",
        "detail": _detail_text(item),
        "source_file": source_name,
        "is_custom": bool(((item.get("payload") or {}) if isinstance(item.get("payload"), dict) else {}).get("is_custom")),
    }


def build_page(items: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    payload_items = [_payload_item(item) for item in items]
    bootstrap = json.dumps(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "items": payload_items,
        },
        ensure_ascii=False,
    )
    generated_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Trading Bot Roadmap</title>
  <style>{build_shared_style()}</style>
  <style>
    .todo-shell {{ display:grid; gap:18px; }}
    .hero-card, .stats-card, .composer-card, .timeline-card, .modal-card {{ background:linear-gradient(180deg, rgba(15,23,42,.96), rgba(2,6,23,.96)); border:1px solid rgba(148,163,184,.18); border-radius:22px; box-shadow:0 22px 48px rgba(2,6,23,.35); }}
    .hero-card {{ padding:24px; display:grid; grid-template-columns:minmax(0, 1.4fr) minmax(260px, .9fr); gap:20px; align-items:center; }}
    .eyebrow {{ color:#38bdf8; font-size:12px; font-weight:700; letter-spacing:.14em; text-transform:uppercase; margin-bottom:8px; }}
    .hero-title {{ margin:0; font-size:34px; line-height:1.05; }}
    .hero-copy {{ margin:12px 0 0; color:#cbd5e1; font-size:15px; line-height:1.7; max-width:760px; }}
    .hero-meta {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }}
    .hero-chip {{ border:1px solid rgba(96,165,250,.28); background:rgba(15,23,42,.75); color:#dbeafe; border-radius:999px; padding:8px 12px; font-size:12px; }}
    .progress-panel {{ display:grid; gap:14px; justify-items:center; }}
    .progress-ring {{ position:relative; width:220px; height:220px; border-radius:50%; background:conic-gradient(#22c55e 0deg, #22c55e var(--done-angle), rgba(59,130,246,.92) var(--done-angle), rgba(59,130,246,.92) 360deg); box-shadow:inset 0 0 0 1px rgba(148,163,184,.12), 0 18px 40px rgba(15,23,42,.42); }}
    .progress-ring::after {{ content:''; position:absolute; inset:22px; border-radius:50%; background:linear-gradient(180deg, rgba(15,23,42,.98), rgba(2,6,23,.98)); box-shadow:inset 0 0 0 1px rgba(148,163,184,.12); }}
    .progress-center {{ position:absolute; inset:0; z-index:1; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:22px; }}
    .progress-value {{ font-size:40px; font-weight:800; line-height:1; color:#f8fafc; }}
    .progress-caption {{ margin-top:8px; color:#94a3b8; font-size:12px; text-transform:uppercase; letter-spacing:.12em; }}
    .progress-summary {{ color:#cbd5e1; font-size:13px; text-align:center; max-width:220px; line-height:1.6; }}
    .stats-card {{ padding:18px; display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:12px; }}
    .stat-block {{ border:1px solid rgba(148,163,184,.12); border-radius:18px; padding:16px; background:rgba(15,23,42,.72); }}
    .stat-label {{ color:#94a3b8; font-size:12px; text-transform:uppercase; letter-spacing:.12em; }}
    .stat-value {{ margin-top:10px; font-size:28px; font-weight:800; color:#f8fafc; }}
    .stat-sub {{ margin-top:6px; color:#cbd5e1; font-size:13px; }}
    .composer-card {{ padding:18px; display:grid; gap:14px; }}
    .composer-head {{ display:flex; justify-content:space-between; gap:14px; align-items:end; flex-wrap:wrap; }}
    .card-title {{ margin:0; font-size:20px; }}
    .card-copy {{ margin:6px 0 0; color:#94a3b8; font-size:13px; line-height:1.6; }}
    .composer-grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.2fr) auto; gap:12px; align-items:end; }}
    .field {{ display:grid; gap:8px; }}
    .field label {{ color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:.14em; }}
    .field input, .field textarea {{ width:100%; border:1px solid rgba(71,85,105,.6); background:rgba(15,23,42,.88); color:#e2e8f0; border-radius:14px; padding:12px 14px; font:inherit; resize:vertical; }}
    .field input:focus, .field textarea:focus {{ outline:none; border-color:rgba(96,165,250,.8); box-shadow:0 0 0 3px rgba(59,130,246,.18); }}
    .composer-actions {{ display:flex; gap:10px; align-items:center; }}
    .btn-primary, .btn-ghost, .toggle-btn {{ border:1px solid rgba(96,165,250,.22); border-radius:14px; font:inherit; cursor:pointer; transition:transform .18s ease, background .18s ease, border-color .18s ease; }}
    .btn-primary {{ background:linear-gradient(135deg, #2563eb, #38bdf8); color:white; padding:12px 16px; font-weight:700; min-height:48px; }}
    .btn-ghost, .toggle-btn {{ background:rgba(15,23,42,.72); color:#dbeafe; padding:10px 14px; }}
    .btn-primary:hover, .btn-ghost:hover, .toggle-btn:hover {{ transform:translateY(-1px); border-color:rgba(125,211,252,.45); }}
    .btn-primary:disabled {{ opacity:.6; cursor:progress; transform:none; }}
    .composer-status {{ color:#93c5fd; font-size:13px; min-height:20px; }}
    .toolbar {{ display:flex; flex-wrap:wrap; justify-content:space-between; gap:12px; align-items:center; margin-bottom:14px; }}
    .toolbar-left {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; }}
    .search-input {{ min-width:240px; border:1px solid rgba(71,85,105,.6); background:rgba(15,23,42,.88); color:#e2e8f0; border-radius:14px; padding:11px 14px; font:inherit; }}
    .search-input:focus {{ outline:none; border-color:rgba(96,165,250,.8); box-shadow:0 0 0 3px rgba(59,130,246,.18); }}
    .filter-pills {{ display:flex; gap:8px; flex-wrap:wrap; }}
    .filter-pill {{ border:1px solid rgba(71,85,105,.5); background:rgba(15,23,42,.74); color:#cbd5e1; border-radius:999px; padding:9px 12px; cursor:pointer; font:inherit; font-size:12px; }}
    .filter-pill.active {{ color:#eff6ff; border-color:rgba(96,165,250,.55); background:rgba(37,99,235,.18); }}
    .timeline-card {{ padding:18px; }}
    .timeline-section + .timeline-section {{ margin-top:22px; padding-top:22px; border-top:1px solid rgba(148,163,184,.12); }}
    .section-head {{ display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:16px; }}
    .section-title {{ margin:0; font-size:18px; }}
    .section-count {{ color:#94a3b8; font-size:12px; text-transform:uppercase; letter-spacing:.12em; }}
    .timeline-list {{ position:relative; display:grid; gap:14px; }}
    .timeline-list::before {{ content:''; position:absolute; left:18px; top:8px; bottom:8px; width:2px; background:linear-gradient(180deg, rgba(56,189,248,.38), rgba(34,197,94,.18)); }}
    .timeline-item {{ position:relative; display:grid; grid-template-columns:auto minmax(0,1fr) auto; gap:14px; align-items:start; padding:16px 16px 16px 0; border:1px solid rgba(148,163,184,.12); border-radius:18px; background:rgba(15,23,42,.68); cursor:pointer; transition:transform .18s ease, border-color .18s ease, background .18s ease; }}
    .timeline-item:hover {{ transform:translateY(-1px); border-color:rgba(96,165,250,.3); background:rgba(15,23,42,.8); }}
    .timeline-dot-wrap {{ position:relative; width:38px; display:flex; justify-content:center; padding-top:4px; }}
    .timeline-dot {{ width:16px; height:16px; border-radius:50%; border:3px solid rgba(15,23,42,.95); box-shadow:0 0 0 4px rgba(59,130,246,.16); background:#3b82f6; z-index:1; }}
    .timeline-dot.done {{ background:#22c55e; box-shadow:0 0 0 4px rgba(34,197,94,.16); }}
    .item-main {{ display:grid; gap:8px; min-width:0; }}
    .item-meta {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
    .stage-chip, .status-chip, .source-chip {{ border-radius:999px; padding:6px 10px; font-size:11px; text-transform:uppercase; letter-spacing:.12em; }}
    .stage-chip {{ background:rgba(59,130,246,.15); color:#bfdbfe; border:1px solid rgba(96,165,250,.24); }}
    .status-chip.upcoming {{ background:rgba(59,130,246,.12); color:#dbeafe; border:1px solid rgba(96,165,250,.2); }}
    .status-chip.completed {{ background:rgba(34,197,94,.12); color:#bbf7d0; border:1px solid rgba(34,197,94,.24); }}
    .source-chip {{ background:rgba(148,163,184,.1); color:#cbd5e1; border:1px solid rgba(148,163,184,.18); }}
    .item-title {{ margin:0; font-size:17px; color:#f8fafc; line-height:1.45; }}
    .item-notes {{ margin:0; color:#94a3b8; font-size:14px; line-height:1.65; }}
    .item-actions {{ display:flex; flex-direction:column; gap:10px; align-items:end; min-width:130px; }}
    .toggle-btn.done {{ color:#bbf7d0; border-color:rgba(34,197,94,.24); }}
    .toggle-btn.reset {{ color:#dbeafe; border-color:rgba(96,165,250,.24); }}
    .empty-state {{ border:1px dashed rgba(148,163,184,.25); border-radius:18px; padding:18px; color:#94a3b8; text-align:center; }}
    .modal-backdrop {{ position:fixed; inset:0; background:rgba(2,6,23,.72); backdrop-filter:blur(8px); display:none; align-items:center; justify-content:center; padding:20px; z-index:90; }}
    .modal-backdrop.open {{ display:flex; }}
    .modal-card {{ width:min(760px, 100%); padding:22px; max-height:min(88vh, 920px); overflow:auto; }}
    .modal-head {{ display:flex; justify-content:space-between; gap:16px; align-items:start; }}
    .modal-close {{ border:none; background:transparent; color:#94a3b8; font-size:26px; cursor:pointer; line-height:1; padding:0; }}
    .modal-title {{ margin:10px 0 0; font-size:24px; line-height:1.3; }}
    .modal-grid {{ display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:12px; margin:18px 0; }}
    .modal-stat {{ border:1px solid rgba(148,163,184,.12); border-radius:16px; padding:12px; background:rgba(15,23,42,.72); }}
    .modal-label {{ color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:.12em; }}
    .modal-value {{ margin-top:8px; color:#f8fafc; font-size:16px; line-height:1.5; }}
    .modal-body {{ display:grid; gap:14px; color:#cbd5e1; font-size:15px; line-height:1.75; }}
    .modal-panel {{ border:1px solid rgba(148,163,184,.12); border-radius:18px; padding:14px; background:rgba(15,23,42,.68); }}
    .modal-panel h4 {{ margin:0 0 8px; font-size:13px; color:#94a3b8; text-transform:uppercase; letter-spacing:.12em; }}
    .modal-panel p {{ margin:0; white-space:pre-wrap; }}
    @media (max-width: 980px) {{
      .hero-card {{ grid-template-columns:1fr; }}
      .composer-grid {{ grid-template-columns:1fr; }}
      .timeline-item {{ grid-template-columns:auto minmax(0,1fr); }}
      .item-actions {{ grid-column:2; align-items:start; flex-direction:row; flex-wrap:wrap; }}
      .modal-grid {{ grid-template-columns:1fr; }}
    }}
    @media (max-width: 720px) {{
      .page-shell {{ padding:14px; }}
      .hero-title {{ font-size:28px; }}
      .stats-card {{ grid-template-columns:1fr; }}
      .toolbar {{ align-items:stretch; }}
      .toolbar-left {{ width:100%; }}
      .search-input {{ width:100%; min-width:0; }}
      .timeline-list::before {{ left:15px; }}
      .timeline-item {{ padding-right:12px; }}
    }}
  </style>
</head>
<body>
  <div class="page-shell">
    <div class="page-header">
      <h1>🗒 Roadmap & TODO</h1>
      <p class="subtitle">Prioritized execution timeline, completion tracking, and DB-backed todo capture for the trading-bot roadmap.</p>
    </div>
    {nav('todo')}
    <div class="todo-shell">
    <section class="hero-card">
      <div>
        <div class="eyebrow">Roadmap timeline</div>
        <h1 class="hero-title">Trading bot TODOs, now ordered for execution</h1>
        <p class="hero-copy">
          Upcoming work stays at the top in roadmap order, completed work falls below it, and every item opens a detail modal so you can inspect context before acting.
          New TODOs are stored in the dashboard database instead of being hardcoded into the page.
        </p>
        <div class="hero-meta">
          <span class="hero-chip">Generated {generated_label}</span>
          <span class="hero-chip">DB-backed roadmap</span>
          <span class="hero-chip">Timeline + modal drill-down</span>
        </div>
      </div>
      <div class="progress-panel">
        <div class="progress-ring" id="progress-ring" style="--done-angle: 0deg;">
          <div class="progress-center">
            <div class="progress-value" id="progress-value">0%</div>
            <div class="progress-caption">Completed</div>
          </div>
        </div>
        <div class="progress-summary" id="progress-summary">0 completed · 0 upcoming</div>
      </div>
    </section>

    <section class="stats-card" id="stats-grid">
      <div class="stat-block">
        <div class="stat-label">Total stages</div>
        <div class="stat-value" id="stat-total">0</div>
        <div class="stat-sub">Unified roadmap items tracked in the shared dashboard DB</div>
      </div>
      <div class="stat-block">
        <div class="stat-label">Upcoming</div>
        <div class="stat-value" id="stat-open">0</div>
        <div class="stat-sub">Prioritized at the top of the timeline</div>
      </div>
      <div class="stat-block">
        <div class="stat-label">Completed</div>
        <div class="stat-value" id="stat-done">0</div>
        <div class="stat-sub">Locked baseline items and manually completed work</div>
      </div>
    </section>

    <section class="composer-card">
      <div class="composer-head">
        <div>
          <h2 class="card-title">Add new TODO</h2>
          <p class="card-copy">Saved directly to the dashboard database, then appended to the roadmap timeline as the next stage.</p>
        </div>
        <div class="composer-status" id="composer-status"></div>
      </div>
      <form id="composer-form" class="composer-grid">
        <div class="field">
          <label for="todo-title">Title</label>
          <input id="todo-title" name="title" type="text" maxlength="220" placeholder="Example: Add live-trading readiness checklist" required />
        </div>
        <div class="field">
          <label for="todo-notes">Further context</label>
          <textarea id="todo-notes" name="notes" rows="2" maxlength="1200" placeholder="Add any detail you want to see in the modal later."></textarea>
        </div>
        <div class="composer-actions">
          <button class="btn-primary" id="composer-submit" type="submit">Save TODO</button>
        </div>
      </form>
    </section>

    <section class="timeline-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <input id="search-input" class="search-input" type="search" placeholder="Search stage title or notes" />
          <div class="filter-pills">
            <button class="filter-pill active" data-filter="all" type="button">All</button>
            <button class="filter-pill" data-filter="open" type="button">Upcoming</button>
            <button class="filter-pill" data-filter="done" type="button">Completed</button>
          </div>
        </div>
        <button class="btn-ghost" id="reload-btn" type="button">Reload from DB</button>
      </div>

      <div class="timeline-section">
        <div class="section-head">
          <h2 class="section-title">Upcoming</h2>
          <div class="section-count" id="upcoming-count">0 items</div>
        </div>
        <div class="timeline-list" id="upcoming-list"></div>
      </div>

      <div class="timeline-section">
        <div class="section-head">
          <h2 class="section-title">Completed</h2>
          <div class="section-count" id="completed-count">0 items</div>
        </div>
        <div class="timeline-list" id="completed-list"></div>
      </div>
    </section>
  </div>

  <div class="modal-backdrop" id="todo-modal" aria-hidden="true">
    <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div class="modal-head">
        <div>
          <div class="eyebrow" id="modal-eyebrow">Stage details</div>
          <h3 class="modal-title" id="modal-title">TODO detail</h3>
        </div>
        <button class="modal-close" id="modal-close" type="button" aria-label="Close">×</button>
      </div>
      <div class="modal-grid">
        <div class="modal-stat">
          <div class="modal-label">Stage</div>
          <div class="modal-value" id="modal-stage">—</div>
        </div>
        <div class="modal-stat">
          <div class="modal-label">Status</div>
          <div class="modal-value" id="modal-status">—</div>
        </div>
        <div class="modal-stat">
          <div class="modal-label">Source</div>
          <div class="modal-value" id="modal-source">—</div>
        </div>
      </div>
      <div class="modal-body">
        <div class="modal-panel">
          <h4>Roadmap context</h4>
          <p id="modal-detail">—</p>
        </div>
        <div class="modal-panel">
          <h4>Saved notes</h4>
          <p id="modal-notes">No extra notes saved.</p>
        </div>
      </div>
    </div>
  </div>

  <script>
    const bootstrap = {bootstrap};
    const state = {{
      items: Array.isArray(bootstrap.items) ? bootstrap.items.slice() : [],
      filter: 'all',
      query: '',
      activeItem: null,
      saving: false,
    }};

    const els = {{
      ring: document.getElementById('progress-ring'),
      progressValue: document.getElementById('progress-value'),
      progressSummary: document.getElementById('progress-summary'),
      statTotal: document.getElementById('stat-total'),
      statOpen: document.getElementById('stat-open'),
      statDone: document.getElementById('stat-done'),
      composerForm: document.getElementById('composer-form'),
      composerSubmit: document.getElementById('composer-submit'),
      composerStatus: document.getElementById('composer-status'),
      titleInput: document.getElementById('todo-title'),
      notesInput: document.getElementById('todo-notes'),
      searchInput: document.getElementById('search-input'),
      reloadBtn: document.getElementById('reload-btn'),
      upcomingList: document.getElementById('upcoming-list'),
      completedList: document.getElementById('completed-list'),
      upcomingCount: document.getElementById('upcoming-count'),
      completedCount: document.getElementById('completed-count'),
      pills: Array.from(document.querySelectorAll('.filter-pill')),
      modal: document.getElementById('todo-modal'),
      modalClose: document.getElementById('modal-close'),
      modalEyebrow: document.getElementById('modal-eyebrow'),
      modalTitle: document.getElementById('modal-title'),
      modalStage: document.getElementById('modal-stage'),
      modalStatus: document.getElementById('modal-status'),
      modalSource: document.getElementById('modal-source'),
      modalDetail: document.getElementById('modal-detail'),
      modalNotes: document.getElementById('modal-notes'),
    }};

    function escapeHtml(value) {{
      return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }}

    function sortedItems(items) {{
      return items.slice().sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0));
    }}

    function filteredItems() {{
      const q = state.query.trim().toLowerCase();
      return sortedItems(state.items).filter(item => {{
        if (state.filter !== 'all' && item.status !== state.filter) return false;
        if (!q) return true;
        const haystack = `${{item.text || ''}} ${{item.notes || ''}} ${{item.detail || ''}}`.toLowerCase();
        return haystack.includes(q);
      }});
    }}

    function statCounts(items) {{
      const total = items.length;
      const done = items.filter(item => item.status === 'done').length;
      const open = total - done;
      return {{ total, done, open, completionPct: total ? Math.round((done / total) * 100) : 0 }};
    }}

    function updateSummary() {{
      const counts = statCounts(state.items);
      els.statTotal.textContent = String(counts.total);
      els.statOpen.textContent = String(counts.open);
      els.statDone.textContent = String(counts.done);
      els.progressValue.textContent = `${{counts.completionPct}}%`;
      els.progressSummary.textContent = `${{counts.done}} completed · ${{counts.open}} upcoming`;
      els.ring.style.setProperty('--done-angle', `${{Math.max(0, Math.min(360, counts.completionPct * 3.6))}}deg`);
    }}

    function cardMarkup(item) {{
      const statusClass = item.status === 'done' ? 'completed' : 'upcoming';
      const toggleLabel = item.status === 'done' ? 'Move back to upcoming' : 'Mark completed';
      const toggleClass = item.status === 'done' ? 'reset' : 'done';
      const notes = item.notes ? `<p class="item-notes">${{escapeHtml(item.notes)}}</p>` : '';
      const sourceChip = item.is_custom ? '<span class="source-chip">DB added</span>' : `<span class="source-chip">${{escapeHtml(item.source_file)}}</span>`;
      const toggle = item.can_toggle
        ? `<button class="toggle-btn ${{toggleClass}}" type="button" data-action="toggle" data-item-key="${{escapeHtml(item.item_key)}}">${{escapeHtml(toggleLabel)}}</button>`
        : '';
      return `
        <article class="timeline-item" data-action="open" data-item-key="${{escapeHtml(item.item_key)}}" tabindex="0" role="button" aria-label="Open stage ${{item.stage_number}} details">
          <div class="timeline-dot-wrap">
            <div class="timeline-dot ${{item.status === 'done' ? 'done' : ''}}"></div>
          </div>
          <div class="item-main">
            <div class="item-meta">
              <span class="stage-chip">Stage #${{item.stage_number}}</span>
              <span class="status-chip ${{statusClass}}">${{escapeHtml(item.status_label)}}</span>
              ${{sourceChip}}
            </div>
            <h3 class="item-title">${{escapeHtml(item.text)}}</h3>
            ${{notes}}
          </div>
          <div class="item-actions">
            ${{toggle}}
          </div>
        </article>
      `;
    }}

    function emptyMarkup(label) {{
      return `<div class="empty-state">No ${{label.toLowerCase()}} items match the current filter.</div>`;
    }}

    function renderTimeline() {{
      const visible = filteredItems();
      const upcoming = visible.filter(item => item.status === 'open');
      const completed = visible.filter(item => item.status === 'done');
      els.upcomingCount.textContent = `${{upcoming.length}} item${{upcoming.length === 1 ? '' : 's'}}`;
      els.completedCount.textContent = `${{completed.length}} item${{completed.length === 1 ? '' : 's'}}`;
      els.upcomingList.innerHTML = upcoming.length ? upcoming.map(cardMarkup).join('') : emptyMarkup('Upcoming');
      els.completedList.innerHTML = completed.length ? completed.map(cardMarkup).join('') : emptyMarkup('Completed');
    }}

    function render() {{
      els.pills.forEach(pill => pill.classList.toggle('active', pill.dataset.filter === state.filter));
      updateSummary();
      renderTimeline();
    }}

    function findItem(itemKey) {{
      return state.items.find(item => item.item_key === itemKey) || null;
    }}

    function openModal(item) {{
      if (!item) return;
      state.activeItem = item;
      els.modalEyebrow.textContent = item.status === 'done' ? 'Completed stage' : 'Upcoming stage';
      els.modalTitle.textContent = item.text || 'TODO detail';
      els.modalStage.textContent = `Stage #${{item.stage_number}}`;
      els.modalStatus.textContent = item.status_label;
      els.modalSource.textContent = item.is_custom ? 'runtime_state.json (user-added)' : item.source_file;
      els.modalDetail.textContent = item.detail || 'No detail available.';
      els.modalNotes.textContent = item.notes || 'No extra notes saved.';
      els.modal.classList.add('open');
      els.modal.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
    }}

    function closeModal() {{
      state.activeItem = null;
      els.modal.classList.remove('open');
      els.modal.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
    }}

    async function reloadItems(statusMessage = '') {{
      if (statusMessage) els.composerStatus.textContent = statusMessage;
      const response = await fetch('/api/todo-data', {{ cache: 'no-store' }});
      if (!response.ok) throw new Error(`Reload failed (${{response.status}})`);
      const payload = await response.json();
      state.items = Array.isArray(payload.items) ? payload.items : [];
      render();
    }}

    async function saveToggle(itemKey) {{
      const item = findItem(itemKey);
      if (!item || !item.can_toggle) return;
      const nextStatus = item.status === 'done' ? 'open' : 'done';
      const response = await fetch('/api/todo-state', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ item_key: itemKey, status: nextStatus }}),
      }});
      if (!response.ok) throw new Error(`Save failed (${{response.status}})`);
      await reloadItems('TODO state saved.');
      if (els.modal.classList.contains('open')) {{
        const refreshed = findItem(itemKey);
        if (refreshed) openModal(refreshed);
      }}
    }}

    async function createTodo(event) {{
      event.preventDefault();
      if (state.saving) return;
      const title = els.titleInput.value.trim();
      const notes = els.notesInput.value.trim();
      if (!title) {{
        els.composerStatus.textContent = 'Title is required.';
        return;
      }}
      state.saving = true;
      els.composerSubmit.disabled = true;
      els.composerStatus.textContent = 'Saving to dashboard DB…';
      try {{
        const response = await fetch('/api/todo-items', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ title, notes }}),
        }});
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || `Save failed (${{response.status}})`);
        els.titleInput.value = '';
        els.notesInput.value = '';
        await reloadItems('Saved. Timeline reloaded from dashboard DB.');
      }} catch (error) {{
        els.composerStatus.textContent = error.message || 'Unable to save TODO.';
      }} finally {{
        state.saving = false;
        els.composerSubmit.disabled = false;
      }}
    }}

    function handleTimelineClick(event) {{
      const toggleButton = event.target.closest('[data-action="toggle"]');
      if (toggleButton) {{
        event.stopPropagation();
        saveToggle(toggleButton.dataset.itemKey).catch(error => {{
          els.composerStatus.textContent = error.message || 'Unable to update TODO status.';
        }});
        return;
      }}
      const card = event.target.closest('[data-action="open"]');
      if (!card) return;
      openModal(findItem(card.dataset.itemKey));
    }}

    function handleTimelineKeydown(event) {{
      const card = event.target.closest('[data-action="open"]');
      if (!card) return;
      if (event.key === 'Enter' || event.key === ' ') {{
        event.preventDefault();
        openModal(findItem(card.dataset.itemKey));
      }}
    }}

    els.pills.forEach(pill => pill.addEventListener('click', () => {{
      state.filter = pill.dataset.filter || 'all';
      render();
    }}));
    els.searchInput.addEventListener('input', event => {{
      state.query = event.target.value || '';
      render();
    }});
    els.composerForm.addEventListener('submit', createTodo);
    els.reloadBtn.addEventListener('click', () => reloadItems('Reloaded from dashboard DB.').catch(error => {{
      els.composerStatus.textContent = error.message || 'Unable to reload roadmap.';
    }}));
    els.upcomingList.addEventListener('click', handleTimelineClick);
    els.completedList.addEventListener('click', handleTimelineClick);
    els.upcomingList.addEventListener('keydown', handleTimelineKeydown);
    els.completedList.addEventListener('keydown', handleTimelineKeydown);
    els.modalClose.addEventListener('click', closeModal);
    els.modal.addEventListener('click', event => {{ if (event.target === els.modal) closeModal(); }});
    document.addEventListener('keydown', event => {{ if (event.key === 'Escape' && els.modal.classList.contains('open')) closeModal(); }});

    render();
  </script>
</body>
</html>
"""


def build_todo_page() -> None:
    sync_all_if_needed(min_interval=0.0)
    items = load_todo_items()
    html = build_page(items, todo_stats(items))
    OUTPUT.write_text(html, encoding="utf-8")


def main() -> None:
    build_todo_page()
    print(f"✅ Wrote {OUTPUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
