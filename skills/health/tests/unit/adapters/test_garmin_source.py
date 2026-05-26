"""Tests for GarminTraceSource.

Strategy: inject a FakeGarminClient via `client_factory` so no network or
upstream library is touched. The fake mirrors the shape of the library's
return values closely enough that the mappers are exercised end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from broomva_health.adapters.clock import FakeClock
from broomva_health.adapters.mfa.prompt import StaticMFAProvider
from broomva_health.adapters.rate_limiters.token_bucket import TokenBucketRateLimiter
from broomva_health.adapters.sources.garmin import GarminTraceSource
from broomva_health.adapters.token_stores.filesystem import FilesystemTokenStore
from broomva_health.config.paths import HealthPaths
from broomva_health.domain.errors import AuthRequired, RateLimited, SourceUnavailable
from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.results import TokenBundle
from broomva_health.domain.samples import CategorySample, CorrelationSample, QuantitySample
from broomva_health.domain.source import Source
from broomva_health.domain.workout import Workout

T0 = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
TODAY = date(2026, 5, 22)


# ---------- repository spy ----------


@dataclass
class FakeRepo:
    """Captures everything written to it; never raises."""

    quantity: list[QuantitySample] = field(default_factory=list)
    category: list[CategorySample] = field(default_factory=list)
    correlation: list[CorrelationSample] = field(default_factory=list)
    workouts: list[Workout] = field(default_factory=list)

    def upsert_quantity(self, samples: list[QuantitySample]) -> int:
        self.quantity.extend(samples)
        return len(samples)

    def upsert_category(self, samples: list[CategorySample]) -> int:
        self.category.extend(samples)
        return len(samples)

    def upsert_correlation(self, samples: list[CorrelationSample]) -> int:
        self.correlation.extend(samples)
        return len(samples)

    def upsert_workout(self, workouts: list[Workout]) -> int:
        self.workouts.extend(workouts)
        return len(workouts)

    def last_sample_ts(self, source: Source, metric: MetricCode) -> datetime | None:
        return None

    def query_quantity(
        self, source, metric, start, end
    ) -> list[QuantitySample]:  # pragma: no cover — not used here
        return []

    def query_workouts(self, source, start, end) -> list[Workout]:  # pragma: no cover
        return []

    def migrate(self) -> int:
        return 0

    def close(self) -> None:
        pass


# ---------- fake Garmin client ----------


class FakeHTTPError(Exception):
    """Mimics requests.exceptions.HTTPError with a `.response.status_code`."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.response = type("R", (), {"status_code": status_code})()


@dataclass
class FakeGarminClient:
    """Fake `garminconnect.Garmin` instance.

    `factory()` returns this; `factory(email=, password=, prompt_mfa=)` returns
    a configured instance for the auth flow.
    """

    stats_result: Any = None
    sleep_result: Any = None
    hrv_result: Any = None
    readiness_result: Any = None
    vo2_result: Any = None
    activities_result: Any = None

    raise_on: str | None = None
    raise_exception: BaseException | None = None
    login_should_raise: BaseException | None = None
    login_calls: list[Any] = field(default_factory=list)
    dump_calls: list[Any] = field(default_factory=list)
    dump_payload: bytes = b'{"oauth1": "x", "oauth2": "y"}'

    def login(self, tokenstore: Any | None = None) -> None:
        self.login_calls.append(tokenstore)
        if self.login_should_raise is not None:
            raise self.login_should_raise

    def dump_tokens(self, path: str) -> None:
        self.dump_calls.append(path)
        # Write a fake token file to the path so the adapter can read it back
        from pathlib import Path as _P

        target = _P(path) / "garmin_tokens.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.dump_payload)

    def _raise_if(self, op: str) -> None:
        if self.raise_on == op and self.raise_exception is not None:
            raise self.raise_exception

    def get_stats(self, day: date) -> Any:
        self._raise_if("get_stats")
        return self.stats_result

    def get_sleep_data(self, day: date) -> Any:
        self._raise_if("get_sleep_data")
        return self.sleep_result

    def get_hrv_data(self, day: date) -> Any:
        self._raise_if("get_hrv_data")
        return self.hrv_result

    def get_training_readiness(self, day: date) -> Any:
        self._raise_if("get_training_readiness")
        return self.readiness_result

    def get_max_metrics(self, day: date) -> Any:
        self._raise_if("get_max_metrics")
        return self.vo2_result

    def get_activities(self, start: int, limit: int) -> Any:
        self._raise_if("get_activities")
        return self.activities_result


