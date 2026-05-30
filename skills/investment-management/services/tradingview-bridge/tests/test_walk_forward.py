"""Walk-forward harness tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tradingview_bridge.evaluation.walk_forward import walk_forward
from tradingview_bridge.strategy.library import SMACrossover
from tradingview_bridge.strategy.types import Bar


def _bars(closes: list[float]) -> list[Bar]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    out = []
    for i, c in enumerate(closes):
        cd = Decimal(str(c))
        out.append(Bar(ts=base + timedelta(days=i), open=cd, high=cd, low=cd, close=cd))
    return out


def test_partitions_into_n_windows() -> None:
    closes = [100.0 - i for i in range(15)] + [85.0 + i * 1.5 for i in range(85)]
    wf = walk_forward(
        SMACrossover(5, 20), _bars(closes), symbol="T", asset_class="stock", n_windows=5
    )
    assert wf.n_windows == 5
    assert len(wf.windows) == 5
    assert wf.windows[0].index == 0
    assert wf.windows[-1].index == 4


def test_consistency_and_dispersion_reported() -> None:
    closes = [100.0 - i for i in range(15)] + [85.0 + i * 1.5 for i in range(85)]
    wf = walk_forward(
        SMACrossover(5, 20), _bars(closes), symbol="T", asset_class="stock", n_windows=5
    )
    assert Decimal(0) <= wf.consistency_pct <= Decimal(100)
    assert wf.return_std >= 0.0
    assert wf.worst_window_return_pct <= wf.best_window_return_pct


def test_flat_market_zero_consistency() -> None:
    wf = walk_forward(
        SMACrossover(5, 20), _bars([100.0] * 100), symbol="T", asset_class="stock", n_windows=5
    )
    # no trades, no return anywhere → 0% of windows profitable
    assert wf.consistency_pct == Decimal(0)
    assert wf.mean_return_pct == Decimal(0)


def test_requires_min_windows() -> None:
    with pytest.raises(ValueError, match="n_windows must be >= 2"):
        walk_forward(
            SMACrossover(2, 5), _bars([1.0] * 50), symbol="T", asset_class="stock", n_windows=1
        )


def test_requires_enough_bars() -> None:
    with pytest.raises(ValueError, match="need >="):
        walk_forward(
            SMACrossover(2, 5), _bars([1.0] * 6), symbol="T", asset_class="stock", n_windows=5
        )


def test_full_backtest_attached() -> None:
    closes = [100.0 + (i % 5) + i * 0.2 for i in range(100)]
    wf = walk_forward(SMACrossover(5, 20), _bars(closes), symbol="MSFT", asset_class="stock")
    assert wf.full.symbol == "MSFT"
    assert wf.full.n_bars == 100
    assert wf.strategy == "sma-crossover-5-20"
