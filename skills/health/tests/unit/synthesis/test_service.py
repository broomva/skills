"""Tests for synthesis/service.py — repo-backed snapshot orchestration.

Uses an inline in-memory fake `TraceRepository`. The fake stores raw
samples and workouts and implements only the read methods the
SynthesisService calls; mutation methods raise NotImplementedError so
any accidental write would fail loudly.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.samples import CategorySample, CorrelationSample, QuantitySample
from broomva_health.domain.source import Source
from broomva_health.domain.workout import Workout
from broomva_health.synthesis.service import SynthesisService, SynthesisSnapshot


class FakeTraceRepository:
    """Minimal in-memory TraceRepository for service tests.

    Stores samples and workouts in lists; query_* methods filter by the
    metric + half-open time window the service supplies.
    """

    def __init__(
        self,
        *,
        quantities: list[QuantitySample] | None = None,
        workouts: list[Workout] | None = None,
    ) -> None:
        self._quantities: list[QuantitySample] = list(quantities or [])
        self._workouts: list[Workout] = list(workouts or [])

    # --- read API used by SynthesisService ---

    def query_quantity(
        self,
        source: Source | None,
        metric: MetricCode,
        start: datetime,
        end: datetime,
    ) -> list[QuantitySample]:
        out = []
        for s in self._quantities:
            if source is not None and s.source != source:
                continue
            if s.metric != metric:
                continue
            if start <= s.start_ts < end:
                out.append(s)
        return out

    def query_workouts(
        self,
        source: Source | None,
        start: datetime,
        end: datetime,
    ) -> list[Workout]:
        out = []
        for w in self._workouts:
            if source is not None and w.source != source:
                continue
            if start <= w.start_ts < end:
                out.append(w)
        return out

    # --- unused but required by the Protocol — raise so accidental use is loud ---

    def upsert_quantity(self, samples: list[QuantitySample]) -> int:
        raise NotImplementedError("fake is read-only")

    def upsert_category(self, samples: list[CategorySample]) -> int:
        raise NotImplementedError("fake is read-only")

    def upsert_correlation(self, samples: list[CorrelationSample]) -> int:
        raise NotImplementedError("fake is read-only")

    def upsert_workout(self, workouts: list[Workout]) -> int:
        raise NotImplementedError("fake is read-only")

    def last_sample_ts(self, source: Source, metric: MetricCode) -> datetime | None:
        return None

    def migrate(self) -> int:
        return 0

    def close(self) -> None:
        return None


def _qs(
    metric: MetricCode, unit: str, value: float, ts: datetime, end_delta: timedelta
) -> QuantitySample:
    # model_construct bypasses the domain validator chain (test decoupling).
    return QuantitySample.model_construct(
        source=Source.GARMIN,
        metric=metric,
        value=value,
        unit=unit,
        start_ts=ts,
        end_ts=ts + end_delta,
        device=None,
        metadata={},
        ingested_at=ts,
    )


def _hrv(value: float, ts: datetime) -> QuantitySample:
    return _qs(MetricCode.HRV_OVERNIGHT, "ms", value, ts, timedelta(hours=8))


def _rhr(value: float, ts: datetime) -> QuantitySample:
    return _qs(MetricCode.RESTING_HEART_RATE, "bpm", value, ts, timedelta(minutes=1))


def _sleep(value: float, ts: datetime) -> QuantitySample:
    return _qs(MetricCode.SLEEP_DURATION, "s", value, ts, timedelta(seconds=int(value)))


def _vo2(value: float, ts: datetime) -> QuantitySample:
    return _qs(MetricCode.VO2_MAX, "ml/kg/min", value, ts, timedelta(minutes=1))


def _workout(day: date, tss: float, idx: int = 0) -> Workout:
    start = datetime(day.year, day.month, day.day, 12, 0, 0, tzinfo=UTC)
    return Workout.model_construct(
        source=Source.GARMIN,
        activity_id=f"wko-{day.isoformat()}-{idx}",
        activity_type="cycling",
        start_ts=start,
        end_ts=start + timedelta(hours=1),
        duration_s=3600,
        distance_m=None,
        kcal=None,
        avg_hr=None,
        max_hr=None,
        training_effect=None,
        training_stress_score=tss,
        device=None,
        fit_blob_sha256=None,
        raw_summary={},
        ingested_at=start,
    )


def test_snapshot_empty_repo_returns_default_snapshot() -> None:
    """No data → snapshot with sensible defaults, not an exception."""
    repo = FakeTraceRepository()
    service = SynthesisService(repo)

    snap = service.snapshot(date(2026, 5, 22))

    assert isinstance(snap, SynthesisSnapshot)
    assert snap.date == date(2026, 5, 22)
    assert snap.hrv_cv_30d is None
    assert snap.ctl == 0.0
    assert snap.atl == 0.0
    assert snap.tsb == 0.0
    assert snap.vo2max_arc == {}
    assert snap.recovery_score is None


def test_snapshot_populates_all_fields() -> None:
    """Full repo: hrv-cv, training load, vo2 arc, recovery all populated."""
    on_date = date(2026, 5, 22)
    series_start = on_date - timedelta(days=40)

    # 40 days of HRV: enough for HRV-CV (30d window) AND recovery (baseline+recent).
    hrv = [
        _hrv(55.0 + (i % 3 - 1) * 0.5, datetime(series_start.year, series_start.month, series_start.day, 23, 0, tzinfo=UTC) + timedelta(days=i))
        for i in range(40)
    ]
    rhr = [
        _rhr(55.0 + (i % 3 - 1) * 0.3, datetime(series_start.year, series_start.month, series_start.day, 6, 0, tzinfo=UTC) + timedelta(days=i))
        for i in range(40)
    ]
    sleep = [
        _sleep(28800.0 + (i % 3 - 1) * 60, datetime(series_start.year, series_start.month, series_start.day, 0, 30, tzinfo=UTC) + timedelta(days=i))
        for i in range(40)
    ]

    # 4 VO2max samples across two quarters.
    vo2 = [
        _vo2(45.0, datetime(2026, 1, 15, tzinfo=UTC)),
        _vo2(47.0, datetime(2026, 2, 20, tzinfo=UTC)),
        _vo2(48.0, datetime(2026, 4, 5, tzinfo=UTC)),
        _vo2(50.0, datetime(2026, 5, 1, tzinfo=UTC)),
    ]

    # 7 days of training right before on_date.
    workouts = [
        _workout(on_date - timedelta(days=10 - i), 100.0, idx=i) for i in range(7)
    ]

    repo = FakeTraceRepository(quantities=hrv + rhr + sleep + vo2, workouts=workouts)
    service = SynthesisService(repo)

    snap = service.snapshot(on_date)

    assert snap.date == on_date
    assert snap.hrv_cv_30d is not None
    assert snap.hrv_cv_30d > 0
    assert snap.hrv_cv_30d < 0.1
    assert snap.ctl > 0
    assert snap.atl > 0
    assert snap.tsb == pytest.approx(snap.ctl - snap.atl)
    assert snap.vo2max_arc == {
        "2026-Q1": pytest.approx(46.0),
        "2026-Q2": pytest.approx(49.0),
    }
    assert snap.recovery_score is not None
    assert 0.0 <= snap.recovery_score <= 100.0


def test_snapshot_only_hrv_data() -> None:
    """Only HRV in the repo: CV populated, training load=0, vo2_arc={}."""
    on_date = date(2026, 5, 22)
    start = on_date - timedelta(days=30)
    hrv = [
        _hrv(55.0 + (i % 3 - 1) * 0.5, datetime(start.year, start.month, start.day, 23, 0, tzinfo=UTC) + timedelta(days=i))
        for i in range(30)
    ]

    repo = FakeTraceRepository(quantities=hrv)
    service = SynthesisService(repo)

    snap = service.snapshot(on_date)

    assert snap.hrv_cv_30d is not None
    assert snap.ctl == 0.0
    assert snap.atl == 0.0
    assert snap.vo2max_arc == {}


def test_synthesis_snapshot_is_frozen() -> None:
    """SynthesisSnapshot is an immutable value object."""
    snap = SynthesisSnapshot(date=date(2026, 5, 22))

    with pytest.raises(Exception):  # noqa: B017 — pydantic raises ValidationError on frozen mutation
        snap.ctl = 99.9  # type: ignore[misc]


def test_synthesis_snapshot_round_trips_via_dict() -> None:
    """Serialization → dict → reconstruction preserves all fields."""
    snap = SynthesisSnapshot(
        date=date(2026, 5, 22),
        hrv_cv_30d=0.047,
        ctl=85.5,
        atl=92.1,
        tsb=-6.6,
        vo2max_arc={"2026-Q1": 47.3, "2026-Q2": 48.9},
        recovery_score=42.0,
    )

    again = SynthesisSnapshot.model_validate(snap.model_dump())

    assert again == snap


def test_service_with_protocol_runtime_check() -> None:
    """Fake repo satisfies the TraceRepository Protocol at runtime."""
    from broomva_health.ports.repository import TraceRepository

    repo = FakeTraceRepository()
    # Protocol is @runtime_checkable; isinstance() should succeed.
    assert isinstance(repo, TraceRepository)
