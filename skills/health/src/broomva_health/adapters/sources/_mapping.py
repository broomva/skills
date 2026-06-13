"""Shared Garmin → domain mappers (used by both the cli and native backends).

`map_context` maps an "eddmann-context"-shaped aggregate document to domain
samples + workouts. Both Garmin backends produce that shape:

- the `cli` backend gets it straight from `garmin-connect --format json context`;
- the `native` backend (garth) normalizes its raw endpoint responses into the
  same shape (and additionally fills `health.hrv` + `training.vo2max`, which the
  eddmann CLI's `context` omits).

Null fields are skipped throughout, so a backend that lacks a field (e.g. the
cli backend has no HRV) simply produces fewer samples.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from broomva_health.domain.device import Device
from broomva_health.domain.metrics import MetricCode, canonical_unit
from broomva_health.domain.samples import QuantitySample
from broomva_health.domain.source import Source
from broomva_health.domain.time import ensure_utc
from broomva_health.domain.workout import Workout

__all__ = ["map_context", "map_workouts"]

_GARMIN_DEVICE = Device(manufacturer="garmin")


def _num(value: Any) -> float | None:
    """Return a float if ``value`` is a real number, else None (null-tolerant)."""
    if isinstance(value, bool):  # bool is an int subclass — never a metric value
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _q(
    metric: MetricCode,
    value: Any,
    *,
    start_ts: datetime,
    end_ts: datetime,
    metadata: dict[str, Any] | None = None,
) -> QuantitySample | None:
    """Build a QuantitySample with the canonical unit, or None if value is null."""
    v = _num(value)
    if v is None:
        return None
    return QuantitySample(
        source=Source.GARMIN,
        metric=metric,
        value=v,
        unit=canonical_unit(metric),
        start_ts=start_ts,
        end_ts=end_ts,
        device=_GARMIN_DEVICE,
        metadata=metadata or {},
    )


def _parse_local_dt(raw: Any) -> datetime | None:
    """Parse a ``startTimeLocal`` ('YYYY-MM-DD HH:MM:SS', no offset).

    The value carries no timezone, so we treat it as UTC-naive (the domain
    coerces naive -> UTC). Known minor imprecision — activity wall-clock is
    local, stored as UTC; the activity_id + raw_summary preserve the original.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return ensure_utc(datetime.fromisoformat(raw.strip()))
    except ValueError:
        return None


