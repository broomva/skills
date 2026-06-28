"""Tests for the param spaces + grid search (space.py, search.py)."""

from __future__ import annotations

from tradingview_bridge.optimize.search import grid_candidates
from tradingview_bridge.optimize.space import (
    BUILTIN_SPACES,
    DONCHIAN_BREAKOUT_SPACE,
    RSI_MEAN_REVERSION_SPACE,
    SMA_CROSSOVER_SPACE,
)


def test_builtin_spaces_has_three_families() -> None:
    assert set(BUILTIN_SPACES) == {"sma-crossover", "rsi-mean-reversion", "donchian-breakout"}


def test_sma_grid_filters_fast_lt_slow() -> None:
    cands = grid_candidates(SMA_CROSSOVER_SPACE)
    assert all(c["fast"] < c["slow"] for c in cands)
    assert len(cands) == 8  # 3x3 product, minus the (20,20) and (20<50/100 keep) → 8 valid


def test_rsi_grid_filters_oversold_lt_overbought() -> None:
    cands = grid_candidates(RSI_MEAN_REVERSION_SPACE)
    assert all(c["oversold"] < c["overbought"] for c in cands)
    assert len(cands) == 12  # length{7,14,21} x oversold{20,30} x overbought{70,80}, all valid


def test_donchian_grid_unconstrained() -> None:
    assert len(grid_candidates(DONCHIAN_BREAKOUT_SPACE)) == 3


def test_grid_candidates_deterministic() -> None:
    assert grid_candidates(SMA_CROSSOVER_SPACE) == grid_candidates(SMA_CROSSOVER_SPACE)


def test_grid_candidates_max_truncation() -> None:
    assert len(grid_candidates(SMA_CROSSOVER_SPACE, max_candidates=3)) == 3


def test_factories_build_correctly_named_strategies() -> None:
    assert SMA_CROSSOVER_SPACE.factory({"fast": 5, "slow": 20}).name == "sma-crossover-5-20"
    rsi = RSI_MEAN_REVERSION_SPACE.factory({"length": 14, "oversold": 30, "overbought": 70})
    assert rsi.name == "rsi-mean-reversion-14"
    assert DONCHIAN_BREAKOUT_SPACE.factory({"length": 20}).name == "donchian-breakout-20"
