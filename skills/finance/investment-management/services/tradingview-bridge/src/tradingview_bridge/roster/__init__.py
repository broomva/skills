"""Roster promotion — the registry that closes the self-improving loop (human-gated).

The optimizer finds better params with an out-of-sample estimate; this registry is
where those params wait for a human to promote them into the roster the orchestrator
measures. Two independent human gates stand between an optimizer result and capital:

  optimizer → propose (auto, OOS-gated) → proposed
                                          → promote (HUMAN) → active
  orchestrator measures active params → recommendation (still human-gated) → capital

  store.py     — RosterStore: persistent registry (async SQLite).
  promotion.py — propose_from_optimization / promote / reject / active_roster.
  types.py     — RosterEntry / RosterStatus.
  cli.py       — the `roster` entry point.
"""

from .promotion import active_roster, promote, propose_from_optimization, reject
from .store import RosterStore, default_roster_db_path
from .types import RosterEntry, RosterStatus

__all__ = [
    "RosterEntry",
    "RosterStatus",
    "RosterStore",
    "active_roster",
    "default_roster_db_path",
    "promote",
    "propose_from_optimization",
    "reject",
]
