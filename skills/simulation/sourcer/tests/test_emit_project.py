"""Tests for the two handoffs: the Parallax tables and the Layer-3 pages.

Both layers answer the same question in different directions — *what may leave
this map, and carrying what provenance* — so they share a file and a fixture.

The property under test in both is the one the whole architecture exists for:
**nothing leaves that the map does not hold and verification did not entail.**
An `unchecked` record is not a weaker finding, it is a finding nobody judged,
and the difference between those two is the entire value of the crawl.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import emit as E  # noqa: E402
import extract as X  # noqa: E402
import project as PJ  # noqa: E402
import store as S  # noqa: E402

EV = {
    "url": "https://example.com/about",
    "sha256": "a" * 64,
    "snapshot": "snapshots/" + "a" * 64,
    "span_start": 12, "span_end": 23, "quote": "ACME S.A.S.",
}


def node(key, name, verdict="entailed", origin="observed", **over):
    base = {
        "id": key, "kind": "node", "canonical_key": key, "depth": 0, "layer": "L2",
        "origin": origin, "verdict": verdict, "attrs": {"name": name},
        "evidence": dict(EV) if origin == "observed" else None,
        "inferred_from": [] if origin == "observed" else ["seed"],
    }
    base.update(over)
    return base


def edge(src, dst, predicate="employs", verdict="entailed", **over):
    eid = X.edge_id(src, predicate, dst)
    base = {
        "id": eid, "kind": "edge", "canonical_key": eid, "depth": 0, "layer": "L2",
        "origin": "observed", "verdict": verdict, "predicate": predicate,
        "src": src, "dst": dst, "evidence": dict(EV), "inferred_from": [],
        "attrs": {X.SUBJECT_SPAN: "12:23", X.OBJECT_SPAN: "30:44"},
    }
    base.update(over)
    return base


@pytest.fixture
def mapped():
    """A small verified map: two orgs, a person, and two relations."""
    return [
        node("org::acme-s-a-s", "ACME S.A.S."),
        node("person::maria-restrepo", "Maria Restrepo"),
        node("org::globex", "Globex"),
        edge("org::acme-s-a-s", "person::maria-restrepo", "employs"),
        edge("org::acme-s-a-s", "org::globex", "partner_of"),
    ]


# --------------------------------------------------------------------------
# What may leave at all
# --------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["unchecked", "refuted", "inconclusive"])
def test_only_entailed_records_ship(mapped, verdict):
    """An unchecked record is not a weaker finding, it is one nobody judged."""
    mapped[0]["verdict"] = verdict
    if verdict == "refuted":
        mapped[0]["refutation"] = "the span says no"
    shipped = {r["id"] for r in E.shippable(mapped)}
    assert "org::acme-s-a-s" not in shipped
    assert "person::maria-restrepo" in shipped, "the rest of the map still ships"


def test_a_simulated_but_entailed_record_ships(mapped):
    """Simulated rows are real output, graded honestly — the whole point of
    carrying the distinction into the table rather than filtering it out."""
    mapped.append(node("org::guess", "Guessed Co", origin="simulated"))
    assert "org::guess" in {r["id"] for r in E.shippable(mapped)}


# --------------------------------------------------------------------------
# The Parallax handoff
# --------------------------------------------------------------------------


def test_the_grammar_comes_from_data_provider_not_from_here():
    """Two spellings of one contract is the drift this codebase keeps finding.

    Asserted structurally: this module must not contain the grammar's own
    punctuation-assembly, because a local copy is the second spelling.
    """
    src = Path(E.__file__).read_text()
    assert 'f"{table}#{len(records)}' not in src, "the grammar was re-spelled here"
    assert "emit_table_arg" in src, "it must go through data-provider's function"


def test_both_tables_are_emitted_with_real_row_counts(mapped):
    out = E.emit(mapped, prefix="t")
    assert out["tables"]["nodes"]["rows"] == 3
    assert out["tables"]["edges"]["rows"] == 2
    assert out["tables"]["nodes"]["arg"].startswith("t_nodes#3:")
    assert out["tables"]["edges"]["arg"].startswith("t_edges#2:")
    assert out["tables"]["nodes"]["argv"][:4] == [
        "parallax", "propose", "--kind", "business-data"
    ]


def test_the_observed_simulated_distinction_survives_the_handoff(mapped):
    """The entire reason the crawl was built this way, and trivially lost in a
    table. If this is not in the emitted string, the handoff is lossy."""
    mapped.append(node("org::guess", "Guessed Co", origin="simulated"))
    arg = E.emit(mapped)["tables"]["nodes"]["arg"]
    assert "simulated" in arg, arg


def test_an_edge_whose_endpoint_did_not_ship_is_dropped_and_reported(mapped):
    """A table asserting a relation between two things it does not contain says
    more than the map does — exactly what projection-fidelity refuses."""
    mapped[2]["verdict"] = "unchecked"          # org::globex stops shipping
    out = E.emit(mapped)
    assert out["tables"]["edges"]["rows"] == 1
    dropped = out["dropped_edges"]
    assert len(dropped) == 1
    assert dropped[0]["missing"] == ["org::globex"]


def test_an_empty_map_is_a_refusal_not_an_empty_table():
    """A run that found nothing is complete, not a table."""
    with pytest.raises(E.EmitError, match="nothing to emit"):
        E.emit([node("org::x", "X", verdict="unchecked")])


def test_retrieval_times_come_from_the_chain_and_say_so(mapped, tmp_path):
    """sourcer's Evidence carries no timestamp because the CHAIN carries it.
    Inventing one here would look identical and mean nothing."""
    out = E.emit(mapped, daemon=None)
    assert out["retrieval_times_resolved"] is False

    class FakeDaemon:
        def verified_rows(self):
            return [{"kind": "fetch", "url": EV["url"], "sha256": EV["sha256"],
                     "retrieved_at": "1750000000.0"}]

    times = E.retrieval_times(FakeDaemon())
    assert times[(EV["url"], EV["sha256"])] == "1750000000.0"
    assert E.emit(mapped, daemon=FakeDaemon())["retrieval_times_resolved"] is True


def test_an_unreadable_daemon_yields_no_times_rather_than_now(mapped):
    class Broken:
        def verified_rows(self):
            raise RuntimeError("chain is broken")

    assert E.retrieval_times(Broken()) == {}


# --------------------------------------------------------------------------
# The knowledge-graph projection
# --------------------------------------------------------------------------


def test_only_observed_entailed_nodes_project(mapped):
    """A simulated record belongs in the Parallax table, not in a permanent
    Layer-3 page — a page is what a later reader cites, and an inference cited
    as a page loses its grade on the way."""
    mapped.append(node("org::guess", "Guessed Co", origin="simulated"))
    keys = {r["canonical_key"] for r in PJ.projectable(mapped)}
    assert "org::guess" not in keys
    assert keys == {"org::acme-s-a-s", "person::maria-restrepo", "org::globex"}


def test_core_claim_never_exceeds_the_linters_hard_cap(mapped):
    """140 characters is an ERROR in `bookkeeping lint`, so a page over it does
    not land at all."""
    long_edges = [edge("org::acme-s-a-s", f"org::{'x' * 60}-{i}", "partner_of")
                  for i in range(5)]
    claim = PJ.core_claim_for(mapped[0], long_edges)
    assert len(claim) <= PJ.MAX_CORE_CLAIM
    assert claim.endswith("…")
    assert not claim[:-1].endswith(" "), "truncate at a word boundary, not mid-token"


def test_every_projection_tag_is_in_the_controlled_vocabulary():
    """A tag outside `_tags.md` is a lint warning, and inventing one per crawled
    company would make the vocabulary meaningless within a week."""
    vocab = Path.home() / "broomva" / "research" / "entities" / "_tags.md"
    if not vocab.is_file():
        pytest.skip("the tag vocabulary is not on this machine")
    # CANONICAL entries only -- a `- \`tag\` — description` line. Matching the
    # tag anywhere in the file passes on words that merely appear inside another
    # tag's description, which is how `provenance` was chosen at first: it reads
    # as a tag in the `knowledge-graph` line and is not one.
    canonical = set(re.findall(r"^- `([a-z0-9-]+)`", vocab.read_text(), re.M))
    assert len(canonical) > 50, "the vocabulary did not parse; this test measures nothing"
    for tag in PJ.PROJECTION_TAGS:
        assert tag in canonical, f"{tag} is not a canonical tag"
    forbidden = {"org", "person", "concept", "pattern", "tool", "project"}
    assert not (set(PJ.PROJECTION_TAGS) & forbidden), "type-redundant tags are forbidden"


def test_a_page_carries_the_bytes_its_claim_was_read_from(mapped):
    page = PJ.page_for(mapped[0], mapped, run_id="r1", today="2026-08-25")
    assert EV["url"] in page.body
    assert EV["sha256"][:12] in page.body
    assert "ACME S.A.S." in page.body
    assert f"[{EV['span_start']}, {EV['span_end']})" in page.body
    assert page.path == "org/acme-s-a-s.md"


def test_a_page_says_it_is_generated_and_must_not_be_hand_edited(mapped):
    """A projection is regenerable, so a hand edit is a claim with no evidence
    behind it — the state this architecture exists to make impossible."""
    body = PJ.page_for(mapped[0], mapped, run_id="r1").body
    assert "generated: sourcer" in body
    assert "Do not edit by hand" in body


def test_a_page_states_what_it_does_not_claim(mapped):
    """A green run is easy to over-read, and the precise wording is the value."""
    body = PJ.page_for(mapped[0], mapped, run_id="r1").body
    assert "not** a claim that what the page says is true" in body


def test_related_links_only_to_pages_that_were_actually_written(mapped):
    """A wikilink to a page that was never written is a dangling reference, and
    pointing at a record verification did not entail asserts exactly what
    projection-fidelity forbids."""
    mapped[2]["verdict"] = "unchecked"       # org::globex no longer projects
    body = PJ.page_for(mapped[0], mapped, run_id="r1").body
    assert "[[maria-restrepo]]" in body
    assert "[[globex]]" not in body


def test_emitted_ids_are_derived_from_what_will_be_written(mapped):
    """The gate audits the artifact, not a list somebody kept in step with it."""
    ids = {i["id"] for i in PJ.emitted_ids(mapped)}
    assert ids == {p.key for p in PJ.build(mapped, run_id="r1")}


def test_the_projection_passes_its_own_fidelity_gate(mapped):
    """The seam: what `project` says it will write must satisfy the gate that
    decides whether it may."""
    import gates as G

    r = G.gate_projection_fidelity(mapped, PJ.emitted_ids(mapped))
    assert r.status == G.PASS
    assert r.counted == 3


def test_projecting_an_unentailed_record_fails_the_gate(mapped):
    """The other direction, so the test above is not vacuous."""
    import gates as G

    r = G.gate_projection_fidelity(mapped, [{"id": "org::never-verified"}])
    assert r.status == G.FAIL


def test_write_is_a_dry_run_by_default(mapped, tmp_path):
    """A projection writes into a permanent, shared, hand-curated graph."""
    pages = PJ.build(mapped, run_id="r1")
    out = PJ.write(pages, tmp_path)
    assert out["dry_run"] is True
    assert list(tmp_path.iterdir()) == [], "a dry run must write nothing"

    out = PJ.write(pages, tmp_path, dry_run=False)
    assert out["dry_run"] is False
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.md"))
    assert written == ["org/acme-s-a-s.md", "org/globex.md", "person/maria-restrepo.md"]


def test_a_projected_page_parses_as_yaml_frontmatter(mapped, tmp_path):
    """The linter parses it; if it is not valid YAML the page never lands."""
    yaml = pytest.importorskip("yaml")
    body = PJ.page_for(mapped[0], mapped, run_id="r1").body
    assert body.startswith("---\n")
    front = body.split("---\n", 2)[1]
    meta = yaml.safe_load(front)
    assert meta["type"] == "org"
    assert len(meta["core_claim"]) <= PJ.MAX_CORE_CLAIM
    assert set(meta["tags"]) == set(PJ.PROJECTION_TAGS)
    assert meta["generated"] == "sourcer"


def test_a_projected_page_passes_the_real_bookkeeping_linter(mapped, tmp_path):
    """The seam that actually decides whether a page lands.

    Every other check here is this module's own opinion about the schema.
    `bookkeeping lint` is the thing that says no at commit time, and a schema
    check written by the code that produces the schema is exactly the vacuity
    this codebase keeps finding. So run the real linter on a real page.
    """
    import subprocess

    linter = Path.home() / ".claude" / "skills" / "bookkeeping" / "scripts" / "bookkeeping.py"
    if not linter.is_file():
        pytest.skip("bookkeeping is not installed on this machine")

    PJ.write(PJ.build(mapped, run_id="r1"), tmp_path, dry_run=False)
    page = tmp_path / "org" / "acme-s-a-s.md"
    assert page.is_file()

    r = subprocess.run(
        ["/usr/bin/python3", str(linter), "lint", "--file", str(page)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "No errors found" in r.stdout, r.stdout


def test_the_linter_would_reject_an_over_length_claim(tmp_path):
    """The other polarity, so the test above is not just describing a happy path.

    If the linter accepted anything, passing it would mean nothing.
    """
    import subprocess

    linter = Path.home() / ".claude" / "skills" / "bookkeeping" / "scripts" / "bookkeeping.py"
    if not linter.is_file():
        pytest.skip("bookkeeping is not installed on this machine")

    bad = tmp_path / "org" / "too-long.md"
    bad.parent.mkdir(parents=True)
    bad.write_text(
        "---\n"
        'id: "org/too-long"\n'
        "type: org\n"
        "status: candidate\n"
        f'core_claim: "{"x" * (PJ.MAX_CORE_CLAIM + 40)}"\n'
        "tags:\n  - knowledge-graph\n"
        "sources:\n  - sourcer-run-r1\n"
        "related: []\n"
        'created: "2026-08-25"\n'
        'updated: "2026-08-25"\n'
        "---\n\n# Too long\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        ["/usr/bin/python3", str(linter), "lint", "--file", str(bad)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0 or "No errors found" not in r.stdout, (
        "the linter accepted an over-length core_claim, so passing it proves nothing"
    )
