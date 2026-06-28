"""Recovery composite score — compute-our-own, don't trust vendor scores.

**Why a custom recovery score?**

Per the validation-evidence rationale, vendor recovery scores (WHOOP
Recovery %, Garmin Body Battery, Oura Readiness, Garmin Training
Readiness) are black-box composites with undisclosed weights and have
been shown to drift, change methodology between firmware versions, and
correlate weakly across vendors for the same individual on the same
day. They are stored AS-IS in the trace layer for reference but the
synthesis layer computes a transparent alternative.

**The composite:**

For a 7-day window ending on `on_date`, compute the *daily averages* of:
- Overnight HRV (higher = better)
- Resting heart rate (lower = better → sign-flipped)
- Sleep duration (longer = better)

Then for each metric:
1. Compute the **baseline mean and stdev** over the *prior* 30-day
   window (i.e. days `[on_date - 37, on_date - 7)`).
2. Convert the recent 7-day average to a z-score against that baseline.
3. Flip the sign for RHR (lower RHR = better recovery).
4. Average the three z-scores into a composite z.
5. Map z to a 0-100 score: `score = clamp(50 + 10 × z, 0, 100)`. So
   z=0 (right at baseline) = 50, z=+1σ better than baseline = 60,
   z=-2σ worse = 30.

**Why this design:**

- Per-individual baseline — no population-normative assumption.
- Sign-aware composition — RHR direction is opposite HRV/sleep.
- Transparent and auditable — every step is in this docstring.
- Stdlib only — `statistics.mean` and `statistics.stdev`.
- Insufficient-data → None, never silent zeros.

**What we deliberately do NOT include:**

- Subjective wellness (would require user input — different concern).
- Training load (separate output via CTL/ATL/TSB synthesis).
- Sleep stages (HealthKit-only, not universal across sources).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from statistics import mean, stdev

from broomva_health.domain.samples import QuantitySample

__all__ = ["compute_recovery_score"]

_RECENT_DAYS = 7
"""Trailing window for the 'current state' estimate."""

_BASELINE_DAYS = 30
"""Length of the prior window used as the per-individual baseline.

The baseline window is `[on_date - _RECENT_DAYS - _BASELINE_DAYS, on_date - _RECENT_DAYS)`
— it does NOT overlap the recent window, so the z-score compares the
recent state against the *prior* baseline, not against itself.
"""

_MIN_RECENT = 3
"""Minimum samples in the recent window for a metric to contribute."""

_MIN_BASELINE = 7
"""Minimum samples in the baseline window for a metric to contribute.

7 ≪ 30 but recognizes that real-world wearable data has gaps. If we
have at least one good week of baseline we can z-score meaningfully.
"""


def _day_range(start: date, end_exclusive: date) -> tuple[datetime, datetime]:
    """Half-open UTC datetime range for a date range."""
    return (
        datetime(start.year, start.month, start.day, tzinfo=UTC),
        datetime(end_exclusive.year, end_exclusive.month, end_exclusive.day, tzinfo=UTC),
    )


def _window_mean(
    samples: list[QuantitySample], lo: datetime, hi: datetime
) -> float | None:
    """Mean of sample values whose start_ts is in `[lo, hi)`. None if empty."""
    vals = [s.value for s in samples if lo <= s.start_ts < hi]
    if not vals:
        return None
    return mean(vals)


def _z_score(
    samples: list[QuantitySample],
    *,
    recent_lo: datetime,
    recent_hi: datetime,
    base_lo: datetime,
    base_hi: datetime,
) -> float | None:
    """Z-score of the recent-window mean against the baseline distribution.

    Returns None if either window has insufficient samples or the
    baseline stdev is 0 (degenerate — no variation to score against).
    """
    recent_vals = [s.value for s in samples if recent_lo <= s.start_ts < recent_hi]
    base_vals = [s.value for s in samples if base_lo <= s.start_ts < base_hi]

    if len(recent_vals) < _MIN_RECENT or len(base_vals) < _MIN_BASELINE:
        return None

    base_mean = mean(base_vals)
    base_sd = stdev(base_vals)
    if base_sd == 0:
        return None

    return (mean(recent_vals) - base_mean) / base_sd


def compute_recovery_score(
    hrv_samples: list[QuantitySample],
    rhr_samples: list[QuantitySample],
    sleep_duration_samples: list[QuantitySample],
    *,
    on_date: date,
) -> float | None:
    """Composite recovery score (0-100, 50 = baseline).

    Args:
        hrv_samples: Overnight HRV samples (HRV_OVERNIGHT). Higher = better.
        rhr_samples: Resting heart rate samples. Lower = better (sign-flipped).
        sleep_duration_samples: Sleep duration samples. Longer = better.
        on_date: The date to score (exclusive upper bound of recent window).

    Returns:
        A composite score in [0, 100], or None if NONE of the three
        metrics had enough data to z-score against its baseline.

    Notes:
        - If only 1 or 2 of the 3 metrics have enough data, the composite
          is averaged over whatever is available (partial credit). Only
          all-three-missing returns None.
        - Score is clamped to [0, 100] — extreme outliers cap rather than
          producing absurd scores.
    """
    # Define the four window edges.
    recent_lo_d = on_date - timedelta(days=_RECENT_DAYS)
    recent_hi_d = on_date
    base_hi_d = recent_lo_d
    base_lo_d = base_hi_d - timedelta(days=_BASELINE_DAYS)

    recent_lo, recent_hi = _day_range(recent_lo_d, recent_hi_d)
    base_lo, base_hi = _day_range(base_lo_d, base_hi_d)

    z_hrv = _z_score(
        hrv_samples,
        recent_lo=recent_lo,
        recent_hi=recent_hi,
        base_lo=base_lo,
        base_hi=base_hi,
    )
    z_rhr_raw = _z_score(
        rhr_samples,
        recent_lo=recent_lo,
        recent_hi=recent_hi,
        base_lo=base_lo,
        base_hi=base_hi,
    )
    # Lower RHR = better recovery → flip sign.
    z_rhr = -z_rhr_raw if z_rhr_raw is not None else None

    z_sleep = _z_score(
        sleep_duration_samples,
        recent_lo=recent_lo,
        recent_hi=recent_hi,
        base_lo=base_lo,
        base_hi=base_hi,
    )

    contributions = [z for z in (z_hrv, z_rhr, z_sleep) if z is not None]
    if not contributions:
        return None

    composite_z = mean(contributions)

    # z=0 → 50, ±1σ → ±10, clamped.
    raw_score = 50.0 + 10.0 * composite_z
    return max(0.0, min(100.0, raw_score))
