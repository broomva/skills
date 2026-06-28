"""Roster types — the promotion registry's entries and statuses.

The registry sits between the optimizer and the orchestrator. Each entry is a
(family, params) candidate carrying the out-of-sample evidence that justified
proposing it. Status encodes which human gate it has passed:

  proposed   — recorded by the optimizer (automatic); awaiting a human decision.
  active     — a human promoted it; the orchestrator now measures these params.
  rejected   — a human declined it.
  superseded — was active, replaced by a newer active entry of the same family.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

RosterStatus = Literal["proposed", "active", "rejected", "superseded"]


@dataclass(frozen=True)
class RosterEntry:
    """One (family, params) candidate in the promotion registry + its OOS evidence."""

    family: str
    params: dict[str, int]
    strategy_name: str
    status: RosterStatus
    train_score: float
    test_score: float
    generalization_gap: float
    note: str = ""
    entry_id: int | None = None  # assigned by the store on insert
    proposed_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    decided_at: datetime | None = None
