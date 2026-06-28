"""Tests for synthesis/training_load.py — Coggan CTL/ATL/TSB EWMA.

The golden test recomputes the expected CTL/ATL with a separate, simpler
EWMA implementation, then asserts the production function matches. This
way the "expected value" is auditable inline — no magic constant from
spreadsheet copy-paste.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from broomva_health.domain.source import Source
from broomva_health.domain.workout import Workout
from broomva_health.synthesis.training_load import compute_ctl_atl_tsb


def _workout(day: date, tss: float | None, *, idx: int = 0) -> Workout:
    """Build a 1-hour cycling workout on `day` with given TSS.

    Uses model_construct to bypass the domain validator chain (decouples
    these tests from in-flight domain-layer fixes — synthesis only reads
    fields, never re-validates).
    """
    start = datetime(day.year, day.month, day.day, 12, 0, 0, tzinfo=UTC)
    return Workout.model_construct(
        source=Source.GARMIN,
        activity_id=f"wko-{day.isoformat()}-{idx}",
        activity_type="cycling",
        start_ts=start,
        end_ts=start + timedelta(hours=1),
        duration_s=3600,
        distance_m=None,
        kcal=None,
        avg_hr=None,
        max_hr=None,
        training_effect=None,
        training_stress_score=tss,
        device=None,
        fit_blob_sha256=None,
        raw_summary={},
        ingested_at=start,
    )


def _reference_ewma(
    daily_tss: dict[date, float],
    *,
    on_date: date,
    n: int,
    warmup_days: int = 60,
) -> float:
    """Independent reference EWMA — same math, fewer features, easy to audit."""
    alpha = 2.0 / (n + 1)
    if not daily_tss:
        return 0.0
    earliest = min(daily_tss)
    start_walk = min(earliest, on_date) - timedelta(days=warmup_days)

    value = 0.0
    cursor = start_walk
    while cursor <= on_date:
        sample = daily_tss.get(cursor, 0.0)
        value = value + alpha * (sample - value)
        cursor = cursor + timedelta(days=1)
    return value


def test_empty_workouts_returns_zeros() -> None:
    assert compute_ctl_atl_tsb([], on_date=date(2026, 5, 22)) == (0.0, 0.0, 0.0)


def test_all_workouts_have_none_tss_returns_zeros() -> None:
    """Workouts with TSS=None are silently skipped → same as empty."""
    base = date(2026, 5, 15)
    workouts = [_workout(base + timedelta(days=i), None) for i in range(5)]

    assert compute_ctl_atl_tsb(workouts, on_date=date(2026, 5, 22)) == (0.0, 0.0, 0.0)


def test_none_tss_workouts_are_skipped() -> None:
    """Mixed None + scored workouts → only scored ones contribute."""
    base = date(2026, 5, 15)
    workouts = [
        _workout(base, 100.0, idx=0),
        _workout(base + timedelta(days=1), None, idx=1),  # skipped
        _workout(base + timedelta(days=2), 100.0, idx=2),
    ]

    ctl, atl, tsb = compute_ctl_atl_tsb(workouts, on_date=date(2026, 5, 22))

    # Reference: only the two scored days (100 TSS each).
    daily = {base: 100.0, base + timedelta(days=2): 100.0}
    expected_ctl = _reference_ewma(daily, on_date=date(2026, 5, 22), n=42)
    expected_atl = _reference_ewma(daily, on_date=date(2026, 5, 22), n=7)
    assert ctl == pytest.approx(expected_ctl)
    assert atl == pytest.approx(expected_atl)
    assert tsb == pytest.approx(expected_ctl - expected_atl)


def test_golden_seven_consecutive_days_of_100_tss() -> None:
    """7 consecutive days of TSS=100 → CTL ramps via α_ctl=2/43.

    Golden — auditable via the inline reference implementation.
    """
    start = date(2026, 5, 1)
    on_date = start + timedelta(days=6)  # 7th day inclusive (days 0..6)
    workouts = [_workout(start + timedelta(days=i), 100.0, idx=i) for i in range(7)]

    ctl, atl, tsb = compute_ctl_atl_tsb(workouts, on_date=on_date)

    daily = {start + timedelta(days=i): 100.0 for i in range(7)}
    expected_ctl = _reference_ewma(daily, on_date=on_date, n=42)
    expected_atl = _reference_ewma(daily, on_date=on_date, n=7)

    # 1 decimal place is the spec from the task brief.
    assert round(ctl, 1) == round(expected_ctl, 1)
    assert round(atl, 1) == round(expected_atl, 1)
    assert round(tsb, 1) == round(expected_ctl - expected_atl, 1)

    # Sanity: 7 days of 100 TSS with α_ctl≈0.0465 → CTL should be ~28
    # (geometric ramp). Verifies the reference impl is itself sane.
    assert 20.0 < ctl < 35.0


def test_atl_responds_faster_than_ctl() -> None:
    """After a hard week, ATL > CTL → TSB is negative ("fatigued")."""
    start = date(2026, 5, 1)
    on_date = start + timedelta(days=6)
    workouts = [_workout(start + timedelta(days=i), 150.0, idx=i) for i in range(7)]

    ctl, atl, tsb = compute_ctl_atl_tsb(workouts, on_date=on_date)

    assert atl > ctl
    assert tsb < 0
    # 150 TSS/day for a week with α_atl=0.25 should drive ATL well above 60.
    assert atl > 60.0


def test_multiple_workouts_same_day_are_summed() -> None:
    """A 'brick' workout (ride + run on the same day) sums TSS that day."""
    day = date(2026, 5, 15)
    on_date = day + timedelta(days=10)
    workouts = [
        _workout(day, 50.0, idx=0),
        _workout(day, 50.0, idx=1),
    ]

    ctl, atl, _tsb = compute_ctl_atl_tsb(workouts, on_date=on_date)

    # Compare against a single 100 TSS workout that day.
    single = [_workout(day, 100.0, idx=0)]
    ctl_single, atl_single, _ = compute_ctl_atl_tsb(single, on_date=on_date)

    assert ctl == pytest.approx(ctl_single)
    assert atl == pytest.approx(atl_single)


def test_long_decay_after_break() -> None:
    """A high-load week followed by rest → ATL collapses fast, CTL slower.

    Quantitatively: after a single hard week (7 days of 100 TSS) peak CTL
    is only ~28 (it takes weeks to truly saturate). After 30 days of
    nothing, ATL has decayed via α=0.25 per day → (1-0.25)^30 ≈ 0.0002 of
    peak — effectively zero. CTL has decayed via α≈0.0465 → (1-0.0465)^30
    ≈ 0.24 of peak. Both decay, but ATL crashes ~3 orders of magnitude
    faster — the key qualitative property.
    """
    start = date(2026, 5, 1)
    workouts = [_workout(start + timedelta(days=i), 100.0, idx=i) for i in range(7)]

    # Right after the hard week.
    _ctl_peak, atl_peak, _ = compute_ctl_atl_tsb(
        workouts, on_date=start + timedelta(days=6)
    )

    # 30 days later, no further training.
    ctl_decay, atl_decay, tsb_decay = compute_ctl_atl_tsb(
        workouts, on_date=start + timedelta(days=36)
    )

    # The qualitative property — ATL decays much faster than CTL.
    assert atl_decay < atl_peak * 0.01, "ATL should have crashed (7d τ)"
    # CTL should still be positive (slow decay) — 30d ≈ 0.7 of CTL time-constant.
    assert ctl_decay > 0.0
    # The ratio ATL/CTL flips: before rest ATL≫CTL (fresh→fatigued),
    # after rest ATL≪CTL (recovered).
    assert atl_decay < ctl_decay
    # After rest, CTL > ATL → positive TSB (fresh, rested).
    assert tsb_decay > 0


def test_on_date_before_any_workouts_returns_initial_state() -> None:
    """Asking for a date that predates all workouts → ramp from 0 to that day."""
    workouts = [_workout(date(2026, 5, 15), 100.0)]
    on_date = date(2026, 5, 1)  # 14 days before the workout

    ctl, atl, tsb = compute_ctl_atl_tsb(workouts, on_date=on_date)

    # No workout has fired by on_date → all values 0 (within EWMA precision).
    assert ctl == pytest.approx(0.0, abs=1e-9)
    assert atl == pytest.approx(0.0, abs=1e-9)
    assert tsb == pytest.approx(0.0, abs=1e-9)
