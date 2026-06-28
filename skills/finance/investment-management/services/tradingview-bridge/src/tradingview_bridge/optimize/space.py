"""Parameter spaces — the mutable-artifact surface of the EGRI loop.

A ParamSpace declares (a) the grid of parameter values to search, (b) how to build
a Strategy from a chosen param-set, and (c) an optional validity constraint (e.g.
SMA fast < slow). These are the *mutable* half of EGRI; the evaluator (walk-forward
+ score) is the *immutable* half, frozen across the search.

The three built-in spaces mirror the strategy library. Grids are deliberately
modest: warmup (e.g. SMA slow) must fit comfortably inside the smaller test
segment, so `slow` tops out at 100 rather than 200.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..strategy.base import Strategy
from ..strategy.library import DonchianBreakout, RSIMeanReversion, SMACrossover


@dataclass(frozen=True)
class ParamSpace:
    """A searchable parameter space for one strategy family."""

    family: str
    factory: Callable[[dict[str, int]], Strategy]
    grid: dict[str, list[int]]
    constraint: Callable[[dict[str, int]], bool] | None = None


def _sma_factory(p: dict[str, int]) -> Strategy:
    return SMACrossover(fast=p["fast"], slow=p["slow"])


def _rsi_factory(p: dict[str, int]) -> Strategy:
    return RSIMeanReversion(length=p["length"], oversold=p["oversold"], overbought=p["overbought"])


def _donchian_factory(p: dict[str, int]) -> Strategy:
    return DonchianBreakout(length=p["length"])


SMA_CROSSOVER_SPACE = ParamSpace(
    family="sma-crossover",
    factory=_sma_factory,
    grid={"fast": [5, 10, 20], "slow": [20, 50, 100]},
    constraint=lambda p: p["fast"] < p["slow"],
)

RSI_MEAN_REVERSION_SPACE = ParamSpace(
    family="rsi-mean-reversion",
    factory=_rsi_factory,
    grid={"length": [7, 14, 21], "oversold": [20, 30], "overbought": [70, 80]},
    # the ctor also enforces 0 < oversold < overbought < 100; this prunes early.
    constraint=lambda p: p["oversold"] < p["overbought"],
)

DONCHIAN_BREAKOUT_SPACE = ParamSpace(
    family="donchian-breakout",
    factory=_donchian_factory,
    grid={"length": [10, 20, 55]},
)

BUILTIN_SPACES: dict[str, ParamSpace] = {
    SMA_CROSSOVER_SPACE.family: SMA_CROSSOVER_SPACE,
    RSI_MEAN_REVERSION_SPACE.family: RSI_MEAN_REVERSION_SPACE,
    DONCHIAN_BREAKOUT_SPACE.family: DONCHIAN_BREAKOUT_SPACE,
}
