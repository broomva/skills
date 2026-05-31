"""research — the pure, deterministic core of the orchestrator.

No I/O. Given strategies + bars: evaluate each (walk-forward + score), rank by
trustworthiness, and recommend an allocation. Every function here is a pure
function of its inputs, so the same strategies + bars always produce the same
leaderboard and the same recommendation — the orchestration logic is fully
unit-testable and reproducible, independent of where the bars came from or
whether anything is persisted.

The stateful half (persisting evaluations, consulting live-paper reality) lives
in runner.py; this module is the brain, that one is the loop.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..evaluation.score import score_walk_forward
from ..evaluation.walk_forward import walk_forward
from ..schemas import AssetClass
from ..strategy.base import Strategy
from ..strategy.types import Bar
from .types import (
    AllocationAction,
    AllocationRecommendation,
    Leaderboard,
    RankedStrategy,
    StrategyEvaluation,
)

# Trust gate: a strategy's overall score must clear this to be a candidate for
# (human-approved) allocation. 0.6 is deliberately demanding — given that
# consistency + robustness are half the score, 0.6 means "consistently decent",
# not "spectacular once".
DEFAULT_TRUST_THRESHOLD = 0.6


def evaluate_all(
    strategies: Sequence[Strategy],
    bars: list[Bar],
    *,
    symbol: str,
    asset_class: AssetClass,
    n_windows: int = 5,
    periods_per_year: int = 252,
) -> list[StrategyEvaluation]:
    """Walk-forward + score every strategy over the same bars. Order preserved."""
    evaluations: list[StrategyEvaluation] = []
    for strat in strategies:
        wf = walk_forward(
            strat,
            bars,
            symbol=symbol,
            asset_class=asset_class,
            n_windows=n_windows,
            periods_per_year=periods_per_year,
        )
        evaluations.append(
            StrategyEvaluation(strategy=strat.name, walk_forward=wf, score=score_walk_forward(wf))
        )
    return evaluations


def rank(evaluations: Sequence[StrategyEvaluation], *, symbol: str) -> Leaderboard:
    """Rank by overall score (desc), tie-break consistency (desc) then name (asc).

    The tie-break is fully deterministic — equal-scored strategies never reorder
    run-to-run, so the leaderboard is reproducible.
    """
    ordered = sorted(
        evaluations,
        key=lambda e: (-e.score.overall, -float(e.walk_forward.consistency_pct), e.strategy),
    )
    ranked = [RankedStrategy(rank=i + 1, evaluation=e) for i, e in enumerate(ordered)]
    return Leaderboard(symbol=symbol, ranked=ranked)


def recommend(
    leaderboard: Leaderboard,
    *,
    trust_threshold: float = DEFAULT_TRUST_THRESHOLD,
) -> AllocationRecommendation:
    """Decide what to do with the best strategy — always human-gated.

    - ``promote_candidate``: best cleared the trust gate; a human may now allocate.
    - ``paper_forward``: promising but below the gate; keep paper-testing.
    - ``reject``: best is far below the gate; allocate to nothing.

    This is a pure function of the leaderboard. The runner may later *temper* a
    ``promote_candidate`` against live-paper reality, but it can only ever weaken
    a recommendation here, never strengthen it past the human gate.
    """
    best = leaderboard.best
    if best is None:
        return AllocationRecommendation(
            symbol=leaderboard.symbol,
            action="reject",
            strategy=None,
            confidence=0.0,
            trust_threshold=trust_threshold,
            rationale="no strategies evaluated — nothing to recommend",
        )

    overall = best.evaluation.score.overall
    name = best.strategy
    action: AllocationAction
    if overall >= trust_threshold:
        action = "promote_candidate"
        rationale = (
            f"{name} cleared the trust gate (score {overall:.3f} >= {trust_threshold:.2f}); "
            f"human approval required before any capital is allocated"
        )
    elif overall >= trust_threshold / 2:
        action = "paper_forward"
        rationale = (
            f"{name} is promising (score {overall:.3f}) but below the trust gate "
            f"({trust_threshold:.2f}) — keep it paper-forward and re-evaluate"
        )
    else:
        action = "reject"
        rationale = (
            f"best strategy {name} scores {overall:.3f}, far below the trust gate "
            f"({trust_threshold:.2f}) — no allocation"
        )
    return AllocationRecommendation(
        symbol=leaderboard.symbol,
        action=action,
        strategy=name,
        confidence=overall,
        trust_threshold=trust_threshold,
        rationale=rationale,
    )
