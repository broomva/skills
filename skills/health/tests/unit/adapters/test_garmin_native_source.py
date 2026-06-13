"""Tests for GarminNativeTraceSource — the in-house garth-backed Garmin source.

A fake garth module (resume/save/connectapi/client.username) stands in for the
real engine, so no network or real token is touched. The connectapi responses
mirror the REAL endpoint shapes captured live; values are synthetic.
"""

from __future__ import annotations

import types
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from broomva_health.adapters.sources.garmin_native import GarminNativeTraceSource
from broomva_health.config.paths import HealthPaths
from broomva_health.domain.errors import AuthRequired, SourceUnavailable
from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.source import Source

NOW = datetime(2026, 6, 12, 22, 0, tzinfo=UTC)

# Real endpoint shapes, synthetic values.
DEFAULT_RESPONSES: dict[str, Any] = {
    "usersummary/daily": {
        "totalSteps": 8000,
        "totalDistanceMeters": 6000,
        "totalKilocalories": 1500.0,
        "restingHeartRate": 50,
        "minHeartRate": 45,
        "maxHeartRate": 120,
        "floorsAscended": 3.0,
    },
    "sleep-service": {
        "dailySleepDTO": {
            "sleepTimeSeconds": 28800,
            "deepSleepSeconds": 4800,
            "lightSleepSeconds": 18000,
            "remSleepSeconds": 5400,
            "awakeSleepSeconds": 600,
            "sleepScores": {"overall": {"value": 81}},
        }
    },
    "hrv-service": {"hrvSummary": {"lastNightAvg": 62}},
    "bodyBattery": [
        {
            "date": "2026-06-12",
            "charged": 70,
            "drained": 50,
            "bodyBatteryValuesArray": [[1781240400000, 20], [1781259840000, 85]],
        }
    ],
    "maxmet": {"generic": {"vo2MaxValue": 49.0}},
    "trainingreadiness": [{"score": 93, "level": "HIGH"}],
    "dailyStress": {"avgStressLevel": 31, "maxStressLevel": 100},
    "/daily/spo2": {"averageSpO2": 90.0, "lowestSpO2": 83},
    "/daily/respiration": {"avgWakingRespirationValue": 14.0, "avgSleepRespirationValue": 11.0},
    "weight-service": {"totalAverage": {"weight": 72500.0, "bmi": 23.1, "bodyFat": 18.0, "muscleMass": 34000.0}},
    "hydration": {"valueInML": 1800.0},
    "activitylist-service": [
        {
            "activityId": 99001,
            "activityName": "Morning Run",
            "activityType": {"typeKey": "running"},
            "distance": 8200.0,
            "duration": 2400.0,
            "startTimeLocal": "2026-06-12 06:30:00",
            "averageHR": 148.0,
            "calories": 620.0,
        }
    ],
}


class _FakeGarth:
    def __init__(
        self,
        responses: dict[str, Any] | None = None,
        *,
        username: str = "Test User",
        resume_raises: BaseException | None = None,
    ) -> None:
        self._responses = DEFAULT_RESPONSES if responses is None else responses
        self.client = types.SimpleNamespace(username=username)
        self.resumed: list[str] = []
        self.saved: list[str] = []
        self.api_calls: list[str] = []
        self._resume_raises = resume_raises

    def resume(self, d: str) -> None:
        self.resumed.append(d)
        if self._resume_raises is not None:
            raise self._resume_raises

    def save(self, d: str) -> None:
        self.saved.append(d)

    def connectapi(self, path: str) -> Any:
        self.api_calls.append(path)
        for needle, resp in self._responses.items():
            if needle in path:
                return resp
        return None


class _FakeRepo:
    def __init__(self) -> None:
        self.quantities: list[Any] = []
        self.workouts: list[Any] = []
        self.raw_docs: list[Any] = []

    def upsert_quantity(self, s: list[Any]) -> int:
        self.quantities.extend(s)
        return len(s)

    def upsert_workout(self, w: list[Any]) -> int:
        self.workouts.extend(w)
        return len(w)

    def upsert_raw_document(self, docs: list[Any]) -> int:
        self.raw_docs.extend(docs)
        return len(docs)


