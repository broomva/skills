"""OrderLedger tests — persistence, position replay, canary filtering."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tradingview_bridge.orders import CANARY_PREFIX, OrderLedger


async def _append(
    ledger: OrderLedger,
    *,
    symbol: str,
    action: str,
    size: str,
    strategy: str = "s1",
    order_id: str = "o1",
) -> bool:
    return await ledger.append(
        order_id=order_id,
        alert_id="a1",
        strategy_name=strategy,
        broker="ibkr",
        asset_class="stock",
        symbol=symbol,
        action=action,
        size=Decimal(size),
        paper=True,
    )


@pytest.mark.asyncio
async def test_append_and_all_orders(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    wrote = await _append(ledger, symbol="AAPL", action="buy", size="10")
    assert wrote is True
    orders = await ledger.all_orders()
    assert len(orders) == 1
    assert orders[0].symbol == "AAPL"
    assert orders[0].size == Decimal("10")


@pytest.mark.asyncio
async def test_canary_orders_filtered(tmp_orders_db_path: Path) -> None:
    """Orders whose strategy_name starts with the canary prefix are never written."""
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    wrote = await _append(
        ledger, symbol="__CANARY__", action="buy", size="1", strategy=f"{CANARY_PREFIX}-operator"
    )
    assert wrote is False
    assert await ledger.all_orders() == []


@pytest.mark.asyncio
async def test_net_positions_buy_sell(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _append(ledger, symbol="AAPL", action="buy", size="10", order_id="o1")
    await _append(ledger, symbol="AAPL", action="buy", size="5", order_id="o2")
    await _append(ledger, symbol="AAPL", action="sell", size="3", order_id="o3")
    net = await ledger.net_positions()
    assert net == {"AAPL": Decimal("12")}


@pytest.mark.asyncio
async def test_net_positions_zero_omitted(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _append(ledger, symbol="AAPL", action="buy", size="10", order_id="o1")
    await _append(ledger, symbol="AAPL", action="sell", size="10", order_id="o2")
    net = await ledger.net_positions()
    assert net == {}  # net zero → omitted


@pytest.mark.asyncio
async def test_net_positions_close(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _append(ledger, symbol="AAPL", action="buy", size="10", order_id="o1")
    await _append(ledger, symbol="AAPL", action="close", size="0", order_id="o2")
    net = await ledger.net_positions()
    assert net == {}


@pytest.mark.asyncio
async def test_net_positions_flatten(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _append(ledger, symbol="AAPL", action="buy", size="10", order_id="o1")
    await _append(ledger, symbol="MSFT", action="buy", size="7", order_id="o2")
    await _append(ledger, symbol="AAPL", action="flatten", size="0", order_id="o3")
    net = await ledger.net_positions()
    assert net == {}  # flatten zeros ALL symbols


@pytest.mark.asyncio
async def test_multi_symbol_independent(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _append(ledger, symbol="AAPL", action="buy", size="10", order_id="o1")
    await _append(ledger, symbol="MSFT", action="buy", size="7", order_id="o2")
    await _append(ledger, symbol="MSFT", action="sell", size="2", order_id="o3")
    net = await ledger.net_positions()
    assert net == {"AAPL": Decimal("10"), "MSFT": Decimal("5")}


@pytest.mark.asyncio
async def test_clear(tmp_orders_db_path: Path) -> None:
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    await _append(ledger, symbol="AAPL", action="buy", size="10")
    await ledger.clear()
    assert await ledger.all_orders() == []


@pytest.mark.asyncio
async def test_db_parent_created(tmp_path: Path) -> None:
    deep = tmp_path / "nested" / "dir" / "orders.sqlite"
    assert not deep.parent.exists()
    ledger = OrderLedger(db_path=deep)
    await _append(ledger, symbol="AAPL", action="buy", size="1")
    assert deep.exists()
