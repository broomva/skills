"""Clock port — injectable for testability."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = ["Clock"]


@runtime_checkable
class Clock(Protocol):
    """Returns the current UTC datetime. Inject a FakeClock for tests."""

    def now(self) -> datetime: ...
