from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - dependency added in requirements
    psycopg = None
    dict_row = None

from trading_bot.config.settings import DATABASE_URL, REPO_ROOT


LOCAL_DATA_DIR = REPO_ROOT / "data"
LOCAL_FALLBACK_PATH = LOCAL_DATA_DIR / "runtime_state.json"

APP_STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS app_state (
    state_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS app_configs (
    config_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS app_blobs (
    blob_key TEXT PRIMARY KEY,
    payload_text TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

STATE_KEY_MAP = {
    "config.json": "config:spot",
    "config_trend.json": "config:trend",
    "paper_state.json": "state:paper:dca",
    "paper_trend.json": "state:paper:trend",
    "paper_grid.json": "state:paper:grid",
    "paper_momentum.json": "state:paper:momentum",
    "paper_deepmr.json": "state:paper:deep_mr",
    "paper_futures.json": "state:paper:futures",
    "manager_state.json": "state:manager",
    "manager_portfolio.json": "state:manager_portfolio",
    "performance_journal.json": "state:performance_journal",
    "market_data.json": "state:market_data",
    "allocation_optimizer_snapshot.json": "state:allocation_optimizer_snapshot",
    "candidate_scores.json": "state:candidate_scores",
    "live_promotion_report.json": "state:live_promotion_report",
    "optimizer_results.json": "state:optimizer_results",
    "cron.json": "state:cron_log",
}


@contextmanager
def connect() -> Iterator[Any]:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    if psycopg is None:
        raise RuntimeError("psycopg is not installed")
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(APP_STATE_TABLE_SQL)
        conn.commit()
        yield conn


def _fallback_load() -> dict[str, Any]:
    if not LOCAL_FALLBACK_PATH.exists():
        return {"state": {}, "configs": {}, "blobs": {}}
    try:
        return json.loads(LOCAL_FALLBACK_PATH.read_text())
    except Exception:
        return {"state": {}, "configs": {}, "blobs": {}}


def _fallback_save(payload: dict[str, Any]) -> None:
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_FALLBACK_PATH.write_text(json.dumps(payload, indent=2))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _basename_key(path: str | Path) -> str:
    return Path(path).name


def key_for_path(path: str | Path) -> str:
    return STATE_KEY_MAP.get(_basename_key(path), f"state:{_basename_key(path)}")


def load_state(key: str, default: Any) -> Any:
    if DATABASE_URL and psycopg is not None:
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT payload_json FROM app_state WHERE state_key = %s", (key,))
                row = cur.fetchone()
                if row:
                    return json.loads(row["payload_json"])
        except Exception:
            pass
    data = _fallback_load()
    return data.get("state", {}).get(key, default)


def save_state(key: str, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    if DATABASE_URL and psycopg is not None:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_state (state_key, payload_json, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (state_key) DO UPDATE SET
                    payload_json = EXCLUDED.payload_json,
                    updated_at = NOW()
                """,
                (key, text),
            )
        return
    data = _fallback_load()
    data.setdefault("state", {})[key] = payload
    _fallback_save(data)


def load_config(key: str, default: Any) -> Any:
    if DATABASE_URL and psycopg is not None:
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT payload_json FROM app_configs WHERE config_key = %s", (key,))
                row = cur.fetchone()
                if row:
                    return json.loads(row["payload_json"])
        except Exception:
            pass
    data = _fallback_load()
    return data.get("configs", {}).get(key, default)


def save_config(key: str, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    if DATABASE_URL and psycopg is not None:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_configs (config_key, payload_json, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (config_key) DO UPDATE SET
                    payload_json = EXCLUDED.payload_json,
                    updated_at = NOW()
                """,
                (key, text),
            )
        return
    data = _fallback_load()
    data.setdefault("configs", {})[key] = payload
    _fallback_save(data)


def load_blob(key: str, default: str = "") -> str:
    if DATABASE_URL and psycopg is not None:
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT payload_text FROM app_blobs WHERE blob_key = %s", (key,))
                row = cur.fetchone()
                if row:
                    return str(row["payload_text"])
        except Exception:
            pass
    data = _fallback_load()
    return str(data.get("blobs", {}).get(key, default))


def save_blob(key: str, payload: str) -> None:
    if DATABASE_URL and psycopg is not None:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_blobs (blob_key, payload_text, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (blob_key) DO UPDATE SET
                    payload_text = EXCLUDED.payload_text,
                    updated_at = NOW()
                """,
                (key, payload),
            )
        return
    data = _fallback_load()
    data.setdefault("blobs", {})[key] = payload
    _fallback_save(data)


def load_json_path(path: str | Path, default: Any) -> Any:
    name = _basename_key(path)
    key = key_for_path(path)
    if name in {"config.json", "config_trend.json"}:
        return load_config(key, default)
    return load_state(key, default)


def save_json_path(path: str | Path, payload: Any) -> None:
    name = _basename_key(path)
    key = key_for_path(path)
    if name in {"config.json", "config_trend.json"}:
        save_config(key, payload)
        return
    save_state(key, payload)


def import_json_file(path: str | Path, *, is_config: bool = False, state_key: str | None = None) -> bool:
    source = Path(path)
    if not source.exists():
        return False
    try:
        payload = json.loads(source.read_text())
    except Exception:
        return False
    key = state_key or key_for_path(source)
    if is_config or source.name in {"config.json", "config_trend.json"}:
        save_config(key, payload)
    else:
        save_state(key, payload)
    return True
