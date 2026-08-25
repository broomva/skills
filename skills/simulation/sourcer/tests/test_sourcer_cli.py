"""Tests for the command line the workflow drives.

A rule that only the library enforces has not been shipped. Every refusal that
matters is asserted here at the exit code and the stderr an operator actually
sees, because a check that raises inside a function and prints a traceback
outside it is not a gate.

The end-to-end test at the bottom is the one that matters: plan, take, land,
expand, gates -- the whole cycle, through argv, with a real chained log.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import gates as G  # noqa: E402
import sourcer as C  # noqa: E402
import store as S  # noqa: E402

SEED = b"ACME S.A.S. keeps its public profile at https://acme.test/team ."
TEAM = b"ACME S.A.S. employs Maria Restrepo as CTO."
SITEMAP = (
    b'<?xml version="1.0"?><urlset '
    b'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    b"<url><loc>https://example.com/about</loc></url></urlset>"
)
PAGES = {
    "https://example.com/robots.txt": b"User-agent: *\nAllow: /\nSitemap: https://example.com/sm.xml\n",
    "https://example.com/sm.xml": SITEMAP,
    "https://example.com/about": SEED,
    "https://acme.test/robots.txt": b"User-agent: *\nAllow: /\n",
    "https://acme.test/team": TEAM,
}


@pytest.fixture(autouse=True)
def keyed(monkeypatch):
    """Every command constructs a daemon, and an unkeyed daemon refuses to."""
    monkeypatch.setenv("SOURCER_CHAIN_KEY", "cli-test-key")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No network, and no politeness delay, without weakening any invariant.

    The transport is replaced; the daemon still content-addresses what it is
    handed, still refuses non-2xx as evidence, and still chains the row.
    """
    import fetchd as F

    monkeypatch.setattr(
        F.FetchDaemon, "_http",
        staticmethod(lambda url: (200, PAGES[url], url) if url in PAGES
                     else (404, b"not found", url)),
    )
    monkeypatch.setattr(F.Politeness, "allows", lambda self, url: True)
    monkeypatch.setattr(F.Politeness, "wait", lambda self, url, **kw: 0.0)


def paths(tmp_path):
    return ["--run", str(tmp_path / "runs" / "r1"), "--db", str(tmp_path / "map.db")]


def out(capsys):
    return json.loads(capsys.readouterr().out)


def at(needle: bytes, page: bytes) -> tuple:
    i = page.find(needle)
    assert i >= 0
    return i, i + len(needle)


def seed_claims() -> list:
    s = at(b"ACME S.A.S.", SEED)
    o = at(b"https://acme.test/team", SEED)
    return [{
        "subject": {"kind": "org", "span_start": s[0], "span_end": s[1]},
        "predicate": "org_profile",
        "object": {"kind": "profile", "span_start": o[0], "span_end": o[1]},
        "span_start": s[0], "span_end": o[1],
    }]


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------


def test_plan_seals_and_queues_the_page_set(tmp_path, capsys):
    code = C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
                   "--budget", "10"])
    assert code == 0
    d = out(capsys)
    assert d["plan"]["fetch_budget"] == 10
    assert d["queued"] >= 1
    assert d["traversals"][0]["closes"] is True


def test_planning_twice_is_refused(tmp_path, capsys):
    """A plan rewritten afterwards makes what was found look like what was
    planned."""
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about"])
    capsys.readouterr()
    assert C.main(["plan", *paths(tmp_path), "--seed", "https://evil.test/"]) == 2
    assert "already exists" in capsys.readouterr().err


@pytest.mark.parametrize("bad", [
    ["--max-depth", "-1"], ["--budget", "0"],
])
def test_an_incoherent_plan_is_refused_at_the_command_line(tmp_path, bad):
    with pytest.raises(C.L.LoopError):
        C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/", *bad])


# --------------------------------------------------------------------------
# take
# --------------------------------------------------------------------------


def test_take_without_a_plan_is_refused(tmp_path, capsys):
    assert C.main(["take", *paths(tmp_path)]) == 2
    assert "no sealed plan" in capsys.readouterr().err


