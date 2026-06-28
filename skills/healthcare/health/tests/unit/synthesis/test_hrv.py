"""Tests for synthesis/hrv.py — HRV coefficient-of-variation computation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.samples import QuantitySample
from broomva_health.domain.source import Source
from broomva_health.synthesis.hrv import compute_hrv_cv


def _make_sample(value: float, day: datetime) -> QuantitySample:
    # Use model_construct to bypass the domain validator chain — the synthesis
    # layer only reads fields, never re-validates, so construct is safe here
    # and decouples these tests from in-flight domain-layer fixes.
    return QuantitySample.model_construct(
        source=Source.GARMIN,
        metric=MetricCode.HRV_OVERNIGHT,
        value=value,
        unit="ms",
        start_ts=day,
        end_ts=day + timedelta(hours=8),
        device=None,
        metadata={},
        ingested_at=day,
    )


def _series(values: list[float], anchor: datetime) -> list[QuantitySample]:
    """One sample per day, ending at `anchor`, walking backwards."""
    return [
        _make_sample(v, anchor - timedelta(days=len(values) - 1 - i))
        for i, v in enumerate(values)
    ]


def test_stable_series_yields_low_cv() -> None:
    """30 stable nights (≈55 ms ± 1) → CV well under 5%."""
    anchor = datetime(2026, 5, 22, 23, 0, 0, tzinfo=UTC)
    # Stable values: alternate 54/55/56 with tiny variation.
    values = [54.0, 55.0, 56.0, 55.0, 54.0, 55.0, 56.0] * 5  # 35 → use 30
    samples = _series(values[:30], anchor)

    cv = compute_hrv_cv(samples, window_days=30)

    assert cv is not None
    assert 0 < cv < 0.05, f"expected stable CV < 0.05, got {cv}"


def test_wildly_varying_series_yields_high_cv() -> None:
    """30 wildly oscillating nights (20-90 ms) → CV ≫ stable."""
    anchor = datetime(2026, 5, 22, 23, 0, 0, tzinfo=UTC)
    # Big swings.
    values = [20.0, 90.0, 25.0, 85.0, 30.0, 80.0] * 5  # 30 samples
    samples = _series(values, anchor)

    cv = compute_hrv_cv(samples, window_days=30)

    assert cv is not None
    assert cv > 0.2, f"expected swingy CV > 0.2, got {cv}"


def test_high_cv_is_greater_than_low_cv() -> None:
    """Sanity: same length, more variation → larger CV."""
    anchor = datetime(2026, 5, 22, 23, 0, 0, tzinfo=UTC)
    stable = _series([55.0] * 15 + [56.0] * 15, anchor)
    swingy = _series([20.0, 90.0] * 15, anchor)

    cv_stable = compute_hrv_cv(stable, window_days=30)
    cv_swingy = compute_hrv_cv(swingy, window_days=30)

    assert cv_stable is not None
    assert cv_swingy is not None
    assert cv_swingy > cv_stable * 5


def test_insufficient_samples_returns_none() -> None:
    """< 7 samples in window → None, not a noisy estimate."""
    anchor = datetime(2026, 5, 22, 23, 0, 0, tzinfo=UTC)
    samples = _series([55.0, 56.0, 54.0, 55.0, 53.0, 57.0], anchor)  # 6 < 7

    assert compute_hrv_cv(samples, window_days=30) is None


def test_empty_input_returns_none() -> None:
    assert compute_hrv_cv([], window_days=30) is None


def test_zero_mean_returns_none() -> None:
    """A series of zeros has undefined CV → must return None, not raise."""
    anchor = datetime(2026, 5, 22, 23, 0, 0, tzinfo=UTC)
    samples = _series([0.0] * 10, anchor)

    assert compute_hrv_cv(samples, window_days=30) is None


def test_window_anchors_to_latest_sample_not_wallclock() -> None:
    """Old samples beyond the window are excluded relative to max(end_ts)."""
    anchor = datetime(2026, 5, 22, 23, 0, 0, tzinfo=UTC)
    # 30 recent samples (in-window) + 10 ancient (out-of-window).
    recent = _series([55.0] * 30, anchor)
    ancient = _series([10.0] * 10, anchor - timedelta(days=100))

    cv_recent_only = compute_hrv_cv(recent, window_days=30)
    cv_with_ancient = compute_hrv_cv(recent + ancient, window_days=30)

    # The ancient samples must NOT influence the CV — anchor is max(end_ts)
    # and the cutoff is anchor - 30d.
    assert cv_recent_only == pytest.approx(cv_with_ancient)


def test_order_does_not_matter() -> None:
    """Function sorts internally; input order is irrelevant."""
    anchor = datetime(2026, 5, 22, 23, 0, 0, tzinfo=UTC)
    samples = _series([50.0, 55.0, 60.0, 53.0, 57.0, 52.0, 58.0, 54.0, 56.0, 51.0], anchor)

    cv_forward = compute_hrv_cv(samples, window_days=30)
    cv_reversed = compute_hrv_cv(list(reversed(samples)), window_days=30)

    assert cv_forward == pytest.approx(cv_reversed)