class _FakeRateLimiter:
    def __init__(self) -> None:
        self.acquired: list[str] = []

    def acquire(self, key: str) -> None:
        self.acquired.append(key)


@pytest.fixture
def paths(tmp_path: Path) -> HealthPaths:
    return HealthPaths.discover(home=tmp_path)


def _seed_token(paths: HealthPaths, profile: str = "default") -> Path:
    d = paths.tokens_dir / "garmin-garth" / profile
    d.mkdir(parents=True, exist_ok=True)
    (d / "oauth1_token.json").write_text('{"oauth_token":"x","oauth_token_secret":"y"}')
    (d / "oauth2_token.json").write_text('{"access_token":"a","refresh_token":"r"}')
    return d


# --------------------------------------------------------------------------- #
# Sync + mapping (the in-house path, incl. HRV + VO2max the cli backend lacks)
# --------------------------------------------------------------------------- #


def test_sync_happy_path_includes_hrv_and_vo2(paths: HealthPaths) -> None:
    _seed_token(paths)
    garth = _FakeGarth()
    src = GarminNativeTraceSource(paths=paths, garth_module=garth)
    repo = _FakeRepo()
    limiter = _FakeRateLimiter()
    result = src.sync(repo=repo, token_store=object(), rate_limiter=limiter)

    assert result.source is Source.GARMIN
    assert result.samples_ingested == len(repo.quantities) > 0
    assert result.workouts_ingested == 1
    assert limiter.acquired == ["garmin:native:sync"]

    by_metric = {s.metric: s.value for s in repo.quantities}
    # The richer in-house metrics the eddmann cli backend dropped:
    assert by_metric[MetricCode.HRV_OVERNIGHT] == 62.0
    assert by_metric[MetricCode.VO2_MAX] == 49.0
    # Plus the standard set:
    assert by_metric[MetricCode.STEPS] == 8000.0
    assert by_metric[MetricCode.RESTING_HEART_RATE] == 50.0
    assert by_metric[MetricCode.SLEEP_DURATION] == 28800.0
    assert by_metric[MetricCode.TRAINING_READINESS] == 93.0
    # body battery time-series → 2 points
    assert sum(1 for s in repo.quantities if s.metric is MetricCode.BODY_BATTERY) == 2
    # Phase-2 expanded metrics:
    assert by_metric[MetricCode.STRESS] == 31.0
    assert by_metric[MetricCode.SPO2_PCT] == 90.0
    assert by_metric[MetricCode.RESPIRATION_RPM] == 14.0
    assert by_metric[MetricCode.SLEEP_SCORE] == 81.0
    assert by_metric[MetricCode.HYDRATION_ML] == 1800.0
    assert by_metric[MetricCode.WEIGHT_KG] == 72.5  # 72500 g → kg
    assert by_metric[MetricCode.BMI] == 23.1
    assert by_metric[MetricCode.BODY_FAT_PCT] == 18.0
    assert by_metric[MetricCode.LEAN_MASS_KG] == 34.0  # 34000 g → kg


def test_sync_persists_refreshed_token(paths: HealthPaths) -> None:
    _seed_token(paths)
    garth = _FakeGarth()
    src = GarminNativeTraceSource(paths=paths, garth_module=garth)
    src.sync(repo=_FakeRepo(), token_store=object(), rate_limiter=_FakeRateLimiter())
    assert garth.saved, "garth.save must be called to persist refreshed tokens"


def test_sync_workout_activity_type_flattened(paths: HealthPaths) -> None:
    _seed_token(paths)
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth())
    repo = _FakeRepo()
    src.sync(repo=repo, token_store=object(), rate_limiter=_FakeRateLimiter())
    assert repo.workouts[0].activity_type == "running"  # dict {typeKey} → "running"
    assert repo.workouts[0].activity_id == "99001"


