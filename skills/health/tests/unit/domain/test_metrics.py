"""Tests for domain/metrics.py — every metric must have a canonical unit."""

from __future__ import annotations

import pytest

from broomva_health.domain.metrics import METRIC_UNITS, MetricCode, canonical_unit


@pytest.mark.parametrize("metric", list(MetricCode))
def test_every_metric_has_a_canonical_unit(metric: MetricCode) -> None:
    assert metric in METRIC_UNITS, f"Missing unit for {metric.value}"
    assert isinstance(METRIC_UNITS[metric], str)


def test_canonical_unit_helper() -> None:
    assert canonical_unit(MetricCode.HEART_RATE) == "bpm"
    assert canonical_unit(MetricCode.WEIGHT_KG) == "kg"


def test_metric_string_values_are_snake_case() -> None:
    for metric in MetricCode:
        assert metric.value == metric.value.lower()
        assert " " not in metric.value
