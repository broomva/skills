"""Repository port — the trace storage interface.

The default adapter is SQLite (`adapters/repositories/sqlite.py`).
SQLCipher upgrade is documented in `References/privacy-architecture.md`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.samples import CategorySample, CorrelationSample, QuantitySample
from broomva_health.domain.source import Source
from broomva_health.domain.workout import Workout

__all__ = ["TraceRepository"]


@runtime_checkable
class TraceRepository(Protocol):
    """Append-only trace storage.

    Invariants:
    - Upserts are idempotent on `(source, metric, start_ts)` for samples
      and `(source, activity_id)` for workouts.
    - `last_sample_ts` enables incremental sync — adapters use it to know
      where to resume from.
    - `query_*` methods are read-only and never raise on empty results.
    - `migrate()` is idempotent — safe to call on every startup.
    """

    # --- mutation ---
    def upsert_quantity(self, samples: list[QuantitySample]) -> int: ...

    def upsert_category(self, samples: list[CategorySample]) -> int: ...

    def upsert_correlation(self, samples: list[CorrelationSample]) -> int: ...

    def upsert_workout(self, workouts: list[Workout]) -> int: ...

    # --- query ---
    def last_sample_ts(self, source: Source, metric: MetricCode) -> datetime | None: ...

    def query_quantity(
        self,
        source: Source | None,
        metric: MetricCode,
        start: datetime,
        end: datetime,
    ) -> list[QuantitySample]: ...

    def query_workouts(
        self,
        source: Source | None,
        start: datetime,
        end: datetime,
    ) -> list[Workout]: ...

    # --- lifecycle ---
    def migrate(self) -> int: ...

    def close(self) -> None: ...
