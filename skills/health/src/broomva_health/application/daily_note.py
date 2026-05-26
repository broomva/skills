"""Daily-note rendering use case.

Builds a `DailyProjection` for `day` by querying the trace repository
across all known sources, computing the synthesis values (HRV-CV, CTL,
ATL, TSB, VO2max), and emitting via `ProjectionTarget`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.results import DailyProjection
from broomva_health.domain.source import Source
from broomva_health.ports.projection import ProjectionTarget
from broomva_health.ports.repository import TraceRepository

__all__ = ["RenderDailyNoteUseCase"]


@dataclass(frozen=True)
class RenderDailyNoteUseCase:
    repo: TraceRepository
    projection: ProjectionTarget

    def execute(self, *, day: date) -> Path:
        start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=1)

        sources_seen: set[Source] = set()
        hrv = self._latest_value(start, end, MetricCode.HRV_OVERNIGHT, sources_seen)
        rhr = self._latest_value(start, end, MetricCode.RESTING_HEART_RATE, sources_seen)
        sleep_dur = self._latest_value(start, end, MetricCode.SLEEP_DURATION, sources_seen)
        sleep_score = self._latest_value(start, end, MetricCode.SLEEP_SCORE, sources_seen)
        vo2 = self._latest_value(start, end, MetricCode.VO2_MAX, sources_seen)
        bb = self._latest_value(start, end, MetricCode.BODY_BATTERY, sources_seen)
        ctl = self._latest_value(start, end, MetricCode.TRAINING_LOAD_CTL, sources_seen)
        atl = self._latest_value(start, end, MetricCode.TRAINING_LOAD_ATL, sources_seen)
        tsb = self._latest_value(start, end, MetricCode.TRAINING_LOAD_TSB, sources_seen)

        workouts = self.repo.query_workouts(source=None, start=start, end=end)
        last_wk = workouts[-1] if workouts else None

        projection = DailyProjection(
            date=day,
            sources_synced=sorted(sources_seen, key=lambda s: s.value),
            hrv_overnight_ms=hrv,
            rhr_bpm=rhr,
            sleep_hours=(sleep_dur / 3600.0) if sleep_dur is not None else None,
            sleep_score=sleep_score,
            vo2_max=vo2,
            body_battery=bb,
            training_load_ctl=ctl,
            training_load_atl=atl,
            training_load_tsb=tsb,
            activities_count=len(workouts),
            last_activity_type=last_wk.activity_type if last_wk else None,
            last_activity_distance_km=(
                (last_wk.distance_m / 1000.0)
                if last_wk and last_wk.distance_m is not None
                else None
            ),
        )
        return self.projection.emit_daily(day, projection)

    def _latest_value(
        self,
        start: datetime,
        end: datetime,
        metric: MetricCode,
        sources_seen: set[Source],
    ) -> float | None:
        samples = self.repo.query_quantity(source=None, metric=metric, start=start, end=end)
        if not samples:
            return None
        latest = max(samples, key=lambda s: s.end_ts)
        sources_seen.add(latest.source)
        return latest.value
