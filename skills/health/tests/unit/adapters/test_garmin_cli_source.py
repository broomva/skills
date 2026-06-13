"""Tests for GarminCliTraceSource — the eddmann-CLI-delegated Garmin backend.

A fake runner returns canned ``garmin-connect`` output, so no real binary or
network is touched. The context fixture mirrors the REAL eddmann ``--format
json context`` schema (captured live) but carries synthetic values — no real
PII is committed.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from broomva_health.adapters.sources.garmin_cli import (
    CliResult,
    GarminCliTraceSource,
    map_context,
)
from broomva_health.config.paths import HealthPaths
from broomva_health.domain.errors import AuthRequired, SourceUnavailable
from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.source import Source

# --------------------------------------------------------------------------- #
# Sanitized fixture — REAL eddmann `context` schema, SYNTHETIC values
# --------------------------------------------------------------------------- #

SANITIZED_CONTEXT: dict[str, Any] = {
    "profile": {"displayName": None, "fullName": "Test User", "profileImageUrl": None},
    "today_stats": {
        "totalSteps": 8000,
        "totalDistanceMeters": 6000,
        "totalKilocalories": 1500.0,
        "floorsClimbed": None,
        "activeTimeInSeconds": None,
        "minHeartRate": 45,
        "maxHeartRate": 100,
        "restingHeartRate": 50,
    },
    "health": {
        "heart_rate": {"resting": 50, "min": 46, "max": 98},
        "sleep": {
            "sleepTimeSeconds": 28800,
            "deepSleepSeconds": 4800,
            "lightSleepSeconds": 18000,
            "remSleepSeconds": 5400,
            "awakeSleepSeconds": 600,
        },
        "body_battery": {
            "date": "2026-06-12",
            "charged": 70,
            "drained": 50,
            "bodyBatteryValuesArray": [[1781240400000, 20], [1781259840000, 85]],
        },
        "stress": {
            "overallStressLevel": None,
            "restStressLevel": None,
            "activityStressLevel": None,
        },
    },
    "training": {"status": None, "readiness": None},
    "weight": {"current_kg": None, "body_fat_pct": None, "muscle_mass_kg": None},
    "recent_activities": [
        {
            "activityId": 99001,
            "activityName": "Morning Run",
            "activityType": "running",
            "distance": 8200.0,
            "duration": 2400.0,
            "startTimeLocal": "2026-06-12 06:30:00",
            "averageHR": 148.0,
            "calories": 620.0,
            "elevationGain": 35.0,
        }
    ],
}

NOW = datetime(2026, 6, 12, 22, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


@dataclass
class _FakeRunner:
    context: CliResult | None = None
    auth: CliResult | None = None
    raise_exc: BaseException | None = None
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, args: Any) -> CliResult:
        self.calls.append(list(args))
        if self.raise_exc is not None:
            raise self.raise_exc
        sub = list(args)[3:]  # drop [cli, "--format", "json"]
        if sub[:1] == ["context"]:
            assert self.context is not None
            return self.context
        if sub[:2] == ["auth", "status"]:
            assert self.auth is not None
            return self.auth
        return CliResult(1, "", f"unexpected subcommand: {sub}")


@dataclass
class _FakeRepo:
    quantities: list[Any] = field(default_factory=list)
    workouts: list[Any] = field(default_factory=list)

    def upsert_quantity(self, samples: list[Any]) -> int:
        self.quantities.extend(samples)
        return len(samples)

    def upsert_workout(self, workouts: list[Any]) -> int:
        self.workouts.extend(workouts)
        return len(workouts)

    def upsert_raw_document(self, docs: list[Any]) -> int:
        return len(docs)

    def query_raw_documents(
        self, source: Any, start: Any, end: Any, endpoint: Any = None
    ) -> list[Any]:
        return []


class _FakeRateLimiter:
    def __init__(self) -> None:
        self.acquired: list[str] = []

    def acquire(self, key: str) -> None:
        self.acquired.append(key)

    def record_success(self, key: str) -> None:  # pragma: no cover
        pass

    def record_429(self, key: str, retry_after_s: float | None = None) -> None:  # pragma: no cover
        pass


@pytest.fixture
def paths(tmp_path: Path) -> HealthPaths:
    return HealthPaths.discover(home=tmp_path)


def _ctx_result() -> CliResult:
    import json

    return CliResult(0, json.dumps(SANITIZED_CONTEXT), "")


def _auth_result(authenticated: bool) -> CliResult:
    import json

    return CliResult(
        0,
        json.dumps({"authenticated": authenticated, "full_name": "Test User"}),
        "",
    )


# --------------------------------------------------------------------------- #
# Pure mapper tests
# --------------------------------------------------------------------------- #


def test_map_context_quantities() -> None:
    q, _ = map_context(SANITIZED_CONTEXT, now=NOW)
    by_metric = {s.metric: s for s in q if s.metric is not MetricCode.BODY_BATTERY}
    assert by_metric[MetricCode.STEPS].value == 8000.0
    assert by_metric[MetricCode.STEPS].unit == "count"
    assert by_metric[MetricCode.DISTANCE_M].value == 6000.0
    assert by_metric[MetricCode.ACTIVE_KCAL].value == 1500.0
    assert by_metric[MetricCode.RESTING_HEART_RATE].value == 50.0
    assert by_metric[MetricCode.RESTING_HEART_RATE].unit == "bpm"
    assert by_metric[MetricCode.SLEEP_DURATION].value == 28800.0
    # All quantities are tagged Garmin + carry the device.
    assert all(s.source is Source.GARMIN for s in q)


def test_map_context_sleep_stage_metadata() -> None:
    q, _ = map_context(SANITIZED_CONTEXT, now=NOW)
    sleep = next(s for s in q if s.metric is MetricCode.SLEEP_DURATION)
    assert sleep.metadata["deep_s"] == 4800
    assert sleep.metadata["light_s"] == 18000
    assert sleep.metadata["rem_s"] == 5400
    assert sleep.metadata["awake_s"] == 600


def test_map_context_body_battery_timeseries() -> None:
    q, _ = map_context(SANITIZED_CONTEXT, now=NOW)
    bb = [s for s in q if s.metric is MetricCode.BODY_BATTERY]
    assert len(bb) == 2
    assert {s.value for s in bb} == {20.0, 85.0}
    # point-in-time: start == end, at the epoch-ms timestamp
    first = min(bb, key=lambda s: s.start_ts)
    assert first.start_ts == first.end_ts
    assert first.start_ts == datetime.fromtimestamp(1781240400000 / 1000, tz=UTC)


def test_map_context_null_tolerant() -> None:
    """None fields (stress, readiness, weight, floors) are skipped, not crashed."""
    q, _ = map_context(SANITIZED_CONTEXT, now=NOW)
    present = {s.metric for s in q}
    assert MetricCode.STRESS not in present
    assert MetricCode.TRAINING_READINESS not in present
    assert MetricCode.WEIGHT_KG not in present
    assert MetricCode.FLOORS_CLIMBED not in present


def test_map_context_workouts() -> None:
    _, w = map_context(SANITIZED_CONTEXT, now=NOW)
    assert len(w) == 1
    wk = w[0]
    assert wk.source is Source.GARMIN
    assert wk.activity_id == "99001"
    assert wk.activity_type == "running"
    assert wk.duration_s == 2400
    assert wk.distance_m == 8200.0
    assert wk.avg_hr == 148.0
    assert wk.kcal == 620.0
    assert wk.raw_summary["activityName"] == "Morning Run"


def test_map_context_empty_is_safe() -> None:
    q, w = map_context({}, now=NOW)
    assert q == []
    assert w == []


# --------------------------------------------------------------------------- #
# Adapter behavior
# --------------------------------------------------------------------------- #


def test_delegated_auth_flag(paths: HealthPaths) -> None:
    src = GarminCliTraceSource(paths=paths, runner=_FakeRunner())
    assert src.delegated_auth is True
    assert src.name is Source.GARMIN


def test_sync_happy_path(paths: HealthPaths) -> None:
    runner = _FakeRunner(context=_ctx_result())
    src = GarminCliTraceSource(paths=paths, runner=runner)
    repo = _FakeRepo()
    limiter = _FakeRateLimiter()
    result = src.sync(repo=repo, token_store=object(), rate_limiter=limiter)
    assert result.source is Source.GARMIN
    assert result.samples_ingested == len(repo.quantities) > 0
    assert result.workouts_ingested == 1
    assert result.errors == []
    assert limiter.acquired == ["garmin:cli:sync"]  # rate limiter honored
    assert runner.calls[0][-1] == "context"


def test_sync_auth_required_exit_2(paths: HealthPaths) -> None:
    runner = _FakeRunner(context=CliResult(2, "", "not authenticated"))
    src = GarminCliTraceSource(paths=paths, runner=runner)
    with pytest.raises(AuthRequired, match="garmin-connect auth login"):
        src.sync(repo=_FakeRepo(), token_store=object(), rate_limiter=_FakeRateLimiter())


def test_authenticate_delegated_when_authed(paths: HealthPaths) -> None:
    runner = _FakeRunner(auth=_auth_result(True))
    src = GarminCliTraceSource(paths=paths, runner=runner)
    # No raise == success; never collects a password.
    src.authenticate(token_store=object(), mfa=object(), email=None, password=None)


def test_authenticate_delegated_when_not_authed(paths: HealthPaths) -> None:
    runner = _FakeRunner(auth=_auth_result(False))
    src = GarminCliTraceSource(paths=paths, runner=runner)
    with pytest.raises(AuthRequired, match="garmin-connect auth login"):
        src.authenticate(token_store=object(), mfa=object())


def test_status_authed(paths: HealthPaths) -> None:
    src = GarminCliTraceSource(paths=paths, runner=_FakeRunner(auth=_auth_result(True)))
    st = src.status(token_store=object())
    assert st.token_valid is True
    assert st.source is Source.GARMIN


def test_status_not_authed(paths: HealthPaths) -> None:
    src = GarminCliTraceSource(paths=paths, runner=_FakeRunner(auth=_auth_result(False)))
    st = src.status(token_store=object())
    assert st.token_valid is False


def test_status_never_raises_when_cli_missing(paths: HealthPaths) -> None:
    runner = _FakeRunner(raise_exc=FileNotFoundError("garmin-connect"))
    src = GarminCliTraceSource(paths=paths, runner=runner)
    st = src.status(token_store=object())  # must NOT raise (P15-reflex path)
    assert st.token_valid is False
    assert st.last_error is not None


def test_run_cli_missing_maps_to_source_unavailable(paths: HealthPaths) -> None:
    runner = _FakeRunner(raise_exc=FileNotFoundError("garmin-connect"))
    src = GarminCliTraceSource(paths=paths, runner=runner)
    with pytest.raises(SourceUnavailable, match="not found on PATH"):
        src.sync(repo=_FakeRepo(), token_store=object(), rate_limiter=_FakeRateLimiter())


def test_run_timeout_maps_to_source_unavailable(paths: HealthPaths) -> None:
    runner = _FakeRunner(raise_exc=subprocess.TimeoutExpired("garmin-connect", 90))
    src = GarminCliTraceSource(paths=paths, runner=runner)
    with pytest.raises(SourceUnavailable, match="timed out"):
        src.sync(repo=_FakeRepo(), token_store=object(), rate_limiter=_FakeRateLimiter())


def test_run_non_json_maps_to_source_unavailable(paths: HealthPaths) -> None:
    runner = _FakeRunner(context=CliResult(0, "not json at all", ""))
    src = GarminCliTraceSource(paths=paths, runner=runner)
    with pytest.raises(SourceUnavailable, match="non-JSON"):
        src.sync(repo=_FakeRepo(), token_store=object(), rate_limiter=_FakeRateLimiter())


def test_run_nonzero_maps_to_source_unavailable(paths: HealthPaths) -> None:
    runner = _FakeRunner(context=CliResult(1, "", "boom"))
    src = GarminCliTraceSource(paths=paths, runner=runner)
    with pytest.raises(SourceUnavailable, match="failed"):
        src.sync(repo=_FakeRepo(), token_store=object(), rate_limiter=_FakeRateLimiter())


def test_backfill_not_implemented(paths: HealthPaths) -> None:
    src = GarminCliTraceSource(paths=paths, runner=_FakeRunner())
    with pytest.raises(SourceUnavailable, match="no historical backfill"):
        src.backfill(
            repo=_FakeRepo(),
            token_store=object(),
            rate_limiter=_FakeRateLimiter(),
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
        )
