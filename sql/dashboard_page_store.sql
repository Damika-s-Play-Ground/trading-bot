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
