#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""
Research Dashboard — numbered, cross-out, progress bar
"""
import re
from pathlib import Path

RESEARCH_FILE = Path.home() / "Documents" / "ai-crypto-research.md"
REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = REPO_ROOT / "research.html"

def parse_entries(content):
    entries = []
    blocks = content.split("\n### ")
    for block in blocks[1:]:
        lines = block.strip().split("\n")
        title = lines[0].strip()
        date_match = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', title)
        date = date_match.group(1) if date_match else "Unknown"
        
        platform = ""
        if "Twitter" in title or "X" in title: platform = "🐦 Twitter/X"
        elif "Reddit" in title: platform = "🔴 Reddit"
        elif "Web" in title or "Blog" in title or "GitHub" in title: platform = "🌐 Web"
        elif "Discord" in title: platform = "💬 Discord"
        else: platform = "📰 Source"
        
        author = ""
        author_match = re.search(r'\|\s*(.+?)$', title)
        if author_match: author = author_match.group(1).strip()
        
        details = {}
        current_key = None
        for line in lines[1:]:
            line = line.strip()
            if line.startswith("**") and ":**" in line:
                km = re.match(r'\*\*(.+?):\*\*\s*(.*)', line)
                if km:
                    current_key = km.group(1).strip()
                    details[current_key] = km.group(2).strip()
            elif line.startswith("- **") and ":**" in line:
                km = re.match(r'- \*\*(.+?):\*\*\s*(.*)', line)
                if km:
                    current_key = km.group(1).strip()
                    details[current_key] = km.group(2).strip()
            elif current_key and line and not line.startswith("#") and not line.startswith("---"):
                details[current_key] += " " + line
        
        entries.append({
            "date": date, "title": title, "platform": platform,
            "author": author, "details": details, "raw": block,
        })
    return entries

if not RESEARCH_FILE.exists():
    html = """<!DOCTYPE html><html lang="en"><head>
    <meta charset="UTF-8"><meta http-equiv="refresh" content="120">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Crypto Research</title>
    <style>*{margin:0;padding:0;box-sizing:border-box}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
    background:#0f172a;color:#e2e8f0;padding:24px}
    </style></head><body>
    <h1>🔬 AI Crypto Research</h1>
    <p style="color:#94a3b8;font-size:14px">No research data yet.</p></body></html>"""
    with open(OUTPUT, "w") as f: f.write(html)
    exit(0)

with open(RESEARCH_FILE) as f:
    content = f.read()

entries = parse_entries(content)
entries.sort(key=lambda x: x["date"], reverse=True)

total = len(entries)
unique_sources = len(set(e["platform"] for e in entries))
latest = entries[0]["date"] if entries else "—"

rows = ""
for idx, e in enumerate(entries, 1):
    d = e["details"]
    strategy = d.get("Strategy", "—")
    results = d.get("Results", "—")
    tools = d.get("Tools", "—")
    takeaway = d.get("Key takeaway", "—")
    url = d.get("URL", "")
    
    results_color = "#94a3b8"
    if "%" in results:
        nums = re.findall(r'[+-]?\d+\.?\d*%', results)
        for n in nums:
            v = float(n.replace("%","").replace("+",""))
            if v > 0: results_color = "#22c55e"
            else: results_color = "#ef4444"
    
    url_html = f'<a href="{url}" target="_blank" style="color:#3b82f6;font-size:12px">Source →</a>' if url else ""
    
    rows += f"""
    <div class="entry" data-id="{idx}" onclick="toggleDone(this)">
        <div class="entry-header">
            <span class="num-badge">#{idx}</span>
            <span class="platform-badge">{e['platform']}</span>
            <span class="date">{e['date']}</span>
            {url_html}
            <span class="done-mark" style="display:none">✅</span>
        </div>
        <div class="entry-title">{e['title']}</div>
        <div class="entry-details">
            <div class="detail"><span class="detail-label">Strategy</span><span>{strategy}</span></div>
            <div class="detail"><span class="detail-label">Results</span><span style="color:{results_color};font-weight:600">{results}</span></div>
            <div class="detail"><span class="detail-label">Tools</span><span>{tools}</span></div>
            <div class="detail takeaway"><span class="detail-label">Takeaway</span><span>{takeaway}</span></div>
        </div>
    </div>"""

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="120">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Crypto Research</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
               background:#0f172a; color:#e2e8f0; padding:24px; }}
        h1 {{ font-size:24px; margin-bottom:4px; }}
        .subtitle {{ color:#94a3b8; font-size:14px; margin-bottom:24px; }}
        .nav {{ display:flex; gap:12px; margin-bottom:24px; }}
        .nav a {{ padding:8px 16px; border-radius:8px; background:#1e293b; color:#94a3b8;
                 text-decoration:none; font-size:13px; transition:0.2s; }}
        .nav a.active {{ background:#3b82f6; color:white; }}
        .nav a:hover {{ background:#334155; }}
        .nav a.active:hover {{ background:#2563eb; }}
        
        /* Stats Row */
        .stats {{ display:flex; gap:16px; margin-bottom:16px; flex-wrap:wrap; }}
        .stat {{ background:#1e293b; border-radius:12px; padding:16px 20px; flex:1; min-width:120px; }}
        .stat .label {{ color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:0.5px; }}
        .stat .value {{ font-size:24px; font-weight:700; margin-top:2px; }}
        
        /* Progress Bar */
        .progress-wrap {{ background:#1e293b; border-radius:12px; padding:16px 20px; margin-bottom:20px; }}
        .progress-header {{ display:flex; justify-content:space-between; margin-bottom:8px; font-size:13px; }}
        .progress-header strong {{ color:#e2e8f0; }}
        .progress-header span {{ color:#94a3b8; }}
        .progress-bar {{ height:8px; background:#334155; border-radius:4px; overflow:hidden; }}
        .progress-fill {{ height:100%; background:linear-gradient(90deg,#22c55e,#3b82f6); border-radius:4px; transition:width 0.5s; width:0%; }}
        .btn-reset {{ background:#334155; border:none; color:#94a3b8; padding:4px 12px; border-radius:6px; cursor:pointer; font-size:12px; }}
        .btn-reset:hover {{ background:#ef4444; color:white; }}
        
        /* Entries */
        .entry {{ background:#1e293b; border-radius:12px; padding:20px; margin-bottom:10px; cursor:pointer; transition:0.2s; }}
        .entry:hover {{ background:#1e3349; }}
        .entry.done {{ opacity:0.35; }}
        .entry.done .entry-title {{ text-decoration:line-through; }}
        
        /* Section headers */
        .section-header {{ display:flex; align-items:center; gap:10px; margin:24px 0 12px; }}
        .section-header h2 {{ font-size:16px; margin:0; }}
        .section-header .count {{ font-size:12px; color:#64748b; background:#334155; padding:2px 10px; border-radius:10px; }}
        .section-header .eval-badge {{ font-size:10px; padding:2px 8px; border-radius:4px; background:#22c55e33; color:#22c55e; }}
        
        /* Empty state */
        .empty-state {{ color:#64748b; text-align:center; padding:20px; font-size:13px; }}
        .entry-header {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; flex-wrap:wrap; }}
        .num-badge {{ font-size:11px; font-weight:700; padding:2px 8px; border-radius:4px; background:#3b82f6; color:white; }}
        .platform-badge {{ font-size:11px; padding:2px 8px; border-radius:4px; background:#334155; color:#94a3b8; }}
        .date {{ font-size:12px; color:#64748b; }}
        .done-mark {{ margin-left:auto; }}
        .entry-title {{ font-size:15px; font-weight:600; margin-bottom:10px; }}
        .entry-details {{ display:grid; grid-template-columns:1fr 1fr; gap:8px 20px; }}
        .detail {{ font-size:13px; }}
        .takeaway {{ grid-column:1/-1; }}
        .detail-label {{ color:#64748b; display:block; font-size:11px; text-transform:uppercase; margin-bottom:2px; }}
        a {{ color:#3b82f6; text-decoration:none; }}
        @media (max-width:600px) {{ .entry-details {{ grid-template-columns:1fr; }} }}
    </style>
    <script>
    // Load progress from localStorage
    function loadProgress() {{
        try {{ return JSON.parse(localStorage.getItem('research_done') || '[]'); }} catch(e) {{ return []; }}
    }}
    
    function saveProgress(done) {{
        localStorage.setItem('research_done', JSON.stringify(done));
    }}
    
    function updateProgress() {{
        const done = loadProgress();
        const total = {total};
        const count = done.length;
        const pct = total > 0 ? (count / total * 100) : 0;
        document.getElementById('progress-count').textContent = count;
        document.getElementById('progress-total').textContent = total;
        document.getElementById('progress-fill').style.width = pct.toFixed(1) + '%';
        document.getElementById('progress-pct').textContent = pct.toFixed(0) + '%';
        document.getElementById('to-eval-count').textContent = total - count;
        document.getElementById('eval-count').textContent = count;
    }}
    
    function toggleDone(el) {{
        const id = el.dataset.id;
        const done = loadProgress();
        const idx = done.indexOf(id);
        const evalContainer = document.getElementById('evaluated-container');
        const toEvalSection = document.getElementById('to-evaluate');
        
        if (idx > -1) {{
            // Un-evaluate: move back to to-evaluate
            done.splice(idx, 1);
            toEvalSection.appendChild(el);
            el.classList.remove('done');
            el.querySelector('.done-mark').style.display = 'none';
        }} else {{
            // Evaluate: move to evaluated section
            done.push(id);
            evalContainer.appendChild(el);
            el.classList.add('done');
            el.querySelector('.done-mark').style.display = 'inline';
        }}
        
        saveProgress(done);
        updateProgress();
        updateEmptyStates();
    }}
    
    function updateEmptyStates() {{
        const toEval = document.getElementById('to-evaluate');
        const evalCont = document.getElementById('evaluated-container');
        
        let empty = toEval.querySelector('.empty-state');
        if (toEval.children.length === 0) {{
            if (!empty) {{
                empty = document.createElement('p');
                empty.className = 'empty-state';
                empty.textContent = '🎉 All items evaluated! Click Reset to start over.';
                toEval.appendChild(empty);
            }}
        }} else {{
            if (empty) empty.remove();
        }}
        
        empty = evalCont.querySelector('.empty-state');
        if (evalCont.children.length === 0) {{
            if (!empty) {{
                empty = document.createElement('p');
                empty.className = 'empty-state';
                empty.textContent = 'Click any item to mark as evaluated. It moves here.';
                evalCont.appendChild(empty);
            }}
        }} else {{
            if (empty) empty.remove();
        }}
    }}
    
    function resetProgress() {{
        if (confirm('Reset all evaluation progress? Items will move back to un-evaluated.')) {{
            localStorage.removeItem('research_done');
            const evalCont = document.getElementById('evaluated-container');
            const toEval = document.getElementById('to-evaluate');
            Array.from(evalCont.children).forEach(el => {{
                if (el.classList.contains('entry')) {{
                    el.classList.remove('done');
                    el.querySelector('.done-mark').style.display = 'none';
                    toEval.appendChild(el);
                }}
            }});
            updateProgress();
            updateEmptyStates();
        }}
    }}
    
    // Apply saved state on load
    window.addEventListener('DOMContentLoaded', function() {{
        const done = loadProgress();
        const evalCont = document.getElementById('evaluated-container');
        const toEval = document.getElementById('to-evaluate');
        
        done.forEach(id => {{
            const el = document.querySelector('.entry[data-id="' + id + '"]');
            if (el) {{
                el.classList.add('done');
                el.querySelector('.done-mark').style.display = 'inline';
                evalCont.appendChild(el);
            }}
        }});
        
        updateProgress();
        updateEmptyStates();
    }});
    </script>
</head>
<body>
    <h1>🔬 AI Crypto Research</h1>
    <p class="subtitle">Real-world AI trading bot case studies — click to mark as evaluated</p>
    
    <div class="nav">
        <a href="dashboard.html">📊 Spot</a>
        <a href="futures.html">🔵 Futures</a>
        <a href="research.html" class="active">🔬 Research</a>
        <a href="cron.html">⏱ Cron</a>
        <a href="glossary.html">📖 Glossary</a>
    </div>
    
    <div class="stats">
        <div class="stat"><div class="label">Total Items</div><div class="value">{total}</div></div>
        <div class="stat"><div class="label">Sources</div><div class="value">{unique_sources}</div></div>
        <div class="stat"><div class="label">Latest</div><div class="value" style="font-size:16px">{latest}</div></div>
        <div class="stat"><div class="label">Refresh</div><div class="value" style="font-size:16px">2 min</div></div>
    </div>

    <div class="progress-wrap">
        <div class="progress-header">
            <strong>📊 Evaluation Progress</strong>
            <span>
                <span id="progress-count">0</span>/<span id="progress-total">{total}</span> evaluated (<span id="progress-pct">0%</span>)
                <button class="btn-reset" onclick="resetProgress()">↺ Reset</button>
            </span>
        </div>
        <div class="progress-bar">
            <div class="progress-fill" id="progress-fill" style="width:0%"></div>
        </div>
    </div>

    <div class="section-header">
        <h2>📋 To Evaluate</h2>
        <span class="count" id="to-eval-count">{total}</span>
        <span class="eval-badge">unreviewed</span>
    </div>
    <div id="to-evaluate">
        {rows}
    </div>

    <div class="section-header" style="margin-top:40px;padding-top:24px;border-top:1px solid #334155;">
        <h2>✅ Evaluated</h2>
        <span class="count" id="eval-count">0</span>
        <span class="eval-badge">reviewed</span>
    </div>
    <div id="evaluated-container">
        <p class="empty-state">Click any item to mark as evaluated. It moves here.</p>
    </div>

    <p style="color:#64748b;font-size:11px;margin-top:24px;">
        Click any entry to mark as evaluated (✓). Progress saved in your browser. Auto-collected every 5 minutes.
    </p>
</body>
</html>"""

with open(OUTPUT, "w") as f:
    f.write(html)

print(f"✅ Research page generated: {OUTPUT} ({total} entries)")
