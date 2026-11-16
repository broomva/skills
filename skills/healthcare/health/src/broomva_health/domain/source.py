"""Trace source identifiers — one per integration."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Final

__all__ = ["IMPORT_ONLY_SOURCES", "Source", "single_stream"]


class Source(StrEnum):
    """A canonical, lower-cased identifier for a trace source.

    New sources are added by appending a member here and registering the
    corresponding adapter in `adapters/sources/_registry.py`. The string
    value is the on-disk identifier — never rename without a migration.
    """

    GARMIN = "garmin"
    APPLE_HEALTH = "apple_health"
    WHOOP = "whoop"
    OURA = "oura"
    CGM = "cgm"
    MANUAL = "manual"


#: Sources imported from a file that hold several producers (Apple Health holds
#: every app and device that wrote to it). Until a producer-aware reconciliation
#: projection exists, they are read only through ``backfill``, ``raw`` and
#: ``series --producer``. Every surface that assumes one stream per source
#: (sync, auth, context, daily-note, synthesis) skips them.
IMPORT_ONLY_SOURCES: Final[frozenset[Source]] = frozenset({Source.APPLE_HEALTH})


def single_stream(sources: Iterable[Source]) -> list[Source]:
    """The given sources minus the import-only ones, order kept."""
    return [s for s in sources if s not in IMPORT_ONLY_SOURCES]
