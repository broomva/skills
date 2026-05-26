"""Versioned SQL migration runner — idempotent, transactional."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from broomva_health.domain.time import utc_now

__all__ = ["MigrationRunner"]

_MIGRATION_FILENAME = re.compile(r"^(\d{3})_(.+)\.sql$")
_SCHEMA_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    "    version INTEGER PRIMARY KEY,"
    "    name TEXT NOT NULL,"
    "    applied_at TEXT NOT NULL"
    ")"
)


class MigrationRunner:
    """Discover and apply versioned SQL migrations to a SQLite database.

    Migrations are files named `NNN_some_label.sql` under `migrations_dir`
    (zero-padded 3-digit version, followed by an underscore, a label, and
    `.sql`). They are applied in numeric order; each runs in a transaction
    that also inserts the corresponding `schema_migrations` row, so a
    failure rolls back both the schema change and the tracking row.

    The runner is idempotent: calling `apply_all` repeatedly is safe and
    cheap — only previously-unseen versions are applied.
    """

    def __init__(self, connection: sqlite3.Connection, migrations_dir: Path) -> None:
        self._conn = connection
        self._dir = Path(migrations_dir)
        self._ensure_schema_table()

    def _ensure_schema_table(self) -> None:
        """Create `schema_migrations` if it doesn't exist."""
        self._conn.execute(_SCHEMA_TABLE_DDL)
        # No commit needed when connection is in autocommit mode (isolation_level=None).
        # Be defensive: commit if there is an open transaction.
        if self._conn.in_transaction:
            self._conn.commit()

    def applied_versions(self) -> set[int]:
        """Return the set of versions already applied."""
        self._ensure_schema_table()
        rows = self._conn.execute("SELECT version FROM schema_migrations").fetchall()
        return {int(row[0]) for row in rows}

    def pending(self) -> list[tuple[int, str, Path]]:
        """Discover migration files not yet applied.

        Returns:
            A list of `(version, name, path)` tuples in numeric order.
        """
        applied = self.applied_versions()
        found: list[tuple[int, str, Path]] = []
        if not self._dir.exists():
            return found
        for path in self._dir.iterdir():
            if not path.is_file():
                continue
            match = _MIGRATION_FILENAME.match(path.name)
            if not match:
                continue
            version = int(match.group(1))
            name = match.group(2)
            if version in applied:
                continue
            found.append((version, name, path))
        found.sort(key=lambda item: item[0])
        return found

    def apply_all(self) -> int:
        """Apply every pending migration in numeric order.

        Each migration is split into individual statements and executed
        inside an explicit transaction together with the
        `schema_migrations` insert. If any statement fails, the entire
        migration is rolled back — schema and tracking row both.

        We deliberately do NOT use `executescript()`: it auto-commits any
        pending transaction before running, which breaks BEGIN/COMMIT
        framing. Statement splitting is naive (split on `;`) but safe for
        the migrations we ship, which contain only `CREATE TABLE` and
        `CREATE INDEX` DDL with no embedded semicolons.

        Returns:
            The number of migrations newly applied (0 if up-to-date).
        """
        pending = self.pending()
        count = 0
        for version, name, path in pending:
            sql = path.read_text(encoding="utf-8")
            statements = _split_sql_statements(sql)
            self._conn.execute("BEGIN")
            try:
                for stmt in statements:
                    self._conn.execute(stmt)
                self._conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, utc_now().isoformat()),
                )
                self._conn.execute("COMMIT")
            except Exception:
                # Roll back BOTH the script changes and the tracking row.
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    # Already rolled back by the engine.
                    pass
                raise
            count += 1
        return count


def _split_sql_statements(sql: str) -> list[str]:
    """Split a SQL script into individual statements.

    Strips line comments (`-- ...`), then splits on `;`. Whitespace-only
    fragments are discarded. This is intentionally minimal — it only has
    to handle the DDL shapes we ship in `migrations/*.sql`.
    """
    cleaned_lines: list[str] = []
    for raw in sql.splitlines():
        idx = raw.find("--")
        line = raw if idx == -1 else raw[:idx]
        cleaned_lines.append(line)
    body = "\n".join(cleaned_lines)
    parts = [chunk.strip() for chunk in body.split(";")]
    return [p for p in parts if p]
