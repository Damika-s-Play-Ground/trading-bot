#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""Interactive roadmap / TODO dashboard generated from the SQLite dashboard store."""
from __future__ import annotations

from pathlib import Path

from trading_bot.dashboards.data_store import load_todo_items, sync_all, todo_stats
from trading_bot.dashboards.shared_ui import build_bar_chart, build_donut_chart
from trading_bot.dashboards.spot_dashboard import build_shared_style, nav

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = REPO_ROOT / "todo.html"


def _status_label(status: str) -> str:
    return {
        "done": "✅ Done",
        "open": "⬜ Open",
        "note": "📝 Note",
    }.get(status, status.title())


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_category_chart(items):
    stats = todo_stats(items)
    palette = {
        "research": "#60a5fa",
        "ops": "#22c55e",
        "risk": "#f59e0b",
        "architecture": "#a855f7",
        "product": "#38bdf8",
        "other": "#94a3b8",
        "done": "#64748b",
    }
    bars = [
        {
            "label": category.title(),
            "value": count,
            "color": palette.get(category, "#3b82f6"),
            "meta": f"{count} task{'s' if count != 1 else ''}",
        }
        for category, count in sorted(stats["categories"].items(), key=lambda kv: kv[1], reverse=True)
    ]
    return build_bar_chart(bars, title="Open work by theme", subtitle="Where the next effort is concentrated", value_suffix="")


def _build_task_cards(items):
    cards = []
    for idx, item in enumerate(items, 1):
        payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
        status = item.get("status", "open")
        category = payload.get("category", "other")
        badge = _status_label(status)
        cards.append(
            f"""
            <article class="todo-card"
                     data-key="{_escape(item.get('item_key', idx))}"
                     data-stage="{idx}"
                     data-base-status="{_escape(item.get('base_status', status))}"
                     data-status="{_escape(status)}"
                     data-category="{_escape(category)}"
                     data-search="{_escape((item.get('text', '') + ' ' + category + ' ' + status + ' stage ' + str(idx)).lower())}"
                     onclick="toggleTask(this)">
                <div class="todo-head">
                    <div class="todo-title-wrap">
                        <span class="todo-index">#{idx}</span>
                        <span class="todo-status status-{_escape(status)}">{badge}</span>
                        <span class="todo-category">{_escape(category.title())}</span>
                    </div>
                    <span class="todo-check">✓</span>
                </div>
                <div class="todo-text">{_escape(item.get('text', ''))}</div>
                <div class="todo-meta">
                    <span>Stage {idx}</span>
                    <span>Section: {_escape(item.get('section', ''))}</span>
                    <span>Source: {_escape(Path(item.get('source_file', '')).name)}</span>
                </div>
            </article>
            """
        )
    return "\n".join(cards)


