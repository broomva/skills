"""Tests for identity resolution.

One property carries this module and every test is a variation on it: **it
proposes, it never merges.** A wrong merge silently attributes one company's
leadership, subsidiaries and profiles to another, and nothing downstream can
recover the two halves because the evidence for both now hangs off one id. A
missing merge is two nodes a reader can see and join.

So the tests come in pairs. That a real near-duplicate IS proposed shows the
similarity works; that nothing is ever merged shows the restraint is a mechanism
rather than a property of the fixture. A resolver that proposed nothing would
pass every no-merge test and fail every proposal test, which is why neither half
is enough alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extract as X  # noqa: E402
import identity as I  # noqa: E402
import store as S  # noqa: E402


def node(key, name, **over):
    base = {
        "id": key, "kind": "node", "canonical_key": key, "depth": 0,
        "layer": "L2", "origin": "observed", "verdict": "entailed",
        "attrs": {"name": name}, "inferred_from": [],
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------


def test_legal_forms_do_not_distinguish_companies():
    """`ACME S.A.S.` and `ACME S.A.` are one company, and the suffix is exactly
    the part that varies between sources."""
    assert I.similarity("ACME S.A.S.", "ACME S.A.") == I.EXACT_AFTER_NORMALISATION
    assert I.comparable("ACME S.A.S.") == I.comparable("ACME Ltda")


@pytest.mark.parametrize("accented,plain", [
    # `Café` is the WEAK case and was the only one here at first: `é` sits at a
    # syllable boundary, so dropping the combining-character filter splits it
    # into the same tokens anyway and a mutation sweep found the filter
    # removable. These are the cases where it actually decides the answer.
    ("Compañía Nacional", "Compania Nacional"),      # compan|i|a without it
    ("Zürich Versicherung", "Zurich Versicherung"),  # zu|rich without it
    ("Ångström AB", "Angstrom AB"),
    ("Škoda Auto", "Skoda Auto"),
    ("Café Nacional", "Cafe Nacional"),
])
def test_accents_do_not_distinguish_companies(accented, plain):
    """One word written by two systems. A crawl that treats these as two
    companies has failed at the first hurdle in every non-English market —
    which is the market this was built for."""
    assert I.similarity(accented, plain) == I.EXACT_AFTER_NORMALISATION
    assert I.comparable(accented) == I.comparable(plain)


def test_an_accented_name_does_not_shatter_into_fragments():
    """The failure the filter prevents, stated directly.

    Without it `Compañía` tokenises to `compan`, `i`, `a` — three fragments that
    match nothing and, once `_join_initials` runs, produce a spurious `ia`
    token. A company whose name shatters is a company that merges with nobody.
    """
    assert I.comparable("Compañía Nacional") == ("compania", "nacional")


def test_token_order_does_not_distinguish_companies():
    """A reader would call these a candidate pair without hesitating."""
    assert I.similarity("Nacional de Café", "Café Nacional") == I.EXACT_AFTER_NORMALISATION


def test_typographically_close_but_different_companies_are_not_similar():
    """The reason this is token overlap and not edit distance.

    `Banco Agrario` and `Banco Agrícola` are two banks a few characters apart;
    character distance calls them the same and gets it badly wrong.
    """
    assert I.similarity("Banco Agrario", "Banco Agrícola") < I.DEFAULT_THRESHOLD


def test_a_shared_stopword_is_not_a_resemblance():
    """Two companies sharing only `Group` are not candidates for being one."""
    assert I.similarity("Alpha Group", "Beta Group") < I.DEFAULT_THRESHOLD


def test_a_name_that_is_all_legal_forms_keeps_its_tokens():
    """Reducing it to nothing would make it match every other poor name at 1.0."""
    assert I.comparable("The Company Ltd") != ()
    assert I.similarity("The Company Ltd", "The Holdings Inc") < 1.0


@pytest.mark.parametrize("a,b", [("", "ACME"), ("ACME", ""), ("", "")])
def test_an_empty_name_resembles_nothing(a, b):
    assert I.similarity(a, b) == 0.0


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------


def test_a_real_near_duplicate_is_proposed():
    """The positive half. Without it, a resolver that returns [] passes
    every no-merge test in this file."""
    recs = [node("org::acme-s-a-s", "ACME S.A.S."), node("org::acme-ltda", "ACME Ltda")]
    found = I.candidates(recs)
    assert len(found) == 1
    assert found[0].score == I.EXACT_AFTER_NORMALISATION
    assert "identical after normalising" in found[0].reason


def test_two_different_companies_are_not_proposed():
    recs = [node("org::alpha", "Alpha Systems"), node("org::beta", "Beta Logistics")]
    assert I.candidates(recs) == []


def test_kinds_are_never_crossed():
    """An org and a person sharing a name are a person and the company named
    after them, and proposing otherwise is worse than proposing nothing."""
    recs = [node("org::maria-restrepo", "Maria Restrepo"),
            node("person::maria-restrepo", "Maria Restrepo")]
    assert I.candidates(recs) == []


def test_profiles_are_never_proposed():
    """A profile's identity is its URL, which is exact by construction. Two
    profile records with different keys are two different pages, and no amount
    of textual similarity makes them one."""
    a = X.key_for("profile", "https://a.test/x/y")
    b = X.key_for("profile", "https://a.test/x-y")
    assert a != b
    recs = [node(a, "https://a.test/x/y"), node(b, "https://a.test/x-y")]
    assert I.candidates(recs) == []
    assert "profile" in X.EXACT_KINDS


def test_a_pair_is_proposed_once_not_once_per_direction():
    """`possibly_same_as` is symmetric; both directions would double-count."""
    recs = [node("org::b-sas", "Beta S.A.S."), node("org::b-ltda", "Beta Ltda")]
    found = I.candidates(recs)
    assert len(found) == 1
    assert found[0].left < found[0].right, "the pair must be ordered"


def test_edges_and_non_node_records_are_ignored():
    recs = [
        {"id": "e", "kind": "edge", "predicate": "employs", "canonical_key": "e"},
        node("org::acme", "ACME S.A.S."),
    ]
    assert I.candidates(recs) == []


def test_a_node_with_no_name_is_ignored():
    recs = [node("org::a", "ACME S.A.S."), node("org::b", "ACME Ltda", attrs={})]
    assert I.candidates(recs) == []


def test_the_pair_cap_refuses_rather_than_truncating():
    """A proposer that quietly stops at a cap reports the same empty tail as a
    map with no more candidates."""
    recs = [node(f"org::acme-{i}", f"ACME {i//3} S.A.S.") for i in range(30)]
    with pytest.raises(I.IdentityError, match="exceed the cap"):
        I.candidates(recs, max_pairs=2)


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.5])
def test_an_incoherent_threshold_is_refused(bad):
    with pytest.raises(I.IdentityError):
        I.candidates([], threshold=bad)


# --------------------------------------------------------------------------
# The proposal is an edge, and it is simulated
# --------------------------------------------------------------------------


def test_a_proposal_is_simulated_not_observed(tmp_path):
    """No page says these two records are the same entity.

    Grading it `observed` because the two records underneath it were observed is
    exactly the laundering `meet_origin` exists to prevent.
    """
    conn = S.connect(tmp_path / "m.db")
    c = I.Candidate("org::a", "org::b", "org", 1.0, "identical")
    rec = I.propose(conn, c, depth=0)
    assert rec.origin == "simulated"
    assert rec.evidence is None
    assert set(rec.inferred_from) == {"org::a", "org::b"}
    assert rec.predicate == X.SAME_AS


def test_a_proposal_can_never_expand(tmp_path):
    """`expandable()` is observed AND entailed. A similarity score is not
    evidence, so a wrong guess costs one edge rather than a subtree."""
    conn = S.connect(tmp_path / "m.db")
    rec = I.propose(conn, I.Candidate("org::a", "org::b", "org", 1.0, "x"), depth=0)
    S.put_record(conn, rec)
    S.set_verdict(conn, rec.id, "entailed")
    assert S.expandable_ids(conn) == [], "a simulated record must not seed a hop"


def test_resolve_proposes_and_merges_nothing(tmp_path):
    """The load-bearing test of the module."""
    conn = S.connect(tmp_path / "m.db")
    for r in (node("org::acme-s-a-s", "ACME S.A.S."), node("org::acme-ltda", "ACME Ltda")):
        S.put_record(conn, S.Record(
            id=r["id"], kind="node", canonical_key=r["canonical_key"], depth=0,
            layer="L2", origin="simulated", inferred_from=("seed",),
            attrs=r["attrs"]))
    before = {r["id"] for r in S.select(conn) if r["kind"] == "node"}
    report = I.resolve(conn)
    after = {r["id"] for r in S.select(conn) if r["kind"] == "node"}

    assert report["proposed"] == 1
    assert report["merged"] == 0
    assert after == before, "resolve must not add, remove or merge any NODE"
    edges = [r for r in S.select(conn) if r["kind"] == "edge"]
    assert len(edges) == 1 and edges[0]["predicate"] == X.SAME_AS
    assert edges[0]["origin"] == "simulated"


def test_resolve_is_idempotent(tmp_path):
    """The edge id is a pure function of its endpoints, so a second pass
    re-sights rather than duplicating."""
    conn = S.connect(tmp_path / "m.db")
    for key, name in (("org::a-sas", "Gamma S.A.S."), ("org::a-ltda", "Gamma Ltda")):
        S.put_record(conn, S.Record(id=key, kind="node", canonical_key=key, depth=0,
                                    layer="L2", origin="simulated",
                                    inferred_from=("seed",), attrs={"name": name}))
    first = I.resolve(conn)
    second = I.resolve(conn)
    assert first["newly_inserted"] == 1
    assert second["newly_inserted"] == 0
    assert second["proposed"] == 1, "still proposed, just not re-inserted"
    assert len([r for r in S.select(conn) if r["kind"] == "edge"]) == 1


def test_resolve_on_a_map_with_no_duplicates_says_so(tmp_path):
    """An empty list is a real answer, reported rather than silent."""
    conn = S.connect(tmp_path / "m.db")
    S.put_record(conn, S.Record(id="org::only", kind="node", canonical_key="org::only",
                                depth=0, layer="L2", origin="simulated",
                                inferred_from=("seed",), attrs={"name": "Solo S.A.S."}))
    report = I.resolve(conn)
    assert report["proposed"] == 0
    assert report["merged"] == 0
    assert "never a merge" in report["note"]


@pytest.mark.parametrize("a,b", [
    ("Acme Holdings", "Acme Company"),
    ("Acme Holdings", "Acme Ventures"),
])
def test_words_that_carry_identity_are_not_stopwords(a, b):
    """`holdings` and `company` LOOK like noise and are not.

    Dropping them scored these at 1.0 — two plausibly distinct sister entities
    proposed as one. The harm is bounded, since a proposal is simulated and
    non-expandable, but a proposer whose list is full of near-certain false
    positives is a proposer nobody reads.
    """
    assert I.similarity(a, b) < I.DEFAULT_THRESHOLD
    assert "holdings" not in I.STOPWORDS and "company" not in I.STOPWORDS


def test_words_that_carry_no_identity_still_are_stopwords():
    """The other direction: the list must not become empty out of caution."""
    assert I.similarity("Alpha Group", "Beta Group") < I.DEFAULT_THRESHOLD
    assert I.similarity("Nacional de Café", "Café Nacional") == I.EXACT_AFTER_NORMALISATION
