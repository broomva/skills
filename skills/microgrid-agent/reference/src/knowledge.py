"""SQLite knowledge graph for microgrid topology, patterns, and priority loads.

Stores entities (devices, loads, zones), relations between them, and learned
temporal patterns. Supports recursive graph queries via CTEs.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

log = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,         -- device, load, zone, bus, generator
    name TEXT NOT NULL,
    properties TEXT DEFAULT '{}',  -- JSON blob
    avg_load_kw REAL DEFAULT 0.0,
    std_load_kw REAL DEFAULT 0.0,
    observation_count INTEGER DEFAULT 0,
    priority INTEGER DEFAULT 0,   -- 0=normal, 1=important, 2=critical
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS relations (
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    kind TEXT NOT NULL,         -- feeds, protects, monitors, controls, connects_to
    weight REAL DEFAULT 1.0,
    properties TEXT DEFAULT '{}',
    created_at REAL NOT NULL,
    PRIMARY KEY (src, dst, kind),
    FOREIGN KEY (src) REFERENCES entities(id),
    FOREIGN KEY (dst) REFERENCES entities(id)
);

CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    pattern_type TEXT NOT NULL,  -- daily_profile, anomaly, correlation
    hour_of_day INTEGER,        -- 0-23
    day_of_week INTEGER,        -- 0-6
    avg_value REAL DEFAULT 0.0,
    std_value REAL DEFAULT 0.0,
    sample_count INTEGER DEFAULT 0,
    updated_at REAL NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(kind);
CREATE INDEX IF NOT EXISTS idx_entities_priority ON entities(priority);
CREATE INDEX IF NOT EXISTS idx_relations_src ON relations(src);
CREATE INDEX IF NOT EXISTS idx_relations_dst ON relations(dst);
CREATE INDEX IF NOT EXISTS idx_patterns_entity ON patterns(entity_id);
CREATE INDEX IF NOT EXISTS idx_patterns_hour ON patterns(hour_of_day);
"""


@dataclass
class Entity:
    id: str
    kind: str
    name: str
    priority: int = 0
    avg_load_kw: float = 0.0
    std_load_kw: float = 0.0


@dataclass
class Relation:
    src: str
    dst: str
    kind: str
    weight: float = 1.0


