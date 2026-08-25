"""Tests for the gate suite.

The suite's own job is to catch defects, so the tests here are mostly one level
up: they check that the suite *can* say no, and that it says no for the right
reason. Three properties carry most of the weight.

  - A fail-closed gate that could not run must make the run INVALID. The
    tempting reading -- "nobody objected, so pass" -- is what turns the two
    judgement gates into decoration, and there is a test for each direction.
  - Every gate reports a denominator. A gate over zero items must be
    distinguishable from a gate that passed, which is why `counted` is asserted
    and not just `status`.
  - The decoy harness must itself be non-vacuous: every probe answered
    correctly, both polarities present, and a broken gate must be caught by it.
    The last of those is the test that keeps the rest honest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extract as X  # noqa: E402
import fetchd as F  # noqa: E402
import gates as G  # noqa: E402
import store as S  # noqa: E402
import traverse as T  # noqa: E402

KEY = b"gates-test-key"

PAGE = (
    b"<html><body><p>ACME S.A.S. appointed Maria Restrepo as CTO in March.</p>"
    b"</body></html>"
)
ROBOTS = b"User-agent: *\nAllow: /\nSitemap: https://example.com/sm.xml\n"
SITEMAP = (
    b'<?xml version="1.0"?><urlset '
    b'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    b"<url><loc>https://example.com/about</loc></url></urlset>"
)

PAGES = {
    "https://example.com/robots.txt": ROBOTS,
    "https://example.com/sm.xml": SITEMAP,
    "https://example.com/about": PAGE,
}


class AllowAll(F.Politeness):
    def __init__(self):
        super().__init__(interval=0.0)

    def allows(self, url):
        return True


def at(needle: bytes, page: bytes = PAGE) -> tuple:
    i = page.find(needle)
    assert i >= 0, f"{needle!r} not in the fixture"
    return i, i + len(needle)


@pytest.fixture
def run(tmp_path):
    """A complete, honest run: traversed, extracted, stored, verdicts set."""
    d = F.FetchDaemon(
        root=tmp_path / "runs", run_id="r1", politeness=AllowAll(),
        transport=lambda u: (200, PAGES[u], u) if u in PAGES else (404, b"x", u),
        key=KEY,
    )
    d.seal_plan({"seeds": ["https://example.com/"], "max_depth": 1})
    trav = T.traverse(d, "https://example.com/", budget=10)
    conn = S.connect(tmp_path / "map.db")

    res = d.fetch("https://example.com/about")
    claim = X.Claim(
        subject=X.Mention("org", *at(b"ACME S.A.S.")),
        predicate="employs",
        object=X.Mention("person", *at(b"Maria Restrepo")),
        span_start=at(b"ACME S.A.S.")[0],
        span_end=at(b"as CTO in March.")[1],
    )
    for rec in X.admit(d, res, claim, depth=1):
        S.put_record(conn, rec, admitter=d)
        S.set_verdict(conn, rec.id, "entailed")
    return d, conn, trav


def entails_everything(quote, claim):
    return True


def entails_nothing(quote, claim):
    return False


# --------------------------------------------------------------------------
# The honest run
# --------------------------------------------------------------------------


def test_an_honest_run_passes_every_deterministic_gate(run):
    d, conn, trav = run
    suite = G.run_suite(d, conn, traversal=trav, verifier=entails_everything,
                        projection=[])
    bad = [r for r in suite.results
           if r.policy == G.CLOSED and r.status != G.PASS]
    assert bad == [], "\n".join(f"{r.gate}: {r.status} {r.failures}" for r in bad)
    assert suite.verdict == G.VALID


def test_every_gate_reports_a_denominator(run):
    """A check that silently iterates over an empty set looks exactly like one
    that passed. `counted` is where the two differ -- and when it IS zero, the
    reason has to be readable.

    Passing at zero is often correct: a map with no edges has no inadmissible
    edges. So the enforceable rule is not "never zero", it is that a zero
    denominator carries a sentence saying why. Written after this test caught
    `lattice-exact` passing at n=0 with nothing said.
    """
    d, conn, trav = run
    suite = G.run_suite(d, conn, traversal=trav, verifier=entails_everything,
                        projection=[{"id": "org::acme-s-a-s"}])
    for r in suite.results:
        assert isinstance(r.counted, int)
        if r.counted == 0 and r.status == G.PASS:
            assert r.detail, f"{r.gate} passed at n=0 without saying why"


def test_a_gate_cannot_be_constructed_passing_at_zero_without_a_reason():
    """The rule above, enforced where it cannot be forgotten.

    A new gate added later gets this for free; a docstring asking the author to
    remember would hold exactly until the next gate.
    """
    with pytest.raises(ValueError, match="empty denominator"):
        G.GateResult("invented", "whole map", G.CLOSED, G.PASS, 0)
    # With a reason, it is fine -- the rule is about legibility, not about
    # forbidding an empty set.
    G.GateResult("invented", "whole map", G.CLOSED, G.PASS, 0, "nothing to check")
    # And a FAILING gate at zero is not the vacuity this guards against.
    G.GateResult("invented", "whole map", G.CLOSED, G.FAIL, 0, "", ("x",))


def test_the_suite_covers_the_twelve_gates_the_spec_names(run):
    d, conn, trav = run
    suite = G.run_suite(d, conn, traversal=trav)
    names = [r.gate for r in suite.results]
    assert names == [
        "plan-sealed-and-log-chained", "transport-custody",
        "record-admissible", "span-verbatim", "span-entails-claim",
        "edge-admissible", "triple-entailed",
        "lattice-exact", "inventory-closed", "corroboration-grade",
        "projection-fidelity", "gate-suite-proven",
    ]
    assert len(names) == 12
    assert sum(1 for r in suite.results if r.policy == G.CLOSED) == 11
    assert sum(1 for r in suite.results if r.policy == G.ANNOTATE) == 1


# --------------------------------------------------------------------------
# A gate that could not run is not a pass
# --------------------------------------------------------------------------


def test_an_unjudged_record_fails_the_entailment_gate(run):
    """The gate audits the verdict ledger the blinded verifier left behind.

    A record still at `unchecked` is one nobody looked at. A map full of those
    has not been verified, however green everything else is.
    """
    d, conn, trav = run
    S.set_verdict(conn, "org::acme-s-a-s", "unchecked")
    suite = G.run_suite(d, conn, traversal=trav, projection=[])
    entails = next(r for r in suite.results if r.gate == "span-entails-claim")
    assert entails.status == G.FAIL
    assert entails.counted == 2, "both observed nodes are the denominator"
    assert any("never judged it" in f for f in entails.failures)
    assert suite.verdict == G.INVALID


def test_a_refuted_record_does_not_fail_the_entailment_gate(run):
    """`Record everything. Expand only what verifies.` -- two rules.

    A disbelieved claim is EXPECTED to be present, carrying its refutation and
    seeding nothing. Failing the run because the verifier did its job would
    invert the rule the whole store is built on.
    """
    d, conn, trav = run
    S.set_verdict(conn, "org::acme-s-a-s", "refuted", refutation="the span says no")
    suite = G.run_suite(d, conn, traversal=trav, projection=[])
    entails = next(r for r in suite.results if r.gate == "span-entails-claim")
    assert entails.status == G.PASS
    assert entails.counted == 2
    # ...and it is still in the map, and still cannot expand.
    assert "org::acme-s-a-s" not in S.expandable_ids(conn)
    assert any(r["id"] == "org::acme-s-a-s" for r in S.select(conn))


def test_no_projection_makes_the_run_invalid(run):
    d, conn, trav = run
    suite = G.run_suite(d, conn, traversal=trav, verifier=entails_everything)
    proj = next(r for r in suite.results if r.gate == "projection-fidelity")
    assert proj.status == G.INCONCLUSIVE
    assert suite.verdict == G.INVALID


def test_a_second_judge_disagreeing_with_the_ledger_fails_the_run(run):
    """Two blinded judges reaching opposite conclusions about one span means at
    least one of them is not judging what it claims to be."""
    d, conn, trav = run
    suite = G.run_suite(d, conn, traversal=trav, verifier=entails_nothing,
                        projection=[])
    entails = next(r for r in suite.results if r.gate == "span-entails-claim")
    assert entails.status == G.FAIL
    assert entails.counted == 2, "both node records must have been judged"
    assert any("second blinded judge" in f for f in entails.failures)
    assert suite.verdict == G.INVALID


def test_an_annotating_gate_never_changes_the_verdict(run):
    """corroboration-grade did not survive attack, so it must not be able to
    fail a run however much it has to say."""
    d, conn, trav = run
    suite = G.run_suite(d, conn, traversal=trav, verifier=entails_everything,
                        projection=[])
    corr = next(r for r in suite.results if r.gate == "corroboration-grade")
    assert corr.policy == G.ANNOTATE
    assert corr.status == G.ANNOTATED
    assert corr.failures, "every claim here rests on one page; it should say so"
    assert suite.verdict == G.VALID


@pytest.mark.parametrize("status", [G.FAIL, G.INCONCLUSIVE])
def test_the_verdict_reads_policy_not_status(status):
    """It is `policy`, not loudness, that decides whether a gate can gate.

    A mutation sweep found this untested: corroboration-grade never actually
    returns FAIL, so dropping the `policy == CLOSED` guard changed nothing
    observable. The guard still has to hold, because the next annotating gate
    might report a failure and must still not sink the run.
    """
    annotating = G.GateResult("some-annotation", "whole map", G.ANNOTATE,
                              status, 3, "loud but advisory", ("x",))
    assert G.SuiteResult(results=[annotating]).verdict == G.VALID
    closed = G.GateResult("some-gate", "whole map", G.CLOSED, status, 3,
                          "", ("x",))
    assert G.SuiteResult(results=[closed]).verdict == G.INVALID


# --------------------------------------------------------------------------
# Individual gates saying no
# --------------------------------------------------------------------------


def test_a_tampered_log_fails_the_ingest_gate(run):
    d, conn, trav = run
    with d.log.open("a") as fh:
        fh.write('{"kind":"fetch","url":"u","sha256":"z","seq":99,"mac":"x"}\n')
    r = G.gate_plan_sealed_and_log_chained(d)
    assert r.status == G.FAIL


def test_a_missing_plan_fails_the_ingest_gate(run):
    d, conn, trav = run
    (d.dir / "plan.json").unlink()
    r = G.gate_plan_sealed_and_log_chained(d)
    assert r.status == G.FAIL
    assert "no sealed plan" in r.detail


def test_a_planted_snapshot_fails_transport_custody(run):
    d, conn, trav = run
    (d.snapshots / ("a" * 64)).write_bytes(b"authored, not fetched")
    r = G.gate_transport_custody(d, S.select(conn))
    assert r.status == G.FAIL
    assert any("hash to its own name" in f for f in r.failures)


def test_the_daemon_snapshots_robots_for_every_host_it_touches(tmp_path):
    """'We honoured robots.txt' must rest on bytes, not on the daemon's memory.

    This gate found a real hole: `Politeness` used to read robots.txt itself
    through `RobotFileParser.read()`, so those bytes never passed through the
    daemon and were never chained. The rules a crawl ran under were unauditable.
    Now the daemon fetches them, and custody holds for a host it has never seen
    before -- which is the case the depth loop produces every time it expands to
    a new site.
    """
    d = F.FetchDaemon(
        root=tmp_path / "runs", run_id="r1",
        transport=lambda u: (200, b"User-agent: *\nAllow: /\n", u)
        if u.endswith("/robots.txt") else (200, PAGE, u),
        key=KEY,
    )
    d.seal_plan({"seeds": ["x"], "max_depth": 0})
    d.fetch("https://never-seen.test/page")
    assert ("https://never-seen.test/robots.txt", F.sha256_of(
        b"User-agent: *\nAllow: /\n")) in d.pairs()
    assert G.gate_transport_custody(d, []).status == G.PASS


def test_a_host_whose_rules_were_never_fetched_fails_custody(tmp_path):
    """The gate still has to be able to say no.

    Pre-loading the rules is the one way a host gets fetched without its
    robots.txt being snapshotted -- `_ensure_robots` short-circuits on a host it
    already knows. That is a legitimate thing for a caller to do and exactly
    what the gate exists to notice, because the resulting run cannot show which
    rules it ran under.
    """
    polite = F.Politeness(interval=0.0)
    polite.load("https://preloaded.test", 200, b"User-agent: *\nAllow: /\n")
    d = F.FetchDaemon(
        root=tmp_path / "runs", run_id="r1", politeness=polite,
        transport=lambda u: (200, PAGE, u), key=KEY,
    )
    d.seal_plan({"seeds": ["x"], "max_depth": 0})
    d.fetch("https://preloaded.test/page")
    assert {u for (u, _dg) in d.pairs()} == {"https://preloaded.test/page"}
    r = G.gate_transport_custody(d, [])
    assert r.status == G.FAIL
    assert any("robots.txt being snapshotted" in f for f in r.failures)


def test_a_page_fetched_and_never_accounted_for_fails_inventory(run):
    """Silent loss: a request was spent and the page appears nowhere."""
    d, conn, trav = run
    PAGES["https://example.com/orphan"] = b"<html>nobody read this</html>"
    try:
        d.fetch("https://example.com/orphan")
        r = G.gate_inventory_closed(d, S.select(conn), trav)
        assert r.status == G.FAIL
        assert any("orphan" in f for f in r.failures)
        # ...and naming it as explicitly-unread closes the accounting again.
        ok = G.gate_inventory_closed(d, S.select(conn), trav,
                                     unread=["https://example.com/orphan"])
        assert ok.status == G.PASS
    finally:
        PAGES.pop("https://example.com/orphan")


def test_a_traversal_that_does_not_close_fails_inventory(run):
    d, conn, trav = run
    broken = trav.as_dict()
    broken["closes"] = False
    broken["seen"] = 99
    r = G.gate_inventory_closed(d, S.select(conn), broken)
    assert r.status == G.FAIL
    assert any("does not close" in f for f in r.failures)


def test_lattice_exact_catches_an_observed_grade_through_a_guess():
    """meetOrigin across the graph, not per record: contamination is transitive."""
    recs = [
        {"id": "a", "kind": "node", "origin": "simulated", "inferred_from": []},
        {"id": "b", "kind": "node", "origin": "simulated", "inferred_from": ["a"]},
        {"id": "c", "kind": "node", "origin": "observed", "inferred_from": ["b"]},
    ]
    r = G.gate_lattice_exact(recs)
    assert r.status == G.FAIL
    assert r.counted == 2
    assert any("meets to simulated" in f for f in r.failures)


def test_lattice_exact_accepts_a_correctly_graded_derivation():
    recs = [
        {"id": "a", "kind": "node", "origin": "observed", "inferred_from": []},
        {"id": "b", "kind": "node", "origin": "observed", "inferred_from": ["a"]},
    ]
    assert G.gate_lattice_exact(recs).status == G.PASS


def test_lattice_exact_does_not_hang_on_a_cycle():
    recs = [
        {"id": "a", "kind": "node", "origin": "observed", "inferred_from": ["b"]},
        {"id": "b", "kind": "node", "origin": "observed", "inferred_from": ["a"]},
    ]
    r = G.gate_lattice_exact(recs)
    assert r.status == G.FAIL


def test_triple_entailed_distinguishes_missing_spans_from_unparseable_ones():
    """Two different bugs, and the operator needs to be told which one.

    A mutation sweep found the `no recorded span` branch removable with the
    suite still green: without it the string falls through to the parser and
    fails anyway, so the gate still says no. It says no for the wrong reason —
    "the producer never recorded this" is a defect in `admit`, while
    "it recorded garbage" is a defect in the data. Asserting the message is what
    keeps the branch meaningful.
    """
    base = {
        "id": "edge::e", "kind": "edge", "predicate": "employs",
        "src": "org::a", "dst": "person::b",
        "evidence": {"url": "u", "sha256": "d", "span_start": 0, "span_end": 50,
                     "quote": "q"},
    }
    missing = G.gate_triple_entailed([dict(base, attrs={})])
    assert missing.status == G.FAIL
    assert any("no recorded subject span" in f for f in missing.failures)
    assert not any("unparseable" in f for f in missing.failures)

    garbage = G.gate_triple_entailed([
        dict(base, attrs={X.SUBJECT_SPAN: "not-a-span", X.OBJECT_SPAN: "0:5"})
    ])
    assert garbage.status == G.FAIL
    assert any("unparseable" in f for f in garbage.failures)


def test_transport_custody_catches_a_pair_that_was_never_fetched(run):
    """Distinct from span-verbatim's version: there the bytes disagree with the
    quote, here there are no bytes at all. A mutation sweep found this branch
    untested — the only custody test exercised the self-hash half."""
    d, conn, trav = run
    records = S.select(conn)
    records[0]["evidence"]["sha256"] = "c" * 64
    r = G.gate_transport_custody(d, records)
    assert r.status == G.FAIL
    assert any("cited but never fetched" in f for f in r.failures)


def test_projection_fidelity_refuses_an_unchecked_record(run):
    d, conn, trav = run
    S.set_verdict(conn, "org::acme-s-a-s", "inconclusive")
    r = G.gate_projection_fidelity(S.select(conn), [{"id": "org::acme-s-a-s"}])
    assert r.status == G.FAIL
    assert r.counted == 1


# --------------------------------------------------------------------------
# The gate on the gates
# --------------------------------------------------------------------------


def test_every_probe_is_answered_correctly():
    probes = G.run_decoys()
    wrong = [(p.gate, p.polarity, p.description) for p in probes if not p.ok]
    assert wrong == [], wrong
    assert G.gate_suite_proven(probes).status == G.PASS


def test_the_probe_set_has_both_polarities():
    """Decoys alone can be satisfied by breaking a gate: one that fails
    everything rejects every decoy. The must-accept half is what stops that."""
    probes = G.run_decoys()
    assert sum(1 for p in probes if p.polarity == "must-reject") >= 10
    assert sum(1 for p in probes if p.polarity == "must-accept") >= 5


def test_the_probe_set_covers_every_deterministic_gate():
    """A gate with no probe is a gate the suite does not prove anything about."""
    probed = {p.gate for p in G.run_decoys()}
    judgement = {"span-entails-claim"}          # needs a model, probed elsewhere
    structural = {"plan-sealed-and-log-chained", "inventory-closed",
                  "corroboration-grade", "gate-suite-proven"}
    deterministic = {
        "transport-custody", "record-admissible", "span-verbatim",
        "edge-admissible", "triple-entailed", "lattice-exact",
        "projection-fidelity",
    }
    assert deterministic <= probed
    assert not (probed & judgement)
    assert not (probed & structural)


def test_a_missed_probe_makes_the_run_invalid(run):
    """The polarity check on the polarity check.

    `gate-suite-proven` passing is only meaningful if it can fail, and the only
    way to see that is to hand it a probe that was not answered."""
    d, conn, trav = run
    probes = G.run_decoys() + [
        G.DecoyResult("record-admissible", "a planted defect nobody caught",
                      "must-reject", False)
    ]
    r = G.gate_suite_proven(probes)
    assert r.status == G.FAIL
    assert "nobody caught" in r.failures[0]
    suite = G.SuiteResult(results=[r], decoys=probes)
    assert suite.verdict == G.INVALID


def test_a_broken_gate_is_caught_by_its_own_probes(monkeypatch):
    """The device, exercised as a device.

    A gate whose predicate is inverted -- passing everything -- must be caught.
    Without this test, `gate-suite-proven` is itself a claim no test enforces.
    """
    monkeypatch.setattr(
        G, "gate_record_admissible",
        lambda records: G.GateResult("record-admissible", "per node", G.CLOSED,
                                     G.PASS, len(records)),
    )
    probes = G.run_decoys()
    missed = [p for p in probes if not p.ok]
    assert missed, "an always-passing gate must fail its must-reject probes"
    assert all(p.gate == "record-admissible" for p in missed)
    assert all(p.polarity == "must-reject" for p in missed)
    assert G.gate_suite_proven(probes).status == G.FAIL


def test_a_gate_that_fails_everything_is_also_caught(monkeypatch):
    """The other direction, which decoys alone cannot see."""
    monkeypatch.setattr(
        G, "gate_edge_admissible",
        lambda records: G.GateResult("edge-admissible", "per edge", G.CLOSED,
                                     G.FAIL, len(records), "", ("no",)),
    )
    probes = G.run_decoys()
    missed = [p for p in probes if not p.ok]
    assert missed, "a gate that fails everything must fail its must-accept probe"
    assert all(p.polarity == "must-accept" for p in missed)
    assert G.gate_suite_proven(probes).status == G.FAIL


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------


def test_the_cli_exits_2_on_an_invalid_run(run, capsys, monkeypatch):
    """A rule that only the library enforces has not been shipped."""
    d, conn, trav = run
    monkeypatch.setenv("SOURCER_CHAIN_KEY", KEY.decode())
    code = G.main([
        "--run", str(d.dir), "--db", str(Path(d.root).parent / "map.db"), "--json",
    ])
    out = json.loads(capsys.readouterr().out)
    # No projection was supplied, so `projection-fidelity` is inconclusive and a
    # fail-closed gate that could not run makes the whole run INVALID. Asserted
    # by name rather than by count: an earlier version of this comment said
    # "two closed gates", which stopped being true the moment
    # `span-entails-claim` began reading the verdict ledger instead of demanding
    # a verifier -- a false description a passing test happily carried.
    inconclusive = [g["gate"] for g in out["gates"] if g["status"] == "inconclusive"]
    assert inconclusive == ["projection-fidelity"], inconclusive
    assert out["verdict"] == "INVALID"
    assert code == 2, "2, not 1 -- a crash also exits 1"


def test_the_cli_reports_every_gate_with_its_denominator(run, capsys, monkeypatch):
    d, conn, trav = run
    monkeypatch.setenv("SOURCER_CHAIN_KEY", KEY.decode())
    G.main(["--run", str(d.dir), "--db", str(Path(d.root).parent / "map.db")])
    text = capsys.readouterr().out
    for gate in ("transport-custody", "record-admissible", "span-verbatim",
                 "gate-suite-proven"):
        assert gate in text
    assert "n=" in text
    assert "verdict: INVALID" in text


def test_an_unjudged_edge_fails_the_relation_gate(run):
    """The arithmetic cannot establish that a relation is STATED.

    Containment and a 600-byte width bound rule out co-mention that is far
    apart. Two names within 600 bytes of each other — an ordinary team page —
    satisfy the arithmetic completely while stating no relation at all. So the
    judgement must have happened, and this gate audits that it did.

    Found by probing, not reading: `span-entails-claim` filters to nodes, so
    before this an unjudged EDGE passed every per-edge gate and the whole run
    reported VALID. Only `projection-fidelity` would have noticed, and only if
    someone happened to project that particular edge.
    """
    d, conn, trav = run
    edge_id = next(r["id"] for r in S.select(conn) if r["kind"] == "edge")
    S.set_verdict(conn, edge_id, "unchecked")
    records = S.select(conn)
    # Every OTHER per-edge check is satisfied -- this is not a case the
    # arithmetic could have caught.
    assert G.gate_edge_admissible(records).status == G.PASS
    assert G.gate_span_entails_claim(d, records).status == G.PASS
    r = G.gate_triple_entailed(records)
    assert r.status == G.FAIL
    assert any("nobody judged this one" in f for f in r.failures)
    suite = G.run_suite(d, conn, traversal=trav, projection=[])
    assert suite.verdict == G.INVALID


def test_a_refuted_edge_does_not_fail_the_relation_gate(run):
    """Symmetric with nodes: a disbelieved relation is kept, carries its
    refutation, and expands nothing. Failing on it would invert the rule."""
    d, conn, trav = run
    edge_id = next(r["id"] for r in S.select(conn) if r["kind"] == "edge")
    S.set_verdict(conn, edge_id, "refuted", refutation="the span does not say it")
    records = S.select(conn)
    assert G.gate_triple_entailed(records).status == G.PASS
    assert edge_id not in S.expandable_ids(conn)


def test_an_always_failing_gate_is_caught_by_its_OWN_probes(monkeypatch):
    """Polarity has to hold per gate, not in aggregate.

    With must-accept counted globally, an always-FAIL `transport-custody`
    satisfied every one of its own must-reject probes while OTHER gates supplied
    the suite's accepting half — so a gate that refused everything was
    indistinguishable from a strict one. Probed on a gate that previously had no
    must-accept probe at all, which is exactly the case that was invisible.
    """
    monkeypatch.setattr(
        G, "gate_transport_custody",
        lambda daemon, records: G.GateResult("transport-custody", "ingest",
                                             G.CLOSED, G.FAIL, 1, "", ("no",)),
    )
    probes = G.run_decoys()
    missed = [p for p in probes if not p.ok]
    assert missed, "an always-failing gate must fail its own must-accept probe"
    assert all(p.gate == "transport-custody" for p in missed)
    assert G.gate_suite_proven(probes).status == G.FAIL


def test_every_probed_gate_has_both_polarities():
    """The coverage rule itself, and that it can report a gap."""
    probes = G.run_decoys()
    assert G.probe_coverage(probes) == []
    thinned = [p for p in probes
               if not (p.gate == "lattice-exact" and p.polarity == "must-accept")]
    gaps = G.probe_coverage(thinned)
    assert gaps == ["lattice-exact: no must-accept probe"], gaps
    assert G.gate_suite_proven(thinned).status == G.FAIL


def test_an_inverted_endpoint_span_fails_containment():
    """`20:10` satisfies `lo <= a and b <= hi` for any enclosing range, so it
    sailed through the check that is meant to be the independent recheck."""
    base = {
        "id": "edge::e", "kind": "edge", "predicate": "employs", "verdict": "entailed",
        "src": "org::a", "dst": "person::b",
        "evidence": {"url": "u", "sha256": "d", "span_start": 0, "span_end": 50,
                     "quote": "q"},
    }
    r = G.gate_triple_entailed([
        dict(base, attrs={X.SUBJECT_SPAN: "20:10", X.OBJECT_SPAN: "0:5"})
    ])
    assert r.status == G.FAIL
    assert any("empty or inverted" in f for f in r.failures)
    ok = G.gate_triple_entailed([
        dict(base, attrs={X.SUBJECT_SPAN: "10:20", X.OBJECT_SPAN: "0:5"})
    ])
    assert ok.status == G.PASS


def test_a_page_read_that_yielded_nothing_is_accounted_for(run, tmp_path):
    """The fourth fate, found by crawling a page with no relations in the
    vocabulary.

    `inventory-closed` knew three: used, dropped-with-reason, explicitly unread.
    A page a worker READ that honestly produced no claims is none of them, so
    every such page read as silent loss — which is the one thing this gate
    exists to tell it apart from.
    """
    d, conn, trav = run
    PAGES["https://example.com/quiet"] = b"<html>nothing relatable here</html>"
    try:
        d.fetch("https://example.com/quiet")
        before = G.gate_inventory_closed(d, S.select(conn), trav)
        assert before.status == G.FAIL
        assert any("quiet" in f for f in before.failures)

        (d.dir / "read.jsonl").write_text(
            json.dumps({"url": "https://example.com/quiet", "digest": "x",
                        "claims_seen": 0, "admitted": 0}) + "\n",
            encoding="utf-8",
        )
        after = G.gate_inventory_closed(d, S.select(conn), trav)
        assert after.status == G.PASS
    finally:
        PAGES.pop("https://example.com/quiet")


def test_the_read_ledger_survives_a_corrupt_line(run):
    """One bad line must not take out the ledger — a crash here would turn a
    cosmetic defect into a failed gate."""
    d, conn, trav = run
    (d.dir / "read.jsonl").write_text(
        "not json\n"
        + json.dumps({"url": "https://example.com/ok"}) + "\n"
        + json.dumps({"no_url": True}) + "\n",
        encoding="utf-8",
    )
    assert G.read_ledger(d.dir) == {"https://example.com/ok"}


def test_an_absent_read_ledger_is_an_empty_set_not_an_error(run):
    d, conn, trav = run
    assert not (d.dir / "read.jsonl").exists()
    assert G.read_ledger(d.dir) == set()
