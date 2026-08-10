#!/usr/bin/env python3
"""Unit tests for what_concepts.py — the deterministic core of the `what` skill.

Run: python3 -m pytest scripts/test_what_concepts.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import what_concepts as wc  # noqa: E402


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

CATALOG = """---
generated: 2026-08-10T00:00:00+00:00
---

# Knowledge Index

#### recursive-controlled-system [concept·entity]
A system whose controller is itself a controlled system at the next level up.
→ stability-budget · ← bstack-engine · #control-theory · aka: RCS, recursive control system · src: paper
path: concept/recursive-controlled-system.md

#### stability-budget [concept·entity]
The shared stability margin lambda_i must stay > 0 at every RCS level.
→ egri-meta-controller · #control-theory · src: paper
path: concept/stability-budget.md

#### linked-skill-inheritance [pattern·candidate]
Inherit external skill corpora by live symlink resolved from a declared source registry.
#bstack · aka: symlink inheritance · src: conversation
path: pattern/linked-skill-inheritance.md
"""

CLAUDE_MD = """# Workspace

**Short-name index** (canonical numbering): Bridge (P1) · Gate (P2) · Bookkeeping (P6) · Cross-Review (P20).

| # | Primitive | What it binds you to |
|---|---|---|
| P1 | **Bridge** — Conversation Bridge | Stop hook writes session. |
| P9 | **Wait** — CI Watcher | Never sleep on CI. |
"""


def jsonl(rows: list[dict]) -> str:
    return "\n".join(json.dumps(r) for r in rows) + "\n"


def human(text: str, **extra) -> dict:
    return {"type": "user", "uuid": f"u-{abs(hash(text)) % 9999}",
            "message": {"role": "user", "content": text}, **extra}


def agent(text: str, **extra) -> dict:
    return {"type": "assistant", "uuid": f"a-{abs(hash(text)) % 9999}",
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}, **extra}


@pytest.fixture()
def catalog(tmp_path: Path) -> Path:
    p = tmp_path / "knowledge-index.md"
    p.write_text(CATALOG, encoding="utf-8")
    return p


@pytest.fixture()
def claude_md(tmp_path: Path) -> Path:
    p = tmp_path / "CLAUDE.md"
    p.write_text(CLAUDE_MD, encoding="utf-8")
    return p


@pytest.fixture()
def kg(catalog: Path, claude_md: Path):
    entities, aliases = wc.parse_catalog(catalog.read_text())
    primitives = wc.parse_primitives(claude_md.read_text())
    return entities, aliases, primitives


# --------------------------------------------------------------------------
# Path resolution
# --------------------------------------------------------------------------

def test_project_slug_flattens_separators():
    assert wc.project_slug(Path("/Users/broomva/broomva")) == "-Users-broomva-broomva"
    assert wc.project_slug(Path("/Users/broomva/.buzz")) == "-Users-broomva--buzz"


def test_resolve_transcript_walks_up_from_a_nested_worktree(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    nested = repo / "a" / "b" / "c"
    nested.mkdir(parents=True)
    projects = tmp_path / "projects"
    pdir = projects / wc.project_slug(repo)
    pdir.mkdir(parents=True)
    (pdir / "session.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects))

    got = wc.resolve_transcript(None, None, nested)
    assert got is not None and got.name == "session.jsonl"


def test_resolve_transcript_returns_none_when_nothing_matches(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(tmp_path / "empty"))
    assert wc.resolve_transcript(None, None, tmp_path) is None


def test_resolve_transcript_picks_the_newest_jsonl(tmp_path: Path):
    d = tmp_path / "proj"
    d.mkdir()
    old, new = d / "old.jsonl", d / "new.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    new.write_text("{}\n", encoding="utf-8")
    import os
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))
    assert wc.resolve_transcript(None, str(d), tmp_path).name == "new.jsonl"


def test_resolve_catalog_prefers_env_then_falls_back(tmp_path: Path, monkeypatch):
    cat = tmp_path / "cat.md"
    cat.write_text("x", encoding="utf-8")
    monkeypatch.setenv("KG_CATALOG", str(cat))
    assert wc.resolve_catalog(None, tmp_path) == cat
    monkeypatch.setenv("KG_CATALOG", str(tmp_path / "missing.md"))
    assert wc.resolve_catalog(None, tmp_path) is None


def test_resolve_catalog_reads_policy_knowledge_block(tmp_path: Path, monkeypatch):
    pytest.importorskip("yaml")
    monkeypatch.delenv("KG_CATALOG", raising=False)
    root = tmp_path / "ws"
    (root / ".control").mkdir(parents=True)
    cat = root / "custom" / "index.md"
    cat.parent.mkdir()
    cat.write_text("x", encoding="utf-8")
    (root / ".control" / "policy.yaml").write_text(
        "knowledge:\n  catalog_path: custom/index.md\n", encoding="utf-8"
    )
    assert wc.resolve_catalog(None, root) == cat


def test_policy_knowledge_block_survives_malformed_yaml(tmp_path: Path):
    p = tmp_path / "policy.yaml"
    p.write_text("knowledge: [oops\n  ::::", encoding="utf-8")
    assert wc.policy_knowledge_block(p) == {}


# --------------------------------------------------------------------------
# Transcript parsing
# --------------------------------------------------------------------------

def test_tool_results_are_never_mined_as_human_turns(tmp_path: Path):
    """A `user` row whose content is a list is tool plumbing, not an utterance."""
    p = tmp_path / "t.jsonl"
    p.write_text(jsonl([
        human("real question about stability-budget"),
        {"type": "user", "uuid": "x", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "quantum-entanglement everywhere"}
        ]}},
        agent("answer"),
    ]), encoding="utf-8")
    turns = wc.load_transcript(p, include_tools=False, include_sidechains=False)
    assert [t.role for t in turns] == ["human", "agent"]
    assert "quantum-entanglement" not in "".join(t.text for t in turns)


def test_thinking_blocks_are_skipped(tmp_path: Path):
    p = tmp_path / "t.jsonl"
    p.write_text(jsonl([{
        "type": "assistant", "uuid": "a1",
        "message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "secret-reasoning-token"},
            {"type": "text", "text": "visible prose"},
        ]},
    }]), encoding="utf-8")
    turns = wc.load_transcript(p, include_tools=False, include_sidechains=False)
    assert turns[0].text == "visible prose"


def test_tool_use_inputs_are_opt_in(tmp_path: Path):
    p = tmp_path / "t.jsonl"
    p.write_text(jsonl([{
        "type": "assistant", "uuid": "a1",
        "message": {"role": "assistant", "content": [
            {"type": "text", "text": "prose"},
            {"type": "tool_use", "id": "t", "name": "Write",
             "input": {"content": "expiry-aware-lease"}},
        ]},
    }]), encoding="utf-8")
    off = wc.load_transcript(p, include_tools=False, include_sidechains=False)
    on = wc.load_transcript(p, include_tools=True, include_sidechains=False)
    assert "expiry-aware-lease" not in off[0].text
    assert "expiry-aware-lease" in on[0].text


def test_sidechains_are_excluded_by_default(tmp_path: Path):
    p = tmp_path / "t.jsonl"
    p.write_text(jsonl([
        agent("main thread prose"),
        agent("subagent prose", isSidechain=True),
    ]), encoding="utf-8")
    assert len(wc.load_transcript(p, False, False)) == 1
    assert len(wc.load_transcript(p, False, True)) == 2


def test_malformed_lines_are_tolerated(tmp_path: Path):
    p = tmp_path / "t.jsonl"
    p.write_text("not json\n\n[1,2,3]\n" + jsonl([agent("survivor prose")]), encoding="utf-8")
    turns = wc.load_transcript(p, False, False)
    assert len(turns) == 1 and turns[0].text == "survivor prose"


def test_meta_rows_are_skipped(tmp_path: Path):
    p = tmp_path / "t.jsonl"
    p.write_text(jsonl([agent("kept"), agent("dropped", isMeta=True)]), encoding="utf-8")
    assert [t.text for t in wc.load_transcript(p, False, False)] == ["kept"]


# --------------------------------------------------------------------------
# Conversation markdown parsing
# --------------------------------------------------------------------------

def test_conversation_markdown_splits_on_role_headers(tmp_path: Path):
    p = tmp_path / "c.md"
    p.write_text(
        "# Log\n\n## User\nwhat did you do\n\n## Assistant\nI applied Cross-Review (P20).\n",
        encoding="utf-8",
    )
    turns = wc.load_conversation(p)
    assert [t.role for t in turns] == ["human", "agent"]
    assert "Cross-Review (P20)" in turns[1].text


def test_conversation_without_headers_degrades_to_one_agent_turn(tmp_path: Path):
    p = tmp_path / "c.md"
    p.write_text("just a wall of prose about stability-budget\n", encoding="utf-8")
    turns = wc.load_conversation(p)
    assert len(turns) == 1 and turns[0].role == "agent"


# --------------------------------------------------------------------------
# Scoping
# --------------------------------------------------------------------------

def test_scope_cuts_at_the_last_what_not_the_first():
    turns = [
        wc.Turn("human", "/what"), wc.Turn("agent", "first explanation"),
        wc.Turn("human", "keep going"), wc.Turn("agent", "more work"),
        wc.Turn("human", "/what again please"), wc.Turn("agent", "SECOND explanation"),
    ]
    sliced, scope = wc.slice_scope(turns, "auto")
    assert scope == "since-last-what"
    assert [t.text for t in sliced] == ["SECOND explanation"]


def test_scope_falls_back_to_session_without_a_marker():
    turns = [wc.Turn("human", "build it"), wc.Turn("agent", "done")]
    sliced, scope = wc.slice_scope(turns, "auto")
    assert scope == "session" and len(sliced) == 2


def test_scope_falls_back_when_what_is_the_final_turn():
    """Nothing followed the marker, so slicing would yield an empty inventory."""
    turns = [wc.Turn("agent", "did work"), wc.Turn("human", "/what")]
    sliced, scope = wc.slice_scope(turns, "auto")
    assert scope == "session" and len(sliced) == 2


def test_explicit_session_scope_ignores_the_marker():
    turns = [wc.Turn("human", "/what"), wc.Turn("agent", "after")]
    assert wc.slice_scope(turns, "session") == (turns, "session")


def test_what_marker_must_be_the_start_of_the_turn():
    turns = [wc.Turn("human", "tell me /what you think"), wc.Turn("agent", "after")]
    _, scope = wc.slice_scope(turns, "auto")
    assert scope == "session"


# --------------------------------------------------------------------------
# Term extraction
# --------------------------------------------------------------------------

def test_scrub_removes_fences_urls_and_paths():
    text = "prose ```\nfenced-token here\n``` https://x.dev/deep-link and docs/knowledge-index.md"
    out = wc.scrub(text, keep_code=False)
    assert "fenced-token" not in out
    assert "deep-link" not in out
    assert "knowledge-index" not in out
    assert "prose" in out


def test_keep_code_preserves_fenced_tokens():
    text = "prose ```\nfenced-token\n```"
    assert "fenced-token" in wc.scrub(text, keep_code=True)


def test_normalize_folds_camel_snake_and_parens():
    assert wc.normalize("Cross-Review (P20)") == "cross-review-p20"
    assert wc.normalize("HttpClient") == "http-client"
    assert wc.normalize("expiry_aware_lease") == "expiry-aware-lease"
    assert wc.normalize("  RCS ") == "rcs"


def test_named_primitive_suppresses_its_bare_forms():
    found = wc.extract_terms("We applied Bookkeeping (P6) and then P6 again, Bookkeeping style.")
    assert found.get("Bookkeeping (P6)") == "primitive"
    assert "Bookkeeping" not in found
    assert "P6" not in found


def test_bare_primitive_recognised_without_a_name():
    """Only P1-P20 are primitives. P21 may still surface, but never as one."""
    found = wc.extract_terms("Ran P20 then P9. P21 is not a primitive.")
    assert found.get("P20") == "primitive"
    assert found.get("P9") == "primitive"
    assert found.get("P21") != "primitive"
    assert found.get("P0") != "primitive"


def test_extraction_kinds():
    found = wc.extract_terms("The expiry-aware-lease in HttpClient used EGRI and reducer_noop_check.")
    assert found["expiry-aware-lease"] == "kebab"
    assert found["HttpClient"] == "camel"
    assert found["EGRI"] == "acronym"
    assert found["reducer_noop_check"] == "snake"


def test_stoplist_and_length_floors_drop_generic_terms():
    assert wc.is_noise("CI", "acronym", wc.STOPWORDS, set())
    assert wc.is_noise("read-only", "kebab", wc.STOPWORDS, set())
    assert wc.is_noise("a-b", "kebab", wc.STOPWORDS, set())        # under the 6-char floor
    assert not wc.is_noise("expiry-aware-lease", "kebab", wc.STOPWORDS, set())


def test_keep_term_overrides_the_stoplist():
    assert wc.is_noise("CI", "acronym", wc.STOPWORDS, set())
    assert not wc.is_noise("CI", "acronym", wc.STOPWORDS, {"ci"})


def test_shouted_status_labels_are_dropped():
    for label in ("FAIL", "BLOCKER", "MAJOR", "WARN"):
        assert wc.is_noise(label, "acronym", wc.STOPWORDS, set()), label


def test_english_prefix_compounds_are_dropped():
    for term in ("re-invoke", "auto-deleted", "non-blocking", "self-hosted"):
        assert wc.is_noise(term, "kebab", wc.STOPWORDS, set()), term


def test_prefix_filter_only_applies_to_two_segment_compounds():
    assert not wc.is_noise("self-hosting-vacuous-pass", "kebab", wc.STOPWORDS, set())
    assert not wc.is_noise("re-entrant-lock-guard", "kebab", wc.STOPWORDS, set())


def test_prefix_filter_does_not_eat_real_workspace_compounds():
    for term in ("cross-review", "expiry-aware-lease", "build-arc", "rule-of-two"):
        assert not wc.is_noise(term, "kebab", wc.STOPWORDS, set()), term


def test_numeric_final_segments_are_dropped_as_identifiers():
    for term in ("round-2", "board-m3", "bro-2107", "run-264"):
        assert wc.is_noise(term, "kebab", wc.STOPWORDS, set()), term
    assert wc.is_noise("slice_1", "snake", wc.STOPWORDS, set())


def test_grounding_rescues_a_term_the_heuristics_would_drop():
    """A term the knowledge graph names is real, whatever shape it has."""
    assert wc.is_noise("re-entrancy", "kebab", wc.STOPWORDS, set(), grounded=False)
    assert not wc.is_noise("re-entrancy", "kebab", wc.STOPWORDS, set(), grounded=True)
    assert wc.is_noise("MAJOR", "acronym", wc.STOPWORDS, set(), grounded=False)
    assert not wc.is_noise("MAJOR", "acronym", wc.STOPWORDS, set(), grounded=True)


def test_grounded_terms_survive_the_filter_end_to_end():
    """A catalog entry whose slug looks like an English prefix compound still lands."""
    text = "#### re-entrancy [concept·entity]\nclaim here\npath: concept/re-entrancy.md\n"
    entities, aliases = wc.parse_catalog(text)
    turns = [wc.Turn("agent", "The re-entrancy bug bit us. re-entrancy again.")]
    terms = {c.term for c in wc.build_inventory(turns, entities, aliases, {})}
    assert "re-entrancy" in terms


def test_definitional_detects_inline_glosses():
    assert wc.definitional("A shadow-lease is a lease that expires.", "shadow-lease")
    assert wc.definitional("shadow-lease — the expiring kind", "shadow-lease")
    assert wc.definitional("shadow-lease (an expiring lease)", "shadow-lease")
    assert not wc.definitional("We used shadow-lease twice. shadow-lease again.", "shadow-lease")


# --------------------------------------------------------------------------
# Catalog + primitive parsing
# --------------------------------------------------------------------------

def test_parse_catalog_extracts_slug_claim_path_and_aliases(catalog: Path):
    entities, aliases = wc.parse_catalog(catalog.read_text())
    assert set(entities) == {
        "recursive-controlled-system", "stability-budget", "linked-skill-inheritance"
    }
    e = entities["recursive-controlled-system"]
    assert e.etype == "concept" and e.status == "entity"
    assert e.claim.startswith("A system whose controller")
    assert e.path == "concept/recursive-controlled-system.md"
    assert aliases["rcs"] == "recursive-controlled-system"
    assert aliases["symlink-inheritance"] == "linked-skill-inheritance"


def test_parse_catalog_never_lets_an_alias_shadow_a_real_slug():
    text = (
        "#### alpha [concept·entity]\nclaim a\n"
        "#tag · aka: beta\npath: concept/alpha.md\n\n"
        "#### beta [concept·entity]\nclaim b\npath: concept/beta.md\n"
    )
    entities, aliases = wc.parse_catalog(text)
    assert "beta" in entities
    assert "beta" not in aliases


def test_parse_primitives_reads_both_the_index_line_and_the_table(claude_md: Path):
    prims = wc.parse_primitives(claude_md.read_text())
    assert prims["p1"] == "Bridge"
    assert prims["p6"] == "Bookkeeping"
    assert prims["p20"] == "Cross-Review"
    assert prims["p9"] == "Wait"  # table-only row


# --------------------------------------------------------------------------
# Grounding
# --------------------------------------------------------------------------

def test_classify_grounds_on_slug_alias_and_primitive(kg):
    entities, aliases, prims = kg
    g = wc.classify("stability-budget", entities, aliases, prims)
    assert g.coverage == "grounded" and g.path == "concept/stability-budget.md"

    g = wc.classify("RCS", entities, aliases, prims)
    assert g.coverage == "grounded" and g.key == "entity:recursive-controlled-system"

    g = wc.classify("Bookkeeping (P6)", entities, aliases, prims)
    assert g.coverage == "grounded" and g.key == "primitive:p6"
    assert "Bookkeeping" in g.claim


def test_classify_reports_ungrounded_for_unknown_terms(kg):
    entities, aliases, prims = kg
    g = wc.classify("dottyback-quantum-widget", entities, aliases, prims)
    assert g.coverage == "ungrounded" and g.path is None and g.key is None


def test_classify_reports_partial_on_a_slug_component(kg):
    entities, aliases, prims = kg
    g = wc.classify("stability", entities, aliases, prims)
    assert g.coverage == "partial" and g.path == "concept/stability-budget.md"


def test_classify_is_ungrounded_when_the_primitive_table_is_empty(kg):
    entities, aliases, _ = kg
    assert wc.classify("P6", entities, aliases, {}).coverage == "ungrounded"


# --------------------------------------------------------------------------
# Inventory + ranking
# --------------------------------------------------------------------------

def test_agent_introduced_is_false_when_the_human_used_the_term(kg):
    entities, aliases, prims = kg
    turns = [
        wc.Turn("human", "tell me about the expiry-aware-lease"),
        wc.Turn("agent", "The expiry-aware-lease matters. expiry-aware-lease again."),
    ]
    got = {c.term: c for c in wc.build_inventory(turns, entities, aliases, prims)}
    assert got["expiry-aware-lease"].agent_introduced is False


def test_agent_introduced_is_true_when_only_the_agent_used_it(kg):
    entities, aliases, prims = kg
    turns = [
        wc.Turn("human", "go"),
        wc.Turn("agent", "The expiry-aware-lease matters. expiry-aware-lease again."),
    ]
    got = {c.term: c for c in wc.build_inventory(turns, entities, aliases, prims)}
    assert got["expiry-aware-lease"].agent_introduced is True


def test_min_freq_excludes_single_mentions(kg):
    entities, aliases, prims = kg
    turns = [wc.Turn("agent", "mentioned-once here and repeated-term repeated-term")]
    terms = {c.term for c in wc.build_inventory(turns, entities, aliases, prims, min_freq=2)}
    assert "repeated-term" in terms
    assert "mentioned-once" not in terms


def test_undefined_agent_introduced_ungrounded_outranks_a_defined_grounded_term(kg):
    entities, aliases, prims = kg
    turns = [wc.Turn("agent",
                     "A stability-budget is the margin. stability-budget again. "
                     "We used dottyback-widget and dottyback-widget once more.")]
    ranked = wc.build_inventory(turns, entities, aliases, prims)
    order = [c.term for c in ranked]
    assert order.index("dottyback-widget") < order.index("stability-budget")


def test_frequency_cannot_outrank_needing_an_explanation(kg):
    """A term repeated 200 times but already glossed must lose to a rare, unexplained one.

    This is the whole point of the ranking: /what leads with what blocks
    understanding, not with what the session said most often.
    """
    entities, aliases, prims = kg
    loud = " ".join(["chattyterm-token"] * 200)
    turns = [
        wc.Turn("human", "chattyterm-token please"),          # human already owns it
        wc.Turn("agent", f"A chattyterm-token is a token. {loud} "
                         "Also dottyback-widget and dottyback-widget."),
    ]
    ranked = [c.term for c in wc.build_inventory(turns, entities, aliases, prims)]
    assert ranked.index("dottyback-widget") < ranked.index("chattyterm-token")


def test_frequency_contribution_is_capped(kg):
    entities, aliases, prims = kg
    def score_for(n):
        turns = [wc.Turn("agent", " ".join(["dottyback-widget"] * n))]
        return wc.build_inventory(turns, entities, aliases, prims)[0].score
    assert score_for(1000) == score_for(100)
    assert score_for(2) < score_for(100)


def test_ranking_is_deterministic_across_runs(kg):
    entities, aliases, prims = kg
    turns = [wc.Turn("agent", "alpha-token alpha-token beta-token beta-token gamma-token gamma-token")]
    runs = [[c.term for c in wc.build_inventory(turns, entities, aliases, prims)] for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_dedupe_merges_an_alias_into_its_slug_and_sums_uses(kg):
    entities, aliases, prims = kg
    turns = [wc.Turn("agent",
                     "RCS is central. RCS again. The recursive-controlled-system "
                     "underpins it, recursive-controlled-system indeed.")]
    merged = wc.dedupe(wc.build_inventory(turns, entities, aliases, prims))
    rcs_rows = [c for c in merged if c.entity_path == "concept/recursive-controlled-system.md"]
    assert len(rcs_rows) == 1
    assert rcs_rows[0].uses == 4


def test_dedupe_does_not_merge_two_different_primitives(kg):
    entities, aliases, prims = kg
    turns = [wc.Turn("agent", "Ran P20 then P20, and P9 twice: P9.")]
    merged = wc.dedupe(wc.build_inventory(turns, entities, aliases, prims))
    keys = {c.claim for c in merged}
    assert len(keys) == 2, f"P20 and P9 must stay distinct rows, got {keys}"


def test_dedupe_does_not_merge_unrelated_partial_hits(kg):
    entities, aliases, prims = kg
    turns = [wc.Turn("agent", "stability stability and budget-line budget-line")]
    merged = wc.dedupe(wc.build_inventory(turns, entities, aliases, prims))
    assert len({c.term for c in merged}) == len(merged)


def test_inventory_works_with_no_catalog_at_all():
    turns = [wc.Turn("agent", "expiry-aware-lease and expiry-aware-lease again")]
    got = wc.build_inventory(turns, {}, {}, {})
    assert got and all(c.coverage == "ungrounded" for c in got)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

BASE_META = {
    "source": "s", "scope": "session", "turns": 2, "agent_turns": 1,
    "human_turns": 1, "catalog": None,
}


def test_empty_inventory_renders_the_repitch_instruction():
    out = wc.render_markdown([], BASE_META)
    assert "re-pitch" in out


def test_render_flags_undefined_terms_and_lists_p6_candidates():
    concepts = [
        wc.Concept("dottyback-widget", "kebab", 4, True, False, "ungrounded", None, None, 9.0),
        wc.Concept("stability-budget", "kebab", 2, True, True, "grounded",
                   "concept/stability-budget.md", "the margin", 6.0),
    ]
    out = wc.render_markdown(concepts, BASE_META)
    assert "| NO |" in out              # undefined term flagged loudly
    assert "Bookkeeping (P6) filing candidates" in out
    assert "`dottyback-widget` (4 uses)" in out
    assert "**stability-budget** — the margin" in out


# --------------------------------------------------------------------------
# CLI end-to-end
# --------------------------------------------------------------------------

def test_cli_end_to_end_json(tmp_path: Path, catalog: Path, claude_md: Path, capsys):
    t = tmp_path / "t.jsonl"
    t.write_text(jsonl([
        human("do the work"),
        agent("Applied Bookkeeping (P6)."),
        human("/what"),
        agent("The expiry-aware-lease guards the tick. expiry-aware-lease again, "
              "and RCS matters, RCS indeed."),
    ]), encoding="utf-8")

    rc = wc.main([
        "--transcript", str(t), "--catalog", str(catalog),
        "--claude-md", str(claude_md), "--cwd", str(tmp_path), "--json",
    ])
    assert rc == wc.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["meta"]["scope"] == "since-last-what"
    assert payload["meta"]["entities_indexed"] == 3
    terms = {c["term"] for c in payload["concepts"]}
    assert "expiry-aware-lease" in terms
    # Bookkeeping (P6) lives BEFORE the /what marker, so the slice must exclude it.
    assert not any("P6" in t for t in terms)


def test_cli_missing_source_exits_1(tmp_path: Path):
    assert wc.main(["--transcript", str(tmp_path / "nope.jsonl")]) == wc.EXIT_NO_SOURCE
    assert wc.main(["--conversation", str(tmp_path / "nope.md")]) == wc.EXIT_NO_SOURCE
    assert wc.main(["--text", str(tmp_path / "nope.txt")]) == wc.EXIT_NO_SOURCE


def test_cli_bad_thresholds_exit_2():
    assert wc.main(["--text", "-", "--top", "0"]) == wc.EXIT_USAGE
    assert wc.main(["--text", "-", "--min-freq", "0"]) == wc.EXIT_USAGE


def test_cli_no_transcript_anywhere_exits_1(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(tmp_path / "none"))
    assert wc.main(["--cwd", str(tmp_path)]) == wc.EXIT_NO_SOURCE


def test_cli_top_truncates(tmp_path: Path, catalog: Path, claude_md: Path, capsys):
    t = tmp_path / "t.jsonl"
    blob = " ".join(f"widget{chr(97 + i)}-handle widget{chr(97 + i)}-handle" for i in range(20))
    t.write_text(jsonl([agent(blob)]), encoding="utf-8")
    wc.main(["--transcript", str(t), "--catalog", str(catalog), "--claude-md", str(claude_md),
             "--cwd", str(tmp_path), "--top", "3", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["concepts"]) == 3


def test_cli_text_source_from_file(tmp_path: Path, catalog: Path, claude_md: Path, capsys):
    p = tmp_path / "note.txt"
    p.write_text("expiry-aware-lease twice: expiry-aware-lease", encoding="utf-8")
    rc = wc.main(["--text", str(p), "--catalog", str(catalog), "--claude-md", str(claude_md),
                  "--cwd", str(tmp_path), "--json"])
    assert rc == wc.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert "expiry-aware-lease" in {c["term"] for c in payload["concepts"]}


def test_cli_markdown_output_has_a_table(tmp_path: Path, catalog: Path, claude_md: Path, capsys):
    p = tmp_path / "note.txt"
    p.write_text("expiry-aware-lease twice: expiry-aware-lease", encoding="utf-8")
    wc.main(["--text", str(p), "--catalog", str(catalog), "--claude-md", str(claude_md),
             "--cwd", str(tmp_path)])
    out = capsys.readouterr().out
    assert "| # | Term | Uses |" in out
    assert "`expiry-aware-lease`" in out