class FakeClientFactory:
    """Callable that returns a pre-configured FakeGarminClient."""

    def __init__(self, client: FakeGarminClient) -> None:
        self._client = client
        self.call_args: list[dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> FakeGarminClient:
        self.call_args.append({"args": args, "kwargs": kwargs})
        return self._client


# ---------- fixtures ----------


@pytest.fixture
def paths(tmp_path: Path) -> HealthPaths:
    p = HealthPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        vault_dir=tmp_path / "vault",
    )
    p.ensure()
    return p


@pytest.fixture
def store(paths: HealthPaths) -> FilesystemTokenStore:
    return FilesystemTokenStore(paths.tokens_dir)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(initial=T0)


@pytest.fixture
def limiter(clock: FakeClock) -> TokenBucketRateLimiter:
    # min_interval_s=0 so per-day backfills don't need clock-advance in tests
    return TokenBucketRateLimiter(min_interval_s=0.0, clock=clock)


@pytest.fixture
def stored_bundle(store: FilesystemTokenStore) -> TokenBundle:
    bundle = TokenBundle.model_construct(
        source=Source.GARMIN,
        profile="default",
        raw_bytes=b'{"oauth1": "x"}',
        stored_at=T0,
        expires_at=None,
    )
    store.put(bundle)
    return bundle


def _stats_payload() -> dict[str, Any]:
    return {
        "totalSteps": 8423,
        "activeKilocalories": 412,
        "restingHeartRate": 54,
        "averageStressLevel": 28,
        "bodyBatteryMostRecentValue": 67,
    }


def _sleep_payload() -> dict[str, Any]:
    return {
        "dailySleepDTO": {
            "sleepTimeSeconds": 27000,
            "sleepScores": {"overall": {"value": 82}},
        },
        "sleepLevels": [
            {"startGMT": "2026-05-22 04:00:00", "endGMT": "2026-05-22 05:00:00", "activityLevel": 0.0},
            {"startGMT": "2026-05-22 05:00:00", "endGMT": "2026-05-22 06:00:00", "activityLevel": 1.0},
            {"startGMT": "2026-05-22 06:00:00", "endGMT": "2026-05-22 07:00:00", "activityLevel": 2.0},
        ],
    }


def _hrv_payload() -> dict[str, Any]:
    return {"hrvSummary": {"lastNightAvg": 47}}


def _readiness_payload() -> list[dict[str, Any]]:
    return [{"score": 73, "level": "moderate"}]


def _vo2_payload() -> list[dict[str, Any]]:
    return [{"generic": {"vo2MaxValue": 51.2}}]


def _activities_payload() -> list[dict[str, Any]]:
    return [
        {
            "activityId": 1111,
            "activityName": "Morning Run",
            "activityType": {"typeKey": "running"},
            "startTimeGMT": "2026-05-22 13:00:00",
            "duration": 3600,
            "distance": 5000,
            "calories": 350,
            "averageHR": 145,
            "maxHR": 175,
            "aerobicTrainingEffect": 3.2,
        },
        {
            "activityId": 2222,
            "activityType": {"typeKey": "cycling"},
            "startTimeGMT": "2026-05-21 13:00:00",
            "duration": 5400,
            "distance": 30000,
            "calories": 800,
            "averageHR": 130,
            "maxHR": 160,
        },
    ]


# ---------- tests ----------


def test_name_is_garmin(paths: HealthPaths) -> None:
    src = GarminTraceSource(paths=paths, client_factory=FakeClientFactory(FakeGarminClient()))
    assert src.name is Source.GARMIN


def test_sync_without_tokens_raises_auth_required(
    paths: HealthPaths, store: FilesystemTokenStore, limiter: TokenBucketRateLimiter
) -> None:
    src = GarminTraceSource(paths=paths, client_factory=FakeClientFactory(FakeGarminClient()))
    repo = FakeRepo()
    with pytest.raises(AuthRequired):
        src.sync(repo=repo, token_store=store, rate_limiter=limiter)


