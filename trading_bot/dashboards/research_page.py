#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""Interactive research dashboard with filters, analyzer scores, and persistent review state."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from trading_bot.dashboards.data_store import load_research_items, sync_all_if_needed
from trading_bot.dashboards.shared_ui import build_bar_chart, build_donut_chart
from trading_bot.dashboards.spot_dashboard import build_shared_style, nav

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = REPO_ROOT / "research.html"
REVIEW_LABELS = {
    "promoted": "Promoted",
    "shortlisted": "Shortlisted",
    "raw": "Raw",
    "rejected": "Rejected",
}
REVIEW_COLORS = {
    "promoted": "#22c55e",
    "shortlisted": "#38bdf8",
    "raw": "#94a3b8",
    "rejected": "#ef4444",
}


def _escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _sentiment_bucket(results: str) -> str:
    nums = []
    for n in re.findall(r"[+-]?\d+\.?\d*%", results or ""):
        try:
            nums.append(float(n.replace("%", "")))
        except Exception:
            pass
    if not nums:
        return "neutral"
    avg = sum(nums) / len(nums)
    if avg > 0:
        return "positive"
    if avg < 0:
        return "negative"
    return "neutral"


def _render_tags(text: str) -> str:
    tags = [part.strip() for part in str(text or "").split(",") if part.strip()]
    if not tags:
        return '<span class="mini-note">No structured tags yet</span>'
    return "".join(f'<span class="tag-chip">{_escape(tag)}</span>' for tag in tags[:6])


def _render_item(item: dict, idx: int) -> str:
    results = item.get("results", "") or "—"
    sentiment = _sentiment_bucket(results)
    sentiment_color = {"positive": "#22c55e", "negative": "#ef4444", "neutral": "#94a3b8"}[sentiment]
    url = item.get("url", "") or ""
    status = "done" if str(item.get("status", "open")) == "done" else "open"
    review_status = str(item.get("review_status", "raw") or "raw")
    review_label = REVIEW_LABELS.get(review_status, review_status.title())
    review_color = REVIEW_COLORS.get(review_status, "#94a3b8")
    done_class = " done" if status == "done" else ""
    link_html = f'<a href="{_escape(url)}" target="_blank" rel="noreferrer" onclick="event.stopPropagation()">Source →</a>' if url else ""
    search_blob = " ".join(
        str(item.get(key, ""))
        for key in (
            "title",
            "strategy",
            "results",
            "tools",
            "takeaway",
            "topic_tags",
            "evidence_summary",
            "suggested_action",
        )
    ).lower()
    return f"""
    <article
        class="research-card{done_class}"
        data-key="{_escape(item.get('item_key', idx))}"
        data-platform="{_escape(item.get('platform', 'source').lower())}"
        data-review="{_escape(review_status)}"
        data-done="{'1' if status == 'done' else '0'}"
        data-search="{_escape(search_blob)}"
        onclick="toggleDone(this)">
        <div class="research-head">
            <div class="research-badges">
                <span class="num-badge">#{idx}</span>
                <span class="platform-badge">{_escape(item.get('platform', 'Source'))}</span>
                <span class="date-badge">{_escape(item.get('date', 'Unknown'))}</span>
                <span class="review-badge review-{_escape(review_status)}">{_escape(review_label)}</span>
            </div>
            <span class="done-mark">✓</span>
        </div>
        <h3 class="research-title">{_escape(item.get('title', 'Untitled'))}</h3>
        <div class="score-grid">
            <div class="score-pill"><span>Total</span><strong>{float(item.get('total_score', 0.0)):.1f}</strong></div>
            <div class="score-pill"><span>Quality</span><strong>{float(item.get('quality_score', 0.0)):.1f}</strong></div>
            <div class="score-pill"><span>Fit</span><strong>{float(item.get('applicability_score', 0.0)):.1f}</strong></div>
            <div class="score-pill"><span>Novelty</span><strong>{float(item.get('novelty_score', 0.0)):.1f}</strong></div>
        </div>
        <div class="research-detail-grid">
            <div><span class="detail-label">Strategy</span><span>{_escape(item.get('strategy', '—'))}</span></div>
            <div><span class="detail-label">Results</span><span style="color:{sentiment_color};font-weight:700">{_escape(results)}</span></div>
            <div><span class="detail-label">Evidence</span><span>{_escape(item.get('evidence_summary', '—'))}</span></div>
            <div><span class="detail-label">Tools</span><span>{_escape(item.get('tools', '—'))}</span></div>
            <div class="takeaway"><span class="detail-label">Takeaway</span><span>{_escape(item.get('takeaway', '—'))}</span></div>
            <div class="takeaway"><span class="detail-label">Suggested action</span><span>{_escape(item.get('suggested_action', '—'))}</span></div>
            <div class="takeaway"><span class="detail-label">Tags</span><span class="tag-row">{_render_tags(item.get('topic_tags', ''))}</span></div>
        </div>
        <div class="research-footer">
            <span class="sentiment sentiment-{sentiment}">{sentiment.title()}</span>
            {link_html}
        </div>
    </article>
    """


