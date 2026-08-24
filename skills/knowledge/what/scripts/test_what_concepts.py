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


def test_scrub_is_linear_on_a_long_slash_free_token():
    """A pasted JWT or hash list must not stall the run (was 16s via `\\S*/\\S*`)."""
    import time
    start = time.monotonic()
    wc.scrub("A" * 200_000, keep_code=False)
    assert time.monotonic() - start < 1.0


def test_scrub_keeps_hyphenated_prose_but_drops_path_and_url_tokens():
    out = wc.scrub("the expiry-aware-lease at https://x.dev/a and src/mod.py held", keep_code=False)
    assert "expiry-aware-lease" in out
    assert "x.dev" not in out and "mod.py" not in out


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


def test_camelcase_primitive_name_is_suppressed_too():
    """A multi-hump name would otherwise be re-extracted as a separate CamelCase row."""
    found = wc.extract_terms("Ran DeepChain (P14) then DeepChain again.")
    assert found.get("DeepChain (P14)") == "primitive"
    assert "DeepChain" not in found, "the bare CamelCase name must not double as its own row"


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


def test_harness_tool_input_keys_are_dropped():
    """Under --include-tools the mined text is code, and these flood the inventory."""
    for key in ("replace_all", "is_file", "file_path", "subagent_type", "tool_use_id"):
        assert wc.is_noise(key, "snake", wc.STOPWORDS, set()), key


def test_harness_keys_are_dropped_end_to_end_with_tools_included(tmp_path: Path):
    p = tmp_path / "t.jsonl"
    p.write_text(jsonl([{
        "type": "assistant", "uuid": "a1",
        "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Applied the edit."},
            {"type": "tool_use", "id": "t1", "name": "Edit",
             "input": {"replace_all": True, "file_path": "/x/y.py",
                       "new_string": "replace_all replace_all file_path file_path "
                                     "expiry-aware-lease guards expiry-aware-lease"}},
        ]},
    }]), encoding="utf-8")
    turns = wc.load_transcript(p, include_tools=True, include_sidechains=False)
    terms = {c.term for c in wc.build_inventory(turns, {}, {}, {})}
    assert "expiry-aware-lease" in terms
    assert not ({"replace_all", "file_path", "new_string"} & terms), terms


def test_shouted_status_labels_are_dropped():
    """Only labels the extractor can actually emit.

    `BLOCKER`/`CRITICAL`/`IMPORTANT` were asserted here on an unreachable path:
    ACRONYM caps total length at 6, so they are never extracted and their
    stopword entries could never fire. They have been removed from STOPWORDS.
    """
    for label in ("FAIL", "MAJOR", "WARN", "SKIP"):
        assert label in wc.extract_terms(f"{label} and {label} again"), label
        assert wc.is_noise(label, "acronym", wc.STOPWORDS, set()), label
    for unreachable in ("BLOCKER", "CRITICAL", "IMPORTANT"):
        assert unreachable not in wc.extract_terms(f"{unreachable} {unreachable}"), unreachable


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
    assert wc.is_noise("re-entrancy", "kebab", wc.STOPWORDS, set())
    assert not wc.is_noise("re-entrancy", "kebab", wc.STOPWORDS, set(), coverage="grounded")
    assert wc.is_noise("MAJOR", "acronym", wc.STOPWORDS, set())
    assert not wc.is_noise("MAJOR", "acronym", wc.STOPWORDS, set(), coverage="grounded")


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


def test_frequency_cannot_outrank_needing_an_explanation_even_when_both_are_agent_introduced(kg):
    """A term repeated 200 times but already glossed must lose to a rare, unexplained one.

    This is the whole point of the ranking: /what leads with what blocks
    understanding, not with what the session said most often.
    """
    entities, aliases, prims = kg
    # No human turn: BOTH terms are agent-introduced, so the only difference is
    # frequency vs never-glossed. The earlier fixture leaked the loud term into the
    # human turn, which stripped its +3 bonus and made the test pass for the wrong
    # reason — flipping that one line inverted the result.
    loud = " ".join(["chattyterm-token"] * 500)
    turns = [wc.Turn("agent", f"A chattyterm-token is a token. {loud} "
                              "Also dottyback-widget and dottyback-widget.")]
    ranked = [c.term for c in wc.build_inventory(turns, entities, aliases, prims)]
    assert ranked.index("dottyback-widget") < ranked.index("chattyterm-token"), ranked


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


