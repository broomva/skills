"""Evaluation — the honest scoreboard (L2 measurement).

Turns "I can backtest one strategy" into "I can rank strategies by trustworthy,
anti-overfit evidence" — the numbers the orchestration layer (and the agent's
reasoning) allocate on.

  walk_forward — partition a continuous backtest into N time windows; report
                 consistency (% windows profitable) + dispersion, not just one
                 lucky number.
  ledger       — PerformanceLedger (SQLite): record every evaluation (backtest /
                 walk-forward / live-paper); compare_sim_vs_live surfaces the
                 backtest-vs-paper gap, the honest "is the edge real" signal.
  score        — score_walk_forward → a 0-1 trustworthiness score with
                 anti-overfitting baked in (consistency + robustness weigh half).
"""

from .ledger import EvaluationRecord, PerformanceLedger, SimLiveGap
from .score import StrategyScore, score_walk_forward
from .walk_forward import WalkForwardResult, WindowMetrics, walk_forward

__all__ = [
    "EvaluationRecord",
    "PerformanceLedger",
    "SimLiveGap",
    "StrategyScore",
    "WalkForwardResult",
    "WindowMetrics",
    "score_walk_forward",
    "walk_forward",
]
