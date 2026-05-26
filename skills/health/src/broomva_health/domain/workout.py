"""Workout — a top-level activity container, HKWorkout-shaped."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from broomva_health.domain.device import Device
from broomva_health.domain.source import Source
from broomva_health.domain.time import ensure_utc, utc_now

__all__ = ["Workout"]


class Workout(BaseModel):
    """A workout / activity.

    Stored alongside per-second sample streams in the trace DB. The original
    FIT/TCX/GPX blob is referenced by `fit_blob_sha256` and lives on disk
    under `~/broomva/health/exports/<source>/fit/<sha256>.fit`.

    Idempotency key: `(source, activity_id)`.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra="forbid")

    source: Source
    activity_id: str = Field(..., min_length=1, description="Stable per-source activity ID")
    activity_type: str = Field(..., min_length=1, description="e.g. 'running', 'cycling', 'strength'")
    start_ts: datetime
    end_ts: datetime | None = Field(default=None, description="Derivable from start+duration if None")
    duration_s: int = Field(..., ge=0, description="Total moving + stationary seconds")
    distance_m: float | None = Field(default=None, ge=0)
    kcal: float | None = Field(default=None, ge=0)
    avg_hr: float | None = Field(default=None, ge=0, le=300)
    max_hr: float | None = Field(default=None, ge=0, le=300)
    training_effect: float | None = Field(default=None, ge=0, le=5)
    training_stress_score: float | None = Field(
        default=None, ge=0, description="Coggan TSS for synthesis"
    )
    device: Device | None = None
    fit_blob_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-fA-F0-9]{64}$",
        description="SHA-256 of the original FIT file blob, if exported",
    )
    raw_summary: dict[str, Any] = Field(default_factory=dict, description="Vendor-shaped summary")
    ingested_at: datetime = Field(default_factory=utc_now)

    _normalize_start = field_validator("start_ts", mode="after")(ensure_utc)
    _normalize_end = field_validator("end_ts", mode="after")(
        lambda v: ensure_utc(v) if v is not None else None
    )
    _normalize_ingested = field_validator("ingested_at", mode="after")(ensure_utc)
