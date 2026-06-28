"""Coggan training-load synthesis — CTL, ATL, TSB.

**Why CTL/ATL/TSB?**

The Performance Management Chart, popularized by Andy Coggan and
TrainingPeaks, is the canonical way to model an endurance athlete's
training adaptation. Three numbers, derived from daily Training Stress
Score (TSS):

- **CTL** ("Chronic Training Load") — 42-day exponentially-weighted moving
  average of daily TSS. Proxy for fitness. Rises slowly with sustained
  load.
- **ATL** ("Acute Training Load") — 7-day exponentially-weighted moving
  average of daily TSS. Proxy for fatigue. Rises fast with hard weeks.
- **TSB** ("Training Stress Balance") — `CTL - ATL`. Proxy for freshness.
  Positive = rested. Strongly negative = overreached.

The EWMA constant is `α = 2 / (N + 1)`. For CTL with N=42:
`α_ctl = 2/43 ≈ 0.0465`. For ATL with N=7: `α_atl = 2/8 = 0.25`. Each
day's CTL is `ctl[t] = ctl[t-1] + α × (tss[t] - ctl[t-1])`.

This is intentionally NOT a vendor score — Garmin's "Training Load" and
Whoop's "Strain" are black-box composites. CTL/ATL/TSB are transparent,
auditable, and standardized across the endurance-sports literature. The
synthesis layer recomputes them from the raw workout TSS values rather
than ingesting vendor numbers.

**Edge cases:**

- Workouts with `training_stress_score=None` are skipped (some activities
  don't have a TSS — e.g. yoga, walks with no power data).
- Empty workouts list → `(0.0, 0.0, 0.0)`.
- We seed CTL and ATL at 0 and warm them up over a 60-day pre-window
  (`_WARMUP_DAYS`). For an athlete with no history this means CTL/ATL
  start low and rise — the correct behavior.
"""

from __future__ import annotations

from datetime import date, timedelta

from broomva_health.domain.workout import Workout

__all__ = ["compute_ctl_atl_tsb"]

_WARMUP_DAYS = 60
"""Days of pre-history walked through to warm up the EWMA before `on_date`.

Long enough that the initial seed of 0 has decayed out (60 days >>
the 42-day CTL time constant), short enough that we don't waste cycles
walking through unrelated history. If callers pass workouts older than
on_date - 60d, those workouts are folded into a single pre-window total
on day 0 — but in practice callers should pass the recent window.
"""


def _ewma_alpha(n: int) -> float:
    """Standard EWMA decay constant: α = 2 / (N + 1)."""
    return 2.0 / (n + 1)


def compute_ctl_atl_tsb(
    workouts: list[Workout],
    *,
    on_date: date,
    ctl_n: int = 42,
    atl_n: int = 7,
) -> tuple[float, float, float]:
    """Compute CTL, ATL, TSB on `on_date` from the workout history.

    Args:
        workouts: All workouts in the history. Order does not matter;
            we bucket by `start_ts.date()`. Workouts with TSS=None are
            silently skipped.
        on_date: The date for which to report CTL/ATL/TSB. Computation
            includes all daily TSS up to AND INCLUDING this date.
        ctl_n: CTL time constant in days. Coggan canonical = 42.
        atl_n: ATL time constant in days. Coggan canonical = 7.

    Returns:
        `(ctl, atl, tsb)` where `tsb = ctl - atl`. All three are TSS/day
        units (the canonical unit for these metrics in METRIC_UNITS).
        For empty input returns `(0.0, 0.0, 0.0)`.
    """
    # Filter to workouts with a TSS value.
    scored = [w for w in workouts if w.training_stress_score is not None]
    if not scored:
        return (0.0, 0.0, 0.0)

    # Bucket TSS by day (UTC date of start_ts). Multiple workouts on the
    # same day sum — a brick workout (ride + run) is two TSS values added.
    daily_tss: dict[date, float] = {}
    for w in scored:
        d = w.start_ts.date()
        # Safe: filter guarantees training_stress_score is not None.
        tss = float(w.training_stress_score)  # type: ignore[arg-type]
        daily_tss[d] = daily_tss.get(d, 0.0) + tss

    # Walk from (earliest workout date - warmup) through on_date inclusive.
    # We need the warmup so initial seed of 0 has time to decay before we
    # care about the value.
    earliest = min(daily_tss)
    start_walk = min(earliest, on_date) - timedelta(days=_WARMUP_DAYS)

    alpha_ctl = _ewma_alpha(ctl_n)
    alpha_atl = _ewma_alpha(atl_n)

    ctl = 0.0
    atl = 0.0
    cursor = start_walk
    while cursor <= on_date:
        tss = daily_tss.get(cursor, 0.0)
        # Standard EWMA step: new = old + α × (sample - old).
        ctl = ctl + alpha_ctl * (tss - ctl)
        atl = atl + alpha_atl * (tss - atl)
        cursor = cursor + timedelta(days=1)

    tsb = ctl - atl
    return (ctl, atl, tsb)
