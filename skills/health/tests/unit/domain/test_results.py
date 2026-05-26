"""Tests for domain/results.py."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from broomva_health.domain.results import (
    BackfillResult,
    DailyProjection,
    SourceStatus,
    SyncResult,
    TokenBundle,
)
from broomva_health.domain.source import Source

T0 = datetime(2026, 5, 22, 8, 0, tzinfo=UTC)
T1 = T0 + timedelta(seconds=2)


def test_sync_result_basic() -> None:
    r = SyncResult(
        source=Source.GARMIN,
        started_at=T0,
        finished_at=T1,
        samples_ingested=42,
        workouts_ingested=1,
    )
    assert r.succeeded is True
    assert r.duration_s == 2.0


def test_sync_result_failed_when_errors() -> None:
    r = SyncResult(
        source=Source.GARMIN,
        started_at=T0,
        finished_at=T1,
        samples_ingested=0,
        workouts_ingested=0,
        errors=["boom"],
    )
    assert r.succeeded is False


def test_sync_result_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        SyncResult(
            source=Source.GARMIN,
            started_at=T0,
            finished_at=T1,
            samples_ingested=-1,
            workouts_ingested=0,
        )


def test_backfill_result_basic() -> None:
    r = BackfillResult(
        source=Source.GARMIN,
        range_start=date(2025, 1, 1),
        range_end=date(2025, 1, 31),
        samples_ingested=10,
        workouts_ingested=2,
    )
    assert r.samples_ingested == 10


def test_source_status_defaults() -> None:
    s = SourceStatus(source=Source.GARMIN)
    assert s.token_valid is False
    assert s.last_sync is None


def test_token_bundle_basic() -> None:
    bundle = TokenBundle(
        source=Source.GARMIN,
        profile="default",
        raw_bytes=b"opaque",
        stored_at=T0,
    )
    assert bundle.raw_bytes == b"opaque"


def test_daily_projection_minimal() -> None:
    p = DailyProjection(date=date(2026, 5, 22), sources_synced=[Source.GARMIN])
    assert p.schema_version == 1
    assert p.activities_count == 0
