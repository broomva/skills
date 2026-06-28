"""SynthesisService — wires the pure synthesis functions to a TraceRepository.

This is the only module in the synthesis layer that does I/O — it queries
the repository for the time windows each pure function needs, then calls
those functions. The pure modules (`hrv.py`, `training_load.py`,
`vo2max.py`, `recovery.py`) remain side-effect-free and trivially
testable in isolation.

The output is a `SynthesisSnapshot` Pydantic model — a frozen value
object that downstream projection / CLI / application layers can consume
directly. The snapshot is the unit of synthesis: one snapshot = one
`(person, date)` worth of derived metrics.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date as date_cls

from pydantic import BaseModel, ConfigDict, Field

from broomva_health.domain.metrics import MetricCode
from broomva_health.ports.repository import TraceRepository
from broomva_health.synthesis.hrv import compute_hrv_cv
from broomva_health.synthesis.recovery import compute_recovery_score
from broomva_health.synthesis.training_load import compute_ctl_atl_tsb
from broomva_health.synthesis.vo2max import compute_vo2max_arc

__all__ = ["SynthesisService", "SynthesisSnapshot"]


_HRV_LOOKBACK_DAYS = 35
"""Lookback for HRV-CV. Slightly larger than the 30d window so the
anchor-trimming inside compute_hrv_cv has headroom for missed nights."""

_WORKOUT_LOOKBACK_DAYS = 200
"""Lookback for CTL/ATL. 200d ≫ 42d CTL constant + 60d warmup, so the
EWMA has fully stabilized at on_date."""

_VO2MAX_LOOKBACK_DAYS = 365 * 3
"""Lookback for the VO2max arc — 3 years catches the multi-year trend
that's the actionable Attia signal."""

_RECOVERY_LOOKBACK_DAYS = 45
"""Lookback for recovery score. Recovery uses a 30d baseline + 7d
recent window — 45d gives the underlying queries enough headroom."""


class SynthesisSnapshot(BaseModel):
    """A point-in-time view of derived health metrics.

    Frozen — synthesis is reproducible from the trace store, so snapshots
    are values, never mutated in place.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    date: date_cls = Field(..., description="The date this snapshot is anchored to")

    hrv_cv_30d: float | None = Field(
        default=None,
        description="HRV coefficient of variation over the trailing 30 days, or None if insufficient data",
    )
    ctl: float = Field(
        default=0.0,
        ge=0.0,
        description="Chronic Training Load — 42d EWMA of per-activity load "
        "(Garmin: activityTrainingLoad / EPOC; Coggan TSS where available)",
    )
    atl: float = Field(
        default=0.0,
        ge=0.0,
        description="Acute Training Load — 7d EWMA of per-activity load (same unit as ctl)",
    )
    tsb: float = Field(
        default=0.0,
        description="Training Stress Balance = CTL - ATL (form; negative = fatigued)",
    )
    vo2max_arc: dict[str, float] = Field(
        default_factory=dict,
        description="VO2max quarterly arc — {'2026-Q1': 47.3, ...}",
    )
    recovery_score: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Custom recovery composite (0-100, 50=baseline), or None if insufficient data",
    )


class SynthesisService:
    """Synthesizes derived metrics from the trace store.

    Construct once per repository and reuse — the service is stateless
    and threadsafe modulo the threadsafety of the underlying repo.
    """

    def __init__(self, repo: TraceRepository) -> None:
        self._repo = repo

    def snapshot(self, on_date: date_cls) -> SynthesisSnapshot:
        """Build a full synthesis snapshot anchored on `on_date`."""
        on_dt = datetime(on_date.year, on_date.month, on_date.day, tzinfo=UTC)

        # --- HRV-CV ---
        hrv_lo = on_dt - timedelta(days=_HRV_LOOKBACK_DAYS)
        hrv_samples = self._repo.query_quantity(
            None, MetricCode.HRV_OVERNIGHT, hrv_lo, on_dt
        )
        hrv_cv = compute_hrv_cv(hrv_samples, window_days=30)

        # --- CTL / ATL / TSB ---
        workouts_lo = on_dt - timedelta(days=_WORKOUT_LOOKBACK_DAYS)
        workouts = self._repo.query_workouts(None, workouts_lo, on_dt)
        ctl, atl, tsb = compute_ctl_atl_tsb(workouts, on_date=on_date)

        # --- VO2max arc ---
        vo2_lo = on_dt - timedelta(days=_VO2MAX_LOOKBACK_DAYS)
        vo2_samples = self._repo.query_quantity(
            None, MetricCode.VO2_MAX, vo2_lo, on_dt
        )
        vo2_arc = compute_vo2max_arc(vo2_samples, bucket="quarter")

        # --- Recovery composite ---
        rec_lo = on_dt - timedelta(days=_RECOVERY_LOOKBACK_DAYS)
        # HRV for recovery is the same metric as for HRV-CV — query both
        # so each pure function gets its independently-bounded window.
        rec_hrv = self._repo.query_quantity(
            None, MetricCode.HRV_OVERNIGHT, rec_lo, on_dt
        )
        rec_rhr = self._repo.query_quantity(
            None, MetricCode.RESTING_HEART_RATE, rec_lo, on_dt
        )
        rec_sleep = self._repo.query_quantity(
            None, MetricCode.SLEEP_DURATION, rec_lo, on_dt
        )
        recovery = compute_recovery_score(
            rec_hrv, rec_rhr, rec_sleep, on_date=on_date
        )

        return SynthesisSnapshot(
            date=on_date,
            hrv_cv_30d=hrv_cv,
            ctl=ctl,
            atl=atl,
            tsb=tsb,
            vo2max_arc=vo2_arc,
            recovery_score=recovery,
        )
