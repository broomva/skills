"""Tests for the orchestrator ↔ roster integration (orchestrator/cli._resolve_roster)."""

from __future__ import annotations

import argparse
from pathlib import Path

from tradingview_bridge.barsource import synthetic_bars
from tradingview_bridge.optimize.egri import optimize_walk_forward
from tradingview_bridge.optimize.space import SMA_CROSSOVER_SPACE
from tradingview_bridge.orchestrator.cli import _resolve_roster, default_roster
from tradingview_bridge.roster.promotion import promote, propose_from_optimization
from tradingview_bridge.roster.store import RosterStore


async def test_resolve_roster_without_db_uses_defaults() -> None:
    roster = await _resolve_roster(argparse.Namespace(roster_db=None))
    assert [s.name for s in roster] == [s.name for s in default_roster()]


async def test_resolve_roster_with_empty_db_falls_back(tmp_path: Path) -> None:
    db = tmp_path / "roster.sqlite"
    roster = await _resolve_roster(argparse.Namespace(roster_db=str(db)))
    assert [s.name for s in roster] == [s.name for s in default_roster()]


async def test_resolve_roster_with_active_uses_promoted_params(tmp_path: Path) -> None:
    db = tmp_path / "roster.sqlite"
    store = RosterStore(db_path=db)
    result = optimize_walk_forward(
        SMA_CROSSOVER_SPACE, synthetic_bars(500), symbol="AAPL", asset_class="stock"
    )
    entry = propose_from_optimization(result)
    assert entry is not None
    new_id = await store.record(entry)
    await promote(store, new_id)  # the human gate

    roster = await _resolve_roster(argparse.Namespace(roster_db=str(db)))
    assert len(roster) == 1
    assert (
        roster[0].name == result.best.strategy_name
    )  # the orchestrator now measures the optimized params
