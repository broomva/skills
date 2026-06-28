"""Unit tests for the colombia-conflict knowledge engine (cc.py).

Pure-stdlib, zero network. Covers the deterministic core: tokenization,
overlap scoring, the data queries, the `align` non-repetition scorer, the
catalog generator, two-tier load, AND data-integrity invariants over the
JSON datasets (so a malformed dataset fails the gate, not just bad code).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cc  # noqa: E402

DATA = ROOT / "data"


def _j(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


# --- tokenize / scoring ------------------------------------------------------

def test_tokenize_folds_accents_and_drops_stopwords():
    toks = cc.tokenize("La reparación de las víctimas")
    assert "reparacion" in toks      # accent-folded
    assert "victimas" in toks
    assert "las" not in toks         # stopword dropped
    assert "de" not in toks


def test_tokenize_drops_short_tokens():
    assert "is" not in cc.tokenize("is a paz")
    assert "paz" in cc.tokenize("is a paz")


def test_score_overlap_bounds():
    assert cc.score_overlap(set(), {"a"}) == 0.0
    assert cc.score_overlap({"a", "b"}, {"a", "b"}) == 1.0
    assert cc.score_overlap({"a", "b"}, {"a"}) == 0.5


# --- recommendation search ---------------------------------------------------

def test_search_recommendations_by_theme():
    blocks = _j("recommendations.json")["blocks"]
    drug = cc.search_recommendations(blocks, theme="drug")
    assert len(drug) == 1
    assert drug[0]["block"] == 4


def test_search_recommendations_by_block_and_query():
    blocks = _j("recommendations.json")["blocks"]
    assert cc.search_recommendations(blocks, block=6)[0]["theme"] == "security"
    hits = cc.search_recommendations(blocks, query="ELN negotiation")
    assert any(b["block"] == 1 for b in hits)


# --- lookups -----------------------------------------------------------------

def test_lookup_all_vs_key():
    stats = _j("statistics.json")["statistics"]
    assert cc.lookup(stats, None, fields=("key", "label")) == stats
    one = cc.lookup(stats, "disappearance", fields=("key", "label"))
    assert one and any("disappearance" in r["label"].lower() for r in one)


def test_lookup_actor():
    actors = _j("actors.json")["actors"]
    para = cc.lookup(actors, "paramilitar", fields=("key", "name", "type"))
    assert para and para[0]["key"] == "paramilitaries"


# --- align (the non-repetition scorer) --------------------------------------

def test_align_routes_drug_policy_to_block4():
    blocks = _j("recommendations.json")["blocks"]
    ranked = cc.align_text(
        "legalize cannabis and regulate coca cultivation as a public-health drug policy",
        blocks)
    assert ranked, "expected at least one matching block"
    assert ranked[0]["block"] == 4
    assert 0.0 < ranked[0]["score"] <= 1.0


def test_align_routes_land_to_territorial_block():
    blocks = _j("recommendations.json")["blocks"]
    ranked = cc.align_text("an agrarian reform and land restitution program for rural campesinos", blocks)
    assert any(b["theme"] == "territorial-peace" for b in ranked)


def test_align_unrelated_returns_empty():
    blocks = _j("recommendations.json")["blocks"]
    assert cc.align_text("quarterly javascript frontend refactor", blocks) == []


def test_contrary_flags_catches_fumigation_as_opposed_to_block4():
    # A proposal the report recommends ENDING must be flagged CONTRARY, not aligned.
    flags = cc.contrary_flags("increase aerial glyphosate fumigation and forced coca eradication")
    blocks = {f["block"] for f in flags}
    assert 4 in blocks
    assert any("glyphosate" in f["contrary_tokens"] or "fumigation" in f["contrary_tokens"]
               for f in flags)


def test_contrary_flags_empty_for_aligned_proposal():
    assert cc.contrary_flags("support campesinos cocaleros with voluntary crop substitution") == []


# --- catalog + two-tier load -------------------------------------------------

def test_build_catalog_mentions_each_dataset():
    cat = cc.build_catalog(
        _j("statistics.json")["statistics"], _j("actors.json")["actors"],
        _j("recommendations.json")["blocks"], _j("concepts.json")["concepts"],
        [("digests/x.md", "X Volume")])
    for needle in ("stat:`homicides`", "actor:`paramilitaries`", "rec-block:4", "concept:`paz grande`", "page:digests/x.md"):
        assert needle in cat, needle


def test_two_tier_load_finds_topic():
    res = cc.two_tier_load("desaparición forzada víctimas", limit=6)
    assert res["topic"]
    assert res["tier1"] or res["tier2"], "expected some retrieval hit"


# --- data integrity invariants ----------------------------------------------

def test_recommendations_have_eight_blocks_and_unique_numbers():
    blocks = _j("recommendations.json")["blocks"]
    assert len(blocks) == 8
    nums = [b["block"] for b in blocks]
    assert nums == sorted(nums) and len(set(nums)) == 8
    for b in blocks:
        assert b["recommendations"] and b["theme"] and b["title"] and b["keywords"]


def test_statistics_have_required_fields():
    for s in _j("statistics.json")["statistics"]:
        assert s.get("key") and s.get("label")
        assert "documented" in s and "period" in s


def test_actors_have_principal_responsibility():
    for a in _j("actors.json")["actors"]:
        assert a.get("key") and a.get("name")
        assert a.get("principal_responsibility")


def test_concepts_have_term_and_gloss():
    for c in _j("concepts.json")["concepts"]:
        assert c.get("term") and c.get("gloss")


def test_all_datasets_are_valid_json():
    for name in ("statistics.json", "actors.json", "recommendations.json", "concepts.json"):
        assert isinstance(_j(name), dict)


def test_committed_catalog_is_not_stale():
    """The committed references/knowledge-index.md must equal a fresh build —
    so `cc.py index --check` is green on a fresh clone (CI gate honesty)."""
    fresh = cc.build_catalog(
        _j("statistics.json")["statistics"], _j("actors.json")["actors"],
        _j("recommendations.json")["blocks"], _j("concepts.json")["concepts"],
        cc._digest_headers())
    committed = (ROOT / "references" / "knowledge-index.md").read_text(encoding="utf-8")
    assert committed == fresh, "knowledge-index.md is stale — run `python3 scripts/cc.py index`"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
