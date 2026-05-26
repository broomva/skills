"""
Tests for the knowledge graph.

Covers:
- Entity and relation CRUD operations
- Recursive CTE graph traversal (including via src.knowledge.KnowledgeGraph)
- Pattern learning from observations (including async update_hourly_pattern)
- Priority loads ordering
"""

import json
import sqlite3
import os
import tempfile

import pytest
import aiosqlite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    ".control",
    "schemas",
    "knowledge-graph.sql",
)


@pytest.fixture
def db():
    """Create a temporary in-memory database with the schema loaded."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Load schema (without seed data)
    schema_sql = _load_schema_without_seeds()
    conn.executescript(schema_sql)

    yield conn
    conn.close()


@pytest.fixture
def seeded_db():
    """Create a temporary database with schema AND seed data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    with open(SCHEMA_PATH, "r") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)

    yield conn
    conn.close()


def _load_schema_without_seeds():
    """Load only the CREATE TABLE/INDEX statements, skip INSERTs."""
    with open(SCHEMA_PATH, "r") as f:
        full_sql = f.read()

    # Split on the seed data marker and take only the schema part
    marker = "-- Example seed data"
    if marker in full_sql:
        return full_sql[: full_sql.index(marker)]
    return full_sql


# ===========================================================================
# Entity CRUD Tests
# ===========================================================================

class TestEntityCRUD:
    """Test basic entity create, read, update, delete."""

    def test_create_entity(self, db):
        """Create an entity and verify it exists."""
        db.execute(
            "INSERT INTO entities (type, name, properties) VALUES (?, ?, ?)",
            ("device", "test_inverter", json.dumps({"capacity_kw": 10.0})),
        )
        db.commit()

        row = db.execute("SELECT * FROM entities WHERE name = 'test_inverter'").fetchone()
        assert row is not None
        assert row["type"] == "device"
        assert json.loads(row["properties"])["capacity_kw"] == 10.0

    def test_create_multiple_entities(self, db):
        """Create several entities of different types."""
        entities = [
            ("device", "solar_panel", "{}"),
            ("device", "battery", "{}"),
            ("load", "hospital", '{"priority": 1}'),
            ("load", "school", '{"priority": 4}'),
            ("zone", "generation", "{}"),
        ]
        db.executemany(
            "INSERT INTO entities (type, name, properties) VALUES (?, ?, ?)",
            entities,
        )
        db.commit()

        count = db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        assert count == 5

        devices = db.execute("SELECT COUNT(*) FROM entities WHERE type = 'device'").fetchone()[0]
        assert devices == 2

    def test_update_entity_properties(self, db):
        """Update an entity's properties."""
        db.execute(
            "INSERT INTO entities (type, name, properties) VALUES (?, ?, ?)",
            ("device", "inverter", json.dumps({"firmware": "1.0"})),
        )
        db.commit()

        db.execute(
            "UPDATE entities SET properties = ?, updated_at = datetime('now') WHERE name = ?",
            (json.dumps({"firmware": "2.0", "upgraded": True}), "inverter"),
        )
        db.commit()

        row = db.execute("SELECT properties FROM entities WHERE name = 'inverter'").fetchone()
        props = json.loads(row["properties"])
        assert props["firmware"] == "2.0"
        assert props["upgraded"] is True

    def test_delete_entity_cascades_relations(self, db):
        """Deleting an entity should cascade delete its relations."""
        db.execute("INSERT INTO entities (type, name) VALUES ('device', 'src')")
        db.execute("INSERT INTO entities (type, name) VALUES ('zone', 'tgt')")
        db.commit()

        src_id = db.execute("SELECT id FROM entities WHERE name = 'src'").fetchone()[0]
        tgt_id = db.execute("SELECT id FROM entities WHERE name = 'tgt'").fetchone()[0]

        db.execute(
            "INSERT INTO relations (source_id, relation, target_id) VALUES (?, 'located_in', ?)",
            (src_id, tgt_id),
        )
        db.commit()

        # Verify relation exists
        rel_count = db.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        assert rel_count == 1

        # Delete source entity
        db.execute("DELETE FROM entities WHERE id = ?", (src_id,))
        db.commit()

        # Relation should be cascade-deleted
        rel_count = db.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        assert rel_count == 0


