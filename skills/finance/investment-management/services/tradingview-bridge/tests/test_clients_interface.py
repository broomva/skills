"""Cross-client interface tests — IBKR/Kraken/Polymarket conform to BrokerClient.

These tests do NOT exercise real broker connections (no creds in CI).
They verify:
- Mock mode works for all three real clients (delegate-to-mock path)
- Real-paper mode without creds raises NotConfiguredError cleanly
- Helper static methods (symbol normalization, contract mapping) behave correctly
"""

from __future__ import annotations

import pytest

from tradingview_bridge.clients import IBKRClient, KrakenClient, PolymarketClient
from tradingview_bridge.clients.base import BrokerClient, NotConfiguredError
from tradingview_bridge.schemas import TVAlert


@pytest.fixture(params=[IBKRClient, KrakenClient, PolymarketClient])
def real_client_class(request: pytest.FixtureRequest) -> type[BrokerClient]:
    return request.param  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_real_client_mock_mode_places_order(
    real_client_class: type[BrokerClient],
    valid_alert_body: dict[str, object],
) -> None:
    """In mock mode every real client should delegate to MockClient."""
    client = real_client_class(broker_mode="mock")  # type: ignore[call-arg]
    # Need to use the right asset_class for each broker
    if isinstance(client, KrakenClient):
        valid_alert_body["asset_class"] = "crypto"
        valid_alert_body["symbol"] = "BTC/USD"
    elif isinstance(client, PolymarketClient):
        valid_alert_body["asset_class"] = "prediction"
        valid_alert_body["symbol"] = "0xMARKET"
    alert = TVAlert(**valid_alert_body)
    receipt = await client.place_order(alert)
    assert receipt.broker == client.broker_name
    assert receipt.order_id.startswith("mock-")
    assert receipt.paper is True


@pytest.mark.asyncio
async def test_real_client_real_paper_without_creds_raises(
    real_client_class: type[BrokerClient],
    valid_alert_body: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real-paper mode without credentials should raise NotConfiguredError.

    Unset every broker cred env var first to guarantee a clean test.
    """
    for env_var in [
        "TVBRIDGE_IBKR_HOST",
        "TVBRIDGE_IBKR_PORT",
        "TVBRIDGE_KRAKEN_API_KEY",
        "TVBRIDGE_KRAKEN_API_SECRET",
        "TVBRIDGE_POLYMARKET_WALLET_KEY",
        "TVBRIDGE_POLYMARKET_CLOB_HOST",
    ]:
        monkeypatch.delenv(env_var, raising=False)

    client = real_client_class(broker_mode="real-paper")  # type: ignore[call-arg]

    if isinstance(client, KrakenClient):
        valid_alert_body["asset_class"] = "crypto"
        valid_alert_body["symbol"] = "BTC/USD"
    elif isinstance(client, PolymarketClient):
        valid_alert_body["asset_class"] = "prediction"
        valid_alert_body["symbol"] = "0xMARKET"
    alert = TVAlert(**valid_alert_body)

    with pytest.raises(NotConfiguredError):
        await client.place_order(alert)


@pytest.mark.asyncio
async def test_health_check_reflects_creds_presence_real_paper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without creds, real-paper clients report unhealthy."""
    for env_var in [
        "TVBRIDGE_IBKR_HOST",
        "TVBRIDGE_IBKR_PORT",
        "TVBRIDGE_KRAKEN_API_KEY",
        "TVBRIDGE_KRAKEN_API_SECRET",
        "TVBRIDGE_POLYMARKET_WALLET_KEY",
        "TVBRIDGE_POLYMARKET_CLOB_HOST",
    ]:
        monkeypatch.delenv(env_var, raising=False)

    assert await IBKRClient(broker_mode="real-paper").health_check() is False
    assert await KrakenClient(broker_mode="real-paper").health_check() is False
    assert await PolymarketClient(broker_mode="real-paper").health_check() is False


def test_ibkr_contract_mapping() -> None:
    assert IBKRClient.map_asset_class_to_contract("stock") == {
        "secType": "STK",
        "exchange": "SMART",
        "currency": "USD",
    }
    assert IBKRClient.map_asset_class_to_contract("etf") == {
        "secType": "STK",
        "exchange": "SMART",
        "currency": "USD",
    }
    assert IBKRClient.map_asset_class_to_contract("bond") == {
        "secType": "BOND",
        "exchange": "SMART",
        "currency": "USD",
    }
    assert IBKRClient.map_asset_class_to_contract("fx") == {
        "secType": "CASH",
        "exchange": "IDEALPRO",
        "currency": "USD",
    }


def test_ibkr_contract_mapping_rejects_unsupported() -> None:
    with pytest.raises(ValueError, match="does not route"):
        IBKRClient.map_asset_class_to_contract("crypto")  # type: ignore[arg-type]


def test_kraken_symbol_normalization_idempotent() -> None:
    assert KrakenClient.normalize_symbol("BTC/USD") == "BTC/USD"
    assert KrakenClient.normalize_symbol("eth/usdt") == "ETH/USDT"


def test_kraken_symbol_normalization_inserts_slash() -> None:
    assert KrakenClient.normalize_symbol("BTCUSD") == "BTC/USD"
    assert KrakenClient.normalize_symbol("ETHUSDT") == "ETH/USDT"
    assert KrakenClient.normalize_symbol("solusd") == "SOL/USD"
