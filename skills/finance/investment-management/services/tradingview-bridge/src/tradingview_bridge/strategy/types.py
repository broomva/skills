"""Core decision-plane types: Bar, MarketState, Signal.

Prices/quantities are Decimal (no float loss in money math). A Strategy reads a
MarketState (history up to + including the current bar) and returns a Signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from ..schemas import AssetClass

StrategyAction = Literal["enter_long", "enter_short", "exit", "hold"]
SignalSizeType = Literal["units", "pct_equity", "notional_usd"]


@dataclass(frozen=True)
class Bar:
    """One OHLCV candle."""

    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal(0)


@dataclass(frozen=True)
class MarketState:
    """The market as a strategy sees it at one point in time.

    ``bars`` is chronological; ``bars[-1]`` is the current (most recent) bar.
    A strategy must tolerate fewer bars than its warmup (return ``hold``).
    """

    symbol: str
    asset_class: AssetClass
    bars: tuple[Bar, ...]

    @property
    def price(self) -> Decimal:
        """Current close. Assumes at least one bar (strategies guard warmup)."""
        return self.bars[-1].close

    @property
    def closes(self) -> list[Decimal]:
        return [b.close for b in self.bars]

    @property
    def highs(self) -> list[Decimal]:
        return [b.high for b in self.bars]

    @property
    def lows(self) -> list[Decimal]:
        return [b.low for b in self.bars]


@dataclass(frozen=True)
class Signal:
    """A strategy's decision for the current bar.

    - enter_long / enter_short — open a position
    - exit — close the current position
    - hold — do nothing (no live alert is emitted)
    """

    action: StrategyAction
    size: Decimal = Decimal(1)
    size_type: SignalSizeType = "units"
    reason: str = ""
    confidence: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)
