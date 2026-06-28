"""Tests for domain/time.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from broomva_health.domain.time import UTC_EPOCH, ensure_utc, utc_now


def test_utc_now_is_aware() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_ensure_utc_naive_assumes_utc() -> None:
    naive = datetime(2026, 5, 22, 12, 0)
    aware = ensure_utc(naive)
    assert aware.tzinfo is UTC
    assert aware.hour == 12  # NOT shifted


def test_ensure_utc_aware_converts() -> None:
    est = timezone(timedelta(hours=-5))
    aware = datetime(2026, 5, 22, 12, 0, tzinfo=est)
    converted = ensure_utc(aware)
    assert converted.tzinfo is UTC
    assert converted.hour == 17  # shifted


def test_utc_epoch_constant() -> None:
    assert UTC_EPOCH.year == 1970
    assert UTC_EPOCH.tzinfo is UTC
