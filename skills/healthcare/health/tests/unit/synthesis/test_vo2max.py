"""Tests for synthesis/vo2max.py — quarterly/monthly/yearly arc bucketing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.samples import QuantitySample
from broomva_health.domain.source import Source
from broomva_health.synthesis.vo2max import compute_vo2max_arc


def _vo2(value: float, ts: datetime) -> QuantitySample:
    # model_construct bypasses the domain validator chain (test decoupling).
    return QuantitySample.model_construct(
        source=Source.GARMIN,
        metric=MetricCode.VO2_MAX,
        value=value,
        unit="ml/kg/min",
        start_ts=ts,
        end_ts=ts + timedelta(minutes=1),
        device=None,
        metadata={},
        ingested_at=ts,
    )


def test_empty_input_returns_empty_dict() -> None:
    assert compute_vo2max_arc([]) == {}


def test_four_samples_across_two_quarters_quarter_bucket() -> None:
    """4 samples → 2 quarter buckets with correct means."""
    samples = [
        _vo2(45.0, datetime(2026, 1, 15, tzinfo=UTC)),  # Q1
        _vo2(47.0, datetime(2026, 2, 20, tzinfo=UTC)),  # Q1
        _vo2(48.0, datetime(2026, 4, 5, tzinfo=UTC)),  # Q2
        _vo2(50.0, datetime(2026, 5, 22, tzinfo=UTC)),  # Q2
    ]

    arc = compute_vo2max_arc(samples, bucket="quarter")

    assert arc == {
        "2026-Q1": pytest.approx(46.0),
        "2026-Q2": pytest.approx(49.0),
    }


def test_all_four_quarters_bucket_correctly() -> None:
    samples = [
        _vo2(40.0, datetime(2026, 1, 15, tzinfo=UTC)),  # Q1
        _vo2(42.0, datetime(2026, 3, 31, tzinfo=UTC)),  # Q1 (boundary)
        _vo2(44.0, datetime(2026, 4, 1, tzinfo=UTC)),  # Q2 (boundary)
        _vo2(46.0, datetime(2026, 7, 15, tzinfo=UTC)),  # Q3
        _vo2(48.0, datetime(2026, 10, 1, tzinfo=UTC)),  # Q4
    ]

    arc = compute_vo2max_arc(samples, bucket="quarter")

    assert list(arc.keys()) == ["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"]
    assert arc["2026-Q1"] == pytest.approx(41.0)
    assert arc["2026-Q2"] == pytest.approx(44.0)
    assert arc["2026-Q3"] == pytest.approx(46.0)
    assert arc["2026-Q4"] == pytest.approx(48.0)


def test_month_bucket() -> None:
    samples = [
        _vo2(45.0, datetime(2026, 1, 1, tzinfo=UTC)),
        _vo2(47.0, datetime(2026, 1, 31, tzinfo=UTC)),
        _vo2(48.0, datetime(2026, 2, 15, tzinfo=UTC)),
    ]

    arc = compute_vo2max_arc(samples, bucket="month")

    assert arc == {"2026-01": pytest.approx(46.0), "2026-02": pytest.approx(48.0)}


def test_year_bucket() -> None:
    samples = [
        _vo2(44.0, datetime(2025, 6, 1, tzinfo=UTC)),
        _vo2(46.0, datetime(2025, 12, 1, tzinfo=UTC)),
        _vo2(50.0, datetime(2026, 6, 1, tzinfo=UTC)),
    ]

    arc = compute_vo2max_arc(samples, bucket="year")

    assert arc == {"2025": pytest.approx(45.0), "2026": pytest.approx(50.0)}


def test_quarter_keys_are_chronologically_sorted_across_years() -> None:
    """Cross-year sort: 2025-Q4 must come before 2026-Q1."""
    samples = [
        _vo2(50.0, datetime(2026, 1, 15, tzinfo=UTC)),  # 2026-Q1
        _vo2(48.0, datetime(2025, 11, 10, tzinfo=UTC)),  # 2025-Q4
        _vo2(46.0, datetime(2025, 4, 20, tzinfo=UTC)),  # 2025-Q2
    ]

    arc = compute_vo2max_arc(samples, bucket="quarter")

    assert list(arc.keys()) == ["2025-Q2", "2025-Q4", "2026-Q1"]


def test_single_sample_single_bucket() -> None:
    samples = [_vo2(47.5, datetime(2026, 5, 22, tzinfo=UTC))]

    arc = compute_vo2max_arc(samples, bucket="quarter")

    assert arc == {"2026-Q2": pytest.approx(47.5)}


def test_no_zero_fill_for_empty_buckets() -> None:
    """Buckets without samples are absent from the result — not filled with 0."""
    samples = [
        _vo2(45.0, datetime(2026, 1, 15, tzinfo=UTC)),  # Q1
        _vo2(50.0, datetime(2026, 10, 1, tzinfo=UTC)),  # Q4
    ]

    arc = compute_vo2max_arc(samples, bucket="quarter")

    # Q2 and Q3 are absent — downstream consumers must opt in to gap-fill.
    assert set(arc.keys()) == {"2026-Q1", "2026-Q4"}
