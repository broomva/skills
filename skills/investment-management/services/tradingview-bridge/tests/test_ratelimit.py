"""Rate limiter tests — token bucket sliding window."""

from __future__ import annotations

import time

import pytest

from tradingview_bridge.ratelimit import TokenBucketLimiter


def test_under_limit_allows() -> None:
    limiter = TokenBucketLimiter(limit_per_minute=5)
    for _ in range(5):
        assert limiter.check("1.2.3.4") is True


def test_over_limit_rejects() -> None:
    limiter = TokenBucketLimiter(limit_per_minute=3)
    for _ in range(3):
        assert limiter.check("1.2.3.4") is True
    assert limiter.check("1.2.3.4") is False


def test_distinct_ips_are_independent() -> None:
    limiter = TokenBucketLimiter(limit_per_minute=2)
    limiter.check("1.1.1.1")
    limiter.check("1.1.1.1")
    # First IP is now at limit, but second IP should still pass
    assert limiter.check("1.1.1.1") is False
    assert limiter.check("2.2.2.2") is True
    assert limiter.check("2.2.2.2") is True
    assert limiter.check("2.2.2.2") is False


def test_reset_clears_single_ip() -> None:
    limiter = TokenBucketLimiter(limit_per_minute=2)
    limiter.check("1.1.1.1")
    limiter.check("1.1.1.1")
    assert limiter.check("1.1.1.1") is False
    limiter.reset("1.1.1.1")
    assert limiter.check("1.1.1.1") is True


def test_reset_all() -> None:
    limiter = TokenBucketLimiter(limit_per_minute=1)
    limiter.check("1.1.1.1")
    limiter.check("2.2.2.2")
    assert limiter.check("1.1.1.1") is False
    assert limiter.check("2.2.2.2") is False
    limiter.reset()
    assert limiter.check("1.1.1.1") is True
    assert limiter.check("2.2.2.2") is True


def test_invalid_limit_raises() -> None:
    with pytest.raises(ValueError, match="limit_per_minute"):
        TokenBucketLimiter(limit_per_minute=0)


def test_sliding_window_eviction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timestamps older than 60s drop out of the window."""
    fake_now = [1000.0]

    def fake_monotonic() -> float:
        return fake_now[0]

    monkeypatch.setattr(time, "monotonic", fake_monotonic)

    limiter = TokenBucketLimiter(limit_per_minute=2)
    assert limiter.check("ip") is True  # t=1000
    assert limiter.check("ip") is True  # t=1000
    assert limiter.check("ip") is False  # at limit

    fake_now[0] = 1061.0  # 61s later — first two should have evicted
    assert limiter.check("ip") is True
