"""Source port — the integration interface every adapter implements.

To add a new source (Apple Health, Whoop, Oura, CGM):
1. Add the enum member to `domain/source.py`.
2. Implement this protocol in `adapters/sources/<name>.py`.
3. Register it in `adapters/sources/_registry.py`.
4. (Optional) Add a CLI passthrough subcommand for source-specific endpoints.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from broomva_health.domain.results import BackfillResult, SourceStatus, SyncResult
from broomva_health.domain.source import Source
from broomva_health.ports.mfa import MFAProvider
from broomva_health.ports.rate_limiter import RateLimiter
from broomva_health.ports.repository import TraceRepository
from broomva_health.ports.token_store import TokenStore

__all__ = ["TraceSource"]


@runtime_checkable
class TraceSource(Protocol):
    """A trace-producing integration.

    Operations:
    - `authenticate`  one-time login + token persistence (MFA via `mfa`).
    - `sync`          incremental pull since the last sample timestamp;
                      writes through `repo`. Returns a `SyncResult`.
    - `backfill`      bounded historical pull over `[start, end]`.
    - `status`        reflexive snapshot — token validity, last sync, rate
                      budget. Never raises; returns a populated `SourceStatus`.

    Every operation MUST acquire from `rate_limiter` before any network I/O.
    Every operation MUST persist updated tokens via `token_store` on success.
    """

    @property
    def name(self) -> Source: ...

    def authenticate(
        self,
        *,
        token_store: TokenStore,
        mfa: MFAProvider,
        email: str | None = None,
        password: str | None = None,
        profile: str = "default",
    ) -> None: ...

    def sync(
        self,
        *,
        repo: TraceRepository,
        token_store: TokenStore,
        rate_limiter: RateLimiter,
        since: datetime | None = None,
        profile: str = "default",
    ) -> SyncResult: ...

    def backfill(
        self,
        *,
        repo: TraceRepository,
        token_store: TokenStore,
        rate_limiter: RateLimiter,
        start: date,
        end: date,
        profile: str = "default",
    ) -> BackfillResult: ...

    def status(
        self, *, token_store: TokenStore, profile: str = "default"
    ) -> SourceStatus: ...