def map_context(
    ctx: dict[str, Any], *, now: datetime, day: date | None = None
) -> tuple[list[QuantitySample], list[Workout]]:
    """Map an aggregate ``context`` document to domain samples + workouts.

    Daily aggregates span ``[day_start, end]``; body-battery points are
    point-in-time. Null fields are skipped. Returns ``(quantities, workouts)``.

    ``day`` pins the calendar day explicitly. **Backfill must pass it.** Without
    it the day is inferred from ``body_battery.date`` (falling back to
    ``now.date()``); on a historical day with empty body-battery that fallback
    stamps the sample with *today*, and because quantity upserts key on
    ``(source, metric, start_ts)`` every such day would collide on today's key
    and overwrite each other — collapsing the whole backfill to a single row.
    """
    health = ctx.get("health") or {}
    bb = health.get("body_battery") or {}

    # Calendar-day anchoring. Explicit `day` (backfill) wins; else infer from
    # body_battery.date; else `now`.
    anchor = day
    if anchor is None:
        day_raw = bb.get("date")
        try:
            anchor = date.fromisoformat(day_raw) if isinstance(day_raw, str) else now.date()
        except ValueError:
            anchor = now.date()
    day_start = datetime(anchor.year, anchor.month, anchor.day, tzinfo=UTC)
    # For a past day, clamp end to that day's boundary; for today, clamp to now.
    day_end = day_start + timedelta(days=1)
    end = min(now, day_end) if now >= day_start else day_start  # guarantee end >= start

    quantities: list[QuantitySample] = []

    def add(metric: MetricCode, value: Any, **md: Any) -> None:
        sample = _q(metric, value, start_ts=day_start, end_ts=end, metadata=md or None)
        if sample is not None:
            quantities.append(sample)

    # --- today_stats ------------------------------------------------------
    stats = ctx.get("today_stats") or {}
    add(MetricCode.STEPS, stats.get("totalSteps"))
    add(MetricCode.DISTANCE_M, stats.get("totalDistanceMeters"))
    add(MetricCode.ACTIVE_KCAL, stats.get("totalKilocalories"))
    add(MetricCode.FLOORS_CLIMBED, stats.get("floorsClimbed"))
    add(MetricCode.ACTIVE_SECONDS, stats.get("activeTimeInSeconds"))

    # Resting HR: prefer the dedicated health block, fall back to today_stats.
    hr = health.get("heart_rate") or {}
    add(MetricCode.RESTING_HEART_RATE, hr.get("resting", stats.get("restingHeartRate")))

    # --- sleep (aggregate; stage breakdown -> metadata) -------------------
    sleep = health.get("sleep") or {}
    add(
        MetricCode.SLEEP_DURATION,
        sleep.get("sleepTimeSeconds"),
        deep_s=sleep.get("deepSleepSeconds"),
        light_s=sleep.get("lightSleepSeconds"),
        rem_s=sleep.get("remSleepSeconds"),
        awake_s=sleep.get("awakeSleepSeconds"),
    )

    # --- HRV + VO2max (native backend supplies these; cli backend omits) ---
    add(MetricCode.HRV_OVERNIGHT, (health.get("hrv") or {}).get("lastNightAvg"))
    add(MetricCode.VO2_MAX, (ctx.get("training") or {}).get("vo2max"))

    # --- stress / training readiness / weight (often null) ----------------
    add(MetricCode.STRESS, (health.get("stress") or {}).get("overallStressLevel"))
    add(MetricCode.TRAINING_READINESS, (ctx.get("training") or {}).get("readiness"))
    weight = ctx.get("weight") or {}
    add(MetricCode.WEIGHT_KG, weight.get("current_kg"))
    add(MetricCode.BMI, weight.get("bmi"))
    add(MetricCode.BODY_FAT_PCT, weight.get("body_fat_pct"))
    add(MetricCode.LEAN_MASS_KG, weight.get("lean_mass_kg"))

    # --- expanded wellness metrics (native backend supplies these) ---------
    add(MetricCode.SLEEP_SCORE, sleep.get("sleepScore"))
    add(MetricCode.SPO2_PCT, (health.get("spo2") or {}).get("average"))
    add(MetricCode.RESPIRATION_RPM, (health.get("respiration") or {}).get("avgWaking"))
    add(MetricCode.HYDRATION_ML, (health.get("hydration") or {}).get("ml"))

    # --- body battery time-series: [[epoch_ms, level], ...] ---------------
    for point in bb.get("bodyBatteryValuesArray") or []:
        if not (isinstance(point, (list, tuple)) and len(point) == 2):
            continue
        ts_ms, level = point
        lvl = _num(level)
        if lvl is None or not isinstance(ts_ms, (int, float)):
            continue
        ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
        quantities.append(
            QuantitySample(
                source=Source.GARMIN,
                metric=MetricCode.BODY_BATTERY,
                value=lvl,
                unit=canonical_unit(MetricCode.BODY_BATTERY),
                start_ts=ts,
                end_ts=ts,
                device=_GARMIN_DEVICE,
            )
        )

    # --- recent activities -> workouts ------------------------------------
    workouts = map_workouts(ctx.get("recent_activities") or [])

    return quantities, workouts


def map_workouts(activities: Iterable[Any]) -> list[Workout]:
    """Map Garmin activity-summary dicts to domain ``Workout`` objects.

    Shared by ``map_context`` (sync's ``recent_activities``) and the native
    backend's windowed activity backfill. Non-dict entries and entries missing
    an id or parseable start time are skipped (null-tolerant).
    """
    workouts: list[Workout] = []
    for act in activities or []:
        if not isinstance(act, dict):
            continue
        activity_id = act.get("activityId")
        start = _parse_local_dt(act.get("startTimeLocal"))
        if activity_id is None or start is None:
            continue
        duration = _num(act.get("duration"))
        workouts.append(
            Workout(
                source=Source.GARMIN,
                activity_id=str(activity_id),
                activity_type=str(act.get("activityType") or "unknown"),
                start_ts=start,
                duration_s=round(duration) if duration is not None else 0,
                distance_m=_num(act.get("distance")),
                kcal=_num(act.get("calories")),
                avg_hr=_num(act.get("averageHR")),
                raw_summary=act,
            )
        )
    return workouts
