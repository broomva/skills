"""SQLite TraceRepository — the default trace storage adapter."""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

import broomva_health.migrations as _migrations_pkg
from broomva_health.domain.device import Device
from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.samples import CategorySample, CorrelationSample, QuantitySample
from broomva_health.domain.source import Source
from broomva_health.domain.time import ensure_utc, utc_now
from broomva_health.domain.workout import Workout
from broomva_health.migrations.runner import MigrationRunner

__all__ = ["SQLiteTraceRepository"]

_ENCRYPTED_V1_MSG = (
    "SQLCipher upgrade lands in v1.1; see References/privacy-architecture.md"
)


def _dumps(value: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _device_to_json(device: Device | None) -> str | None:
    """Serialize a Device value object (or NULL)."""
    if device is None:
        return None
    return _dumps(device.model_dump(mode="json"))


def _device_from_json(blob: str | None) -> Device | None:
    """Rebuild a Device from its JSON blob (or None)."""
    if blob is None:
        return None
    data = json.loads(blob)
    return Device.model_validate(data)


def _metadata_to_json(metadata: dict[str, Any]) -> str | None:
    """Serialize sample metadata (NULL when empty for storage compactness)."""
    if not metadata:
        return None
    return _dumps(metadata)


def _metadata_from_json(blob: str | None) -> dict[str, Any]:
    """Rebuild sample metadata from JSON (empty dict for NULL)."""
    if blob is None:
        return {}
    data = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError(f"metadata_json did not deserialize to a dict: {data!r}")
    return data


def _parse_ts(value: str) -> datetime:
    """Parse an ISO-8601 timestamp string back to a UTC-aware datetime."""
    return ensure_utc(datetime.fromisoformat(value))


class SQLiteTraceRepository:
    """SQLite-backed implementation of the `TraceRepository` protocol.

    Connection is opened with `isolation_level=None` (autocommit), which
    lets the migration runner manage its own explicit transactions.
    PRAGMAs `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL`
    are applied at open.

    Encryption: `encrypt=True` raises `NotImplementedError` for v1 — the
    SQLCipher path is documented in `References/privacy-architecture.md`
    and lands in v1.1.

    The repository is a context manager: `with SQLiteTraceRepository(p) as r:`
    closes the connection on exit.
    """

    def __init__(
        self,
        db_path: Path,
        *,
        encrypt: bool = False,
        encryption_key: str | None = None,  # noqa: ARG002 — reserved for v1.1
    ) -> None:
        if encrypt:
            raise NotImplementedError(_ENCRYPTED_V1_MSG)
        self._db_path = Path(db_path)
        # Ensure parent dir exists for fresh on-disk DBs (in-memory paths skip this).
        if str(self._db_path) != ":memory:" and self._db_path.parent != Path():
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self._db_path,
            isolation_level=None,
            check_same_thread=False,
            detect_types=0,
        )
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    # ------------------------------------------------------------------ #
    # Context manager
    # ------------------------------------------------------------------ #
    def __enter__(self) -> SQLiteTraceRepository:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def migrate(self) -> int:
        """Apply any pending schema migrations. Idempotent.

        Returns:
            The number of migrations newly applied.
        """
        migrations_dir = Path(_migrations_pkg.__file__).parent
        runner = MigrationRunner(self._conn, migrations_dir)
        return runner.apply_all()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._conn is not None:
            self._conn.close()

    # ------------------------------------------------------------------ #
    # Upserts
    # ------------------------------------------------------------------ #
    def upsert_quantity(self, samples: list[QuantitySample]) -> int:
        """Insert-or-replace quantity samples. Idempotent on (source, metric, start_ts)."""
        if not samples:
            return 0
        rows = [self._serialize_quantity_row(s) for s in samples]
        with self._txn():
            self._conn.executemany(
                "INSERT OR REPLACE INTO quantity_sample "
                "(source, metric, start_ts, end_ts, value, unit, "
                " device_json, metadata_json, ingested_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def upsert_category(self, samples: list[CategorySample]) -> int:
        """Insert-or-replace category samples. Idempotent on (source, metric, start_ts)."""
        if not samples:
            return 0
        rows = [self._serialize_category_row(s) for s in samples]
        with self._txn():
            self._conn.executemany(
                "INSERT OR REPLACE INTO category_sample "
                "(source, metric, start_ts, end_ts, category, "
                " device_json, metadata_json, ingested_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def upsert_correlation(self, samples: list[CorrelationSample]) -> int:
        """Insert-or-replace correlation samples. Idempotent on (source, metric, start_ts)."""
        if not samples:
            return 0
        rows = [self._serialize_correlation_row(s) for s in samples]
        with self._txn():
            self._conn.executemany(
                "INSERT OR REPLACE INTO correlation_sample "
                "(source, metric, start_ts, end_ts, components_json, units_json, "
                " device_json, metadata_json, ingested_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def upsert_workout(self, workouts: list[Workout]) -> int:
        """Insert-or-replace workouts. Idempotent on (source, activity_id)."""
        if not workouts:
            return 0
        rows = [self._serialize_workout_row(w) for w in workouts]
        with self._txn():
            self._conn.executemany(
                "INSERT OR REPLACE INTO workout "
                "(source, activity_id, activity_type, start_ts, end_ts, duration_s, "
                " distance_m, kcal, avg_hr, max_hr, training_effect, training_stress_score, "
                " device_json, fit_blob_sha256, raw_summary_json, ingested_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def last_sample_ts(self, source: Source, metric: MetricCode) -> datetime | None:
        """Max(end_ts) for the given (source, metric), or None if empty.

        Used by the sync loop to know where to resume from.
        """
        row = self._conn.execute(
            "SELECT MAX(end_ts) FROM quantity_sample WHERE source = ? AND metric = ?",
            (str(source), str(metric)),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return _parse_ts(row[0])

    def query_quantity(
        self,
        source: Source | None,
        metric: MetricCode,
        start: datetime,
        end: datetime,
    ) -> list[QuantitySample]:
        """Read quantity samples in `[start, end]` for `metric` (and optionally source)."""
        start_iso = ensure_utc(start).isoformat()
        end_iso = ensure_utc(end).isoformat()
        if source is None:
            cursor = self._conn.execute(
                "SELECT source, metric, start_ts, end_ts, value, unit, "
                "       device_json, metadata_json, ingested_at "
                "FROM quantity_sample "
                "WHERE metric = ? AND start_ts >= ? AND start_ts <= ? "
                "ORDER BY start_ts ASC",
                (str(metric), start_iso, end_iso),
            )
        else:
            cursor = self._conn.execute(
                "SELECT source, metric, start_ts, end_ts, value, unit, "
                "       device_json, metadata_json, ingested_at "
                "FROM quantity_sample "
                "WHERE source = ? AND metric = ? AND start_ts >= ? AND start_ts <= ? "
                "ORDER BY start_ts ASC",
                (str(source), str(metric), start_iso, end_iso),
            )
        return [self._deserialize_quantity_row(row) for row in cursor.fetchall()]

    def query_workouts(
        self,
        source: Source | None,
        start: datetime,
        end: datetime,
    ) -> list[Workout]:
        """Read workouts whose `start_ts` falls inside `[start, end]`."""
        start_iso = ensure_utc(start).isoformat()
        end_iso = ensure_utc(end).isoformat()
        if source is None:
            cursor = self._conn.execute(
                "SELECT source, activity_id, activity_type, start_ts, end_ts, duration_s, "
                "       distance_m, kcal, avg_hr, max_hr, training_effect, training_stress_score, "
                "       device_json, fit_blob_sha256, raw_summary_json, ingested_at "
                "FROM workout "
                "WHERE start_ts >= ? AND start_ts <= ? "
                "ORDER BY start_ts ASC",
                (start_iso, end_iso),
            )
        else:
            cursor = self._conn.execute(
                "SELECT source, activity_id, activity_type, start_ts, end_ts, duration_s, "
                "       distance_m, kcal, avg_hr, max_hr, training_effect, training_stress_score, "
                "       device_json, fit_blob_sha256, raw_summary_json, ingested_at "
                "FROM workout "
                "WHERE source = ? AND start_ts >= ? AND start_ts <= ? "
                "ORDER BY start_ts ASC",
                (str(source), start_iso, end_iso),
            )
        return [self._deserialize_workout_row(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    class _Txn:
        """Tiny BEGIN/COMMIT helper for autocommit-mode connections."""

        def __init__(self, conn: sqlite3.Connection) -> None:
            self._conn = conn

        def __enter__(self) -> None:
            self._conn.execute("BEGIN")

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> None:
            if exc is None:
                self._conn.execute("COMMIT")
            else:
                with contextlib.suppress(sqlite3.OperationalError):
                    self._conn.execute("ROLLBACK")

    def _txn(self) -> _Txn:
        return SQLiteTraceRepository._Txn(self._conn)

    # ---- row (de)serialization -------------------------------------- #
    def _serialize_quantity_row(
        self, s: QuantitySample
    ) -> tuple[str, str, str, str, float, str, str | None, str | None, str]:
        return (
            str(s.source),
            str(s.metric),
            s.start_ts.isoformat(),
            s.end_ts.isoformat(),
            float(s.value),
            s.unit,
            _device_to_json(s.device),
            _metadata_to_json(s.metadata),
            s.ingested_at.isoformat(),
        )

    def _serialize_category_row(
        self, s: CategorySample
    ) -> tuple[str, str, str, str, str, str | None, str | None, str]:
        return (
            str(s.source),
            str(s.metric),
            s.start_ts.isoformat(),
            s.end_ts.isoformat(),
            s.category,
            _device_to_json(s.device),
            _metadata_to_json(s.metadata),
            s.ingested_at.isoformat(),
        )

    def _serialize_correlation_row(
        self, s: CorrelationSample
    ) -> tuple[str, str, str, str, str, str, str | None, str | None, str]:
        return (
            str(s.source),
            str(s.metric),
            s.start_ts.isoformat(),
            s.end_ts.isoformat(),
            _dumps(s.components),
            _dumps(s.unit_by_component),
            _device_to_json(s.device),
            _metadata_to_json(s.metadata),
            s.ingested_at.isoformat(),
        )

    def _serialize_workout_row(
        self, w: Workout
    ) -> tuple[
        str,
        str,
        str,
        str,
        str | None,
        int,
        float | None,
        float | None,
        float | None,
        float | None,
        float | None,
        float | None,
        str | None,
        str | None,
        str | None,
        str,
    ]:
        return (
            str(w.source),
            w.activity_id,
            w.activity_type,
            w.start_ts.isoformat(),
            w.end_ts.isoformat() if w.end_ts is not None else None,
            int(w.duration_s),
            w.distance_m,
            w.kcal,
            w.avg_hr,
            w.max_hr,
            w.training_effect,
            w.training_stress_score,
            _device_to_json(w.device),
            w.fit_blob_sha256,
            _dumps(w.raw_summary) if w.raw_summary else None,
            w.ingested_at.isoformat(),
        )

    def _deserialize_quantity_row(self, row: tuple[Any, ...]) -> QuantitySample:
        (
            source,
            metric,
            start_ts,
            end_ts,
            value,
            unit,
            device_json,
            metadata_json,
            ingested_at,
        ) = row
        return QuantitySample(
            source=Source(source),
            metric=MetricCode(metric),
            start_ts=_parse_ts(start_ts),
            end_ts=_parse_ts(end_ts),
            value=float(value),
            unit=unit,
            device=_device_from_json(device_json),
            metadata=_metadata_from_json(metadata_json),
            ingested_at=_parse_ts(ingested_at),
        )

    def _deserialize_category_row(self, row: tuple[Any, ...]) -> CategorySample:
        (
            source,
            metric,
            start_ts,
            end_ts,
            category,
            device_json,
            metadata_json,
            ingested_at,
        ) = row
        return CategorySample(
            source=Source(source),
            metric=MetricCode(metric),
            start_ts=_parse_ts(start_ts),
            end_ts=_parse_ts(end_ts),
            category=category,
            device=_device_from_json(device_json),
            metadata=_metadata_from_json(metadata_json),
            ingested_at=_parse_ts(ingested_at),
        )

    def _deserialize_correlation_row(self, row: tuple[Any, ...]) -> CorrelationSample:
        (
            source,
            metric,
            start_ts,
            end_ts,
            components_json,
            units_json,
            device_json,
            metadata_json,
            ingested_at,
        ) = row
        return CorrelationSample(
            source=Source(source),
            metric=MetricCode(metric),
            start_ts=_parse_ts(start_ts),
            end_ts=_parse_ts(end_ts),
            components={k: float(v) for k, v in json.loads(components_json).items()},
            unit_by_component=dict(json.loads(units_json)),
            device=_device_from_json(device_json),
            metadata=_metadata_from_json(metadata_json),
            ingested_at=_parse_ts(ingested_at),
        )

    def _deserialize_workout_row(self, row: tuple[Any, ...]) -> Workout:
        (
            source,
            activity_id,
            activity_type,
            start_ts,
            end_ts,
            duration_s,
            distance_m,
            kcal,
            avg_hr,
            max_hr,
            training_effect,
            training_stress_score,
            device_json,
            fit_blob_sha256,
            raw_summary_json,
            ingested_at,
        ) = row
        raw_summary: dict[str, Any] = {}
        if raw_summary_json is not None:
            loaded = json.loads(raw_summary_json)
            if not isinstance(loaded, dict):
                raise ValueError(f"raw_summary_json did not deserialize to a dict: {loaded!r}")
            raw_summary = loaded
        return Workout(
            source=Source(source),
            activity_id=activity_id,
            activity_type=activity_type,
            start_ts=_parse_ts(start_ts),
            end_ts=_parse_ts(end_ts) if end_ts is not None else None,
            duration_s=int(duration_s),
            distance_m=distance_m,
            kcal=kcal,
            avg_hr=avg_hr,
            max_hr=max_hr,
            training_effect=training_effect,
            training_stress_score=training_stress_score,
            device=_device_from_json(device_json),
            fit_blob_sha256=fit_blob_sha256,
            raw_summary=raw_summary,
            ingested_at=_parse_ts(ingested_at),
        )


# Suppress unused-import lint if utc_now is only used via tests.
_ = utc_now
