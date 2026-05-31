"""egri — the EGRI parameter-optimization loop with a true train/test holdout.

EGRI = Evaluator-Governed Recursive Improvement (composes with the autoany skill):

  - **Mutable artifact** — strategy parameters (the thing we search over).
  - **Immutable evaluator** — ``walk_forward`` + ``score_walk_forward``, FROZEN
    across the search. This is the stop-gradient guarantee: the optimizer can only
    change the params, never the scorer, so it cannot tune the yardstick to fit the
    data.
  - **Harness** — run a candidate param-set through the evaluator.
  - **Promotion policy** — ``generalizes`` iff the out-of-sample test score clears a
    floor AND the train→test gap is within tolerance. Always human-gated.

The honest part is the split. Searching N param-sets and keeping the best is a
multiple-comparisons overfitting risk: even noise has an in-sample winner. So the
winner is *selected on the train segment only*, then *scored exactly once on a test
segment the search never saw*. The train-test gap quantifies the overfitting that
selection bias would otherwise hide.
"""

from __future__ import annotations

import structlog

from ..evaluation.score import score_walk_forward
from ..evaluation.walk_forward import walk_forward
from ..schemas import AssetClass
from ..strategy.base import Strategy
from ..strategy.types import Bar
from .search import grid_candidates
from .space import ParamSpace
from .types import OptimizationResult, ParamCandidate

log = structlog.get_logger("tradingview_bridge.optimize.egri")

DEFAULT_TRAIN_FRAC = 0.7
DEFAULT_MIN_TEST_SCORE = 0.5
DEFAULT_MAX_GAP = 0.25


def _score_on(
    strategy: Strategy,
    bars: list[Bar],
    *,
    symbol: str,
    asset_class: AssetClass,
    n_windows: int,
    periods_per_year: int,
) -> float:
    """The immutable evaluator: walk-forward then anti-overfit score → overall."""
    wf = walk_forward(
        strategy,
        bars,
        symbol=symbol,
        asset_class=asset_class,
        n_windows=n_windows,
        periods_per_year=periods_per_year,
    )
    return score_walk_forward(wf).overall


def optimize_walk_forward(
    space: ParamSpace,
    bars: list[Bar],
    *,
    symbol: str,
    asset_class: AssetClass,
    train_frac: float = DEFAULT_TRAIN_FRAC,
    n_windows: int = 4,
    periods_per_year: int = 252,
    min_test_score: float = DEFAULT_MIN_TEST_SCORE,
    max_gap: float = DEFAULT_MAX_GAP,
    max_candidates: int | None = None,
) -> OptimizationResult:
    """Grid-search ``space`` over ``bars`` with a train/test holdout. Pure, no I/O."""
    if not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must be in (0, 1)")
    split = int(len(bars) * train_frac)
    train_bars, test_bars = bars[:split], bars[split:]
    need = n_windows * 2
    if len(train_bars) < need or len(test_bars) < need:
        raise ValueError(
            f"need >= {need} bars in each of train ({len(train_bars)}) and test "
            f"({len(test_bars)}) for {n_windows} windows; supply more bars or lower "
            f"n_windows / move train_frac toward 0.5"
        )

    candidates = grid_candidates(space, max_candidates=max_candidates)
    if not candidates:
        raise ValueError(f"param space '{space.family}' produced no valid candidates")

    # --- search the TRAIN segment (the evaluator is frozen; only params vary) ---
    ranked_raw: list[ParamCandidate] = []
    for params in candidates:
        strat = space.factory(params)
        train_score = _score_on(
            strat,
            train_bars,
            symbol=symbol,
            asset_class=asset_class,
            n_windows=n_windows,
            periods_per_year=periods_per_year,
        )
        ranked_raw.append(
            ParamCandidate(params=params, strategy_name=strat.name, train_score=train_score)
        )
    ranked = sorted(ranked_raw, key=lambda c: (-c.train_score, c.strategy_name))
    best = ranked[0]

    # --- estimate the winner ONCE on the held-out TEST segment (no test selection) ---
    test_score = _score_on(
        space.factory(best.params),
        test_bars,
        symbol=symbol,
        asset_class=asset_class,
        n_windows=n_windows,
        periods_per_year=periods_per_year,
    )
    gap = best.train_score - test_score
    generalizes = test_score >= min_test_score and gap <= max_gap

    name = best.strategy_name
    train = best.train_score
    if generalizes:
        rationale = (
            f"{name} generalizes: out-of-sample test {test_score:.3f} >= {min_test_score:.2f} "
            f"and gap {gap:+.3f} <= {max_gap:.2f} (train {train:.3f}). "
            f"Human approval required before promotion."
        )
    elif test_score < min_test_score:
        rationale = (
            f"{name} does NOT generalize: out-of-sample test {test_score:.3f} is below the floor "
            f"{min_test_score:.2f} (train was {train:.3f}) — the in-sample winner did not hold up."
        )
    else:
        rationale = (
            f"{name} OVERFIT: train {train:.3f} but test {test_score:.3f}, gap {gap:+.3f} > "
            f"{max_gap:.2f} — tuned to the train windows, did not generalize out-of-sample."
        )

    log.info(
        "optimization_done",
        family=space.family,
        symbol=symbol,
        n_candidates=len(candidates),
        best=best.strategy_name,
        train=round(best.train_score, 3),
        test=round(test_score, 3),
        gap=round(gap, 3),
        generalizes=generalizes,
    )

    return OptimizationResult(
        family=space.family,
        symbol=symbol,
        n_candidates=len(candidates),
        train_frac=train_frac,
        split_index=split,
        ranked=ranked,
        best=best,
        test_score=test_score,
        generalization_gap=gap,
        generalizes=generalizes,
        min_test_score=min_test_score,
        max_gap=max_gap,
        rationale=rationale,
    )
