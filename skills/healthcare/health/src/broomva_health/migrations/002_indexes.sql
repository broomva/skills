-- 002_indexes.sql — read-path indexes for time-windowed queries.

CREATE INDEX IF NOT EXISTS ix_quantity_metric_start ON quantity_sample(metric, start_ts);
CREATE INDEX IF NOT EXISTS ix_quantity_source_metric_start ON quantity_sample(source, metric, start_ts);
CREATE INDEX IF NOT EXISTS ix_category_metric_start ON category_sample(metric, start_ts);
CREATE INDEX IF NOT EXISTS ix_workout_start ON workout(start_ts);
CREATE INDEX IF NOT EXISTS ix_workout_type_start ON workout(activity_type, start_ts);
