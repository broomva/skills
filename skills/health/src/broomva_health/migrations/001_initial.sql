-- 001_initial.sql — initial trace schema.
--
-- All TEXT timestamps store ISO 8601 UTC (from `.isoformat()` on a UTC-aware datetime).
-- All `*_json` columns store deterministically-serialized JSON (sort_keys=True).

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quantity_sample (
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    device_json TEXT,
    metadata_json TEXT,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (source, metric, start_ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS category_sample (
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    category TEXT NOT NULL,
    device_json TEXT,
    metadata_json TEXT,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (source, metric, start_ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS correlation_sample (
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    components_json TEXT NOT NULL,
    units_json TEXT NOT NULL,
    device_json TEXT,
    metadata_json TEXT,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (source, metric, start_ts)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS workout (
    source TEXT NOT NULL,
    activity_id TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT,
    duration_s INTEGER NOT NULL,
    distance_m REAL,
    kcal REAL,
    avg_hr REAL,
    max_hr REAL,
    training_effect REAL,
    training_stress_score REAL,
    device_json TEXT,
    fit_blob_sha256 TEXT,
    raw_summary_json TEXT,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (source, activity_id)
) WITHOUT ROWID;
