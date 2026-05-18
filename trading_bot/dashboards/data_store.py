#!/Users/damikaanupama/trading-bot/venv/bin/python3.13
"""DB-backed dashboard data store.

All mutable dashboard/runtime data lives in the external database via the shared
state_store helpers. Local files are treated as migration/bootstrap sources only.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from trading_bot.config.settings import RESEARCH_SOURCE_PATH
from trading_bot.core.state_store import import_json_file, load_blob, load_json_path, load_state, save_blob, save_state

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "runtime_state.json"
SUMMARY_FILE = REPO_ROOT / "trading_bot" / "roadmap_summary.yml"
RESEARCH_FILE = RESEARCH_SOURCE_PATH
PERFORMANCE_FILE = REPO_ROOT / "performance_journal.json"
CRON_FILE = REPO_ROOT / "logs" / "cron.json"

PERFORMANCE_RUNS_KEY = "dashboard:performance_runs"
CRON_RUNS_KEY = "dashboard:cron_runs"
RESEARCH_ITEMS_KEY = "dashboard:research_items"
RESEARCH_OVERRIDES_KEY = "dashboard:research_overrides"
TODO_ITEMS_KEY = "dashboard:todo_items"
TODO_OVERRIDES_KEY = "dashboard:todo_overrides"
RESEARCH_BLOB_KEY = "dashboard:research_markdown"

_SYNC_CACHE = {"stamp": None, "result": None, "checked_at": 0.0}

RESEARCH_REVIEW_ORDER = {"promoted": 0, "shortlisted": 1, "raw": 2, "rejected": 3}
RESEARCH_LOW_SIGNAL_TERMS = {"mev", "sandwich", "exploit", "cheat", "farm", "game", "solana", "copytrading", "sports"}
RESEARCH_RELEVANCE_TERMS = {
    "binance", "ccxt", "spot", "risk", "grid", "momentum", "mean reversion", "backtest", "paper trading",
    "allocation", "portfolio", "slippage", "order book", "atr", "trailing stop",
}
RESEARCH_NOVELTY_TERMS = {
    "order book", "slippage", "depth", "hysteresis", "atr", "regime", "allocation", "portfolio", "optimizer", "promotion", "gates", "risk control",
}


def _file_signature(path: Path) -> tuple[float, int]:
    try:
        stat = path.stat()
        return stat.st_mtime, stat.st_size
    except FileNotFoundError:
        return 0.0, 0


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _hash_key(*parts: str) -> str:
    raw = "|".join(_normalize(p or "") for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:18]


def _parse_time(text: Any) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except Exception:
        return None


def _load_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _hydrate_json_state(path: Path, default: Any) -> Any:
    current = load_json_path(path, None)
    if current is not None:
        return current
    if path.exists():
        import_json_file(path)
        current = load_json_path(path, None)
        if current is not None:
            return current
    return default


def ensure_schema() -> None:
    _hydrate_json_state(PERFORMANCE_FILE, {"runs": []})
    _hydrate_json_state(CRON_FILE, {"runs": []})
    if RESEARCH_FILE.exists() and not load_blob(RESEARCH_BLOB_KEY, ""):
        save_blob(RESEARCH_BLOB_KEY, RESEARCH_FILE.read_text(encoding="utf-8", errors="ignore"))
    for key, default in [
        (PERFORMANCE_RUNS_KEY, []),
        (CRON_RUNS_KEY, []),
        (RESEARCH_ITEMS_KEY, []),
        (RESEARCH_OVERRIDES_KEY, {}),
        (TODO_ITEMS_KEY, []),
        (TODO_OVERRIDES_KEY, {}),
    ]:
        if load_state(key, None) is None:
            save_state(key, default)


def sync_performance_runs(path: Path = PERFORMANCE_FILE) -> int:
    data = _hydrate_json_state(path, {"runs": []})
    runs = data.get("runs", []) if isinstance(data, dict) else []
    normalized = [run for run in runs if isinstance(run, dict) and str(run.get("timestamp") or run.get("time") or "")]
    normalized.sort(key=lambda item: str(item.get("timestamp") or item.get("time") or ""))
    save_state(PERFORMANCE_RUNS_KEY, normalized)
    return len(normalized)


def sync_cron_runs(path: Path = CRON_FILE) -> int:
    data = _hydrate_json_state(path, {"runs": []})
    runs = data.get("runs", []) if isinstance(data, dict) else []
    normalized = [run for run in runs if isinstance(run, dict) and str(run.get("timestamp") or "") and str(run.get("job") or "")]
    normalized.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    save_state(CRON_RUNS_KEY, normalized)
    return len(normalized)


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
        entries.append({"date": date, "title": title, "platform": platform, "author": author, "details": details, "raw": block})
    return entries


def _extract_source_name(title: str) -> str:
    if "|" not in title:
        return ""
    tail = title.split("|", 1)[1].strip()
    return tail.split("—", 1)[0].strip()


def _parse_repo_metrics(results: str) -> tuple[float, float]:
    star_match = re.search(r"(\d+(?:\.\d+)?)\s*★", results or "")
    fork_match = re.search(r"(\d+(?:\.\d+)?)\s*fork", results or "", re.IGNORECASE)
    stars = float(star_match.group(1)) if star_match else 0.0
    forks = float(fork_match.group(1)) if fork_match else 0.0
    return stars, forks


def _score_text_hits(text: str, terms: set[str], weight: float) -> float:
    lowered = text.lower()
    return sum(weight for term in terms if term in lowered)


def _research_metadata(entry: dict[str, Any], details: dict[str, str]) -> dict[str, Any]:
    title = str(entry.get("title", ""))
    platform = str(entry.get("platform", "Source"))
    strategy = str(details.get("Strategy", ""))
    results = str(details.get("Results", ""))
    tools = str(details.get("Tools", ""))
    takeaway = str(details.get("Key takeaway", details.get("Takeaway", "")))
    body = " ".join([title, strategy, results, tools, takeaway])
    source_name = _extract_source_name(title)
    stars, forks = _parse_repo_metrics(results)
    quality_score = min(100.0, 20.0 + stars * 0.35 + forks * 0.8)
    relevance_score = min(100.0, _score_text_hits(body, RESEARCH_RELEVANCE_TERMS, 10.0))
    novelty_score = min(100.0, _score_text_hits(body, RESEARCH_NOVELTY_TERMS, 12.5))
    applicability_score = 55.0
    if any(term in body.lower() for term in RESEARCH_LOW_SIGNAL_TERMS):
        applicability_score -= 20.0
    if "binance" in body.lower() or "ccxt" in body.lower():
        applicability_score += 15.0
    if "paper" in body.lower() or "backtest" in body.lower():
        applicability_score += 10.0
    applicability_score = max(0.0, min(100.0, applicability_score))
    total_score = round((quality_score * 0.2) + (relevance_score * 0.35) + (novelty_score * 0.2) + (applicability_score * 0.25), 2)
    topic_tags = sorted({term for term in RESEARCH_RELEVANCE_TERMS.union(RESEARCH_NOVELTY_TERMS) if term in body.lower()})
    review_status = "shortlisted" if total_score >= 55 else "raw"
    evidence_summary = _normalize(f"{strategy} {results} {takeaway}")[:380]
    suggested_action = "Review for bot integration" if total_score >= 55 else "Keep as reference"
    discovered_at = str(entry.get("date") or datetime.now(timezone.utc).date().isoformat())
    return {
        "source_type": platform,
        "source_name": source_name,
        "discovered_at": discovered_at,
        "fingerprint": _hash_key(title, strategy, results, tools, takeaway),
        "topic_tags": ", ".join(topic_tags),
        "quality_score": round(quality_score, 2),
        "relevance_score": round(relevance_score, 2),
        "novelty_score": round(novelty_score, 2),
        "applicability_score": round(applicability_score, 2),
        "total_score": total_score,
        "review_status": review_status,
        "evidence_summary": evidence_summary,
        "suggested_action": suggested_action,
    }


def sync_research_entries(path: Path = RESEARCH_FILE) -> int:
    ensure_schema()
    existing_items = {str(item.get("item_key")): item for item in load_state(RESEARCH_ITEMS_KEY, []) if isinstance(item, dict)}
    if path.exists():
        save_blob(RESEARCH_BLOB_KEY, path.read_text(encoding="utf-8", errors="ignore"))
    text = load_blob(RESEARCH_BLOB_KEY, "")
    if not text:
        save_state(RESEARCH_ITEMS_KEY, [])
        return 0
    entries = _parse_research_entries(text)
    synced_at = datetime.now(timezone.utc).isoformat()
    items: list[dict[str, Any]] = []
    for entry in entries:
        details = entry.get("details", {}) if isinstance(entry.get("details"), dict) else {}
        metadata = _research_metadata(entry, details)
        item_key = _hash_key(entry.get("date", ""), entry.get("title", ""))
        existing = existing_items.get(item_key, {})
        first_seen = str(existing.get("first_seen_at") or synced_at)
        items.append({
            "item_key": item_key,
            "date": entry.get("date"),
            "platform": entry.get("platform"),
            "title": entry.get("title"),
            "author": entry.get("author"),
            "strategy": details.get("Strategy", ""),
            "results": details.get("Results", ""),
            "tools": details.get("Tools", ""),
            "takeaway": details.get("Key takeaway", details.get("Takeaway", "")),
            "url": details.get("URL", ""),
            "raw": entry.get("raw", ""),
            "source_type": metadata.get("source_type"),
            "source_name": metadata.get("source_name"),
            "discovered_at": metadata.get("discovered_at"),
            "fingerprint": metadata.get("fingerprint"),
            "active_in_feed": True,
            "first_seen_at": first_seen,
            "last_seen_at": synced_at,
            "archived_at": None,
            "topic_tags": metadata.get("topic_tags"),
            "quality_score": metadata.get("quality_score"),
            "relevance_score": metadata.get("relevance_score"),
            "novelty_score": metadata.get("novelty_score"),
            "applicability_score": metadata.get("applicability_score"),
            "total_score": metadata.get("total_score"),
            "review_status": metadata.get("review_status"),
            "evidence_summary": metadata.get("evidence_summary"),
            "suggested_action": metadata.get("suggested_action"),
        })
    save_state(RESEARCH_ITEMS_KEY, items)
    overrides = {key: value for key, value in load_research_state_overrides().items() if key in {str(item.get("item_key")) for item in items}}
    save_state(RESEARCH_OVERRIDES_KEY, overrides)
    return len(items)


def import_research_archive(snapshot_db: Path | str, archived_at: str | None = None) -> int:
    ensure_schema()
    snapshot_path = Path(snapshot_db)
    if not snapshot_path.exists():
        return 0
    archived_stamp = archived_at or datetime.now(timezone.utc).isoformat()
    legacy = sqlite3.connect(snapshot_path)
    legacy.row_factory = sqlite3.Row
    try:
        legacy_rows = legacy.execute("SELECT item_key, date, platform, title, author, strategy, results, tools, takeaway, url, raw FROM research_items").fetchall()
    finally:
        legacy.close()
    current = {str(item.get("item_key")): item for item in load_state(RESEARCH_ITEMS_KEY, []) if isinstance(item, dict)}
    imported = 0
    for row in legacy_rows:
        item = dict(row)
        item_key = str(item.get("item_key") or _hash_key(str(item.get("date") or ""), str(item.get("title") or "")))
        if item_key in current:
            continue
        details = {
            "Strategy": str(item.get("strategy") or ""),
            "Results": str(item.get("results") or ""),
            "Tools": str(item.get("tools") or ""),
            "Key takeaway": str(item.get("takeaway") or ""),
            "URL": str(item.get("url") or ""),
        }
        metadata = _research_metadata(item, details)
        current[item_key] = {
            **item,
            **metadata,
            "item_key": item_key,
            "active_in_feed": False,
            "first_seen_at": str(item.get("date") or archived_stamp),
            "last_seen_at": str(item.get("date") or archived_stamp),
            "archived_at": archived_stamp,
            "takeaway": str(item.get("takeaway") or ""),
        }
        imported += 1
    save_state(RESEARCH_ITEMS_KEY, list(current.values()))
    return imported


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
    stop_markers = {"what the original staged plan was", "what has been achieved so far", "what is not fully achieved yet", "recommended next build order"}
    items = []
    sort_order = 0
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered in stop_markers:
            section = None
            continue
        if lowered.startswith("what’s done") or lowered.startswith("what's done"):
            section = "done"
            continue
        if lowered.startswith("what’s still missing") or lowered.startswith("what's still missing"):
            section = "open"
            continue
        if lowered.startswith("current live status") or lowered.startswith("active cron jobs"):
            section = "status"
            continue
        if line.startswith("- ") and section in {"done", "open", "status"}:
            text = line[2:].strip()
            normalized_text = text.lower()
            if (
                not text
                or normalized_text.startswith(("job id:", "schedule:", "mode:"))
                or normalized_text.startswith("current focus")
            ):
                continue
            item_status = "done" if section == "done" else "open"
            items.append({
                "section": section,
                "status": item_status,
                "sort_order": sort_order,
                "text": text,
                "notes": "",
                "source_file": str(path),
                "category": _classify_todo(text, item_status),
            })
            sort_order += 1
    return items


def sync_todo_items(path: Path = SUMMARY_FILE) -> int:
    ensure_schema()
    summary_items = _parse_summary_items(path)
    existing = [item for item in load_state(TODO_ITEMS_KEY, []) if isinstance(item, dict)]
    custom_items = [item for item in existing if Path(str(item.get("source_file") or "")).name == DB_PATH.name or bool(((item.get("payload") or {}) if isinstance(item.get("payload"), dict) else {}).get("is_custom"))]
    normalized_summary = []
    seen_texts: set[str] = set()
    for item in summary_items:
        normalized_text = _normalize(str(item.get("text") or "")).lower()
        if normalized_text in seen_texts:
            continue
        seen_texts.add(normalized_text)
        item_key = _hash_key(item.get("section", ""), item.get("text", ""), str(item.get("sort_order", 0)))
        payload = dict(item)
        normalized_summary.append({
            "item_key": item_key,
            "section": item.get("section"),
            "status": item.get("status"),
            "sort_order": item.get("sort_order", 0),
            "text": item.get("text"),
            "notes": item.get("notes"),
            "source_file": str(path),
            "payload": payload,
        })
    next_sort = len(normalized_summary)
    normalized_custom = []
    for item in sorted(custom_items, key=lambda row: int(row.get("sort_order", 0))):
        normalized_text = _normalize(str(item.get("text") or "")).lower()
        if normalized_text in seen_texts:
            continue
        seen_texts.add(normalized_text)
        payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
        normalized_custom.append({
            "item_key": str(item.get("item_key")),
            "section": str(item.get("section") or "custom"),
            "status": str(item.get("status") or "open"),
            "sort_order": next_sort,
            "text": str(item.get("text") or "").strip(),
            "notes": str(item.get("notes") or "").strip(),
            "source_file": str(DB_PATH),
            "payload": {**payload, "sort_order": next_sort, "is_custom": True},
        })
        next_sort += 1
    merged = normalized_summary + normalized_custom
    save_state(TODO_ITEMS_KEY, merged)
    overrides = {key: value for key, value in load_todo_state_overrides().items() if key in {str(item.get("item_key")) for item in merged}}
    save_state(TODO_OVERRIDES_KEY, overrides)
    return len(merged)


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
    stamp = (_file_signature(PERFORMANCE_FILE), _file_signature(CRON_FILE), _file_signature(RESEARCH_FILE), _file_signature(SUMMARY_FILE))
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
    items = [item for item in load_state(PERFORMANCE_RUNS_KEY, []) if isinstance(item, dict)]
    items.sort(key=lambda item: str(item.get("timestamp") or item.get("time") or ""))
    return items[-limit:]


def load_cron_runs(limit: int = 80) -> list[dict[str, Any]]:
    ensure_schema()
    items = [item for item in load_state(CRON_RUNS_KEY, []) if isinstance(item, dict)]
    items.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    return items[:limit]


def load_research_state_overrides() -> dict[str, dict[str, Any]]:
    ensure_schema()
    raw = load_state(RESEARCH_OVERRIDES_KEY, {})
    return raw if isinstance(raw, dict) else {}


def save_research_state(item_key: str, status: str, source: str = "dashboard") -> dict[str, Any]:
    ensure_schema()
    normalized_status = status if status in {"open", "done"} else "open"
    updated_at = datetime.now(timezone.utc).isoformat()
    overrides = load_research_state_overrides()
    overrides[str(item_key)] = {"status": normalized_status, "updated_at": updated_at, "source": source}
    save_state(RESEARCH_OVERRIDES_KEY, overrides)
    return {"item_key": item_key, "status": normalized_status, "updated_at": updated_at, "source": source}


def load_research_items(limit: int = 200) -> list[dict[str, Any]]:
    ensure_schema()
    overrides = load_research_state_overrides()
    rows = [item for item in load_state(RESEARCH_ITEMS_KEY, []) if isinstance(item, dict)]
    rows.sort(key=lambda item: (
        0 if item.get("active_in_feed", True) else 1,
        RESEARCH_REVIEW_ORDER.get(str(item.get("review_status") or "raw"), 9),
        -float(item.get("total_score") or 0.0),
        str(item.get("date") or ""),
        str(item.get("title") or ""),
    ))
    items = []
    for item in rows[:limit]:
        row = dict(item)
        row["status"] = "open"
        row["active_in_feed"] = bool(row.get("active_in_feed", True))
        override = overrides.get(str(row.get("item_key")))
        if override:
            row["status"] = override.get("status", "open")
            row["status_updated_at"] = override.get("updated_at", "")
            row["status_source"] = override.get("source", "dashboard")
        items.append(row)
    return items


def load_todo_state_overrides() -> dict[str, dict[str, Any]]:
    ensure_schema()
    raw = load_state(TODO_OVERRIDES_KEY, {})
    return raw if isinstance(raw, dict) else {}


def save_todo_state(item_key: str, status: str, source: str = "dashboard") -> dict[str, Any]:
    ensure_schema()
    normalized_status = status if status in {"open", "done"} else "open"
    updated_at = datetime.now(timezone.utc).isoformat()
    overrides = load_todo_state_overrides()
    overrides[str(item_key)] = {"status": normalized_status, "updated_at": updated_at, "source": source}
    save_state(TODO_OVERRIDES_KEY, overrides)
    return {"item_key": item_key, "status": normalized_status, "updated_at": updated_at, "source": source}


def create_todo_item(title: str, notes: str = "", source: str = "dashboard") -> dict[str, Any]:
    ensure_schema()
    cleaned_title = _normalize(title)
    cleaned_notes = str(notes or "").strip()
    if not cleaned_title:
        raise ValueError("title is required")
    items = [item for item in load_state(TODO_ITEMS_KEY, []) if isinstance(item, dict)]
    created_at = datetime.now(timezone.utc).isoformat()
    sort_order = max([int(item.get("sort_order", -1)) for item in items], default=-1) + 1
    item_key = _hash_key("custom", cleaned_title, created_at)
    payload = {
        "section": "custom",
        "status": "open",
        "sort_order": sort_order,
        "text": cleaned_title,
        "notes": cleaned_notes,
        "source_file": str(DB_PATH),
        "category": "other",
        "is_custom": True,
        "created_at": created_at,
    }
    item = {
        "item_key": item_key,
        "section": "custom",
        "status": "open",
        "sort_order": sort_order,
        "text": cleaned_title,
        "notes": cleaned_notes,
        "source_file": str(DB_PATH),
        "payload": payload,
    }
    items.append(item)
    save_state(TODO_ITEMS_KEY, items)
    return {**item, "created_at": created_at, "source": source}


def load_todo_items() -> list[dict[str, Any]]:
    ensure_schema()
    overrides = load_todo_state_overrides()
    rows = [item for item in load_state(TODO_ITEMS_KEY, []) if isinstance(item, dict)]
    rows.sort(key=lambda item: int(item.get("sort_order", 0)))
    items = []
    for item in rows:
        row = dict(item)
        row["payload"] = row.get("payload", {}) if isinstance(row.get("payload"), dict) else {}
        base_status = str(row.get("status", "open") or "open")
        if base_status == "note":
            base_status = "open"
        row["base_status"] = base_status
        row["status"] = base_status
        override = overrides.get(str(row.get("item_key")))
        if override and row["base_status"] != "done":
            override_status = str(override.get("status", row["status"]))
            row["status"] = override_status if override_status in {"open", "done"} else "open"
            row["status_updated_at"] = override.get("updated_at", "")
            row["status_source"] = override.get("source", "dashboard")
        items.append(row)
    return items


def todo_stats(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(items)
    total = len(items)
    done = sum(1 for item in items if item.get("status") == "done")
    open_count = sum(1 for item in items if item.get("status") == "open")
    categories: dict[str, int] = {}
    for item in items:
        payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
        category = payload.get("category", "other")
        categories[category] = categories.get(category, 0) + 1
    return {"total": total, "done": done, "open": open_count, "notes": 0, "categories": categories, "completion_pct": round(done / total * 100, 1) if total else 0.0}


def latest_timestamp() -> str:
    runs = load_performance_runs(limit=1)
    if not runs:
        return ""
    latest = runs[-1]
    return str(latest.get("timestamp") or latest.get("time") or "")
