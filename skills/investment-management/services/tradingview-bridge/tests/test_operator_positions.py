"""PositionManager tests — net positions, count, drift."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tradingview_bridge.operator.positions import PositionManager
from tradingview_bridge.orders import OrderLedger


async def _buy(ledger: OrderLedger, symbol: str, size: str, oid: str) -> None:
    await ledger.append(
        order_id=oid,
        alert_id="a",
        strategy_name="s",
        broker="ibkr",
        asset_class="stock",
        symbol=symbol,
        action="buy",
        size=Decimal(size),
        paper=True,
    )


@pytest.mark.asyncio
async def test_net_positions_passthrough(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _buy(ledger, "AAPL", "10", "o1")
    pm = PositionManager(ledger)
    assert await pm.net_positions() == {"AAPL": Decimal("10")}


@pytest.mark.asyncio
async def test_open_position_count(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _buy(ledger, "AAPL", "10", "o1")
    await _buy(ledger, "MSFT", "5", "o2")
    pm = PositionManager(ledger)
    assert await pm.open_position_count() == 2


@pytest.mark.asyncio
async def test_drift_empty_without_target(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _buy(ledger, "AAPL", "10", "o1")
    pm = PositionManager(ledger)  # no target
    assert await pm.drift() == []


@pytest.mark.asyncio
async def test_drift_computes_delta(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _buy(ledger, "AAPL", "10", "o1")
    pm = PositionManager(ledger, target_allocation={"AAPL": Decimal("15")})
    drifts = await pm.drift()
    assert len(drifts) == 1
    d = drifts[0]
    assert d.symbol == "AAPL"
    assert d.current == Decimal("10")
    assert d.target == Decimal("15")
    assert d.delta == Decimal("5")  # need to buy 5 more


@pytest.mark.asyncio
async def test_drift_omits_aligned_symbols(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _buy(ledger, "AAPL", "15", "o1")
    pm = PositionManager(ledger, target_allocation={"AAPL": Decimal("15")})
    assert await pm.drift() == []  # current == target → no drift


@pytest.mark.asyncio
async def test_drift_flags_unwanted_position(tmp_orders_db_path: Path) -> None:
    """A held symbol with target 0 should surface a sell delta."""
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _buy(ledger, "AAPL", "10", "o1")
    pm = PositionManager(ledger, target_allocation={"MSFT": Decimal("5")})
    drifts = {d.symbol: d for d in await pm.drift()}
    assert drifts["AAPL"].delta == Decimal("-10")  # sell all AAPL
    assert drifts["MSFT"].delta == Decimal("5")  # buy MSFT
