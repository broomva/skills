"""Pydantic schemas for TradingView alerts and dispatcher results.

The `TVAlert` schema is the contract between Pine Script alerts and the
multi-broker dispatcher. New brokers do not require schema changes — they
extend `AssetClass` and add a route in `dispatch.py`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints

AssetClass = Literal["stock", "etf", "bond", "fx", "crypto", "prediction"]
"""Asset classes the dispatcher knows how to route.

Add a new asset class here and add the routing arm in `dispatch.py:Dispatcher._route`.
"""

Action = Literal["buy", "sell", "close", "flatten"]
"""Order intent.

- `buy` / `sell` — directional entry
- `close` — close the position for `symbol` if any
- `flatten` — close ALL positions for the strategy (broader scope than `close`)
"""

SizeType = Literal["units", "pct_equity", "notional_usd"]
"""How the `size` field is interpreted.

- `units` — number of shares / contracts / coins
- `pct_equity` — percentage of account equity (0-100)
- `notional_usd` — dollar amount
"""

OrderType = Literal["market", "limit", "stop"]


class TVAlert(BaseModel):
    """A single TradingView Pine Script alert payload.

    The `secret` field is the shared-secret auth; `auth.py` strips it before
    handing the alert to the dispatcher to avoid leaking it into structured logs.

    All numeric fields are `Decimal` to avoid floating-point loss in cross-broker
    quantity arithmetic.
    """

    model_config = ConfigDict(
        extra="allow",  # allow brokers to thread extra fields without breaking
        str_strip_whitespace=True,
    )

    alert_id: Annotated[str, StringConstraints(min_length=1, max_length=128)] = Field(
        description="Idempotency key. PR 2 dedupes on this. Use TradingView's "
        "{{strategy.order.id}} or a UUID."
    )
    secret: SecretStr = Field(
        description="Shared-secret auth. Compared constant-time against env "
        "TVBRIDGE_TV_WEBHOOK_SECRET. Stripped before logging."
    )
    strategy_name: Annotated[str, StringConstraints(min_length=1, max_length=128)] = Field(
        description="Free-form strategy identifier. Used for bookkeeping journal "
        "and per-strategy position-cap gates."
    )
    asset_class: AssetClass = Field(description="Determines which broker the dispatcher routes to.")
    symbol: Annotated[str, StringConstraints(min_length=1, max_length=64)] = Field(
        description="Broker-native symbol. Examples: 'AAPL' (IBKR stock), "
        "'BTC/USD' (Kraken pair), 'EURUSD' (IBKR FX), '0x...' (Polymarket market id)."
    )
    action: Action
    size: Decimal = Field(
        gt=Decimal(0),
        description="Quantity, interpretation depends on size_type.",
    )
    size_type: SizeType = "units"
    price_hint: Decimal | None = Field(
        default=None,
        gt=Decimal(0),
        description="Optional. Used for slippage check and limit/stop orders.",
    )
    order_type: OrderType = "market"
    time: datetime = Field(description="Pine Script's {{time}} — UTC ISO8601.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form. Brokers can read strategy-specific hints here "
        "without schema changes.",
    )


class DispatchResult(BaseModel):
    """What the dispatcher returns to the webhook endpoint."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "rejected", "stubbed", "duplicate"]
    broker: Literal["ibkr", "kraken", "polymarket", "tradingview-paper"]
    detail: str = Field(description="Human-readable reason or trace id.")
    alert_id: str
    order_id: str | None = Field(
        default=None,
        description="Broker order id. None for stubbed/rejected results.",
    )
