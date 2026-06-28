"""KrakenClient — Kraken Pro via ccxt sandbox / kraken-api.

PR 2 ships this as a SKELETON, same pattern as IBKR — mock-mode forwards
to MockClient; real-paper raises NotConfiguredError until PR 2b wires ccxt.

Why ccxt: kraken's REST + WS surface is well-supported by ccxt's async
adapter (`ccxt.async_support.kraken`). Kraken's sandbox is enabled by
passing `'sandbox': True` to the ccxt constructor (see ccxt docs).
"""

from __future__ import annotations

import os

import structlog

from ..schemas import TVAlert
from .base import BrokerClient, BrokerName, NotConfiguredError, OrderReceipt
from .mock import MockClient

log = structlog.get_logger("tradingview_bridge.clients.kraken")


def _kraken_creds_present() -> bool:
    return bool(os.environ.get("TVBRIDGE_KRAKEN_API_KEY")) and bool(
        os.environ.get("TVBRIDGE_KRAKEN_API_SECRET")
    )


class KrakenClient(BrokerClient):
    """Kraken Pro client. PR 2: skeleton + delegate-to-mock fallback."""

    def __init__(self, broker_mode: str = "mock") -> None:
        self._mode = broker_mode
        self._mock: MockClient | None = None
        if broker_mode == "mock":
            self._mock = MockClient("kraken")

    @property
    def broker_name(self) -> BrokerName:
        return "kraken"

    async def place_order(self, alert: TVAlert) -> OrderReceipt:
        if self._mode == "mock" and self._mock is not None:
            return await self._mock.place_order(alert)

        if not _kraken_creds_present():
            raise NotConfiguredError(
                "Kraken real-paper mode requires TVBRIDGE_KRAKEN_API_KEY + "
                "TVBRIDGE_KRAKEN_API_SECRET env vars (use Kraken's sandbox keys "
                "from https://demo-futures.kraken.com or main-net read-only "
                "keys for spot). Use TVBRIDGE_BROKER_MODE=mock for tests."
            )
        # PR 2b would: ccxt.async_support.kraken({'apiKey': ..., 'secret': ...,
        # 'options': {'defaultType': 'spot'}, 'sandbox': True}); call
        # create_order(symbol=..., type=..., side=..., amount=...); map
        # to OrderReceipt.
        raise NotImplementedError(
            "PR 2b — ccxt Kraken wiring deferred. Mock path covers PR 2 tests."
        )

    async def health_check(self) -> bool:
        if self._mock is not None:
            return await self._mock.health_check()
        return _kraken_creds_present()

    @staticmethod
    def normalize_symbol(tv_symbol: str) -> str:
        """TradingView symbols → Kraken/ccxt symbol convention.

        TradingView's Pine Script alerts pass symbols like 'BTCUSD' or
        'BTC/USD'; ccxt expects 'BTC/USD'. Insert the slash if missing.
        Locked in PR 2; tested in test_clients_interface.py.
        """
        if "/" in tv_symbol:
            return tv_symbol.upper()
        # Heuristic — common quote currencies: USD, USDT, EUR, GBP
        for quote in ("USDT", "USD", "EUR", "GBP", "JPY"):
            if tv_symbol.upper().endswith(quote):
                base = tv_symbol.upper()[: -len(quote)]
                return f"{base}/{quote}"
        # Fallback — let ccxt's symbol parser complain
        return tv_symbol.upper()
