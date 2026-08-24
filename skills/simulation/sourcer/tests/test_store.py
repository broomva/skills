"""Tests for the sourcer store.

The invariants worth testing here are the ones that would be expensive to
discover later: that nothing is deleted, that a refuted record survives with its
refutation, that expansion is narrower than retention, and that two workers
racing the frontier produce one winner.

Several tests assert a REFUSAL. A store that silently accepted an unclassified
record would push the failure to whatever reads it next, by which point the
information needed to classify it is gone.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import store as S  # noqa: E402


def ev(url="https://example.com/a", digest="a" * 64, start=0, end=5, quote="ACME"):
    return S.Evidence(
        url=url, sha256=digest, snapshot=f"snapshots/{digest}", span_start=start,
        span_end=end, quote=quote,
    )


def node(id="n1", depth=0, origin="observed", verdict="unchecked", **kw):
    kw.setdefault("evidence", ev() if origin == "observed" else None)
    kw.setdefault("inferred_from", () if origin == "observed" else ("n0",))
    return S.Record(
        id=id, kind="node", canonical_key=f"key::{id}", depth=depth, layer="L2",
        origin=origin, verdict=verdict, **kw,
    )


# ---------------------------------------------------------------- lattice


def test_meet_origin_matches_provenance_ts_truth_table():
    """The lattice is duplicated in TypeScript; a divergence must fail here."""
    assert S.meet_origin("observed") == "observed"
    assert S.meet_origin("observed", "observed") == "observed"
    assert S.meet_origin("observed", "simulated") == "simulated"
    assert S.meet_origin("simulated", "observed") == "simulated"
    assert S.meet_origin("simulated", "simulated") == "simulated"


def test_meet_origin_of_nothing_is_observed():
    """Vacuous meet is the lattice top -- matches `[].includes()` being false."""
    assert S.meet_origin() == "observed"


# ------------------------------------------------------- birth-time typing


def test_observed_requires_evidence():
    with pytest.raises(S.StoreError, match="observed requires evidence"):
        S.Record(id="x", kind="node", canonical_key="k", depth=0, layer="L2",
                 origin="observed", evidence=None)


def test_observed_forbids_inferred_from():
    """Carrying both would make the record's own origin unanswerable."""
    with pytest.raises(S.StoreError, match="observed forbids inferred_from"):
        S.Record(id="x", kind="node", canonical_key="k", depth=0, layer="L2",
                 origin="observed", evidence=ev(), inferred_from=("n0",))


def test_simulated_requires_inferred_from():
    with pytest.raises(S.StoreError, match="simulated requires inferred_from"):
        S.Record(id="x", kind="node", canonical_key="k", depth=0, layer="L2",
                 origin="simulated")


def test_simulated_forbids_evidence():
    with pytest.raises(S.StoreError, match="simulated forbids evidence"):
        S.Record(id="x", kind="node", canonical_key="k", depth=0, layer="L2",
                 origin="simulated", inferred_from=("n0",), evidence=ev())


def test_edge_requires_its_three_parts():
    with pytest.raises(S.StoreError, match="needs src, dst and predicate"):
        S.Record(id="e", kind="edge", canonical_key="k", depth=1, layer="L2",
                 origin="observed", evidence=ev(), src="a", dst="b")


def test_refuted_requires_a_reason():
    """'We checked' and 'it passed' must not be able to look identical."""
    with pytest.raises(S.StoreError, match="refuted requires a refutation"):
        node(verdict="refuted")


def test_refutation_without_refuted_verdict_is_refused():
    with pytest.raises(S.StoreError, match="carries a refutation but verdict"):
        node(verdict="entailed", refutation="span does not say this")


def test_depth_and_layer_are_validated():
    with pytest.raises(S.StoreError, match="depth must be >= 0"):
        node(depth=-1)
    with pytest.raises(S.StoreError, match="layer must be L2 or L3"):
        S.Record(id="x", kind="node", canonical_key="k", depth=0, layer="L9",
                 origin="observed", evidence=ev())


# ------------------------------------------------- record everything (D5)


def test_refuted_record_is_retained_with_its_refutation(tmp_path):
    """The operator's rule: a claim paid for in tokens is kept even when wrong."""
    conn = S.connect(tmp_path / "s.db")
    S.put_record(conn, node(id="n1"))
    S.set_verdict(conn, "n1", "refuted", "the span does not mention this person")

    got = S.get_record(conn, "n1")
    assert got is not None, "a refuted record must survive -- nothing is deleted"
    assert got["verdict"] == "refuted"
    assert "does not mention" in got["refutation"]


def test_nothing_in_the_module_deletes():
    """Structural guard: 'record everything' is a property of the SQL, not a habit."""
    src = (Path(__file__).resolve().parents[1] / "scripts" / "store.py").read_text()
    lowered = src.lower()
    assert "delete from" not in lowered
    assert "drop table" not in lowered


