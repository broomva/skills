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

import sqlite3
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import store as S  # noqa: E402

# Stands in for FetchDaemon.attests. Tests about the STORE are not about custody,
# so they say so explicitly rather than leaving the requirement unexercised --
# and test_observed_record_requires_an_attestor asserts the requirement itself.
ATTESTS_ALL = lambda url, digest: True   # noqa: E731
ATTESTS_NONE = lambda url, digest: False  # noqa: E731


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
    S.put_record(conn, node(id="n1"), attestor=ATTESTS_ALL)
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
    S.put_record(conn, node(id="a", depth=0, verdict="entailed"), attestor=ATTESTS_ALL)
    S.put_record(conn, node(id="b", depth=1, origin="simulated"), attestor=ATTESTS_ALL)
    S.put_record(conn, node(id="c", depth=2), attestor=ATTESTS_ALL)
    S.set_verdict(conn, "c", "refuted", "no such span")
    S.put_record(conn, node(id="d", depth=2, verdict="inconclusive"), attestor=ATTESTS_ALL)

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
        S.put_record(conn, r, attestor=ATTESTS_ALL)
    S.put_record(conn, node(id="ref"), attestor=ATTESTS_ALL)
    S.set_verdict(conn, "ref", "refuted", "nope")

    from_query = set(S.expandable_ids(conn))
    from_objects = {r.id for r in recs if r.expandable()}
    assert from_query == from_objects == {"ok"}


# ------------------------------------------------------------- re-sighting


