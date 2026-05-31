"""Tests for the EGRI optimization loop (egri.py) — the honest train/test core."""

from __future__ import annotations

import pytest

from tradingview_bridge.optimize.egri import optimize_walk_forward
from tradingview_bridge.optimize.space import SMA_CROSSOVER_SPACE, ParamSpace
from tradingview_bridge.optimize.types import OptimizationResult, ParamCandidate
from tradingview_bridge.orchestrator.cli import synthetic_bars
from tradingview_bridge.strategy.base import Strategy
from tradingview_bridge.strategy.library import SMACrossover


def _opt(**kw: object) -> OptimizationResult:
    bars = synthetic_bars(500)
    return optimize_walk_forward(
        SMA_CROSSOVER_SPACE, bars, symbol="AAPL", asset_class="stock", **kw
    )  # type: ignore[arg-type]


def test_ranks_by_train_desc_and_best_is_first() -> None:
    res = _opt()
    scores = [c.train_score for c in res.ranked]
    assert scores == sorted(scores, reverse=True)
    assert res.best is res.ranked[0]
    assert res.n_candidates == len(res.ranked) == 8


def test_gap_is_train_minus_test() -> None:
    res = _opt()
    assert res.generalization_gap == pytest.approx(res.best.train_score - res.test_score)


def test_split_index_matches_train_frac() -> None:
    assert _opt(train_frac=0.6).split_index == 300


def test_selection_uses_train_only() -> None:
    """The train ranking must be INVARIANT to the test segment — the proof that
    selection never peeked at the holdout. Same train bars + different test bars
    → identical train ranking and scores."""
    base = synthetic_bars(500)
    split = int(500 * 0.7)
    swapped = base[:split] + list(reversed(base[split:]))  # same train, different test
    a = optimize_walk_forward(SMA_CROSSOVER_SPACE, base, symbol="X", asset_class="stock")
    b = optimize_walk_forward(SMA_CROSSOVER_SPACE, swapped, symbol="X", asset_class="stock")
    assert [c.strategy_name for c in a.ranked] == [c.strategy_name for c in b.ranked]
    assert [round(c.train_score, 9) for c in a.ranked] == [
        round(c.train_score, 9) for c in b.ranked
    ]


def test_generalizes_true_when_thresholds_lax() -> None:
    assert _opt(min_test_score=0.0, max_gap=10.0).generalizes is True


def test_overfit_caught_by_impossible_max_gap() -> None:
    """An impossible max_gap forces a non-generalize verdict regardless of how
    dazzling the train score is — the holdout rejecting a curve-fit winner."""
    res = _opt(min_test_score=0.0, max_gap=-1.0)  # gap <= -1 needs test >= train+1 (impossible)
    assert res.generalizes is False
    assert "OVERFIT" in res.rationale or "does NOT generalize" in res.rationale


def test_weak_oos_caught_by_impossible_floor() -> None:
    res = _opt(min_test_score=1.5, max_gap=10.0)  # scores <= 1, so floor never met
    assert res.generalizes is False
    assert "does NOT generalize" in res.rationale


def test_train_frac_out_of_range_raises() -> None:
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="train_frac"):
            _opt(train_frac=bad)


def test_too_few_bars_raises() -> None:
    bars = synthetic_bars(12)  # split 8/4 at frac 0.7 → test segment too small for 4 windows
    with pytest.raises(ValueError, match="bars"):
        optimize_walk_forward(
            SMA_CROSSOVER_SPACE, bars, symbol="X", asset_class="stock", n_windows=4
        )


def test_empty_space_raises() -> None:
    def _factory(p: dict[str, int]) -> Strategy:
        return SMACrossover(5, 20)

    impossible = ParamSpace(
        family="x", factory=_factory, grid={"a": [1, 2]}, constraint=lambda p: False
    )
    with pytest.raises(ValueError, match="no valid candidates"):
        optimize_walk_forward(impossible, synthetic_bars(500), symbol="X", asset_class="stock")


def test_result_cannot_disable_human_gate() -> None:
    with pytest.raises(ValueError, match="human-gated"):
        OptimizationResult(
            family="x",
            symbol="X",
            n_candidates=1,
            train_frac=0.7,
            split_index=10,
            ranked=[],
            best=ParamCandidate(params={}, strategy_name="s", train_score=0.5),
            test_score=0.5,
            generalization_gap=0.0,
            generalizes=True,
            min_test_score=0.5,
            max_gap=0.25,
            rationale="x",
            requires_human_approval=False,
        )