def test_sync_without_token_raises_auth_required(paths: HealthPaths) -> None:
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth())
    with pytest.raises(AuthRequired, match="health auth import"):
        src.sync(repo=_FakeRepo(), token_store=object(), rate_limiter=_FakeRateLimiter())


def test_sync_queries_local_date_not_utc(paths: HealthPaths) -> None:
    """Regression: daily data is keyed by the user's LOCAL date, not UTC.

    Using utc_now().date() asks Garmin for tomorrow's (empty) day for any user
    behind UTC in the evening. Sync must query the local calendar date.
    """
    from datetime import datetime as _dt

    _seed_token(paths)
    garth = _FakeGarth()
    src = GarminNativeTraceSource(paths=paths, garth_module=garth)
    src.sync(repo=_FakeRepo(), token_store=object(), rate_limiter=_FakeRateLimiter())
    local_today = _dt.now().astimezone().date().isoformat()
    daily_calls = [c for c in garth.api_calls if "usersummary/daily" in c]
    assert daily_calls, "sync must hit the daily summary endpoint"
    assert local_today in daily_calls[0], (
        f"daily query must use local date {local_today}, got {daily_calls[0]}"
    )


def test_sync_partial_tolerant_when_endpoint_fails(paths: HealthPaths) -> None:
    """A failing endpoint yields an empty section, not a dead sync."""
    _seed_token(paths)
    # hrv endpoint returns None (missing key) → no HRV sample, rest still maps.
    resp = {k: v for k, v in DEFAULT_RESPONSES.items() if k != "hrv-service"}
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth(resp))
    repo = _FakeRepo()
    src.sync(repo=repo, token_store=object(), rate_limiter=_FakeRateLimiter())
    metrics = {s.metric for s in repo.quantities}
    assert MetricCode.HRV_OVERNIGHT not in metrics
    assert MetricCode.STEPS in metrics  # the rest survived


def test_sync_captures_raw_documents_losslessly(paths: HealthPaths) -> None:
    """Every non-null endpoint is persisted verbatim — incl. fields we never map."""
    from datetime import datetime as _dt

    _seed_token(paths)
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth())
    repo = _FakeRepo()
    src.sync(repo=repo, token_store=object(), rate_limiter=_FakeRateLimiter())

    endpoints = {d.endpoint for d in repo.raw_docs}
    assert {
        "daily_summary", "sleep", "hrv", "body_battery", "vo2max",
        "stress", "spo2", "respiration", "weight", "hydration",
    } <= endpoints
    # The raw payload keeps fields the structured mapping drops (minHeartRate /
    # maxHeartRate are not MetricCodes) — this is the whole point of passthrough.
    daily = next(d for d in repo.raw_docs if d.endpoint == "daily_summary")
    assert daily.payload["minHeartRate"] == 45
    assert daily.payload["maxHeartRate"] == 120
    assert daily.calendar_date == _dt.now().astimezone().date()


# --------------------------------------------------------------------------- #
# auth import (bootstrap) + auth + status
# --------------------------------------------------------------------------- #


def test_import_tokens_copies_and_verifies(paths: HealthPaths, tmp_path: Path) -> None:
    srcdir = tmp_path / "eddmann"
    srcdir.mkdir()
    (srcdir / "oauth1_token.json").write_text('{"oauth_token":"x","oauth_token_secret":"y"}')
    (srcdir / "oauth2_token.json").write_text('{"access_token":"a","refresh_token":"r"}')

    garth = _FakeGarth()
    src = GarminNativeTraceSource(paths=paths, garth_module=garth)
    n = src.import_tokens(from_dir=str(srcdir))
    assert n == 2
    dst = paths.tokens_dir / "garmin-garth" / "default"
    assert (dst / "oauth1_token.json").exists()
    assert (dst / "oauth2_token.json").exists()
    assert garth.resumed, "import must verify by resuming"


def test_import_tokens_missing_source_raises(paths: HealthPaths, tmp_path: Path) -> None:
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth())
    with pytest.raises(SourceUnavailable, match="token file not found"):
        src.import_tokens(from_dir=str(tmp_path / "nope"))


