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

from dataclasses import dataclass
from decimal import Decimal

import structlog

from ..orders import OrderLedger

log = structlog.get_logger("tradingview_bridge.operator.positions")


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


class PositionManager:
    """Computes positions and drift from the order ledger."""

    def __init__(
        self,
        order_ledger: OrderLedger,
        *,
        target_allocation: dict[str, Decimal] | None = None,
    ) -> None:
        self._ledger = order_ledger
        self._target = target_allocation or {}

    async def net_positions(self) -> dict[str, Decimal]:
        """Net position per symbol (canary orders are already excluded at write)."""
        return await self._ledger.net_positions()

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