def test_take_hands_back_a_readable_path_and_the_vocabulary(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about"])
    capsys.readouterr()
    C.main(["take", *paths(tmp_path)])
    d = out(capsys)
    item = d["item"]
    assert Path(item["path"]).read_bytes() == PAGES[item["url"]]
    assert item["n_bytes"] == len(PAGES[item["url"]])
    # The agent is told the closed vocabulary rather than expected to know it.
    assert "org_profile" in d["vocabulary"]


def test_take_reports_an_empty_frontier_rather_than_failing(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    C.main(["take", *paths(tmp_path)])
    capsys.readouterr()
    assert C.main(["take", *paths(tmp_path)]) == 0
    d = out(capsys)
    assert d["item"] is None
    assert "nothing claimable" in d["reason"]


def test_take_stops_at_the_fetch_budget(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--budget", "3"])
    capsys.readouterr()
    # plan already spent robots + sitemap; one more take exhausts the budget.
    C.main(["take", *paths(tmp_path)])
    capsys.readouterr()
    C.main(["take", *paths(tmp_path)])
    d = out(capsys)
    assert d["item"] is None
    assert "budget" in d["reason"]


def test_a_404_finishes_the_item_instead_of_retrying_it_forever(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/gone",
            "--no-traverse"])
    capsys.readouterr()
    C.main(["take", *paths(tmp_path)])
    d = out(capsys)
    assert d["item"] is None and "not a page" in d["reason"]
    conn = S.connect(Path(str(tmp_path / "map.db")))
    assert S.frontier_stats(conn)["remaining"] == 0, "a dead page is not outstanding work"


# --------------------------------------------------------------------------
# land
# --------------------------------------------------------------------------


def _take(tmp_path, capsys):
    C.main(["take", *paths(tmp_path)])
    return out(capsys)["item"]


def test_land_admits_claims_and_expands_only_what_verified(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    item = _take(tmp_path, capsys)

    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps(seed_claims()))
    C.main(["land", *paths(tmp_path), "--url", item["url"], "--digest", item["digest"], "--token", item["claim_token"],
            "--claims", str(claims)])
    d = out(capsys)
    assert d["stats"]["admitted"] == 3
    # No verdicts file at all, so every record stays `unchecked` -- which is not
    # a synonym for inconclusive and is emphatically not permission to expand.
    assert d["stats"]["expanded"] == 0
    assert d["stats"]["entailed"] == 0
    assert d["stats"]["refuted"] == 0
    conn = S.connect(tmp_path / "map.db")
    assert S.expandable_ids(conn) == []


def test_verdicts_are_what_make_a_page_expand(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    item = _take(tmp_path, capsys)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps(seed_claims()))
    # The verifier says no. Only the EDGE is refuted -- the entities may be
    # named correctly on a page that does not state the relation between them.
    verdicts = tmp_path / "v.json"
    verdicts.write_text(json.dumps({"0": False}))
    C.main(["land", *paths(tmp_path), "--url", item["url"], "--digest", item["digest"], "--token", item["claim_token"],
            "--claims", str(claims), "--verdicts", str(verdicts)])
    d = out(capsys)
    assert d["stats"]["refuted"] == 1
    assert d["stats"]["entailed"] == 0
    assert d["stats"]["expanded"] == 0, "an unverified edge is not a way to travel"
    conn = S.connect(tmp_path / "map.db")
    verdicts_by_kind = {r["kind"]: r["verdict"] for r in S.select(conn)}
    assert verdicts_by_kind["edge"] == "refuted"
    assert verdicts_by_kind["node"] == "unchecked", (
        "a refuted relation does not make the entities wrong -- but unchecked "
        "still keeps them out of the next hop"
    )


def test_a_fully_verified_page_expands_to_the_next_hop(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    item = _take(tmp_path, capsys)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps(seed_claims()))

    verdicts = tmp_path / "v.json"
    verdicts.write_text(json.dumps({"0": True}))
    C.main(["land", *paths(tmp_path), "--url", item["url"], "--digest", item["digest"], "--token", item["claim_token"],
            "--claims", str(claims), "--verdicts", str(verdicts)])
    d = out(capsys)
    assert d["stats"]["entailed"] == 3
    assert d["stats"]["expanded"] == 1
    nxt = _take(tmp_path, capsys)
    assert nxt["url"] == "https://acme.test/team"


def test_landing_a_page_that_was_never_fetched_is_refused(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    item = _take(tmp_path, capsys)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([]))
    code = C.main(["land", *paths(tmp_path), "--url", "https://elsewhere.test/x",
                   "--digest", "0" * 64, "--token", item["claim_token"],
                   "--claims", str(claims)])
    assert code == 2
    # The lease is checked first now, so a url nobody holds is refused there.
    # Either refusal is correct; what matters is that it is REFUSED and typed.
    assert "no item held under that claim token" in capsys.readouterr().err


def test_a_wrong_claim_token_mutates_nothing_at_all(tmp_path, capsys):
    """Authorisation happens BEFORE any mutation, not as a side effect of the
    last step.

    The earlier version of this test submitted an EMPTY claims list, so there
    was no mutation for it to miss — and the token was in fact only checked by
    the final `finish`, after records were admitted, verdicts written and the
    frontier expanded. A caller with a wrong token got everything it asked for
    and an error message. This submits REAL claims and a REAL verdict, which is
    the only way the test can see the difference.
    """
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    item = _take(tmp_path, capsys)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps(seed_claims()))
    verdicts = tmp_path / "v.json"
    verdicts.write_text(json.dumps({"0": True}))

    code = C.main(["land", *paths(tmp_path), "--url", item["url"],
                   "--digest", item["digest"], "--token", "not-the-token",
                   "--claims", str(claims), "--verdicts", str(verdicts)])
    assert code == 2
    assert "no item held under that claim token" in capsys.readouterr().err

    conn = S.connect(tmp_path / "map.db")
    assert S.inventory(conn)["total"] == 0, "records were admitted without a lease"
    assert S.expandable_ids(conn) == []
    assert S.frontier_stats(conn)["total"] == 1, "the frontier was expanded"
    # ...and the real holder can still land it, so the refusal cost nothing.
    assert C.main(["land", *paths(tmp_path), "--url", item["url"],
                   "--digest", item["digest"], "--token", item["claim_token"],
                   "--claims", str(claims), "--verdicts", str(verdicts)]) == 0


def test_the_depth_comes_from_the_lease_and_cannot_be_supplied(tmp_path, capsys):
    """`--depth` is gone, not validated.

    As a free argument it let a worker holding a valid lease on a depth-2 item
    land it as depth 0 and push its descendants in at depth 1 — walking under
    the sealed max_depth for as long as it liked. Removing the argument removes
    the class of defect instead of checking for it.
    """
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    item = _take(tmp_path, capsys)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps(seed_claims()))
    with pytest.raises(SystemExit):
        C.main(["land", *paths(tmp_path), "--url", item["url"],
                "--digest", item["digest"], "--token", item["claim_token"],
                "--claims", str(claims), "--depth", "0"])
    capsys.readouterr()
    C.main(["land", *paths(tmp_path), "--url", item["url"],
            "--digest", item["digest"], "--token", item["claim_token"],
            "--claims", str(claims)])
    assert out(capsys)["depth"] == item["depth"], "depth must come from the lease"