# ===========================================================================
# Relation CRUD Tests
# ===========================================================================

class TestRelationCRUD:
    """Test relation create, read, and traversal."""

    def test_create_relation(self, db):
        """Create a relation between two entities."""
        db.execute("INSERT INTO entities (type, name) VALUES ('device', 'solar')")
        db.execute("INSERT INTO entities (type, name) VALUES ('zone', 'gen_zone')")
        db.commit()

        solar_id = db.execute("SELECT id FROM entities WHERE name = 'solar'").fetchone()[0]
        zone_id = db.execute("SELECT id FROM entities WHERE name = 'gen_zone'").fetchone()[0]

        db.execute(
            "INSERT INTO relations (source_id, relation, target_id, weight) VALUES (?, ?, ?, ?)",
            (solar_id, "located_in", zone_id, 1.0),
        )
        db.commit()

        rel = db.execute(
            "SELECT * FROM relations WHERE source_id = ? AND relation = 'located_in'",
            (solar_id,),
        ).fetchone()

        assert rel is not None
        assert rel["target_id"] == zone_id
        assert rel["weight"] == 1.0

    def test_bidirectional_query(self, db):
        """Query relations in both directions."""
        db.execute("INSERT INTO entities (type, name) VALUES ('device', 'a')")
        db.execute("INSERT INTO entities (type, name) VALUES ('device', 'b')")
        db.commit()

        id_a = db.execute("SELECT id FROM entities WHERE name = 'a'").fetchone()[0]
        id_b = db.execute("SELECT id FROM entities WHERE name = 'b'").fetchone()[0]

        db.execute(
            "INSERT INTO relations (source_id, relation, target_id) VALUES (?, 'powers', ?)",
            (id_a, id_b),
        )
        db.commit()

        # Forward: a powers b
        forward = db.execute(
            "SELECT target_id FROM relations WHERE source_id = ? AND relation = 'powers'",
            (id_a,),
        ).fetchall()
        assert len(forward) == 1
        assert forward[0]["target_id"] == id_b

        # Reverse: what powers b?
        reverse = db.execute(
            "SELECT source_id FROM relations WHERE target_id = ? AND relation = 'powers'",
            (id_b,),
        ).fetchall()
        assert len(reverse) == 1
        assert reverse[0]["source_id"] == id_a

    def test_weighted_relations(self, db):
        """Relations with different weights should be queryable."""
        db.execute("INSERT INTO entities (type, name) VALUES ('device', 'src')")
        db.execute("INSERT INTO entities (type, name) VALUES ('load', 'high_pri')")
        db.execute("INSERT INTO entities (type, name) VALUES ('load', 'low_pri')")
        db.commit()

        src_id = db.execute("SELECT id FROM entities WHERE name = 'src'").fetchone()[0]
        hi_id = db.execute("SELECT id FROM entities WHERE name = 'high_pri'").fetchone()[0]
        lo_id = db.execute("SELECT id FROM entities WHERE name = 'low_pri'").fetchone()[0]

        db.execute(
            "INSERT INTO relations (source_id, relation, target_id, weight) VALUES (?, 'powers', ?, ?)",
            (src_id, hi_id, 0.9),
        )
        db.execute(
            "INSERT INTO relations (source_id, relation, target_id, weight) VALUES (?, 'powers', ?, ?)",
            (src_id, lo_id, 0.3),
        )
        db.commit()

        # Query ordered by weight descending
        rows = db.execute(
            "SELECT e.name, r.weight FROM relations r JOIN entities e ON r.target_id = e.id "
            "WHERE r.source_id = ? ORDER BY r.weight DESC",
            (src_id,),
        ).fetchall()

        assert len(rows) == 2
        assert rows[0]["name"] == "high_pri"
        assert rows[1]["name"] == "low_pri"


# ===========================================================================
# Recursive CTE Graph Traversal
# ===========================================================================

