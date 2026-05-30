"""Walk-forward evaluation — robustness across time, not one lucky backtest.

Runs ONE continuous backtest (so indicator warmup is unbroken) then partitions
the equity curve into N contiguous time windows, computing per-window metrics.
The aggregates that matter are **consistency** (fraction of windows that were
profitable) and **dispersion** (std of window returns) — a strategy that is
brilliant in one window and terrible in others is NOT trustworthy, and these
metrics say so where a single backtest number would hide it.

Honesty: the strategies here carry fixed params (no optimizer in this layer), so
this is rolling out-of-sample evaluation across disjoint periods — it tests
whether edge is CONSISTENT, not whether tuned params generalize. True train→test
optimization walk-forward composes this with the EGRI param search (next layer).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from ..schemas import AssetClass
from ..strategy.backtest_runner import BacktestResult, run_backtest
from ..strategy.base import Strategy
from ..strategy.types import Bar


@dataclass(frozen=True)
class WindowMetrics:
    """Metrics for one time window of the walk-forward."""

    index: int
    start_index: int
    end_index: int
    return_pct: Decimal
    sharpe: float
    max_drawdown_pct: Decimal

    @property
    def profitable(self) -> bool:
        return self.return_pct > 0


@dataclass(frozen=True)
class WalkForwardResult:
    """Aggregate of a strategy's performance across N windows."""

    strategy: str
    symbol: str
    n_windows: int
    windows: list[WindowMetrics]
    full: BacktestResult
    mean_return_pct: Decimal
    return_std: float
    mean_sharpe: float
    consistency_pct: Decimal
    worst_window_return_pct: Decimal
    best_window_return_pct: Decimal

    @property
    def worst_window_drawdown_pct(self) -> Decimal:
        return max((w.max_drawdown_pct for w in self.windows), default=Decimal(0))


def _sharpe(returns: list[float], periods_per_year: int) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var)
    return (mean / std) * math.sqrt(periods_per_year) if std > 0 else 0.0


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


def walk_forward(
    strategy: Strategy,
    bars: list[Bar],
    *,
    symbol: str,
    asset_class: AssetClass,
    n_windows: int = 5,
    periods_per_year: int = 252,
) -> WalkForwardResult:
    """Evaluate ``strategy`` across ``n_windows`` contiguous time windows."""
    if n_windows < 2:
        raise ValueError("n_windows must be >= 2")
    if len(bars) < n_windows * 2:
        raise ValueError(f"need >= {n_windows * 2} bars for {n_windows} windows")

    full = run_backtest(
        strategy,
        bars,
        symbol=symbol,
        asset_class=asset_class,
        periods_per_year=periods_per_year,
    )
    eq = full.equity_curve
    n = len(eq)
    seg = n // n_windows

    windows: list[WindowMetrics] = []
    for k in range(n_windows):
        a = k * seg
        b = (k + 1) * seg - 1 if k < n_windows - 1 else n - 1
        start_eq = eq[a]
        end_eq = eq[b]
        win_return = (end_eq - start_eq) / start_eq * Decimal(100) if start_eq > 0 else Decimal(0)
        seg_eq = eq[a : b + 1]
        seg_returns = [
            float((seg_eq[i] - seg_eq[i - 1]) / seg_eq[i - 1])
            for i in range(1, len(seg_eq))
            if seg_eq[i - 1] > 0
        ]
        windows.append(
            WindowMetrics(
                index=k,
                start_index=a,
                end_index=b,
                return_pct=win_return,
                sharpe=_sharpe(seg_returns, periods_per_year),
                max_drawdown_pct=_max_drawdown_pct(seg_eq),
            )
        )

    returns = [w.return_pct for w in windows]
    mean_return = sum(returns, Decimal(0)) / Decimal(len(returns))
    float_returns = [float(r) for r in returns]
    mean_f = sum(float_returns) / len(float_returns)
    return_std = (
        math.sqrt(sum((r - mean_f) ** 2 for r in float_returns) / (len(float_returns) - 1))
        if len(float_returns) > 1
        else 0.0
    )
    profitable = sum(1 for w in windows if w.profitable)
    consistency = Decimal(profitable) / Decimal(len(windows)) * Decimal(100)

    return WalkForwardResult(
        strategy=strategy.name,
        symbol=symbol,
        n_windows=n_windows,
        windows=windows,
        full=full,
        mean_return_pct=mean_return,
        return_std=return_std,
        mean_sharpe=sum(w.sharpe for w in windows) / len(windows),
        consistency_pct=consistency,
        worst_window_return_pct=min(returns),
        best_window_return_pct=max(returns),
    )