@pytest.mark.parametrize("bad", ['{"0": "false"}', '{"0": 1}', '{"0": null}',
                                 '[true]', '{"zero": true}'])
def test_a_verdict_that_is_not_a_json_boolean_is_refused(tmp_path, capsys, bad):
    """Truthiness is not a verdict.

    `{"0": "false"}` is a string, and a string is truthy, so it marked all three
    of a claim's records `entailed` and let the crawl expand on the strength of
    a judge that said no.
    """
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    item = _take(tmp_path, capsys)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps(seed_claims()))
    verdicts = tmp_path / "v.json"
    verdicts.write_text(bad)
    code = C.main(["land", *paths(tmp_path), "--url", item["url"],
                   "--digest", item["digest"], "--token", item["claim_token"],
                   "--claims", str(claims), "--verdicts", str(verdicts)])
    assert code == 2
    conn = S.connect(tmp_path / "map.db")
    assert S.expandable_ids(conn) == [], "a malformed verdict must not verify anything"


def test_malformed_extractor_output_is_refused_and_releases_the_lease(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    item = _take(tmp_path, capsys)
    claims = tmp_path / "claims.json"
    claims.write_text('[{"subject": {"kind": "org", "name": "ACME"}}]')
    code = C.main(["land", *paths(tmp_path), "--url", item["url"],
                   "--digest", item["digest"],
                   "--token", item["claim_token"], "--claims", str(claims)])
    assert code == 2
    assert "extractor output refused" in capsys.readouterr().err
    conn = S.connect(tmp_path / "map.db")
    assert S.frontier_stats(conn)["in_flight"] == 0, "the lease must not be stranded"


# --------------------------------------------------------------------------
# status, and the whole cycle
# --------------------------------------------------------------------------


def test_status_reports_the_chain_and_the_inventory(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about"])
    capsys.readouterr()
    C.main(["status", *paths(tmp_path)])
    d = out(capsys)
    assert d["chain"]["ok"] is True
    assert d["chain"]["rows"] > 0
    assert d["plan"]["max_depth"] == 2
    assert d["inventory"]["total"] == 0
    assert d["expandable"] == 0


def test_status_reports_a_broken_chain_rather_than_crashing(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about"])
    capsys.readouterr()
    log = tmp_path / "runs" / "r1" / "fetchlog.jsonl"
    with log.open("a") as fh:
        fh.write('{"kind":"fetch","url":"u","sha256":"z","seq":99,"mac":"x"}\n')
    assert C.main(["status", *paths(tmp_path)]) == 0
    assert out(capsys)["chain"]["ok"] is False


def test_the_whole_cycle_produces_a_map_the_gates_accept(tmp_path, capsys):
    """plan -> take -> land -> expand -> take -> land, then the gate suite.

    The seam test. Each module's own suite proves its invariants in isolation,
    which is exactly how an architectural hole survives; this drives the four of
    them through argv and then asks the gates whether the result holds up.
    """
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--budget", "20"])
    capsys.readouterr()

    def cycle(claim_builder):
        item = _take(tmp_path, capsys)
        assert item is not None
        claims = claim_builder()
        cf = tmp_path / f"c-{item['digest'][:8]}.json"
        cf.write_text(json.dumps(claims))
        vf = tmp_path / f"v-{item['digest'][:8]}.json"
        vf.write_text(json.dumps({str(i): True for i in range(len(claims))}))
        C.main(["land", *paths(tmp_path), "--url", item["url"],
                "--digest", item["digest"],
                "--token", item["claim_token"], "--claims", str(cf),
                "--verdicts", str(vf)])
        return out(capsys)

    # The sitemap queued /about; take it, and land the profile claim.
    first = cycle(seed_claims)
    assert first["stats"]["expanded"] == 1

    def team_claims():
        s = at(b"ACME S.A.S.", TEAM)
        o = at(b"Maria Restrepo", TEAM)
        return [{
            "subject": {"kind": "org", "span_start": s[0], "span_end": s[1]},
            "predicate": "employs",
            "object": {"kind": "person", "span_start": o[0], "span_end": o[1]},
            "span_start": s[0], "span_end": at(b"as CTO.", TEAM)[1],
        }]

    second = cycle(team_claims)
    assert second["stats"]["admitted"] == 3

    # -- and now the gates, over what all of that left on disk ---------------
    import fetchd as F

    daemon = F.FetchDaemon(root=tmp_path / "runs", run_id="r1")
    conn = S.connect(tmp_path / "map.db")
    records = S.select(conn)
    for gate in (
        G.gate_plan_sealed_and_log_chained(daemon),
        G.gate_transport_custody(daemon, records),
        G.gate_record_admissible(records),
        G.gate_span_verbatim(daemon, records),
        G.gate_edge_admissible(records),
        G.gate_triple_entailed(records),
        G.gate_lattice_exact(records),
        G.gate_projection_fidelity(records, [{"id": "person::maria-restrepo"}]),
    ):
        assert gate.status == G.PASS, f"{gate.gate}: {gate.failures}"

    # The map actually contains the second hop, reached only because the first
    # verified. That is the whole product in one assertion.
    keys = {r["canonical_key"] for r in records}
    assert "person::maria-restrepo" in keys
