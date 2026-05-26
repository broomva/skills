"""Tests for adapters.clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from broomva_health.adapters.clock import FakeClock, SystemClock


def test_system_clock_returns_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is UTC or now.utcoffset() == timedelta(0)


def test_system_clock_increases_monotonic_ish() -> None:
    clock = SystemClock()
    a = clock.now()
    b = clock.now()
    assert b >= a


def test_fake_clock_initial() -> None:
    t0 = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    clock = FakeClock(initial=t0)
    assert clock.now() == t0


def test_fake_clock_advance() -> None:
    t0 = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    clock = FakeClock(initial=t0)
    clock.advance(60)
    assert clock.now() == t0 + timedelta(seconds=60)


def test_fake_clock_set() -> None:
    t0 = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    clock = FakeClock(initial=t0)
    t1 = datetime(2027, 1, 1, 0, 0, tzinfo=UTC)
    clock.set(t1)
    assert clock.now() == t1


def test_fake_clock_coerces_naive_to_utc() -> None:
    naive = datetime(2026, 5, 22, 12, 0)
    clock = FakeClock(initial=naive)
    assert clock.now().tzinfo is UTC