def test_equal_scores_break_ties_by_term_not_by_appearance_order(kg):
    """Without an explicit tie-break the order would leak the order of appearance."""
    entities, aliases, prims = kg
    turns = [wc.Turn("agent", "zeta-token zeta-token mid-token-x mid-token-x alpha-token alpha-token")]
    ranked = [c.term for c in wc.build_inventory(turns, entities, aliases, prims)]
    assert len({c for c in ranked}) == 3
    assert ranked == sorted(ranked), f"equal scores must sort by term, got {ranked}"


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
    """Two DISTINCT partial hits on the same entity must stay two rows.

    The earlier fixture used bare lowercase words, which no extraction pattern
    matches, so the inventory had one row and the assertion compared a list to
    itself. These terms are really extracted and really both classify `partial`.
    """
    entities, aliases, prims = kg
    turns = [wc.Turn("agent", "stability-margin stability-margin and stability-window stability-window")]
    inv = wc.build_inventory(turns, entities, aliases, prims)
    assert len(inv) == 2, [c.term for c in inv]
    assert {c.coverage for c in inv} == {"partial"}, [(c.term, c.coverage) for c in inv]
    merged = wc.dedupe(inv)
    assert len(merged) == 2, [c.term for c in merged]


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
    assert "Bookkeeping (P6) candidates (score before filing)" in out
    assert "5/9" in out, "the report must carry the scoring gate, not a file-everything order"
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


# --------------------------------------------------------------------------
# P20 round-1 regressions — every test below pins a defect the review found
# --------------------------------------------------------------------------

def test_slash_command_is_recognised_in_the_xml_envelope_form():
    """Claude Code records `/what` as XML, not as the typed text.

    Matching only the raw form made the whole since-last-what scope inert in
    production while every offline test stayed green.
    """
    xml = ("<command-name>/what</command-name>\n"
           "            <command-message>what</command-message>\n"
           "            <command-args></command-args>")
    assert wc.is_what_invocation(xml)
    assert wc.is_what_invocation("/what")
    assert wc.is_what_invocation("  /what --scope session")


def test_other_slash_commands_are_not_what_markers():
    for other in ("/effort", "/compact", "/checkit", "/whatever"):
        env = f"<command-name>{other}</command-name>\n<command-message>x</command-message>"
        assert not wc.is_what_invocation(env), other
    assert not wc.is_what_invocation("/whatever")


def test_scope_uses_the_previous_marker_when_the_last_one_is_the_live_invocation():
    """The `/what` firing now is the final turn; slicing after it yields nothing.

    "Everything since you last asked" means the slice opens at the PREVIOUS marker.
    """
    turns = [
        wc.Turn("human", "/what"), wc.Turn("agent", "first explanation"),
        wc.Turn("human", "keep going"), wc.Turn("agent", "more work"),
        wc.Turn("human", "<command-name>/what</command-name>"),
    ]
    sliced, scope = wc.slice_scope(turns, "auto")
    assert scope == "since-last-what"
    assert [t.text for t in sliced] == ["first explanation", "keep going", "more work"]


def test_scope_is_session_when_the_live_invocation_is_the_only_marker():
    turns = [wc.Turn("agent", "did work"), wc.Turn("human", "<command-name>/what</command-name>")]
    assert wc.slice_scope(turns, "auto")[1] == "session"


def test_catalog_parses_em_dash_status_and_trailing_score_metadata():
    """43 of 895 live entities were invisible, so real pages read `ungrounded`."""
    text = (
        "#### em-dash-status [concept·—]\nclaim a\npath: concept/em-dash-status.md\n\n"
        "#### scored-entity [pattern·candidate] · score 7/9\nclaim b\npath: pattern/scored-entity.md\n\n"
        "#### _tags [_root·—]\nclaim c\npath: _tags.md\n"
    )
    entities, _ = wc.parse_catalog(text)
    assert set(entities) == {"em-dash-status", "scored-entity", "_tags"}
    assert entities["scored-entity"].claim == "claim b"


