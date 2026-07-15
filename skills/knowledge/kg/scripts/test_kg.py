#!/usr/bin/env python3
"""Dependency-free tests for kg.py (run: python3 scripts/test_kg.py).

Covers the routing-batch additions (BRO-1422):
  A  --terms query expansion (dedupe, ordering)
  B  --expand graph 1-hop neighbour gathering
  C  --explain per-signal score trace
  D  hub-aware tiebreak (in-degree before alphabetical)

Plus regression coverage of the pre-existing scorer/parser so the batch
can't silently change baseline behaviour. Pure asserts, no pytest.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("kg", _HERE / "kg.py")
kg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kg)

_failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        _failures.append(msg)


def _entry(slug, type_="concept", status="entity", claim="", tags=None,
           out_links=None, in_links=None, sources=None, rel_path=None):
    e = kg.CatalogEntry(slug)
    e.type, e.status, e.claim = type_, status, claim
    e.tags = tags or []
    e.out_links = out_links or []
    e.in_links = in_links or []
    e.sources = sources or []
    e.rel_path = rel_path or f"{type_}/{slug}.md"
    return e


# ── tokenize_topic ────────────────────────────────────────────────────────────
def test_tokenize():
    print("test_tokenize")
    toks = kg.tokenize_topic("What is the LLM-as-index architecture?")
    check("llm-as-index" in toks, "keeps hyphenated term")
    check("the" not in toks and "is" not in toks, "drops stopwords")
    check(all(len(t) >= 2 for t in toks), "drops single chars")


# ── score_entity + trace (C) ────────────────────────────────────────────────
def test_score_and_trace():
    print("test_score_and_trace")
    e = _entry("qmd", type_="tool", claim="hybrid markdown search",
               tags=["retrieval", "markdown-first"], sources=["github"])
    trace: list = []
    score = kg.score_entity(e, ["qmd", "retrieval", "search"], trace=trace)
    # slug==qmd(10) + claim~search(3) + tag==retrieval(4) = 17
    check(score == 17, f"score rubric sums correctly (got {score}, want 17)")
    check(sum(p for _, p in trace) == score, "trace points sum to score")
    check(any(lbl == "slug==qmd" for lbl, _ in trace), "trace records exact slug hit")
    # hot path (trace=None) returns identical score, no error
    check(kg.score_entity(e, ["qmd", "retrieval", "search"]) == 17,
          "trace=None matches traced score")


# ── query expansion dedupe (A) ──────────────────────────────────────────────
def test_terms_expansion_dedupe():
    print("test_terms_expansion_dedupe")
    # Mirror the cmd_load expansion logic on its inputs.
    topic_terms = kg.tokenize_topic("agent memory")
    for extra in ["memory,recall", "knowledge graph"]:
        topic_terms.extend(kg.tokenize_topic(extra))
    deduped = list(dict.fromkeys(topic_terms))
    check(deduped.count("memory") == 1, "duplicate term collapsed")
    check(deduped[:2] == ["agent", "memory"], "topic terms keep priority")
    check("recall" in deduped and "knowledge" in deduped, "synonyms added")


# ── hub-aware tiebreak (D) ──────────────────────────────────────────────────
def test_hub_tiebreak():
    print("test_hub_tiebreak")
    a = _entry("a-low", in_links=[])              # in-degree 0
    b = _entry("b-hub", in_links=["x", "y", "z"]) # in-degree 3
    c = _entry("c-mid", in_links=["x"])           # in-degree 1
    scored = [(10, a), (10, b), (10, c)]  # all tied on relevance
    scored.sort(key=lambda x: (-x[0], -len(x[1].in_links), x[1].slug))
    order = [e.slug for _, e in scored]
    check(order == ["b-hub", "c-mid", "a-low"],
          f"ties ordered by in-degree desc (got {order})")


# ── parse_catalog round-trip ────────────────────────────────────────────────
CATALOG = """---
generated: 2026-01-01T00:00:00+00:00
schema: dense-catalog-v2
---

