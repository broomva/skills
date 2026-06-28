"""Dispatcher routing tests — PR 2 wires real clients (mock mode in tests)."""

from __future__ import annotations

import pytest

from tradingview_bridge.clients import MockClient
from tradingview_bridge.clients.base import BrokerClient, BrokerName
from tradingview_bridge.dispatch import Dispatcher, route_asset_class
from tradingview_bridge.schemas import TVAlert


def _all_mock_clients() -> dict[BrokerName, BrokerClient]:
    return {
        "ibkr": MockClient("ibkr"),
        "kraken": MockClient("kraken"),
        "polymarket": MockClient("polymarket"),
    }


@pytest.mark.parametrize(
    ("asset_class", "expected_broker"),
    [
        ("stock", "ibkr"),
        ("etf", "ibkr"),
        ("bond", "ibkr"),
        ("fx", "ibkr"),
        ("crypto", "kraken"),
        ("prediction", "polymarket"),
    ],
)
def test_route_asset_class(asset_class: str, expected_broker: str) -> None:
    assert route_asset_class(asset_class) == expected_broker  # type: ignore[arg-type]


def test_route_asset_class_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown asset class"):
        route_asset_class("options")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dispatch_stock_returns_accepted_ibkr(
    valid_alert_body: dict[str, object],
) -> None:
    alert = TVAlert(**valid_alert_body)
    dispatcher = Dispatcher(clients_override=_all_mock_clients())
    result = await dispatcher.dispatch(alert)
    assert result.status == "accepted"
    assert result.broker == "ibkr"
    assert result.alert_id == "test-alert-001"
    assert result.order_id is not None
    assert result.order_id.startswith("mock-")


@pytest.mark.asyncio
async def test_dispatch_crypto_routes_to_kraken(
    valid_alert_body: dict[str, object],
) -> None:
    valid_alert_body["asset_class"] = "crypto"
    valid_alert_body["symbol"] = "BTC/USD"
    alert = TVAlert(**valid_alert_body)
    dispatcher = Dispatcher(clients_override=_all_mock_clients())
    result = await dispatcher.dispatch(alert)
    assert result.status == "accepted"
    assert result.broker == "kraken"


@pytest.mark.asyncio
async def test_dispatch_prediction_routes_to_polymarket(
    valid_alert_body: dict[str, object],
) -> None:
    valid_alert_body["asset_class"] = "prediction"
    valid_alert_body["symbol"] = "0xMARKET"
    alert = TVAlert(**valid_alert_body)
    dispatcher = Dispatcher(clients_override=_all_mock_clients())
    result = await dispatcher.dispatch(alert)
    assert result.status == "accepted"
    assert result.broker == "polymarket"


@pytest.mark.asyncio
async def test_dispatch_records_order_in_client(
    valid_alert_body: dict[str, object],
) -> None:
    """The MockClient records orders; verify the dispatcher delivers them."""
    clients = _all_mock_clients()
    dispatcher = Dispatcher(clients_override=clients)
    alert = TVAlert(**valid_alert_body)

    result = await dispatcher.dispatch(alert)
    assert result.status == "accepted"

    ibkr_mock = clients["ibkr"]
    assert isinstance(ibkr_mock, MockClient)
    assert len(ibkr_mock.placed_orders) == 1
    assert ibkr_mock.placed_orders[0].alert_id == "test-alert-001"
    assert ibkr_mock.placed_orders[0].symbol == "AAPL"


@pytest.mark.asyncio
async def test_health_check_aggregates_per_broker(
    valid_alert_body: dict[str, object],
) -> None:
    clients = _all_mock_clients()
    dispatcher = Dispatcher(clients_override=clients)
    health = await dispatcher.health_check()
    assert health == {"ibkr": True, "kraken": True, "polymarket": True}


# ---- active_broker_client (for operator reconciliation) -----------------


def test_active_broker_client_none_in_mock_mode() -> None:
    from tradingview_bridge.dispatch import Dispatcher

    assert Dispatcher(broker_mode="mock").active_broker_client() is None


def test_active_broker_client_is_tv_paper_in_tv_paper_mode() -> None:
    from tradingview_bridge.dispatch import Dispatcher

    client = Dispatcher(broker_mode="tradingview-paper").active_broker_client()
    assert client is not None
    assert client.broker_name == "tradingview-paper"
    # exposes the real-book reader the operator reconciles against
    assert hasattr(client, "list_positions")
