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

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, Protocol

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


class SupportsAdmits(Protocol):
    """Whatever decides an observed record may enter -- in practice FetchDaemon.

    A Protocol rather than a Callable so the store names the CAPABILITY it needs
    instead of a signature any lambda satisfies. `admitter=lambda ev: True` no
    longer type-checks, and the thing a reviewer must look for in a diff is a
    hand-rolled object rather than an inline expression.
    """

    def admits(self, ev) -> bool: ...


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

-- Records. The payload is the SINGLE source of truth; every queryable field is a
-- GENERATED column reading out of it.
--
-- The first version stored these as ordinary columns alongside the payload, so
-- each fact existed twice. Cross-model review demonstrated the consequence:
-- writing origin='observed', verdict='entailed' onto a simulated row made the
-- scheduler expand it while a reader still saw no evidence and a populated
-- inferred_from. The repair at the time -- overlaying the columns on read -- made
-- it worse, because it CONCEALED the contradiction instead of refusing it.
--
-- Generated columns remove the case rather than detect it. There is one copy, so
-- there is nothing to drift, and a hand-written UPDATE against a generated column
-- is rejected by SQLite rather than silently believed.
CREATE TABLE IF NOT EXISTS records (
  id             TEXT PRIMARY KEY,
  payload        TEXT NOT NULL,
  first_seen     REAL NOT NULL,
  last_seen      REAL NOT NULL,
  kind           TEXT    GENERATED ALWAYS AS (json_extract(payload,'$.kind'))    VIRTUAL,
  canonical_key  TEXT    GENERATED ALWAYS AS (json_extract(payload,'$.canonical_key')) VIRTUAL,
  depth          INTEGER GENERATED ALWAYS AS (json_extract(payload,'$.depth'))   VIRTUAL,
  layer          TEXT    GENERATED ALWAYS AS (json_extract(payload,'$.layer'))   VIRTUAL,
  origin         TEXT    GENERATED ALWAYS AS (json_extract(payload,'$.origin'))  VIRTUAL,
  verdict        TEXT    GENERATED ALWAYS AS (json_extract(payload,'$.verdict')) VIRTUAL,
  refutation     TEXT    GENERATED ALWAYS AS (json_extract(payload,'$.refutation')) VIRTUAL
);
CREATE INDEX IF NOT EXISTS idx_records_depth  ON records(depth);
CREATE INDEX IF NOT EXISTS idx_records_origin ON records(origin);
CREATE INDEX IF NOT EXISTS idx_records_kind   ON records(kind);

-- Verdict history. Append-only, and the reason "record everything" is a schema
-- property rather than a promise.
--
-- set_verdict() used to overwrite. Cross-model review showed a refuted record
-- could be resurrected -- set_verdict(id,'refuted','wrong') then
-- set_verdict(id,'entailed') left refutation NULL and put the record back in
-- expandable_ids(). A claim the crawl had already disproved returned to spending
-- the fetch budget, and the disproof was gone. That is the exact inverse of the
-- operator's instruction, so the history is now the record and the payload's
-- verdict is only its latest entry.
CREATE TABLE IF NOT EXISTS verdicts (
  record_id   TEXT NOT NULL,
  seq         INTEGER NOT NULL,
  at          REAL NOT NULL,
  verdict     TEXT NOT NULL,
  refutation  TEXT,
  supersedes  TEXT,
  PRIMARY KEY (record_id, seq)
);

-- Re-sightings. A second agent reaching a record a sibling already holds
-- records that it was seen again, rather than a duplicate -- this is the
-- "reconcile online" primitive, and the count is evidence of corroboration
-- breadth (not of truth: two outlets reprinting one release sight twice).
CREATE TABLE IF NOT EXISTS sightings (
  record_id  TEXT NOT NULL,
  at         REAL NOT NULL,
  by         TEXT NOT NULL,
  depth      INTEGER NOT NULL,
  conflict   TEXT
);
CREATE INDEX IF NOT EXISTS idx_sightings_rec ON sightings(record_id);

