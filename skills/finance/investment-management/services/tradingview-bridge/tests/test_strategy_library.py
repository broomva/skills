"""Strategy library tests — signals on hand-computed data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingview_bridge.strategy.library import (
    DonchianBreakout,
    RSIMeanReversion,
    SMACrossover,
)
from tradingview_bridge.strategy.types import Bar, MarketState


def _bars(
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> tuple[Bar, ...]:
    out = []
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i, c in enumerate(closes):
        cd = Decimal(str(c))
        hd = Decimal(str(highs[i])) if highs else cd
        ld = Decimal(str(lows[i])) if lows else cd
        out.append(Bar(ts=base + timedelta(days=i), open=cd, high=hd, low=ld, close=cd))
    return tuple(out)


def _state(closes: list[float], **kw: list[float]) -> MarketState:
    return MarketState(symbol="TEST", asset_class="stock", bars=_bars(closes, **kw))


# ---- SMA crossover ------------------------------------------------------


def test_sma_warmup_holds() -> None:
    assert SMACrossover(2, 3).signal(_state([10, 9])).action == "hold"


def test_sma_golden_cross_enters_long() -> None:
    # hand-computed: fast(2) crosses above slow(3) at the last bar
    sig = SMACrossover(fast=2, slow=3).signal(_state([10, 8, 6, 9, 12]))
    assert sig.action == "enter_long"
    assert "golden" in sig.reason


def test_sma_death_cross_exits() -> None:
    sig = SMACrossover(fast=2, slow=3).signal(_state([6, 9, 12, 8, 5]))
    assert sig.action == "exit"


def test_sma_invalid_params() -> None:
    import pytest

    with pytest.raises(ValueError, match="fast must be < slow"):
        SMACrossover(fast=200, slow=50)


# ---- RSI mean reversion -------------------------------------------------


def test_rsi_warmup_holds() -> None:
    assert RSIMeanReversion(length=2).signal(_state([10, 9])).action == "hold"


def test_rsi_exit_oversold_enters_long() -> None:
    # two down days (RSI→0) then an up day (RSI lifts above oversold)
    sig = RSIMeanReversion(length=2, oversold=30, overbought=70).signal(_state([10, 9, 8, 9]))
    assert sig.action == "enter_long"


# ---- Donchian breakout --------------------------------------------------


def test_donchian_breakout_high_enters_long() -> None:
    sig = DonchianBreakout(length=2).signal(_state([10, 11, 9, 13]))
    assert sig.action == "enter_long"
    assert "breakout" in sig.reason


def test_donchian_breakout_low_exits() -> None:
    sig = DonchianBreakout(length=2).signal(_state([10, 11, 9, 5]))
    assert sig.action == "exit"


def test_donchian_inside_range_holds() -> None:
    sig = DonchianBreakout(length=2).signal(_state([10, 12, 8, 10]))
    assert sig.action == "hold"


def test_strategy_names_include_params() -> None:
    assert SMACrossover(50, 200).name == "sma-crossover-50-200"
    assert RSIMeanReversion(14).name == "rsi-mean-reversion-14"
    assert DonchianBreakout(20).name == "donchian-breakout-20"