class TestGraphTraversal:
    """Test recursive CTE queries for graph exploration."""

    def test_find_all_downstream_loads(self, seeded_db):
        """Find all loads reachable from the distribution zone via 'connected_to'."""
        # In the seed data, loads are connected_to the distribution_zone (id=4)
        rows = seeded_db.execute("""
            WITH RECURSIVE downstream AS (
                SELECT id, name, type FROM entities WHERE name = 'distribution_zone'
                UNION ALL
                SELECT e.id, e.name, e.type
                FROM entities e
                JOIN relations r ON r.source_id = e.id
                JOIN downstream d ON r.target_id = d.id
                WHERE r.relation = 'connected_to'
            )
            SELECT name, type FROM downstream WHERE type = 'load'
        """).fetchall()

        load_names = {row["name"] for row in rows}
        assert "health_post" in load_names
        assert "school" in load_names
        assert "community_center" in load_names
        assert len(load_names) >= 5, f"Expected at least 5 loads, got {len(load_names)}"

    def test_find_all_power_sources(self, seeded_db):
        """Find all devices that power the distribution zone."""
        rows = seeded_db.execute("""
            SELECT e.name, e.type
            FROM relations r
            JOIN entities e ON r.source_id = e.id
            WHERE r.relation = 'powers'
              AND r.target_id = (SELECT id FROM entities WHERE name = 'distribution_zone')
        """).fetchall()

        source_names = {row["name"] for row in rows}
        assert "solar_inverter" in source_names
        assert "battery_inverter" in source_names
        assert "diesel_genset" in source_names

    def test_transitive_reachability(self, db):
        """Test multi-hop graph traversal with recursive CTE."""
        # Build a chain: A -> B -> C -> D
        for name in ["A", "B", "C", "D"]:
            db.execute("INSERT INTO entities (type, name) VALUES ('node', ?)", (name,))
        db.commit()

        ids = {}
        for name in ["A", "B", "C", "D"]:
            ids[name] = db.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()[0]

        for src, tgt in [("A", "B"), ("B", "C"), ("C", "D")]:
            db.execute(
                "INSERT INTO relations (source_id, relation, target_id) VALUES (?, 'connects', ?)",
                (ids[src], ids[tgt]),
            )
        db.commit()

        # Find all nodes reachable from A
        rows = db.execute("""
            WITH RECURSIVE reachable AS (
                SELECT id, name, 0 AS depth FROM entities WHERE name = 'A'
                UNION ALL
                SELECT e.id, e.name, r2.depth + 1
                FROM entities e
                JOIN relations r ON r.source_id = r2.id AND r.target_id = e.id AND r.relation = 'connects'
                JOIN reachable r2 ON r.source_id = r2.id
            )
            SELECT DISTINCT name, depth FROM reachable ORDER BY depth
        """).fetchall()

        names = [row["name"] for row in rows]
        assert names == ["A", "B", "C", "D"], f"Expected [A,B,C,D] got {names}"

    def test_cycle_detection_with_limit(self, db):
        """Recursive CTE should handle cycles with LIMIT."""
        db.execute("INSERT INTO entities (type, name) VALUES ('node', 'X')")
        db.execute("INSERT INTO entities (type, name) VALUES ('node', 'Y')")
        db.commit()

        x_id = db.execute("SELECT id FROM entities WHERE name = 'X'").fetchone()[0]
        y_id = db.execute("SELECT id FROM entities WHERE name = 'Y'").fetchone()[0]

        # Create a cycle: X -> Y -> X
        db.execute("INSERT INTO relations (source_id, relation, target_id) VALUES (?, 'links', ?)", (x_id, y_id))
        db.execute("INSERT INTO relations (source_id, relation, target_id) VALUES (?, 'links', ?)", (y_id, x_id))
        db.commit()

        # Query with LIMIT to prevent infinite recursion
        rows = db.execute("""
            WITH RECURSIVE traverse AS (
                SELECT id, name, 0 AS depth FROM entities WHERE name = 'X'
                UNION ALL
                SELECT e.id, e.name, t.depth + 1
                FROM entities e
                JOIN relations r ON r.target_id = e.id
                JOIN traverse t ON r.source_id = t.id
                WHERE t.depth < 5
            )
            SELECT name, depth FROM traverse LIMIT 20
        """).fetchall()

        # Should not crash, and should have entries
        assert len(rows) > 0
        assert len(rows) <= 20, "LIMIT should prevent unbounded results"


