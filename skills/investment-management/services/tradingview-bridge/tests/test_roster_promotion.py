"""Tests for the two human gates (promotion.py) — the safety heart of the loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from tradingview_bridge.barsource import synthetic_bars
from tradingview_bridge.optimize.egri import optimize_walk_forward
from tradingview_bridge.optimize.space import SMA_CROSSOVER_SPACE
from tradingview_bridge.optimize.types import OptimizationResult
from tradingview_bridge.roster.promotion import (
    active_roster,
    promote,
    propose_from_optimization,
    reject,
)
from tradingview_bridge.roster.store import RosterStore
from tradingview_bridge.roster.types import RosterEntry
from tradingview_bridge.strategy.library import SMACrossover


def _result(**kw: object) -> OptimizationResult:
    return optimize_walk_forward(
        SMA_CROSSOVER_SPACE,
        synthetic_bars(500),
        symbol="AAPL",
        asset_class="stock",
        **kw,  # type: ignore[arg-type]
    )


@pytest.fixture
def store(tmp_path: Path) -> RosterStore:
    return RosterStore(db_path=tmp_path / "roster.sqlite")


# --- propose: automatic, OOS-gated, NEVER active ---------------------------


def test_propose_yields_proposed_never_active() -> None:
    result = _result()
    assert result.generalizes is True
    entry = propose_from_optimization(result)
    assert entry is not None
    assert entry.status == "proposed"  # THE gate — propose can never yield 'active'
    assert entry.strategy_name == result.best.strategy_name
    assert entry.test_score == result.test_score


def test_propose_returns_none_when_not_generalizes() -> None:
    result = _result(min_test_score=1.5)  # impossible floor → does not generalize
    assert result.generalizes is False
    assert propose_from_optimization(result) is None  # overfit winners are never proposed


def test_propose_can_override_generalizes_gate() -> None:
    entry = propose_from_optimization(_result(min_test_score=1.5), require_generalizes=False)
    assert entry is not None
    assert entry.status == "proposed"


# --- promote / reject: the human gates -------------------------------------


async def test_promote_activates_and_supersedes_sibling(store: RosterStore) -> None:
    e1 = propose_from_optimization(_result())
    assert e1 is not None
    id1 = await store.record(e1)
    e2 = RosterEntry(
        family="sma-crossover",
        params={"fast": 10, "slow": 50},
        strategy_name="sma-crossover-10-50",
        status="proposed",
        train_score=0.5,
        test_score=0.6,
        generalization_gap=-0.1,
    )
    id2 = await store.record(e2)

    await promote(store, id1)
    await promote(store, id2)  # promoting the second supersedes the first

    actives = await store.active_entries()
    assert len(actives) == 1  # exactly one active per family
    assert actives[0].entry_id == id2
    superseded = await store.get(id1)
    assert superseded is not None
    assert superseded.status == "superseded"


async def test_promote_rejects_non_proposed(store: RosterStore) -> None:
    e1 = propose_from_optimization(_result())
    assert e1 is not None
    id1 = await store.record(e1)
    await promote(store, id1)
    with pytest.raises(ValueError, match="only a 'proposed'"):
        await promote(store, id1)  # already active → cannot re-promote


async def test_promote_missing_raises(store: RosterStore) -> None:
    with pytest.raises(ValueError, match="no roster entry"):
        await promote(store, 999)


async def test_reject(store: RosterStore) -> None:
    e1 = propose_from_optimization(_result())
    assert e1 is not None
    id1 = await store.record(e1)
    await reject(store, id1, note="not now")
    got = await store.get(id1)
    assert got is not None
    assert got.status == "rejected"
    assert got.note == "not now"


# --- active_roster: reconstruct, fall back, skip unknown -------------------


def test_active_roster_falls_back_when_empty() -> None:
    fallback = [SMACrossover(5, 20)]
    assert active_roster([], fallback=fallback) is fallback


def test_active_roster_reconstructs_strategies() -> None:
    entry = RosterEntry(
        family="sma-crossover",
        params={"fast": 10, "slow": 50},
        strategy_name="sma-crossover-10-50",
        status="active",
        train_score=0.6,
        test_score=0.7,
        generalization_gap=-0.1,
    )
    strategies = active_roster([entry], fallback=[SMACrossover(5, 20)])
    assert len(strategies) == 1
    assert strategies[0].name == "sma-crossover-10-50"


def test_active_roster_skips_unknown_family_and_falls_back() -> None:
    entry = RosterEntry(
        family="not-a-family",
        params={"x": 1},
        strategy_name="x",
        status="active",
        train_score=0.5,
        test_score=0.5,
        generalization_gap=0.0,
    )
    fallback = [SMACrossover(5, 20)]
    assert active_roster([entry], fallback=fallback) is fallback  # unknown skipped → fallback
