"""Trustworthiness score tests — including the anti-overfit property."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradingview_bridge.evaluation.score import DEFAULT_WEIGHTS, score_walk_forward
from tradingview_bridge.evaluation.walk_forward import WalkForwardResult, WindowMetrics
from tradingview_bridge.strategy.backtest_runner import BacktestResult


def _wf(
    *, sharpe: float, consistency: float, dispersion: float, worst_dd: float
) -> WalkForwardResult:
    windows = [
        WindowMetrics(
            index=0,
            start_index=0,
            end_index=1,
            return_pct=Decimal("1"),
            sharpe=sharpe,
            max_drawdown_pct=Decimal(str(worst_dd)),
        )
    ]
    full = BacktestResult(
        strategy="s",
        symbol="T",
        n_bars=1,
        n_trades=0,
        total_return_pct=Decimal(0),
        sharpe=sharpe,
        max_drawdown_pct=Decimal(str(worst_dd)),
        win_rate_pct=Decimal(0),
    )
    return WalkForwardResult(
        strategy="s",
        symbol="T",
        n_windows=1,
        windows=windows,
        full=full,
        mean_return_pct=Decimal(0),
        return_std=dispersion,
        mean_sharpe=sharpe,
        consistency_pct=Decimal(str(consistency)),
        worst_window_return_pct=Decimal(0),
        best_window_return_pct=Decimal(0),
    )


def test_all_components_in_unit_range() -> None:
    s = score_walk_forward(_wf(sharpe=1.0, consistency=60, dispersion=10, worst_dd=10))
    for v in (s.risk_adjusted, s.consistency, s.robustness, s.drawdown_safety, s.overall):
        assert 0.0 <= v <= 1.0


def test_excellent_strategy_scores_high() -> None:
    s = score_walk_forward(_wf(sharpe=2.5, consistency=100, dispersion=2, worst_dd=3))
    assert s.overall > 0.85


def test_anti_overfit_inconsistent_strategy_scores_low() -> None:
    """High Sharpe but inconsistent + high dispersion must NOT score well —
    the whole point of the scoreboard."""
    seductive = _wf(sharpe=5.0, consistency=20, dispersion=40, worst_dd=25)
    s = score_walk_forward(seductive)
    # risk_adjusted saturates at 1.0, but consistency+robustness (half the weight)
    # collapse → overall stays mediocre at best.
    assert s.consistency < 0.3
    assert s.robustness < 0.2
    assert s.overall < 0.55


def test_consistency_beats_lucky_sharpe() -> None:
    consistent = score_walk_forward(_wf(sharpe=1.2, consistency=100, dispersion=3, worst_dd=5))
    lucky = score_walk_forward(_wf(sharpe=3.0, consistency=40, dispersion=35, worst_dd=20))
    assert consistent.overall > lucky.overall


def test_rationale_is_populated() -> None:
    s = score_walk_forward(_wf(sharpe=1.5, consistency=80, dispersion=8, worst_dd=10))
    assert "sharpe" in s.rationale
    assert "consistency" in s.rationale


def test_zero_reference_rejected() -> None:
    """A 0 reference would divide-by-zero — reject it up front."""
    wf = _wf(sharpe=1.0, consistency=60, dispersion=10, worst_dd=10)
    for kwargs in ({"sharpe_target": 0.0}, {"dispersion_ref": 0.0}, {"drawdown_ref": 0.0}):
        with pytest.raises(ValueError, match="must be > 0"):
            score_walk_forward(wf, **kwargs)  # type: ignore[arg-type]


def test_partial_weights_rejected() -> None:
    """A weights dict missing keys would KeyError mid-computation — reject it."""
    wf = _wf(sharpe=1.0, consistency=60, dispersion=10, worst_dd=10)
    with pytest.raises(ValueError, match="exactly these keys"):
        score_walk_forward(wf, weights={"risk_adjusted": 1.0})


def test_non_normalized_weights_stay_in_unit_range() -> None:
    """Non-normalized weights are normalized so overall cannot exceed 1.0."""
    wf = _wf(sharpe=10.0, consistency=100, dispersion=0, worst_dd=0)  # everything maxed
    doubled = {k: v * 2 for k, v in DEFAULT_WEIGHTS.items()}  # sums to 2.0
    s = score_walk_forward(wf, weights=doubled)
    assert 0.0 <= s.overall <= 1.0
    # matches the normalized-default result (same proportions)
    assert abs(s.overall - score_walk_forward(wf).overall) < 1e-9