class KnowledgeGraph:
    """Lightweight SQLite-backed knowledge graph for microgrid topology."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self):
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()
        log.info("Knowledge graph opened: %s", self.db_path)

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def add_entity(
        self, entity_id: str, kind: str, name: str,
        priority: int = 0, properties: str = "{}",
    ) -> None:
        now = time.time()
        await self._db.execute(
            """INSERT INTO entities (id, kind, name, priority, properties, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, priority=excluded.priority,
                 properties=excluded.properties, updated_at=excluded.updated_at""",
            (entity_id, kind, name, priority, properties, now, now),
        )
        await self._db.commit()

    async def add_relation(
        self, src: str, dst: str, kind: str, weight: float = 1.0,
        properties: str = "{}",
    ) -> None:
        now = time.time()
        await self._db.execute(
            """INSERT INTO relations (src, dst, kind, weight, properties, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(src, dst, kind) DO UPDATE SET
                 weight=excluded.weight, properties=excluded.properties""",
            (src, dst, kind, weight, properties, now),
        )
        await self._db.commit()

    async def get_entity(self, entity_id: str) -> Entity | None:
        cursor = await self._db.execute(
            "SELECT id, kind, name, priority, avg_load_kw, std_load_kw FROM entities WHERE id = ?",
            (entity_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Entity(
            id=row["id"], kind=row["kind"], name=row["name"],
            priority=row["priority"], avg_load_kw=row["avg_load_kw"],
            std_load_kw=row["std_load_kw"],
        )

    async def get_priority_loads(self, min_priority: int = 1) -> list[Entity]:
        """Return all load entities at or above the given priority level."""
        cursor = await self._db.execute(
            """SELECT id, kind, name, priority, avg_load_kw, std_load_kw
               FROM entities WHERE kind = 'load' AND priority >= ?
               ORDER BY priority DESC""",
            (min_priority,),
        )
        rows = await cursor.fetchall()
        return [
            Entity(id=r["id"], kind=r["kind"], name=r["name"],
                   priority=r["priority"], avg_load_kw=r["avg_load_kw"],
                   std_load_kw=r["std_load_kw"])
            for r in rows
        ]

    async def query_affected(self, entity_id: str, max_depth: int = 3) -> list[Entity]:
        """Find all entities downstream of the given entity via recursive CTE."""
        cursor = await self._db.execute(
            """
            WITH RECURSIVE downstream(id, depth) AS (
                SELECT dst, 1 FROM relations WHERE src = ?
                UNION
                SELECT r.dst, d.depth + 1
                FROM relations r
                JOIN downstream d ON r.src = d.id
                WHERE d.depth < ?
            )
            SELECT DISTINCT e.id, e.kind, e.name, e.priority, e.avg_load_kw, e.std_load_kw
            FROM downstream d
            JOIN entities e ON e.id = d.id
            ORDER BY e.priority DESC
            """,
            (entity_id, max_depth),
        )
        rows = await cursor.fetchall()
        return [
            Entity(id=r["id"], kind=r["kind"], name=r["name"],
                   priority=r["priority"], avg_load_kw=r["avg_load_kw"],
                   std_load_kw=r["std_load_kw"])
            for r in rows
        ]

    async def update_load_observation(
        self, entity_id: str, observed_kw: float,
    ) -> None:
        """Incrementally update running mean/std for load observations."""
        cursor = await self._db.execute(
            "SELECT avg_load_kw, std_load_kw, observation_count FROM entities WHERE id = ?",
            (entity_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return

        n = row["observation_count"] + 1
        old_mean = row["avg_load_kw"]
        old_std = row["std_load_kw"]

        # Welford's online algorithm
        delta = observed_kw - old_mean
        new_mean = old_mean + delta / n
        delta2 = observed_kw - new_mean
        # M2 = (old_std^2) * (n-1) + delta * delta2
        m2 = (old_std ** 2) * max(n - 2, 0) + delta * delta2
        new_std = (m2 / max(n - 1, 1)) ** 0.5

        now = time.time()
        await self._db.execute(
            """UPDATE entities SET avg_load_kw = ?, std_load_kw = ?,
               observation_count = ?, updated_at = ? WHERE id = ?""",
            (new_mean, new_std, n, now, entity_id),
        )
        await self._db.commit()

    async def update_hourly_pattern(
        self, entity_id: str, hour: int, value: float,
    ) -> None:
        """Update the hourly load pattern for temporal learning."""
        now = time.time()
        cursor = await self._db.execute(
            """SELECT avg_value, std_value, sample_count FROM patterns
               WHERE entity_id = ? AND pattern_type = 'daily_profile' AND hour_of_day = ?""",
            (entity_id, hour),
        )
        row = await cursor.fetchone()

        if row is None:
            await self._db.execute(
                """INSERT INTO patterns (entity_id, pattern_type, hour_of_day, avg_value, std_value, sample_count, updated_at)
                   VALUES (?, 'daily_profile', ?, ?, 0.0, 1, ?)""",
                (entity_id, hour, value, now),
            )
        else:
            n = row["sample_count"] + 1
            old_mean = row["avg_value"]
            delta = value - old_mean
            new_mean = old_mean + delta / n
            delta2 = value - new_mean
            m2 = (row["std_value"] ** 2) * max(n - 2, 0) + delta * delta2
            new_std = (m2 / max(n - 1, 1)) ** 0.5
            await self._db.execute(
                """UPDATE patterns SET avg_value = ?, std_value = ?, sample_count = ?, updated_at = ?
                   WHERE entity_id = ? AND pattern_type = 'daily_profile' AND hour_of_day = ?""",
                (new_mean, new_std, n, now, entity_id, hour),
            )
        await self._db.commit()

    async def get_total_priority_load_kw(self, min_priority: int = 1) -> float:
        loads = await self.get_priority_loads(min_priority)
        return sum(e.avg_load_kw for e in loads)
