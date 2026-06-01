"""scheduled_search — adaptive-budget optimization via the UCB1 scheduler.

Allocates a fixed budget of grid-candidate evaluations across strategy families
using UCB1, concentrating spend on promising families instead of evaluating every
family's whole grid uniformly. The "what to optimize next" brain.

Honesty (same discipline as BRO-1277): the bandit explores the TRAIN segment only —
rewards are train scores. After the budget (or grid exhaustion), the single
best-by-train candidate is validated EXACTLY ONCE on the held-out TEST segment. No
test-set peeking; the evaluator (walk_forward + score_walk_forward) stays immutable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import structlog

from ..evaluation.score import score_walk_forward
from ..evaluation.walk_forward import walk_forward
from ..schemas import AssetClass
from ..strategy.types import Bar
from .egri import DEFAULT_MAX_GAP, DEFAULT_MIN_TEST_SCORE, DEFAULT_TRAIN_FRAC
from .scheduler import DEFAULT_UCB_C, ArmStat, UCB1Scheduler
from .search import grid_candidates
from .space import ParamSpace
from .types import ParamCandidate

log = structlog.get_logger("tradingview_bridge.optimize.scheduled_search")


@dataclass(frozen=True)
class ScheduledResult:
    """The result of a budget-scheduled optimization. Human-gated by construction."""

    symbol: str
    budget: int
    n_evaluated: int
    arms: list[ArmStat]  # per-family pulls + mean train reward (the allocation)
    best: ParamCandidate  # best by TRAIN score across everything evaluated
    best_family: str
    test_score: float  # the winner's OOS test score (computed once)
    generalization_gap: float
    generalizes: bool
    rationale: str
    requires_human_approval: bool = True

    def __post_init__(self) -> None:
        if self.requires_human_approval is not True:
            raise ValueError(
                "requires_human_approval must be True — promotion to live capital is human-gated"
            )


def _train_score(
    space: ParamSpace,
    params: dict[str, int],
    bars: list[Bar],
    *,
    symbol: str,
    asset_class: AssetClass,
    n_windows: int,
    periods_per_year: int,
) -> float:
    """The immutable evaluator, on the train segment → overall score in [0, 1]."""
    wf = walk_forward(
        space.factory(params),
        bars,
        symbol=symbol,
        asset_class=asset_class,
        n_windows=n_windows,
        periods_per_year=periods_per_year,
    )
    return score_walk_forward(wf).overall


def scheduled_optimize(
    spaces: Sequence[ParamSpace],
    bars: list[Bar],
    *,
    symbol: str,
    asset_class: AssetClass,
    budget: int,
    train_frac: float = DEFAULT_TRAIN_FRAC,
    n_windows: int = 4,
    periods_per_year: int = 252,
    min_test_score: float = DEFAULT_MIN_TEST_SCORE,
    max_gap: float = DEFAULT_MAX_GAP,
    ucb_c: float = DEFAULT_UCB_C,
) -> ScheduledResult:
    """UCB1-schedule ``budget`` candidate-evaluations across ``spaces``. Pure, no I/O."""
    if budget < 1:
        raise ValueError("budget must be >= 1")
    if not spaces:
        raise ValueError("no spaces to schedule over")
    split = int(len(bars) * train_frac)
    train_bars, test_bars = bars[:split], bars[split:]
    need = n_windows * 2
    if len(train_bars) < need or len(test_bars) < need:
        raise ValueError(
            f"need >= {need} bars in each of train ({len(train_bars)}) and test "
            f"({len(test_bars)}) for {n_windows} windows; supply more bars or lower "
            f"n_windows / move train_frac toward 0.5"
        )

    # Per-family candidate queues (deterministic order), empty families dropped.
    queues: dict[str, list[dict[str, int]]] = {}
    space_by_family: dict[str, ParamSpace] = {}
    for space in spaces:
        candidates = grid_candidates(space)
        if candidates:
            queues[space.family] = candidates
            space_by_family[space.family] = space
    if not queues:
        raise ValueError("all spaces produced no valid candidates")
    cursor: dict[str, int] = dict.fromkeys(queues, 0)

    scheduler = UCB1Scheduler(list(queues), c=ucb_c)
    evaluated: list[tuple[str, ParamCandidate]] = []
    while len(evaluated) < budget:
        available = [f for f in queues if cursor[f] < len(queues[f])]
        if not available:
            break  # every grid exhausted before the budget ran out
        family = scheduler.select(available)
        params = queues[family][cursor[family]]
        cursor[family] += 1
        space = space_by_family[family]
        score = _train_score(
            space,
            params,
            train_bars,
            symbol=symbol,
            asset_class=asset_class,
            n_windows=n_windows,
            periods_per_year=periods_per_year,
        )
        scheduler.update(family, score)
        evaluated.append(
            (
                family,
                ParamCandidate(
                    params=params, strategy_name=space.factory(params).name, train_score=score
                ),
            )
        )

    # Best by TRAIN score. Tie-break: name, then the full params (some families —
    # e.g. RSI — share a strategy_name across band variants, so params is the
    # collision-proof final key; the choice never depends on insertion order).
    best_family, best = min(
        evaluated,
        key=lambda fc: (
            -fc[1].train_score,
            fc[1].strategy_name,
            tuple(sorted(fc[1].params.items())),
        ),
    )

    # Validate the winner ONCE on the held-out TEST segment (no test-set selection).
    test_score = _train_score(
        space_by_family[best_family],
        best.params,
        test_bars,
        symbol=symbol,
        asset_class=asset_class,
        n_windows=n_windows,
        periods_per_year=periods_per_year,
    )
    gap = best.train_score - test_score
    generalizes = test_score >= min_test_score and gap <= max_gap
    verdict = "generalizes" if generalizes else "does NOT generalize"
    rationale = (
        f"scheduled {len(evaluated)}/{budget} evals across {len(queues)} families; winner "
        f"{best.strategy_name} (family {best_family}) train {best.train_score:.3f} → test "
        f"{test_score:.3f}, gap {gap:+.3f} — {verdict} (floor {min_test_score:.2f}, "
        f"max gap {max_gap:.2f}). Human approval required before promotion."
    )

    log.info(
        "scheduled_optimize_done",
        symbol=symbol,
        budget=budget,
        n_evaluated=len(evaluated),
        best=best.strategy_name,
        best_family=best_family,
        test=round(test_score, 3),
        generalizes=generalizes,
    )
    return ScheduledResult(
        symbol=symbol,
        budget=budget,
        n_evaluated=len(evaluated),
        arms=scheduler.stats(),
        best=best,
        best_family=best_family,
        test_score=test_score,
        generalization_gap=gap,
        generalizes=generalizes,
        rationale=rationale,
    )
