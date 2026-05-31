"""Grid search over a ParamSpace — deterministic candidate enumeration.

v1 is exhaustive grid search: the Cartesian product of the grid, filtered by the
space's validity constraint. Deterministic (sorted key order → stable candidate
order) so an optimization run is reproducible. Evolutionary / Bayesian search is a
later layer; grid is the honest baseline.
"""

from __future__ import annotations

import itertools

import structlog

from .space import ParamSpace

log = structlog.get_logger("tradingview_bridge.optimize.search")


def grid_candidates(
    space: ParamSpace, *, max_candidates: int | None = None
) -> list[dict[str, int]]:
    """Enumerate valid param-sets for ``space``.

    If ``max_candidates`` is set and the grid is larger, the list is truncated
    deterministically and the drop is logged — never silently capped (P11).
    """
    keys = sorted(space.grid)  # deterministic key order
    out: list[dict[str, int]] = []
    for combo in itertools.product(*(space.grid[k] for k in keys)):
        params = dict(zip(keys, combo, strict=True))
        if space.constraint is None or space.constraint(params):
            out.append(params)
    if max_candidates is not None and len(out) > max_candidates:
        log.warning(
            "grid_truncated",
            family=space.family,
            kept=max_candidates,
            dropped=len(out) - max_candidates,
        )
        out = out[:max_candidates]
    return out
