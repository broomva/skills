"""Backtest runner tests — metrics on synthetic series."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingview_bridge.strategy.backtest_runner import run_backtest
from tradingview_bridge.strategy.library import SMACrossover
from tradingview_bridge.strategy.types import Bar


def _bars(closes: list[float]) -> list[Bar]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    out = []
    for i, c in enumerate(closes):
        cd = Decimal(str(c))
        out.append(Bar(ts=base + timedelta(days=i), open=cd, high=cd, low=cd, close=cd))
    return out


def test_v_shape_recovery_is_profitable() -> None:
    # A dip then a sustained recovery: the fast SMA crosses ABOVE the slow during
    # the rise (a real golden cross), the strategy enters long and rides it up.
    # (A pure monotonic uptrend never crosses — fast is above slow from bar 1.)
    closes = [100.0 - i for i in range(15)] + [85.0 + i * 1.5 for i in range(65)]
    res = run_backtest(
        SMACrossover(fast=5, slow=20),
        _bars(closes),
        symbol="TEST",
        asset_class="stock",
    )
    assert res.n_trades >= 1
    assert res.total_return_pct > 0
    assert res.max_drawdown_pct >= 0
    assert 0 <= res.win_rate_pct <= 100
    assert len(res.equity_curve) == len(closes)


def test_flat_market_no_trades_no_return() -> None:
    closes = [100.0] * 60
    res = run_backtest(
        SMACrossover(fast=5, slow=20),
        _bars(closes),
        symbol="TEST",
        asset_class="stock",
    )
    assert res.n_trades == 0
    assert res.total_return_pct == 0
    assert res.sharpe == 0.0


def test_result_carries_strategy_and_symbol() -> None:
    res = run_backtest(
        SMACrossover(fast=2, slow=5),
        _bars([10.0, 9, 8, 7, 8, 9, 10, 11, 12]),
        symbol="MSFT",
        asset_class="stock",
    )
    assert res.strategy == "sma-crossover-2-5"
    assert res.symbol == "MSFT"
    assert res.n_bars == 9


def test_metrics_are_finite() -> None:
    import math

    # noisy series
    closes = [100 + (i % 7) - 3 + (i * 0.3) for i in range(100)]
    res = run_backtest(
        SMACrossover(fast=10, slow=30),
        _bars(closes),
        symbol="TEST",
        asset_class="stock",
    )
    assert math.isfinite(res.sharpe)
    assert res.max_drawdown_pct >= 0
