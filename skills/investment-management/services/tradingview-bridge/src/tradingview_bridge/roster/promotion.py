"""Promotion logic — the two human gates made concrete.

``propose_from_optimization`` is AUTOMATIC: it turns an optimizer result into a
*proposed* roster entry — but only if the result cleared the out-of-sample holdout
(`generalizes`). It can NEVER return an active entry; status is always 'proposed'.

``promote`` / ``reject`` are the HUMAN gates (driven by the `roster` CLI). The
orchestrator only ever measures `active` entries, and even then its allocation
recommendation stays human-gated — so two independent human decisions stand
between an optimizer result and any capital:

    optimizer → [propose: auto, OOS-gated] → proposed
                                              → [promote: HUMAN] → active
    orchestrator measures active params → recommendation (requires_human_approval)
                                              → [allocate: HUMAN] → capital
"""

from __future__ import annotations

import structlog

from ..optimize.space import BUILTIN_SPACES
from ..optimize.types import OptimizationResult
from ..strategy.base import Strategy
from .store import RosterStore
from .types import RosterEntry

log = structlog.get_logger("tradingview_bridge.roster.promotion")


def propose_from_optimization(
    result: OptimizationResult, *, require_generalizes: bool = True
) -> RosterEntry | None:
    """Build a *proposed* roster entry from an optimization result.

    Returns None when the result did not generalize (and ``require_generalizes``)
    — overfit winners are never proposed. The returned entry is ALWAYS
    ``status='proposed'``; this function cannot create an active entry.
    """
    if require_generalizes and not result.generalizes:
        return None
    return RosterEntry(
        family=result.family,
        params=dict(result.best.params),
        strategy_name=result.best.strategy_name,
        status="proposed",
        train_score=result.best.train_score,
        test_score=result.test_score,
        generalization_gap=result.generalization_gap,
        note=(
            f"proposed from optimization: test {result.test_score:.3f}, "
            f"gap {result.generalization_gap:+.3f}"
        ),
    )


async def promote(store: RosterStore, entry_id: int) -> RosterEntry:
    """HUMAN gate: move a *proposed* entry to active, superseding any prior active
    entry of the same family (so exactly one param-set is active per family).

    Raises if the entry doesn't exist or isn't currently 'proposed' — you cannot
    promote something that was rejected/superseded without re-proposing it.
    """
    entry = await store.get(entry_id)
    if entry is None:
        raise ValueError(f"no roster entry with id {entry_id}")
    if entry.status != "proposed":
        raise ValueError(
            f"entry {entry_id} is '{entry.status}'; only a 'proposed' entry can be promoted"
        )
    for active in await store.list_entries(status="active", family=entry.family):
        if active.entry_id is not None:
            await store.set_status(
                active.entry_id, "superseded", note=f"superseded by entry {entry_id}"
            )
    await store.set_status(entry_id, "active", note="promoted by human")
    promoted = await store.get(entry_id)
    assert promoted is not None
    log.info("roster_promoted", id=entry_id, family=entry.family, strategy=entry.strategy_name)
    return promoted


async def reject(store: RosterStore, entry_id: int, *, note: str = "") -> RosterEntry:
    """HUMAN gate: decline an entry."""
    entry = await store.get(entry_id)
    if entry is None:
        raise ValueError(f"no roster entry with id {entry_id}")
    await store.set_status(entry_id, "rejected", note=note or "rejected by human")
    rejected = await store.get(entry_id)
    assert rejected is not None
    return rejected


def active_roster(entries: list[RosterEntry], *, fallback: list[Strategy]) -> list[Strategy]:
    """Reconstruct the active strategy roster from active entries.

    Falls back to the injected built-in roster when there are no usable active
    entries. The fallback is a PARAMETER (not an import) so this module never
    depends on the orchestrator — keeping the dependency one-directional.
    """
    strategies: list[Strategy] = []
    for entry in entries:
        space = BUILTIN_SPACES.get(entry.family)
        if space is None:
            log.warning("roster_unknown_family", family=entry.family, strategy=entry.strategy_name)
            continue
        strategies.append(space.factory(entry.params))
    return strategies or fallback
