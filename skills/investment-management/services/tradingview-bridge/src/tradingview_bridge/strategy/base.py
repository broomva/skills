"""Strategy ABC — the unit the whole decision plane measures and orchestrates."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import MarketState, Signal


class Strategy(ABC):
    """A pure, deterministic signal function over market state.

    Implementations MUST be deterministic (same state → same signal) and
    side-effect free, so a backtest and a live run of the same strategy on the
    same bars produce identical signals. That determinism is what makes the
    backtest-vs-live comparison meaningful.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier (includes params), e.g. ``sma-crossover-50-200``."""

    @property
    def warmup(self) -> int:
        """Minimum bars before the strategy can emit a non-hold signal."""
        return 0

    @abstractmethod
    def signal(self, state: MarketState) -> Signal:
        """Decide for the current (last) bar of ``state``."""
