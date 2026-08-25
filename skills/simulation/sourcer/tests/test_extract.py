"""Tests for typed extraction.

What is under test is not "can a model read a page" -- it cannot be, here. It is
the admission layer: given a claim an extractor produced, does anything false
about it get in. So most of these tests are attempts to smuggle something
through, and the ones that matter are the refusals.

The three devices, each tested at the property it actually holds:

  - a name is the bytes, so `resolve` must produce the name the page contains
    and no other, and a key must be recomputable from the span alone;
  - a relation is a bounded span containing both mentions, so co-mention across
    a page must be unrepresentable rather than merely discouraged;
  - the vocabulary is closed and typed, so a wrong-way edge must be refused at
    construction rather than stored and flagged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extract as X  # noqa: E402
import fetchd as F  # noqa: E402
import store as S  # noqa: E402

KEY = b"extract-test-key"

# One page, used by nearly everything. Offsets are computed, never typed --
# a hand-counted offset that drifts turns a real test into a vacuous one.
PAGE = (
    b"<html><body>"
    b"<p>ACME S.A.S. appointed Maria Restrepo as its Chief Technology Officer "
    b"in March 2026.</p>"
    b"<p>Unrelated filler about the weather.</p>"
    b"</body></html>"
)


def at(needle: bytes, page: bytes = PAGE) -> tuple:
    i = page.find(needle)
    assert i >= 0, f"{needle!r} not in the fixture -- the test is measuring nothing"
    return i, i + len(needle)


class AllowAll(F.Politeness):
    def __init__(self):
        super().__init__(interval=0.0)

    def allows(self, url):
        return True


@pytest.fixture
def rig(tmp_path):
    """A daemon that has fetched PAGE, plus the FetchResult for it."""

    def transport(url):
        if url == "https://example.com/about":
            return (200, PAGE, url)
        return (404, b"nope", url)

    d = F.FetchDaemon(
        root=tmp_path / "runs", run_id="r1", politeness=AllowAll(),
        transport=transport, key=KEY,
    )
    d.seal_plan({"seeds": ["https://example.com/"], "max_depth": 1})
    res = d.fetch("https://example.com/about")
    return d, res


def sentence_span() -> tuple:
    return at(b"ACME S.A.S. appointed Maria Restrepo as its Chief Technology Officer")


def acme_person_claim() -> X.Claim:
    s0, s1 = at(b"ACME S.A.S.")
    o0, o1 = at(b"Maria Restrepo")
    r0, r1 = sentence_span()
    return X.Claim(
        subject=X.Mention("org", s0, s1),
        predicate="employs",
        object=X.Mention("person", o0, o1),
        span_start=r0,
        span_end=r1,
        attrs={"title": "Chief Technology Officer"},
    )


# --------------------------------------------------------------------------
# Names and keys
# --------------------------------------------------------------------------


def test_the_key_is_recomputable_from_the_span_alone(rig):
    """The central property: an extractor cannot name what the page does not say."""
    d, res = rig
    s0, s1 = at(b"ACME S.A.S.")
    ent = X.resolve(d, res, X.Mention("org", s0, s1))
    assert ent.name == "ACME S.A.S."
    assert ent.key == "org::acme-s-a-s"
    # And the key is a pure function of (kind, bytes) -- no state, no daemon.
    assert X.key_for("org", PAGE[s0:s1].decode()) == ent.key


def test_fullwidth_and_split_names_normalise_to_one_key():
    """Two pages naming the same company must not become two entities."""
    assert X.key_for("org", "ＡＣＭＥ　S.A.S.") == X.key_for("org", "ACME S.A.S.")
    assert X.key_for("org", "ACME\n  S.A.S.") == X.key_for("org", "ACME S.A.S.")
    assert X.key_for("org", "acme s.a.s.") == X.key_for("org", "ACME S.A.S.")


def test_a_name_of_pure_punctuation_is_refused():
    with pytest.raises(X.ExtractionError, match="empty key"):
        X.key_for("org", "--- / ---")


def test_an_unknown_kind_has_no_key():
    with pytest.raises(X.ExtractionError):
        X.key_for("spaceship", "ACME")


def test_a_paragraph_quoted_as_a_name_is_refused(rig):
    """A span wide enough to hold a paragraph passes every offset check there is.
    The length bound is the only thing standing between that and an entity
    called 'the whole page'."""
    d, res = rig
    with pytest.raises(X.ExtractionError, match="passage, not a name"):
        X.resolve(d, res, X.Mention("org", 0, len(PAGE)))


def test_a_one_character_name_is_refused(rig):
    d, res = rig
    i = PAGE.find(b"A")
    with pytest.raises(X.ExtractionError, match="too short"):
        X.resolve(d, res, X.Mention("org", i, i + 1))


def test_a_span_cutting_a_multibyte_character_is_refused(tmp_path):
    """Spans are BYTE offsets; `evidence_for` decodes with errors="replace". An
    off-by-one inside an accented character yields a name with U+FFFD in it,
    whose key is wrong permanently and merges with nothing."""
    page = "Compañía Nacional de Café".encode("utf-8")

    d = F.FetchDaemon(
        root=tmp_path / "runs", run_id="r1", politeness=AllowAll(),
        transport=lambda u: (200, page, u), key=KEY,
    )
    d.seal_plan({"seeds": ["x"], "max_depth": 1})
    res = d.fetch("https://example.com/es")
    n_tilde = page.find("ñ".encode())
    with pytest.raises(X.ExtractionError, match="replacement character"):
        # Ends one byte into the two-byte "ñ".
        X.resolve(d, res, X.Mention("org", 0, n_tilde + 1))
    # The aligned span is fine, which is what makes the refusal above a real
    # boundary rather than a rejection of the whole fixture.
    ok = X.resolve(d, res, X.Mention("org", 0, len(page)))
    assert ok.name == "Compañía Nacional de Café"


# --------------------------------------------------------------------------
# The closed, typed vocabulary
# --------------------------------------------------------------------------


def test_a_predicate_outside_the_vocabulary_is_refused():
    with pytest.raises(X.ExtractionError, match="outside the closed vocabulary"):
        X.Claim(
            subject=X.Mention("org", 0, 5), predicate="vibes_with",
            object=X.Mention("org", 6, 10), span_start=0, span_end=20,
        )


def test_a_wrong_way_edge_is_refused_at_construction():
    """`employs` is org -> person. A person employing an org is not a near-miss."""
    with pytest.raises(X.ExtractionError, match=r"\(org -> person\)"):
        X.Claim(
            subject=X.Mention("person", 0, 5), predicate="employs",
            object=X.Mention("org", 6, 10), span_start=0, span_end=20,
        )


def test_every_declared_predicate_has_valid_kinds():
    """The table is data, and data drifts. This is the meta-test on it."""
    for p, (s, o) in X.PREDICATES.items():
        assert s in X.ENTITY_KINDS, f"{p} domain {s!r} is not an entity kind"
        assert o in X.ENTITY_KINDS, f"{p} range {o!r} is not an entity kind"
    for a, b in X.INVERSES.items():
        assert a in X.PREDICATES, f"{a} has an inverse but is not a predicate"
        assert b in X.PREDICATES, f"{b} is named as an inverse but is not a predicate"
        assert X.INVERSES[b] == a, f"{a}/{b} inverse is not symmetric"
    for p in X.SYMMETRIC:
        assert p in X.PREDICATES or p == X.SAME_AS


def test_possibly_same_as_requires_matching_kinds():
    with pytest.raises(X.ExtractionError, match="same kind"):
        X.Claim(
            subject=X.Mention("org", 0, 5), predicate=X.SAME_AS,
            object=X.Mention("person", 6, 10), span_start=0, span_end=20,
        )
    # Same kind is fine, and the kind is free -- which is why it cannot live in
    # the fixed-pair table.
    X.Claim(
        subject=X.Mention("person", 0, 5), predicate=X.SAME_AS,
        object=X.Mention("person", 6, 10), span_start=0, span_end=20,
    )


def test_the_vocabulary_doc_is_generated_from_the_tables():
    """A prompt that lists the predicates by hand is a doc that goes stale."""
    doc = X.vocabulary_doc()
    for p in X.PREDICATES:
        assert p in doc, f"{p} is in the vocabulary but not in the brief"
    assert X.SAME_AS in doc
    assert str(X.MAX_RELATION_SPAN) in doc


# --------------------------------------------------------------------------
# The co-mention defence
# --------------------------------------------------------------------------


def test_a_relation_span_must_contain_both_mentions():
    with pytest.raises(X.ExtractionError, match="not inside the relation span"):
        X.Claim(
            subject=X.Mention("org", 0, 5), predicate="employs",
            object=X.Mention("person", 900, 910), span_start=0, span_end=100,
        )


def test_co_mention_across_a_page_cannot_be_expressed():
    """The whole `triple-entailed` defence, as arithmetic.

    A company in the header and a person in the footer CAN be enclosed by a
    span -- the page itself. What that span cannot be is short. Widening the
    span until it contains both is exactly the move the bound refuses."""
    with pytest.raises(X.ExtractionError, match="co-mentioned, not related"):
        X.Claim(
            subject=X.Mention("org", 0, 11),
            predicate="employs",
            object=X.Mention("person", 5000, 5014),
            span_start=0,
            span_end=5014,
        )


def test_a_relation_span_at_exactly_the_bound_is_allowed():
    """The bound must not be off by one in the refusing direction."""
    w = X.MAX_RELATION_SPAN
    X.Claim(
        subject=X.Mention("org", 0, 11), predicate="employs",
        object=X.Mention("person", w - 14, w), span_start=0, span_end=w,
    )
    with pytest.raises(X.ExtractionError, match="co-mentioned"):
        X.Claim(
            subject=X.Mention("org", 0, 11), predicate="employs",
            object=X.Mention("person", w - 13, w + 1), span_start=0, span_end=w + 1,
        )


# --------------------------------------------------------------------------
# Attributes
# --------------------------------------------------------------------------


def test_an_attribute_outside_the_allowlist_is_refused():
    s0, s1 = at(b"ACME S.A.S.")
    o0, o1 = at(b"Maria Restrepo")
    r0, r1 = sentence_span()
    with pytest.raises(X.ExtractionError, match="outside"):
        X.Claim(
            subject=X.Mention("org", s0, s1), predicate="employs",
            object=X.Mention("person", o0, o1), span_start=r0, span_end=r1,
            attrs={"salary": "lots"},
        )


def test_a_non_string_attribute_is_refused():
    s0, s1 = at(b"ACME S.A.S.")
    o0, o1 = at(b"Maria Restrepo")
    r0, r1 = sentence_span()
    with pytest.raises(X.ExtractionError, match="strings"):
        X.Claim(
            subject=X.Mention("org", s0, s1), predicate="employs",
            object=X.Mention("person", o0, o1), span_start=r0, span_end=r1,
            attrs={"since": 2026},
        )


# --------------------------------------------------------------------------
# Admission end to end
# --------------------------------------------------------------------------


def test_a_claim_becomes_two_nodes_and_an_edge(rig):
    d, res = rig
    recs = X.admit(d, res, acme_person_claim(), depth=1)
    assert [r.kind for r in recs] == ["node", "node", "edge"]
    subj, obj, edge = recs
    assert subj.canonical_key == "org::acme-s-a-s"
    assert obj.canonical_key == "person::maria-restrepo"
    assert edge.src == subj.id and edge.dst == obj.id
    assert edge.predicate == "employs"
    assert edge.attrs["title"] == "Chief Technology Officer"
    # Every record is observed, and each carries its OWN span.
    assert all(r.origin == "observed" for r in recs)
    assert subj.evidence.quote == "ACME S.A.S."
    assert obj.evidence.quote == "Maria Restrepo"
    assert "appointed" in edge.evidence.quote


def test_admitted_records_reach_the_store(rig):
    """The seam. The store asks the daemon for itself, so this proves the
    evidence built here satisfies a gate this module does not implement."""
    d, res = rig
    conn = S.connect(Path(d.root).parent / "map.db")
    recs = X.admit(d, res, acme_person_claim(), depth=1)
    assert [S.put_record(conn, r, admitter=d) for r in recs] == ["inserted"] * 3
    assert S.inventory(conn)["total"] == 3


def test_an_admitted_record_is_not_yet_expandable(rig):
    """`Record everything. Expand only what verifies.` Admission is not a verdict."""
    d, res = rig
    conn = S.connect(Path(d.root).parent / "map.db")
    for r in X.admit(d, res, acme_person_claim(), depth=1):
        S.put_record(conn, r, admitter=d)
    assert S.expandable_ids(conn) == []
    S.set_verdict(conn, "org::acme-s-a-s", "entailed")
    assert S.expandable_ids(conn) == ["org::acme-s-a-s"]


def test_a_self_edge_is_refused(rig):
    d, res = rig
    s0, s1 = at(b"ACME S.A.S.")
    r0, r1 = sentence_span()
    with pytest.raises(X.ExtractionError, match="self-edge"):
        X.admit(d, res, X.Claim(
            subject=X.Mention("org", s0, s1), predicate="partner_of",
            object=X.Mention("org", s0, s1), span_start=r0, span_end=r1,
        ), depth=1)


def test_two_spans_naming_the_same_company_are_a_self_edge(tmp_path):
    """Not the same offsets, the same ENTITY. The check is on keys, not spans."""
    page = b"ACME S.A.S. and acme s.a.s. are partners, allegedly."
    d = F.FetchDaemon(
        root=tmp_path / "runs", run_id="r2", politeness=AllowAll(),
        transport=lambda u: (200, page, u), key=KEY,
    )
    d.seal_plan({"seeds": ["x"], "max_depth": 1})
    res = d.fetch("https://example.com/dup")
    a0, a1 = at(b"ACME S.A.S.", page)
    b0, b1 = at(b"acme s.a.s.", page)
    with pytest.raises(X.ExtractionError, match="self-edge"):
        X.admit(d, res, X.Claim(
            subject=X.Mention("org", a0, a1), predicate="partner_of",
            object=X.Mention("org", b0, b1), span_start=0, span_end=len(page),
        ), depth=1)


def test_a_span_past_the_end_of_the_page_is_refused(rig):
    d, res = rig
    r0, r1 = sentence_span()
    with pytest.raises(F.FetchError, match="runs past"):
        X.admit(d, res, X.Claim(
            subject=X.Mention("org", *at(b"ACME S.A.S.")), predicate="employs",
            object=X.Mention("person", len(PAGE) + 1, len(PAGE) + 20),
            span_start=0, span_end=len(PAGE) + 20,
        ), depth=1)


def test_edge_ids_are_deterministic_and_do_not_collide():
    a = X.edge_id("org::a", "employs", "person::b")
    assert a == X.edge_id("org::a", "employs", "person::b")
    assert a != X.edge_id("org::b", "employs", "person::a")


def test_edge_ids_survive_a_field_boundary_shifting():
    """The separator, tested at the collision it actually prevents.

    An earlier version of this test asserted a pair that does not collide under
    concatenation either, so a mutation sweep removing the separators survived
    it. These two DO concatenate to the same string: without a delimiter, both
    ("a", "bc", "d") and ("ab", "c", "d") are "abcd", and the store would read
    two unrelated edges as one edge sighted twice.
    """
    assert "a" + "bc" + "d" == "ab" + "c" + "d", "the fixture must actually collide"
    assert X.edge_id("a", "bc", "d") != X.edge_id("ab", "c", "d")


def test_the_daemon_still_refuses_forged_evidence_after_extraction(rig, tmp_path):
    """Admission is a convenience, not the security boundary. A caller that
    skipped this module entirely must still be refused at the store."""
    d, res = rig
    conn = S.connect(tmp_path / "forged.db")
    forged = b"ACME S.A.S. is a criminal enterprise"
    digest = F.sha256_of(forged)
    (d.snapshots / digest).write_bytes(forged)
    rec = S.Record(
        id="org::acme-s-a-s", kind="node", canonical_key="org::acme-s-a-s",
        depth=1, layer="L2", origin="observed",
        evidence=S.Evidence(url=res.url, sha256=digest,
                            snapshot=f"snapshots/{digest}", span_start=0,
                            span_end=11, quote="ACME S.A.S."),
    )
    with pytest.raises(S.StoreError):
        S.put_record(conn, rec, admitter=d)


# --------------------------------------------------------------------------
# The extractor's wire format
# --------------------------------------------------------------------------


def test_claims_round_trip_through_json(rig):
    d, res = rig
    s0, s1 = at(b"ACME S.A.S.")
    o0, o1 = at(b"Maria Restrepo")
    r0, r1 = sentence_span()
    blob = json.dumps([{
        "subject": {"kind": "org", "span_start": s0, "span_end": s1},
        "predicate": "employs",
        "object": {"kind": "person", "span_start": o0, "span_end": o1},
        "span_start": r0, "span_end": r1,
        "attrs": {"title": "Chief Technology Officer"},
    }])
    claims = X.claims_from_json(blob)
    assert len(claims) == 1
    recs = X.admit(d, res, claims[0], depth=1)
    assert recs[1].canonical_key == "person::maria-restrepo"


def test_an_extractor_that_names_an_entity_is_refused():
    """The field this design removed on purpose. Ignoring it would hide the
    misunderstanding; the whole point is that a name is not sayable."""
    blob = json.dumps([{
        "subject": {"kind": "org", "span_start": 0, "span_end": 5, "name": "ACME"},
        "predicate": "employs",
        "object": {"kind": "person", "span_start": 6, "span_end": 10},
        "span_start": 0, "span_end": 20,
    }])
    with pytest.raises(X.ExtractionError, match="unknown keys"):
        X.claims_from_json(blob)


def test_an_unknown_key_on_the_claim_itself_is_refused():
    """The mention-level check and the claim-level check are different code.

    A mutation sweep found the claim-level one unenforced: the only test for an
    invented field put it inside a `subject`, so removing the outer refusal
    changed nothing. `confidence` is the realistic case — a model asked for
    structured output volunteers one, and silently dropping it would let a
    reader believe the number was considered.
    """
    blob = json.dumps([{
        "subject": {"kind": "org", "span_start": 0, "span_end": 5},
        "predicate": "employs",
        "object": {"kind": "person", "span_start": 6, "span_end": 10},
        "span_start": 0, "span_end": 20,
        "confidence": 0.91,
    }])
    with pytest.raises(X.ExtractionError, match="unknown keys"):
        X.claims_from_json(blob)


def test_a_boolean_offset_is_refused():
    """`isinstance(True, int)` is True in Python, so a bool silently means 0."""
    blob = json.dumps([{
        "subject": {"kind": "org", "span_start": True, "span_end": 5},
        "predicate": "employs",
        "object": {"kind": "person", "span_start": 6, "span_end": 10},
        "span_start": 0, "span_end": 20,
    }])
    with pytest.raises(X.ExtractionError, match="must be an integer"):
        X.claims_from_json(blob)


@pytest.mark.parametrize("blob,match", [
    ("not json at all", "not JSON"),
    ('{"a": 1}', "expected a list"),
    ("[3]", "not an object"),
    ('[{"predicate": "employs"}]', "missing"),
])
def test_malformed_extractor_output_is_refused(blob, match):
    with pytest.raises(X.ExtractionError, match=match):
        X.claims_from_json(blob)


def test_an_empty_claim_list_is_a_valid_answer():
    """A page that relates nothing is a real outcome, not a failure."""
    assert X.claims_from_json("[]") == []