# ===========================================================================
# Pattern Learning Tests
# ===========================================================================

class TestPatternLearning:
    """Test pattern learning from observation data."""

    def test_insert_pattern(self, db):
        """Insert a load pattern observation."""
        db.execute("INSERT INTO entities (type, name) VALUES ('load', 'test_load')")
        db.commit()
        entity_id = db.execute("SELECT id FROM entities WHERE name = 'test_load'").fetchone()[0]

        db.execute(
            "INSERT INTO patterns (entity_id, pattern_type, hour, avg_load, std_load, count) "
            "VALUES (?, 'load_profile', 12, 5.0, 0.8, 1)",
            (entity_id,),
        )
        db.commit()

        row = db.execute(
            "SELECT * FROM patterns WHERE entity_id = ? AND hour = 12",
            (entity_id,),
        ).fetchone()

        assert row is not None
        assert row["avg_load"] == 5.0
        assert row["count"] == 1

    def test_update_running_average(self, db):
        """Simulate incremental pattern learning with running average."""
        db.execute("INSERT INTO entities (type, name) VALUES ('load', 'sensor')")
        db.commit()
        entity_id = db.execute("SELECT id FROM entities WHERE name = 'sensor'").fetchone()[0]

        # Insert initial observation
        db.execute(
            "INSERT INTO patterns (entity_id, pattern_type, hour, avg_load, std_load, count) "
            "VALUES (?, 'load_profile', 14, 10.0, 0.0, 1)",
            (entity_id,),
        )
        db.commit()

        # Simulate a new observation of 12.0 kW at hour 14
        new_value = 12.0
        db.execute("""
            UPDATE patterns
            SET avg_load = (avg_load * count + ?) / (count + 1),
                count = count + 1,
                updated_at = datetime('now')
            WHERE entity_id = ? AND pattern_type = 'load_profile' AND hour = 14
        """, (new_value, entity_id))
        db.commit()

        row = db.execute(
            "SELECT avg_load, count FROM patterns WHERE entity_id = ? AND hour = 14",
            (entity_id,),
        ).fetchone()

        assert row["count"] == 2
        assert row["avg_load"] == pytest.approx(11.0, abs=0.01), \
            "Running average of (10.0 + 12.0) / 2 should be 11.0"

    def test_pattern_query_by_time(self, db):
        """Query patterns for a specific time window."""
        db.execute("INSERT INTO entities (type, name) VALUES ('load', 'pump')")
        db.commit()
        entity_id = db.execute("SELECT id FROM entities WHERE name = 'pump'").fetchone()[0]

        # Insert patterns for different hours
        for hour, load in [(6, 3.0), (7, 5.0), (8, 7.0), (12, 4.0), (18, 6.0)]:
            db.execute(
                "INSERT INTO patterns (entity_id, pattern_type, hour, avg_load, count) "
                "VALUES (?, 'load_profile', ?, ?, 10)",
                (entity_id, hour, load),
            )
        db.commit()

        # Query morning hours (6-9)
        rows = db.execute(
            "SELECT hour, avg_load FROM patterns "
            "WHERE entity_id = ? AND hour BETWEEN 6 AND 9 ORDER BY hour",
            (entity_id,),
        ).fetchall()

        assert len(rows) == 3
        assert rows[1]["avg_load"] == 5.0  # hour 7

    def test_seed_data_patterns(self, seeded_db):
        """Verify seed data patterns are loaded correctly."""
        # Check that the health_post has load patterns
        health_id = seeded_db.execute(
            "SELECT id FROM entities WHERE name = 'health_post'"
        ).fetchone()[0]

        patterns = seeded_db.execute(
            "SELECT COUNT(*) FROM patterns WHERE entity_id = ?",
            (health_id,),
        ).fetchone()[0]

        assert patterns > 0, "Health post should have load patterns from seed data"

    def test_aggregate_daily_pattern(self, db):
        """Test aggregating hourly patterns into a daily summary."""
        db.execute("INSERT INTO entities (type, name) VALUES ('load', 'agg_test')")
        db.commit()
        entity_id = db.execute("SELECT id FROM entities WHERE name = 'agg_test'").fetchone()[0]

        # Insert 24 hours of pattern data
        for hour in range(24):
            load = 5.0 + 10.0 * (1 if 7 <= hour <= 20 else 0)  # 5kW base, +10kW during day
            db.execute(
                "INSERT INTO patterns (entity_id, pattern_type, hour, avg_load, count) "
                "VALUES (?, 'load_profile', ?, ?, 30)",
                (entity_id, hour, load),
            )
        db.commit()

        # Aggregate: average load across all hours
        row = db.execute(
            "SELECT AVG(avg_load) as daily_avg, MAX(avg_load) as peak, MIN(avg_load) as min_load "
            "FROM patterns WHERE entity_id = ?",
            (entity_id,),
        ).fetchone()

        assert row["peak"] == 15.0, "Peak should be 15kW (5 base + 10 day)"
        assert row["min_load"] == 5.0, "Minimum should be 5kW (night base)"
        assert row["daily_avg"] > 5.0, "Daily average should be above night base"


