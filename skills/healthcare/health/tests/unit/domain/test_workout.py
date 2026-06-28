"""Tests for domain/workout.py."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from broomva_health.domain.source import Source
from broomva_health.domain.workout import Workout

T0 = datetime(2026, 5, 22, 8, 0, tzinfo=UTC)


def test_workout_minimal() -> None:
    w = Workout(
        source=Source.GARMIN,
        activity_id="123456",
        activity_type="running",
        start_ts=T0,
        duration_s=2400,
    )
    assert w.activity_id == "123456"
    assert w.duration_s == 2400


def test_workout_rejects_negative_duration() -> None:
    with pytest.raises(ValidationError):
        Workout(
            source=Source.GARMIN,
            activity_id="1",
            activity_type="running",
            start_ts=T0,
            duration_s=-1,
        )


def test_workout_rejects_bad_sha256() -> None:
    with pytest.raises(ValidationError):
        Workout(
            source=Source.GARMIN,
            activity_id="1",
            activity_type="running",
            start_ts=T0,
            duration_s=60,
            fit_blob_sha256="not-a-real-sha256",
        )


def test_workout_accepts_valid_sha256() -> None:
    sha = "a" * 64
    w = Workout(
        source=Source.GARMIN,
        activity_id="1",
        activity_type="running",
        start_ts=T0,
        duration_s=60,
        fit_blob_sha256=sha,
    )
    assert w.fit_blob_sha256 == sha


def test_workout_is_frozen() -> None:
    w = Workout(
        source=Source.GARMIN,
        activity_id="1",
        activity_type="running",
        start_ts=T0,
        duration_s=60,
    )
    with pytest.raises(ValidationError):
        w.activity_type = "cycling"  # type: ignore[misc]