def test_scoring_constants_guarantee_the_ranking_invariant():
    """The headline claim is arithmetic, so assert it on the constants themselves."""
    need = wc.UNDEFINED_BONUS + (wc.COVERAGE_WEIGHT["ungrounded"] - wc.COVERAGE_WEIGHT["grounded"])
    assert need > wc.FREQ_CAP, f"{need} must exceed the max frequency advantage {wc.FREQ_CAP}"


def test_a_never_glossed_ungrounded_term_wins_at_any_frequency(kg):
    entities, aliases, prims = kg
    for n in (2, 15, 60, 500):
        loud = " ".join(["stability-budget"] * n)
        turns = [wc.Turn("agent", f"A stability-budget is the margin. {loud} "
                                  "quietterm-beta and quietterm-beta.")]
        ranked = [c.term for c in wc.build_inventory(turns, entities, aliases, prims)]
        assert ranked.index("quietterm-beta") < ranked.index("stability-budget"), (n, ranked)


def test_definitional_does_not_fire_on_a_longer_hyphenated_sibling():
    text = "gate-chain-v2 shipped. gate-chain held. gate-chain again."
    assert not wc.definitional(text, "gate-chain")
    assert not wc.definitional("we ran cross-review-gate twice", "cross-review")
    assert not wc.definitional("the gate-chain held", "gate")


def test_definitional_still_fires_on_a_real_gloss():
    assert wc.definitional("A gate-chain — the ordered set of gates", "gate-chain")
    assert wc.definitional("gate-chain: the ordered set", "gate-chain")
    assert wc.definitional("A gate-chain is the ordered set", "gate-chain")


def test_acronym_counts_inside_a_hyphenated_compound():
    """`RCS` in `RCS-based` is a use; the strict guard scored it 0 and dropped it."""
    text = "RCS-based here, RCS-based there, RCS-based everywhere."
    assert wc.count_uses(text, "RCS", "acronym") == 3
    assert "RCS" in {c.term for c in wc.build_inventory([wc.Turn("agent", text)], {}, {}, {})}


def test_kebab_does_not_count_inside_a_longer_compound():
    assert wc.count_uses("cross-review here and cross-review-gate there", "cross-review", "kebab") == 1


def test_every_extracted_term_recounts_to_at_least_one(kg):
    """Extraction and the recount must agree, or terms vanish with no trace."""
    entities, aliases, prims = kg
    prose = ("RCS-based work on the expiry-aware-lease. Applied Cross-Review\n(P20) twice. "
             "HttpClient and reducer_noop_check and EGRI here. Bookkeeping(P6) too.")
    text = wc.scrub(prose, keep_code=False)
    for term, kind in wc.extract_terms(text).items():
        assert wc.count_uses(text, term, kind) >= 1, f"{term!r} ({kind}) extracted but recounts to 0"


def test_line_wrapped_primitive_survives_the_recount():
    turns = [wc.Turn("agent", "Applied Cross-Review\n(P20) here. Cross-Review\n(P20) there.")]
    assert "Cross-Review (P20)" in {c.term for c in wc.build_inventory(turns, {}, {}, {})}


def test_dedupe_recomputes_score_from_the_merged_use_count(kg):
    entities, aliases, prims = kg
    turns = [wc.Turn("agent", "RCS is central. RCS again. recursive-controlled-system "
                              "underpins it, recursive-controlled-system indeed.")]
    merged = wc.dedupe(wc.build_inventory(turns, entities, aliases, prims))
    row = next(c for c in merged if c.entity_path == "concept/recursive-controlled-system.md")
    assert row.uses == 4
    assert row.score == wc.score_concept(4, row.agent_introduced, row.defined_inline,
                                         row.kind, row.coverage)