-- The frontier. The one genuinely shared mutable structure, and therefore the
-- only place needing a concurrency protocol. `claimed_by` is set with a
-- conditional UPDATE so two agents cannot crawl one entity.
-- The frontier. Claims carry an EXPIRING lease and an ownership token.
--
-- Without them a worker that claimed an item and died removed it from the crawl
-- permanently, while frontier_stats() reported remaining=0 -- a run that silently
-- skipped work and called itself complete. `finish` also accepted any caller, so
-- a key could be marked done by something that never held it.
CREATE TABLE IF NOT EXISTS frontier (
  key         TEXT PRIMARY KEY NOT NULL,
  depth       INTEGER NOT NULL,
  parent_id   TEXT,
  claimed_by  TEXT,
  claim_token TEXT,
  lease_until REAL,
  attempts    INTEGER NOT NULL DEFAULT 0,
  done_at     REAL
);
CREATE INDEX IF NOT EXISTS idx_frontier_open ON frontier(done_at, lease_until, depth);
"""

# How long a claim is held before another worker may reclaim it. A crashed
# worker costs one lease, not the item.
LEASE_SECONDS = 300.0


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


def put_record(
    conn: sqlite3.Connection,
    rec: Record,
    by: str = "-",
    admitter: Optional["SupportsAdmits"] = None,
) -> str:
    """Insert a record, or sight it again if already held.

    An `observed` record REQUIRES an `admitter` -- an object with `.admits(ev)`,
    which in practice is the `FetchDaemon` that fetched the bytes. Without one
    this refuses.

    It takes the OBJECT rather than a callable, and that is the whole point. The
    previous contract was `Callable[[Evidence], bool]`, and no method on
    FetchDaemon had that shape -- so every caller hand-wrote an adapter, every
    adapter wired to the narrowest available check, and the three guarantees
    `evidence_for` uniquely owned (status/emptiness, the whitespace-span refusal,
    and snapshot-derived-from-digest) were all bypassed at the one door that
    decides what a human reads. A contract nothing implements is a contract each
    caller invents.

    `FetchDaemon.admits` composes every check the daemon can make. The store asks
    one question and cannot be handed a weaker one by accident.

    That requirement is the whole custody architecture, and its absence was the
    hole cross-model review found. The daemon could prove bytes came off a wire,
    and the store never asked: a Record carrying an entirely invented Evidence --
    a url never requested, a digest of nothing -- was accepted and became
    expandable. The check existed at one entry point and the other entry point
    did not use it, which is the same shape as `verify_chain` having no caller.

    Passing `attestor=lambda *_: True` is possible and is the one thing a reader
    should look for in a diff. It is not defended against, because a store cannot
    stop its own caller lying to it; what it can do is make the lie explicit
    rather than the default.

    Returns "inserted", "sighted" or "conflicted". The insert is a single atomic
    statement -- the earlier SELECT-then-INSERT let two workers both observe an
    absent id and one then raise, losing a claim already paid for.

    A re-sighting never rewrites substance. Two records sharing a canonical key
    are corroboration; if their payloads genuinely differ the difference is kept
    as a conflict row rather than discarded, because "record everything" does not
    have an exception for the copy that lost a race.
    """
    if rec.origin == "observed":
        if admitter is None:
            raise StoreError(
                f"{rec.id}: an observed record requires an admitter. Its evidence "
                "claims bytes came from a url and that they say a particular "
                "thing, and nothing here has checked either -- pass the "
                "FetchDaemon that fetched them."
            )
        assert rec.evidence is not None  # guaranteed by __post_init__
        if not admitter.admits(rec.evidence):
            raise StoreError(
                f"{rec.id}: the attested bytes for {rec.evidence.url} at "
                f"{rec.evidence.sha256[:12]} do not say what this record quotes at "
                f"[{rec.evidence.span_start},{rec.evidence.span_end}). Either the "
                "bytes were never fetched, or the quote is not what is there. "
                "Record it as simulated with an inferred_from, or re-read the page."
            )
    now = time.time()
    payload = json.dumps(rec.as_dict(), sort_keys=True)
    cur = conn.execute(
        "INSERT INTO records (id, payload, first_seen, last_seen) VALUES (?,?,?,?)"
        " ON CONFLICT(id) DO NOTHING",
        (rec.id, payload, now, now),
    )
    inserted = cur.rowcount == 1
    if inserted:
        conn.execute(
            "INSERT INTO verdicts (record_id, seq, at, verdict, refutation)"
            " VALUES (?,?,?,?,?)",
            (rec.id, 0, now, rec.verdict, rec.refutation),
        )
    else:
        held = conn.execute(
            "SELECT payload FROM records WHERE id = ?", (rec.id,)
        ).fetchone()["payload"]
        conn.execute("UPDATE records SET last_seen = ? WHERE id = ?", (now, rec.id))
        if json.loads(held) != json.loads(payload):
            # Same identity, different substance. Keeping only the first would
            # silently drop a paid-for observation.
            conn.execute(
                "INSERT INTO sightings (record_id, at, by, depth, conflict)"
                " VALUES (?,?,?,?,?)",
                (rec.id, now, by, rec.depth, payload),
            )
            conn.commit()
            return "conflicted"
    conn.execute(
        "INSERT INTO sightings (record_id, at, by, depth, conflict) VALUES (?,?,?,?,NULL)",
        (rec.id, now, by, rec.depth),
    )
    conn.commit()
    return "inserted" if inserted else "sighted"


def set_verdict(
    conn: sqlite3.Connection,
    record_id: str,
    verdict: Verdict,
    refutation: Optional[str] = None,
    supersedes: Optional[str] = None,
) -> None:
    """Append a verdict. History is append-only; a refutation is never erased.

    Leaving a `refuted` verdict requires an explicit `supersedes` reason. Without
    that requirement the sequence refuted -> entailed silently resurrected a claim
    the crawl had already disproved AND dropped the disproof, which is the exact
    inverse of the rule this store exists to keep.
    """
    if verdict == "refuted" and not refutation:
        raise StoreError(f"{record_id}: refuted requires a refutation reason")
    # The lock comes FIRST. The previous version read the current verdict, then
    # began the transaction, so between the two another verifier could commit a
    # refutation that this call then overwrote without a supersedes reason -- the
    # round-3 defect reopened as a race. Checking state you read outside the lock
    # is checking a copy.
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        "SELECT payload, verdict FROM records WHERE id = ?", (record_id,)
    ).fetchone()
    if row is None:
        conn.execute("ROLLBACK")
        raise StoreError(f"{record_id}: no such record")

    current = row["verdict"]
    if current == "refuted" and verdict != "refuted" and not supersedes:
        conn.execute("ROLLBACK")
        raise StoreError(
            f"{record_id}: leaving a refuted verdict requires an explicit "
            "`supersedes` reason. A refutation is evidence, and evidence is not "
            "dropped because a later pass disagreed -- say why it is superseded "
            "and both stay on the record."
        )

    seq = conn.execute(
        "SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM verdicts WHERE record_id = ?",
        (record_id,),
    ).fetchone()["n"]
    conn.execute(
        "INSERT INTO verdicts (record_id, seq, at, verdict, refutation, supersedes)"
        " VALUES (?,?,?,?,?,?)",
        (record_id, seq, time.time(), verdict, refutation, supersedes),
    )
    payload = json.loads(row["payload"])
    payload["verdict"] = verdict
    payload["refutation"] = refutation
    conn.execute(
        "UPDATE records SET payload = ? WHERE id = ?",
        (json.dumps(payload, sort_keys=True), record_id),
    )
    conn.commit()


def verdict_history(conn: sqlite3.Connection, record_id: str) -> list[dict]:
    """Every verdict this record has ever carried, oldest first."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT seq, at, verdict, refutation, supersedes FROM verdicts"
            " WHERE record_id = ? ORDER BY seq",
            (record_id,),
        )
    ]


