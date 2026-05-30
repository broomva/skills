"""Decision plane — the strategy abstraction (L1).

The control plane (operator + TV-paper adapter) executes; this package decides.
A Strategy is a pure function ``signal(market_state) -> Signal`` that drives BOTH:

  - simulation: ``backtest_runner.run_backtest`` walks history → metrics
  - live: ``tvalert.signal_to_tvalert`` converts a signal → TVAlert → operator

One strategy spec, dual execution — so the same rules are measured in backtest
and run live, and the gap between the two (backtest vs paper-forward) is the
honest signal of whether an edge is real.

This is the keystone the rest of the decision plane composes on: market study
feeds MarketState; the walk-forward harness + performance ledger measure a
Strategy; the orchestrator allocates across Strategies; the autoresearch loop
evolves them.
"""

from .backtest_runner import BacktestResult, Trade, run_backtest
from .base import Strategy
from .library import DonchianBreakout, RSIMeanReversion, SMACrossover
from .tvalert import signal_to_tvalert
from .types import Bar, MarketState, Signal, StrategyAction

__all__ = [
    "BacktestResult",
    "Bar",
    "DonchianBreakout",
    "MarketState",
    "RSIMeanReversion",
    "SMACrossover",
    "Signal",
    "Strategy",
    "StrategyAction",
    "Trade",
    "run_backtest",
    "signal_to_tvalert",
]
