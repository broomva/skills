"""Tests for the pure orchestrator core (research.py) — no I/O."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradingview_bridge.evaluation.score import StrategyScore
from tradingview_bridge.evaluation.walk_forward import WalkForwardResult
from tradingview_bridge.orchestrator.cli import synthetic_bars
from tradingview_bridge.orchestrator.research import evaluate_all, rank, recommend
from tradingview_bridge.orchestrator.types import (
    AllocationRecommendation,
    Leaderboard,
    RankedStrategy,
    StrategyEvaluation,
)
from tradingview_bridge.strategy.backtest_runner import BacktestResult
from tradingview_bridge.strategy.library import DonchianBreakout, RSIMeanReversion, SMACrossover

# --- factory helpers: build a minimal valid evaluation with a chosen score ---


def _wf(name: str, consistency: float) -> WalkForwardResult:
    bt = BacktestResult(
        strategy=name,
        symbol="X",
        n_bars=10,
        n_trades=2,
        total_return_pct=Decimal("5"),
        sharpe=1.0,
        max_drawdown_pct=Decimal("3"),
        win_rate_pct=Decimal("50"),
        equity_curve=[Decimal(100)],
        trades=[],
    )
    return WalkForwardResult(
        strategy=name,
        symbol="X",
        n_windows=5,
        windows=[],
        full=bt,
        mean_return_pct=Decimal("5"),
        return_std=2.0,
        mean_sharpe=1.0,
        consistency_pct=Decimal(str(consistency)),
        worst_window_return_pct=Decimal("-1"),
        best_window_return_pct=Decimal("8"),
    )


def _score(name: str, overall: float) -> StrategyScore:
    return StrategyScore(
        strategy=name,
        risk_adjusted=overall,
        consistency=overall,
        robustness=overall,
        drawdown_safety=overall,
        overall=overall,
        rationale="test",
    )


def _eval(name: str, overall: float, consistency: float = 50.0) -> StrategyEvaluation:
    return StrategyEvaluation(
        strategy=name, walk_forward=_wf(name, consistency), score=_score(name, overall)
    )


def _board(evals: list[StrategyEvaluation]) -> Leaderboard:
    return rank(evals, symbol="X")


# --- evaluate_all ---------------------------------------------------------


def test_evaluate_all_one_per_strategy_order_preserved() -> None:
    bars = synthetic_bars(120)
    roster = [SMACrossover(5, 20), RSIMeanReversion(14), DonchianBreakout(20)]
    evals = evaluate_all(roster, bars, symbol="AAPL", asset_class="stock", n_windows=4)
    assert [e.strategy for e in evals] == [s.name for s in roster]
    assert all(0.0 <= e.score.overall <= 1.0 for e in evals)


def test_evaluate_all_is_deterministic() -> None:
    bars = synthetic_bars(120)
    roster = [SMACrossover(5, 20)]
    a = evaluate_all(roster, bars, symbol="AAPL", asset_class="stock", n_windows=4)
    b = evaluate_all(roster, bars, symbol="AAPL", asset_class="stock", n_windows=4)
    assert a[0].score.overall == b[0].score.overall
    assert a[0].walk_forward.mean_return_pct == b[0].walk_forward.mean_return_pct


# --- rank -----------------------------------------------------------------


def test_rank_orders_by_overall_desc() -> None:
    board = _board([_eval("a", 0.3), _eval("b", 0.9), _eval("c", 0.6)])
    assert [r.strategy for r in board.ranked] == ["b", "c", "a"]
    assert [r.rank for r in board.ranked] == [1, 2, 3]
    assert board.best is not None
    assert board.best.overall == 0.9


def test_rank_tiebreak_consistency_then_name() -> None:
    # equal overall → higher consistency wins; equal both → name ascending
    board = _board(
        [
            _eval("zebra", 0.5, consistency=80.0),
            _eval("alpha", 0.5, consistency=80.0),
            _eval("mid", 0.5, consistency=40.0),
        ]
    )
    assert [r.strategy for r in board.ranked] == ["alpha", "zebra", "mid"]


def test_rank_empty_leaderboard_has_no_best() -> None:
    board = _board([])
    assert board.ranked == []
    assert board.best is None


# --- recommend (the gate logic) -------------------------------------------


def test_recommend_promote_above_gate() -> None:
    rec = recommend(_board([_eval("good", 0.75)]), trust_threshold=0.6)
    assert rec.action == "promote_candidate"
    assert rec.strategy == "good"
    assert rec.confidence == 0.75
    assert rec.requires_human_approval is True


def test_recommend_paper_forward_midrange() -> None:
    rec = recommend(_board([_eval("mid", 0.4)]), trust_threshold=0.6)
    assert rec.action == "paper_forward"  # 0.4 >= 0.3 (half the gate)
    assert rec.strategy == "mid"


def test_recommend_reject_below_half_gate() -> None:
    rec = recommend(_board([_eval("bad", 0.2)]), trust_threshold=0.6)
    assert rec.action == "reject"  # 0.2 < 0.3
    assert rec.strategy == "bad"


def test_recommend_empty_is_reject_with_no_strategy() -> None:
    rec = recommend(_board([]), trust_threshold=0.6)
    assert rec.action == "reject"
    assert rec.strategy is None
    assert rec.confidence == 0.0


@pytest.mark.parametrize("overall", [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
def test_recommend_is_always_human_gated_and_never_go_live(overall: float) -> None:
    rec = recommend(_board([_eval("s", overall)]), trust_threshold=0.6)
    assert rec.requires_human_approval is True
    assert rec.action in {"promote_candidate", "paper_forward", "reject"}  # no go-live, ever


# --- the human-gate safety invariant --------------------------------------


def test_recommendation_cannot_disable_human_gate() -> None:
    """The orchestrator must not be able to emit a recommendation that bypasses
    human approval — constructing one with the gate off raises."""
    with pytest.raises(ValueError, match="human-gated"):
        AllocationRecommendation(
            symbol="X",
            action="promote_candidate",
            strategy="s",
            confidence=0.9,
            trust_threshold=0.6,
            rationale="attempting to bypass the gate",
            requires_human_approval=False,
        )


def test_ranked_strategy_convenience_properties() -> None:
    ev = _eval("s", 0.7, consistency=60.0)
    rs = RankedStrategy(rank=1, evaluation=ev)
    assert rs.strategy == "s"
    assert rs.overall == 0.7
