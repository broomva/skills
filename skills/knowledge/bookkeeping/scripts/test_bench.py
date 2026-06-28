#!/usr/bin/env python3
"""Unit tests for the bookkeeping retrieval benchmark (BRO-1246).

Verifies the IR-metric math (Precision@k, Recall@k, MRR) on tiny synthetic
inputs with hand-computed expected values, plus the two-tier `retrieve()`
ranking and the end-to-end `run_bench` aggregation against a synthetic catalog.

stdlib-only; run:  python3 skills/bookkeeping/scripts/test_bench.py
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Import the module under test (scripts/ dir is this file's parent).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bookkeeping as bk  # noqa: E402


class TestPrecisionAtK(unittest.TestCase):
    def test_all_relevant(self):
        # 5 retrieved, all relevant → 5/5 = 1.0
        self.assertEqual(
            bk.precision_at_k(["a", "b", "c", "d", "e"], {"a", "b", "c", "d", "e"}, 5),
            1.0,
        )

    def test_one_relevant_of_five(self):
        # 1 hit in top-5 → 1/5 = 0.2 (the single-gold ceiling)
        self.assertAlmostEqual(
            bk.precision_at_k(["a", "x", "y", "z", "w"], {"a"}, 5), 0.2
        )

    def test_two_relevant_of_five(self):
        self.assertAlmostEqual(
            bk.precision_at_k(["a", "b", "y", "z", "w"], {"a", "b"}, 5), 0.4
        )

    def test_cutoff_truncates(self):
        # k=3: only first 3 counted; "c" beyond cutoff is ignored → 2/3
        self.assertAlmostEqual(
            bk.precision_at_k(["a", "b", "x", "c"], {"a", "b", "c"}, 3), 2 / 3
        )

    def test_empty_retrieved(self):
        self.assertEqual(bk.precision_at_k([], {"a"}, 5), 0.0)

    def test_k_zero(self):
        self.assertEqual(bk.precision_at_k(["a"], {"a"}, 0), 0.0)

    def test_relevant_beyond_k_not_counted(self):
        # Relevant item at rank 6 with k=5 → 0 hits in window
        self.assertEqual(
            bk.precision_at_k(["x", "y", "z", "w", "v", "a"], {"a"}, 5), 0.0
        )


class TestRecallAtK(unittest.TestCase):
    def test_full_recall(self):
        # both gold items in top-5 → 2/2 = 1.0
        self.assertEqual(
            bk.recall_at_k(["a", "b", "x", "y", "z"], {"a", "b"}, 5), 1.0
        )

    def test_half_recall(self):
        # 1 of 2 gold items retrieved → 0.5
        self.assertAlmostEqual(
            bk.recall_at_k(["a", "x", "y", "z", "w"], {"a", "b"}, 5), 0.5
        )

    def test_recall_independent_of_extra_retrieved(self):
        # single gold, retrieved at rank 1 → recall 1.0 regardless of noise
        self.assertEqual(
            bk.recall_at_k(["a", "x", "y", "z", "w"], {"a"}, 5), 1.0
        )

    def test_gold_beyond_k(self):
        # gold "b" only at rank 6 with k=5 → recall 1/2 = 0.5
        self.assertAlmostEqual(
            bk.recall_at_k(["a", "x", "y", "z", "w", "b"], {"a", "b"}, 5), 0.5
        )

    def test_empty_expected(self):
        self.assertEqual(bk.recall_at_k(["a", "b"], set(), 5), 0.0)


class TestReciprocalRank(unittest.TestCase):
    def test_first_position(self):
        self.assertEqual(bk.reciprocal_rank(["a", "b", "c"], {"a"}), 1.0)

    def test_second_position(self):
        self.assertAlmostEqual(bk.reciprocal_rank(["x", "a", "c"], {"a"}), 0.5)

    def test_third_position(self):
        self.assertAlmostEqual(bk.reciprocal_rank(["x", "y", "a"], {"a"}), 1 / 3)

    def test_first_relevant_wins(self):
        # two gold items; RR uses the FIRST relevant (rank 2 here)
        self.assertAlmostEqual(bk.reciprocal_rank(["x", "b", "a"], {"a", "b"}), 0.5)

    def test_none_retrieved(self):
        self.assertEqual(bk.reciprocal_rank(["x", "y", "z"], {"a"}), 0.0)


class TestRetrieveRanking(unittest.TestCase):
    """retrieve() over a synthetic in-memory catalog (no filesystem needed)."""

    def _entries(self):
        e1 = bk._CatalogEntry(slug="rope-embeddings")
        e1.type = "concept"
        e1.rel_path = "concept/rope-embeddings.md"
        e1.claim = "Rotary position embeddings encode relative position."
        e1.tags = ["transformers", "position"]
        e2 = bk._CatalogEntry(slug="attention")
        e2.type = "concept"
        e2.rel_path = "concept/attention.md"
        e2.claim = "Attention weights any token against any other token."
        e2.tags = ["transformers"]
        e3 = bk._CatalogEntry(slug="lago-event-journal")
        e3.type = "tool"
        e3.rel_path = "tool/lago-event-journal.md"
        e3.claim = "Content-addressed append-only event log."
        e3.tags = ["storage", "event-sourcing"]
        return [e1, e2, e3]

    def test_exact_slug_ranks_first(self):
        ids = bk.retrieve("attention", k=3, entries=self._entries())
        self.assertEqual(ids[0], "concept/attention")

    def test_tag_match_recovers_entity(self):
        ids = bk.retrieve("position embeddings", k=3, entries=self._entries())
        self.assertIn("concept/rope-embeddings", ids)

    def test_returns_type_slug_ids(self):
        ids = bk.retrieve("event journal", k=3, entries=self._entries())
        self.assertIn("tool/lago-event-journal", ids)

    def test_no_match_returns_empty(self):
        ids = bk.retrieve("quantum chromodynamics", k=3, entries=self._entries())
        self.assertEqual(ids, [])

    def test_k_caps_results(self):
        # query matching all three via shared "transformers"/generic terms,
        # but k=1 returns at most 1
        ids = bk.retrieve("transformers", k=1, entries=self._entries())
        self.assertLessEqual(len(ids), 1)


class TestPrecisionRecallDedup(unittest.TestCase):
    """Duplicate ids in the ranked list must not inflate P@k / R@k."""

    def test_precision_dedups_duplicate_hits(self):
        # "a" repeated 5×; only 1 distinct relevant id retrieved → 1/5, not 5/5.
        self.assertAlmostEqual(
            bk.precision_at_k(["a", "a", "a", "a", "a"], {"a"}, 5), 0.2
        )

    def test_recall_cannot_exceed_one_with_duplicates(self):
        # both gold present but "a" duplicated — recall stays 2/2 = 1.0, not >1.
        self.assertEqual(
            bk.recall_at_k(["a", "a", "b", "x", "y"], {"a", "b"}, 5), 1.0
        )

    def test_recall_single_gold_duplicated(self):
        # "a" appears twice; one distinct gold of two → recall 0.5, not 1.0.
        self.assertAlmostEqual(
            bk.recall_at_k(["a", "a", "x", "y", "z"], {"a", "b"}, 5), 0.5
        )

    def test_precision_duplicate_within_and_beyond_cutoff(self):
        # k=3 window ["a","a","x"]; distinct relevant in window = {"a"} → 1/3.
        self.assertAlmostEqual(
            bk.precision_at_k(["a", "a", "x", "a"], {"a"}, 3), 1 / 3
        )


class TestLoadBenchFixtureValidation(unittest.TestCase):
    """The fixture loader must FAIL LOUDLY, never silently skip/empty."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, text: str) -> Path:
        p = self.root / "fix.jsonl"
        p.write_text(text)
        return p

    def test_missing_file_raises(self):
        with self.assertRaises(bk.BenchFixtureError):
            bk.load_bench_fixture(self.root / "does-not-exist.jsonl")

    def test_empty_file_raises(self):
        p = self._write("")
        with self.assertRaises(bk.BenchFixtureError):
            bk.load_bench_fixture(p)

    def test_all_comment_file_raises(self):
        p = self._write("# just a comment\n\n# another\n")
        with self.assertRaises(bk.BenchFixtureError):
            bk.load_bench_fixture(p)

    def test_invalid_json_line_raises(self):
        p = self._write('{"query": "ok", "expected": ["a/b"]}\n{not json}\n')
        with self.assertRaises(bk.BenchFixtureError):
            bk.load_bench_fixture(p)

    def test_row_without_query_raises(self):
        p = self._write('{"expected": ["a/b"]}\n')
        with self.assertRaises(bk.BenchFixtureError):
            bk.load_bench_fixture(p)

    def test_string_expected_raises(self):
        # A bare string would be character-split by set(); must be rejected.
        p = self._write('{"query": "q", "expected": "concept/a"}\n')
        with self.assertRaises(bk.BenchFixtureError):
            bk.load_bench_fixture(p)

    def test_non_string_in_expected_list_raises(self):
        p = self._write('{"query": "q", "expected": ["a/b", 7]}\n')
        with self.assertRaises(bk.BenchFixtureError):
            bk.load_bench_fixture(p)

    def test_valid_fixture_parses_and_keeps_list(self):
        p = self._write(
            '{"query": "q1", "expected": ["concept/a"]}\n'
            '# comment line\n'
            '\n'
            '{"query": "q2", "expected": []}\n'
        )
        cases = bk.load_bench_fixture(p)
        self.assertEqual(len(cases), 2)
        self.assertEqual(cases[0]["expected"], ["concept/a"])
        self.assertEqual(cases[1]["expected"], [])
        self.assertIn("notes", cases[0])


