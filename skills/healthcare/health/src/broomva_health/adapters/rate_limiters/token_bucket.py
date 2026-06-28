"""TokenBucketRateLimiter — per-key minimum-interval + 429 cooldown.

Non-blocking: `acquire` raises `RateLimited` immediately rather than
sleeping. The CLI layer decides whether to surface the error or sleep
& retry — keeping this adapter free of I/O makes it deterministic in
unit tests.

State persistence: when constructed with a `state_path`, the limiter
serializes its `_last_acquire_at` and `_cooldown_until` maps to JSON
after every mutation. This closes the cross-process-restart gap that
would otherwise let a cron firing every 60s bypass the 15-min poll
floor — each fresh process would otherwise start with an empty bucket.

State file shape (versioned for forward compat):

    {
      "version": 1,
      "last_acquire_at": {"garmin:sync": "2026-05-23T04:51:34+00:00"},
      "cooldown_until":  {"garmin:sync": "2026-05-23T05:06:34+00:00"}
    }
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from broomva_health.domain.errors import RateLimited
from broomva_health.domain.time import ensure_utc
from broomva_health.ports.clock import Clock

__all__ = ["TokenBucketRateLimiter"]

logger = logging.getLogger(__name__)

_STATE_VERSION = 1


class TokenBucketRateLimiter:
    """Simple token-bucket-with-cooldown limiter.

    - `min_interval_s` enforces a per-key minimum spacing between acquires.
    - `on_429_backoff_s` is the default cooldown applied when the limiter is
      told the upstream returned 429.
    - `state_path` (optional) persists `_last_acquire_at` + `_cooldown_until`
      to disk so cross-process invocations honor the interval. If omitted
      (or set to None), state lives only in-memory (acceptable for tests
      and one-shot CLI use, but not for cron / shell-loop scenarios).
    - All time comes from the injected `Clock` so tests can drive a FakeClock.
    """

    def __init__(
        self,
        *,
        min_interval_s: float,
        clock: Clock,
        on_429_backoff_s: float = 1800.0,
        state_path: Path | None = None,
    ) -> None:
        if min_interval_s < 0:
            raise ValueError(f"min_interval_s must be >= 0, got {min_interval_s}")
        if on_429_backoff_s < 0:
            raise ValueError(f"on_429_backoff_s must be >= 0, got {on_429_backoff_s}")

        self._min_interval = timedelta(seconds=min_interval_s)
        self._on_429 = timedelta(seconds=on_429_backoff_s)
        self._clock = clock
        self._state_path = state_path
        self._last_acquire_at: dict[str, datetime] = {}
        self._cooldown_until: dict[str, datetime] = {}
        if state_path is not None:
            self._load()

    # --- public API ---------------------------------------------------

    def acquire(self, key: str) -> None:
        now = self._clock.now()

        cooldown = self._cooldown_until.get(key)
        if cooldown is not None and cooldown > now:
            remaining = (cooldown - now).total_seconds()
            raise RateLimited(
                f"rate-limited: cooldown active for {key!r}",
                retry_after_s=remaining,
            )

        last = self._last_acquire_at.get(key)
        if last is not None:
            elapsed = now - last
            if elapsed < self._min_interval:
                remaining = (self._min_interval - elapsed).total_seconds()
                raise RateLimited(
                    f"rate-limited: min_interval not yet elapsed for {key!r}",
                    retry_after_s=remaining,
                )

        self._last_acquire_at[key] = now
        self._persist()

    def record_success(self, key: str) -> None:
        """Clear any cooldown after a successful call.

        Does NOT reset `last_acquire_at` — that timestamp is what guarantees
        the next acquire respects `min_interval_s`.
        """
        if key in self._cooldown_until:
            del self._cooldown_until[key]
            self._persist()

    def record_429(self, key: str, retry_after_s: float | None = None) -> None:
        backoff = (
            timedelta(seconds=retry_after_s) if retry_after_s is not None else self._on_429
        )
        self._cooldown_until[key] = self._clock.now() + backoff
        logger.warning(
            "rate_limiter: %s in cooldown until %s",
            key,
            self._cooldown_until[key].isoformat(),
        )
        self._persist()

    def snapshot(self) -> dict[str, dict[str, str]]:
        """Return a serializable view of current state (for `health status`)."""
        return {
            "last_acquire_at": {k: v.isoformat() for k, v in self._last_acquire_at.items()},
            "cooldown_until": {k: v.isoformat() for k, v in self._cooldown_until.items()},
        }

    # --- persistence helpers -----------------------------------------

    def _persist(self) -> None:
        if self._state_path is None:
            return
        try:
            payload = {
                "version": _STATE_VERSION,
                "last_acquire_at": {
                    k: v.isoformat() for k, v in self._last_acquire_at.items()
                },
                "cooldown_until": {
                    k: v.isoformat() for k, v in self._cooldown_until.items()
                },
            }
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write — tmp + replace
            fd, tmp = tempfile.mkstemp(
                prefix=".token_bucket.", suffix=".tmp", dir=str(self._state_path.parent)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, sort_keys=True, separators=(",", ":"))
                os.replace(tmp, self._state_path)
            except Exception:
                Path(tmp).unlink(missing_ok=True)
                raise
            try:
                os.chmod(self._state_path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            # Don't fail the request because we couldn't persist — log and continue.
            logger.warning("token_bucket: persist to %s failed: %s", self._state_path, exc)

    def _load(self) -> None:
        path = self._state_path
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("token_bucket: failed to load state from %s: %s", path, exc)
            return
        if not isinstance(data, dict) or data.get("version") != _STATE_VERSION:
            logger.warning(
                "token_bucket: state file %s has unknown version; ignoring", path
            )
            return
        try:
            self._last_acquire_at = {
                k: ensure_utc(datetime.fromisoformat(v))
                for k, v in (data.get("last_acquire_at") or {}).items()
            }
            self._cooldown_until = {
                k: ensure_utc(datetime.fromisoformat(v))
                for k, v in (data.get("cooldown_until") or {}).items()
            }
        except (TypeError, ValueError) as exc:
            logger.warning(
                "token_bucket: state file %s has malformed entries; ignoring: %s", path, exc
            )
            self._last_acquire_at = {}
            self._cooldown_until = {}
