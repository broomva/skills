"""OperatorState — filesystem-persisted operator state (P12 cross-context).

State lives in a JSON file so the operator can be killed and restarted (by a
cron, /loop, or persist iterate) and pick up exactly where it left off. This is
the Persist (P12) discipline: state in the filesystem, each tick a fresh context.

Two halt concepts:
  - soft halt (this tick only): the canary failed this tick. Auto-recovers the
    next tick the canary passes.
  - hard halt (sticky): the canary failed `halt_after_failures` consecutive
    times. Requires an explicit `operate reset` to clear — a human/operator must
    acknowledge before position management resumes.

Position management proceeds iff `last_canary_passed AND not hard_halted`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


@dataclass
class CanarySnapshot:
    """The result of the most recent canary, persisted for inspection."""

    passed: bool
    detail: str
    checks: dict[str, bool] = field(default_factory=dict)
    ts: str = field(default_factory=_now_iso)


@dataclass
class OperatorState:
    """Operator state. Serialized to JSON.

    Fields:
        tick_count: monotonically-increasing tick counter.
        last_canary_passed: did the most recent canary pass?
        consecutive_canary_failures: reset to 0 on any pass.
        hard_halted: sticky halt; only `reset()` clears it.
        halt_reason: human-readable reason for the current halt, if any.
        last_canary: snapshot of the most recent canary result.
        last_tick_ts: ISO timestamp of the most recent tick.
        started_at: ISO timestamp of first tick (process lineage marker).
    """

    tick_count: int = 0
    last_canary_passed: bool = False
    consecutive_canary_failures: int = 0
    hard_halted: bool = False
    halt_reason: str | None = None
    last_canary: CanarySnapshot | None = None
    last_tick_ts: str | None = None
    started_at: str | None = None

    @property
    def position_management_allowed(self) -> bool:
        """True iff it is safe to manage positions right now.

        The dogfood-as-precondition interlock in one expression.
        """
        return self.last_canary_passed and not self.hard_halted

    def record_canary(self, snapshot: CanarySnapshot, *, halt_after_failures: int) -> None:
        """Fold a canary result into the state, applying the interlock rules."""
        self.last_canary = snapshot
        self.last_canary_passed = snapshot.passed
        if snapshot.passed:
            self.consecutive_canary_failures = 0
            # A passing canary does NOT clear a hard halt — that needs reset().
            if not self.hard_halted:
                self.halt_reason = None
        else:
            self.consecutive_canary_failures += 1
            if self.consecutive_canary_failures >= halt_after_failures:
                self.hard_halted = True
                self.halt_reason = (
                    f"hard halt: {self.consecutive_canary_failures} consecutive "
                    f"canary failures (>= {halt_after_failures}). Run `operate reset`."
                )
            else:
                self.halt_reason = (
                    f"soft halt: canary failed "
                    f"({self.consecutive_canary_failures}/{halt_after_failures}) — "
                    f"{snapshot.detail}"
                )

    def reset(self) -> None:
        """Clear the hard halt and failure counter. Operator-acknowledged recovery."""
        self.hard_halted = False
        self.halt_reason = None
        self.consecutive_canary_failures = 0

    # ---- persistence ----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OperatorState:
        canary = d.get("last_canary")
        snapshot = CanarySnapshot(**canary) if isinstance(canary, dict) else None
        return cls(
            tick_count=d.get("tick_count", 0),
            last_canary_passed=d.get("last_canary_passed", False),
            consecutive_canary_failures=d.get("consecutive_canary_failures", 0),
            hard_halted=d.get("hard_halted", False),
            halt_reason=d.get("halt_reason"),
            last_canary=snapshot,
            last_tick_ts=d.get("last_tick_ts"),
            started_at=d.get("started_at"),
        )

    @classmethod
    def load(cls, path: Path) -> OperatorState:
        """Load state from JSON, or return a fresh state if the file is absent."""
        if not path.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError, ValueError):
            # Corrupt state file — start fresh rather than crash the operator.
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
