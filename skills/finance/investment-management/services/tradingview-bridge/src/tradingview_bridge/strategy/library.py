"""Strategy library — three baseline strategies matching the Pine templates.

These mirror strategies/pine/{01-sma-crossover, 02-rsi-mean-reversion,
03-donchian-breakout}.pine, so the SAME logic is backtestable here and runs live
via TradingView. Deliberate baselines, not edge-edge alpha — they are the
reference strategies the measurement/orchestration layers are built against.
"""

from __future__ import annotations

from decimal import Decimal

from .base import Strategy
from .types import MarketState, Signal


def _sma(values: list[Decimal], n: int) -> Decimal:
    return sum(values[-n:], Decimal(0)) / Decimal(n)


def _rsi(closes: list[Decimal], n: int) -> Decimal:
    """Wilder-style RSI over the last n deltas. Returns 0..100."""
    if len(closes) < n + 1:
        return Decimal(50)
    gains = Decimal(0)
    losses = Decimal(0)
    for i in range(len(closes) - n, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses += -diff
    avg_gain = gains / Decimal(n)
    avg_loss = losses / Decimal(n)
    if avg_loss == 0:
        return Decimal(100)
    rs = avg_gain / avg_loss
    return Decimal(100) - (Decimal(100) / (Decimal(1) + rs))


class SMACrossover(Strategy):
    """Golden/death cross of a fast and slow SMA. Trend-following baseline."""

    def __init__(self, fast: int = 50, slow: int = 200, size: Decimal = Decimal(1)) -> None:
        if fast < 1 or slow < 2:
            raise ValueError("fast >= 1 and slow >= 2 required")
        if fast >= slow:
            raise ValueError("fast must be < slow")
        self._fast = fast
        self._slow = slow
        self._size = size

    @property
    def name(self) -> str:
        return f"sma-crossover-{self._fast}-{self._slow}"

    @property
    def warmup(self) -> int:
        return self._slow + 1

    def signal(self, state: MarketState) -> Signal:
        closes = state.closes
        if len(closes) < self._slow + 1:
            return Signal("hold", reason="warmup")
        fast_now = _sma(closes, self._fast)
        slow_now = _sma(closes, self._slow)
        prev = closes[:-1]
        fast_prev = _sma(prev, self._fast)
        slow_prev = _sma(prev, self._slow)
        if fast_prev <= slow_prev and fast_now > slow_now:
            return Signal("enter_long", size=self._size, reason="golden cross")
        if fast_prev >= slow_prev and fast_now < slow_now:
            return Signal("exit", reason="death cross")
        return Signal("hold")


class RSIMeanReversion(Strategy):
    """Enter long on exit-from-oversold; exit on exit-from-overbought."""

    def __init__(
        self,
        length: int = 14,
        oversold: int = 30,
        overbought: int = 70,
        size: Decimal = Decimal(1),
    ) -> None:
        if length < 2:
            raise ValueError("length >= 2 required")
        if not 0 < oversold < overbought < 100:
            raise ValueError("require 0 < oversold < overbought < 100")
        self._length = length
        self._oversold = Decimal(oversold)
        self._overbought = Decimal(overbought)
        self._size = size

    @property
    def name(self) -> str:
        return f"rsi-mean-reversion-{self._length}"

    @property
    def warmup(self) -> int:
        return self._length + 2

    def signal(self, state: MarketState) -> Signal:
        closes = state.closes
        if len(closes) < self._length + 2:
            return Signal("hold", reason="warmup")
        rsi_now = _rsi(closes, self._length)
        rsi_prev = _rsi(closes[:-1], self._length)
        if rsi_prev <= self._oversold and rsi_now > self._oversold:
            return Signal("enter_long", size=self._size, reason="exit oversold")
        if rsi_prev >= self._overbought and rsi_now < self._overbought:
            return Signal("exit", reason="exit overbought")
        return Signal("hold")


class DonchianBreakout(Strategy):
    """Enter long on a new N-bar high; exit on a new N-bar low (Turtle-style)."""

    def __init__(self, length: int = 20, size: Decimal = Decimal(1)) -> None:
        if length < 2:
            raise ValueError("length >= 2 required")
        self._length = length
        self._size = size

    @property
    def name(self) -> str:
        return f"donchian-breakout-{self._length}"

    @property
    def warmup(self) -> int:
        return self._length + 1

    def signal(self, state: MarketState) -> Signal:
        bars = state.bars
        if len(bars) < self._length + 1:
            return Signal("hold", reason="warmup")
        # Prior N bars, excluding the current — breakout vs the *prior* range.
        prior = bars[-(self._length + 1) : -1]
        upper = max(b.high for b in prior)
        lower = min(b.low for b in prior)
        price = state.price
        if price > upper:
            return Signal("enter_long", size=self._size, reason="breakout high")
        if price < lower:
            return Signal("exit", reason="breakout low")
        return Signal("hold")
