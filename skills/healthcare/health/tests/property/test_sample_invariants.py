"""Hypothesis property tests — domain-layer invariants.

These tests probe the *shape* of the invariant rather than picking a
single example: any datetime, any source, any metric. They catch the
class of bug where a hand-coded test happened to land on the one timezone
the validator agrees with — Hypothesis will find the others.

Conventions:
- `max_examples=50, deadline=None` keeps CI green on slower machines
  while still giving the strategies enough surface to find bugs.
- All datetimes are tz-aware UTC via `st.datetimes(timezones=just(UTC))` —
  the domain layer rejects naive datetimes implicitly by coercing them,
  so we test only the contract Hypothesis can reason about.
- `min_value=-1e6, max_value=1e6` on floats matches realistic sample
  magnitudes (HR <= 300, kcal <= ~5000) without forcing the strategy
  to explore subnormal / overflow regimes that hit Pydantic's float
  validation rather than the invariants under test.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.samples import (
    CategorySample,
    CorrelationSample,
    QuantitySample,
)
from broomva_health.domain.source import Source
from broomva_health.domain.workout import Workout

# --------------------------------------------------------------------------
# Module-level strategy + Hypothesis settings
# --------------------------------------------------------------------------

settings.register_profile("property", max_examples=50, deadline=None)
settings.load_profile("property")

# Tz-aware UTC datetimes only — the domain accepts naive and coerces them,
# but the property under test is *equality of round-trip* which is sharper
# when we start from a value that already has tzinfo.
_dt_utc = st.datetimes(timezones=st.just(UTC))
_source = st.sampled_from(list(Source))
_metric = st.sampled_from(list(MetricCode))
_finite_float = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
)
_short_text = st.text(
    min_size=1, max_size=24, alphabet=st.characters(min_codepoint=33, max_codepoint=126)
)


def _ordered_pair(dt_a: datetime, dt_b: datetime) -> tuple[datetime, datetime]:
    """Return (start, end) with start <= end (swap if needed)."""
    if dt_a <= dt_b:
        return dt_a, dt_b
    return dt_b, dt_a


# --------------------------------------------------------------------------
# QuantitySample
# --------------------------------------------------------------------------


@given(
    src=_source,
    metric=_metric,
    dt_a=_dt_utc,
    dt_b=_dt_utc,
    value=_finite_float,
    unit=_short_text,
)
def test_quantity_sample_roundtrip_via_model_dump(
    src: Source,
    metric: MetricCode,
    dt_a: datetime,
    dt_b: datetime,
    value: float,
    unit: str,
) -> None:
    """Round-trip invariant: model_dump(mode='json') → model_validate restores equality."""
    start, end = _ordered_pair(dt_a, dt_b)
    original = QuantitySample(
        source=src,
        metric=metric,
        start_ts=start,
        end_ts=end,
        value=value,
        unit=unit,
    )
    dumped = original.model_dump(mode="json")
    rebuilt = QuantitySample.model_validate(dumped)
    assert rebuilt == original


@given(dt_a=_dt_utc, dt_b=_dt_utc)
def test_quantity_sample_rejects_end_before_start(dt_a: datetime, dt_b: datetime) -> None:
    """Inverted-interval invariant: end < start always raises ValidationError.

    Constructs a strictly-inverted pair `(later, earlier)` so the validator
    must reject it regardless of which datetimes Hypothesis picks.
    """
    if dt_a == dt_b:
        # Skip the equal-timestamp case — that's a valid zero-length interval.
        return
    earlier, later = _ordered_pair(dt_a, dt_b)
    # Swap so the constructed sample has end strictly preceding start.
    bad_start, bad_end = later, earlier
    assert bad_end < bad_start  # sanity for the test, not the SUT
    with pytest.raises(ValidationError, match=r"end_ts.*precedes"):
        QuantitySample(
            source=Source.GARMIN,
            metric=MetricCode.HEART_RATE,
            start_ts=bad_start,
            end_ts=bad_end,
            value=64.0,
            unit="bpm",
        )


# --------------------------------------------------------------------------
# CategorySample
# --------------------------------------------------------------------------


@given(
    src=_source,
    metric=_metric,
    dt_a=_dt_utc,
    dt_b=_dt_utc,
    category=_short_text,
)
def test_category_sample_roundtrip(
    src: Source,
    metric: MetricCode,
    dt_a: datetime,
    dt_b: datetime,
    category: str,
) -> None:
    """Round-trip invariant for CategorySample under model_dump → model_validate."""
    start, end = _ordered_pair(dt_a, dt_b)
    original = CategorySample(
        source=src,
        metric=metric,
        start_ts=start,
        end_ts=end,
        category=category,
    )
    dumped = original.model_dump(mode="json")
    rebuilt = CategorySample.model_validate(dumped)
    assert rebuilt == original


# --------------------------------------------------------------------------
# CorrelationSample
# --------------------------------------------------------------------------


@given(
    src=_source,
    metric=_metric,
    dt_a=_dt_utc,
    dt_b=_dt_utc,
    components=st.dictionaries(
        keys=_short_text, values=_finite_float, min_size=1, max_size=5
    ),
)
def test_correlation_sample_components_units_match(
    src: Source,
    metric: MetricCode,
    dt_a: datetime,
    dt_b: datetime,
    components: dict[str, float],
) -> None:
    """When unit_by_component has the same keys, construction succeeds; missing → fails."""
    start, end = _ordered_pair(dt_a, dt_b)
    units = dict.fromkeys(components, "unit")

    # Same keys → valid.
    sample = CorrelationSample(
        source=src,
        metric=metric,
        start_ts=start,
        end_ts=end,
        components=components,
        unit_by_component=units,
    )
    assert set(sample.components.keys()) == set(sample.unit_by_component.keys())

    # Drop ONE key from units → must raise.
    missing_key = next(iter(components))
    bad_units = {k: v for k, v in units.items() if k != missing_key}
    with pytest.raises(ValidationError, match=r"without units"):
        CorrelationSample(
            source=src,
            metric=metric,
            start_ts=start,
            end_ts=end,
            components=components,
            unit_by_component=bad_units,
        )


# --------------------------------------------------------------------------
# Workout
# --------------------------------------------------------------------------


@given(
    src=_source,
    activity_id=_short_text,
    activity_type=_short_text,
    dt=_dt_utc,
    duration_s=st.integers(min_value=0, max_value=86_400),
)
def test_workout_duration_non_negative(
    src: Source,
    activity_id: str,
    activity_type: str,
    dt: datetime,
    duration_s: int,
) -> None:
    """Duration invariant: any non-negative integer constructs cleanly.

    Pairs with the per-layer unit test that asserts a *negative* value
    raises — Hypothesis here proves the positive half of the domain.
    """
    workout = Workout(
        source=src,
        activity_id=activity_id,
        activity_type=activity_type,
        start_ts=dt,
        end_ts=dt + timedelta(seconds=duration_s),
        duration_s=duration_s,
    )
    assert workout.duration_s >= 0
    assert workout.start_ts.tzinfo is UTC
