"""MockClient tests — the broker simulation used by every other test."""

from __future__ import annotations

from datetime import UTC

import pytest

from tradingview_bridge.clients import MockClient
from tradingview_bridge.schemas import TVAlert


@pytest.mark.asyncio
async def test_mock_returns_synthetic_receipt(
    valid_alert_body: dict[str, object],
) -> None:
    client = MockClient("ibkr")
    alert = TVAlert(**valid_alert_body)
    receipt = await client.place_order(alert)

    assert receipt.broker == "ibkr"
    assert receipt.alert_id == "test-alert-001"
    assert receipt.symbol == "AAPL"
    assert receipt.action == "buy"
    assert receipt.paper is True
    assert receipt.order_id.startswith("mock-")
    assert len(receipt.order_id) > len("mock-")


@pytest.mark.asyncio
async def test_mock_records_orders(
    valid_alert_body: dict[str, object],
) -> None:
    client = MockClient("kraken")
    alert = TVAlert(**valid_alert_body)
    await client.place_order(alert)
    await client.place_order(alert)
    assert len(client.placed_orders) == 2


@pytest.mark.asyncio
async def test_mock_clear() -> None:
    client = MockClient("ibkr")
    # Manually inject a fake receipt to test clear() without going through place_order
    from datetime import datetime
    from decimal import Decimal

    from tradingview_bridge.clients.base import OrderReceipt

    client.placed_orders.append(
        OrderReceipt(
            broker="ibkr",
            order_id="mock-xyz",
            alert_id="x",
            symbol="x",
            action="buy",
            size=Decimal("1"),
            submitted_at=datetime.now(tz=UTC),
            paper=True,
        )
    )
    assert len(client.placed_orders) == 1
    client.clear()
    assert client.placed_orders == []


@pytest.mark.asyncio
async def test_mock_health_check_always_true() -> None:
    assert await MockClient("ibkr").health_check() is True
    assert await MockClient("kraken").health_check() is True
    assert await MockClient("polymarket").health_check() is True


def test_mock_broker_name_persists() -> None:
    assert MockClient("ibkr").broker_name == "ibkr"
    assert MockClient("kraken").broker_name == "kraken"
    assert MockClient("polymarket").broker_name == "polymarket"
