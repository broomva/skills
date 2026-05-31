"""Optimization plane — EGRI parameter-optimization (the self-improving step).

The evaluation plane scores one strategy; the orchestrator ranks a fixed roster;
this plane *evolves* a strategy's parameters — honestly. It searches a parameter
grid on a TRAIN segment, then estimates the winner ONCE on a held-out TEST segment
the search never saw, so the reported score reflects generalization, not
curve-fitting. The evaluator (walk-forward + score) is frozen across the search:
the optimizer can change the params, never the yardstick.

  space.py  — ParamSpace + the 3 built-in spaces (the mutable artifact surface).
  search.py — deterministic grid search (grid_candidates).
  egri.py   — optimize_walk_forward: the train/test loop + generalization gap.
  types.py  — ParamCandidate / OptimizationResult (human-gated by construction).
  cli.py    — the `optimize` entry point.
"""

from .egri import (
    DEFAULT_MAX_GAP,
    DEFAULT_MIN_TEST_SCORE,
    DEFAULT_TRAIN_FRAC,
    optimize_walk_forward,
)
from .search import grid_candidates
from .space import (
    BUILTIN_SPACES,
    DONCHIAN_BREAKOUT_SPACE,
    RSI_MEAN_REVERSION_SPACE,
    SMA_CROSSOVER_SPACE,
    ParamSpace,
)
from .types import OptimizationResult, ParamCandidate

__all__ = [
    "BUILTIN_SPACES",
    "DEFAULT_MAX_GAP",
    "DEFAULT_MIN_TEST_SCORE",
    "DEFAULT_TRAIN_FRAC",
    "DONCHIAN_BREAKOUT_SPACE",
    "RSI_MEAN_REVERSION_SPACE",
    "SMA_CROSSOVER_SPACE",
    "OptimizationResult",
    "ParamCandidate",
    "ParamSpace",
    "grid_candidates",
    "optimize_walk_forward",
]
