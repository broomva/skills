"""Sync use case — delegates to a source's `sync` for incremental pull.

The rate limiter is passed through to the source; the use case does NOT
pre-acquire because per-source adapters know their own endpoint shape
(e.g. backfill acquires once per day). Double-acquire here would
spuriously trip the limiter on the second call.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from broomva_health.domain.results import SyncResult
from broomva_health.ports.mfa import MFAProvider
from broomva_health.ports.rate_limiter import RateLimiter
from broomva_health.ports.repository import TraceRepository
from broomva_health.ports.source import TraceSource
from broomva_health.ports.token_store import TokenStore

__all__ = ["SyncSourceUseCase"]


@dataclass(frozen=True)
class SyncSourceUseCase:
    """Pull incremental samples + workouts from a source into the trace DB.

    Dependencies are injected at construction. Each call is a single
    rate-limited sync run; failures bubble as `HealthError` subtypes.
    Rate-limit acquisition is delegated to the source adapter.
    """

    source: TraceSource
    repo: TraceRepository
    token_store: TokenStore
    rate_limiter: RateLimiter
    mfa: MFAProvider

    def execute(
        self, *, since: datetime | None = None, profile: str = "default"
    ) -> SyncResult:
        return self.source.sync(
            repo=self.repo,
            token_store=self.token_store,
            rate_limiter=self.rate_limiter,
            since=since,
            profile=profile,
        )