def test_import_tokens_invalid_raises_auth_required(paths: HealthPaths, tmp_path: Path) -> None:
    srcdir = tmp_path / "bad"
    srcdir.mkdir()
    (srcdir / "oauth1_token.json").write_text("{}")
    (srcdir / "oauth2_token.json").write_text("{}")
    garth = _FakeGarth(resume_raises=RuntimeError("expired"))
    src = GarminNativeTraceSource(paths=paths, garth_module=garth)
    with pytest.raises(AuthRequired, match="failed to load"):
        src.import_tokens(from_dir=str(srcdir))


def test_authenticate_without_token_points_to_import(paths: HealthPaths) -> None:
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth())
    with pytest.raises(AuthRequired, match="health auth import"):
        src.authenticate(token_store=object(), mfa=object())


def test_authenticate_with_token_ok(paths: HealthPaths) -> None:
    _seed_token(paths)
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth())
    src.authenticate(token_store=object(), mfa=object())  # no raise


def test_status_no_token_invalid(paths: HealthPaths) -> None:
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth())
    st = src.status(token_store=object())
    assert st.token_valid is False


def test_status_with_token_valid(paths: HealthPaths) -> None:
    _seed_token(paths)
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth())
    st = src.status(token_store=object())
    assert st.token_valid is True


def test_status_never_raises_on_bad_token(paths: HealthPaths) -> None:
    _seed_token(paths)
    garth = _FakeGarth(resume_raises=RuntimeError("boom"))
    src = GarminNativeTraceSource(paths=paths, garth_module=garth)
    st = src.status(token_store=object())  # must not raise (P15 reflex)
    assert st.token_valid is False
    assert st.last_error is not None


def test_delegated_auth_flag(paths: HealthPaths) -> None:
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth())
    assert src.delegated_auth is True
    assert src.name is Source.GARMIN


# --------------------------------------------------------------------------- #
# backfill
# --------------------------------------------------------------------------- #


