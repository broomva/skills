"""The sourcer store -- what a crawl records, and what it refuses to forget.

Two rules govern everything here, and they are not the same rule:

    Record everything.  Expand only what verifies.

The first is an operator decision (BRO-2282 D5, 2026-08-24): a claim that was
paid for in tokens is kept even when it turns out to be wrong, because a
downstream reader can filter what it can see and cannot filter what was thrown
away. So nothing in this module deletes. A refuted claim is retained *with its
refutation attached*; quarantine is a marked partition, never a `DELETE`.

The second keeps the first from being ruinous. If refuted nodes also seeded
subtrees, one hallucinated company at hop two would spend the entire fetch
budget on its imaginary descendants. So `expandable()` is deliberately narrow
and is the only thing that reads a verdict as permission.

Every record carries `origin`, `depth` and `layer` at birth, for the same reason
provenance.ts types values at birth: the information needed to separate them is
available only at the moment the record is created. There is no add-it-later
path, by construction rather than by discipline.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

# --------------------------------------------------------------------------
# The provenance lattice -- mirrors provenance.ts exactly.
# --------------------------------------------------------------------------

Origin = Literal["observed", "simulated"]


def meet_origin(*origins: Origin) -> Origin:
    """Contamination flows one way: anything derived from simulated is simulated.

    A meet on the two-element lattice observed > simulated. Kept
    byte-for-byte equivalent to `meetOrigin` in
    skills/simulation/parallax/runtime/src/core/provenance.ts -- if that
    changes, this must, and test_store.py asserts the truth table so the
    divergence is caught rather than discovered.
    """
    return "simulated" if "simulated" in origins else "observed"


# A claim's standing after verification. `unchecked` is the birth state and is
# NOT a synonym for `inconclusive`: one means nobody looked, the other means
# somebody looked and the artifact could not settle it. Collapsing them would
# let an unrun verifier read as a considered judgement.
Verdict = Literal["unchecked", "entailed", "refuted", "inconclusive"]

# The knowledge-graph tier a record belongs to, per CLAUDE.md's layer model.
# Carried so a consumer can filter by tier without re-deriving it.
Layer = Literal["L2", "L3"]

KIND = ("node", "edge")


class StoreError(Exception):
    """A refusal, raised where a silent coercion would lose provenance."""


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    """A pointer to bytes the fetch daemon put on disk.

    `span` is a byte range into the snapshot, not a substring to search for.
    Substring search lets a producer pick the needle after seeing the haystack;
    an offset is a location it had to commit to before the check ran.
    """

    url: str
    sha256: str
    snapshot: str
    span_start: int
    span_end: int
    quote: str

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "sha256": self.sha256,
            "snapshot": self.snapshot,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "quote": self.quote,
        }


@dataclass(frozen=True)
class Record:
    """One node or edge, typed at birth.

    The origin/evidence disjunction is enforced in `__post_init__` rather than
    checked by a later gate, because a record that reaches the store
    unclassified has already lost the information needed to classify it.
    """

    id: str
    kind: str
    canonical_key: str
    depth: int
    layer: Layer
    origin: Origin
    verdict: Verdict = "unchecked"
    evidence: Optional[Evidence] = None
    inferred_from: tuple[str, ...] = ()
    predicate: Optional[str] = None
    src: Optional[str] = None
    dst: Optional[str] = None
    refutation: Optional[str] = None
    attrs: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in KIND:
            raise StoreError(f"kind must be one of {KIND}, got {self.kind!r}")
        if self.depth < 0:
            raise StoreError(f"depth must be >= 0, got {self.depth}")
        if self.layer not in ("L2", "L3"):
            raise StoreError(f"layer must be L2 or L3, got {self.layer!r}")

        # The disjunction. `observed` means bytes exist; `simulated` means a
        # derivation exists. Neither may masquerade as the other, and a record
        # carrying both would make meet_origin unanswerable.
        if self.origin == "observed":
            if self.evidence is None:
                raise StoreError(f"{self.id}: observed requires evidence")
            if self.inferred_from:
                raise StoreError(
                    f"{self.id}: observed forbids inferred_from -- a value read "
                    "from bytes is not also derived from other records"
                )
        else:
            if not self.inferred_from:
                raise StoreError(f"{self.id}: simulated requires inferred_from")
            if self.evidence is not None:
                raise StoreError(
                    f"{self.id}: simulated forbids evidence -- attach the bytes to "
                    "the observed record they actually support"
                )

        if self.kind == "edge":
            if not (self.src and self.dst and self.predicate):
                raise StoreError(f"{self.id}: an edge needs src, dst and predicate")

        # A refutation is the evidence that a verdict was reached. Storing one
        # without the other is how "we checked" and "it passed" get conflated.
        if self.verdict == "refuted" and not self.refutation:
            raise StoreError(f"{self.id}: refuted requires a refutation reason")
        if self.refutation and self.verdict != "refuted":
            raise StoreError(
                f"{self.id}: carries a refutation but verdict is {self.verdict!r}"
            )

    def expandable(self) -> bool:
        """May this record's discoveries enter the frontier for depth+1?

        Deliberately narrow, and deliberately not the same question as "is this
        worth keeping". A simulated record is kept and reported; it does not get
        to spend the fetch budget on descendants inferred from an inference.
        """
        return self.origin == "observed" and self.verdict == "entailed"

    def as_dict(self) -> dict:
        d = {
            "id": self.id,
            "kind": self.kind,
            "canonical_key": self.canonical_key,
            "depth": self.depth,
            "layer": self.layer,
            "origin": self.origin,
            "verdict": self.verdict,
            "evidence": self.evidence.as_dict() if self.evidence else None,
            "inferred_from": list(self.inferred_from),
            "predicate": self.predicate,
            "src": self.src,
            "dst": self.dst,
            "refutation": self.refutation,
            "attrs": self.attrs,
        }
        return d


# --------------------------------------------------------------------------
# The store
# --------------------------------------------------------------------------

SCHEMA = """
PRAGMA journal_mode=WAL;

