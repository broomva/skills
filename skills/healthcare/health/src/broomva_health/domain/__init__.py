"""Domain layer — pure value objects and entities. No I/O."""

from __future__ import annotations

from broomva_health.domain.device import Device
from broomva_health.domain.errors import (
    AuthRequired,
    ConfigError,
    HealthError,
    MFANeeded,
    ProjectionError,
    RateLimited,
    RepositoryError,
    SourceUnavailable,
    SyncFailed,
)
from broomva_health.domain.metrics import METRIC_UNITS, MetricCode
from broomva_health.domain.results import (
    BackfillResult,
    DailyProjection,
    SourceStatus,
    SyncResult,
    TokenBundle,
)
from broomva_health.domain.samples import (
    CategorySample,
    CorrelationSample,
    QuantitySample,
)
from broomva_health.domain.source import Source
from broomva_health.domain.time import ensure_utc, utc_now
from broomva_health.domain.workout import Workout

__all__ = [
    "METRIC_UNITS",
    "AuthRequired",
    "BackfillResult",
    "CategorySample",
    "ConfigError",
    "CorrelationSample",
    "DailyProjection",
    "Device",
    "HealthError",
    "MFANeeded",
    "MetricCode",
    "ProjectionError",
    "QuantitySample",
    "RateLimited",
    "RepositoryError",
    "Source",
    "SourceStatus",
    "SourceUnavailable",
    "SyncFailed",
    "SyncResult",
    "TokenBundle",
    "Workout",
    "ensure_utc",
    "utc_now",
]