def get_record(conn: sqlite3.Connection, record_id: str) -> Optional[dict]:
    """Read a record. The payload is the only copy, so nothing is overlaid."""
    row = conn.execute(
        "SELECT payload FROM records WHERE id = ?", (record_id,)
    ).fetchone()
    return json.loads(row["payload"]) if row else None


def sighting_count(conn: sqlite3.Connection, record_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM sightings WHERE record_id = ?", (record_id,)
    ).fetchone()["n"]


def conflicts(conn: sqlite3.Connection) -> list[dict]:
    """Re-sightings whose substance differed from the record already held."""
    return [
        {"record_id": r["record_id"], "at": r["at"], "by": r["by"],
         "payload": json.loads(r["conflict"])}
        for r in conn.execute(
            "SELECT record_id, at, by, conflict FROM sightings"
            " WHERE conflict IS NOT NULL ORDER BY at"
        )
    ]


# --------------------------------------------------------------------------
# The frontier
# --------------------------------------------------------------------------


def push_frontier(
    conn: sqlite3.Connection, key: str, depth: int, parent_id: Optional[str] = None
) -> bool:
    """Offer an entity for crawling at `depth`. Returns True if newly queued.

    INSERT OR IGNORE rather than catching IntegrityError: the previous version
    swallowed *every* integrity error as "already present" and left the
    transaction open, so a genuinely invalid row read as a duplicate while the
    single WAL writer lock was still held.
    """
    cur = conn.execute(
        "INSERT OR IGNORE INTO frontier (key, depth, parent_id) VALUES (?,?,?)",
        (key, depth, parent_id),
    )
    if cur.rowcount == 0:
        # Already queued. If this sighting reached it by a SHORTER path, take the
        # shorter depth -- depth was birth-only, so an entity first seen at hop 4
        # and later found at hop 1 stayed at 4, could sit above max_depth, and was
        # then never claimable while still counted as outstanding work.
        # Only while unclaimed and unfinished: re-parenting something in flight
        # would change the depth a worker is already crawling against.
        conn.execute(
            "UPDATE frontier SET depth = ?, parent_id = ?"
            " WHERE key = ? AND depth > ? AND done_at IS NULL AND lease_until IS NULL",
            (depth, parent_id, key, depth),
        )
    conn.commit()
    return cur.rowcount == 1


