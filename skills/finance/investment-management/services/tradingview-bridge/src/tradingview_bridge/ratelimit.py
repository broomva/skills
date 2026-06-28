"""Rate limiter — in-memory token bucket per source IP, 60-second rolling window.

Pure stdlib; no Redis, no external store. Acceptable for a single-instance
service; PR 3+ may swap for a Redis-backed limiter when running multi-replica.

The limiter is constructed once (in `app.py` lifespan) and used by a FastAPI
middleware that runs BEFORE the webhook handler. Excess requests get 429
without consuming the secret/schema validation budget.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock

import structlog

log = structlog.get_logger("tradingview_bridge.ratelimit")


class TokenBucketLimiter:
    """Sliding 60-second window per source IP. Thread-safe via a single Lock.

    Stores a deque of timestamps per IP; on each check, evicts timestamps
    older than 60s and counts what's left. If count > limit, reject.
    """

    def __init__(self, limit_per_minute: int) -> None:
        if limit_per_minute < 1:
            raise ValueError("limit_per_minute must be >= 1")
        self._limit = limit_per_minute
        self._window_seconds = 60.0
        self._buckets: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, ip: str) -> bool:
        """True if the request is allowed; False if rate-limited.

        Side effect: when True, records the current timestamp in the IP's bucket.
        """
        now = time.monotonic()
        cutoff = now - self._window_seconds

        with self._lock:
            bucket = self._buckets.setdefault(ip, deque())
            # Evict old timestamps
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                log.warning(
                    "rate_limit_exceeded",
                    ip=ip,
                    limit_per_minute=self._limit,
                    current_count=len(bucket),
                )
                return False
            bucket.append(now)
            return True

    def reset(self, ip: str | None = None) -> None:
        """Reset the bucket for one IP, or all IPs if ip is None.

        Test fixtures call reset() between cases.
        """
        with self._lock:
            if ip is None:
                self._buckets.clear()
            else:
                self._buckets.pop(ip, None)

    @property
    def limit(self) -> int:
        return self._limit