def test_second_sighting_does_not_duplicate_but_is_counted(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    assert S.put_record(conn, node(id="n1"), by="w1", attestor=ATTESTS_ALL) == "inserted"
    assert S.put_record(conn, node(id="n1"), by="w2", attestor=ATTESTS_ALL) == "sighted"
    assert S.inventory(conn)["total"] == 1
    assert S.sighting_count(conn, "n1") == 2


def test_sighting_does_not_overwrite_a_verdict(tmp_path):
    """A later sighting is corroboration, not a correction that silently reopens."""
    conn = S.connect(tmp_path / "s.db")
    S.put_record(conn, node(id="n1"), attestor=ATTESTS_ALL)
    S.set_verdict(conn, "n1", "refuted", "checked and wrong")
    S.put_record(conn, node(id="n1"), by="w2", attestor=ATTESTS_ALL)
    assert S.get_record(conn, "n1")["verdict"] == "refuted"
    assert S.inventory(conn)["by_verdict"] == {"refuted": 1}
    assert S.expandable_ids(conn) == []


def test_a_differing_re_sighting_is_kept_as_a_conflict(tmp_path):
    """'Record everything' has no exception for the copy that lost a race."""
    conn = S.connect(tmp_path / "s.db")
    S.put_record(conn, node(id="n1", depth=1), by="w1", attestor=ATTESTS_ALL)
    out = S.put_record(conn, node(id="n1", depth=1, attrs={"role": "CTO"}), by="w2", attestor=ATTESTS_ALL)
    assert out == "conflicted"
    cf = S.conflicts(conn)
    assert len(cf) == 1 and cf[0]["payload"]["attrs"] == {"role": "CTO"}
    assert S.inventory(conn)["conflicts"] == 1


# ------------------------------------- one copy of each fact (BLOCKER, codex)


def test_generated_columns_cannot_be_written_directly(tmp_path):
    """Drift is impossible rather than detectable.

    The first schema stored verdict/origin/depth twice -- an indexed column and
    the payload. Cross-model review showed that writing origin='observed',
    verdict='entailed' onto a SIMULATED row made the scheduler expand it while a
    reader still saw no evidence. Overlaying the columns on read made it worse by
    concealing the contradiction. Generated columns remove the case: SQLite
    refuses the write outright.
    """
    conn = S.connect(tmp_path / "s.db")
    S.put_record(conn, node(id="n2", origin="simulated"), attestor=ATTESTS_ALL)
    with pytest.raises(sqlite3.OperationalError, match="generated column"):
        conn.execute("UPDATE records SET origin='observed' WHERE id='n2'")


def test_a_simulated_record_can_never_become_expandable_by_a_column_write(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.put_record(conn, node(id="n2", origin="simulated"), attestor=ATTESTS_ALL)
    for col in ("origin", "verdict"):
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(f"UPDATE records SET {col}='x' WHERE id='n2'")
    assert S.expandable_ids(conn) == []
    got = S.get_record(conn, "n2")
    assert got["origin"] == "simulated" and got["evidence"] is None


# ------------------------------- a refutation is never erased (BLOCKER, codex)


def test_a_refutation_cannot_be_silently_erased(tmp_path):
    """refuted -> entailed used to null the reason and re-expand the record.

    That resurrected a claim the crawl had already disproved AND dropped the
    disproof -- the exact inverse of "record everything".
    """
    conn = S.connect(tmp_path / "s.db")
    S.put_record(conn, node(id="n1"), attestor=ATTESTS_ALL)
    S.set_verdict(conn, "n1", "refuted", "the span does not say this")
    with pytest.raises(S.StoreError, match="requires an explicit `supersedes`"):
        S.set_verdict(conn, "n1", "entailed")
    assert S.get_record(conn, "n1")["verdict"] == "refuted"
    assert S.expandable_ids(conn) == []


def test_superseding_a_refutation_keeps_both_on_the_record(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.put_record(conn, node(id="n1"), attestor=ATTESTS_ALL)
    S.set_verdict(conn, "n1", "refuted", "misread the span")
    S.set_verdict(conn, "n1", "entailed", supersedes="re-read at the right offsets")

    hist = S.verdict_history(conn, "n1")
    assert [h["verdict"] for h in hist] == ["unchecked", "refuted", "entailed"]
    assert hist[1]["refutation"] == "misread the span", "the disproof survives"
    assert hist[2]["supersedes"] == "re-read at the right offsets"
    assert S.expandable_ids(conn) == ["n1"]


def test_verdict_history_is_append_only(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.put_record(conn, node(id="n1"), attestor=ATTESTS_ALL)
    S.set_verdict(conn, "n1", "inconclusive")
    S.set_verdict(conn, "n1", "refuted", "resolved against it")
    assert len(S.verdict_history(conn, "n1")) == 3


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
    assert first["key"] == "acme" and first["claim_token"]
    assert S.claim(conn, "w2", max_depth=4) is None


def test_claim_respects_the_depth_bound(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.push_frontier(conn, "deep", 9)
    assert S.claim(conn, "w1", max_depth=4) is None


def test_claim_is_breadth_first(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.push_frontier(conn, "deep", 3)
    S.push_frontier(conn, "shallow", 1)
    assert S.claim(conn, "w1", max_depth=5)["key"] == "shallow"


# ------------------------------------ crashed workers (BLOCKER, codex)


def test_an_expired_lease_is_reclaimable(tmp_path):
    """A worker that claims and dies must cost one lease, not the item.

    Before leases the row was excluded from claim() forever while
    frontier_stats reported remaining=0 -- a run that silently skipped work and
    called itself complete.
    """
    conn = S.connect(tmp_path / "s.db")
    S.push_frontier(conn, "acme", 0)
    first = S.claim(conn, "w1", max_depth=4, lease=10.0, now=1000.0)
    assert first["key"] == "acme"
    assert S.claim(conn, "w2", max_depth=4, now=1005.0) is None, "lease still held"

    again = S.claim(conn, "w2", max_depth=4, now=1011.0)
    assert again["key"] == "acme", "reclaimed after the lease lapsed"
    assert again["claim_token"] != first["claim_token"]


def test_an_expired_lease_is_not_counted_as_in_flight(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.push_frontier(conn, "acme", 0)
    S.claim(conn, "w1", max_depth=4, lease=10.0, now=1000.0)
    st = S.frontier_stats(conn, now=1011.0)
    assert st["expired"] == 1 and st["in_flight"] == 0
    assert st["remaining"] == 1, "a stranded item is still outstanding work"


def test_a_stale_token_cannot_finish_a_reclaimed_item(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.push_frontier(conn, "acme", 0)
    dead = S.claim(conn, "w1", max_depth=4, lease=10.0, now=1000.0)
    S.claim(conn, "w2", max_depth=4, now=1011.0)
    with pytest.raises(S.StoreError, match="no open item with that claim token"):
        S.finish(conn, "acme", dead["claim_token"])


# ---------------------------------- finish needs ownership (MAJOR, codex)


def test_finish_requires_a_claim_token(tmp_path):
    """finish(key) used to succeed for a caller that never claimed the item."""
    conn = S.connect(tmp_path / "s.db")
    S.push_frontier(conn, "acme", 0)
    with pytest.raises(S.StoreError, match="no open item with that claim token"):
        S.finish(conn, "acme", "not-a-real-token")
    assert S.frontier_stats(conn)["done"] == 0


def test_finish_with_the_right_token_completes(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    S.push_frontier(conn, "acme", 0)
    row = S.claim(conn, "w1", max_depth=4)
    S.finish(conn, "acme", row["claim_token"])
    assert S.frontier_stats(conn)["done"] == 1


# ------------------------------------------------------------ concurrency


def test_concurrent_claims_never_collide(tmp_path):
    """8 threads, 40 items, no key issued twice -- and no worker may die quietly.

    Thread.join() does not propagate exceptions, so a crashed worker used to
    leave both final assertions green while the others did its share.
    """
    db = tmp_path / "s.db"
    seed = S.connect(db)
    for i in range(40):
        S.push_frontier(seed, f"e{i:02d}", 0)

    taken: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker(name: str) -> None:
        try:
            conn = S.connect(db)
            while True:
                row = S.claim(conn, name, max_depth=4)
                if row is None:
                    return
                with lock:
                    taken.append(row["key"])
                S.finish(conn, row["key"], row["claim_token"])
        except BaseException as exc:  # noqa: BLE001 -- the point is to see it
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"a worker raised: {errors[:2]}"
    assert len(taken) == 40
    assert len(set(taken)) == 40, "no key was handed to two workers"
    assert S.frontier_stats(seed)["remaining"] == 0


def test_frontier_stats_reports_an_honest_remainder(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    for i in range(5):
        S.push_frontier(conn, f"e{i}", 0)
    S.claim(conn, "w1", max_depth=4, now=1000.0)
    st = S.frontier_stats(conn, now=1000.0)
    assert st == {"total": 5, "done": 0, "in_flight": 1, "expired": 0, "remaining": 4}


# ------------------------- custody reaches the store (BLOCKER, strata B)


def test_observed_record_requires_an_attestor(tmp_path):
    """The architectural hole: the daemon could prove custody and the store never asked.

    A Record carrying an entirely invented Evidence -- a url never requested, a
    digest of nothing -- was accepted and became expandable. The check existed at
    one entry point and the other entry point did not use it.
    """
    conn = S.connect(tmp_path / "s.db")
    with pytest.raises(S.StoreError, match="requires an attestor"):
        S.put_record(conn, node(id="x1"))


def test_unattested_evidence_is_refused(tmp_path):
    conn = S.connect(tmp_path / "s.db")
    fake = S.Evidence(url="https://example.com/never-fetched", sha256="f" * 64,
                      snapshot="snapshots/" + "f" * 64, span_start=0, span_end=4,
                      quote="FAKE")
    rec = S.Record(id="x1", kind="node", canonical_key="k", depth=3, layer="L2",
                   origin="observed", evidence=fake)
    with pytest.raises(S.StoreError, match="no fetch attests"):
        S.put_record(conn, rec, attestor=ATTESTS_NONE)
    assert S.inventory(conn)["total"] == 0
    assert S.expandable_ids(conn) == []


def test_a_simulated_record_needs_no_attestor(tmp_path):
    """Custody is about bytes. An inference has none and claims none."""
    conn = S.connect(tmp_path / "s.db")
    assert S.put_record(conn, node(id="s1", origin="simulated")) == "inserted"


def test_the_attestor_is_asked_about_the_cited_pair(tmp_path):
    """Not merely called -- called with the url and digest the record cites."""
    conn = S.connect(tmp_path / "s.db")
    seen = []
    S.put_record(conn, node(id="n1"), attestor=lambda u, d: (seen.append((u, d)), True)[1])
    assert seen == [("https://example.com/a", "a" * 64)]