def test_sync_happy_path(
    paths: HealthPaths,
    store: FilesystemTokenStore,
    limiter: TokenBucketRateLimiter,
    stored_bundle: TokenBundle,
) -> None:
    client = FakeGarminClient(
        stats_result=_stats_payload(),
        sleep_result=_sleep_payload(),
        hrv_result=_hrv_payload(),
        readiness_result=_readiness_payload(),
        vo2_result=_vo2_payload(),
        activities_result=_activities_payload(),
    )
    factory = FakeClientFactory(client)
    src = GarminTraceSource(paths=paths, client_factory=factory)
    repo = FakeRepo()

    result = src.sync(repo=repo, token_store=store, rate_limiter=limiter)

    # Quantity samples — stats(5) + sleep(2: duration + score) + hrv(1) + readiness(1) + vo2(1) = 10
    quantities_by_metric = {s.metric for s in repo.quantity}
    assert MetricCode.STEPS in quantities_by_metric
    assert MetricCode.ACTIVE_KCAL in quantities_by_metric
    assert MetricCode.RESTING_HEART_RATE in quantities_by_metric
    assert MetricCode.STRESS in quantities_by_metric
    assert MetricCode.BODY_BATTERY in quantities_by_metric
    assert MetricCode.SLEEP_DURATION in quantities_by_metric
    assert MetricCode.SLEEP_SCORE in quantities_by_metric
    assert MetricCode.HRV_OVERNIGHT in quantities_by_metric
    assert MetricCode.TRAINING_READINESS in quantities_by_metric
    assert MetricCode.VO2_MAX in quantities_by_metric

    # Category samples: 3 sleep stages
    sleep_cats = [s for s in repo.category if s.metric == MetricCode.SLEEP_STAGE]
    assert len(sleep_cats) == 3
    assert {c.category for c in sleep_cats} == {"deep", "light", "rem"}

    # Workouts: 2 activities
    assert len(repo.workouts) == 2
    assert repo.workouts[0].activity_id == "1111"
    assert repo.workouts[0].activity_type == "running"
    assert repo.workouts[0].duration_s == 3600

    # SyncResult — counts come from repo.upsert return values
    assert result.source is Source.GARMIN
    assert result.samples_ingested == len(repo.quantity) + len(repo.category)
    assert result.workouts_ingested == len(repo.workouts)
    assert result.errors == []


def test_sync_handles_429_records_to_limiter(
    paths: HealthPaths,
    store: FilesystemTokenStore,
    limiter: TokenBucketRateLimiter,
    stored_bundle: TokenBundle,
    clock: FakeClock,
) -> None:
    client = FakeGarminClient(
        raise_on="get_stats",
        raise_exception=FakeHTTPError(429),
    )
    factory = FakeClientFactory(client)
    src = GarminTraceSource(paths=paths, client_factory=factory)
    repo = FakeRepo()

    with pytest.raises(RateLimited):
        src.sync(repo=repo, token_store=store, rate_limiter=limiter)

    # Verify the limiter is now in cooldown for the key
    with pytest.raises(RateLimited):
        limiter.acquire("garmin:sync")


def test_sync_handles_401_as_auth_required(
    paths: HealthPaths,
    store: FilesystemTokenStore,
    limiter: TokenBucketRateLimiter,
    stored_bundle: TokenBundle,
) -> None:
    client = FakeGarminClient(
        raise_on="get_stats",
        raise_exception=FakeHTTPError(401),
    )
    factory = FakeClientFactory(client)
    src = GarminTraceSource(paths=paths, client_factory=factory)
    repo = FakeRepo()

    with pytest.raises(AuthRequired):
        src.sync(repo=repo, token_store=store, rate_limiter=limiter)


def test_sync_partial_failure_continues(
    paths: HealthPaths,
    store: FilesystemTokenStore,
    limiter: TokenBucketRateLimiter,
    stored_bundle: TokenBundle,
) -> None:
    """A non-fatal exception on one endpoint should not blow up the whole sync."""
    client = FakeGarminClient(
        stats_result=_stats_payload(),
        sleep_result=None,
        hrv_result=_hrv_payload(),
        readiness_result=None,
        vo2_result=None,
        activities_result=_activities_payload(),
        raise_on="get_sleep_data",
        raise_exception=ValueError("malformed payload"),
    )
    factory = FakeClientFactory(client)
    src = GarminTraceSource(paths=paths, client_factory=factory)
    repo = FakeRepo()

    result = src.sync(repo=repo, token_store=store, rate_limiter=limiter)

    assert any("get_sleep_data" in err for err in result.errors)
    # Other endpoints still produced samples
    assert any(s.metric == MetricCode.STEPS for s in repo.quantity)
    assert any(s.metric == MetricCode.HRV_OVERNIGHT for s in repo.quantity)
    assert len(repo.workouts) == 2


def test_status_no_tokens_returns_invalid(
    paths: HealthPaths, store: FilesystemTokenStore
) -> None:
    src = GarminTraceSource(paths=paths, client_factory=FakeClientFactory(FakeGarminClient()))
    status = src.status(token_store=store)
    assert status.source is Source.GARMIN
    assert status.token_valid is False
    assert status.token_expires_at is None
    assert status.last_sync is None


