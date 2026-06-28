"""Clock adapters — `SystemClock` for production, `FakeClock` for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from broomva_health.domain.time import ensure_utc, utc_now

__all__ = ["FakeClock", "SystemClock"]


class SystemClock:
    """Production clock — wraps `utc_now()`."""

    def now(self) -> datetime:
        return utc_now()


@dataclass
class FakeClock:
    """Deterministic clock for tests.

    Construct with an initial UTC datetime; call `advance(seconds)` to move
    time forward. Naive datetimes are coerced to UTC.
    """

    initial: datetime
    _current: datetime = field(init=False)

    def __post_init__(self) -> None:
        self._current = ensure_utc(self.initial)

    def now(self) -> datetime:
        return self._current

    def advance(self, seconds: float) -> None:
        """Move the clock forward by `seconds`."""
        self._current = self._current + timedelta(seconds=seconds)

    def set(self, when: datetime) -> None:
        """Hard-set the clock to a specific UTC instant."""
        self._current = ensure_utc(when)
