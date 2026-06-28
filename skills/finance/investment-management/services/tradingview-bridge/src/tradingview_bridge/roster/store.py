"""RosterStore — the persistent promotion registry (async SQLite, mirrors the ledger).

A small, auditable store of (family, params) candidates and the human decisions on
them. Cross-process safe (SQLite file), so the `roster` CLI can write while the
orchestrator reads the active roster.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from .types import RosterEntry, RosterStatus

log = structlog.get_logger("tradingview_bridge.roster.store")

# Explicit column list (and matching order) so row→entry mapping never silently
# drifts if the schema gains a column.
_COLUMNS = (
    "id, family, params, strategy_name, status, train_score, test_score, "
    "generalization_gap, note, proposed_at, decided_at"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS roster (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    family             TEXT NOT NULL,
    params             TEXT NOT NULL,
    strategy_name      TEXT NOT NULL,
    status             TEXT NOT NULL
                       CHECK (status IN ('proposed', 'active', 'rejected', 'superseded')),
    train_score        REAL NOT NULL,
    test_score         REAL NOT NULL,
    generalization_gap REAL NOT NULL,
    note               TEXT NOT NULL DEFAULT '',
    proposed_at        TEXT NOT NULL,
    decided_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_roster_status ON roster(status);
CREATE INDEX IF NOT EXISTS idx_roster_family ON roster(family);
"""


def default_roster_db_path() -> Path:
    override = os.environ.get("TVBRIDGE_ROSTER_DB_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".tradingview-bridge" / "roster.sqlite"


def _row_to_entry(r: tuple[Any, ...]) -> RosterEntry:
    status: RosterStatus = str(r[4])  # type: ignore[assignment]
    return RosterEntry(
        entry_id=int(r[0]),
        family=str(r[1]),
        params=json.loads(str(r[2])),
        strategy_name=str(r[3]),
        status=status,
        train_score=float(r[5]),
        test_score=float(r[6]),
        generalization_gap=float(r[7]),
        note=str(r[8]),
        proposed_at=datetime.fromisoformat(str(r[9])),
        decided_at=datetime.fromisoformat(str(r[10])) if r[10] is not None else None,
    )


class RosterStore:
    """Async SQLite store of roster entries."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or default_roster_db_path()
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

    async def record(self, entry: RosterEntry) -> int:
        """Insert an entry, returning its new id."""
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            cursor = await db.execute(
                "INSERT INTO roster (family, params, strategy_name, status, train_score, "
                "test_score, generalization_gap, note, proposed_at, decided_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.family,
                    json.dumps(entry.params),
                    entry.strategy_name,
                    entry.status,
                    entry.train_score,
                    entry.test_score,
                    entry.generalization_gap,
                    entry.note,
                    entry.proposed_at.isoformat(),
                    entry.decided_at.isoformat() if entry.decided_at is not None else None,
                ),
            )
            await db.commit()
            new_id = cursor.lastrowid
        assert new_id is not None
        log.info(
            "roster_recorded",
            id=new_id,
            family=entry.family,
            strategy=entry.strategy_name,
            status=entry.status,
        )
        return new_id

    async def get(self, entry_id: int) -> RosterEntry | None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            cursor = await db.execute(
                "SELECT id, family, params, strategy_name, status, train_score, test_score, "
                "generalization_gap, note, proposed_at, decided_at FROM roster WHERE id = ?",
                (entry_id,),
            )
            row = await cursor.fetchone()
        return _row_to_entry(tuple(row)) if row is not None else None

    async def list_entries(
        self, *, status: RosterStatus | None = None, family: str | None = None
    ) -> list[RosterEntry]:
        clauses: list[str] = []
        params: list[str] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if family is not None:
            clauses.append("family = ?")
            params.append(family)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        # `where` is built only from literal column clauses; all values are
        # parameterized below. No injection surface.
        query = f"SELECT {_COLUMNS} FROM roster{where} ORDER BY id ASC"  # noqa: S608
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [_row_to_entry(tuple(r)) for r in rows]

    async def set_status(self, entry_id: int, status: RosterStatus, *, note: str = "") -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            await db.execute(
                "UPDATE roster SET status = ?, note = ?, decided_at = ? WHERE id = ?",
                (status, note, datetime.now(tz=UTC).isoformat(), entry_id),
            )
            await db.commit()
        log.info("roster_status_set", id=entry_id, status=status)

    async def active_entries(self) -> list[RosterEntry]:
        return await self.list_entries(status="active")

    async def clear(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await self._ensure_schema(db)
            await db.execute("DELETE FROM roster")
            await db.commit()
