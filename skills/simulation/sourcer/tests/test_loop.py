"""Tests for the depth loop.

One claim carries this module, and most of these tests are about it: a node that
fails verification never expands. Everything else -- budgets, leases, breadth --
is bookkeeping around that.

The claim is tested in both directions, because only one direction is
interesting on its own. That a verified profile DOES expand shows the mechanism
works; that a refuted one does NOT shows it is a mechanism rather than a
coincidence of the fixture. A loop that expands nothing passes the second test
and fails the first, which is why neither is enough alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extract as X  # noqa: E402
import fetchd as F  # noqa: E402
import loop as L  # noqa: E402
import store as S  # noqa: E402

KEY = b"loop-test-key"

# A seed page naming a company and its profile URL, and the profile page naming
# a person. Two hops, which is the smallest crawl that can show expansion.
SEED = (
    b"ACME S.A.S. keeps its public profile at https://acme.test/team ."
)
TEAM = (
    b"ACME S.A.S. employs Maria Restrepo as CTO."
)

PAGES = {
    "https://example.com/robots.txt": b"User-agent: *\nAllow: /\n",
    "https://example.com/about": SEED,
    "https://acme.test/robots.txt": b"User-agent: *\nAllow: /\n",
    "https://acme.test/team": TEAM,
}


class AllowAll(F.Politeness):
    def __init__(self):
        super().__init__(interval=0.0)

    def allows(self, url):
        return True


def at(needle: bytes, page: bytes) -> tuple:
    i = page.find(needle)
    assert i >= 0, f"{needle!r} not in fixture"
    return i, i + len(needle)


@pytest.fixture
def rig(tmp_path):
    d = F.FetchDaemon(
        root=tmp_path / "runs", run_id="r1", politeness=AllowAll(),
        transport=lambda u: (200, PAGES[u], u) if u in PAGES else (404, b"x", u),
        key=KEY,
    )
    d.seal_plan({"seeds": ["https://example.com/about"], "max_depth": 2})
    conn = S.connect(tmp_path / "map.db")
    return d, conn


def extractor(payload, url):
    """A stand-in for the extraction agent, keyed off which page it is given."""
    if payload == SEED:
        s = at(b"ACME S.A.S.", SEED)
        o = at(b"https://acme.test/team", SEED)
        return [X.Claim(
            subject=X.Mention("org", *s), predicate="org_profile",
            object=X.Mention("profile", *o),
            span_start=s[0], span_end=o[1],
        )]
    if payload == TEAM:
        s = at(b"ACME S.A.S.", TEAM)
        o = at(b"Maria Restrepo", TEAM)
        return [X.Claim(
            subject=X.Mention("org", *s), predicate="employs",
            object=X.Mention("person", *o),
            span_start=s[0], span_end=at(b"as CTO.", TEAM)[1],
        )]
    return []


def believe_all(quote, subject):
    return True


def believe_nothing(quote, subject):
    return False


def plan(**over):
    base = dict(seeds=("https://example.com/about",), max_depth=2, fetch_budget=10)
    base.update(over)
    return L.Plan(**base)


# --------------------------------------------------------------------------
# The claim, both directions
# --------------------------------------------------------------------------


def test_a_verified_profile_expands_to_the_next_hop(rig):
    d, conn = rig
    stats = L.run(d, conn, plan(), extractor, believe_all)
    assert stats.expanded == 1, stats.as_dict()
    assert stats.fetched == 2, "the seed and the profile it pointed at"
    # And the second hop was actually read: the person only appears on /team.
    keys = {r["canonical_key"] for r in S.select(conn)}
    assert "person::maria-restrepo" in keys


def test_a_refuted_profile_never_expands(rig):
    """The load-bearing test of the whole module.

    Same pages, same extractor, same budget -- the only difference is that the
    verifier does not believe the span. The second page must never be fetched.
    """
    d, conn = rig
    stats = L.run(d, conn, plan(), extractor, believe_nothing)
    assert stats.refuted > 0, "the fixture must actually produce refutations"
    assert stats.expanded == 0
    assert stats.fetched == 1, "the profile page must never have been fetched"
    fetched = {u for (u, _d) in d.pairs()}
    assert "https://acme.test/team" not in fetched


def test_a_refuted_record_is_kept_not_deleted(rig):
    """`Record everything. Expand only what verifies.` -- two rules, not one."""
    d, conn = rig
    L.run(d, conn, plan(), extractor, believe_nothing)
    inv = S.inventory(conn)
    assert inv["total"] > 0, "refuted records are retained"
    assert inv["by_verdict"].get("refuted", 0) > 0
    assert S.expandable_ids(conn) == []
    # ...and the refutation itself is on the record, not merely implied.
    refuted = [r for r in S.select(conn) if r["verdict"] == "refuted"]
    assert all(r["refutation"] for r in refuted)


def test_verification_runs_before_expansion_not_after(rig):
    """Ordering, observed rather than asserted from the source.

    If expansion ran first, the profile URL would be on the frontier by the time
    the verdict landed, and the refutation would arrive with a subtree already
    hanging off it. Checking the frontier is how that ordering becomes visible.
    """
    d, conn = rig
    L.run(d, conn, plan(), extractor, believe_nothing)
    queued = [
        r["key"] for r in conn.execute("SELECT key FROM frontier ORDER BY key")
    ]
    assert queued == ["https://example.com/about"], queued


# --------------------------------------------------------------------------
# Expansion is narrow on purpose
# --------------------------------------------------------------------------


def test_only_profile_edges_expand(rig):
    """An `employs` edge names a person, not a place to go."""
    d, conn = rig
    L.run(d, conn, plan(), extractor, believe_all)
    # /team produced an `employs` edge whose object is a person. Nothing was
    # queued from it, so the frontier holds exactly what was fetched.
    remaining = S.frontier_stats(conn)["remaining"]
    assert remaining == 0
    assert S.frontier_stats(conn)["total"] == 2


def test_a_non_expansion_predicate_pointing_at_a_profile_does_not_expand(tmp_path):
    """EXPANSION_PREDICATES is the control point, not an accident of typing.

    Today the typed vocabulary already makes this unreachable through `admit`:
    `has_profile` and `org_profile` are the only predicates whose range is
    `profile`, so no other edge can point at one. A mutation sweep found the
    guard removable for exactly that reason. It is still the guard that decides
    what the crawl may follow, and the next predicate given a `profile` range
    must not silently become a way to move.
    """
    conn = S.connect(tmp_path / "m.db")
    records = [
        {"id": "e", "kind": "edge", "predicate": "competitor_of", "dst": "p",
         "src": "org::a", "origin": "observed", "verdict": "entailed"},
        {"id": "p", "kind": "node", "canonical_key": "profile::x",
         "origin": "observed", "verdict": "entailed",
         "attrs": {"name": "https://acme.test/t"}},
    ]
    assert L.expand(conn, records, depth=1) == 0
    records[0]["predicate"] = "org_profile"
    assert L.expand(conn, records, depth=1) == 1


def test_expansion_reads_the_verdicts_from_the_store_not_from_memory(rig):
    """The ordering, stated as the thing that actually goes wrong without it.

    The in-memory records are all `unchecked` at construction; the verdicts only
    exist in the store, written by the verify stage. Expanding from the objects
    in hand rather than re-reading would therefore expand nothing at all -- and
    the version where expansion runs FIRST is the same bug with the opposite
    sign, expanding everything before any verdict is known.
    """
    d, conn = rig
    L.run(d, conn, plan(), extractor, believe_all)
    # The profile page was reached, which is only possible if expansion saw an
    # `entailed` verdict that did not exist on the object it was built from.
    assert "https://acme.test/team" in {u for (u, _dg) in d.pairs()}


@pytest.mark.parametrize("name,expected", [
    ("https://acme.test/team", "https://acme.test/team"),
    ("http://acme.test/x", "http://acme.test/x"),
    ("acme.test/team", None),            # not absolute -- nowhere to go
    ("javascript:alert(1)", None),
    ("file:///etc/passwd", None),
    ("", None),
])
def test_profile_url_only_accepts_an_absolute_http_url(name, expected):
    rec = {"canonical_key": "profile::x", "attrs": {"name": name}}
    assert L.profile_url(rec) == expected


def test_a_non_profile_node_is_never_a_place_to_go():
    rec = {"canonical_key": "org::x", "attrs": {"name": "https://acme.test/"}}
    assert L.profile_url(rec) is None


def test_an_unverified_edge_to_a_verified_profile_does_not_expand(tmp_path):
    """Both ends must have verified. A believed destination reached by a
    disbelieved link is still a link the run declined to believe."""
    conn = S.connect(tmp_path / "m.db")
    records = [
        {"id": "e", "kind": "edge", "predicate": "org_profile", "dst": "p",
         "src": "org::a", "origin": "observed", "verdict": "unchecked"},
        {"id": "p", "kind": "node", "canonical_key": "profile::x",
         "origin": "observed", "verdict": "entailed",
         "attrs": {"name": "https://acme.test/t"}},
    ]
    assert L.expand(conn, records, depth=1) == 0
    records[0]["verdict"] = "entailed"
    assert L.expand(conn, records, depth=1) == 1


def test_a_verified_edge_to_an_unverified_profile_does_not_expand(tmp_path):
    conn = S.connect(tmp_path / "m.db")
    records = [
        {"id": "e", "kind": "edge", "predicate": "org_profile", "dst": "p",
         "src": "org::a", "origin": "observed", "verdict": "entailed"},
        {"id": "p", "kind": "node", "canonical_key": "profile::x",
         "origin": "observed", "verdict": "refuted",
         "attrs": {"name": "https://acme.test/t"}},
    ]
    assert L.expand(conn, records, depth=1) == 0


def test_a_simulated_profile_does_not_expand(tmp_path):
    """`expandable` is observed AND entailed. An inference does not spend budget."""
    conn = S.connect(tmp_path / "m.db")
    records = [
        {"id": "e", "kind": "edge", "predicate": "org_profile", "dst": "p",
         "src": "org::a", "origin": "observed", "verdict": "entailed"},
        {"id": "p", "kind": "node", "canonical_key": "profile::x",
         "origin": "simulated", "verdict": "entailed",
         "attrs": {"name": "https://acme.test/t"}},
    ]
    assert L.expand(conn, records, depth=1) == 0


# --------------------------------------------------------------------------
# Bounds
# --------------------------------------------------------------------------


def test_the_fetch_budget_stops_the_run_and_says_so(rig):
    d, conn = rig
    stats = L.run(d, conn, plan(fetch_budget=1), extractor, believe_all)
    assert stats.fetched == 1
    assert stats.budget_stops == 1
    assert any("fetch budget" in n for n in stats.notes)
    assert any("still holds" in n for n in stats.notes), "the remainder must be named"


def test_the_depth_bound_stops_expansion(rig):
    d, conn = rig
    stats = L.run(d, conn, plan(max_depth=0), extractor, believe_all)
    assert stats.fetched == 1, "depth 1 was queued but is above the bound"
    assert stats.expanded == 1, "it was still QUEUED -- the bound is on claiming"
    assert S.frontier_stats(conn)["remaining"] == 1


@pytest.mark.parametrize("bad", [
    dict(seeds=()), dict(max_depth=-1), dict(fetch_budget=0),
])
def test_an_incoherent_plan_is_refused(bad):
    with pytest.raises(L.LoopError):
        plan(**bad)


# --------------------------------------------------------------------------
# One bad item does not lose the run
# --------------------------------------------------------------------------


def test_a_404_does_not_abort_the_run(rig):
    d, conn = rig
    stats = L.run(
        d, conn,
        L.Plan(seeds=("https://example.com/gone", "https://example.com/about"),
               max_depth=2, fetch_budget=10),
        extractor, believe_all,
    )
    assert any("gone" in n for n in stats.notes)
    assert stats.admitted > 0, "the good page must still have been read"


def test_an_extractor_that_raises_is_recorded_not_fatal(rig):
    d, conn = rig

    def boom(payload, url):
        raise RuntimeError("the model returned prose")

    stats = L.run(d, conn, plan(), boom, believe_all)
    assert stats.items_done == 1
    assert any("extractor raised RuntimeError" in n for n in stats.notes)
    assert stats.admitted == 0


def test_an_inadmissible_claim_is_counted_and_dropped_not_downgraded(rig):
    """No `simulated` fallback. A bad reading is not a derivation."""
    d, conn = rig

    def wrong_way(payload, url):
        if payload != SEED:
            return []
        s = at(b"ACME S.A.S.", SEED)
        o = at(b"https://acme.test/team", SEED)
        # Relation span omits the object entirely -> refused at construction,
        # so build it the only way that reaches `admit`: a valid Claim whose
        # object span resolves to a name too short to identify anything.
        return [X.Claim(
            subject=X.Mention("org", *s), predicate="org_profile",
            object=X.Mention("profile", o[0], o[0] + 1),
            span_start=s[0], span_end=o[1],
        )]

    stats = L.run(d, conn, plan(), wrong_way, believe_all)
    assert stats.claims_seen == 1
    assert stats.rejected == 1
    assert stats.admitted == 0
    assert S.inventory(conn)["by_origin"].get("simulated", 0) == 0


def test_a_verifier_that_raises_leaves_the_record_unchecked(rig):
    """Not entailed, not refuted. A verifier that crashed did not decide."""
    d, conn = rig

    def boom(quote, subject):
        raise RuntimeError("the judge timed out")

    stats = L.run(d, conn, plan(), extractor, boom)
    assert stats.entailed == 0 and stats.refuted == 0
    assert any("verifier raised" in n for n in stats.notes)
    assert S.expandable_ids(conn) == []
    assert all(r["verdict"] == "unchecked" for r in S.select(conn))


def test_the_lease_is_released_even_when_an_item_explodes(rig, monkeypatch):
    """A crash mid-item must not leave work reported as in flight forever."""
    d, conn = rig

    def explode(*a, **k):
        raise KeyboardInterrupt("operator stopped it")

    monkeypatch.setattr(L, "process_item", explode)
    with pytest.raises(KeyboardInterrupt):
        L.run(d, conn, plan(), extractor, believe_all)
    assert S.frontier_stats(conn)["in_flight"] == 0
    assert S.frontier_stats(conn)["done"] == 1


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------


def test_stats_separate_refuted_from_nothing_found(rig, tmp_path):
    """A run that disbelieved everything and a run that found nothing are
    different outcomes, and the record count alone cannot tell them apart.

    Run at `max_depth=0` so neither run expands and both read exactly the same
    single page. That makes them identical in everything except the verdicts,
    which is the only condition under which this test is about the verdict
    fields at all -- at depth 2 the believed run goes on to fetch a second page
    and the counts diverge for a reason that has nothing to do with reporting.
    """
    d, conn = rig
    believed = L.run(d, conn, plan(max_depth=0), extractor, believe_all).as_dict()

    d2 = F.FetchDaemon(
        root=tmp_path / "runs2", run_id="r2", politeness=AllowAll(),
        transport=lambda u: (200, PAGES[u], u) if u in PAGES else (404, b"x", u),
        key=KEY,
    )
    d2.seal_plan({"seeds": ["https://example.com/about"], "max_depth": 2})
    conn2 = S.connect(tmp_path / "map2.db")
    disbelieved = L.run(d2, conn2, plan(max_depth=0), extractor,
                        believe_nothing).as_dict()

    assert believed["fetched"] == disbelieved["fetched"] == 1
    assert believed["admitted"] == disbelieved["admitted"] > 0, (
        "the two runs must be indistinguishable by record count -- otherwise "
        "this test is not about the verdict fields at all"
    )
    assert believed["entailed"] > 0 and believed["refuted"] == 0
    assert disbelieved["refuted"] > 0 and disbelieved["entailed"] == 0


def test_stats_round_trip_as_a_dict(rig):
    d, conn = rig
    s = L.run(d, conn, plan(), extractor, believe_all).as_dict()
    assert set(s) == {
        "fetched", "items_done", "claims_seen", "admitted", "rejected",
        "entailed", "refuted", "expanded", "budget_stops", "notes",
    }


# --------------------------------------------------------------------------
# The verifier must be shown the whole claim
# --------------------------------------------------------------------------

CROSSED = b"ACME employs Alice. Globex employs Bob."


def test_the_verifier_is_asked_about_the_named_endpoints_not_the_predicate():
    """A crossed relation fits inside 600 bytes and contains both mentions.

    On this page, relating ACME to Bob satisfies every arithmetic defence. The
    verifier used to be handed the bare predicate — `"employs"` — so it was
    asked only "does this text say employs", which it plainly does. The crossed
    edge was recorded `entailed` and passed every gate: a complete path from
    genuine attested bytes to a false verified relation.

    A verifier cannot refuse a claim it was never shown.
    """
    class Rec:
        kind, predicate = "edge", "employs"
        src, dst, canonical_key, attrs = "org::acme", "person::bob", "edge::x", {}

    names = {"org::acme": "ACME", "person::bob": "Bob"}
    asked = L.proposition(Rec(), names)
    assert "ACME" in asked and "Bob" in asked, asked
    assert asked != "employs"

    # A judge that reads the page can now say no, and the wording is what lets it.
    def honest(quote, claim):
        return "'ACME' employs 'Alice'" == claim

    assert honest(CROSSED.decode(), asked) is False
    assert honest(CROSSED.decode(),
                  L.proposition(Rec(), {"org::acme": "ACME",
                                        "person::bob": "Alice"})) is True


def test_a_crossed_relation_is_refused_end_to_end(tmp_path):
    """The same defect driven through the real loop, with a judge that reads."""
    pages = {"https://x.test/robots.txt": b"User-agent: *\nAllow: /\n",
             "https://x.test/p": CROSSED}
    d = F.FetchDaemon(
        root=tmp_path / "runs", run_id="r1", politeness=AllowAll(),
        transport=lambda u: (200, pages[u], u) if u in pages else (404, b"x", u),
        key=KEY,
    )
    d.seal_plan({"seeds": ["https://x.test/p"], "max_depth": 0})
    conn = S.connect(tmp_path / "m.db")

    def crossed_extractor(payload, url):
        s = at(b"ACME", CROSSED)
        o = at(b"Bob", CROSSED)
        return [X.Claim(subject=X.Mention("org", *s), predicate="employs",
                        object=X.Mention("person", *o),
                        span_start=0, span_end=len(CROSSED))]

    def reads_the_page(quote, claim):
        # Only believes a relation the text actually states.
        return "'ACME' employs 'Alice'" in claim or "names the" in claim

    stats = L.run(d, conn,
                  L.Plan(seeds=("https://x.test/p",), max_depth=0, fetch_budget=5),
                  crossed_extractor, reads_the_page)
    assert stats.refuted == 1, stats.as_dict()
    edge = [r for r in S.select(conn) if r["kind"] == "edge"][0]
    assert edge["verdict"] == "refuted"
    assert edge["id"] not in S.expandable_ids(conn)


def test_a_transport_error_does_not_silently_lose_the_item(tmp_path):
    """An exception below the daemon is not a domain refusal.

    Letting it escape meant `run`'s `finally` marked the lease DONE on the way
    out, so the item was permanently dropped from a crawl that then reported
    itself complete. One bad page must cost one page.
    """
    import urllib.error

    def flaky(url):
        if url.endswith("/robots.txt"):
            return (200, b"User-agent: *\nAllow: /\n", url)
        raise urllib.error.URLError("connection reset")

    d = F.FetchDaemon(root=tmp_path / "runs", run_id="r1",
                      politeness=AllowAll(), transport=flaky, key=KEY)
    d.seal_plan({"seeds": ["https://x.test/p"], "max_depth": 0})
    conn = S.connect(tmp_path / "m.db")
    stats = L.run(d, conn,
                  L.Plan(seeds=("https://x.test/p",), max_depth=0, fetch_budget=5),
                  extractor, believe_all)
    assert any("transport raised URLError" in n for n in stats.notes), stats.notes
    assert stats.items_done == 1
    assert S.frontier_stats(conn)["in_flight"] == 0
