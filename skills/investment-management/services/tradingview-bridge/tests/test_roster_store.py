"""Tests for RosterStore (store.py)."""

from __future__ import annotations

from pathlib import Path
from sqlite3 import IntegrityError

import pytest

from tradingview_bridge.roster.store import RosterStore
from tradingview_bridge.roster.types import RosterEntry


def _entry(
    status: str = "proposed",
    family: str = "sma-crossover",
    name: str = "sma-crossover-5-20",
) -> RosterEntry:
    return RosterEntry(
        family=family,
        params={"fast": 5, "slow": 20},
        strategy_name=name,
        status=status,  # type: ignore[arg-type]
        train_score=0.6,
        test_score=0.8,
        generalization_gap=-0.2,
    )


@pytest.fixture
def store(tmp_path: Path) -> RosterStore:
    return RosterStore(db_path=tmp_path / "roster.sqlite")


async def test_record_and_get(store: RosterStore) -> None:
    new_id = await store.record(_entry())
    got = await store.get(new_id)
    assert got is not None
    assert got.entry_id == new_id
    assert got.params == {"fast": 5, "slow": 20}  # JSON round-trips ints
    assert got.status == "proposed"
    assert got.strategy_name == "sma-crossover-5-20"


async def test_get_missing_returns_none(store: RosterStore) -> None:
    assert await store.get(999) is None


async def test_list_filters_by_status_and_family(store: RosterStore) -> None:
    await store.record(_entry(status="proposed", family="sma-crossover"))
    await store.record(
        _entry(status="active", family="donchian-breakout", name="donchian-breakout-20")
    )
    assert len(await store.list_entries()) == 2
    assert len(await store.list_entries(status="proposed")) == 1
    assert len(await store.list_entries(family="donchian-breakout")) == 1


async def test_set_status_updates_decided_at_and_note(store: RosterStore) -> None:
    new_id = await store.record(_entry())
    await store.set_status(new_id, "active", note="promoted")
    got = await store.get(new_id)
    assert got is not None
    assert got.status == "active"
    assert got.decided_at is not None
    assert got.note == "promoted"


async def test_invalid_status_rejected_by_db(store: RosterStore) -> None:
    """The DB CHECK constraint refuses an out-of-vocabulary status."""
    with pytest.raises(IntegrityError):
        await store.record(_entry(status="bogus"))


async def test_active_entries(store: RosterStore) -> None:
    await store.record(_entry(status="proposed"))
    aid = await store.record(_entry(status="active", name="sma-crossover-10-50"))
    actives = await store.active_entries()
    assert len(actives) == 1
    assert actives[0].entry_id == aid


async def test_clear(store: RosterStore) -> None:
    await store.record(_entry())
    await store.clear()
    assert await store.list_entries() == []