def claim(
    conn: sqlite3.Connection,
    worker: str,
    max_depth: int,
    lease: float = LEASE_SECONDS,
    now: Optional[float] = None,
) -> Optional[sqlite3.Row]:
    """Atomically take one frontier item, shallowest first, under a lease.

    Returns a row carrying `claim_token`, which `finish` requires. An item whose
    lease has expired is reclaimable: a worker that crashed mid-item costs one
    lease, where before it removed the item from the crawl permanently while the
    run still reported itself complete.
    """
    t = time.time() if now is None else now
    for _ in range(64):
        row = conn.execute(
            "SELECT key, depth, parent_id, attempts FROM frontier"
            " WHERE done_at IS NULL AND depth <= ?"
            "   AND (lease_until IS NULL OR lease_until < ?)"
            " ORDER BY depth ASC, key ASC LIMIT 1",
            (max_depth, t),
        ).fetchone()
        if row is None:
            return None
        token = hashlib.sha256(
            f"{worker}:{row['key']}:{t}:{row['attempts']}".encode()
        ).hexdigest()[:16]
        cur = conn.execute(
            "UPDATE frontier SET claimed_by = ?, claim_token = ?, lease_until = ?,"
            " attempts = attempts + 1"
            " WHERE key = ? AND done_at IS NULL"
            "   AND (lease_until IS NULL OR lease_until < ?)",
            (worker, token, t + lease, row["key"], t),
        )
        conn.commit()
        if cur.rowcount == 1:
            return {
                "key": row["key"], "depth": row["depth"],
                "parent_id": row["parent_id"], "claim_token": token,
            }
        # Lost the race for this row; another worker holds it. Try the next.
    raise StoreError(
        "claim() exhausted 64 attempts without acquiring a row -- this is "
        "contention or a livelock, and looping forever would hide it"
    )