def test_partial_tier_fires_on_a_shared_slug_segment(kg):
    entities, aliases, prims = kg
    g = wc.classify("stability-margin", entities, aliases, prims)
    assert g.coverage == "partial" and g.path == "concept/stability-budget.md"


def test_partial_tier_ignores_short_generic_segments(kg):
    entities, aliases, prims = kg
    assert wc.classify("the-gate-loop", entities, aliases, prims).coverage == "ungrounded"


def test_coverage_weight_separates_ungrounded_from_grounded():
    """"Ungrounded is the highest-value row" must be a scored fact, not a slogan."""
    a = wc.score_concept(3, True, False, "kebab", "ungrounded")
    b = wc.score_concept(3, True, False, "kebab", "grounded")
    c = wc.score_concept(3, True, False, "kebab", "partial")
    assert a > c > b, (a, c, b)


def test_kind_weight_ranks_a_primitive_above_a_bare_snake_identifier():
    p = wc.score_concept(3, True, False, "primitive", "ungrounded")
    k = wc.score_concept(3, True, False, "kebab", "ungrounded")
    s = wc.score_concept(3, True, False, "snake", "ungrounded")
    assert p > k > s, (p, k, s)


def test_dedupe_keeps_the_best_row_not_the_first():
    """Two surfaces of one entity: the higher-scoring row must be the survivor."""
    low = wc.Concept("RCS", "acronym", 2, True, True, "grounded",
                     "concept/recursive-controlled-system.md", "claim", 4.0)
    high = wc.Concept("recursive-controlled-system", "kebab", 2, True, False, "grounded",
                      "concept/recursive-controlled-system.md", "claim", 9.0)
    merged = wc.dedupe([low, high])
    assert len(merged) == 1
    assert merged[0].term == "recursive-controlled-system", merged[0].term


def test_dedupe_output_is_totally_ordered_on_equal_scores():
    """dedupe's own sort is what the CLI emits; build_inventory's is not enough."""
    def mk(term):
        return wc.Concept(term, "kebab", 2, True, False, "ungrounded", None, None, 7.0)
    merged = wc.dedupe([mk("zeta-token"), mk("mid-token-x"), mk("alpha-token")])
    assert [c.term for c in merged] == sorted(c.term for c in merged)


def test_partial_tier_requires_a_long_shared_segment(kg):
    """A 5-char segment like `skill` matches half the graph and means nothing."""
    entities, aliases, prims = kg          # holds `linked-skill-inheritance`
    assert wc.classify("skill-gate", entities, aliases, prims).coverage == "ungrounded"
    assert wc.classify("inheritance-gate", entities, aliases, prims).coverage == "partial"


# --------------------------------------------------------------------------
# BRO-2129 precision round
# --------------------------------------------------------------------------

def test_generic_tails_are_demoted_not_deleted():
    """The suffix rule scores, it does not filter.

    A filter here could only ever fire on `ungrounded` terms — the un-filed
    coinages the skill exists to surface — so it would delete exactly its own
    highest-value rows. Demotion keeps them visible and sinks the filler.
    """
    for term in ("audit-time", "build-time", "cache-first", "root-level", "dev-like",
                 "long-lived", "repo-root", "role-aware", "free-form", "server-side",
                 "prose-only", "cross-model", "needs-you"):
        assert wc.has_generic_tail(term, "kebab"), term
        assert not wc.is_noise(term, "kebab", wc.STOPWORDS, set()), f"{term} must survive"
    generic = wc.score_concept(4, True, False, "kebab", "ungrounded", "audit-time")
    real = wc.score_concept(4, True, False, "kebab", "ungrounded", "expiry-aware-lease")
    assert real > generic, (real, generic)


def test_a_real_coinage_with_a_generic_tail_still_appears():
    """`threat-model` and `sell-side` are vocabulary, not filler. Demoted, not gone."""
    # `real-time` is deliberately absent: it is an explicit STOPWORDS entry, which
    # is a stronger statement than "generic tail" and is meant to remove it.
    for term in ("threat-model", "sell-side", "usage-based", "io-bound", "world-model"):
        turns = [wc.Turn("agent", f"the {term} matters. {term} again.")]
        assert term in {c.term for c in wc.build_inventory(turns, {}, {}, {})}, term