class TestCmdBenchKValidation(unittest.TestCase):
    """cmd_bench must reject k < 1 with a non-zero exit before doing work."""

    def _run_with_k(self, k: int):
        ns = argparse.Namespace(fixture=None, k=k, json=False)
        return bk.cmd_bench(ns)

    def test_k_zero_exits_nonzero(self):
        with self.assertRaises(SystemExit) as cm:
            self._run_with_k(0)
        self.assertNotEqual(cm.exception.code, 0)

    def test_k_negative_exits_nonzero(self):
        with self.assertRaises(SystemExit) as cm:
            self._run_with_k(-3)
        self.assertNotEqual(cm.exception.code, 0)


class TestRunBenchAggregation(unittest.TestCase):
    """End-to-end: a synthetic catalog + fixture flows through run_bench()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "docs").mkdir()
        (root / "research" / "entities" / "concept").mkdir(parents=True)
        # Minimal v2 catalog with two parseable blocks.
        catalog = (
            "---\n"
            "generated: 2026-01-01T00:00:00+00:00\n"
            "schema: dense-catalog-v2\n"
            "---\n\n"
            "# Knowledge Index\n\n"
            "## Entities\n\n"
            "### concept (2)\n\n"
            "#### alpha [concept·entity]\n"
            "Alpha is the first synthetic concept about widgets.\n"
            "→  · ←  · #alpha #widgets · src: test\n"
            "path: concept/alpha.md\n\n"
            "#### beta [concept·entity]\n"
            "Beta is the second synthetic concept about gadgets.\n"
            "→  · ←  · #beta #gadgets · src: test\n"
            "path: concept/beta.md\n\n"
        )
        self.catalog_path = root / "docs" / "knowledge-index.md"
        self.catalog_path.write_text(catalog)
        (root / "research" / "entities" / "concept" / "alpha.md").write_text(
            "---\ncore_claim: alpha\n---\nAlpha body widgets.\n"
        )
        (root / "research" / "entities" / "concept" / "beta.md").write_text(
            "---\ncore_claim: beta\n---\nBeta body gadgets.\n"
        )
        # Point module globals at the synthetic root.
        self._saved = (bk.CATALOG_PATH, bk.ENTITIES_DIR)
        bk.CATALOG_PATH = self.catalog_path
        bk.ENTITIES_DIR = root / "research" / "entities"

        self.fixture = root / "fix.jsonl"
        self.fixture.write_text(
            json.dumps({"query": "widgets alpha", "expected": ["concept/alpha"]}) + "\n"
            + json.dumps({"query": "gadgets beta", "expected": ["concept/beta"]}) + "\n"
        )

    def tearDown(self):
        bk.CATALOG_PATH, bk.ENTITIES_DIR = self._saved
        self.tmp.cleanup()

    def test_perfect_retrieval_aggregates(self):
        result = bk.run_bench(self.fixture, k=5)
        self.assertEqual(result["n_queries"], 2)
        # Each query has exactly 1 gold, retrieved at rank 1.
        self.assertEqual(result["mrr"], 1.0)
        self.assertEqual(result["mean_recall_at_k"], 1.0)
        # P@5 with single gold per query = 1/5 each → mean 0.2
        self.assertAlmostEqual(result["mean_precision_at_k"], 0.2)
        # Per-query hits recorded.
        for q in result["per_query"]:
            self.assertEqual(len(q["hits"]), 1)

    def test_macro_average_is_mean_of_per_query(self):
        result = bk.run_bench(self.fixture, k=5)
        manual = sum(q["reciprocal_rank"] for q in result["per_query"]) / len(result["per_query"])
        self.assertAlmostEqual(result["mrr"], round(manual, 4))


class TestBacklogExport(unittest.TestCase):
    """gaps_to_backlog_candidates: pure gaps → ticket-candidate mapping (BRO-1258)."""

    @staticmethod
    def _pending():
        return [
            {"kind": "broken_link", "target": "lifegw", "inbound": 5,
             "referrers": ["a", "b", "c", "d", "e"], "suggestion": "Create [[lifegw]]"},
            {"kind": "referenced_stub", "target": "bstack", "inbound": 3,
             "referrers": ["x", "y", "z"], "suggestion": "Expand stub"},
            {"kind": "claim_missing", "target": "foo", "inbound": 1,
             "referrers": [], "suggestion": "Add claim"},
        ]

    def test_structure_and_dedup_key(self):
        cands = bk.gaps_to_backlog_candidates(self._pending(), cap=10)
        self.assertEqual(len(cands), 3)
        for c in cands:
            for key in ("dedup_key", "title", "body", "kind", "target", "leverage"):
                self.assertIn(key, c)
        # dedup_key stable + encodes kind:target (skip-already-filed contract)
        self.assertEqual(cands[0]["dedup_key"], "kg-gap:broken_link:lifegw")

    def test_sorted_by_leverage_desc(self):
        cands = bk.gaps_to_backlog_candidates(self._pending(), cap=10)
        levs = [c["leverage"] for c in cands]
        self.assertEqual(levs, sorted(levs, reverse=True))
        self.assertEqual(cands[0]["target"], "lifegw")  # highest inbound first

    def test_cap_respected(self):
        self.assertEqual(len(bk.gaps_to_backlog_candidates(self._pending(), cap=2)), 2)
        self.assertEqual(len(bk.gaps_to_backlog_candidates(self._pending(), cap=0)), 0)

    def test_ref_pluralization(self):
        one = bk.gaps_to_backlog_candidates(
            [{"kind": "claim_missing", "target": "foo", "inbound": 1, "referrers": []}])
        self.assertIn("(1 ref)", one[0]["title"])
        two = bk.gaps_to_backlog_candidates(
            [{"kind": "claim_missing", "target": "foo", "inbound": 2, "referrers": []}])
        self.assertIn("(2 refs)", two[0]["title"])

    def test_dedup_keys_idempotent(self):
        a = bk.gaps_to_backlog_candidates(self._pending())
        b = bk.gaps_to_backlog_candidates(self._pending())
        self.assertEqual([c["dedup_key"] for c in a], [c["dedup_key"] for c in b])

    def test_empty_input(self):
        self.assertEqual(bk.gaps_to_backlog_candidates([], cap=10), [])

    def test_dedup_collapses_same_slug_different_type(self):
        # bstack exists as concept|pattern|tool → 3 pending entries, same target.
        dup = [
            {"kind": "referenced_stub", "target": "bstack", "inbound": 19, "referrers": []},
            {"kind": "referenced_stub", "target": "bstack", "inbound": 19, "referrers": []},
            {"kind": "referenced_stub", "target": "bstack", "inbound": 19, "referrers": []},
        ]
        cands = bk.gaps_to_backlog_candidates(dup, cap=10)
        self.assertEqual(len(cands), 1)  # collapsed to one candidate
        keys = [c["dedup_key"] for c in cands]
        self.assertEqual(len(keys), len(set(keys)))  # dedup_keys are unique

    def test_dedup_keys_unique_on_mixed_input(self):
        cands = bk.gaps_to_backlog_candidates(self._pending() + self._pending(), cap=20)
        keys = [c["dedup_key"] for c in cands]
        self.assertEqual(len(keys), len(set(keys)))  # no dup keys ever emitted


class TestRunBenchReal(unittest.TestCase):
    """run_bench_real drives the INSTALLED kg.py via subprocess across A/B modes.

    Skipped when kg.py isn't installed (keeps the suite hermetic in CI without
    the kg skill present). When present, it is a real integration check that the
    production loader + the bench wiring agree.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()
        (self.root / "research" / "entities" / "concept").mkdir(parents=True)
        catalog = (
            "---\ngenerated: 2026-01-01T00:00:00+00:00\nschema: dense-catalog-v2\n---\n\n"
            "# Knowledge Index\n\n"
            "#### alpha [concept·entity] · score 9\n"
            "Alpha is the first synthetic concept about widgets.\n"
            "→  · ←  · #alpha #widgets · src: test\npath: concept/alpha.md\n\n"
            "#### beta [concept·entity] · score 7/9\n"
            "Beta is the second synthetic concept about gadgets.\n"
            "→  · ←  · #beta #gadgets · src: test\npath: concept/beta.md\n"
        )
        (self.root / "docs" / "knowledge-index.md").write_text(catalog)
        (self.root / "research" / "entities" / "concept" / "alpha.md").write_text(
            "---\ncore_claim: alpha\n---\nAlpha body widgets.\n")
        (self.root / "research" / "entities" / "concept" / "beta.md").write_text(
            "---\ncore_claim: beta\n---\nBeta body gadgets.\n")
        self.fixture = self.root / "fix.jsonl"
        self.fixture.write_text(
            json.dumps({"query": "widgets alpha", "expected": ["concept/alpha"],
                        "terms": "widget,alpha"}) + "\n"
            + json.dumps({"query": "gadgets beta", "expected": ["concept/beta"]}) + "\n"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_engine_modes_and_recall(self):
        if not bk.KG_PY.exists():
            self.skipTest(f"kg.py not installed at {bk.KG_PY}")
        result = bk.run_bench_real(self.fixture, k=5, root=self.root)
        self.assertEqual(result["n_queries"], 2)
        self.assertIn("modes", result)
        for label in ("baseline", "+body-search", "+terms"):
            self.assertIn(label, result["modes"])
        # Both gold entities findable via the real loader → baseline recall 1.0.
        self.assertEqual(result["mean_recall_at_k"], 1.0)
        self.assertEqual(result["engine"], "kg.py (real loader, subprocess)")
        # +terms ran only on the one row that carries a `terms` field.
        self.assertEqual(result["modes"]["+terms"]["n_queries"], 1)
        self.assertEqual(result["modes"]["+terms"]["n_skipped"], 1)


class TestCatalogScalarScore(unittest.TestCase):
    """cmd_index must emit a SPACE-FREE scalar score token, never a dict repr.

    Regression for the parse-drop bug: a dict-repr score ('score {...}') broke
    kg.py's `· score \\S+` block grammar and silently dropped the entity from
    routing (23 entities at 370). The fix reduces a dict score to its `total`.
    """

    def _block(self, score):
        node = {"fm": {"type": "industry-pattern", "status": "candidate",
                       "score": score, "core_claim": "A stub-scored pattern."},
                "body": "body", "type_dir": "industry-pattern",
                "path": str(bk.ENTITIES_DIR / "industry-pattern" / "stub-pat.md")}
        return bk._catalog_render_entity_block(
            "stub-pat", node, out_edges={}, in_edges={})

    def test_dict_score_reduced_to_total(self):
        line1 = self._block({"total": "6/9", "novelty": 1, "method": "stub"}).splitlines()[0]
        self.assertIn("· score 6/9", line1)
        self.assertNotIn("{", line1)          # no dict repr leaks into the catalog
        self.assertNotIn("  ", line1.split("· score")[1])  # no embedded spaces in token

    def test_scalar_score_passes_through(self):
        self.assertIn("· score 7/9", self._block("7/9").splitlines()[0])

    def test_none_score_omits_suffix(self):
        self.assertNotIn("· score", self._block(None).splitlines()[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