-- Records. Append-only by policy: `verdict` and `refutation` may be filled in
-- once, and nothing is ever removed. There is no DELETE anywhere in this file.
CREATE TABLE IF NOT EXISTS records (
  id             TEXT PRIMARY KEY,
  kind           TEXT NOT NULL,
  canonical_key  TEXT NOT NULL,
  depth          INTEGER NOT NULL,
  layer          TEXT NOT NULL,
  origin         TEXT NOT NULL,
  verdict        TEXT NOT NULL,
  payload        TEXT NOT NULL,
  first_seen     REAL NOT NULL,
  last_seen      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_depth  ON records(depth);
CREATE INDEX IF NOT EXISTS idx_records_origin ON records(origin);
CREATE INDEX IF NOT EXISTS idx_records_kind   ON records(kind);

-- Re-sightings. A second agent reaching a record a sibling already holds
-- records that it was seen again, rather than a duplicate -- this is the
-- "reconcile online" primitive, and the count is evidence of corroboration
-- breadth (not of truth: two outlets reprinting one release sight twice).
CREATE TABLE IF NOT EXISTS sightings (
  record_id  TEXT NOT NULL,
  at         REAL NOT NULL,
  by         TEXT NOT NULL,
  depth      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sightings_rec ON sightings(record_id);

-- The frontier. The one genuinely shared mutable structure, and therefore the
-- only place needing a concurrency protocol. `claimed_by` is set with a
-- conditional UPDATE so two agents cannot crawl one entity.
CREATE TABLE IF NOT EXISTS frontier (
  key         TEXT PRIMARY KEY,
  depth       INTEGER NOT NULL,
  parent_id   TEXT,
  claimed_by  TEXT,
  claimed_at  REAL,
  done_at     REAL
);
CREATE INDEX IF NOT EXISTS idx_frontier_open ON frontier(done_at, claimed_by, depth);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the store for concurrent use.

    WAL lets readers coexist with one writer; two writers still contend, and the
    default busy_timeout of 0 makes the loser raise "database is locked"
    instantly. Wait instead -- the claim and ledger writes are short.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def put_record(conn: sqlite3.Connection, rec: Record, by: str = "-") -> str:
    """Insert a record, or sight it again if already held.

    Returns "inserted" or "sighted". Never overwrites a record's substance: a
    second observation of the same canonical key is corroboration, not a
    correction, and treating it as an overwrite would silently drop whichever
    copy lost the race.
    """
    now = time.time()
    cur = conn.execute("SELECT id FROM records WHERE id = ?", (rec.id,))
    if cur.fetchone() is None:
        conn.execute(
            "INSERT INTO records (id, kind, canonical_key, depth, layer, origin,"
            " verdict, payload, first_seen, last_seen)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                rec.id,
                rec.kind,
                rec.canonical_key,
                rec.depth,
                rec.layer,
                rec.origin,
                rec.verdict,
                json.dumps(rec.as_dict(), sort_keys=True),
                now,
                now,
            ),
        )
        outcome = "inserted"
    else:
        conn.execute("UPDATE records SET last_seen = ? WHERE id = ?", (now, rec.id))
        outcome = "sighted"
    conn.execute(
        "INSERT INTO sightings (record_id, at, by, depth) VALUES (?,?,?,?)",
        (rec.id, now, by, rec.depth),
    )
    conn.commit()
    return outcome


def set_verdict(
    conn: sqlite3.Connection,
    record_id: str,
    verdict: Verdict,
    refutation: Optional[str] = None,
) -> None:
    """Attach a verifier's judgement. The record itself is never removed.

    Refuted records stay in the store, carrying the reason they were refuted, so
    a reader can see what the crawl believed and why it stopped believing it.
    """
    if verdict == "refuted" and not refutation:
        raise StoreError(f"{record_id}: refuted requires a refutation reason")
    row = conn.execute(
        "SELECT payload FROM records WHERE id = ?", (record_id,)
    ).fetchone()
    if row is None:
        raise StoreError(f"{record_id}: no such record")
    payload = json.loads(row["payload"])
    payload["verdict"] = verdict
    payload["refutation"] = refutation
    conn.execute(
        "UPDATE records SET verdict = ?, payload = ? WHERE id = ?",
        (verdict, json.dumps(payload, sort_keys=True), record_id),
    )
    conn.commit()


def get_record(conn: sqlite3.Connection, record_id: str) -> Optional[dict]:
    """Read a record, with the indexed columns overlaid onto the payload.

    `verdict`, `origin`, `depth` and `layer` are stored twice: as columns, so
    they can be queried and grouped, and inside the payload, so a record round
    trips as one object. Two copies of a fact will eventually disagree, and a
    reader that happened to consult the payload while `expandable_ids` consulted
    the column would then be reading a different record than the scheduler was.

    Mutation testing found exactly that: an UPDATE that touched only the column
    left the payload stale and every payload-reading assertion still passed. The
    columns are therefore authoritative and are overlaid here, so the two cannot
    be observed disagreeing even if a writer updates only one.
    """
    row = conn.execute(
        "SELECT payload, verdict, origin, depth, layer FROM records WHERE id = ?",
        (record_id,),
    ).fetchone()
    if row is None:
        return None
    payload = json.loads(row["payload"])
    payload["verdict"] = row["verdict"]
    payload["origin"] = row["origin"]
    payload["depth"] = row["depth"]
    payload["layer"] = row["layer"]
    return payload


def drifted(conn: sqlite3.Connection) -> list[dict]:
    """Records whose indexed columns disagree with their stored payload.

    Should always be empty. It is a query rather than an assertion because the
    gate suite reports it as a number, and a check that can only crash cannot be
    counted -- a denominator of zero is indistinguishable from a pass.
    """
    out = []
    for r in conn.execute(
        "SELECT id, payload, verdict, origin, depth, layer FROM records"
    ):
        p = json.loads(r["payload"])
        for col in ("verdict", "origin", "depth", "layer"):
            if p.get(col) != r[col]:
                out.append(
                    {"id": r["id"], "field": col, "column": r[col], "payload": p.get(col)}
                )
    return out


def sighting_count(conn: sqlite3.Connection, record_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM sightings WHERE record_id = ?", (record_id,)
    ).fetchone()["n"]


# --------------------------------------------------------------------------
# The frontier
# --------------------------------------------------------------------------


def push_frontier(
    conn: sqlite3.Connection, key: str, depth: int, parent_id: Optional[str] = None
) -> bool:
    """Offer an entity for crawling at `depth`. Returns True if newly queued.

    Re-offering a key already seen is a no-op rather than a duplicate row: the
    visited set and the queue are the same table, which is what makes
    "have we already been here" answerable without a second structure that can
    disagree with this one.
    """
    try:
        conn.execute(
            "INSERT INTO frontier (key, depth, parent_id) VALUES (?,?,?)",
            (key, depth, parent_id),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def claim(conn: sqlite3.Connection, worker: str, max_depth: int) -> Optional[sqlite3.Row]:
    """Atomically take one unclaimed frontier item, shallowest first.

    The conditional UPDATE is the whole concurrency protocol. Two workers racing
    the same row produce one winner and one `rowcount == 0`, because SQLite
    serialises writers -- so no lease, no lock file, and no clock is involved.
    """
    while True:
        row = conn.execute(
            "SELECT key, depth, parent_id FROM frontier"
            " WHERE claimed_by IS NULL AND done_at IS NULL AND depth <= ?"
            " ORDER BY depth ASC, key ASC LIMIT 1",
            (max_depth,),
        ).fetchone()
        if row is None:
            return None
        cur = conn.execute(
            "UPDATE frontier SET claimed_by = ?, claimed_at = ?"
            " WHERE key = ? AND claimed_by IS NULL AND done_at IS NULL",
            (worker, time.time(), row["key"]),
        )
        conn.commit()
        if cur.rowcount == 1:
            return row
        # Lost the race; another worker holds it. Try the next one.


def finish(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("UPDATE frontier SET done_at = ? WHERE key = ?", (time.time(), key))
    conn.commit()


def frontier_stats(conn: sqlite3.Connection) -> dict:
    """The denominator, and the parts of it that cannot lie.

    `remaining` is what a run that stops early must report, because a
    fully-green partial answer and a fully-green complete one are
    indistinguishable without it.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN done_at IS NOT NULL THEN 1 ELSE 0 END) AS done,"
        " SUM(CASE WHEN claimed_by IS NOT NULL AND done_at IS NULL THEN 1 ELSE 0 END) AS in_flight"
        " FROM frontier"
    ).fetchone()
    total = row["total"] or 0
    done = row["done"] or 0
    in_flight = row["in_flight"] or 0
    return {
        "total": total,
        "done": done,
        "in_flight": in_flight,
        "remaining": total - done - in_flight,
    }


def inventory(conn: sqlite3.Connection) -> dict:
    """Everything the store holds, partitioned rather than filtered.

    Reported by depth, origin and verdict so that "record everything" stays
    auditable: a consumer that wants only hop<=2 observed-entailed rows can say
    so, and can also see exactly how much it chose not to look at.
    """
    by_depth: dict[int, int] = {}
    for r in conn.execute("SELECT depth, COUNT(*) AS n FROM records GROUP BY depth"):
        by_depth[r["depth"]] = r["n"]
    by_origin: dict[str, int] = {}
    for r in conn.execute("SELECT origin, COUNT(*) AS n FROM records GROUP BY origin"):
        by_origin[r["origin"]] = r["n"]
    by_verdict: dict[str, int] = {}
    for r in conn.execute("SELECT verdict, COUNT(*) AS n FROM records GROUP BY verdict"):
        by_verdict[r["verdict"]] = r["n"]
    by_kind: dict[str, int] = {}
    for r in conn.execute("SELECT kind, COUNT(*) AS n FROM records GROUP BY kind"):
        by_kind[r["kind"]] = r["n"]
    total = conn.execute("SELECT COUNT(*) AS n FROM records").fetchone()["n"]
    return {
        "total": total,
        "by_depth": dict(sorted(by_depth.items())),
        "by_origin": by_origin,
        "by_verdict": by_verdict,
        "by_kind": by_kind,
        "frontier": frontier_stats(conn),
    }


def expandable_ids(conn: sqlite3.Connection) -> list[str]:
    """Records permitted to seed the next hop -- observed AND entailed.

    Expressed as a query rather than by calling Record.expandable() per row so
    that the store and the dataclass cannot drift into disagreeing about which
    records spend the budget.
    """
    return [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM records WHERE origin = 'observed' AND verdict = 'entailed'"
            " ORDER BY id"
        )
    ]