def build_todo_page() -> None:
    sync_all()
    items = load_todo_items()
    stats = todo_stats(items)
    done = stats["done"]
    open_count = stats["open"]
    notes = stats["notes"]
    total = stats["total"]
    pct = stats["completion_pct"]

    donut_html = build_donut_chart(
        [
            {"label": "Done", "value": done, "color": "#22c55e"},
            {"label": "Open", "value": open_count, "color": "#3b82f6"},
            {"label": "Notes", "value": notes, "color": "#94a3b8"},
        ],
        title="Roadmap progress",
        center_value=f"{pct:.0f}%",
        center_label="complete",
        subtitle="Quick snapshot of current roadmap state",
    )
    donut_html = donut_html.replace('class="donut-value">', 'class="donut-value" id="todo-donut-value">')
    donut_html = donut_html.replace('class="donut-label">', 'class="donut-label" id="todo-donut-label">')
    categories_html = _build_category_chart(items)
    tasks_html = _build_task_cards(items)
    current_focus = next((item for item in items if item.get("status") == "open"), items[0] if items else None)
    current_focus_text = _escape(current_focus.get("text", "Nothing queued")) if current_focus else "Nothing queued"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="120">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project Roadmap / TODO</title>
    <style>
        {build_shared_style('#22c55e')}
        .hero {{
            display:grid; grid-template-columns:1.6fr 1fr; gap:16px; margin-bottom:18px;
        }}
        .hero-card, .todo-board {{ background:#1e293b; border:1px solid #334155; border-radius:18px; padding:18px; box-shadow:0 12px 30px rgba(15,23,42,.24); }}
        .hero-card h2 {{ font-size:26px; margin-bottom:6px; }}
        .hero-card p {{ color:#94a3b8; line-height:1.65; }}
        .focus-box {{ margin-top:14px; padding:14px 16px; background:#0f172a; border:1px solid #334155; border-radius:14px; }}
        .focus-label {{ color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:.6px; margin-bottom:6px; }}
        .focus-text {{ font-size:14px; line-height:1.6; }}
        .stats-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin:18px 0; }}
        .stat-card {{ background:#1e293b; border-radius:14px; padding:16px 18px; border:1px solid #334155; }}
        .stat-card .label {{ color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:.6px; }}
        .stat-card .value {{ font-size:28px; font-weight:800; margin-top:4px; font-variant-numeric:tabular-nums; }}
        .stat-card .sub {{ color:#64748b; font-size:12px; margin-top:4px; }}
        .progress-wrap {{ background:#1e293b; border:1px solid #334155; border-radius:16px; padding:16px 18px; margin-bottom:18px; }}
        .progress-head {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:8px; align-items:center; }}
        .progress-head strong {{ font-size:14px; }}
        .progress-meta {{ color:#94a3b8; font-size:12px; }}
        .progress-bar {{ height:10px; background:#0f172a; border-radius:999px; overflow:hidden; box-shadow:inset 0 0 0 1px #334155; }}
        .progress-fill {{ height:100%; width:{pct:.1f}%; background:linear-gradient(90deg,#22c55e,#60a5fa); border-radius:999px; transition:width .35s ease; }}
        .toolbar {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:14px; align-items:center; }}
        .toolbar-left {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
        .search-input {{ width:min(360px,100%); background:#0f172a; border:1px solid #334155; color:#e2e8f0; padding:11px 12px; border-radius:12px; font-size:13px; outline:none; }}
        .search-input:focus {{ border-color:#22c55e; box-shadow:0 0 0 3px rgba(34,197,94,.14); }}
        .chip-row {{ display:flex; flex-wrap:wrap; gap:8px; }}
        .chip {{ padding:8px 12px; border-radius:999px; background:#0f172a; border:1px solid #334155; color:#cbd5e1; font-size:12px; cursor:pointer; user-select:none; }}
        .chip.active {{ background:#22c55e22; border-color:#22c55e55; color:#86efac; }}
        .chip:hover {{ border-color:#475569; }}
        .chart-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:18px; }}
        .todo-board {{ margin-bottom:18px; }}
        .todo-section {{ margin-bottom:16px; }}
        .todo-section-header {{ display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; align-items:center; margin-bottom:12px; padding:0 2px; }}
        .todo-section-header strong {{ font-size:14px; }}
        .todo-section-header .mini-note {{ font-size:12px; }}
        .todo-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:14px; }}
        .todo-card {{ background:#0f172a; border:1px solid #334155; border-radius:16px; padding:14px 15px; cursor:pointer; transition:transform .15s ease, border-color .15s ease, background .15s ease; }}
        .todo-card:hover {{ transform:translateY(-1px); border-color:#475569; background:#101b31; }}
        .todo-card.done {{ opacity:.72; }}
        .todo-card.done .todo-text {{ text-decoration:line-through; color:#94a3b8; }}
        .todo-head {{ display:flex; justify-content:space-between; gap:10px; align-items:flex-start; margin-bottom:10px; }}
        .todo-title-wrap {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
        .todo-index {{ display:inline-flex; align-items:center; justify-content:center; min-width:28px; height:24px; padding:0 8px; border-radius:999px; background:#22c55e22; color:#86efac; font-weight:800; font-size:11px; }}
        .todo-status, .todo-category {{ font-size:11px; padding:3px 8px; border-radius:999px; border:1px solid #334155; }}
        .status-done {{ color:#86efac; background:#22c55e1a; border-color:#22c55e44; }}
        .status-open {{ color:#93c5fd; background:#3b82f61a; border-color:#3b82f644; }}
        .status-note {{ color:#cbd5e1; background:#334155; }}
        .todo-category {{ color:#cbd5e1; background:#0f172a; }}
        .todo-check {{ color:#22c55e; font-weight:800; opacity:.2; }}
        .todo-card.done .todo-check {{ opacity:1; }}
        .todo-text {{ font-size:14px; line-height:1.65; color:#e2e8f0; margin-bottom:10px; }}
        .todo-meta {{ display:flex; flex-wrap:wrap; gap:10px 14px; color:#64748b; font-size:11px; }}
        .empty-state {{ color:#64748b; text-align:center; padding:22px 14px; font-size:13px; }}
        .legend {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }}
        .legend-pill {{ padding:4px 8px; border-radius:999px; background:#0f172a; border:1px solid #334155; color:#94a3b8; font-size:11px; }}
        .chart-card .chart-head {{ align-items:flex-start; }}
        @media (max-width: 900px) {{
            .hero {{ grid-template-columns:1fr; }}
            .chart-grid {{ grid-template-columns:1fr; }}
        }}
        @media (max-width: 640px) {{
            body {{ padding:16px; }}
            .nav a {{ width:calc(50% - 4px); text-align:center; }}
            .search-input {{ width:100%; }}
            .todo-grid {{ grid-template-columns:1fr; }}
            .trade-why {{ padding-left:0; }}
        }}
    </style>
    <script>
    const STORAGE_KEY = 'todo_done_keys_v4';
    let doneState = [];
    function loadDone() {{
        try {{ return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }} catch (e) {{ return []; }}
    }}
    function saveDone(done) {{
        doneState = Array.from(new Set(done));
        localStorage.setItem(STORAGE_KEY, JSON.stringify(doneState));
    }}
    async function hydrateDone() {{
        const local = loadDone();
        doneState = [...local];
        if (!window.location.origin.startsWith('http')) {{
            saveDone(local);
            return;
        }}
        try {{
            const resp = await fetch('/api/todo-state', {{ cache: 'no-store' }});
            const payload = await resp.json();
            const remoteDone = Object.entries(payload?.items || {{}})
                .filter(([, item]) => item?.status === 'done')
                .map(([key]) => key);
            saveDone([...local, ...remoteDone]);
        }} catch (error) {{
            console.log('todo state hydrate failed', error);
            saveDone(local);
        }}
    }}
    async function persistTaskState(key, status) {{
        if (!window.location.origin.startsWith('http')) return;
        try {{
            await fetch('/api/todo-state', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ item_key: key, status }}),
            }});
        }} catch (error) {{
            console.log('todo state sync failed', error);
        }}
    }}
    function getCards() {{ return Array.from(document.querySelectorAll('.todo-card')); }}
    function setStatusChip(value) {{
        document.querySelectorAll('[data-chip-group="status"] .chip').forEach(ch => ch.classList.toggle('active', ch.dataset.value === value));
    }}
    function setCategoryChip(value) {{
        document.querySelectorAll('[data-chip-group="category"] .chip').forEach(ch => ch.classList.toggle('active', ch.dataset.value === value));
    }}
    function updateFocusBox() {{
        const focus = getCards().find(card => card.dataset.currentStatus === 'open' && card.style.display !== 'none');
        const focusText = document.getElementById('focus-text');
        const focusBadge = document.getElementById('focus-badge');
        if (!focus) {{
            if (focusText) focusText.textContent = 'Nothing queued — the open queue is clear.';
            if (focusBadge) focusBadge.textContent = 'All clear';
            return;
        }}
        if (focusText) focusText.textContent = focus.querySelector('.todo-text')?.textContent || 'Queued item';
        if (focusBadge) focusBadge.textContent = `Stage #${{focus.dataset.stage}} is next`;
    }}
    function updateCounters() {{
        const cards = getCards();
        const open = cards.filter(c => c.dataset.currentStatus === 'open').length;
        const done = cards.filter(c => c.dataset.currentStatus === 'done').length;
        const notes = cards.filter(c => c.dataset.currentStatus === 'note').length;
        const total = cards.length;
        const pct = total ? (done / total * 100) : 0;
        const set = (id, val) => {{ const el = document.getElementById(id); if (el) el.textContent = val; }};
        set('stat-total', total);
        set('stat-done', done);
        set('stat-open', open);
        set('stat-notes', notes);
        set('open-count', open);
        set('done-count', done);
        set('progress-text', `${{done}}/${{total}} complete`);
        const bar = document.getElementById('progress-fill');
        if (bar) bar.style.width = pct.toFixed(1) + '%';
        const donut = document.getElementById('todo-donut-value');
        if (donut) donut.textContent = pct.toFixed(0) + '%';
        const label = document.getElementById('todo-donut-label');
        if (label) label.textContent = done ? 'complete' : 'starting';
    }}
    function applyFilters() {{
        const q = (document.getElementById('todo-search')?.value || '').trim().toLowerCase();
        const status = document.querySelector('[data-chip-group="status"] .chip.active')?.dataset.value || 'all';
        const category = document.querySelector('[data-chip-group="category"] .chip.active')?.dataset.value || 'all';
        getCards().forEach(card => {{
            const matchSearch = !q || card.dataset.search.includes(q);
            const matchStatus = status === 'all' || card.dataset.currentStatus === status;
            const matchCategory = category === 'all' || card.dataset.category === category;
            card.style.display = (matchSearch && matchStatus && matchCategory) ? '' : 'none';
        }});
        updateFocusBox();
    }}
    function syncCardLocations() {{
        const openGrid = document.getElementById('todo-open-grid');
        const doneGrid = document.getElementById('todo-done-grid');
        if (!openGrid || !doneGrid) return;
        const doneKeys = new Set(doneState);
        const cards = getCards().sort((a, b) => Number(a.dataset.stage) - Number(b.dataset.stage));
        cards.forEach(card => {{
            const baseStatus = card.dataset.baseStatus;
            const isDone = baseStatus === 'done' || doneKeys.has(card.dataset.key);
            card.dataset.currentStatus = isDone ? 'done' : baseStatus;
            card.classList.toggle('done', isDone);
            (isDone ? doneGrid : openGrid).appendChild(card);
        }});
        updateCounters();
        applyFilters();
    }}
    async function toggleTask(card) {{
        if (!card || card.dataset.baseStatus === 'done') return;
        const done = [...doneState];
        const key = card.dataset.key;
        const idx = done.indexOf(key);
        let status = 'done';
        if (idx >= 0) {{
            done.splice(idx, 1);
            status = 'open';
        }} else {{
            done.push(key);
        }}
        saveDone(done);
        syncCardLocations();
        await persistTaskState(key, status);
    }}
    function clearFilters() {{
        const search = document.getElementById('todo-search');
        if (search) search.value = '';
        setStatusChip('all');
        setCategoryChip('all');
        applyFilters();
    }}
    window.addEventListener('DOMContentLoaded', async () => {{
        document.querySelectorAll('[data-chip-group]').forEach(group => {{
            group.addEventListener('click', (e) => {{
                const chip = e.target.closest('.chip');
                if (!chip) return;
                if (group.dataset.chipGroup === 'status') setStatusChip(chip.dataset.value);
                if (group.dataset.chipGroup === 'category') setCategoryChip(chip.dataset.value);
                applyFilters();
            }});
        }});
        document.getElementById('todo-search')?.addEventListener('input', applyFilters);
        await hydrateDone();
        syncCardLocations();
    }});
    </script>
</head>
<body>
    <h1>🗒 Project Roadmap / TODO</h1>
    <p class="subtitle">A live, filterable roadmap view pulled from the dashboard database. Click any card to move it between the open and done sections with completion state synced into the dashboard store.</p>
    {nav('todo')}

    <div class="hero">
        <div class="hero-card">
            <h2>Clear next steps, not a wall of text</h2>
            <p>
                This page turns the project summary into a lightweight planning board. It separates completed work,
                the remaining open path, and live operational notes, then keeps your view state synced to the dashboard store
                (with browser fallback) so it behaves like a real planning board instead of a static checklist.
            </p>
            <div class="focus-box">
                <div class="focus-label">Current focus</div>
                <div class="focus-text" id="focus-text">{current_focus_text}</div>
            </div>
            <div class="legend">
                <span class="legend-pill">Click to move between sections</span>
                <span class="legend-pill">Searchable</span>
                <span class="legend-pill">Category filters</span>
                <span class="legend-pill" id="focus-badge">Stage #{current_focus.get('sort_order', 0) + 1 if current_focus else 0} is next</span>
            </div>
        </div>
        {donut_html}
    </div>

    <div class="stats-grid">
        <div class="stat-card"><div class="label">Total</div><div class="value" id="stat-total">{total}</div><div class="sub">roadmap items</div></div>
        <div class="stat-card"><div class="label">Done</div><div class="value" id="stat-done">{done}</div><div class="sub">completed items</div></div>
        <div class="stat-card"><div class="label">Open</div><div class="value" id="stat-open">{open_count}</div><div class="sub">next actions</div></div>
        <div class="stat-card"><div class="label">Notes</div><div class="value" id="stat-notes">{notes}</div><div class="sub">operational reminders</div></div>
    </div>

    <div class="progress-wrap">
        <div class="progress-head">
            <strong>Progress</strong>
            <div class="progress-meta"><span id="progress-text">{done}/{total} complete</span> · syncs to the dashboard store</div>
        </div>
        <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
    </div>

    <div class="chart-grid">
        {categories_html}
        <div class="chart-card">
            <div class="chart-head">
                <div>
                    <strong>How to read this board</strong>
                    <div class="mini-note">It is optimized for quick scanning on both desktop and mobile.</div>
                </div>
            </div>
            <div class="empty-box" style="padding:24px 18px; text-align:left; line-height:1.7;">
                • Done items stay separated in their own section at the bottom.<br>
                • Search matches the text, section, category tags, and stage number.<br>
                • The open-priority badge updates as you toggle items.<br>
                • The donut, counters, and focus box update instantly when you click a card.
            </div>
        </div>
    </div>

    <div class="todo-board">
        <div class="toolbar">
            <div class="toolbar-left">
                <input id="todo-search" class="search-input" placeholder="Search roadmap items, sections, categories, or stage numbers..." />
                <button class="chip" type="button" onclick="clearFilters()">Reset filters</button>
            </div>
            <div class="chip-row">
                <span class="chip active" data-value="all" data-chip-group="status">All</span>
                <span class="chip" data-value="open" data-chip-group="status">Open</span>
                <span class="chip" data-value="done" data-chip-group="status">Done</span>
                <span class="chip" data-value="note" data-chip-group="status">Notes</span>
            </div>
        </div>
        <div class="toolbar">
            <div class="chip-row" data-chip-group="category">
                <span class="chip active" data-value="all">All themes</span>
                <span class="chip" data-value="research">Research</span>
                <span class="chip" data-value="ops">Ops</span>
                <span class="chip" data-value="risk">Risk</span>
                <span class="chip" data-value="architecture">Architecture</span>
                <span class="chip" data-value="product">Product</span>
                <span class="chip" data-value="other">Other</span>
            </div>
        </div>

        <div class="todo-section">
            <div class="todo-section-header">
                <strong>Open work</strong>
                <span class="mini-note"><span id="open-count">{open_count}</span> items waiting</span>
            </div>
            <div class="todo-grid" id="todo-open-grid">
                {tasks_html if tasks_html.strip() else '<div class="empty-state">No roadmap items found in the dashboard database.</div>'}
            </div>
        </div>

        <div class="todo-section">
            <div class="todo-section-header">
                <strong>Completed work</strong>
                <span class="mini-note"><span id="done-count">{done}</span> finished items</span>
            </div>
            <div class="todo-grid" id="todo-done-grid"></div>
        </div>
    </div>

    <p class="footer-note" style="color:#64748b;font-size:12px;margin-top:10px;">
        Source: {REPO_ROOT / 'data' / 'dashboard.sqlite'} · refreshed from the repo summary and live dashboard outputs.
    </p>
</body>
</html>"""
    OUTPUT.write_text(html)
    print(f"✅ Roadmap page generated: {OUTPUT}")


def main() -> None:
    build_todo_page()


if __name__ == "__main__":
    main()
