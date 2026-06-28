"""Tests for the `health synthesis` CLI wiring.

`synthesis_by_source` is exercised against a real in-memory SQLite repo seeded
with HRV / RHR / sleep / VO2max samples + TSS-bearing workouts, so the test
covers the actual synthesis math wiring (not a mock). Also verifies that
CTL/ATL/TSB *do* populate when workouts carry TSS — the real-data 0.0 is a
Garmin-summary data gap, not a wiring bug.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import pytest
import typer

from broomva_health.adapters.repositories.sqlite import SQLiteTraceRepository
from broomva_health.cli.synthesis import _parse_on, synthesis_by_source
from broomva_health.domain.device import Device
from broomva_health.domain.metrics import MetricCode, canonical_unit
from broomva_health.domain.samples import QuantitySample
from broomva_health.domain.source import Source
from broomva_health.domain.workout import Workout

_GARMIN = Device(manufacturer="garmin")
ON = date(2026, 6, 12)


class _FakeContainer:
    """Minimal container surface used by synthesis_by_source."""

    def __init__(self, repo: SQLiteTraceRepository) -> None:
        self.sources = {Source.GARMIN: object()}
        self._repo = repo

    def repository_for(self, _src: Source) -> SQLiteTraceRepository:
        return self._repo


def _q(metric: MetricCode, value: float, day: date) -> QuantitySample:
    ts = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return QuantitySample(
        source=Source.GARMIN,
        metric=metric,
        value=value,
        unit=canonical_unit(metric),
        start_ts=ts,
        end_ts=ts,
        device=_GARMIN,
    )


def _seeded_repo() -> SQLiteTraceRepository:
    repo = SQLiteTraceRepository(Path(":memory:"))
    repo.migrate()
    quantities: list[QuantitySample] = []
    # 28 daily HRV / RHR / sleep values with variation → hrv_cv + recovery compute.
    for i in range(28):
        d = ON - timedelta(days=i)
        quantities.append(_q(MetricCode.HRV_OVERNIGHT, 60.0 + (i % 5), d))
        quantities.append(_q(MetricCode.RESTING_HEART_RATE, 50.0 + (i % 3), d))
        quantities.append(_q(MetricCode.SLEEP_DURATION, 25200.0 + (i % 4) * 600, d))
    # VO2max across two quarters → arc buckets.
    quantities.append(_q(MetricCode.VO2_MAX, 48.0, date(2026, 2, 1)))
    quantities.append(_q(MetricCode.VO2_MAX, 50.0, date(2026, 5, 1)))
    repo.upsert_quantity(quantities)
    # Workouts WITH TSS → CTL/ATL/TSB populate (the real Garmin summary lacks TSS).
    workouts = [
        Workout(
            source=Source.GARMIN,
            activity_id=f"w{i}",
            activity_type="running",
            start_ts=datetime(ON.year, ON.month, ON.day, tzinfo=UTC) - timedelta(days=i * 2),
            duration_s=3600,
            training_stress_score=80.0,
        )
        for i in range(20)
    ]
    repo.upsert_workout(workouts)
    return repo


def test_synthesis_by_source_computes_over_repo() -> None:
    repo = _seeded_repo()
    try:
        out = synthesis_by_source(_FakeContainer(repo), ON)
    finally:
        repo.close()
    assert set(out) == {"garmin"}
    snap = out["garmin"]
    assert snap["date"] == "2026-06-12"
    assert snap["hrv_cv_30d"] is not None
    assert snap["hrv_cv_30d"] > 0
    # CTL/ATL/TSB populate because the seeded workouts carry TSS.
    assert snap["ctl"] > 0
    assert snap["atl"] > 0
    assert snap["tsb"] == pytest.approx(snap["ctl"] - snap["atl"], abs=1e-6)
    # VO2max arc bucketed by quarter.
    assert snap["vo2max_arc"]["2026-Q1"] == 48.0
    assert snap["vo2max_arc"]["2026-Q2"] == 50.0
    assert snap["recovery_score"] is not None


def test_synthesis_source_error_isolated() -> None:
    """A source whose repo won't open yields an error entry, not a crash."""

    class _BoomContainer:
        sources: ClassVar = {Source.GARMIN: object()}

        def repository_for(self, _src: Source) -> SQLiteTraceRepository:
            raise RuntimeError("db locked")

    out = synthesis_by_source(_BoomContainer(), ON)
    assert out["garmin"] == {"error": "db locked"}


def test_parse_on_defaults_to_local_today() -> None:
    assert _parse_on(None, local_today=ON) == ON


def test_parse_on_explicit_iso() -> None:
    assert _parse_on("2025-08-12", local_today=ON) == date(2025, 8, 12)


def test_parse_on_rejects_garbage() -> None:
    with pytest.raises(typer.BadParameter, match="must be ISO"):
        _parse_on("not-a-date", local_today=ON)
