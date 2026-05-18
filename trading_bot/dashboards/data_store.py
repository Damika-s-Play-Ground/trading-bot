#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""SQLite-backed data store for generated dashboard data.

This keeps generated analytics, history, and backlog state out of the codebase
and gives the dashboard generators a single structured source of truth.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "dashboard.sqlite"
SUMMARY_FILE = REPO_ROOT / "trading_bot" / "roadmap_summary.yml"
RESEARCH_FILE = Path.home() / "Documents" / "ai-crypto-research.md"
PERFORMANCE_FILE = REPO_ROOT / "performance_journal.json"
CRON_FILE = REPO_ROOT / "logs" / "cron.json"

_SYNC_CACHE = {
    "stamp": None,
    "result": None,
    "checked_at": 0.0,
}


def _file_signature(path: Path) -> tuple[float, int]:
    try:
        stat = path.stat()
        return stat.st_mtime, stat.st_size
    except FileNotFoundError:
        return 0.0, 0


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def ensure_schema() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS performance_runs (
                timestamp TEXT PRIMARY KEY,
                regime TEXT,
                portfolio_total REAL,
                unrealized_pnl REAL,
                realized_pnl_recent REAL,
                combined_loss_pct REAL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cron_runs (
                timestamp TEXT NOT NULL,
                job TEXT NOT NULL,
                status TEXT,
                duration_ms INTEGER,
                steps_json TEXT,
                error TEXT,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (timestamp, job, status)
            );

            CREATE TABLE IF NOT EXISTS research_items (
                item_key TEXT PRIMARY KEY,
                date TEXT,
                platform TEXT,
                title TEXT,
                author TEXT,
                strategy TEXT,
                results TEXT,
                tools TEXT,
                takeaway TEXT,
                url TEXT,
                raw TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_state_overrides (
                item_key TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT DEFAULT 'dashboard'
            );

            CREATE TABLE IF NOT EXISTS todo_items (
                item_key TEXT PRIMARY KEY,
                section TEXT NOT NULL,
                status TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                text TEXT NOT NULL,
                notes TEXT,
                source_file TEXT,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS todo_state_overrides (
                item_key TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT DEFAULT 'dashboard'
            );
            """
        )


def _load_json(path: Path, default: Any) -> Any:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _parse_time(text: Any) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except Exception:
        return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _hash_key(*parts: str) -> str:
    raw = "|".join(_normalize(p or "") for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:18]


def sync_performance_runs(path: Path = PERFORMANCE_FILE) -> int:
    data = _load_json(path, {"runs": []})
    runs = data.get("runs", []) if isinstance(data, dict) else []
    count = 0
    with _connect() as conn:
        for run in runs if isinstance(runs, list) else []:
            if not isinstance(run, dict):
                continue
            ts = str(run.get("timestamp") or run.get("time") or "")
            if not ts:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO performance_runs
                (timestamp, regime, portfolio_total, unrealized_pnl, realized_pnl_recent, combined_loss_pct, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    run.get("regime"),
                    run.get("portfolio_total"),
                    run.get("unrealized_pnl"),
                    run.get("realized_pnl_recent"),
                    run.get("combined_loss_pct"),
                    json.dumps(run, ensure_ascii=False),
                ),
            )
            count += 1
    return count


def sync_cron_runs(path: Path = CRON_FILE) -> int:
    data = _load_json(path, {"runs": []})
    runs = data.get("runs", []) if isinstance(data, dict) else []
    count = 0
    with _connect() as conn:
        for run in runs if isinstance(runs, list) else []:
            if not isinstance(run, dict):
                continue
            ts = str(run.get("timestamp") or "")
            job = str(run.get("job") or "")
            if not ts or not job:
                continue
            payload = json.dumps(run, ensure_ascii=False)
            steps = json.dumps(run.get("steps", {}), ensure_ascii=False)
            conn.execute(
                """
                INSERT OR REPLACE INTO cron_runs
                (timestamp, job, status, duration_ms, steps_json, error, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    job,
                    run.get("status"),
                    run.get("duration_ms"),
                    steps,
                    run.get("error") or run.get("last_delivery_error"),
                    payload,
                ),
            )
            count += 1
    return count


def _parse_research_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    blocks = text.split("\n### ")
    for block in blocks[1:]:
        lines = block.strip().split("\n")
        if not lines:
            continue
        title = lines[0].strip()
        date_match = re.search(r"\[(\d{4}-\d{2}-\d{2})\]", title)
        date = date_match.group(1) if date_match else "Unknown"
        if "Twitter" in title or "X" in title:
            platform = "Twitter/X"
        elif "Reddit" in title:
            platform = "Reddit"
        elif "Web" in title or "Blog" in title or "GitHub" in title:
            platform = "Web"
        elif "Discord" in title:
            platform = "Discord"
        else:
            platform = "Source"

        author_match = re.search(r"\|\s*(.+?)$", title)
        author = author_match.group(1).strip() if author_match else ""

        details: dict[str, str] = {}
        current_key: str | None = None
        for line in lines[1:]:
            line = line.strip()
            if line.startswith("**") and ":**" in line:
                km = re.match(r"\*\*(.+?):\*\*\s*(.*)", line)
                if km:
                    current_key = km.group(1).strip()
                    details[current_key] = km.group(2).strip()
            elif line.startswith("- **") and ":**" in line:
                km = re.match(r"- \*\*(.+?):\*\*\s*(.*)", line)
                if km:
                    current_key = km.group(1).strip()
                    details[current_key] = km.group(2).strip()
            elif current_key and line and not line.startswith("#") and not line.startswith("---"):
                details[current_key] += " " + line

        entries.append(
            {
                "date": date,
                "title": title,
                "platform": platform,
                "author": author,
                "details": details,
                "raw": block,
            }
        )
    return entries


def sync_research_entries(path: Path = RESEARCH_FILE) -> int:
    if not path.exists():
        return 0
    text = path.read_text()
    entries = _parse_research_entries(text)
    count = 0
    item_keys = [_hash_key(entry.get("date", ""), entry.get("title", "")) for entry in entries]
    with _connect() as conn:
        if item_keys:
            placeholders = ", ".join("?" for _ in item_keys)
            conn.execute(
                f"DELETE FROM research_items WHERE item_key NOT IN ({placeholders})",
                item_keys,
            )
        else:
            conn.execute("DELETE FROM research_items")
        for entry in entries:
            details = entry.get("details", {}) if isinstance(entry.get("details"), dict) else {}
            item_key = _hash_key(entry.get("date", ""), entry.get("title", ""))
            conn.execute(
                """
                INSERT OR REPLACE INTO research_items
                (item_key, date, platform, title, author, strategy, results, tools, takeaway, url, raw)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_key,
                    entry.get("date"),
                    entry.get("platform"),
                    entry.get("title"),
                    entry.get("author"),
                    details.get("Strategy", ""),
                    details.get("Results", ""),
                    details.get("Tools", ""),
                    details.get("Key takeaway", details.get("Takeaway", "")),
                    details.get("URL", ""),
                    entry.get("raw", ""),
                ),
            )
            count += 1
        conn.execute(
            "DELETE FROM research_state_overrides WHERE item_key NOT IN (SELECT item_key FROM research_items)"
        )
    return count


def _classify_todo(text: str, section: str) -> str:
    if section == "done":
        return "done"
    lowered = text.lower()
    if any(word in lowered for word in ["research", "optimizer", "scorer", "validation"]):
        return "research"
    if any(word in lowered for word in ["deploy", "vps", "ops", "alert", "automation", "cron"]):
        return "ops"
    if any(word in lowered for word in ["risk", "governance", "circuit", "drawdown", "capital"]):
        return "risk"
    if any(word in lowered for word in ["state", "layout", "structure", "database", "output"]):
        return "architecture"
    return "product"


def _parse_summary_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    section = None
    stop_markers = {
        "what the original staged plan was",
        "what has been achieved so far",
        "what is not fully achieved yet",
        "recommended next build order",
    }
    items = []
    sort_order = 0
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.lower() in stop_markers:
            section = None
            continue
        if line.lower().startswith("what’s done") or line.lower().startswith("what's done"):
            section = "done"
            continue
        if line.lower().startswith("what’s still missing") or line.lower().startswith("what's still missing"):
            section = "open"
            continue
        if line.lower().startswith("current live status"):
            section = "status"
            continue
        if line.lower().startswith("active cron jobs"):
            section = "status"
            continue
        if line.startswith("- ") and section in {"done", "open", "status"}:
            text = line[2:].strip()
            if not text:
                continue
            if text.lower().startswith("job id:") or text.lower().startswith("schedule:") or text.lower().startswith("mode:"):
                continue
            item_section = section
            item_status = "done" if section == "done" else ("open" if section == "open" else "note")
            items.append(
                {
                    "section": item_section,
                    "status": item_status,
                    "sort_order": sort_order,
                    "text": text,
                    "notes": "",
                    "source_file": str(path),
                    "category": _classify_todo(text, item_status),
                }
            )
            sort_order += 1
    return items


def sync_todo_items(path: Path = SUMMARY_FILE) -> int:
    items = _parse_summary_items(path)
    count = 0
    item_keys = [
        _hash_key(item.get("section", ""), item.get("text", ""), str(item.get("sort_order", 0)))
        for item in items
    ]
    with _connect() as conn:
        if item_keys:
            placeholders = ", ".join("?" for _ in item_keys)
            conn.execute(
                f"DELETE FROM todo_items WHERE source_file = ? OR item_key IN ({placeholders})",
                (str(path), *item_keys),
            )
        else:
            conn.execute("DELETE FROM todo_items WHERE source_file = ?", (str(path),))
        for item in items:
            item_key = _hash_key(item.get("section", ""), item.get("text", ""), str(item.get("sort_order", 0)))
            payload = dict(item)
            conn.execute(
                """
                INSERT OR REPLACE INTO todo_items
                (item_key, section, status, sort_order, text, notes, source_file, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_key,
                    item.get("section"),
                    item.get("status"),
                    item.get("sort_order", 0),
                    item.get("text"),
                    item.get("notes"),
                    str(path),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            count += 1
        conn.execute(
            "DELETE FROM todo_state_overrides WHERE item_key NOT IN (SELECT item_key FROM todo_items)"
        )
    return count


def sync_all() -> dict[str, int]:
    ensure_schema()
    return {
        "performance_runs": sync_performance_runs(),
        "cron_runs": sync_cron_runs(),
        "research_items": sync_research_entries(),
        "todo_items": sync_todo_items(),
    }


def sync_all_if_needed(force: bool = False, min_interval: float = 5.0) -> dict[str, int]:
    ensure_schema()
    now = datetime.now(timezone.utc).timestamp()
    stamp = (
        _file_signature(PERFORMANCE_FILE),
        _file_signature(CRON_FILE),
        _file_signature(RESEARCH_FILE),
        _file_signature(SUMMARY_FILE),
    )
    cached_stamp = _SYNC_CACHE.get("stamp")
    cached_result = _SYNC_CACHE.get("result")
    checked_at = float(_SYNC_CACHE.get("checked_at") or 0.0)
    if not force and cached_stamp == stamp and cached_result is not None and (now - checked_at) < max(min_interval, 0.0):
        return dict(cached_result)
    result = sync_all() if force or cached_stamp != stamp or cached_result is None else dict(cached_result)
    _SYNC_CACHE["stamp"] = stamp
    _SYNC_CACHE["result"] = dict(result)
    _SYNC_CACHE["checked_at"] = now
    return dict(result)


def load_performance_runs(limit: int = 60) -> list[dict[str, Any]]:
    ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT payload_json FROM performance_runs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    items = [json.loads(row[0]) for row in rows][::-1]
    return items


def load_cron_runs(limit: int = 80) -> list[dict[str, Any]]:
    ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT payload_json FROM cron_runs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def load_research_items(limit: int = 200) -> list[dict[str, Any]]:
    ensure_schema()
    overrides = load_research_state_overrides()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT item_key, date, platform, title, author, strategy, results, tools, takeaway, url, raw
            FROM research_items
            ORDER BY COALESCE(date, '') DESC, title DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["status"] = "open"
        override = overrides.get(str(item.get("item_key")))
        if override:
            item["status"] = override.get("status", "open")
            item["status_updated_at"] = override.get("updated_at", "")
            item["status_source"] = override.get("source", "dashboard")
        items.append(item)
    return items


def load_research_state_overrides() -> dict[str, dict[str, Any]]:
    ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT item_key, status, updated_at, source FROM research_state_overrides"
        ).fetchall()
    return {
        str(row["item_key"]): {
            "status": row["status"],
            "updated_at": row["updated_at"],
            "source": row["source"],
        }
        for row in rows
    }


def save_research_state(item_key: str, status: str, source: str = "dashboard") -> dict[str, Any]:
    ensure_schema()
    normalized_status = status if status in {"open", "done"} else "open"
    updated_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO research_state_overrides (item_key, status, updated_at, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(item_key) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at,
                source = excluded.source
            """,
            (item_key, normalized_status, updated_at, source),
        )
    return {
        "item_key": item_key,
        "status": normalized_status,
        "updated_at": updated_at,
        "source": source,
    }


def load_todo_state_overrides() -> dict[str, dict[str, Any]]:
    ensure_schema()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT item_key, status, updated_at, source FROM todo_state_overrides"
        ).fetchall()
    return {
        str(row["item_key"]): {
            "status": row["status"],
            "updated_at": row["updated_at"],
            "source": row["source"],
        }
        for row in rows
    }


def save_todo_state(item_key: str, status: str, source: str = "dashboard") -> dict[str, Any]:
    ensure_schema()
    normalized_status = status if status in {"open", "done", "note"} else "open"
    updated_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO todo_state_overrides (item_key, status, updated_at, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(item_key) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at,
                source = excluded.source
            """,
            (item_key, normalized_status, updated_at, source),
        )
    return {
        "item_key": item_key,
        "status": normalized_status,
        "updated_at": updated_at,
        "source": source,
    }


def load_todo_items() -> list[dict[str, Any]]:
    ensure_schema()
    overrides = load_todo_state_overrides()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT item_key, section, status, sort_order, text, notes, source_file, payload_json
            FROM todo_items
            ORDER BY sort_order ASC
            """
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["base_status"] = item.get("status", "open")
        try:
            item["payload"] = json.loads(item.pop("payload_json"))
        except Exception:
            item["payload"] = {}
        override = overrides.get(str(item.get("item_key")))
        if override and item["base_status"] != "done":
            item["status"] = override.get("status", item["status"])
            item["status_updated_at"] = override.get("updated_at", "")
            item["status_source"] = override.get("source", "dashboard")
        items.append(item)
    return items


def todo_stats(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(items)
    total = len(items)
    done = sum(1 for item in items if item.get("status") == "done")
    open_count = sum(1 for item in items if item.get("status") == "open")
    notes = total - done - open_count
    categories: dict[str, int] = {}
    for item in items:
        payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
        category = payload.get("category", "other")
        categories[category] = categories.get(category, 0) + 1
    return {
        "total": total,
        "done": done,
        "open": open_count,
        "notes": notes,
        "categories": categories,
        "completion_pct": round(done / total * 100, 1) if total else 0.0,
    }


def latest_timestamp() -> str:
    ensure_schema()
    with _connect() as conn:
        row = conn.execute("SELECT MAX(timestamp) AS ts FROM performance_runs").fetchone()
    return row["ts"] if row and row["ts"] else ""