def test_every_origin_and_verdict_survives_and_is_counted(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.put_record(conn, node(id="a", depth=0, verdict="entailed"))
    S.put_record(conn, node(id="b", depth=1, origin="simulated"))
    S.put_record(conn, node(id="c", depth=2))
    S.set_verdict(conn, "c", "refuted", "no such span")
    S.put_record(conn, node(id="d", depth=2, verdict="inconclusive"))

    inv = S.inventory(conn)
    assert inv["total"] == 4, "every record is retained regardless of verdict"
    assert inv["by_origin"] == {"observed": 3, "simulated": 1}
    assert inv["by_verdict"]["refuted"] == 1
    assert inv["by_verdict"]["inconclusive"] == 1
    assert inv["by_depth"] == {0: 1, 1: 1, 2: 2}, "depth is filterable downstream"


# --------------------------------------- expand only what verifies (D5's twin)


def test_expandable_is_narrower_than_retained():
    """Kept and trusted-enough-to-spend-budget-on are different questions."""
    assert node(verdict="entailed").expandable()
    assert not node(verdict="unchecked").expandable()
    assert not node(verdict="inconclusive").expandable()
    assert not node(verdict="refuted", refutation="r").expandable()
    # Observed+entailed only: an inference does not get to seed descendants
    # inferred from an inference.
    assert not node(origin="simulated", verdict="entailed").expandable()


def test_expandable_ids_agrees_with_the_dataclass(tmp_path):
    """The query and the method must not drift into disagreeing."""
    conn = S.connect(tmp_path / "s.db")
    recs = [
        node(id="ok", verdict="entailed"),
        node(id="sim", origin="simulated", verdict="entailed"),
        node(id="unchecked"),
        node(id="bad", verdict="inconclusive"),
    ]
    for r in recs:
        S.put_record(conn, r)
    S.put_record(conn, node(id="ref"))
    S.set_verdict(conn, "ref", "refuted", "nope")

    from_query = set(S.expandable_ids(conn))
    from_objects = {r.id for r in recs if r.expandable()}
    assert from_query == from_objects == {"ok"}


# ------------------------------------------------------------- re-sighting


def test_second_sighting_does_not_duplicate_but_is_counted(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    assert S.put_record(conn, node(id="n1"), by="w1") == "inserted"
    assert S.put_record(conn, node(id="n1"), by="w2") == "sighted"
    assert S.inventory(conn)["total"] == 1
    assert S.sighting_count(conn, "n1") == 2


def test_sighting_does_not_overwrite_a_verdict(tmp_path):
    """A later sighting is corroboration, not a correction that silently reopens.

    Asserted through BOTH read paths. The first version of this test checked
    only get_record(), which read the payload -- so a mutation that reset the
    verdict COLUMN survived, because the scheduler and the reader consult
    different copies of the same fact.
    """
    conn = S.connect(tmp_path / "s.db")
    S.put_record(conn, node(id="n1"))
    S.set_verdict(conn, "n1", "refuted", "checked and wrong")
    S.put_record(conn, node(id="n1"), by="w2")

    assert S.get_record(conn, "n1")["verdict"] == "refuted"
    assert S.inventory(conn)["by_verdict"] == {"refuted": 1}, "the column too"
    assert S.expandable_ids(conn) == [], "a re-sighted refutation must not expand"
    assert S.drifted(conn) == []


def test_column_and_payload_never_disagree(tmp_path):
    """The indexed columns are authoritative; drift is a reportable number."""
    conn = S.connect(tmp_path / "s.db")
    S.put_record(conn, node(id="a", verdict="entailed"))
    S.put_record(conn, node(id="b", depth=2, origin="simulated"))
    S.set_verdict(conn, "b", "refuted", "inferred from a refuted parent")
    assert S.drifted(conn) == []

    # Simulate a writer that updates only the column -- the exact shape the
    # mutation sweep exploited. drifted() must see it.
    conn.execute("UPDATE records SET verdict = 'entailed' WHERE id = 'b'")
    conn.commit()
    drift = S.drifted(conn)
    assert len(drift) == 1 and drift[0]["field"] == "verdict"
    # And the reader is not fooled into disagreeing with the scheduler.
    assert S.get_record(conn, "b")["verdict"] == "entailed"


# --------------------------------------------------------------- frontier


def test_push_is_idempotent(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    assert S.push_frontier(conn, "acme", 0) is True
    assert S.push_frontier(conn, "acme", 0) is False
    assert S.frontier_stats(conn)["total"] == 1


def test_claim_is_exclusive(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.push_frontier(conn, "acme", 0)
    first = S.claim(conn, "w1", max_depth=4)
    assert first["key"] == "acme"
    assert S.claim(conn, "w2", max_depth=4) is None, "a claimed item is not re-issued"


def test_claim_respects_the_depth_bound(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.push_frontier(conn, "deep", 9)
    assert S.claim(conn, "w1", max_depth=4) is None


def test_claim_is_breadth_first(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.push_frontier(conn, "deep", 3)
    S.push_frontier(conn, "shallow", 1)
    assert S.claim(conn, "w1", max_depth=5)["key"] == "shallow"


def test_concurrent_claims_never_collide(tmp_path):
    """The real test of the protocol: 8 threads, 40 items, no key issued twice."""
    db = tmp_path / "s.db"
    seed = S.connect(db)
    for i in range(40):
        S.push_frontier(seed, f"e{i:02d}", 0)

    taken: list[str] = []
    lock = threading.Lock()

    def worker(name: str) -> None:
        conn = S.connect(db)
        while True:
            row = S.claim(conn, name, max_depth=4)
            if row is None:
                return
            with lock:
                taken.append(row["key"])
            S.finish(conn, row["key"])

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(taken) == 40, f"every item claimed exactly once, got {len(taken)}"
    assert len(set(taken)) == 40, "no key was handed to two workers"
    assert S.frontier_stats(seed)["remaining"] == 0


def test_frontier_stats_reports_an_honest_remainder(tmp_path):
    """A partial run must be distinguishable from a complete one."""
    conn = S.connect(tmp_path / "s.db")
    for i in range(5):
        S.push_frontier(conn, f"e{i}", 0)
    S.claim(conn, "w1", max_depth=4)
    st = S.frontier_stats(conn)
    assert st == {"total": 5, "done": 0, "in_flight": 1, "remaining": 4}
