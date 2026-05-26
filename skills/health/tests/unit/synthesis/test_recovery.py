"""Tests for synthesis/recovery.py — custom recovery composite score."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.samples import QuantitySample
from broomva_health.domain.source import Source
from broomva_health.synthesis.recovery import compute_recovery_score


def _qs(metric: MetricCode, unit: str, value: float, ts: datetime) -> QuantitySample:
    # model_construct bypasses the domain validator chain (test decoupling).
    return QuantitySample.model_construct(
        source=Source.GARMIN,
        metric=metric,
        value=value,
        unit=unit,
        start_ts=ts,
        end_ts=ts + timedelta(minutes=1),
        device=None,
        metadata={},
        ingested_at=ts,
    )


def _series(
    metric: MetricCode,
    unit: str,
    values: list[float],
    start_day: date,
) -> list[QuantitySample]:
    """One sample per day starting at `start_day`."""
    return [
        _qs(metric, unit, v, datetime(start_day.year, start_day.month, start_day.day, 8, 0, tzinfo=UTC) + timedelta(days=i))
        for i, v in enumerate(values)
    ]


def test_empty_inputs_return_none() -> None:
    assert compute_recovery_score([], [], [], on_date=date(2026, 5, 22)) is None


def test_insufficient_baseline_returns_none() -> None:
    """All series too short → no metric has enough baseline → None."""
    on_date = date(2026, 5, 22)
    start = on_date - timedelta(days=5)
    hrv = _series(MetricCode.HRV_OVERNIGHT, "ms", [55.0] * 5, start)
    rhr = _series(MetricCode.RESTING_HEART_RATE, "bpm", [55.0] * 5, start)
    sleep = _series(MetricCode.SLEEP_DURATION, "s", [28800.0] * 5, start)

    assert compute_recovery_score(hrv, rhr, sleep, on_date=on_date) is None


def test_stable_inputs_score_near_50() -> None:
    """When the recent week matches the baseline ≈ exactly, score ≈ 50."""
    on_date = date(2026, 5, 22)
    # 45 days of perfectly flat values — recent week matches baseline.
    # Tiny perturbation so stdev is nonzero (avoids the degenerate path).
    series_start = on_date - timedelta(days=45)

    hrv_vals = [55.0 + (i % 3 - 1) * 0.5 for i in range(45)]  # ±0.5 ms
    rhr_vals = [55.0 + (i % 3 - 1) * 0.5 for i in range(45)]
    sleep_vals = [28800.0 + (i % 3 - 1) * 60 for i in range(45)]

    hrv = _series(MetricCode.HRV_OVERNIGHT, "ms", hrv_vals, series_start)
    rhr = _series(MetricCode.RESTING_HEART_RATE, "bpm", rhr_vals, series_start)
    sleep = _series(MetricCode.SLEEP_DURATION, "s", sleep_vals, series_start)

    score = compute_recovery_score(hrv, rhr, sleep, on_date=on_date)

    assert score is not None
    # Tolerate ±10 around 50 — micro-perturbation can drift slightly.
    assert 40.0 <= score <= 60.0


def test_improvement_above_baseline_scores_higher_than_50() -> None:
    """Recent week: HRV up, RHR down, sleep up → score > 50."""
    on_date = date(2026, 5, 22)
    series_start = on_date - timedelta(days=37)

    # Baseline 30 days: flat moderate values with tiny noise.
    base_hrv = [50.0 + (i % 3 - 1) * 0.5 for i in range(30)]
    base_rhr = [60.0 + (i % 3 - 1) * 0.5 for i in range(30)]
    base_sleep = [27000.0 + (i % 3 - 1) * 60 for i in range(30)]

    # Recent 7 days: clearly better.
    recent_hrv = [70.0] * 7  # +20 ms ≈ multi-sigma above baseline
    recent_rhr = [50.0] * 7  # -10 bpm
    recent_sleep = [32400.0] * 7  # +1.5h

    hrv = _series(MetricCode.HRV_OVERNIGHT, "ms", base_hrv + recent_hrv, series_start)
    rhr = _series(
        MetricCode.RESTING_HEART_RATE, "bpm", base_rhr + recent_rhr, series_start
    )
    sleep = _series(MetricCode.SLEEP_DURATION, "s", base_sleep + recent_sleep, series_start)

    score = compute_recovery_score(hrv, rhr, sleep, on_date=on_date)

    assert score is not None
    assert score > 50.0


def test_decline_below_baseline_scores_lower_than_50() -> None:
    """Recent week: HRV down, RHR up, sleep down → score < 50."""
    on_date = date(2026, 5, 22)
    series_start = on_date - timedelta(days=37)

    base_hrv = [60.0 + (i % 3 - 1) * 0.5 for i in range(30)]
    base_rhr = [55.0 + (i % 3 - 1) * 0.5 for i in range(30)]
    base_sleep = [28800.0 + (i % 3 - 1) * 60 for i in range(30)]

    # Recent: worse.
    recent_hrv = [40.0] * 7
    recent_rhr = [70.0] * 7
    recent_sleep = [21600.0] * 7  # 6h

    hrv = _series(MetricCode.HRV_OVERNIGHT, "ms", base_hrv + recent_hrv, series_start)
    rhr = _series(
        MetricCode.RESTING_HEART_RATE, "bpm", base_rhr + recent_rhr, series_start
    )
    sleep = _series(MetricCode.SLEEP_DURATION, "s", base_sleep + recent_sleep, series_start)

    score = compute_recovery_score(hrv, rhr, sleep, on_date=on_date)

    assert score is not None
    assert score < 50.0


def test_rhr_direction_is_sign_flipped() -> None:
    """RHR alone: lower than baseline → score > 50 (good recovery)."""
    on_date = date(2026, 5, 22)
    series_start = on_date - timedelta(days=37)

    base = [60.0 + (i % 3 - 1) * 0.5 for i in range(30)]
    recent_low_rhr = [50.0] * 7

    rhr = _series(
        MetricCode.RESTING_HEART_RATE, "bpm", base + recent_low_rhr, series_start
    )

    score = compute_recovery_score([], rhr, [], on_date=on_date)

    assert score is not None
    assert score > 50.0


def test_extreme_swing_is_clamped_to_range() -> None:
    """Massive deviation → score clamped to [0, 100], not 200 or -50."""
    on_date = date(2026, 5, 22)
    series_start = on_date - timedelta(days=37)

    # Tiny baseline variation, huge recent value → z-score is enormous.
    base_hrv = [50.0 + (i % 2) * 0.01 for i in range(30)]
    recent_hrv = [500.0] * 7  # absurdly high

    hrv = _series(MetricCode.HRV_OVERNIGHT, "ms", base_hrv + recent_hrv, series_start)

    score = compute_recovery_score(hrv, [], [], on_date=on_date)

    assert score is not None
    assert score == pytest.approx(100.0)


def test_partial_metrics_still_score() -> None:
    """Only HRV available → still produces a score from that one metric."""
    on_date = date(2026, 5, 22)
    series_start = on_date - timedelta(days=37)

    base_hrv = [55.0 + (i % 3 - 1) * 0.5 for i in range(30)]
    recent_hrv = [55.0] * 7

    hrv = _series(MetricCode.HRV_OVERNIGHT, "ms", base_hrv + recent_hrv, series_start)

    score = compute_recovery_score(hrv, [], [], on_date=on_date)

    assert score is not None
    assert 40.0 <= score <= 60.0
