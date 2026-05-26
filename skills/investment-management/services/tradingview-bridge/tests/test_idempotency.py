"""Idempotency store tests — SQLite alert_id dedup."""

from __future__ import annotations

from pathlib import Path

import pytest

from tradingview_bridge.idempotency import IdempotencyStore


@pytest.mark.asyncio
async def test_first_insert_is_new(tmp_db_path: Path) -> None:
    store = IdempotencyStore(db_path=tmp_db_path)
    is_new, existing = await store.check_or_insert(
        alert_id="alert-1",
        broker="ibkr",
        order_id="ord-1",
    )
    assert is_new is True
    assert existing is None


@pytest.mark.asyncio
async def test_second_insert_hits_existing(tmp_db_path: Path) -> None:
    store = IdempotencyStore(db_path=tmp_db_path)
    await store.check_or_insert(alert_id="alert-1", broker="ibkr", order_id="ord-1")
    is_new, existing = await store.check_or_insert(
        alert_id="alert-1",
        broker="kraken",  # different broker on the duplicate — should NOT update
        order_id="ord-2",
    )
    assert is_new is False
    assert existing is not None
    assert existing.alert_id == "alert-1"
    assert existing.broker == "ibkr"  # original, not the duplicate's broker
    assert existing.order_id == "ord-1"


@pytest.mark.asyncio
async def test_different_alert_ids_are_independent(tmp_db_path: Path) -> None:
    store = IdempotencyStore(db_path=tmp_db_path)
    is_new_a, _ = await store.check_or_insert("alert-a", "ibkr", "ord-a")
    is_new_b, _ = await store.check_or_insert("alert-b", "ibkr", "ord-b")
    assert is_new_a is True
    assert is_new_b is True


@pytest.mark.asyncio
async def test_clear_removes_all(tmp_db_path: Path) -> None:
    store = IdempotencyStore(db_path=tmp_db_path)
    await store.check_or_insert("alert-1", "ibkr", "ord-1")
    await store.check_or_insert("alert-2", "kraken", "ord-2")
    await store.clear()
    is_new, _ = await store.check_or_insert("alert-1", "ibkr", "ord-1")
    assert is_new is True  # was cleared, now new again


@pytest.mark.asyncio
async def test_db_path_parent_created(tmp_path: Path) -> None:
    """IdempotencyStore creates the parent dir if missing."""
    deep_path = tmp_path / "nested" / "dir" / "idem.sqlite"
    assert not deep_path.parent.exists()
    store = IdempotencyStore(db_path=deep_path)
    await store.check_or_insert("alert-1", "ibkr", "ord-1")
    assert deep_path.exists()
