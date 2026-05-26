"""IBKRClient — Interactive Brokers via ib_async (paper-port 7497).

PR 2 ships this as a SKELETON. The interface is complete; the real
ib_async wiring is wrapped in `_connect()` which raises NotConfiguredError
unless `TVBRIDGE_IBKR_HOST` + `TVBRIDGE_IBKR_PORT` env vars are set AND a
TWS/IB Gateway is actually running on that port. CI never sets those
vars, so the skeleton stays untouched in tests.

PR 2b (after broker onboarding via the broker-selection ADR) replaces
the placeholder body of `place_order` with the real ib_async calls.
The contract (TVAlert in, OrderReceipt out) is locked here.

Symbol mapping (locked here, used by both PR 2 mock-mode and PR 2b real-paper):
- stock/etf  → IBKR Stock contract (SMART routing, USD)
- bond       → IBKR Bond contract (IBKR's bond CUSIP lookup)
- fx         → IBKR Forex contract (idealpro venue)
"""

from __future__ import annotations

import os
from typing import Any

import structlog

from ..schemas import AssetClass, TVAlert
from .base import BrokerClient, BrokerName, NotConfiguredError, OrderReceipt
from .mock import MockClient

log = structlog.get_logger("tradingview_bridge.clients.ibkr")


def _ibkr_creds_present() -> bool:
    """True if env vars suggest a configured ib_async target."""
    return bool(os.environ.get("TVBRIDGE_IBKR_HOST")) and bool(os.environ.get("TVBRIDGE_IBKR_PORT"))


class IBKRClient(BrokerClient):
    """IBKR Pro client. PR 2: skeleton + delegate-to-mock fallback.

    Usage:
      - `TVBRIDGE_BROKER_MODE=mock` → constructor wraps a MockClient and forwards
        all calls. Used by every test and by local dev without TWS.
      - `TVBRIDGE_BROKER_MODE=real-paper` + creds → constructor would connect
        to TWS at the configured host:port; PR 2 raises NotConfiguredError
        because real-paper wiring is PR 2b's scope.

    The dispatcher constructs IBKRClient and calls place_order; the mock
    fallback path means tests never have to know whether real or mock is
    behind the abstraction.
    """

    def __init__(self, broker_mode: str = "mock") -> None:
        self._mode = broker_mode
        self._mock: MockClient | None = None
        if broker_mode == "mock":
            self._mock = MockClient("ibkr")

    @property
    def broker_name(self) -> BrokerName:
        return "ibkr"

    async def place_order(self, alert: TVAlert) -> OrderReceipt:
        if self._mode == "mock" and self._mock is not None:
            return await self._mock.place_order(alert)

        # real-paper path — skeleton only in PR 2
        if not _ibkr_creds_present():
            raise NotConfiguredError(
                "IBKR real-paper mode requires TVBRIDGE_IBKR_HOST + "
                "TVBRIDGE_IBKR_PORT env vars AND a running TWS/IB Gateway. "
                "Use TVBRIDGE_BROKER_MODE=mock for tests."
            )
        # PR 2b would: connect via ib_async, build Contract by asset_class,
        # submit Order, wait for fill, return OrderReceipt.
        raise NotImplementedError("PR 2b — ib_async wiring deferred. Mock path covers PR 2 tests.")

    async def health_check(self) -> bool:
        if self._mock is not None:
            return await self._mock.health_check()
        return _ibkr_creds_present()

    @staticmethod
    def map_asset_class_to_contract(asset_class: AssetClass) -> dict[str, Any]:
        """Pure-function mapping from TVAlert.asset_class to IBKR contract kwargs.

        Locked in PR 2 so PR 2b just plugs it into ib_async's Contract()
        constructor. Tested in test_clients_interface.py.
        """
        if asset_class == "stock" or asset_class == "etf":
            return {"secType": "STK", "exchange": "SMART", "currency": "USD"}
        if asset_class == "bond":
            return {"secType": "BOND", "exchange": "SMART", "currency": "USD"}
        if asset_class == "fx":
            return {"secType": "CASH", "exchange": "IDEALPRO", "currency": "USD"}
        raise ValueError(f"IBKR does not route asset_class={asset_class!r}")
