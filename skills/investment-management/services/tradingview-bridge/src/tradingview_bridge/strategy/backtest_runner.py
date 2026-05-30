"""Event-driven backtest runner — the simulation half of the keystone.

Walks a strategy bar-by-bar over history, simulating a long-only, fully-allocated
book (a position is the whole equity in one instrument), and reports the core
metrics the decision plane scores on: total return, Sharpe, max drawdown, win
rate, trade count + the equity curve.

Deliberately simple and honest about its simplifications (stated below), so the
numbers are not oversold. Costs/slippage, short side, partial sizing, and
walk-forward/out-of-sample splitting are the next layer (a separate PR) — this
runner is the inner loop they wrap.

Simplifications (v1):
  - long-only: enter_long opens, exit closes; enter_short is treated as exit.
  - full allocation: a position holds 100% of equity (no sizing, no leverage).
  - fills at the bar close, no commission/slippage.
  - Sharpe annualized with ``periods_per_year`` (default 252 = daily bars);
    set it to match your bar timeframe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal

# Reuse the asset-class type without a hard schema import at call sites.
from ..schemas import AssetClass
from .base import Strategy
from .types import Bar, MarketState


@dataclass(frozen=True)
class Trade:
    """One round-trip (entry → exit)."""

    entry_index: int
    exit_index: int
    entry_price: Decimal
    exit_price: Decimal

    @property
    def return_pct(self) -> Decimal:
        if self.entry_price == 0:
            return Decimal(0)
        return (self.exit_price - self.entry_price) / self.entry_price * Decimal(100)

    @property
    def won(self) -> bool:
        return self.exit_price > self.entry_price


@dataclass(frozen=True)
class BacktestResult:
    """Metrics + equity curve from a single backtest."""

    strategy: str
    symbol: str
    n_bars: int
    n_trades: int
    total_return_pct: Decimal
    sharpe: float
    max_drawdown_pct: Decimal
    win_rate_pct: Decimal
    equity_curve: list[Decimal] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)


def _sharpe(returns: list[float], periods_per_year: int) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(periods_per_year)


def _max_drawdown_pct(equity: list[Decimal]) -> Decimal:
    peak = equity[0] if equity else Decimal(0)
    max_dd = Decimal(0)
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * Decimal(100)
            if dd > max_dd:
                max_dd = dd
    return max_dd


def run_backtest(
    strategy: Strategy,
    bars: list[Bar],
    *,
    symbol: str,
    asset_class: AssetClass,
    initial: Decimal = Decimal(10000),
    periods_per_year: int = 252,
) -> BacktestResult:
    """Run ``strategy`` over ``bars`` and return metrics. Long-only, full-alloc."""
    cash = initial
    units = Decimal(0)
    entry_price: Decimal | None = None
    entry_index = 0
    equity_curve: list[Decimal] = []
    returns: list[float] = []
    trades: list[Trade] = []
    prev_equity = initial

    for i, bar in enumerate(bars):
        state = MarketState(symbol=symbol, asset_class=asset_class, bars=tuple(bars[: i + 1]))
        sig = strategy.signal(state)
        price = bar.close

        if sig.action == "enter_long" and units == 0 and price > 0:
            units = cash / price
            cash = Decimal(0)
            entry_price = price
            entry_index = i
        elif sig.action in ("exit", "enter_short") and units > 0:
            cash = units * price
            if entry_price is not None:
                trades.append(
                    Trade(
                        entry_index=entry_index,
                        exit_index=i,
                        entry_price=entry_price,
                        exit_price=price,
                    )
                )
            units = Decimal(0)
            entry_price = None

        equity = cash + units * price
        equity_curve.append(equity)
        if prev_equity > 0:
            returns.append(float((equity - prev_equity) / prev_equity))
        prev_equity = equity

    # Close any open position at the final close (mark the trade).
    if units > 0 and bars and entry_price is not None:
        final_price = bars[-1].close
        trades.append(
            Trade(
                entry_index=entry_index,
                exit_index=len(bars) - 1,
                entry_price=entry_price,
                exit_price=final_price,
            )
        )

    final_equity = equity_curve[-1] if equity_curve else initial
    total_return = (final_equity - initial) / initial * Decimal(100) if initial > 0 else Decimal(0)
    wins = sum(1 for t in trades if t.won)
    win_rate = Decimal(wins) / Decimal(len(trades)) * Decimal(100) if trades else Decimal(0)

    return BacktestResult(
        strategy=strategy.name,
        symbol=symbol,
        n_bars=len(bars),
        n_trades=len(trades),
        total_return_pct=total_return,
        sharpe=_sharpe(returns, periods_per_year),
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        win_rate_pct=win_rate,
        equity_curve=equity_curve,
        trades=trades,
    )
