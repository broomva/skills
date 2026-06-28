"""Optimization types — the structured output of the EGRI param-search.

The honesty lives in the separation: `ranked` is ordered by TRAIN score (the only
thing selection is allowed to see), while `test_score` and `generalization_gap`
come from a held-out segment the search never touched. `generalizes` is the
human-gated promotion verdict — and like the orchestrator's recommendation, an
OptimizationResult cannot be constructed with the human gate disabled.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParamCandidate:
    """One evaluated param-set.

    ``train_score`` is the in-sample walk-forward score that selection ranks on.
    The test score is deliberately NOT stored here — only the chosen winner is
    ever scored out-of-sample, so a candidate object can never carry a number that
    would tempt test-set selection.
    """

    params: dict[str, int]
    strategy_name: str
    train_score: float


@dataclass(frozen=True)
class OptimizationResult:
    """The result of a train/test param-optimization.

    Selection is on ``ranked`` (train only). The promotion-relevant numbers are the
    winner's ``test_score`` (out-of-sample, computed exactly once) and the
    ``generalization_gap`` (train - test). A large positive gap means the in-sample
    winner overfit and did not hold up.
    """

    family: str
    symbol: str
    n_candidates: int
    train_frac: float
    split_index: int
    ranked: list[ParamCandidate]
    best: ParamCandidate
    test_score: float
    generalization_gap: float
    generalizes: bool
    min_test_score: float
    max_gap: float
    rationale: str
    requires_human_approval: bool = True

    def __post_init__(self) -> None:
        if self.requires_human_approval is not True:
            raise ValueError(
                "requires_human_approval must be True — optimized params are a "
                "recommendation; promotion to the live roster or capital is human-gated"
            )