def held_lease(
    conn: sqlite3.Connection, key: str, claim_token: str, now: Optional[float] = None
) -> dict:
    """The frontier row this token currently holds a live lease on, or refuse.

    Split out of `finish` so authorisation can happen BEFORE any mutation rather
    than as a side effect of the last step. A caller that admitted records, wrote
    verdicts and expanded the frontier and only then discovered it never held the
    lease has already done all the damage the token exists to prevent.

    Returns the row, so the caller can take the item's DEPTH from the lease
    instead of from an argument. That removes a second class of defect rather
    than checking for it: depth arrived as a free parameter, so a worker holding
    a valid lease on a depth-2 item could land it as depth 0 and walk its
    descendants in under the sealed max_depth indefinitely.
    """
    t = time.time() if now is None else now
    row = conn.execute(
        "SELECT key, depth, parent_id FROM frontier"
        " WHERE key = ? AND claim_token = ? AND done_at IS NULL"
        "   AND lease_until IS NOT NULL AND lease_until >= ?",
        (key, claim_token, t),
    ).fetchone()
    if row is None:
        raise StoreError(
            f"{key}: no item held under that claim token with a live lease. It "
            "expired, was reclaimed, or was never claimed by you."
        )
    return {"key": row["key"], "depth": row["depth"], "parent_id": row["parent_id"]}


def finish(
    conn: sqlite3.Connection, key: str, claim_token: str, now: Optional[float] = None
) -> None:
    """Mark an item done. Only the holder of the current lease may.

    The token requirement is not ceremony: `finish(key)` used to succeed for any
    caller, including one that had never claimed the item, so a key could be
    marked done before it was ever crawled and the run would still look complete.
    """
    t = time.time() if now is None else now
    # The lease is part of the predicate, not merely the token. Checking the token
    # alone let a worker whose lease had already lapsed -- and whose item was
    # therefore available to anyone -- still mark it done, so work that was never
    # completed by its holder counted as complete.
    cur = conn.execute(
        "UPDATE frontier SET done_at = ?, lease_until = NULL"
        " WHERE key = ? AND claim_token = ? AND done_at IS NULL"
        "   AND lease_until IS NOT NULL AND lease_until >= ?",
        (t, key, claim_token, t),
    )
    conn.commit()
    if cur.rowcount != 1:
        raise StoreError(
            f"{key}: refusing to finish -- no item held under that claim token with "
            "a live lease. It expired, was reclaimed, or was never claimed by you."
        )


def frontier_stats(conn: sqlite3.Connection, now: Optional[float] = None) -> dict:
    """The denominator, and the parts of it that cannot lie.

    `expired` is counted separately from `in_flight`: an item whose lease lapsed
    is not being worked on, and folding it into either "done" or "in flight"
    is how a run that dropped work reports itself complete.
    """
    t = time.time() if now is None else now
    row = conn.execute(
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN done_at IS NOT NULL THEN 1 ELSE 0 END) AS done,"
        " SUM(CASE WHEN done_at IS NULL AND lease_until IS NOT NULL AND lease_until >= ?"
        "          THEN 1 ELSE 0 END) AS in_flight,"
        " SUM(CASE WHEN done_at IS NULL AND lease_until IS NOT NULL AND lease_until < ?"
        "          THEN 1 ELSE 0 END) AS expired"
        " FROM frontier",
        (t, t),
    ).fetchone()
    total = row["total"] or 0
    done = row["done"] or 0
    in_flight = row["in_flight"] or 0
    expired = row["expired"] or 0
    return {
        "total": total,
        "done": done,
        "in_flight": in_flight,
        "expired": expired,
        "remaining": total - done - in_flight,
    }


