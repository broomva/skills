"""BrokerClient ABC + shared types.

Every concrete broker client (IBKR, Kraken, Polymarket, Mock) implements
this interface. The Dispatcher in `dispatch.py` resolves a client by
broker_name and calls `place_order(alert)` — no broker-specific code
leaks past this boundary.

Design intent: a new broker is added by writing one new module that
implements BrokerClient. The Dispatcher and the rest of the codebase
do not change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import TVAlert

BrokerName = Literal["ibkr", "kraken", "polymarket", "mock"]


class NotConfiguredError(RuntimeError):
    """Raised when a real broker client is invoked without credentials.

    The skeleton implementations (IBKR/Kraken/Polymarket in PR 2) raise
    this when `TVBRIDGE_BROKER_MODE=real-paper` but the broker's credential
    env vars are missing. PR 2 tests always run in `TVBRIDGE_BROKER_MODE=mock`
    so this is never raised in CI; in production it surfaces a clean error
    instead of a cryptic broker-SDK exception.
    """


class OrderReceipt(BaseModel):
    """What a broker returns after accepting an order (paper or live).

    Distinct from DispatchResult — DispatchResult is the response to the
    webhook caller (TradingView); OrderReceipt is the broker's
    confirmation, captured for the bookkeeping journal.
    """

    model_config = ConfigDict(extra="forbid")

    broker: BrokerName
    order_id: str = Field(description="Broker-assigned order identifier")
    alert_id: str = Field(description="Pine Script alert idempotency key")
    symbol: str
    action: str
    size: Decimal
    submitted_at: datetime
    paper: bool = Field(
        default=True,
        description="True if this was a paper-mode order (mock or broker sandbox).",
    )
    raw: dict[str, str] = Field(
        default_factory=dict,
        description="Broker-specific response fields for audit/replay.",
    )


class BrokerClient(ABC):
    """Abstract broker client. One implementation per broker."""

    @property
    @abstractmethod
    def broker_name(self) -> BrokerName:
        """Stable identifier used by the Dispatcher to route alerts."""

    @abstractmethod
    async def place_order(self, alert: TVAlert) -> OrderReceipt:
        """Submit a paper order derived from a TVAlert.

        Raises:
            NotConfiguredError: if real-paper mode is requested but credentials
                are missing. Production callers should catch this and translate
                into a 503 DispatchResult.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the broker connection is usable.

        Mock clients return True unconditionally; real clients ping the
        broker. Used by `/health` to surface broker connectivity.
        """
