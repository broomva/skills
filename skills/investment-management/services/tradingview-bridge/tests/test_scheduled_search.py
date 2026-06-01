"""Tests for the scheduled (UCB1-allocated) optimizer (scheduled_search.py)."""

from __future__ import annotations

import pytest

from tradingview_bridge.barsource import synthetic_bars
from tradingview_bridge.optimize.scheduled_search import ScheduledResult, scheduled_optimize
from tradingview_bridge.optimize.space import BUILTIN_SPACES, SMA_CROSSOVER_SPACE
from tradingview_bridge.optimize.types import ParamCandidate

_SPACES = list(BUILTIN_SPACES.values())  # 8 + 12 + 3 = 23 total candidates


def _run(**kw: object) -> ScheduledResult:
    return scheduled_optimize(
        _SPACES,
        synthetic_bars(500),
        symbol="AAPL",
        asset_class="stock",
        **kw,  # type: ignore[arg-type]
    )


def test_budget_allocated_and_human_gated() -> None:
    res = _run(budget=10)
    assert res.n_evaluated == 10
    assert sum(a.pulls for a in res.arms) == 10  # the allocation accounts for every eval
    assert res.requires_human_approval is True
    assert isinstance(res.best, ParamCandidate)
    assert res.best_family in BUILTIN_SPACES


def test_gap_is_train_minus_test() -> None:
    res = _run(budget=12)
    assert res.generalization_gap == pytest.approx(res.best.train_score - res.test_score)


def test_budget_exceeding_total_evaluates_everything() -> None:
    res = _run(budget=100)  # > 23 total candidates → exhausts all grids, no error
    assert res.n_evaluated == 23
    assert sum(a.pulls for a in res.arms) == 23


def test_deterministic_same_allocation_and_winner() -> None:
    a = _run(budget=10)
    b = _run(budget=10)
    assert a.best.strategy_name == b.best.strategy_name
    assert [(s.arm, s.pulls) for s in a.arms] == [(s.arm, s.pulls) for s in b.arms]
    assert a.test_score == b.test_score


def test_winner_is_best_by_train_across_arms() -> None:
    """The winner's train score is >= every arm's mean (it's the best individual find)."""
    res = _run(budget=15)
    assert all(res.best.train_score >= a.mean_reward - 1e-9 for a in res.arms)


def test_budget_zero_raises() -> None:
    with pytest.raises(ValueError, match="budget must be"):
        _run(budget=0)


def test_no_spaces_raises() -> None:
    with pytest.raises(ValueError, match="no spaces"):
        scheduled_optimize([], synthetic_bars(500), symbol="X", asset_class="stock", budget=5)


def test_too_few_bars_raises() -> None:
    with pytest.raises(ValueError, match="bars"):
        scheduled_optimize(
            [SMA_CROSSOVER_SPACE],
            synthetic_bars(12),
            symbol="X",
            asset_class="stock",
            budget=5,
            n_windows=4,
        )


def test_result_cannot_disable_human_gate() -> None:
    with pytest.raises(ValueError, match="human-gated"):
        ScheduledResult(
            symbol="X",
            budget=1,
            n_evaluated=1,
            arms=[],
            best=ParamCandidate(params={}, strategy_name="s", train_score=0.5),
            best_family="sma-crossover",
            test_score=0.5,
            generalization_gap=0.0,
            generalizes=True,
            rationale="x",
            requires_human_approval=False,
        )
