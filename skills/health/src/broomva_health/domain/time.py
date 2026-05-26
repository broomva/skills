"""Timezone-aware UTC time helpers — every domain timestamp goes through here."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

__all__ = ["UTC_EPOCH", "ensure_utc", "utc_now"]

UTC_EPOCH: Final[datetime] = datetime(1970, 1, 1, tzinfo=UTC)


def utc_now() -> datetime:
    """Return a timezone-aware UTC datetime for `now`.

    Use this everywhere instead of `datetime.now()` or `datetime.utcnow()` —
    the latter returns a naive datetime which silently breaks comparison
    against any timezone-aware datetime.
    """
    return datetime.now(tz=UTC)


def ensure_utc(value: datetime) -> datetime:
    """Coerce a datetime to UTC.

    - If naive: assume UTC and attach the UTC tzinfo (do not shift).
    - If aware: convert to UTC.

    The "assume UTC for naive" behavior is intentional — we receive ISO-8601
    strings from many sources and many of them omit the offset for UTC
    timestamps. If you have a known-local-timezone source, convert at the
    adapter boundary BEFORE handing the datetime to the domain.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