def inventory(conn: sqlite3.Connection) -> dict:
    """Everything the store holds, partitioned rather than filtered.

    Reported by depth, origin and verdict so that "record everything" stays
    auditable: a consumer wanting only hop<=2 observed-entailed rows can say so,
    and can also see exactly how much it chose not to look at.
    """
    def group(col: str) -> dict:
        return {
            r[col]: r["n"]
            for r in conn.execute(f"SELECT {col}, COUNT(*) AS n FROM records GROUP BY {col}")
        }

    total = conn.execute("SELECT COUNT(*) AS n FROM records").fetchone()["n"]
    n_conflicts = len(conflicts(conn))
    return {
        # `total` counts identities; `payloads_held` counts everything the run
        # paid for, including re-sightings whose substance differed. Reporting
        # only the first would satisfy "record everything" in storage and break it
        # in retrieval, which is the same claim being true and false at once.
        "total": total,
        "payloads_held": total + n_conflicts,
        "by_depth": dict(sorted(group("depth").items())),
        "by_origin": group("origin"),
        "by_verdict": group("verdict"),
        "by_kind": group("kind"),
        "by_layer": group("layer"),
        "conflicts": len(conflicts(conn)),
        "frontier": frontier_stats(conn),
    }


def select(
    conn: sqlite3.Connection,
    max_depth: Optional[int] = None,
    origin: Optional[Origin] = None,
    verdict: Optional[Verdict] = None,
    layer: Optional[Layer] = None,
    include_conflicts: bool = True,
) -> list[dict]:
    """Filter the map without re-crawling it.

    This is what "record everything, filter downstream" actually requires: the
    run keeps every claim it paid for, and a consumer says which slice it wants.
    Also the only reader of `layer`, which was until now validated, stored and
    read by nothing -- a field whose stated purpose had no implementation, which
    is indistinguishable from a field that does not work.
    """
    clauses, args = [], []
    if max_depth is not None:
        clauses.append("depth <= ?"); args.append(max_depth)
    if origin is not None:
        clauses.append("origin = ?"); args.append(origin)
    if verdict is not None:
        clauses.append("verdict = ?"); args.append(verdict)
    if layer is not None:
        clauses.append("layer = ?"); args.append(layer)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    out = [
        json.loads(r["payload"])
        for r in conn.execute(f"SELECT payload FROM records{where} ORDER BY id", args)
    ]
    if not include_conflicts:
        return out
    # Conflicting re-sightings are records the run paid for and chose to keep.
    # Excluding them from every reader made them invisible to everything except
    # conflicts(), so the data existed and could not be found.
    def matches(p: dict) -> bool:
        return (
            (max_depth is None or p.get("depth", 0) <= max_depth)
            and (origin is None or p.get("origin") == origin)
            and (verdict is None or p.get("verdict") == verdict)
            and (layer is None or p.get("layer") == layer)
        )

    out.extend(c["payload"] for c in conflicts(conn) if matches(c["payload"]))
    return sorted(out, key=lambda p: (p.get("id", ""), p.get("depth", 0)))


def expandable_ids(conn: sqlite3.Connection) -> list[str]:
    """Records permitted to seed the next hop -- observed AND entailed.

    A SQL query rather than a per-row call so the store and the dataclass cannot
    drift about which records spend the budget. Both now read the same single
    copy of each field, so they cannot disagree even in principle.
    """
    return [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM records WHERE origin = 'observed' AND verdict = 'entailed'"
            " ORDER BY id"
        )
    ]