class _RecordingSleep:
    """A no-op sleeper that records its durations (so tests never block)."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _backfill_src(paths: HealthPaths, garth: _FakeGarth) -> GarminNativeTraceSource:
    """A native source whose backfill never actually sleeps."""
    return GarminNativeTraceSource(paths=paths, garth_module=garth, sleep=_RecordingSleep())


def test_backfill_iterates_days(paths: HealthPaths) -> None:
    _seed_token(paths)
    garth = _FakeGarth()
    src = _backfill_src(paths, garth)
    repo = _FakeRepo()
    result = src.backfill(
        repo=repo,
        token_store=object(),
        rate_limiter=_FakeRateLimiter(),
        start=date(2026, 6, 10),
        end=date(2026, 6, 12),
    )
    assert result.samples_ingested > 0
    # daily wellness endpoint hit once per day (3 days)
    daily_calls = [c for c in garth.api_calls if "usersummary/daily" in c]
    assert len(daily_calls) == 3


def test_backfill_anchors_each_day_explicitly(paths: HealthPaths) -> None:
    """Regression (catastrophic collapse): each historical day must anchor on
    ITS OWN date, not on body_battery.date / today.

    The fake returns a fixed body_battery.date (2026-06-12) for every call. With
    the old (inferred-day) mapping, all 3 days would anchor to 2026-06-12 and —
    because quantity upserts key on (source, metric, start_ts) — collapse onto a
    single row. With explicit per-day anchoring they stay distinct.
    """
    _seed_token(paths)
    src = _backfill_src(paths, _FakeGarth())
    repo = _FakeRepo()
    src.backfill(
        repo=repo,
        token_store=object(),
        rate_limiter=_FakeRateLimiter(),
        start=date(2026, 6, 10),
        end=date(2026, 6, 12),
    )
    step_days = {s.start_ts.date() for s in repo.quantities if s.metric is MetricCode.STEPS}
    assert step_days == {date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)}
    # And end_ts is clamped to that day's boundary, not "now" (fix #3): the
    # 2026-06-10 aggregate must end at 2026-06-11T00:00, not months later.
    s0 = next(
        s
        for s in repo.quantities
        if s.metric is MetricCode.STEPS and s.start_ts.date() == date(2026, 6, 10)
    )
    assert s0.end_ts == datetime(2026, 6, 11, tzinfo=UTC)


def test_backfill_does_not_touch_poll_floor(paths: HealthPaths) -> None:
    """Regression (day-1 death + 15-min-floor block): backfill must NOT acquire
    the sync poll-floor limiter at all — it is deliberate and self-paced.

    The old code acquired per day (died on day 2 under the 15-min floor); the
    interim fix acquired once at entry (still blocked a bulk pull for 15 min
    after any recent sync). Backfill now bypasses the poll-floor entirely.
    """
    _seed_token(paths)
    src = _backfill_src(paths, _FakeGarth())
    limiter = _FakeRateLimiter()
    src.backfill(
        repo=_FakeRepo(),
        token_store=object(),
        rate_limiter=limiter,
        start=date(2026, 6, 1),
        end=date(2026, 6, 12),  # 12 days — would die on day 2 under the old code
    )
    assert limiter.acquired == []


def test_backfill_paces_between_days(paths: HealthPaths) -> None:
    """Gentle inter-day pacing: N days → N-1 inter-day sleeps (≥)."""
    _seed_token(paths)
    sleeper = _RecordingSleep()
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth(), sleep=sleeper)
    src.backfill(
        repo=_FakeRepo(),
        token_store=object(),
        rate_limiter=_FakeRateLimiter(),
        start=date(2026, 6, 10),
        end=date(2026, 6, 12),
    )
    # 3 days → at least 2 inter-day sleeps (window pagination may add more).
    assert len(sleeper.calls) >= 2
    assert all(s > 0 for s in sleeper.calls)


def test_backfill_fetches_activities_once_not_per_day(paths: HealthPaths) -> None:
    """Regression (activities don't backfill): the activity search is a windowed
    one-shot, not a per-day re-pull of the recent set."""
    _seed_token(paths)
    garth = _FakeGarth()
    src = _backfill_src(paths, garth)
    repo = _FakeRepo()
    result = src.backfill(
        repo=repo,
        token_store=object(),
        rate_limiter=_FakeRateLimiter(),
        start=date(2026, 6, 10),
        end=date(2026, 6, 12),  # 3 days
    )
    activity_calls = [c for c in garth.api_calls if "activitylist-service" in c]
    assert len(activity_calls) == 1, "activities fetched once for the window, not per day"
    # The windowed search must carry the date-range filter.
    assert "startDate=2026-06-10" in activity_calls[0]
    assert "endDate=2026-06-12" in activity_calls[0]
    assert result.workouts_ingested == 1  # the one synthetic activity in range


def test_backfill_captures_raw_per_day(paths: HealthPaths) -> None:
    """Backfill persists verbatim daily endpoints per calendar day (no activities)."""
    _seed_token(paths)
    src = _backfill_src(paths, _FakeGarth())
    repo = _FakeRepo()
    src.backfill(
        repo=repo,
        token_store=object(),
        rate_limiter=_FakeRateLimiter(),
        start=date(2026, 6, 10),
        end=date(2026, 6, 12),
    )
    assert {d.calendar_date for d in repo.raw_docs} == {
        date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)
    }
    # Activities are a windowed one-shot, not a per-day raw doc on the backfill path.
    assert all(d.endpoint != "activities_recent" for d in repo.raw_docs)
    # daily_summary captured once per day.
    assert sum(1 for d in repo.raw_docs if d.endpoint == "daily_summary") == 3


def test_backfill_inverted_range_raises(paths: HealthPaths) -> None:
    _seed_token(paths)
    src = GarminNativeTraceSource(paths=paths, garth_module=_FakeGarth())
    with pytest.raises(SourceUnavailable, match="precedes start"):
        src.backfill(
            repo=_FakeRepo(),
            token_store=object(),
            rate_limiter=_FakeRateLimiter(),
            start=date(2026, 6, 12),
            end=date(2026, 6, 10),
        )
