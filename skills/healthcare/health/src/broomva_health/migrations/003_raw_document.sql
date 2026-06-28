-- 003_raw_document.sql — lossless raw-passthrough store.
--
-- The structured tables (quantity_sample, …) keep a curated, typed subset of
-- each upstream response. This table keeps the WHOLE response, verbatim, so the
-- agent can reach any field we did not map (e.g. Garmin's daily summary returns
-- ~94 fields; we type ~5). One row per (source, calendar_date, endpoint); the
-- payload is the raw JSON exactly as returned. INSERT OR REPLACE keyed on the
-- PK makes a re-backfill overwrite losslessly and idempotently.

CREATE TABLE IF NOT EXISTS raw_document (
    source        TEXT NOT NULL,
    calendar_date TEXT NOT NULL,   -- 'YYYY-MM-DD', the local day the doc pertains to
    endpoint      TEXT NOT NULL,   -- logical name: daily_summary, sleep, hrv, stress, …
    fetched_at    TEXT NOT NULL,   -- ISO-8601 UTC timestamp of the pull
    payload_json  TEXT NOT NULL,   -- the raw response, verbatim (object or array)
    PRIMARY KEY (source, calendar_date, endpoint)
);

CREATE INDEX IF NOT EXISTS ix_raw_document_source_date ON raw_document(source, calendar_date);
CREATE INDEX IF NOT EXISTS ix_raw_document_endpoint ON raw_document(endpoint);