# ===========================================================================
# Async KnowledgeGraph Tests (src.knowledge)
# ===========================================================================

from src.knowledge import KnowledgeGraph, Entity


@pytest.fixture
async def kg(tmp_path):
    """Create a temporary KnowledgeGraph instance."""
    db_path = tmp_path / "test_kg.db"
    graph = KnowledgeGraph(db_path)
    await graph.open()
    yield graph
    await graph.close()


class TestRecursiveCteTraversal:
    """Test recursive CTE traversal via async KnowledgeGraph.query_affected()."""

    @pytest.mark.asyncio
    async def test_query_affected_finds_downstream(self, kg):
        """query_affected should find entities downstream via relations."""
        await kg.add_entity("bus-1", "bus", "Main Bus")
        await kg.add_entity("load-1", "load", "Hospital", priority=2)
        await kg.add_entity("load-2", "load", "School", priority=1)
        await kg.add_relation("bus-1", "load-1", "feeds")
        await kg.add_relation("bus-1", "load-2", "feeds")

        affected = await kg.query_affected("bus-1", max_depth=3)
        affected_ids = {e.id for e in affected}
        assert "load-1" in affected_ids
        assert "load-2" in affected_ids

    @pytest.mark.asyncio
    async def test_query_affected_multi_hop(self, kg):
        """Multi-hop traversal: A -> B -> C should find C from A."""
        await kg.add_entity("A", "bus", "Bus A")
        await kg.add_entity("B", "bus", "Bus B")
        await kg.add_entity("C", "load", "Load C", priority=1)
        await kg.add_relation("A", "B", "feeds")
        await kg.add_relation("B", "C", "feeds")

        affected = await kg.query_affected("A", max_depth=3)
        affected_ids = {e.id for e in affected}
        assert "B" in affected_ids
        assert "C" in affected_ids

    @pytest.mark.asyncio
    async def test_query_affected_respects_depth(self, kg):
        """Traversal should not go beyond max_depth."""
        await kg.add_entity("A", "bus", "A")
        await kg.add_entity("B", "bus", "B")
        await kg.add_entity("C", "bus", "C")
        await kg.add_entity("D", "load", "D")
        await kg.add_relation("A", "B", "feeds")
        await kg.add_relation("B", "C", "feeds")
        await kg.add_relation("C", "D", "feeds")

        # depth=2 should find B and C but not D (which is 3 hops)
        affected = await kg.query_affected("A", max_depth=2)
        affected_ids = {e.id for e in affected}
        assert "B" in affected_ids
        assert "C" in affected_ids
        assert "D" not in affected_ids

    @pytest.mark.asyncio
    async def test_query_affected_empty(self, kg):
        """Entity with no outgoing relations should return empty list."""
        await kg.add_entity("orphan", "device", "Lone Device")
        affected = await kg.query_affected("orphan")
        assert len(affected) == 0


