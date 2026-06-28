"""Tests for TokenBucketRateLimiter."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from broomva_health.adapters.clock import FakeClock
from broomva_health.adapters.rate_limiters.token_bucket import TokenBucketRateLimiter
from broomva_health.domain.errors import RateLimited

T0 = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(initial=T0)


@pytest.fixture
def limiter(clock: FakeClock) -> TokenBucketRateLimiter:
    return TokenBucketRateLimiter(min_interval_s=900.0, clock=clock, on_429_backoff_s=1800.0)


def test_first_acquire_succeeds(limiter: TokenBucketRateLimiter) -> None:
    limiter.acquire("garmin:sync")  # no exception


def test_second_acquire_within_interval_raises(
    limiter: TokenBucketRateLimiter, clock: FakeClock
) -> None:
    limiter.acquire("garmin:sync")
    clock.advance(60)
    with pytest.raises(RateLimited) as exc_info:
        limiter.acquire("garmin:sync")
    assert exc_info.value.retry_after_s == pytest.approx(840.0, abs=1.0)


def test_acquire_succeeds_after_min_interval(
    limiter: TokenBucketRateLimiter, clock: FakeClock
) -> None:
    limiter.acquire("garmin:sync")
    clock.advance(900)
    limiter.acquire("garmin:sync")  # no exception


def test_per_key_independence(limiter: TokenBucketRateLimiter, clock: FakeClock) -> None:
    limiter.acquire("garmin:sync")
    # Different key should not be affected
    limiter.acquire("whoop:sync")
    clock.advance(60)
    with pytest.raises(RateLimited):
        limiter.acquire("garmin:sync")
    with pytest.raises(RateLimited):
        limiter.acquire("whoop:sync")


def test_record_429_puts_key_in_cooldown(
    limiter: TokenBucketRateLimiter, clock: FakeClock
) -> None:
    limiter.record_429("garmin:sync")
    # advance well past min_interval — still in cooldown
    clock.advance(1000)
    with pytest.raises(RateLimited) as exc_info:
        limiter.acquire("garmin:sync")
    assert exc_info.value.retry_after_s == pytest.approx(800.0, abs=1.0)


def test_record_429_with_explicit_retry_after(
    limiter: TokenBucketRateLimiter, clock: FakeClock
) -> None:
    limiter.record_429("garmin:sync", retry_after_s=60.0)
    clock.advance(30)
    with pytest.raises(RateLimited) as exc_info:
        limiter.acquire("garmin:sync")
    assert exc_info.value.retry_after_s == pytest.approx(30.0, abs=1.0)


def test_cooldown_expires(limiter: TokenBucketRateLimiter, clock: FakeClock) -> None:
    limiter.record_429("garmin:sync", retry_after_s=60.0)
    clock.advance(61)
    limiter.acquire("garmin:sync")  # cooldown elapsed


def test_record_success_clears_cooldown(
    limiter: TokenBucketRateLimiter, clock: FakeClock
) -> None:
    limiter.record_429("garmin:sync", retry_after_s=10_000)
    limiter.record_success("garmin:sync")
    # cooldown gone, but still min_interval — first ever acquire OK
    limiter.acquire("garmin:sync")


def test_record_success_noop_for_unknown_key(
    limiter: TokenBucketRateLimiter,
) -> None:
    # should not raise
    limiter.record_success("never-seen")


def test_rejects_negative_min_interval(clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="min_interval_s"):
        TokenBucketRateLimiter(min_interval_s=-1.0, clock=clock)


def test_rejects_negative_on_429_backoff(clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="on_429_backoff_s"):
        TokenBucketRateLimiter(min_interval_s=1.0, clock=clock, on_429_backoff_s=-1.0)
