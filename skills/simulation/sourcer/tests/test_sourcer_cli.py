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
    C.main(["land", *paths(tmp_path), "--url", item["url"], "--digest", item["digest"],
            "--depth", str(item["depth"]), "--token", item["claim_token"],
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
    # Both NODES verified; the edge between them deliberately gets no verdict.
    verdicts = tmp_path / "v.json"
    verdicts.write_text(json.dumps({
        "org::acme-s-a-s": True,
        "profile::https-acme-test-team": True,
    }))
    C.main(["land", *paths(tmp_path), "--url", item["url"], "--digest", item["digest"],
            "--depth", str(item["depth"]), "--token", item["claim_token"],
            "--claims", str(claims), "--verdicts", str(verdicts)])
    d = out(capsys)
    # Both node ids verified; the edge did not, so the crawl must NOT move.
    assert d["stats"]["entailed"] == 2
    assert d["stats"]["expanded"] == 0, "an unverified edge is not a way to travel"


def test_a_fully_verified_page_expands_to_the_next_hop(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    item = _take(tmp_path, capsys)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps(seed_claims()))

    # Compute the edge id the same way `admit` does, from the closed vocabulary.
    import extract as X
    eid = X.edge_id("org::acme-s-a-s", "org_profile", "profile::https-acme-test-team")
    verdicts = tmp_path / "v.json"
    verdicts.write_text(json.dumps({
        "org::acme-s-a-s": True,
        "profile::https-acme-test-team": True,
        eid: True,
    }))
    C.main(["land", *paths(tmp_path), "--url", item["url"], "--digest", item["digest"],
            "--depth", str(item["depth"]), "--token", item["claim_token"],
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
                   "--digest", "0" * 64, "--depth", "0",
                   "--token", item["claim_token"], "--claims", str(claims)])
    assert code == 2
    assert "no chained log row" in capsys.readouterr().err


def test_a_wrong_claim_token_cannot_finish_an_item(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    item = _take(tmp_path, capsys)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([]))
    code = C.main(["land", *paths(tmp_path), "--url", item["url"],
                   "--digest", item["digest"], "--depth", str(item["depth"]),
                   "--token", "not-the-token", "--claims", str(claims)])
    assert code == 2
    assert "refusing to finish" in capsys.readouterr().err


def test_malformed_extractor_output_is_refused_and_releases_the_lease(tmp_path, capsys):
    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--no-traverse"])
    capsys.readouterr()
    item = _take(tmp_path, capsys)
    claims = tmp_path / "claims.json"
    claims.write_text('[{"subject": {"kind": "org", "name": "ACME"}}]')
    code = C.main(["land", *paths(tmp_path), "--url", item["url"],
                   "--digest", item["digest"], "--depth", str(item["depth"]),
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
    import extract as X

    C.main(["plan", *paths(tmp_path), "--seed", "https://example.com/about",
            "--budget", "20"])
    capsys.readouterr()

    def cycle(claim_builder, verdict_ids):
        item = _take(tmp_path, capsys)
        assert item is not None
        cf = tmp_path / f"c-{item['digest'][:8]}.json"
        cf.write_text(json.dumps(claim_builder()))
        vf = tmp_path / f"v-{item['digest'][:8]}.json"
        vf.write_text(json.dumps({i: True for i in verdict_ids}))
        C.main(["land", *paths(tmp_path), "--url", item["url"],
                "--digest", item["digest"], "--depth", str(item["depth"]),
                "--token", item["claim_token"], "--claims", str(cf),
                "--verdicts", str(vf)])
        return out(capsys)

    # The sitemap queued /about; take it, and land the profile claim.
    first = cycle(seed_claims, [
        "org::acme-s-a-s", "profile::https-acme-test-team",
        X.edge_id("org::acme-s-a-s", "org_profile", "profile::https-acme-test-team"),
    ])
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

    second = cycle(team_claims, [
        "org::acme-s-a-s", "person::maria-restrepo",
        X.edge_id("org::acme-s-a-s", "employs", "person::maria-restrepo"),
    ])
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
