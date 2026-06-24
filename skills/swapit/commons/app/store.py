"""SQLite store for the swapit knowledge commons.

Content-addressed facts: identical contributions from different users share an id and
*corroborate* (count up) rather than duplicate. A fact is served only once it clears the
moderation gate (corroboration >= 2 OR confidence >= 0.7) — the Nous-gate analog. Raw
contributor tokens are never stored, only a short hash, so contributions stay anonymous.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

KINDS = ("product", "item_class_hazard", "alternative")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _status(confidence: float, corroboration: int) -> str:
    return "approved" if (corroboration >= 2 or confidence >= 0.7) else "pending"


class Store:
    def __init__(self, db_path: str | Path) -> None:
        self.path = str(db_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        # isolation_level=None → manual transaction control, so the explicit BEGIN IMMEDIATE
        # in upsert() is version-independent (and the `with conn:` block still commits/rolls back).
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # concurrent readers + a single writer
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init(self) -> None:
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS facts(
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    corroboration_count INTEGER NOT NULL,
                    contributors TEXT NOT NULL,
                    status TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                )"""
            )

    def upsert(self, fact: dict, token: str | None = None) -> dict:
        fid = fact["id"]
        kind = fact["kind"]
        payload = fact.get("payload", {})
        conf = float(payload.get("confidence", 0.5) or 0.5)
        tok_hash = hashlib.sha256(token.encode()).hexdigest()[:32] if token else None
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")  # take the write lock up front — atomic read-modify-write
            row = c.execute("SELECT * FROM facts WHERE id = ?", (fid,)).fetchone()
            if row:
                contributors = set(json.loads(row["contributors"]))
                if tok_hash:
                    contributors.add(tok_hash)
                corro = row["corroboration_count"] + 1
                conf = max(row["confidence"], conf)
                # corroboration means "I agree with THIS fact" — keep the first-seen payload;
                # never let a corroborator swap the meaning of an already-stored fact.
                c.execute(
                    "UPDATE facts SET confidence=?, corroboration_count=?, contributors=?, status=?, last_seen=? WHERE id=?",
                    (conf, corro, json.dumps(sorted(contributors)), _status(conf, corro), _now(), fid),
                )
            else:
                contributors = [tok_hash] if tok_hash else []
                now = _now()
                c.execute(
                    "INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?)",
                    (fid, kind, json.dumps(payload), conf, 1, json.dumps(contributors), _status(conf, 1), now, now),
                )
        return self.get(fid)  # type: ignore[return-value]

    def get(self, fid: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM facts WHERE id = ?", (fid,)).fetchone()
        return self._row(row) if row else None

    def list_since(self, since: str = "", min_corroboration: int = 1) -> list[dict]:
        with self._conn() as c:
            # >= (not >) so a fact whose last_seen equals the caller's cursor isn't dropped at
            # the second-resolution boundary; the client merge is idempotent so re-pulls are safe.
            rows = c.execute(
                "SELECT * FROM facts WHERE status='approved' AND last_seen >= ? AND corroboration_count >= ? ORDER BY last_seen",
                (since or "", min_corroboration),
            ).fetchall()
        return [self._row(r) for r in rows]

    def stats(self) -> dict:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            approved = c.execute("SELECT COUNT(*) FROM facts WHERE status='approved'").fetchone()[0]
        return {"facts_total": total, "facts_approved": approved}

    @staticmethod
    def _row(r: sqlite3.Row) -> dict:
        return {
            "id": r["id"],
            "kind": r["kind"],
            "payload": json.loads(r["payload"]),
            "confidence": r["confidence"],
            "corroboration_count": r["corroboration_count"],
            "contributor_count": len(json.loads(r["contributors"])),
            "status": r["status"],
            "first_seen": r["first_seen"],
            "last_seen": r["last_seen"],
        }
