"""MigrationRunner — discovery + apply + rollback semantics."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from broomva_health.migrations.runner import MigrationRunner


@pytest.fixture
def conn() -> sqlite3.Connection:
    """In-memory autocommit-mode connection per test."""
    c = sqlite3.connect(":memory:", isolation_level=None)
    yield c
    c.close()


def _write(migrations_dir: Path, name: str, sql: str) -> Path:
    migrations_dir.mkdir(parents=True, exist_ok=True)
    path = migrations_dir / name
    path.write_text(sql, encoding="utf-8")
    return path


def test_discovers_sql_files_in_order(tmp_path: Path, conn: sqlite3.Connection) -> None:
    mdir = tmp_path / "migrations"
    # Intentionally write out of numeric order.
    _write(mdir, "002_bar.sql", "CREATE TABLE bar (x INTEGER);")
    _write(mdir, "001_foo.sql", "CREATE TABLE foo (x INTEGER);")
    _write(mdir, "010_baz.sql", "CREATE TABLE baz (x INTEGER);")
    runner = MigrationRunner(conn, mdir)
    pending = runner.pending()
    assert [v for v, _, _ in pending] == [1, 2, 10]
    assert [n for _, n, _ in pending] == ["foo", "bar", "baz"]


def test_applies_pending_in_transaction(tmp_path: Path, conn: sqlite3.Connection) -> None:
    mdir = tmp_path / "migrations"
    _write(mdir, "001_foo.sql", "CREATE TABLE foo (x INTEGER);")
    _write(mdir, "002_bar.sql", "CREATE TABLE bar (x INTEGER);")
    runner = MigrationRunner(conn, mdir)
    assert runner.apply_all() == 2
    # Both tables exist.
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('foo', 'bar') "
        "ORDER BY name"
    ).fetchall()
    assert [r[0] for r in rows] == ["bar", "foo"]
    # schema_migrations now records both.
    assert runner.applied_versions() == {1, 2}
    # Idempotent — second apply is a no-op.
    assert runner.apply_all() == 0


def test_applied_versions_persists_across_runs(tmp_path: Path) -> None:
    db_file = tmp_path / "persist.db"
    mdir = tmp_path / "migrations"
    _write(mdir, "001_foo.sql", "CREATE TABLE foo (x INTEGER);")
    # First connection: apply once.
    c1 = sqlite3.connect(db_file, isolation_level=None)
    try:
        MigrationRunner(c1, mdir).apply_all()
    finally:
        c1.close()
    # Second connection: should see the migration as already applied.
    c2 = sqlite3.connect(db_file, isolation_level=None)
    try:
        runner = MigrationRunner(c2, mdir)
        assert runner.applied_versions() == {1}
        assert runner.apply_all() == 0
    finally:
        c2.close()


def test_partial_failure_rolls_back(tmp_path: Path, conn: sqlite3.Connection) -> None:
    mdir = tmp_path / "migrations"
    _write(mdir, "001_good.sql", "CREATE TABLE good (x INTEGER);")
    _write(mdir, "002_bad.sql", "CREATE TABLE bad (x INTEGER); SELECT * FROM nonexistent_table;")
    runner = MigrationRunner(conn, mdir)
    with pytest.raises(sqlite3.OperationalError):
        runner.apply_all()
    # Migration 1 applied + recorded (its txn committed before #2 ran).
    assert runner.applied_versions() == {1}
    # Migration 2 should be rolled back: bad's table must not exist AND row absent.
    bad_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'bad'"
    ).fetchone()
    assert bad_table is None
    has_two = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = 2"
    ).fetchone()
    assert has_two is None


def test_ignores_non_matching_filenames(tmp_path: Path, conn: sqlite3.Connection) -> None:
    mdir = tmp_path / "migrations"
    _write(mdir, "001_foo.sql", "CREATE TABLE foo (x INTEGER);")
    _write(mdir, "README.md", "not a migration")
    _write(mdir, "foo.sql", "not a migration either")  # no NNN_ prefix
    _write(mdir, "1_short.sql", "not zero-padded")  # only 1 digit
    _write(mdir, "001_foo.sql.bak", "backup file")
    runner = MigrationRunner(conn, mdir)
    pending = runner.pending()
    assert [v for v, _, _ in pending] == [1]
    assert runner.apply_all() == 1


def test_empty_migrations_dir(tmp_path: Path, conn: sqlite3.Connection) -> None:
    mdir = tmp_path / "migrations"
    mdir.mkdir()
    runner = MigrationRunner(conn, mdir)
    assert runner.pending() == []
    assert runner.apply_all() == 0
    # schema_migrations should still exist (created by __init__).
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchall()
    assert len(rows) == 1
