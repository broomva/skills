"""Operation results returned by use cases and adapters."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from broomva_health.domain.source import Source
from broomva_health.domain.time import ensure_utc

__all__ = [
    "BackfillResult",
    "DailyProjection",
    "SourceStatus",
    "SyncResult",
    "TokenBundle",
]


class _ResultBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SyncResult(_ResultBase):
    """Outcome of a single source sync run."""

    source: Source
    started_at: datetime
    finished_at: datetime
    samples_ingested: int = Field(..., ge=0)
    workouts_ingested: int = Field(..., ge=0)
    errors: list[str] = Field(default_factory=list)
    rate_limit_remaining_s: float | None = Field(
        default=None, ge=0, description="Seconds until the source's rate-limit budget resets"
    )

    _norm_started = field_validator("started_at", mode="after")(ensure_utc)
    _norm_finished = field_validator("finished_at", mode="after")(ensure_utc)

    @property
    def succeeded(self) -> bool:
        return len(self.errors) == 0

    @property
    def duration_s(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


class BackfillResult(_ResultBase):
    """Outcome of a historical backfill."""

    source: Source
    range_start: date
    range_end: date
    samples_ingested: int = Field(..., ge=0)
    workouts_ingested: int = Field(..., ge=0)
    errors: list[str] = Field(default_factory=list)


class SourceStatus(_ResultBase):
    """Reflexive snapshot of a source's current state — feeds `health status`."""

    source: Source
    last_sync: datetime | None = None
    last_error: str | None = None
    rate_limit_resets_at: datetime | None = None
    token_valid: bool = False
    token_expires_at: datetime | None = None

    _norm_sync = field_validator("last_sync", mode="after")(
        lambda v: ensure_utc(v) if v is not None else None
    )
    _norm_reset = field_validator("rate_limit_resets_at", mode="after")(
        lambda v: ensure_utc(v) if v is not None else None
    )
    _norm_expires_status = field_validator("token_expires_at", mode="after")(
        lambda v: ensure_utc(v) if v is not None else None
    )


class TokenBundle(_ResultBase):
    """Opaque token bytes + provenance, written to a TokenStore."""

    source: Source
    profile: str = Field(..., min_length=1)
    raw_bytes: bytes = Field(..., description="Whatever the source library hands us")
    stored_at: datetime
    expires_at: datetime | None = None

    _norm_stored = field_validator("stored_at", mode="after")(ensure_utc)
    _norm_expires = field_validator("expires_at", mode="after")(
        lambda v: ensure_utc(v) if v is not None else None
    )


class DailyProjection(_ResultBase):
    """Versioned daily-note frontmatter payload.

    Bumping `schema_version` requires updating downstream consumers
    (Obsidian Dataview queries, healthOS readers).
    """

    schema_version: int = Field(default=1, ge=1)
    date: date
    sources_synced: list[Source]
    hrv_overnight_ms: float | None = None
    hrv_cv_30d: float | None = None
    rhr_bpm: float | None = None
    sleep_hours: float | None = None
    sleep_score: float | None = None
    training_load_ctl: float | None = None
    training_load_atl: float | None = None
    training_load_tsb: float | None = None
    vo2_max: float | None = None
    body_battery: float | None = None
    activities_count: int = 0
    last_activity_type: str | None = None
    last_activity_distance_km: float | None = None
    extras: dict[str, Any] = Field(default_factory=dict)