def test_generic_tail_penalty_only_applies_to_ungrounded_terms():
    a = wc.score_concept(4, True, False, "kebab", "grounded", "audit-time")
    b = wc.score_concept(4, True, False, "kebab", "grounded", "expiry-aware-lease")
    assert a == b, "a grounded term must not be penalised for its tail"


def test_generic_tail_is_two_segments_only():
    """Two segments only; a wider variant was tried and reverted."""
    for term in ("audit-time", "cache-first", "dev-like", "root-level"):
        assert wc.has_generic_tail(term, "kebab"), term
    for term in ("not-cache-first", "ready-at-boot-time", "end-user-facing"):
        assert not wc.has_generic_tail(term, "kebab"), term


def test_a_noun_tail_is_never_generic_however_long():
    for term in ("expiry-aware-lease", "gate-chain", "self-hosting-vacuous-pass",
                 "grounded-vs-ungrounded-improvement"):
        assert not wc.has_generic_tail(term, "kebab"), term


def test_suffix_stoplist_keeps_noun_tailed_compounds():
    """`-table`/`-room`/`-layer`/`-contractor` name things; they must survive."""
    # `counter-metric` is deliberately absent: `counter-` is in PREFIX_SEGMENTS, so
    # it is prefix-filtered unless the graph knows it.
    #
    # This asserts on has_generic_tail, not is_noise. is_noise contains no suffix
    # logic at all, so the earlier version held identically for `audit-time` — the
    # exact term its docstring says must be treated differently — and adding
    # `table`/`room`/`layer` to SUFFIX_SEGMENTS left the whole suite green.
    for term in ("cap-table", "clean-room", "control-layer", "independent-contractor",
                 "disguised-employment", "force-graph", "cost-per-node"):
        assert not wc.is_noise(term, "kebab", wc.STOPWORDS, set()), term
        assert not wc.has_generic_tail(term, "kebab"), f"{term} must not read as generic"
    assert wc.has_generic_tail("audit-time", "kebab"), "control: a real generic tail"


def test_partial_bypasses_shape_rules_but_never_the_stoplist():
    """Partial is ONE shared >=6-char segment — weak evidence.

    Letting it bypass the stoplist silently disabled entries, including the
    tool-schema keys the stoplist exists to remove.
    """
    assert wc.is_noise("re-entrancy", "kebab", wc.STOPWORDS, set())
    assert not wc.is_noise("re-entrancy", "kebab", wc.STOPWORDS, set(), coverage="partial")
    for key in ("new_string", "old_string", "run_in_background", "file_path", "agents"):
        assert wc.is_noise(key, "snake", wc.STOPWORDS, set(), coverage="partial"), key
    assert not wc.is_noise("new_string", "snake", wc.STOPWORDS, set(), coverage="grounded")


def test_partial_coverage_is_exempt_end_to_end():
    """Uses a term the shape rules WOULD drop, so deleting the exemption fails.

    The earlier version picked `append-only`, which clears `is_noise` on shape
    alone — so it passed with the exemption removed and tested nothing.
    """
    text = "#### entrancy-guard [pattern·entity]\nclaim\npath: pattern/entrancy-guard.md\n"
    entities, aliases = wc.parse_catalog(text)
    # `re-entrancy` is a two-segment compound with the `re-` prefix: dropped by the
    # shape heuristics unless partial coverage exempts it.
    assert wc.is_noise("re-entrancy", "kebab", wc.STOPWORDS, set())
    turns = [wc.Turn("agent", "the re-entrancy bug bit us. re-entrancy again.")]
    assert "re-entrancy" in {c.term for c in wc.build_inventory(turns, entities, aliases, {})}


