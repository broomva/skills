"""Migration 004 adds `producer` to every sample table's key without losing rows."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import broomva_health.migrations as migrations_pkg
from broomva_health.adapters.repositories.sqlite import SQLiteTraceRepository
from broomva_health.migrations.runner import MigrationRunner

MIGRATIONS = Path(migrations_pkg.__file__).parent


def test_upgrade_from_003_keeps_rows_and_widens_the_key(tmp_path: Path) -> None:
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    for f in sorted(MIGRATIONS.glob("00[123]_*.sql")):
        shutil.copy(f, old_dir / f.name)
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db, isolation_level=None)
    MigrationRunner(conn, old_dir).apply_all()
    conn.execute(
        "INSERT INTO quantity_sample VALUES ('garmin','heart_rate','2024-01-01T00:00:00+00:00',"
        "'2024-01-01T00:00:00+00:00',60,'bpm',NULL,NULL,'2024-01-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO category_sample VALUES ('garmin','sleep_stage','2024-01-01T00:00:00+00:00',"
        "'2024-01-01T01:00:00+00:00','deep',NULL,NULL,'2024-01-01T00:00:00+00:00')"
    )
    conn.close()

    repo = SQLiteTraceRepository(db)
    assert repo.migrate() == 1
    repo.close()

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT value, producer FROM quantity_sample").fetchall() == [(60.0, "")]
    assert conn.execute("SELECT category, producer FROM category_sample").fetchall() == [
        ("deep", "")
    ]
    for table in ("quantity_sample", "category_sample", "correlation_sample"):
        pk = [r[1] for r in conn.execute(f"PRAGMA table_info({table})") if r[5]]
        assert "producer" in pk, table
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {
        "ix_quantity_metric_start",
        "ix_quantity_source_metric_start",
        "ix_category_metric_start",
    } <= indexes
    conn.close()
