-- A source can hold several producers (Apple Health holds every app and device
-- that wrote to it), and distinct records of one producer can share a start
-- time (an in-bed record and the first sleep stage). Add `producer` for
-- provenance and `record_key` to each sample's identity. Sources that update a
-- sample in place (Garmin) leave record_key '' and keep their identity, and so
-- do all existing rows.

CREATE TABLE quantity_sample_new (
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    device_json TEXT,
    metadata_json TEXT,
    ingested_at TEXT NOT NULL,
    producer TEXT NOT NULL DEFAULT '',
    record_key TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source, metric, start_ts, record_key)
) WITHOUT ROWID;
INSERT INTO quantity_sample_new
    (source, metric, start_ts, end_ts, value, unit, device_json, metadata_json, ingested_at)
    SELECT source, metric, start_ts, end_ts, value, unit, device_json, metadata_json, ingested_at
    FROM quantity_sample;
DROP TABLE quantity_sample;
ALTER TABLE quantity_sample_new RENAME TO quantity_sample;

CREATE TABLE category_sample_new (
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    category TEXT NOT NULL,
    device_json TEXT,
    metadata_json TEXT,
    ingested_at TEXT NOT NULL,
    producer TEXT NOT NULL DEFAULT '',
    record_key TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source, metric, start_ts, record_key)
) WITHOUT ROWID;
INSERT INTO category_sample_new
    (source, metric, start_ts, end_ts, category, device_json, metadata_json, ingested_at)
    SELECT source, metric, start_ts, end_ts, category, device_json, metadata_json, ingested_at
    FROM category_sample;
DROP TABLE category_sample;
ALTER TABLE category_sample_new RENAME TO category_sample;

CREATE TABLE correlation_sample_new (
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    start_ts TEXT NOT NULL,
    end_ts TEXT NOT NULL,
    components_json TEXT NOT NULL,
    units_json TEXT NOT NULL,
    device_json TEXT,
    metadata_json TEXT,
    ingested_at TEXT NOT NULL,
    producer TEXT NOT NULL DEFAULT '',
    record_key TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source, metric, start_ts, record_key)
) WITHOUT ROWID;
INSERT INTO correlation_sample_new
    (source, metric, start_ts, end_ts, components_json, units_json, device_json, metadata_json,
     ingested_at)
    SELECT source, metric, start_ts, end_ts, components_json, units_json, device_json,
           metadata_json, ingested_at
    FROM correlation_sample;
DROP TABLE correlation_sample;
ALTER TABLE correlation_sample_new RENAME TO correlation_sample;

-- DROP TABLE removed the 002 indexes with their tables, so recreate them.
CREATE INDEX IF NOT EXISTS ix_quantity_metric_start ON quantity_sample(metric, start_ts);
CREATE INDEX IF NOT EXISTS ix_quantity_source_metric_start ON quantity_sample(source, metric, start_ts);
CREATE INDEX IF NOT EXISTS ix_category_metric_start ON category_sample(metric, start_ts);
