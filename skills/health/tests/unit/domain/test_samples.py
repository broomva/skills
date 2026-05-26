"""Tests for domain/samples.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.samples import (
    CategorySample,
    CorrelationSample,
    QuantitySample,
)
from broomva_health.domain.source import Source

T0 = datetime(2026, 5, 22, 8, 0, tzinfo=UTC)
T1 = T0 + timedelta(minutes=1)


def test_quantity_sample_minimal() -> None:
    s = QuantitySample(
        source=Source.GARMIN,
        metric=MetricCode.HEART_RATE,
        start_ts=T0,
        end_ts=T1,
        value=64.0,
        unit="bpm",
    )
    assert s.value == 64.0
    assert s.unit == "bpm"
    assert s.start_ts.tzinfo is UTC


def test_quantity_sample_is_frozen() -> None:
    s = QuantitySample(
        source=Source.GARMIN,
        metric=MetricCode.HEART_RATE,
        start_ts=T0,
        end_ts=T1,
        value=64.0,
        unit="bpm",
    )
    with pytest.raises(ValidationError):
        s.value = 70.0  # type: ignore[misc]


def test_quantity_sample_rejects_inverted_interval() -> None:
    with pytest.raises(ValidationError, match="end_ts.*precedes"):
        QuantitySample(
            source=Source.GARMIN,
            metric=MetricCode.HEART_RATE,
            start_ts=T1,
            end_ts=T0,
            value=64.0,
            unit="bpm",
        )


def test_quantity_sample_normalizes_naive_to_utc() -> None:
    naive = datetime(2026, 5, 22, 8, 0)
    s = QuantitySample(
        source=Source.GARMIN,
        metric=MetricCode.HEART_RATE,
        start_ts=naive,
        end_ts=naive,
        value=64.0,
        unit="bpm",
    )
    assert s.start_ts.tzinfo is UTC


def test_category_sample_basic() -> None:
    s = CategorySample(
        source=Source.GARMIN,
        metric=MetricCode.SLEEP_STAGE,
        start_ts=T0,
        end_ts=T1,
        category="deep",
    )
    assert s.category == "deep"


def test_correlation_sample_basic() -> None:
    s = CorrelationSample(
        source=Source.MANUAL,
        metric=MetricCode.BLOOD_PRESSURE,
        start_ts=T0,
        end_ts=T1,
        components={"systolic": 121, "diastolic": 78, "pulse": 64},
        unit_by_component={"systolic": "mmHg", "diastolic": "mmHg", "pulse": "bpm"},
    )
    assert s.components["systolic"] == 121


def test_correlation_sample_rejects_missing_unit() -> None:
    with pytest.raises(ValidationError, match="without units"):
        CorrelationSample(
            source=Source.MANUAL,
            metric=MetricCode.BLOOD_PRESSURE,
            start_ts=T0,
            end_ts=T1,
            components={"systolic": 121, "diastolic": 78},
            unit_by_component={"systolic": "mmHg"},
        )


def test_quantity_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        QuantitySample(
            source=Source.GARMIN,
            metric=MetricCode.HEART_RATE,
            start_ts=T0,
            end_ts=T1,
            value=64.0,
            unit="bpm",
            unknown_field="oops",  # type: ignore[call-arg]
        )
