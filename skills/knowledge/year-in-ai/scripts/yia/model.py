"""Core types shared by every reader and by the aggregator.

Two ideas carry the whole design:

``Event``
    A single timestamped thing that happened in an AI session, normalised
    across vendors.  Readers yield these lazily; the aggregator folds them
    one at a time so a 20 GB corpus never lands in memory.

``SourceReport``
    What a reader found *and did not find*.  Absence is the resting state of
    a local store, so it cannot also be the error signal: a reader that finds
    nothing must say so positively, with a reason, and the cards that depend
    on it are dropped rather than rendered as zero.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------

#: Event kinds. ``meta`` carries session-level facts (cwd, branch, model) that
#: are not themselves messages.
KINDS = ("user", "assistant", "tool", "meta")


@dataclass(slots=True)
class Event:
    """One normalised occurrence in an AI session."""

    ts: _dt.datetime
    source: str
    kind: str
    session: str | None = None
    project: str | None = None
    branch: str | None = None
    model: str | None = None
    tool: str | None = None
    skill: str | None = None
    mcp_tool: str | None = None
    #: Token counts, vendor-normalised: input/output/cache_read/cache_write.
    tokens: dict[str, int] | None = None
    #: Only ever populated for user prompts, and truncated by the reader.
    text: str | None = None
    #: False when the turn came from an SDK, ``exec`` run or subagent rather
    #: than a person at a terminal. Cards about what the operator *said* read
    #: only interactive turns; counts and rankings read everything.
    interactive: bool = True

    def __post_init__(self) -> None:
        if self.kind not in KINDS:  # pragma: no cover - guards programmer error
            raise ValueError(f"unknown event kind: {self.kind!r}")


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------


@dataclass(slots=True)
class SourceReport:
    """What one store contributed, including the case where it contributed nothing.

    ``available`` is never inferred from ``records == 0``.  A store that exists
    but is empty is still available (and says so with ``records=0``); a store
    that is not on this machine is unavailable and carries a ``reason``.
    """

    name: str
    available: bool
    reason: str | None = None
    root: str | None = None
    files: int = 0
    records: int = 0
    first: _dt.datetime | None = None
    last: _dt.datetime | None = None

    def observe(self, ts: _dt.datetime) -> None:
        """Widen the observed span to include ``ts``."""
        self.records += 1
        if self.first is None or ts < self.first:
            self.first = ts
        if self.last is None or ts > self.last:
            self.last = ts

    @property
    def span_days(self) -> int | None:
        if self.first is None or self.last is None:
            return None
        return (self.last - self.first).days

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.name,
            "available": self.available,
            "reason": self.reason,
            "root": self.root,
            "files": self.files,
            "records": self.records,
            "first": self.first.isoformat() if self.first else None,
            "last": self.last.isoformat() if self.last else None,
            "span_days": self.span_days,
        }


@dataclass(slots=True)
class Window:
    """The half-open time window a run covers, plus what was actually observed.

    ``requested`` is what the operator asked for; ``observed`` is what the
    corpus could answer.  Reporting only the first would let a skill titled
    "Your Year in AI" imply twelve months of evidence it does not have.
    """

    start: _dt.datetime | None = None
    end: _dt.datetime | None = None
    label: str = "all time"
    observed_first: _dt.datetime | None = None
    observed_last: _dt.datetime | None = None

    def contains(self, ts: _dt.datetime) -> bool:
        if self.start is not None and ts < self.start:
            return False
        if self.end is not None and ts >= self.end:
            return False
        return True

    def observe(self, ts: _dt.datetime) -> None:
        if self.observed_first is None or ts < self.observed_first:
            self.observed_first = ts
        if self.observed_last is None or ts > self.observed_last:
            self.observed_last = ts

    @property
    def observed_days(self) -> int | None:
        if self.observed_first is None or self.observed_last is None:
            return None
        return (self.observed_last - self.observed_first).days + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "requested_start": self.start.isoformat() if self.start else None,
            "requested_end": self.end.isoformat() if self.end else None,
            "observed_first": self.observed_first.isoformat() if self.observed_first else None,
            "observed_last": self.observed_last.isoformat() if self.observed_last else None,
            "observed_days": self.observed_days,
        }


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Provenance:
    """Anchors every claim in the payload to something on disk.

    The narrative stage may only assert things that appear here.  This is the
    guard against the failure mode that sank Spotify's own 2024 edition:
    generated prose that reads plausibly and cites nothing.
    """

    entries: dict[str, dict[str, Any]] = field(default_factory=dict)

    def anchor(self, claim: str, **anchor: Any) -> str:
        """Record where ``claim`` came from; returns the claim id."""
        self.entries[claim] = {k: v for k, v in anchor.items() if v is not None}
        return claim

    def to_dict(self) -> dict[str, Any]:
        return dict(self.entries)
