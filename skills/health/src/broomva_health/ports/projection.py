"""Projection port — Layer-3 view emitters."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol, runtime_checkable

from broomva_health.domain.results import DailyProjection

__all__ = ["ProjectionTarget"]


@runtime_checkable
class ProjectionTarget(Protocol):
    """Write a daily projection to a downstream consumer.

    Default adapter: `ObsidianDailyNoteProjection` writes Markdown +
    frontmatter to `~/broomva-vault/07-Health/YYYY-MM-DD.md`.

    Implementations MUST be idempotent on `date` — re-running for the same
    day either overwrites in-place (preserving any prose section the user
    added) or no-ops if the content hash is unchanged.
    """

    def emit_daily(self, day: date, projection: DailyProjection) -> Path: ...
