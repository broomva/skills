"""Idempotency store — SQLite-backed dedup keyed on alert_id.

Pine Script alerts can fire twice (network retry, TradingView duplicate
trigger). Without idempotency the same buy fires twice → 2x position.

Design:
- aiosqlite for non-blocking writes
- Single table: alert_id (PK) + broker + order_id + created_at
- `check_or_insert(alert_id, broker, order_id)` returns (is_new, existing_record)
- If is_new: the alert hasn't been seen; caller proceeds with broker call
- If not is_new: the existing OrderReceipt is returned; caller short-circuits

The table lives at `~/.tradingview-bridge/idempotency.sqlite` by default,
overridable via TVBRIDGE_DB_PATH.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite
import structlog

log = structlog.get_logger("tradingview_bridge.idempotency")


@dataclass(frozen=True)
class IdempotencyRecord:
    """The "already-seen" record returned on dedup hit."""

    alert_id: str
    broker: str
    order_id: str
    created_at: datetime


def default_db_path() -> Path:
    """Default SQLite location, overridable via TVBRIDGE_DB_PATH."""
    override = os.environ.get("TVBRIDGE_DB_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".tradingview-bridge" / "idempotency.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS alert_idempotency (
    alert_id   TEXT PRIMARY KEY,
    broker     TEXT NOT NULL,
    order_id   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class IdempotencyStore:
    """Async SQLite idempotency store. Construct once per process, reuse."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or default_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def _ensure_schema(self, db: aiosqlite.Connection) -> None:
        if not self._initialized:
            await db.executescript(SCHEMA)
            await db.commit()
            self._initialized = True

    async def check_or_insert(
        self,
        alert_id: str,
        broker: str,
        order_id: str,
    ) -> tuple[bool, IdempotencyRecord | None]:
        """Atomically insert-if-new, else return the existing record.

        Returns:
            (True, None) — alert_id was new, insert succeeded
            (False, IdempotencyRecord) — alert_id existed, returning prior record
        """
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            cursor = await db.execute(
                "SELECT broker, order_id, created_at FROM alert_idempotency WHERE alert_id = ?",
                (alert_id,),
            )
            row = await cursor.fetchone()
            if row is not None:
                existing = IdempotencyRecord(
                    alert_id=alert_id,
                    broker=row[0],
                    order_id=row[1],
                    created_at=datetime.fromisoformat(row[2]),
                )
                log.info(
                    "idempotency_hit",
                    alert_id=alert_id,
                    existing_broker=existing.broker,
                    existing_order_id=existing.order_id,
                )
                return (False, existing)

            now_iso = datetime.now(tz=UTC).isoformat()
            await db.execute(
                "INSERT INTO alert_idempotency (alert_id, broker, order_id, created_at) "
                "VALUES (?, ?, ?, ?)",
                (alert_id, broker, order_id, now_iso),
            )
            await db.commit()
            log.info("idempotency_insert", alert_id=alert_id, broker=broker, order_id=order_id)
            return (True, None)

    async def clear(self) -> None:
        """Drop all rows. Used by test fixtures between cases."""
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            await db.execute("DELETE FROM alert_idempotency")
            await db.commit()
