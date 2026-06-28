"""Orchestrator — the L2 slow loop (agent-driven strategy research).

The control plane *executes*; the evaluation plane *measures*; this plane
*decides what to trust*. One tick: evaluate every strategy (walk-forward +
anti-overfit score) → record to the ledger → rank → recommend an allocation,
tempered by live-paper reality. The recommendation is **always human-gated** —
the orchestrator flags candidates; it never promotes to live capital itself.

  research.py — pure core: evaluate_all / rank / recommend (no I/O).
  runner.py   — AutoResearch: the stateful tick (ledger + live-reality check).
  types.py    — StrategyEvaluation / Leaderboard / AllocationRecommendation.
  cli.py      — the `research` entry point (run / leaderboard).
"""

from .research import DEFAULT_TRUST_THRESHOLD, evaluate_all, rank, recommend
from .runner import DEFAULT_LIVE_DECAY_TOLERANCE_PCT, AutoResearch, ResearchReport
from .types import (
    AllocationAction,
    AllocationRecommendation,
    Leaderboard,
    RankedStrategy,
    StrategyEvaluation,
)

__all__ = [
    "DEFAULT_LIVE_DECAY_TOLERANCE_PCT",
    "DEFAULT_TRUST_THRESHOLD",
    "AllocationAction",
    "AllocationRecommendation",
    "AutoResearch",
    "Leaderboard",
    "RankedStrategy",
    "ResearchReport",
    "StrategyEvaluation",
    "evaluate_all",
    "rank",
    "recommend",
]
