"""Rate-limiter port — every source operation goes through one.

The default adapter is a token bucket with a per-source minimum interval
(15 minutes for Garmin; library maintainer guidance documented in
References/rate-limit-discipline.md).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["RateLimiter"]


@runtime_checkable
class RateLimiter(Protocol):
    """Bucket per `key` (typically the source name + endpoint).

    `acquire` blocks (or raises RateLimited if non-blocking is requested by
    the implementation) until a slot is available.

    `record_429` notifies the limiter to back off — the next `acquire` for
    the same key will wait at least the implementation's exponential-backoff
    minimum.
    """

    def acquire(self, key: str) -> None: ...

    def record_success(self, key: str) -> None: ...

    def record_429(self, key: str, retry_after_s: float | None = None) -> None: ...
