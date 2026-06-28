"""Backfill use case — delegates to a source's `backfill` for historical pull.

As with the Sync use case, rate-limit acquisition lives in the source
adapter (each day in the range needs its own acquire to honor the
minimum interval between hits).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from broomva_health.domain.results import BackfillResult
from broomva_health.ports.mfa import MFAProvider
from broomva_health.ports.rate_limiter import RateLimiter
from broomva_health.ports.repository import TraceRepository
from broomva_health.ports.source import TraceSource
from broomva_health.ports.token_store import TokenStore

__all__ = ["BackfillSourceUseCase"]


@dataclass(frozen=True)
class BackfillSourceUseCase:
    """Run a historical backfill against a source.

    Prefer per-source bulk-export endpoints (e.g. Garmin's GDPR
    'Export Your Data' tarball) over this for cold-start ingest. This
    use case is the API-driven fallback when bulk-export isn't available.
    """

    source: TraceSource
    repo: TraceRepository
    token_store: TokenStore
    rate_limiter: RateLimiter
    mfa: MFAProvider

    def execute(
        self, *, start: date, end: date, profile: str = "default"
    ) -> BackfillResult:
        if end < start:
            raise ValueError(f"end ({end}) precedes start ({start})")
        return self.source.backfill(
            repo=self.repo,
            token_store=self.token_store,
            rate_limiter=self.rate_limiter,
            start=start,
            end=end,
            profile=profile,
        )
