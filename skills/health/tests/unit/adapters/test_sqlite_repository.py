"""SQLiteTraceRepository — adapter-level tests."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from broomva_health.adapters.repositories.sqlite import SQLiteTraceRepository
from broomva_health.domain.device import Device
from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.samples import CategorySample, CorrelationSample, QuantitySample
from broomva_health.domain.source import Source
from broomva_health.domain.workout import Workout


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Fresh on-disk SQLite database per test."""
    return tmp_path / "trace.db"


@pytest.fixture
def repo(db_path: Path):  # type: ignore[no-untyped-def]
    r = SQLiteTraceRepository(db_path)
    r.migrate()
    try:
        yield r
    finally:
        r.close()


def _t(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _qs(
    *,
    source: Source = Source.GARMIN,
    metric: MetricCode = MetricCode.HEART_RATE,
    start: datetime | None = None,
    value: float = 64.0,
    unit: str = "bpm",
    device: Device | None = None,
    metadata: dict | None = None,
) -> QuantitySample:
    start = start or _t(2026, 5, 22, 12, 0)
    return QuantitySample(
        source=source,
        metric=metric,
        start_ts=start,
        end_ts=start + timedelta(seconds=1),
        value=value,
        unit=unit,
        device=device,
        metadata=metadata or {},
    )


# --------------------------------------------------------------------------- #
# Migration idempotency
# --------------------------------------------------------------------------- #
def test_migrate_is_idempotent(db_path: Path) -> None:
    r = SQLiteTraceRepository(db_path)
    try:
        first = r.migrate()
        second = r.migrate()
        assert first >= 2  # 001_initial + 002_indexes
        assert second == 0
    finally:
        r.close()


# --------------------------------------------------------------------------- #
# Quantity samples
# --------------------------------------------------------------------------- #
def test_upsert_quantity_roundtrip(repo: SQLiteTraceRepository) -> None:
    base = _t(2026, 5, 22, 8, 0)
    samples = [
        _qs(start=base + timedelta(minutes=i), value=60.0 + i, metadata={"src_id": str(i)})
        for i in range(3)
    ]
    n = repo.upsert_quantity(samples)
    assert n == 3
    out = repo.query_quantity(
        Source.GARMIN,
        MetricCode.HEART_RATE,
        base - timedelta(minutes=1),
        base + timedelta(minutes=10),
    )
    assert len(out) == 3
    for original, fetched in zip(samples, out, strict=True):
        # ingested_at is set by domain default — not stable across roundtrip if
        # the test recreated samples, so compare the user-set fields only.
        assert fetched.source == original.source
        assert fetched.metric == original.metric
        assert fetched.start_ts == original.start_ts
        assert fetched.end_ts == original.end_ts
        assert fetched.value == original.value
        assert fetched.unit == original.unit
        assert fetched.metadata == original.metadata
        assert fetched.device == original.device


def test_upsert_quantity_idempotent(repo: SQLiteTraceRepository) -> None:
    s1 = _qs(value=60.0)
    s2 = _qs(value=99.0)  # same (source, metric, start_ts), different value
    assert repo.upsert_quantity([s1]) == 1
    assert repo.upsert_quantity([s2]) == 1  # REPLACE counts as 1 logical op
    row_count = repo._conn.execute(
        "SELECT COUNT(*) FROM quantity_sample"
    ).fetchone()[0]
    assert row_count == 1  # idempotent — no duplicate row
    out = repo.query_quantity(
        Source.GARMIN,
        MetricCode.HEART_RATE,
        _t(2026, 5, 22, 0, 0),
        _t(2026, 5, 22, 23, 59),
    )
    assert len(out) == 1
    assert out[0].value == 99.0  # second write wins


def test_upsert_quantity_with_device_roundtrip(repo: SQLiteTraceRepository) -> None:
    device = Device(
        manufacturer="garmin",
        product="fenix 7x sapphire solar",
        hardware_id="ABC123",
        software_version="14.50",
    )
    s = _qs(device=device, metadata={"src_id": "1", "nested": {"k": [1, 2, 3]}})
    repo.upsert_quantity([s])
    out = repo.query_quantity(
        Source.GARMIN,
        MetricCode.HEART_RATE,
        _t(2026, 5, 22, 0, 0),
        _t(2026, 5, 22, 23, 59),
    )
    assert len(out) == 1
    assert out[0].device == device
    assert out[0].metadata == s.metadata


# --------------------------------------------------------------------------- #
# Category samples
# --------------------------------------------------------------------------- #
def test_upsert_category_roundtrip(repo: SQLiteTraceRepository) -> None:
    base = _t(2026, 5, 22, 1, 0)
    samples = [
        CategorySample(
            source=Source.GARMIN,
            metric=MetricCode.SLEEP_STAGE,
            start_ts=base + timedelta(minutes=i * 5),
            end_ts=base + timedelta(minutes=(i + 1) * 5),
            category=cat,
        )
        for i, cat in enumerate(["awake", "light", "deep", "rem"])
    ]
    assert repo.upsert_category(samples) == 4
    # Direct DB read — we don't have a query_category method in the protocol.
    rows = repo._conn.execute(  # type: ignore[attr-defined]
        "SELECT source, metric, start_ts, category FROM category_sample ORDER BY start_ts"
    ).fetchall()
    assert [r[3] for r in rows] == ["awake", "light", "deep", "rem"]
    # Idempotent replace.
    replacement = CategorySample(
        source=Source.GARMIN,
        metric=MetricCode.SLEEP_STAGE,
        start_ts=base,
        end_ts=base + timedelta(minutes=5),
        category="deep",
    )
    repo.upsert_category([replacement])
    count = repo._conn.execute(  # type: ignore[attr-defined]
        "SELECT COUNT(*) FROM category_sample"
    ).fetchone()[0]
    assert count == 4


# --------------------------------------------------------------------------- #
# Correlation samples
# --------------------------------------------------------------------------- #
def test_upsert_correlation_roundtrip(repo: SQLiteTraceRepository) -> None:
    start = _t(2026, 5, 22, 7, 30)
    bp = CorrelationSample(
        source=Source.MANUAL,
        metric=MetricCode.BLOOD_PRESSURE,
        start_ts=start,
        end_ts=start + timedelta(seconds=1),
        components={"systolic": 121.0, "diastolic": 78.0, "pulse": 64.0},
        unit_by_component={"systolic": "mmHg", "diastolic": "mmHg", "pulse": "bpm"},
        metadata={"cuff": "omron-x7"},
    )
    assert repo.upsert_correlation([bp]) == 1
    row = repo._conn.execute(  # type: ignore[attr-defined]
        "SELECT components_json, units_json, metadata_json FROM correlation_sample"
    ).fetchone()
    assert row is not None
    import json

    assert json.loads(row[0]) == {"systolic": 121.0, "diastolic": 78.0, "pulse": 64.0}
    assert json.loads(row[1]) == {
        "systolic": "mmHg",
        "diastolic": "mmHg",
        "pulse": "bpm",
    }
    assert json.loads(row[2]) == {"cuff": "omron-x7"}


# --------------------------------------------------------------------------- #
# Workouts
# --------------------------------------------------------------------------- #
def test_upsert_workout_roundtrip_minimal(repo: SQLiteTraceRepository) -> None:
    w = Workout(
        source=Source.GARMIN,
        activity_id="abc-001",
        activity_type="running",
        start_ts=_t(2026, 5, 22, 6, 30),
        duration_s=1800,
    )
    assert repo.upsert_workout([w]) == 1
    out = repo.query_workouts(Source.GARMIN, _t(2026, 5, 22, 0, 0), _t(2026, 5, 23, 0, 0))
    assert len(out) == 1
    assert out[0].activity_id == "abc-001"
    assert out[0].activity_type == "running"
    assert out[0].duration_s == 1800
    assert out[0].end_ts is None
    assert out[0].distance_m is None
    assert out[0].device is None
    assert out[0].raw_summary == {}


def test_upsert_workout_roundtrip_full(repo: SQLiteTraceRepository) -> None:
    device = Device(manufacturer="garmin", product="fenix 7x", software_version="14.50")
    start = _t(2026, 5, 22, 6, 30)
    w = Workout(
        source=Source.GARMIN,
        activity_id="abc-002",
        activity_type="cycling",
        start_ts=start,
        end_ts=start + timedelta(hours=2),
        duration_s=7200,
        distance_m=42_195.0,
        kcal=890.5,
        avg_hr=145.0,
        max_hr=178.0,
        training_effect=3.7,
        training_stress_score=120.0,
        device=device,
        fit_blob_sha256="a" * 64,
        raw_summary={"intensity": "Z3", "splits": [{"i": 1, "pace": 4.5}]},
    )
    repo.upsert_workout([w])
    out = repo.query_workouts(None, _t(2026, 5, 22, 0, 0), _t(2026, 5, 23, 0, 0))
    assert len(out) == 1
    fetched = out[0]
    assert fetched.source == Source.GARMIN
    assert fetched.end_ts == start + timedelta(hours=2)
    assert fetched.distance_m == 42_195.0
    assert fetched.kcal == 890.5
    assert fetched.avg_hr == 145.0
    assert fetched.max_hr == 178.0
    assert fetched.training_effect == 3.7
    assert fetched.training_stress_score == 120.0
    assert fetched.device == device
    assert fetched.fit_blob_sha256 == "a" * 64
    assert fetched.raw_summary == {"intensity": "Z3", "splits": [{"i": 1, "pace": 4.5}]}


def test_upsert_workout_idempotent(repo: SQLiteTraceRepository) -> None:
    w1 = Workout(
        source=Source.GARMIN,
        activity_id="dup-1",
        activity_type="running",
        start_ts=_t(2026, 5, 22, 6, 0),
        duration_s=600,
        kcal=50.0,
    )
    w2 = w1.model_copy(update={"kcal": 75.0})
    repo.upsert_workout([w1])
    repo.upsert_workout([w2])
    out = repo.query_workouts(Source.GARMIN, _t(2026, 5, 22, 0, 0), _t(2026, 5, 23, 0, 0))
    assert len(out) == 1
    assert out[0].kcal == 75.0


# --------------------------------------------------------------------------- #
# last_sample_ts
# --------------------------------------------------------------------------- #
def test_last_sample_ts_returns_max_end_ts(repo: SQLiteTraceRepository) -> None:
    base = _t(2026, 5, 22, 6, 0)
    samples = [
        _qs(start=base + timedelta(minutes=i), value=60.0 + i, metadata={"n": str(i)})
        for i in range(5)
    ]
    repo.upsert_quantity(samples)
    latest = repo.last_sample_ts(Source.GARMIN, MetricCode.HEART_RATE)
    assert latest is not None
    # Latest end_ts is the last sample's start + 1s.
    assert latest == base + timedelta(minutes=4, seconds=1)
    assert latest.tzinfo is UTC


def test_last_sample_ts_returns_none_when_empty(repo: SQLiteTraceRepository) -> None:
    assert repo.last_sample_ts(Source.GARMIN, MetricCode.HEART_RATE) is None


# --------------------------------------------------------------------------- #
# query_quantity filters
# --------------------------------------------------------------------------- #
def test_query_quantity_filters_by_source_none_returns_all_sources(
    repo: SQLiteTraceRepository,
) -> None:
    base = _t(2026, 5, 22, 6, 0)
    repo.upsert_quantity(
        [
            _qs(source=Source.GARMIN, start=base, value=64.0, metadata={"a": "1"}),
            _qs(
                source=Source.APPLE_HEALTH,
                start=base + timedelta(minutes=1),
                value=66.0,
                metadata={"a": "2"},
            ),
            _qs(
                source=Source.WHOOP,
                start=base + timedelta(minutes=2),
                value=68.0,
                metadata={"a": "3"},
            ),
        ]
    )
    out = repo.query_quantity(
        None,
        MetricCode.HEART_RATE,
        base - timedelta(minutes=1),
        base + timedelta(minutes=10),
    )
    assert {s.source for s in out} == {Source.GARMIN, Source.APPLE_HEALTH, Source.WHOOP}
    only_garmin = repo.query_quantity(
        Source.GARMIN,
        MetricCode.HEART_RATE,
        base - timedelta(minutes=1),
        base + timedelta(minutes=10),
    )
    assert {s.source for s in only_garmin} == {Source.GARMIN}


def test_query_quantity_filters_by_time_window(repo: SQLiteTraceRepository) -> None:
    base = _t(2026, 5, 22, 0, 0)
    samples = [
        _qs(start=base + timedelta(hours=h), value=60.0 + h, metadata={"h": str(h)})
        for h in range(24)
    ]
    repo.upsert_quantity(samples)
    window = repo.query_quantity(
        Source.GARMIN,
        MetricCode.HEART_RATE,
        base + timedelta(hours=8),
        base + timedelta(hours=16),
    )
    hours = sorted(s.start_ts.hour for s in window)
    assert hours == list(range(8, 17))


# --------------------------------------------------------------------------- #
# Encryption (v1.0 — not implemented)
# --------------------------------------------------------------------------- #
def test_encryption_v1_raises_not_implemented(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="SQLCipher upgrade lands in v1.1"):
        SQLiteTraceRepository(tmp_path / "enc.db", encrypt=True)


# --------------------------------------------------------------------------- #
# Context manager
# --------------------------------------------------------------------------- #
def test_context_manager_closes_connection(db_path: Path) -> None:
    import sqlite3

    with SQLiteTraceRepository(db_path) as r:
        r.migrate()
        assert r.upsert_quantity([_qs()]) == 1
        conn = r._conn  # type: ignore[attr-defined]
    # After __exit__, the underlying connection should be closed.
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


# --------------------------------------------------------------------------- #
# Performance smoke
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    os.environ.get("CI_SLOW_DISABLE") == "1", reason="perf smoke disabled in slow-CI mode"
)
def test_bulk_upsert_1000_samples_fast(repo: SQLiteTraceRepository) -> None:
    base = _t(2026, 5, 22, 0, 0)
    samples = [
        _qs(start=base + timedelta(seconds=i), value=60.0 + (i % 30), metadata={"i": str(i)})
        for i in range(1000)
    ]
    t0 = time.monotonic()
    n = repo.upsert_quantity(samples)
    elapsed = time.monotonic() - t0
    assert n == 1000
    assert elapsed < 5.0, f"bulk upsert took {elapsed:.2f}s (budget 5s)"
