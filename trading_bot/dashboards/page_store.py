from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from trading_bot.config.settings import DATABASE_URL
from trading_bot.core import state_store
from trading_bot.core.state_store import connect, load_state, save_state
from trading_bot.dashboards import data_store as legacy_data_store

GLOSSARY_FALLBACK_KEY = "dashboard:glossary_terms"
CRON_JOBS_FALLBACK_KEY = "dashboard:cron_jobs_meta"

PAGE_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS dashboard;

CREATE TABLE IF NOT EXISTS dashboard.glossary_terms (
    term_key TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    content_markdown TEXT NOT NULL,
    content_html TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'glossary.py',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS glossary_terms_active_sort_idx ON dashboard.glossary_terms (is_active, sort_order, title);

CREATE TABLE IF NOT EXISTS dashboard.cron_jobs (
    job_key TEXT PRIMARY KEY,
    job_id TEXT,
    name TEXT NOT NULL,
    schedule TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    deliver TEXT NOT NULL DEFAULT '',
    script TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT '',
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dashboard.cron_runs (
    run_key TEXT PRIMARY KEY,
    job_key TEXT NOT NULL REFERENCES dashboard.cron_jobs(job_key) ON DELETE CASCADE,
    run_timestamp TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    duration_ms BIGINT,
    error_message TEXT,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS cron_runs_job_time_idx ON dashboard.cron_runs (job_key, run_timestamp DESC);
CREATE INDEX IF NOT EXISTS cron_runs_time_idx ON dashboard.cron_runs (run_timestamp DESC);

CREATE TABLE IF NOT EXISTS dashboard.todo_items (
    item_key TEXT PRIMARY KEY,
    section TEXT NOT NULL DEFAULT 'open',
    base_status TEXT NOT NULL DEFAULT 'open',
    current_status TEXT NOT NULL DEFAULT 'open',
    sort_order INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'other',
    source_file TEXT NOT NULL DEFAULT '',
    is_custom BOOLEAN NOT NULL DEFAULT FALSE,
    status_source TEXT NOT NULL DEFAULT 'sync',
    status_updated_at TIMESTAMPTZ,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS todo_items_active_sort_idx ON dashboard.todo_items (is_active, sort_order);
"""


def _db_enabled() -> bool:
    return bool(DATABASE_URL and getattr(state_store, "psycopg", None) is not None)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")
    return slug or "term"


def _hash_key(*parts: str) -> str:
    return hashlib.sha1("|".join(str(part or "").strip() for part in parts).encode("utf-8")).hexdigest()[:20]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _coerce_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value


def ensure_page_schema() -> bool:
    if not _db_enabled():
        return False
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(PAGE_SCHEMA_SQL)
        return True
    except Exception:
        return False


def glossary_seed_records(default_terms: Iterable[tuple[str, str, str]], *, content_html_builder) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for sort_order, (title, category, content_markdown) in enumerate(default_terms):
        term_key = _slugify(title)
        records.append(
            {
                "term_key": term_key,
                "slug": term_key,
                "title": str(title),
                "category": str(category),
                "content_markdown": str(content_markdown),
                "content_html": str(content_html_builder(content_markdown)),
                "sort_order": sort_order,
                "source": "glossary.py",
            }
        )
    return records


def sync_glossary_terms(default_terms: Iterable[tuple[str, str, str]], *, content_html_builder) -> int:
    records = glossary_seed_records(default_terms, content_html_builder=content_html_builder)
    save_state(GLOSSARY_FALLBACK_KEY, records)
    if not ensure_page_schema():
        return len(records)
    keys = [record["term_key"] for record in records]
    try:
        with connect() as conn, conn.cursor() as cur:
            if keys:
                cur.execute("UPDATE dashboard.glossary_terms SET is_active = FALSE, updated_at = NOW() WHERE term_key <> ALL(%s)", (keys,))
            for record in records:
                cur.execute(
                    """
                    INSERT INTO dashboard.glossary_terms
                        (term_key, slug, title, category, content_markdown, content_html, sort_order, source, is_active, updated_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
                    ON CONFLICT (term_key) DO UPDATE SET
                        slug = EXCLUDED.slug,
                        title = EXCLUDED.title,
                        category = EXCLUDED.category,
                        content_markdown = EXCLUDED.content_markdown,
                        content_html = EXCLUDED.content_html,
                        sort_order = EXCLUDED.sort_order,
                        source = EXCLUDED.source,
                        is_active = TRUE,
                        updated_at = NOW()
                    """,
                    (
                        record["term_key"],
                        record["slug"],
                        record["title"],
                        record["category"],
                        record["content_markdown"],
                        record["content_html"],
                        record["sort_order"],
                        record["source"],
                    ),
                )
        return len(records)
    except Exception:
        return len(records)


def load_glossary_terms(default_terms: Iterable[tuple[str, str, str]] | None = None, *, content_html_builder) -> list[dict[str, Any]]:
    if default_terms is not None:
        sync_glossary_terms(default_terms, content_html_builder=content_html_builder)
    if ensure_page_schema():
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT term_key, slug, title, category, content_markdown, content_html, sort_order, source
                    FROM dashboard.glossary_terms
                    WHERE is_active = TRUE
                    ORDER BY sort_order ASC, title ASC
                    """
                )
                rows = cur.fetchall() or []
            if rows:
                return [dict(row) for row in rows]
        except Exception:
            pass
    fallback = load_state(GLOSSARY_FALLBACK_KEY, [])
    if isinstance(fallback, list) and fallback:
        return [dict(item) for item in fallback if isinstance(item, dict)]
    if default_terms is None:
        return []
    return glossary_seed_records(default_terms, content_html_builder=content_html_builder)


def sync_cron_jobs(job_meta: dict[str, dict[str, Any]]) -> int:
    records = []
    for job_key, payload in job_meta.items():
        records.append({
            "job_key": str(job_key),
            "job_id": str(payload.get("job_id", "") or ""),
            "name": str(payload.get("name", job_key) or job_key),
            "schedule": str(payload.get("schedule", "") or ""),
            "details": str(payload.get("details", "") or ""),
            "deliver": str(payload.get("deliver", "") or ""),
            "script": str(payload.get("script", "") or ""),
            "mode": str(payload.get("mode", "") or ""),
            "payload_json": _jsonable(payload),
        })
    save_state(CRON_JOBS_FALLBACK_KEY, records)
    if not ensure_page_schema():
        return len(records)
    keys = [record["job_key"] for record in records]
    try:
        with connect() as conn, conn.cursor() as cur:
            if keys:
                cur.execute("DELETE FROM dashboard.cron_jobs WHERE job_key <> ALL(%s)", (keys,))
            for record in records:
                cur.execute(
                    """
                    INSERT INTO dashboard.cron_jobs
                        (job_key, job_id, name, schedule, details, deliver, script, mode, payload_json, updated_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (job_key) DO UPDATE SET
                        job_id = EXCLUDED.job_id,
                        name = EXCLUDED.name,
                        schedule = EXCLUDED.schedule,
                        details = EXCLUDED.details,
                        deliver = EXCLUDED.deliver,
                        script = EXCLUDED.script,
                        mode = EXCLUDED.mode,
                        payload_json = EXCLUDED.payload_json,
                        updated_at = NOW()
                    """,
                    (
                        record["job_key"],
                        record["job_id"],
                        record["name"],
                        record["schedule"],
                        record["details"],
                        record["deliver"],
                        record["script"],
                        record["mode"],
                        json.dumps(record["payload_json"], ensure_ascii=False),
                    ),
                )
        return len(records)
    except Exception:
        return len(records)


def load_cron_jobs(job_meta: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if job_meta is not None:
        sync_cron_jobs(job_meta)
    if ensure_page_schema():
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT job_key, job_id, name, schedule, details, deliver, script, mode, payload_json
                    FROM dashboard.cron_jobs
                    ORDER BY name ASC
                    """
                )
                rows = cur.fetchall() or []
            if rows:
                return [
                    {
                        **dict(row),
                        "payload_json": _coerce_json(row.get("payload_json"), {}),
                    }
                    for row in rows
                ]
        except Exception:
            pass
    fallback = load_state(CRON_JOBS_FALLBACK_KEY, [])
    if isinstance(fallback, list) and fallback:
        return [dict(item) for item in fallback if isinstance(item, dict)]
    if not job_meta:
        return []
    return [
        {
            "job_key": str(job_key),
            **_jsonable(payload),
            "payload_json": _jsonable(payload),
        }
        for job_key, payload in job_meta.items()
    ]


def sync_cron_runs(path: Path | None = None, job_meta: dict[str, dict[str, Any]] | None = None) -> int:
    if job_meta:
        sync_cron_jobs(job_meta)
    legacy_data_store.sync_cron_runs(path or legacy_data_store.CRON_FILE)
    runs = legacy_data_store.load_cron_runs(limit=2000)
    if not ensure_page_schema():
        return len(runs)
    known_jobs = {row["job_key"] for row in load_cron_jobs(job_meta)}
    try:
        with connect() as conn, conn.cursor() as cur:
            for run in runs:
                job_key = str(run.get("job") or "unknown")
                if job_key not in known_jobs:
                    cur.execute(
                        """
                        INSERT INTO dashboard.cron_jobs (job_key, job_id, name, schedule, details, deliver, script, mode, payload_json, updated_at)
                        VALUES (%s, '', %s, '', '', '', '', '', %s::jsonb, NOW())
                        ON CONFLICT (job_key) DO NOTHING
                        """,
                        (job_key, job_key, json.dumps({}, ensure_ascii=False)),
                    )
                    known_jobs.add(job_key)
                timestamp = str(run.get("timestamp") or _iso_now())
                steps = run.get("steps", {}) if isinstance(run.get("steps"), dict) else {}
                run_key = _hash_key(job_key, timestamp, str(run.get("status") or ""), json.dumps(_jsonable(steps), sort_keys=True))
                error_message = str(run.get("error") or run.get("last_delivery_error") or "") or None
                duration_ms = run.get("duration_ms")
                try:
                    duration_value = int(duration_ms) if duration_ms is not None else None
                except Exception:
                    duration_value = None
                cur.execute(
                    """
                    INSERT INTO dashboard.cron_runs
                        (run_key, job_key, run_timestamp, status, duration_ms, error_message, payload_json, updated_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (run_key) DO UPDATE SET
                        status = EXCLUDED.status,
                        duration_ms = EXCLUDED.duration_ms,
                        error_message = EXCLUDED.error_message,
                        payload_json = EXCLUDED.payload_json,
                        updated_at = NOW()
                    """,
                    (
                        run_key,
                        job_key,
                        timestamp,
                        str(run.get("status") or "unknown"),
                        duration_value,
                        error_message,
                        json.dumps(_jsonable(run), ensure_ascii=False),
                    ),
                )
        return len(runs)
    except Exception:
        return len(runs)


def load_cron_runs(limit: int = 80, job_meta: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if job_meta is not None:
        sync_cron_jobs(job_meta)
    if ensure_page_schema():
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT job_key, run_timestamp, status, duration_ms, error_message, payload_json
                    FROM dashboard.cron_runs
                    ORDER BY run_timestamp DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall() or []
            if rows:
                output = []
                for row in rows:
                    payload = _coerce_json(row.get("payload_json"), {})
                    payload = payload if isinstance(payload, dict) else {}
                    merged = dict(payload)
                    merged.setdefault("job", row.get("job_key"))
                    merged.setdefault("status", row.get("status"))
                    merged.setdefault("duration_ms", row.get("duration_ms"))
                    merged.setdefault("error", row.get("error_message") or "")
                    run_ts = row.get("run_timestamp")
                    merged["timestamp"] = run_ts.isoformat() if isinstance(run_ts, datetime) else str(run_ts)
                    output.append(merged)
                return output
        except Exception:
            pass
    return legacy_data_store.load_cron_runs(limit=limit)


def sync_todo_items() -> int:
    legacy_data_store.sync_todo_items()
    stored_rows = [item for item in load_state(legacy_data_store.TODO_ITEMS_KEY, []) if isinstance(item, dict)]
    overrides = legacy_data_store.load_todo_state_overrides()
    keys = [str(item.get("item_key")) for item in stored_rows if str(item.get("item_key") or "")]
    if not ensure_page_schema():
        return len(stored_rows)
    try:
        with connect() as conn, conn.cursor() as cur:
            if keys:
                cur.execute("UPDATE dashboard.todo_items SET is_active = FALSE, updated_at = NOW() WHERE item_key <> ALL(%s)", (keys,))
            for item in stored_rows:
                item_key = str(item.get("item_key") or "")
                if not item_key:
                    continue
                payload = item.get("payload", {}) if isinstance(item.get("payload"), dict) else {}
                base_status = str(item.get("status", "open") or "open")
                if base_status == "note":
                    base_status = "open"
                current_status = base_status
                override = overrides.get(item_key, {}) if isinstance(overrides, dict) else {}
                if override and base_status != "done":
                    current_status = str(override.get("status") or base_status)
                status_source = str((override or {}).get("source") or "sync")
                status_updated_at = (override or {}).get("updated_at")
                cur.execute(
                    """
                    INSERT INTO dashboard.todo_items
                        (item_key, section, base_status, current_status, sort_order, title, notes, category, source_file, is_custom, status_source, status_updated_at, payload_json, is_active, updated_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, TRUE, NOW())
                    ON CONFLICT (item_key) DO UPDATE SET
                        section = EXCLUDED.section,
                        base_status = EXCLUDED.base_status,
                        current_status = EXCLUDED.current_status,
                        sort_order = EXCLUDED.sort_order,
                        title = EXCLUDED.title,
                        notes = EXCLUDED.notes,
                        category = EXCLUDED.category,
                        source_file = EXCLUDED.source_file,
                        is_custom = EXCLUDED.is_custom,
                        status_source = EXCLUDED.status_source,
                        status_updated_at = EXCLUDED.status_updated_at,
                        payload_json = EXCLUDED.payload_json,
                        is_active = TRUE,
                        updated_at = NOW()
                    """,
                    (
                        item_key,
                        str(item.get("section") or "open"),
                        base_status,
                        current_status if current_status in {"open", "done"} else "open",
                        int(item.get("sort_order", 0) or 0),
                        str(item.get("text") or ""),
                        str(item.get("notes") or ""),
                        str(payload.get("category") or item.get("category") or "other"),
                        str(item.get("source_file") or ""),
                        bool(payload.get("is_custom")),
                        status_source,
                        status_updated_at,
                        json.dumps(_jsonable(payload), ensure_ascii=False),
                    ),
                )
        return len(stored_rows)
    except Exception:
        return len(stored_rows)


def load_todo_items() -> list[dict[str, Any]]:
    if ensure_page_schema():
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT item_key, section, base_status, current_status, sort_order, title, notes, category, source_file,
                           is_custom, status_source, status_updated_at, payload_json
                    FROM dashboard.todo_items
                    WHERE is_active = TRUE
                    ORDER BY sort_order ASC, title ASC
                    """
                )
                rows = cur.fetchall() or []
            if rows:
                output = []
                for row in rows:
                    payload = _coerce_json(row.get("payload_json"), {})
                    payload = payload if isinstance(payload, dict) else {}
                    payload.setdefault("category", row.get("category") or "other")
                    payload.setdefault("is_custom", bool(row.get("is_custom")))
                    record = {
                        "item_key": str(row.get("item_key") or ""),
                        "section": str(row.get("section") or "open"),
                        "status": str(row.get("current_status") or "open"),
                        "base_status": str(row.get("base_status") or "open"),
                        "sort_order": int(row.get("sort_order") or 0),
                        "text": str(row.get("title") or ""),
                        "notes": str(row.get("notes") or ""),
                        "source_file": str(row.get("source_file") or ""),
                        "payload": payload,
                    }
                    if row.get("status_source"):
                        record["status_source"] = str(row.get("status_source"))
                    if row.get("status_updated_at"):
                        stamp = row.get("status_updated_at")
                        record["status_updated_at"] = stamp.isoformat() if isinstance(stamp, datetime) else str(stamp)
                    output.append(record)
                return output
        except Exception:
            pass
    return legacy_data_store.load_todo_items()


def save_todo_state(item_key: str, status: str, source: str = "dashboard") -> dict[str, Any]:
    normalized_status = status if status in {"open", "done"} else "open"
    updated_at = _iso_now()
    if not ensure_page_schema():
        return legacy_data_store.save_todo_state(item_key=item_key, status=status, source=source)
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard.todo_items
                SET current_status = CASE WHEN base_status = 'done' THEN base_status ELSE %s END,
                    status_source = %s,
                    status_updated_at = %s,
                    updated_at = NOW()
                WHERE item_key = %s AND is_active = TRUE
                """,
                (normalized_status, source, updated_at, item_key),
            )
            if cur.rowcount == 0:
                return legacy_data_store.save_todo_state(item_key=item_key, status=status, source=source)
        legacy_data_store.save_todo_state(item_key=item_key, status=status, source=source)
        return {"item_key": item_key, "status": normalized_status, "updated_at": updated_at, "source": source}
    except Exception:
        return legacy_data_store.save_todo_state(item_key=item_key, status=status, source=source)


def create_todo_item(title: str, notes: str = "", source: str = "dashboard") -> dict[str, Any]:
    cleaned_title = legacy_data_store._normalize(title)
    cleaned_notes = str(notes or "").strip()
    if not cleaned_title:
        raise ValueError("title is required")
    created_at = _iso_now()
    if not ensure_page_schema():
        return legacy_data_store.create_todo_item(title=title, notes=notes, source=source)
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_sort FROM dashboard.todo_items WHERE is_active = TRUE")
            row = cur.fetchone() or {"next_sort": 0}
            sort_order = int(row.get("next_sort") or 0)
            item_key = _hash_key("custom", cleaned_title, created_at)
            payload = {
                "section": "custom",
                "status": "open",
                "sort_order": sort_order,
                "text": cleaned_title,
                "notes": cleaned_notes,
                "source_file": str(legacy_data_store.DB_PATH),
                "category": "other",
                "is_custom": True,
                "created_at": created_at,
            }
            cur.execute(
                """
                INSERT INTO dashboard.todo_items
                    (item_key, section, base_status, current_status, sort_order, title, notes, category, source_file, is_custom, status_source, status_updated_at, payload_json, is_active, updated_at)
                VALUES
                    (%s, 'custom', 'open', 'open', %s, %s, %s, 'other', %s, TRUE, %s, %s, %s::jsonb, TRUE, NOW())
                """,
                (
                    item_key,
                    sort_order,
                    cleaned_title,
                    cleaned_notes,
                    str(legacy_data_store.DB_PATH),
                    source,
                    created_at,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
        items = [item for item in load_state(legacy_data_store.TODO_ITEMS_KEY, []) if isinstance(item, dict)]
        items.append(
            {
                "item_key": item_key,
                "section": "custom",
                "status": "open",
                "sort_order": sort_order,
                "text": cleaned_title,
                "notes": cleaned_notes,
                "source_file": str(legacy_data_store.DB_PATH),
                "payload": payload,
            }
        )
        save_state(legacy_data_store.TODO_ITEMS_KEY, items)
        return {
            "item_key": item_key,
            "section": "custom",
            "status": "open",
            "base_status": "open",
            "sort_order": sort_order,
            "text": cleaned_title,
            "notes": cleaned_notes,
            "source_file": str(legacy_data_store.DB_PATH),
            "payload": payload,
            "created_at": created_at,
            "source": source,
        }
    except Exception:
        return legacy_data_store.create_todo_item(title=title, notes=notes, source=source)


def todo_stats(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return legacy_data_store.todo_stats(items)


def sync_page_data(*, glossary_terms: Iterable[tuple[str, str, str]], content_html_builder, cron_jobs: dict[str, dict[str, Any]]) -> dict[str, int]:
    return {
        "glossary_terms": sync_glossary_terms(glossary_terms, content_html_builder=content_html_builder),
        "cron_jobs": sync_cron_jobs(cron_jobs),
        "cron_runs": sync_cron_runs(job_meta=cron_jobs),
        "todo_items": sync_todo_items(),
    }
