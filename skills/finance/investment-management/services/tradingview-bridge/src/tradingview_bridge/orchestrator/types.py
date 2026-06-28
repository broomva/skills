"""Orchestrator types — the structured outputs of the L2 slow loop.

A strategy's evidence (`StrategyEvaluation`) → its place in the ranking
(`RankedStrategy` / `Leaderboard`) → the orchestrator's decision
(`AllocationRecommendation`). The recommendation is **human-gated by
construction**: it can never be built to bypass human approval (see
`AllocationRecommendation.__post_init__`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..evaluation.ledger import SimLiveGap
from ..evaluation.score import StrategyScore
from ..evaluation.walk_forward import WalkForwardResult

# What the orchestrator recommends doing with a strategy. NOTE: there is no
# "go_live" action — promotion to real capital is always a separate human
# decision. The strongest action the orchestrator can take is flag a candidate.
AllocationAction = Literal["promote_candidate", "paper_forward", "reject"]


@dataclass(frozen=True)
class StrategyEvaluation:
    """One strategy's full evaluation evidence: the walk-forward + its score."""

    strategy: str
    walk_forward: WalkForwardResult
    score: StrategyScore

    @property
    def overall(self) -> float:
        return self.score.overall


@dataclass(frozen=True)
class RankedStrategy:
    """A strategy's place in the leaderboard (rank 1 = most trustworthy)."""

    rank: int
    evaluation: StrategyEvaluation

    @property
    def strategy(self) -> str:
        return self.evaluation.strategy

    @property
    def overall(self) -> float:
        return self.evaluation.score.overall


@dataclass(frozen=True)
class Leaderboard:
    """Strategies ranked by trustworthiness (overall score, descending)."""

    symbol: str
    ranked: list[RankedStrategy]

    @property
    def best(self) -> RankedStrategy | None:
        return self.ranked[0] if self.ranked else None


@dataclass(frozen=True)
class AllocationRecommendation:
    """The orchestrator's output. Human-gated by construction.

    ``requires_human_approval`` is always True — the orchestrator NEVER promotes a
    strategy to live capital on its own. The strongest action it can take is
    ``promote_candidate``: "this strategy cleared the trust gate; a human may now
    decide whether to allocate." Constructing one with the gate disabled raises —
    the human gate is a safety invariant, not a default a caller can flip.
    """

    symbol: str
    action: AllocationAction
    strategy: str | None
    confidence: float
    trust_threshold: float
    rationale: str
    live_reality: SimLiveGap | None = None
    requires_human_approval: bool = True

    def __post_init__(self) -> None:
        if self.requires_human_approval is not True:
            raise ValueError(
                "requires_human_approval must be True — promotion to live capital is "
                "human-gated; the orchestrator cannot emit a recommendation that bypasses it"
            )