def test_status_with_tokens_returns_valid(
    paths: HealthPaths, store: FilesystemTokenStore
) -> None:
    bundle = TokenBundle.model_construct(
        source=Source.GARMIN,
        profile="default",
        raw_bytes=b"x",
        stored_at=T0,
        expires_at=T0 + timedelta(hours=24),
    )
    store.put(bundle)
    src = GarminTraceSource(paths=paths, client_factory=FakeClientFactory(FakeGarminClient()))
    status = src.status(token_store=store)
    assert status.token_valid is True
    assert status.token_expires_at == T0 + timedelta(hours=24)


def test_status_makes_no_network_call(
    paths: HealthPaths, store: FilesystemTokenStore
) -> None:
    client = FakeGarminClient()
    factory = FakeClientFactory(client)
    src = GarminTraceSource(paths=paths, client_factory=factory)
    src.status(token_store=store)
    # No factory calls — confirms no client was constructed for status
    assert factory.call_args == []


def test_authenticate_persists_tokens(
    paths: HealthPaths, store: FilesystemTokenStore
) -> None:
    client = FakeGarminClient(dump_payload=b'{"oauth1": "abc"}')
    factory = FakeClientFactory(client)
    src = GarminTraceSource(paths=paths, client_factory=factory)

    src.authenticate(
        token_store=store,
        mfa=StaticMFAProvider("123456"),
        email="me@example.com",
        password="hunter2",
    )

    # Factory called with (email, password, prompt_mfa=callable)
    assert len(factory.call_args) == 1
    kwargs = factory.call_args[0]["kwargs"]
    assert kwargs["email"] == "me@example.com"
    assert kwargs["password"] == "hunter2"
    assert callable(kwargs["prompt_mfa"])

    # Tokens persisted
    loaded = store.get(Source.GARMIN)
    assert loaded is not None
    assert loaded.raw_bytes == b'{"oauth1": "abc"}'


def test_authenticate_missing_creds_raises_auth_required(
    paths: HealthPaths, store: FilesystemTokenStore
) -> None:
    src = GarminTraceSource(paths=paths, client_factory=FakeClientFactory(FakeGarminClient()))
    with pytest.raises(AuthRequired):
        src.authenticate(
            token_store=store,
            mfa=StaticMFAProvider("123456"),
            email=None,
            password=None,
        )


def test_authenticate_maps_401_to_auth_required(
    paths: HealthPaths, store: FilesystemTokenStore
) -> None:
    client = FakeGarminClient(login_should_raise=FakeHTTPError(401))
    factory = FakeClientFactory(client)
    src = GarminTraceSource(paths=paths, client_factory=factory)
    with pytest.raises(AuthRequired):
        src.authenticate(
            token_store=store,
            mfa=StaticMFAProvider("123"),
            email="x@y.com",
            password="pw",
        )


def test_backfill_iterates_days_and_acquires_per_day(
    paths: HealthPaths,
    store: FilesystemTokenStore,
    limiter: TokenBucketRateLimiter,
    stored_bundle: TokenBundle,
) -> None:
    client = FakeGarminClient(
        stats_result={"totalSteps": 5000},
        hrv_result=_hrv_payload(),
        readiness_result=None,
        vo2_result=None,
        sleep_result=None,
        activities_result=_activities_payload(),
    )
    factory = FakeClientFactory(client)
    src = GarminTraceSource(paths=paths, client_factory=factory)
    repo = FakeRepo()

    result = src.backfill(
        repo=repo,
        token_store=store,
        rate_limiter=limiter,
        start=date(2026, 5, 20),
        end=date(2026, 5, 22),
    )

    # 3 days * (steps + hrv) = 6 samples
    assert len([s for s in repo.quantity if s.metric == MetricCode.STEPS]) == 3
    assert len([s for s in repo.quantity if s.metric == MetricCode.HRV_OVERNIGHT]) == 3
    # Activities filtered to range — both fall within [2026-05-20, 2026-05-22]
    assert len(repo.workouts) == 2
    assert result.range_start == date(2026, 5, 20)
    assert result.range_end == date(2026, 5, 22)


def test_backfill_rejects_inverted_range(
    paths: HealthPaths,
    store: FilesystemTokenStore,
    limiter: TokenBucketRateLimiter,
    stored_bundle: TokenBundle,
) -> None:
    src = GarminTraceSource(paths=paths, client_factory=FakeClientFactory(FakeGarminClient()))
    repo = FakeRepo()
    with pytest.raises(SourceUnavailable):
        src.backfill(
            repo=repo,
            token_store=store,
            rate_limiter=limiter,
            start=date(2026, 5, 25),
            end=date(2026, 5, 20),
        )
