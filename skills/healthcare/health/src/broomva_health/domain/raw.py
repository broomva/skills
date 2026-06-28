"""RawDocument — a verbatim upstream response, losslessly preserved.

The structured sample types (`QuantitySample`, …) hold the curated, typed
subset we map from each source response. ``RawDocument`` holds the *whole*
response so the agent can reach any field we did not map. It is intentionally
schemaless in its ``payload`` — completeness over curation.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from broomva_health.domain.source import Source
from broomva_health.domain.time import ensure_utc

__all__ = ["RawDocument"]


class RawDocument(BaseModel):
    """One upstream response, verbatim, keyed by (source, calendar_date, endpoint)."""

    model_config = ConfigDict(frozen=True)

    source: Source
    calendar_date: date_cls = Field(..., description="Local day the document pertains to")
    endpoint: str = Field(..., min_length=1, description="Logical endpoint name (e.g. 'sleep')")
    fetched_at: datetime = Field(..., description="When the document was pulled (UTC)")
    payload: Any = Field(..., description="The raw response, verbatim (object or array)")

    def normalized_fetched_at(self) -> datetime:
        """``fetched_at`` coerced to UTC-aware (naive is treated as UTC)."""
        return ensure_utc(self.fetched_at)
