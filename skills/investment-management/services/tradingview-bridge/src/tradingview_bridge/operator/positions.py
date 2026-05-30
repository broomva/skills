"""PositionManager — net positions + drift from the order ledger.

Reads the OrderLedger (the persistent economic record of accepted orders) and
computes:
  - net positions per symbol (replay of buy/sell/close/flatten)
  - open position count (for the position-cap gate)
  - drift vs an optional target allocation (units per symbol)

Price-weighted drift is deliberately out of scope for this module — it requires
market data (the parent investment-management skill's market_data.py). Here
``target_allocation`` is expressed in *units* per symbol, so drift is a pure
ledger computation with no price dependency. Real price-weighted rebalancing is
a follow-up that composes this module with the quant toolkit.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

import structlog

from ..orders import OrderLedger

log = structlog.get_logger("tradingview_bridge.operator.positions")

# An async reader of the real broker book: () -> {symbol: detail}. The symbols
# may be venue-qualified (e.g. NASDAQ:AAPL); reconciliation normalizes to ticker.
BrokerReader = Callable[[], Awaitable[dict[str, str]]]


def _ticker(symbol: str) -> str:
    """Normalize a venue-qualified symbol (NASDAQ:AAPL) to its ticker (AAPL)."""
    return symbol.split(":")[-1].upper().strip()


@dataclass(frozen=True)
class Drift:
    """Drift of one symbol's net position from its target (in units)."""

    symbol: str
    current: Decimal
    target: Decimal

    @property
    def delta(self) -> Decimal:
        """Signed correction needed: positive = need to buy, negative = need to sell."""
        return self.target - self.current

    @property
    def needs_action(self) -> bool:
        return self.delta != 0


@dataclass(frozen=True)
class Reconciliation:
    """Ledger (what the operator placed) vs broker (what's actually open).

    Symbols are normalized to tickers for comparison.
    """

    matched: list[str]  # open in both — the operator's view agrees with reality
    ledger_only: list[str]  # operator believes open; broker doesn't show it
    broker_only: list[str]  # broker shows open; operator never placed it (drift)

    @property
    def has_drift(self) -> bool:
        return bool(self.ledger_only or self.broker_only)


class PositionManager:
    """Computes positions and drift from the order ledger, with optional
    reconciliation against the real broker book."""

    def __init__(
        self,
        order_ledger: OrderLedger,
        *,
        target_allocation: dict[str, Decimal] | None = None,
        broker_reader: BrokerReader | None = None,
    ) -> None:
        self._ledger = order_ledger
        self._target = target_allocation or {}
        self._broker_reader = broker_reader

    async def net_positions(self) -> dict[str, Decimal]:
        """Net position per symbol (canary orders are already excluded at write)."""
        return await self._ledger.net_positions()

    async def reconcile(self) -> Reconciliation | None:
        """Compare the ledger's positions against the real broker book.

        Returns None when no broker reader is configured (mock mode) — the
        operator then trusts its own ledger. With a reader (tv-paper mode), any
        ``broker_only`` symbol is a position the operator did not place (manual
        order, external fill) and any ``ledger_only`` is a believed-open
        position the broker no longer shows — both are surfaced as drift.
        """
        if self._broker_reader is None:
            return None
        ledger = {_ticker(s) for s in await self.net_positions()}
        broker = {_ticker(s) for s in (await self._broker_reader())}
        return Reconciliation(
            matched=sorted(ledger & broker),
            ledger_only=sorted(ledger - broker),
            broker_only=sorted(broker - ledger),
        )

    async def open_position_count(self) -> int:
        """Number of distinct symbols with a non-zero net position."""
        return len(await self.net_positions())

    async def drift(self) -> list[Drift]:
        """Drift of each symbol (union of current + target) from its target.

        Returns an empty list when no target allocation is configured — the
        operator then only reports positions, never proposes rebalances.
        """
        if not self._target:
            return []
        current = await self.net_positions()
        symbols = set(current) | set(self._target)
        drifts = [
            Drift(
                symbol=sym,
                current=current.get(sym, Decimal(0)),
                target=self._target.get(sym, Decimal(0)),
            )
            for sym in sorted(symbols)
        ]
        return [d for d in drifts if d.needs_action]