def test_quoted_markdown_tables_are_not_mined():
    """Quoting another session's inventory made every term in it look new here."""
    prose = ("Results below.\n"
             "| # | Term | Uses |\n"
             "|---|---|---|\n"
             "| 1 | `zzz-contamination` | 9 |\n"
             "| 2 | `yyy-contamination` | 7 |\n"
             "That is the table.")
    out = wc.scrub(prose, keep_code=False)
    assert "zzz-contamination" not in out
    assert "yyy-contamination" not in out
    assert "Results below." in out and "That is the table." in out


def test_markdown_punctuation_no_longer_hides_a_path_suffix():
    """A backticked filename kept its stem, so `SKILL.md` surfaced as `SKILL`."""
    for src in ("see `SKILL.md` now", "see SKILL.md now", "(see `loop-prompt.md`)",
                "**`README.md`**"):
        out = wc.scrub(src, keep_code=False)
        assert "SKILL" not in out and "loop-prompt" not in out and "README" not in out, src


def test_filename_stems_do_not_enter_the_inventory():
    turns = [wc.Turn("agent", "Edit `loop-prompt.md` then `loop-prompt.md` again.")]
    assert wc.build_inventory(turns, {}, {}, {}, min_freq=1) == []


def test_table_rows_are_never_scrubbed_from_human_turns():
    """A human pasting a spec table must not make those terms agent-introduced."""
    table = "| Field | Note |\n|---|---|\n| disguised-employment | flag it |"
    turns = [wc.Turn("human", table),
             wc.Turn("agent", "disguised-employment is the exposure. "
                              "disguised-employment again, disguised-employment.")]
    row = next(c for c in wc.build_inventory(turns, {}, {}, {})
               if c.term == "disguised-employment")
    assert row.agent_introduced is False, "the human said it inside a table"


def test_agent_authored_tables_are_still_scrubbed():
    turns = [wc.Turn("agent", "| # | Term |\n|---|---|\n| 1 | `zzz-widget` |\n"
                              "| 2 | `zzz-widget` |")]
    assert "zzz-widget" not in {c.term for c in wc.build_inventory(turns, {}, {}, {}, min_freq=1)}


def test_harness_stopwords_are_documented_and_live():
    """The seven added in the precision round. Inert once `partial` bypassed them."""
    # `session` and `prompts` are 7 chars; ACRONYM caps at 6 and no other pattern
    # emits a bare lowercase word, so they were dead entries and are gone. Every
    # entry asserted here is reachable: the (term, kind) pair below is one the
    # extractor can really produce.
    for w in ("skill", "skills", "agent", "agents", "prompt"):
        assert w in wc.STOPWORDS, w
        assert w.upper() in wc.extract_terms(f"{w.upper()} and {w.upper()} again"), w
        assert wc.is_noise(w.upper(), "acronym", wc.STOPWORDS, set(), coverage="partial"), w
    for dead in ("session", "prompts"):
        assert dead not in wc.STOPWORDS, f"{dead} is unreachable; do not re-add it"


def test_table_scrub_keeps_prose_that_merely_contains_a_pipe():
    """Over-breadth guard: only a full `| ... |` row is a table row."""
    out = wc.scrub("run a | b to pipe it, and shell-pipeline shell-pipeline", keep_code=False)
    assert "shell-pipeline" in out
    assert "pipe" in out


def test_suffix_list_excludes_nouns_that_name_things():
    """Over-breadth guard: widening the list to real nouns must break this."""
    for tail_noun in ("expiry-aware-lease", "gate-chain", "error-budget",
                      "trust-boundary", "attack-surface", "context-window"):
        assert not wc.has_generic_tail(tail_noun, "kebab"), tail_noun


def test_agent_introduced_bonus_decides_the_ranking():
    """The skill's headline signal had no test and no mutation pinning its weight.

    Nothing asserted that the field changes the ORDER, so zeroing the bonus was
    green everywhere.
    """
    assert wc.AGENT_INTRODUCED_BONUS > 0
    mine = wc.score_concept(4, True, False, "kebab", "ungrounded", "shadow-lease")
    theirs = wc.score_concept(4, False, False, "kebab", "ungrounded", "quorum-drift")
    assert mine > theirs, (mine, theirs)
    # and it must survive a frequency deficit, or the signal is decorative
    loud_theirs = wc.score_concept(500, False, False, "kebab", "ungrounded", "quorum-drift")
    assert mine > loud_theirs, (mine, loud_theirs)