class TestPatternLearningUpdatesStats:
    """Pattern learning via update_hourly_pattern updates running stats."""

    @pytest.mark.asyncio
    async def test_first_observation_creates_pattern(self, kg):
        """First call to update_hourly_pattern should create a new pattern row."""
        await kg.add_entity("load-x", "load", "Test Load")
        await kg.update_hourly_pattern("load-x", hour=10, value=5.0)

        cursor = await kg._db.execute(
            "SELECT avg_value, sample_count FROM patterns WHERE entity_id = 'load-x' AND hour_of_day = 10"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["avg_value"] == pytest.approx(5.0)
        assert row["sample_count"] == 1

    @pytest.mark.asyncio
    async def test_multiple_observations_update_mean(self, kg):
        """Multiple observations should update the running average."""
        await kg.add_entity("load-y", "load", "Test Load Y")
        await kg.update_hourly_pattern("load-y", hour=14, value=10.0)
        await kg.update_hourly_pattern("load-y", hour=14, value=12.0)
        await kg.update_hourly_pattern("load-y", hour=14, value=11.0)

        cursor = await kg._db.execute(
            "SELECT avg_value, sample_count FROM patterns WHERE entity_id = 'load-y' AND hour_of_day = 14"
        )
        row = await cursor.fetchone()
        assert row["sample_count"] == 3
        assert row["avg_value"] == pytest.approx(11.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_load_observation_updates_entity(self, kg):
        """update_load_observation should update entity avg_load_kw."""
        await kg.add_entity("load-z", "load", "Test Load Z")
        await kg.update_load_observation("load-z", 5.0)
        await kg.update_load_observation("load-z", 7.0)

        entity = await kg.get_entity("load-z")
        assert entity is not None
        assert entity.avg_load_kw == pytest.approx(6.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_std_updates_with_observations(self, kg):
        """Standard deviation should become non-zero with varying observations."""
        await kg.add_entity("load-std", "load", "Std Test")
        await kg.update_load_observation("load-std", 2.0)
        await kg.update_load_observation("load-std", 8.0)
        await kg.update_load_observation("load-std", 5.0)

        entity = await kg.get_entity("load-std")
        assert entity.std_load_kw > 0.0


class TestPriorityLoadsOrdering:
    """Priority loads should be returned in descending priority order."""

    @pytest.mark.asyncio
    async def test_priority_loads_descending(self, kg):
        """get_priority_loads should return loads ordered by priority DESC."""
        await kg.add_entity("l-low", "load", "Low Priority", priority=1)
        await kg.add_entity("l-mid", "load", "Mid Priority", priority=3)
        await kg.add_entity("l-high", "load", "High Priority", priority=5)
        await kg.add_entity("l-normal", "load", "Normal", priority=0)

        loads = await kg.get_priority_loads(min_priority=1)
        assert len(loads) == 3  # excludes priority=0
        assert loads[0].priority >= loads[1].priority >= loads[2].priority
        assert loads[0].id == "l-high"

    @pytest.mark.asyncio
    async def test_priority_loads_min_filter(self, kg):
        """min_priority filter should exclude lower priority loads."""
        await kg.add_entity("l1", "load", "L1", priority=1)
        await kg.add_entity("l2", "load", "L2", priority=2)
        await kg.add_entity("l3", "load", "L3", priority=3)

        loads = await kg.get_priority_loads(min_priority=2)
        assert len(loads) == 2
        assert all(e.priority >= 2 for e in loads)

    @pytest.mark.asyncio
    async def test_total_priority_load_kw(self, kg):
        """get_total_priority_load_kw should sum avg_load_kw of priority loads."""
        await kg.add_entity("lp1", "load", "LP1", priority=2)
        await kg.add_entity("lp2", "load", "LP2", priority=1)
        await kg.add_entity("lp0", "load", "LP0", priority=0)  # excluded

        # Simulate observations to set avg_load_kw
        await kg.update_load_observation("lp1", 3.0)
        await kg.update_load_observation("lp2", 5.0)
        await kg.update_load_observation("lp0", 10.0)  # should not be counted

        total = await kg.get_total_priority_load_kw(min_priority=1)
        assert total == pytest.approx(8.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_non_load_entities_excluded(self, kg):
        """Only 'load' kind entities should be returned by get_priority_loads."""
        await kg.add_entity("dev1", "device", "Solar Panel", priority=5)
        await kg.add_entity("load1", "load", "Hospital", priority=5)

        loads = await kg.get_priority_loads(min_priority=1)
        assert len(loads) == 1
        assert loads[0].id == "load1"
