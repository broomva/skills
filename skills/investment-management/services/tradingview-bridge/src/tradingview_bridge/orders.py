"""Order ledger — persistent record of every accepted order, for position tracking.

Distinct from the idempotency store (which only records alert_id → order_id for
dedup). The order ledger records the *economic* content of each order — symbol,
action, size — so the operator can replay them into net positions.

Cross-process safe: the bridge process writes; the operator process reads the
same SQLite file. Canary orders (strategy_name starting with ``__canary__``) are
never written here — they exercise the pipeline without affecting positions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import aiosqlite
import structlog

log = structlog.get_logger("tradingview_bridge.orders")

CANARY_PREFIX = "__canary__"


def default_orders_db_path() -> Path:
    """Default SQLite location, overridable via TVBRIDGE_ORDERS_DB_PATH.

    Defaults next to the idempotency DB under ~/.tradingview-bridge/.
    """
    override = os.environ.get("TVBRIDGE_ORDERS_DB_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".tradingview-bridge" / "orders.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      TEXT NOT NULL,
    alert_id      TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    broker        TEXT NOT NULL,
    asset_class   TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    action        TEXT NOT NULL,
    size          TEXT NOT NULL,
    paper         INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
"""


@dataclass(frozen=True)
class OrderRow:
    """One recorded order."""

    order_id: str
    alert_id: str
    strategy_name: str
    broker: str
    asset_class: str
    symbol: str
    action: str
    size: Decimal
    paper: bool
    created_at: datetime


class OrderLedger:
    """Async SQLite order ledger. Construct once per process, reuse."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or default_orders_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    @property
    def db_path(self) -> Path:
        return self._db_path

    async def _ensure_schema(self, db: aiosqlite.Connection) -> None:
        if not self._initialized:
            await db.executescript(SCHEMA)
            await db.commit()
            self._initialized = True

    async def append(
        self,
        *,
        order_id: str,
        alert_id: str,
        strategy_name: str,
        broker: str,
        asset_class: str,
        symbol: str,
        action: str,
        size: Decimal,
        paper: bool,
    ) -> bool:
        """Append an order. Returns False (skipped) for canary orders.

        Canary orders exercise the pipeline but must never affect positions,
        so they are filtered here at the single write point.
        """
        if strategy_name.startswith(CANARY_PREFIX):
            return False
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            await db.execute(
                "INSERT INTO orders (order_id, alert_id, strategy_name, broker, "
                "asset_class, symbol, action, size, paper, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order_id,
                    alert_id,
                    strategy_name,
                    broker,
                    asset_class,
                    symbol,
                    action,
                    str(size),
                    1 if paper else 0,
                    datetime.now(tz=UTC).isoformat(),
                ),
            )
            await db.commit()
        log.info("order_recorded", order_id=order_id, symbol=symbol, action=action, size=str(size))
        return True

    async def all_orders(self) -> list[OrderRow]:
        """Return all orders in chronological order."""
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            cursor = await db.execute(
                "SELECT order_id, alert_id, strategy_name, broker, asset_class, "
                "symbol, action, size, paper, created_at FROM orders ORDER BY id ASC"
            )
            rows = await cursor.fetchall()
        return [
            OrderRow(
                order_id=r[0],
                alert_id=r[1],
                strategy_name=r[2],
                broker=r[3],
                asset_class=r[4],
                symbol=r[5],
                action=r[6],
                size=Decimal(r[7]),
                paper=bool(r[8]),
                created_at=datetime.fromisoformat(r[9]),
            )
            for r in rows
        ]

    async def net_positions(self) -> dict[str, Decimal]:
        """Replay orders into net positions per symbol.

        Semantics:
          buy     → +size
          sell    → -size
          close   → set that symbol's net to 0
          flatten → set ALL symbols' net to 0

        Symbols whose net is exactly 0 are omitted from the result.
        """
        orders = await self.all_orders()
        net: dict[str, Decimal] = {}
        for o in orders:
            if o.action == "buy":
                net[o.symbol] = net.get(o.symbol, Decimal(0)) + o.size
            elif o.action == "sell":
                net[o.symbol] = net.get(o.symbol, Decimal(0)) - o.size
            elif o.action == "close":
                net[o.symbol] = Decimal(0)
            elif o.action == "flatten":
                net = {sym: Decimal(0) for sym in net}
        return {sym: qty for sym, qty in net.items() if qty != 0}

    async def clear(self) -> None:
        """Drop all rows. Used by test fixtures between cases."""
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            await db.execute("DELETE FROM orders")
            await db.commit()