def test_generic_tail_applies_to_snake_case_too():
    """camel was pinned last round; the identical snake escape was not, and
    `dedupe` recovers the penalty from whichever surface scores highest."""
    assert wc.has_generic_tail("build_time", "snake")
    assert not wc.has_generic_tail("cache_layer", "snake")
    penalised = wc.score_concept(4, True, False, "snake", "ungrounded", "build_time")
    plain = wc.score_concept(4, True, False, "snake", "ungrounded", "cache_layer")
    assert penalised < plain, (penalised, plain)


def test_generic_technology_acronyms_stay_stoplisted():
    """These are industry vocabulary, not this workspace's jargon."""
    for acronym in ("LLM", "MCP", "SDK", "API", "SSH", "DNS"):
        assert wc.is_noise(acronym, "acronym", wc.STOPWORDS, set()), acronym


def test_camelcase_surface_cannot_escape_the_generic_tail_penalty():
    """`dedupe` keeps the highest-scoring surface, so a kind-gated penalty let
    spelling a term both ways recover the full demotion."""
    assert wc.has_generic_tail("WorldModel", "camel")
    assert not wc.has_generic_tail("CapTable", "camel")
    kebab = wc.score_concept(4, True, False, "kebab", "ungrounded", "world-model")
    turns = [wc.Turn("agent", "world-model world-model WorldModel WorldModel")]
    merged = wc.dedupe(wc.build_inventory(turns, {}, {}, {}))
    row = next(c for c in merged if wc.normalize(c.term) == "world-model")
    assert row.score <= kebab, f"dedupe recovered the penalty: {row.score} vs {kebab}"


def test_stoplist_holds_no_unreachable_entries():
    """Every acronym-shaped stopword must be one the extractor can emit.

    ACRONYM caps total length at 6. Longer bare-word entries are decoration and
    were silently accumulating (`session`, `prompts`, `blocker`, `critical`,
    `important`).
    """
    too_long = sorted(w for w in wc.STOPWORDS
                      if w.isalpha() and len(w) > 6 and "-" not in w and "_" not in w)
    assert not too_long, f"unreachable acronym-shaped stopwords: {too_long}"


def test_partial_coverage_does_not_rescue_identifier_shapes():
    """Grounding says a term is vocabulary; it does not say a ticket id is an idea.

    The exemption was added to rescue near-miss vocabulary from the English-shape
    rules and was sitting above the identifier filter purely by placement.
    """
    for ident in ("dispatch-bro-1945", "round-2", "board-m3", "run-264"):
        assert wc.is_noise(ident, "kebab", wc.STOPWORDS, set()), ident
        assert wc.is_noise(ident, "kebab", wc.STOPWORDS, set(), coverage="partial"), ident
    # ...while still rescuing what it was added for
    assert not wc.is_noise("re-entrancy", "kebab", wc.STOPWORDS, set(), coverage="partial")
    # a stoplisted acronym stays stopped whatever its coverage
    assert wc.is_noise("MAJOR", "acronym", wc.STOPWORDS, set(), coverage="partial")


def test_table_scrub_survives_include_tools():
    """`--include-tools` is about mining CODE; nesting the scrub under it silently
    disabled table scrubbing whenever that flag was passed."""
    table = "| # | Term |\n|---|---|\n| 1 | `zzz-widget` |\n| 2 | `zzz-widget` |"
    for keep_code in (False, True):
        assert "zzz-widget" not in wc.scrub(table, keep_code=keep_code), keep_code


def test_blockquoted_tables_are_scrubbed_too():
    quoted = "> | # | Term |\n> |---|---|\n> | 1 | `zzz-widget` |\n> | 2 | `zzz-widget` |"
    assert "zzz-widget" not in wc.scrub(quoted, keep_code=False)