# Knowledge Index

#### root [pattern·entity] · score 9
A root pattern about retrieval and indexing.
→ child-a, child-b · ← parent · #pattern #retrieval · aka: root-alias, oldname · src: paper | repo
path: pattern/root.md

#### child-a [concept·entity]
Child A concept body.
→ root · #concept
path: concept/child-a.md

#### child-b [tool·entity]
Child B tool.
→ root · #tool
path: tool/child-b.md
"""


def test_parse_catalog():
    print("test_parse_catalog")
    meta, entries = kg.parse_catalog(CATALOG)
    check(meta.get("schema") == "dense-catalog-v2", "frontmatter parsed")
    check(len(entries) == 3, f"3 blocks parsed (got {len(entries)})")
    root = next(e for e in entries if e.slug == "root")
    check(root.out_links == ["child-a", "child-b"], "out_links parsed")
    check(root.in_links == ["parent"], "in_links parsed")
    check(set(root.tags) == {"pattern", "retrieval"}, "tags parsed")
    check(root.sources == ["paper", "repo"], "pipe-separated sources parsed")
    check(root.aliases == ["root-alias", "oldname"], "aka: aliases parsed")
    check(root.rel_path == "pattern/root.md", "path line parsed")


# ── alias scoring (BRO-1423: a query for an alias routes to the entity) ──────
def test_alias_scoring():
    print("test_alias_scoring")
    meta, entries = kg.parse_catalog(CATALOG)
    root = next(e for e in entries if e.slug == "root")
    # exact alias match scores +8 (just below slug's +10, above tag's +4)
    tr = []
    s_exact = kg.score_entity(root, ["oldname"], trace=tr)
    check(s_exact == 8, f"exact alias match scores 8 (got {s_exact})")
    check(any(lbl == "alias==oldname" for lbl, _ in tr), "alias-exact trace label present")
    # substring alias match scores +4
    s_sub = kg.score_entity(root, ["alias"], trace=None)  # 'alias' ⊂ 'root-alias'
    check(s_sub == 4, f"substring alias match scores 4 (got {s_sub})")
    # an entity with NO aliases is unaffected
    child = next(e for e in entries if e.slug == "child-a")
    check(child.aliases == [], "entity without aka: has empty aliases")
    check(kg.score_entity(child, ["oldname"]) == 0, "no spurious alias score")


# ── tolerant score parsing (regression: dict-repr score must not drop block) ──
def test_parse_tolerates_space_bearing_score():
    print("test_parse_tolerates_space_bearing_score")
    # Stub-deterministic entities once emitted a dict-repr score with embedded
    # spaces; the old `score \S+` grammar made the whole block fail to match,
    # silently dropping the entity from routing (23 entities at 370).
    catalog = (
        "---\nschema: dense-catalog-v2\n---\n\n# Knowledge Index\n\n"
        "#### dict-scored [industry-pattern·candidate] · "
        "score {'total': '6/9', 'novelty': 1, 'method': 'stub-deterministic'}\n"
        "A pattern whose score is a dict repr with spaces.\n"
        "→ other · #industry-pattern\n"
        "path: industry-pattern/dict-scored.md\n\n"
        "#### plain [concept·entity] · score 9\n"
        "A normally-scored concept.\n"
        "→ other · #concept\n"
        "path: concept/plain.md\n"
    )
    meta, entries = kg.parse_catalog(catalog)
    slugs = {e.slug for e in entries}
    check("dict-scored" in slugs, "dict-repr-score block is NOT dropped")
    check("plain" in slugs, "normal block still parses alongside")
    ds = next((e for e in entries if e.slug == "dict-scored"), None)
    check(ds is not None and ds.rel_path == "industry-pattern/dict-scored.md",
          "dict-scored path still parsed (block grammar intact)")
    check(ds is not None and ds.tags == ["industry-pattern"],
          "dict-scored meta-line still parsed after space-bearing score")


# ── integration: cmd_load with --expand and --explain (B + C) ───────────────
def test_cmd_load_integration():
    print("test_cmd_load_integration")
    tmp = Path(tempfile.mkdtemp())
    (tmp / "docs").mkdir()
    ents = tmp / "research" / "entities"
    for sub in ("pattern", "concept", "tool"):
        (ents / sub).mkdir(parents=True)
    (tmp / "docs" / "knowledge-index.md").write_text(CATALOG)
    (ents / "pattern" / "root.md").write_text("# root\nbody about retrieval\n")
    (ents / "concept" / "child-a.md").write_text("# child-a\nbody\n")
    (ents / "tool" / "child-b.md").write_text("# child-b\nbody\n")

    # Repoint module globals at the fixture.
    orig = (kg.BROOMVA_ROOT, kg.CATALOG_PATH, kg.ENTITIES_DIR, kg.STALE_WARN_SECONDS)
    kg.BROOMVA_ROOT = tmp
    kg.CATALOG_PATH = tmp / "docs" / "knowledge-index.md"
    kg.ENTITIES_DIR = ents
    kg.STALE_WARN_SECONDS = 10**9  # never warn in tests
    try:
        # --expand 1 with headroom (n=5) pulls all of root's neighbours.
        args = SimpleNamespace(topic="retrieval indexing", n=5, type=None,
                               terms=None, expand=1, explain=False, json=True,
                               no_bodies=True, body_search=False, quiet=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = kg.cmd_load(args)
        check(rc == 0, "cmd_load returns 0")
        payload = json.loads(buf.getvalue())
        slugs = [(m["slug"], m["via"]) for m in payload["matches"]]
        primary = [s for s, v in slugs if v is None]
        expanded = [(s, v) for s, v in slugs if v is not None]
        check(primary == ["root"], f"primary match is root (got {primary})")
        check({s for s, _ in expanded} == {"child-a", "child-b"},
              f"1-hop pulled both neighbours (got {expanded})")
        check(all(v == "root" for _, v in expanded), "neighbours tagged via=root")

        # Hub-explosion guard: expansion is capped at --n. With n=1, the single
        # primary plus at most one neighbour (the more-central one) come back.
        args.n = 1
        buf = io.StringIO()
        with redirect_stdout(buf):
            kg.cmd_load(args)
        capped = json.loads(buf.getvalue())["matches"]
        n_exp = sum(1 for m in capped if m["via"] is not None)
        check(n_exp == 1, f"expansion capped at --n (got {n_exp} neighbours for n=1)")

        # --expand clamps to 1 hop: a large hop count yields the same neighbour
        # set as --expand 1 (provenance can't dangle).
        args.n = 5
        args.expand = 1
        buf = io.StringIO()
        with redirect_stdout(buf):
            kg.cmd_load(args)
        one_hop = {m["slug"] for m in json.loads(buf.getvalue())["matches"] if m["via"]}
        args.expand = 9
        buf = io.StringIO()
        with redirect_stdout(buf):
            kg.cmd_load(args)
        many_hop = {m["slug"] for m in json.loads(buf.getvalue())["matches"] if m["via"]}
        check(one_hop == many_hop, "--expand >1 clamps to identical 1-hop result")

        # --explain populates a trace without changing rc.
        args.expand, args.explain, args.json = 0, True, False
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = kg.cmd_load(args)
        check(rc == 0 and "explain:" in buf.getvalue(), "--explain emits a trace line")
    finally:
        kg.BROOMVA_ROOT, kg.CATALOG_PATH, kg.ENTITIES_DIR, kg.STALE_WARN_SECONDS = orig


# ── tier-2 confidence trigger (auto-recall when tier-1 hits are weak) ─────────
def test_tier2_confidence_trigger():
    print("test_tier2_confidence_trigger")
    tmp = Path(tempfile.mkdtemp())
    (tmp / "docs").mkdir()
    ents = tmp / "research" / "entities"
    (ents / "concept").mkdir(parents=True)
    # weak-match: 'widget' appears only as a TAG SUBSTRING (#widgetry) → tier-1 ≈ 3.
    # body-answer: query terms appear ONLY in the body → tier-1 = 0, body bonus = 4.
    catalog = (
        "---\nschema: dense-catalog-v2\n---\n\n# Knowledge Index\n\n"
        "#### weak-match [concept·entity]\nA concept about gizmos.\n"
        "→ other · #widgetry · src: t\npath: concept/weak-match.md\n\n"
        "#### body-answer [concept·entity]\nA concept about sprockets.\n"
        "→ other · #sprockets · src: t\npath: concept/body-answer.md\n"
    )
    (tmp / "docs" / "knowledge-index.md").write_text(catalog)
    (ents / "concept" / "weak-match.md").write_text("# weak-match\ngizmos only\n")
    (ents / "concept" / "body-answer.md").write_text(
        "# body-answer\nthis body mentions widget and gadget prominently\n")
    orig = (kg.BROOMVA_ROOT, kg.CATALOG_PATH, kg.ENTITIES_DIR, kg.STALE_WARN_SECONDS)
    kg.BROOMVA_ROOT = tmp
    kg.CATALOG_PATH = tmp / "docs" / "knowledge-index.md"
    kg.ENTITIES_DIR = ents
    kg.STALE_WARN_SECONDS = 10**9
    try:
        def load(floor):
            # n=1 → only the single weak tier-1 hit; the OLD `count < n` gate can't
            # fire (1 hit, not < 1). Only the confidence gate (top < floor) can.
            args = SimpleNamespace(topic="widget gadget", n=1, type=None, terms=None,
                                   expand=0, explain=False, json=True, no_bodies=True,
                                   body_search=False, tier2_floor=floor, quiet=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                kg.cmd_load(args)
            return [m["slug"] for m in json.loads(buf.getvalue())["matches"]]

        with_gate = load(None)  # default floor 18: top≈3 < 18 → tier-2 fires
        check(with_gate == ["body-answer"],
              f"confidence gate surfaces body-only answer over weak tier-1 hit (got {with_gate})")
        no_gate = load(0)       # floor 0: gate off, count<n can't fire → body-only never seen
        check("body-answer" not in no_gate,
              f"--tier2-floor 0 disables the gate — weak hit stands (got {no_gate})")
    finally:
        kg.BROOMVA_ROOT, kg.CATALOG_PATH, kg.ENTITIES_DIR, kg.STALE_WARN_SECONDS = orig


# ── Repo-native path resolution (BRO-1903) ────────────────────────────────────
# These use real `assert` (not check()) so they gate under pytest too — the
# check() harness only surfaces failures via main()'s exit code.

def _write_policy(repo, knowledge_block):
    ctl = repo / ".control"
    ctl.mkdir(parents=True, exist_ok=True)
    body = "gates:\n  - G1\n"
    if knowledge_block is not None:
        body += knowledge_block
    (ctl / "policy.yaml").write_text(body)


def _have_yaml():
    try:
        import yaml  # noqa: F401
        return True
    except ImportError:
        return False


def test_resolve_default_and_env():
    default_root = Path.home() / "broomva"
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)  # isolated — no .control/policy.yaml up-tree
        root, ent, cat = kg._resolve_knowledge_paths(start_dir=tmp, env={})
        assert root == default_root, f"default root (got {root})"
        assert ent == default_root / "research" / "entities"
        assert cat == default_root / "docs" / "knowledge-index.md"
        check(True, "default resolution → ~/broomva layout")

        root, _, cat = kg._resolve_knowledge_paths(start_dir=tmp, env={"BROOMVA_ROOT": "/opt/g"})
        assert root == Path("/opt/g") and cat == Path("/opt/g/docs/knowledge-index.md")
        check(True, "legacy BROOMVA_ROOT env honored")

        root, ent, cat = kg._resolve_knowledge_paths(
            start_dir=tmp, env={"KG_ROOT": "/r", "KG_ENTITIES_DIR": "/e", "KG_CATALOG": "/c.md"})
        assert (root, ent, cat) == (Path("/r"), Path("/e"), Path("/c.md"))
        check(True, "KG_* env overrides each key independently")


def test_resolve_config_block():
    if not _have_yaml():
        check(True, "config-block test skipped (PyYAML absent — soft dep)")
        return
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d).resolve() / "repo"  # resolve() so it matches the resolver's canonicalized path (macOS /var→/private/var)
        _write_policy(repo, "knowledge:\n  entities_dir: docs/research/entities\n"
                            "  catalog_path: docs/research/knowledge-index.md\n")
        deep = repo / "src" / "deep"
        deep.mkdir(parents=True)
        root, ent, cat = kg._resolve_knowledge_paths(start_dir=deep, env={})
        assert root == repo, f"block anchors root at repo (got {root})"
        assert ent == repo / "docs" / "research" / "entities"
        assert cat == repo / "docs" / "research" / "knowledge-index.md"
        check(True, "knowledge: block → docs/research (SRI opt-in shape)")

        root2, _, _ = kg._resolve_knowledge_paths(start_dir=deep, env={"BROOMVA_ROOT": "/ignored"})
        assert root2 == repo, "config block must beat BROOMVA_ROOT env"
        check(True, "config block beats BROOMVA_ROOT env")


def test_resolve_plants_knowledge_ignored():
    if not _have_yaml():
        check(True, "plants.knowledge test skipped (PyYAML absent)")
        return
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d).resolve() / "repo"
        _write_policy(repo, "plants:\n  knowledge:\n    entities_dir: SHOULD_NOT_BE_READ\n")
        root, ent, _ = kg._resolve_knowledge_paths(start_dir=repo, env={})
        assert root == Path.home() / "broomva", "nested plants.knowledge must not be read as config"
        assert "SHOULD_NOT_BE_READ" not in str(ent)
        check(True, "nested plants.knowledge ignored (backward-compat linchpin)")


def test_resolve_malformed_config_degrades():
    # A non-str value (YAML `entities_dir: 123` → int) or a typo'd key must NOT
    # crash the module at import — it degrades to the default / env root.
    if not _have_yaml():
        check(True, "malformed-config test skipped (PyYAML absent)")
        return
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d).resolve() / "repo"
        _write_policy(repo, "knowledge:\n  entities_dir: 123\n")  # int, not a str
        root, ent, _ = kg._resolve_knowledge_paths(start_dir=repo, env={})
        assert root == Path.home() / "broomva", "non-str value must degrade to default (no crash)"
        assert ent == Path.home() / "broomva" / "research" / "entities"
        check(True, "non-str knowledge value degrades to default (no import crash)")

        _write_policy(repo, "knowledge:\n  entities_dirr: docs/research/entities\n")  # typo key
        root2, _, _ = kg._resolve_knowledge_paths(start_dir=repo, env={"BROOMVA_ROOT": "/env/root"})
        assert root2 == Path("/env/root"), "typo-only block must not hijack root off env"
        check(True, "typo-only block does not hijack root")


def main():
    for fn in (test_tokenize, test_score_and_trace, test_terms_expansion_dedupe,
               test_hub_tiebreak, test_parse_catalog, test_alias_scoring,
               test_parse_tolerates_space_bearing_score, test_cmd_load_integration,
               test_tier2_confidence_trigger,
               test_resolve_default_and_env, test_resolve_config_block,
               test_resolve_plants_knowledge_ignored, test_resolve_malformed_config_degrades):
        fn()
    print()
    if _failures:
        print(f"FAILED — {len(_failures)} assertion(s):")
        for m in _failures:
            print(f"  - {m}")
        sys.exit(1)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