def build_research_page() -> None:
    sync_all_if_needed(min_interval=5.0)
    items = load_research_items()
    total = len(items)
    platform_counts: Counter[str] = Counter()
    sent_counts = {"positive": 0, "negative": 0, "neutral": 0}
    review_counts: Counter[str] = Counter()
    latest = "—"
    promoted = 0
    shortlisted = 0
    if items:
        latest = items[0].get("date", "—")
    for item in items:
        platform = (item.get("platform") or "source").title()
        platform_counts[platform] += 1
        sent_counts[_sentiment_bucket(item.get("results", ""))] += 1
        review_status = str(item.get("review_status", "raw") or "raw")
        review_counts[review_status] += 1
    promoted = review_counts.get("promoted", 0)
    shortlisted = review_counts.get("shortlisted", 0)

    platform_chart = build_bar_chart(
        [
            {
                "label": k,
                "value": v,
                "color": "#3b82f6" if k == "Twitter/X" else "#22c55e" if k == "Web" else "#a855f7",
                "meta": f"{v} items",
            }
            for k, v in sorted(platform_counts.items(), key=lambda kv: kv[1], reverse=True)
        ],
        title="Source mix",
        subtitle="Where the research is coming from",
    )
    sentiment_chart = build_donut_chart(
        [
            {"label": "Positive", "value": sent_counts["positive"], "color": "#22c55e"},
            {"label": "Neutral", "value": sent_counts["neutral"], "color": "#94a3b8"},
            {"label": "Negative", "value": sent_counts["negative"], "color": "#ef4444"},
        ],
        title="Result sentiment",
        center_value=str(total),
        center_label="items",
        subtitle="Quick read on the direction of the collected evidence",
    )
    review_chart = build_bar_chart(
        [
            {"label": "Promoted", "value": review_counts.get("promoted", 0), "color": REVIEW_COLORS["promoted"], "meta": "Review first"},
            {"label": "Shortlisted", "value": review_counts.get("shortlisted", 0), "color": REVIEW_COLORS["shortlisted"], "meta": "Keep in focus"},
            {"label": "Raw", "value": review_counts.get("raw", 0), "color": REVIEW_COLORS["raw"], "meta": "Needs validation"},
            {"label": "Rejected", "value": review_counts.get("rejected", 0), "color": REVIEW_COLORS["rejected"], "meta": "Low current fit"},
        ],
        title="Analyzer funnel",
        subtitle="Deterministic fit scoring for the current Binance spot roadmap",
    )

    cards_html = "\n".join(_render_item(item, idx) for idx, item in enumerate(items, 1))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="120">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Crypto Research</title>
    <style>
        {build_shared_style('#3b82f6')}
        .hero {{ display:grid; grid-template-columns:1.2fr 1fr; gap:16px; margin-bottom:18px; }}
        .hero-card, .research-panel {{ background:#1e293b; border:1px solid #334155; border-radius:18px; padding:18px; box-shadow:0 12px 30px rgba(15,23,42,.24); }}
        .hero-card h2 {{ font-size:26px; margin-bottom:6px; }}
        .hero-card p {{ color:#94a3b8; line-height:1.65; }}
        .hero-stats {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:14px; }}
        .hero-stat {{ background:#0f172a; border:1px solid #334155; border-radius:14px; padding:12px 14px; }}
        .hero-stat .k {{ color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:.6px; }}
        .hero-stat .v {{ font-size:22px; font-weight:800; margin-top:4px; font-variant-numeric:tabular-nums; }}
        .research-layout {{ display:grid; grid-template-columns:1fr; gap:16px; }}
        .chart-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
        .progress-wrap {{ background:#1e293b; border:1px solid #334155; border-radius:16px; padding:16px 18px; }}
        .progress-head {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; align-items:center; margin-bottom:8px; }}
        .progress-head strong {{ font-size:14px; }}
        .progress-bar {{ height:10px; background:#0f172a; border-radius:999px; overflow:hidden; box-shadow:inset 0 0 0 1px #334155; }}
        .progress-fill {{ height:100%; width:0%; background:linear-gradient(90deg,#60a5fa,#22c55e); border-radius:999px; transition:width .35s ease; }}
        .research-toolbar {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin:14px 0; align-items:center; }}
        .research-toolbar-left {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
        .search-input {{ width:min(360px,100%); background:#0f172a; border:1px solid #334155; color:#e2e8f0; padding:11px 12px; border-radius:12px; font-size:13px; outline:none; }}
        .search-input:focus {{ border-color:#3b82f6; box-shadow:0 0 0 3px rgba(59,130,246,.16); }}
        .chip-row {{ display:flex; flex-wrap:wrap; gap:8px; }}
        .chip {{ padding:8px 12px; border-radius:999px; background:#0f172a; border:1px solid #334155; color:#cbd5e1; font-size:12px; cursor:pointer; user-select:none; }}
        .chip.active {{ background:#3b82f622; border-color:#3b82f655; color:#93c5fd; }}
        .chip:hover {{ border-color:#475569; }}
        .section-title {{ display:flex; justify-content:space-between; gap:12px; align-items:center; margin:18px 0 12px; }}
        .section-title h2 {{ font-size:16px; }}
        .section-title .count {{ color:#94a3b8; font-size:12px; }}
        .research-card-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(350px,1fr)); gap:14px; }}
        .research-card {{ background:#0f172a; border:1px solid #334155; border-radius:16px; padding:15px 16px; cursor:pointer; transition:transform .15s ease, border-color .15s ease, background .15s ease; }}
        .research-card:hover {{ transform:translateY(-1px); border-color:#475569; background:#101b31; }}
        .research-card.done {{ opacity:.72; }}
        .research-card.done .research-title {{ text-decoration:line-through; color:#94a3b8; }}
        .research-head {{ display:flex; justify-content:space-between; gap:10px; align-items:flex-start; margin-bottom:10px; }}
        .research-badges {{ display:flex; flex-wrap:wrap; gap:8px; }}
        .num-badge, .platform-badge, .date-badge, .sentiment, .review-badge {{ font-size:11px; padding:3px 8px; border-radius:999px; border:1px solid #334155; }}
        .num-badge {{ background:#3b82f622; color:#93c5fd; border-color:#3b82f655; font-weight:800; }}
        .platform-badge, .date-badge {{ background:#0f172a; color:#cbd5e1; }}
        .review-promoted {{ background:#22c55e1a; color:#86efac; border-color:#22c55e55; }}
        .review-shortlisted {{ background:#38bdf81a; color:#7dd3fc; border-color:#38bdf855; }}
        .review-raw {{ background:#334155; color:#cbd5e1; border-color:#475569; }}
        .review-rejected {{ background:#ef44441a; color:#fca5a5; border-color:#ef444455; }}
        .done-mark {{ color:#22c55e; font-size:18px; opacity:.25; }}
        .research-card.done .done-mark {{ opacity:1; }}
        .research-title {{ font-size:15px; line-height:1.45; margin-bottom:10px; }}
        .score-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin-bottom:12px; }}
        .score-pill {{ background:#111c31; border:1px solid #23324d; border-radius:12px; padding:9px 10px; }}
        .score-pill span {{ display:block; color:#94a3b8; font-size:10px; text-transform:uppercase; letter-spacing:.55px; }}
        .score-pill strong {{ display:block; margin-top:4px; font-size:15px; }}
        .research-detail-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px 16px; min-width:0; }}
        .takeaway {{ grid-column:1/-1; }}
        .detail-label {{ color:#64748b; display:block; font-size:10px; text-transform:uppercase; letter-spacing:.5px; margin-bottom:2px; }}
        .tag-row {{ display:flex; flex-wrap:wrap; gap:7px; }}
        .tag-chip {{ display:inline-flex; align-items:center; padding:4px 8px; border-radius:999px; border:1px solid #334155; background:#0b1322; color:#cbd5e1; font-size:11px; }}
        .research-footer {{ display:flex; justify-content:space-between; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap; }}
        .sentiment-positive {{ background:#22c55e1a; color:#86efac; border-color:#22c55e44; }}
        .sentiment-negative {{ background:#ef44441a; color:#fca5a5; border-color:#ef444444; }}
        .sentiment-neutral {{ background:#334155; color:#cbd5e1; }}
        .empty-state {{ color:#64748b; text-align:center; padding:18px; font-size:13px; }}
        @media (max-width: 980px) {{
            .hero, .chart-grid {{ grid-template-columns:1fr; }}
        }}
        @media (max-width: 900px) {{
            .research-card-grid, .research-detail-grid, .score-grid {{ grid-template-columns:1fr; }}
        }}
        @media (max-width: 640px) {{
            .nav a {{ width:100%; text-align:center; }}
            .search-input {{ width:100%; }}
        }}
    </style>
    <script>
    function moveCardByState(card) {{
        const openBox = document.getElementById('to-evaluate');
        const doneBox = document.getElementById('evaluated-container');
        const isDone = card.dataset.done === '1';
        card.classList.toggle('done', isDone);
        (isDone ? doneBox : openBox).appendChild(card);
    }}
    async function persistDone(key, status) {{
        if (!window.location.origin.startsWith('http')) return;
        try {{
            await fetch('/api/research-state', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ item_key: key, status }}),
            }});
        }} catch (error) {{
            console.log('research state sync failed', error);
        }}
    }}
    function applySavedState(items = null) {{
        const stateMap = items && typeof items === 'object' ? items : {{}};
        document.querySelectorAll('.research-card').forEach(card => {{
            const override = stateMap[card.dataset.key];
            card.dataset.done = override?.status === 'done' || (!override && card.dataset.done === '1') ? '1' : '0';
            moveCardByState(card);
        }});
        updateProgress();
        applyFilters();
        syncEmptyStates();
    }}
    async function toggleDone(card) {{
        const nextDone = card.dataset.done === '1' ? '0' : '1';
        card.dataset.done = nextDone;
        moveCardByState(card);
        updateProgress();
        syncEmptyStates();
        applyFilters();
        await persistDone(card.dataset.key, nextDone === '1' ? 'done' : 'open');
    }}
    function updateProgress() {{
        const cards = Array.from(document.querySelectorAll('.research-card'));
        const done = cards.filter(c => c.dataset.done === '1').length;
        const total = cards.length;
        const pct = total ? done / total * 100 : 0;
        document.getElementById('progress-count').textContent = done;
        document.getElementById('progress-total').textContent = total;
        document.getElementById('progress-pct').textContent = pct.toFixed(0) + '%';
        document.getElementById('progress-fill').style.width = pct.toFixed(1) + '%';
        document.getElementById('to-eval-count').textContent = total - done;
        document.getElementById('eval-count').textContent = done;
    }}
    function applyFilters() {{
        const q = (document.getElementById('research-search')?.value || '').trim().toLowerCase();
        const platform = document.querySelector('[data-chip-group="platform"] .chip.active')?.dataset.value || 'all';
        const show = document.querySelector('[data-chip-group="state"] .chip.active')?.dataset.value || 'all';
        const review = document.querySelector('[data-chip-group="review"] .chip.active')?.dataset.value || 'all';
        document.querySelectorAll('.research-card').forEach(card => {{
            const matchSearch = !q || card.dataset.search.includes(q);
            const matchPlatform = platform === 'all' || card.dataset.platform === platform;
            const done = card.dataset.done === '1';
            const matchState = show === 'all' || (show === 'done' && done) || (show === 'open' && !done);
            const matchReview = review === 'all' || card.dataset.review === review;
            card.style.display = (matchSearch && matchPlatform && matchState && matchReview) ? '' : 'none';
        }});
    }}
    function syncEmptyStates() {{
        const openBox = document.getElementById('to-evaluate');
        const doneBox = document.getElementById('evaluated-container');
        const openPlaceholder = document.getElementById('open-empty');
        const donePlaceholder = document.getElementById('evaluated-empty');
        const openVisible = Array.from(openBox.querySelectorAll('.research-card')).filter(card => card.style.display !== 'none').length;
        const doneVisible = Array.from(doneBox.querySelectorAll('.research-card')).filter(card => card.style.display !== 'none').length;
        if (openPlaceholder) openPlaceholder.style.display = openVisible ? 'none' : '';
        if (donePlaceholder) donePlaceholder.style.display = doneVisible ? 'none' : '';
    }}
    async function resetProgress() {{
        if (!confirm('Reset all research progress?')) return;
        const cards = Array.from(document.querySelectorAll('.research-card'));
        cards.forEach(card => {{
            card.dataset.done = '0';
            moveCardByState(card);
        }});
        updateProgress();
        syncEmptyStates();
        applyFilters();
        await Promise.all(cards.map(card => persistDone(card.dataset.key, 'open')));
    }}
    async function hydrateFromApi() {{
        if (!window.location.origin.startsWith('http')) return;
        try {{
            const response = await fetch('/api/research-state', {{ cache: 'no-store' }});
            const payload = await response.json();
            applySavedState(payload?.items || {{}});
        }} catch (error) {{
            console.log('research state hydrate failed', error);
        }}
    }}
    window.addEventListener('DOMContentLoaded', async () => {{
        document.querySelectorAll('[data-chip-group]').forEach(group => {{
            group.addEventListener('click', (e) => {{
                const chip = e.target.closest('.chip');
                if (!chip) return;
                group.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                applyFilters();
                syncEmptyStates();
            }});
        }});
        document.getElementById('research-search')?.addEventListener('input', () => {{
            applyFilters();
            syncEmptyStates();
        }});
        applySavedState();
        await hydrateFromApi();
    }});
    </script>
</head>
<body>
    <div class="page-shell">
    <div class="page-header">
        <h1>🔬 AI Crypto Research</h1>
        <p class="subtitle">DB-backed research queue with deterministic analyzer scores, promotion labels, and persistent review state.</p>
    </div>
    {nav('research')}

    <div class="hero">
        <div class="hero-card">
            <h2>High-signal research, ranked for operator review</h2>
            <p>
                The raw feed is now synchronized into SQLite with structured fit scores, tags, suggested actions,
                and promotion states. Use this page to process the queue from best-fit ideas down to low-fit noise.
            </p>
            <div class="hero-stats">
                <div class="hero-stat"><div class="k">Total items</div><div class="v">{total}</div></div>
                <div class="hero-stat"><div class="k">Latest</div><div class="v" style="font-size:16px">{_escape(latest)}</div></div>
                <div class="hero-stat"><div class="k">Promoted</div><div class="v">{promoted}</div></div>
                <div class="hero-stat"><div class="k">Shortlisted</div><div class="v">{shortlisted}</div></div>
                <div class="hero-stat"><div class="k">Open</div><div class="v" id="to-eval-count">{total}</div></div>
                <div class="hero-stat"><div class="k">Evaluated</div><div class="v" id="eval-count">0</div></div>
            </div>
        </div>
        {sentiment_chart}
    </div>

    <div class="chart-grid">
        {platform_chart}
        {review_chart}
    </div>

    <div class="progress-wrap">
        <div class="progress-head">
            <strong>Evaluation progress</strong>
            <div class="progress-meta"><span id="progress-count">0</span>/<span id="progress-total">{total}</span> reviewed · <span id="progress-pct">0%</span></div>
        </div>
        <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
    </div>

    <div class="research-toolbar">
        <div class="research-toolbar-left">
            <input id="research-search" class="search-input" placeholder="Search titles, tags, evidence, tools, actions..." />
            <button class="chip" type="button" onclick="resetProgress()">Reset progress</button>
        </div>
        <div class="chip-row" data-chip-group="state">
            <span class="chip active" data-value="all">All</span>
            <span class="chip" data-value="open">Open</span>
            <span class="chip" data-value="done">Evaluated</span>
        </div>
        <div class="chip-row" data-chip-group="review">
            <span class="chip active" data-value="all">All fit levels</span>
            <span class="chip" data-value="promoted">Promoted</span>
            <span class="chip" data-value="shortlisted">Shortlisted</span>
            <span class="chip" data-value="raw">Raw</span>
            <span class="chip" data-value="rejected">Rejected</span>
        </div>
        <div class="chip-row" data-chip-group="platform">
            <span class="chip active" data-value="all">All sources</span>
            <span class="chip" data-value="twitter/x">Twitter/X</span>
            <span class="chip" data-value="web">Web</span>
            <span class="chip" data-value="reddit">Reddit</span>
            <span class="chip" data-value="discord">Discord</span>
            <span class="chip" data-value="source">Other</span>
        </div>
    </div>

    <div class="research-layout">
        <div>
            <div class="section-title"><h2>📋 To Evaluate</h2><span class="count">sorted by analyzer fit and score</span></div>
            <div class="research-card-grid" id="to-evaluate"><div class="empty-state" id="open-empty" style="display:none;">No open items match the current filter.</div>{cards_html}</div>
        </div>
        <div>
            <div class="section-title"><h2>✅ Evaluated</h2><span class="count">click again to move back</span></div>
            <div class="research-card-grid" id="evaluated-container"><div class="empty-state" id="evaluated-empty">No evaluated items yet.</div></div>
        </div>
    </div>

    <p class="footer-note" style="color:#64748b;font-size:12px;margin-top:12px;">
        Source: {REPO_ROOT / 'data' / 'dashboard.sqlite'} · research feed regenerated from {Path.home() / 'Documents' / 'ai-crypto-research.md'}.
    </p>
    </div>
</body>
</html>"""

    OUTPUT.write_text(html)
    print(f"✅ Research page generated: {OUTPUT} ({total} entries)")


def main() -> None:
    build_research_page()


if __name__ == "__main__":
    main()
