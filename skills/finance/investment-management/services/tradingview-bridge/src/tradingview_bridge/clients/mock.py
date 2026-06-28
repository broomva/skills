"""MockClient — in-memory broker simulation for tests and dev.

No network I/O. Records every accepted order in a list so tests can
inspect dispatch behavior end-to-end. Returns a synthetic order_id
(UUID) and OrderReceipt(paper=True).

Used in:
- All tests (TVBRIDGE_BROKER_MODE=mock by default in conftest.py)
- Local dev when no broker credentials are configured
- CI (no broker creds available)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

import structlog

from ..schemas import TVAlert
from .base import BrokerClient, BrokerName, OrderReceipt

log = structlog.get_logger("tradingview_bridge.clients.mock")


class MockClient(BrokerClient):
    """In-memory broker mock. Records orders; no network I/O."""

    def __init__(self, broker_name: BrokerName) -> None:
        """A single MockClient impersonates one broker at a time.

        The dispatcher constructs one MockClient per broker_name when in
        mock mode (so test fixtures can assert "Kraken got this order"
        vs "IBKR got that one").
        """
        self._broker_name: BrokerName = broker_name
        self.placed_orders: list[OrderReceipt] = []

    @property
    def broker_name(self) -> BrokerName:
        return self._broker_name

    async def place_order(self, alert: TVAlert) -> OrderReceipt:
        order_id = f"mock-{uuid.uuid4().hex[:12]}"
        receipt = OrderReceipt(
            broker=self._broker_name,
            order_id=order_id,
            alert_id=alert.alert_id,
            symbol=alert.symbol,
            action=alert.action,
            size=alert.size,
            submitted_at=datetime.now(tz=UTC),
            paper=True,
            raw={"mode": "mock", "size_type": alert.size_type, "order_type": alert.order_type},
        )
        self.placed_orders.append(receipt)
        log.info(
            "mock_order_placed",
            broker=self._broker_name,
            order_id=order_id,
            alert_id=alert.alert_id,
            symbol=alert.symbol,
            action=alert.action,
            size=str(alert.size),
        )
        return receipt

    async def health_check(self) -> Literal[True]:
        """Always healthy — no real connection to check."""
        return True

    def clear(self) -> None:
        """Reset placed orders. Test fixtures call this between cases."""
        self.placed_orders.clear()
