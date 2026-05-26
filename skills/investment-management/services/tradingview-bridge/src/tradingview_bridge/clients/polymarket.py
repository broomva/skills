"""PolymarketClient — prediction markets via py-clob-client.

PR 2 ships this as a SKELETON. Real-paper wiring (PR 2b) requires a
wallet private key (signs CLOB orders) — that's a separate onboarding
flow from IBKR/Kraken because Polymarket uses on-chain settlement.
"""

from __future__ import annotations

import os

import structlog

from ..schemas import TVAlert
from .base import BrokerClient, BrokerName, NotConfiguredError, OrderReceipt
from .mock import MockClient

log = structlog.get_logger("tradingview_bridge.clients.polymarket")


def _polymarket_creds_present() -> bool:
    """Wallet key + CLOB host both required for real-paper Polymarket."""
    return bool(os.environ.get("TVBRIDGE_POLYMARKET_WALLET_KEY")) and bool(
        os.environ.get("TVBRIDGE_POLYMARKET_CLOB_HOST")
    )


class PolymarketClient(BrokerClient):
    """Polymarket CLOB client. PR 2: skeleton + delegate-to-mock fallback."""

    def __init__(self, broker_mode: str = "mock") -> None:
        self._mode = broker_mode
        self._mock: MockClient | None = None
        if broker_mode == "mock":
            self._mock = MockClient("polymarket")

    @property
    def broker_name(self) -> BrokerName:
        return "polymarket"

    async def place_order(self, alert: TVAlert) -> OrderReceipt:
        if self._mode == "mock" and self._mock is not None:
            return await self._mock.place_order(alert)

        if not _polymarket_creds_present():
            raise NotConfiguredError(
                "Polymarket real-paper mode requires "
                "TVBRIDGE_POLYMARKET_WALLET_KEY (eth private key, hex) + "
                "TVBRIDGE_POLYMARKET_CLOB_HOST (default https://clob.polymarket.com). "
                "Use TVBRIDGE_BROKER_MODE=mock for tests."
            )
        # PR 2b would: ClobClient(host, key=...); place_order(condition_id,
        # outcome=..., side=..., price=..., size=...); map to OrderReceipt.
        raise NotImplementedError(
            "PR 2b — py-clob-client wiring deferred. Mock path covers PR 2 tests."
        )

    async def health_check(self) -> bool:
        if self._mock is not None:
            return await self._mock.health_check()
        return _polymarket_creds_present()
