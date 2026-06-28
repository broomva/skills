"""Sample types — shaped on Apple HealthKit's `HKSample` hierarchy.

Three top-level shapes:

- `QuantitySample` — single numeric value over a time interval (heart rate,
  steps, weight, VO2max). Equivalent to `HKQuantitySample`.
- `CategorySample` — categorical state over an interval (sleep stage,
  menstrual flow, cycle phase). Equivalent to `HKCategorySample`.
- `CorrelationSample` — composite measurement where multiple values must
  travel together (blood pressure: systolic + diastolic + pulse).
  Equivalent to `HKCorrelationSample`.

All samples carry `source` + optional device metadata so the trace layer
preserves provenance — reconciliation (which source wins for a given
metric/time-window) is a projection above the trace layer, never a
column inside it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from broomva_health.domain.device import Device
from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.source import Source
from broomva_health.domain.time import ensure_utc, utc_now

__all__ = ["CategorySample", "CorrelationSample", "QuantitySample"]


def _coerce_utc(value: datetime) -> datetime:
    """Field validator helper — every datetime field goes through this."""
    return ensure_utc(value)


class _SampleBase(BaseModel):
    """Common base for all sample types. Frozen and immutable."""

    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=False,
        extra="forbid",
    )

    source: Source = Field(..., description="Which integration produced this sample")
    device: Device | None = Field(default=None, description="Optional device that produced it")
    start_ts: datetime = Field(..., description="UTC start of the sample interval")
    end_ts: datetime = Field(..., description="UTC end of the sample interval")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Source-specific extras")
    ingested_at: datetime = Field(default_factory=utc_now, description="When the trace was written")

    _normalize_start = field_validator("start_ts", mode="after")(_coerce_utc)
    _normalize_end = field_validator("end_ts", mode="after")(_coerce_utc)
    _normalize_ingested = field_validator("ingested_at", mode="after")(_coerce_utc)

    @model_validator(mode="after")
    def _interval_ordered(self) -> _SampleBase:
        if self.end_ts < self.start_ts:
            raise ValueError(
                f"end_ts ({self.end_ts.isoformat()}) precedes start_ts ({self.start_ts.isoformat()})"
            )
        return self


class QuantitySample(_SampleBase):
    """Scalar measurement over an interval.

    Examples:
        QuantitySample(source=GARMIN, metric=HEART_RATE, value=64.0,
                       unit="bpm", start_ts=..., end_ts=...)
    """

    metric: MetricCode = Field(..., description="What is being measured")
    value: float = Field(..., description="The measured value in `unit`")
    unit: str = Field(..., description="Unit string; must match the canonical unit for `metric`")


class CategorySample(_SampleBase):
    """Categorical state over an interval (sleep stage, menstrual flow)."""

    metric: MetricCode = Field(..., description="What category dimension")
    category: str = Field(..., description="The category value, e.g. 'deep', 'rem', 'awake'")


class CorrelationSample(_SampleBase):
    """Composite measurement where multiple values must travel together.

    Examples:
        BP = CorrelationSample(metric=BLOOD_PRESSURE,
                               components={"systolic": 121, "diastolic": 78, "pulse": 64},
                               unit_by_component={"systolic": "mmHg", "diastolic": "mmHg", "pulse": "bpm"})
    """

    metric: MetricCode = Field(..., description="The composite metric label")
    components: dict[str, float] = Field(..., description="Named component values")
    unit_by_component: dict[str, str] = Field(..., description="Unit per component")

    @model_validator(mode="after")
    def _components_have_units(self) -> CorrelationSample:
        missing = set(self.components.keys()) - set(self.unit_by_component.keys())
        if missing:
            raise ValueError(f"Components without units: {sorted(missing)}")
        return self
