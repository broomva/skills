"""Trace source identifiers — one per integration."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["Source"]


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
