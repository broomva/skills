"""Unit tests for skills/p9/scripts/p9.py.

Pure-function tests, no live subprocess calls. State directory is
redirected to a tmpdir via BROOMVA_P9_HOME.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
_FIXTURES = _HERE / "fixtures"
sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    """Fresh import of p9 with a tmpdir state home and the good-policy fixture."""
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    if "p9" in sys.modules:
        del sys.modules["p9"]
    mod = importlib.import_module("p9")
    return mod


def _read_fixture(name: str) -> str:
    return (_FIXTURES / "failures" / name).read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Classifier
# ─────────────────────────────────────────────────────────────────────────────
class TestClassifier:
    @pytest.mark.parametrize(
        "fixture, expected_type, expected_classified",
        [
            ("lint.txt", "lint", True),
            ("format.txt", "format", True),
            ("type.txt", "type", False),  # type errors → escalate
            ("codegen_drift.txt", "codegen_drift", True),
            ("import_missing.txt", "import_missing", False),  # complex; escalate v1
            ("unclassified.txt", "unclassified", False),
        ],
    )
    def test_classifies_fixture(self, p9, fixture, expected_type, expected_classified):
        log = _read_fixture(fixture)
        result = p9.classify(log)
        assert result.failure_type == expected_type, (
            f"expected {expected_type}, got {result.failure_type}; "
            f"rationale: {result.rationale}"
        )
        assert result.classified is expected_classified

    def test_unclassified_returns_zero_or_below_floor_confidence(self, p9):
        log = _read_fixture("unclassified.txt")
        result = p9.classify(log)
        assert result.confidence < 0.7
        assert result.heal_command is None

    def test_classified_lint_has_heal_command(self, p9):
        log = _read_fixture("lint.txt")
        result = p9.classify(log)
        assert result.heal_command is not None
        assert "lint" in result.heal_command

    def test_signature_hash_is_stable(self, p9):
        log = _read_fixture("lint.txt")
        s1 = p9.classify(log).signature_hash
        s2 = p9.classify(log).signature_hash
        assert s1 == s2 and len(s1) == 16

    def test_signature_hash_differs_across_failure_types(self, p9):
        s_lint = p9.classify(_read_fixture("lint.txt")).signature_hash
        s_type = p9.classify(_read_fixture("type.txt")).signature_hash
        assert s_lint != s_type

    def test_test_flaky_requires_high_confidence(self, p9):
        # FAIL marker alone should NOT classify as flaky (confidence_floor=0.9)
        log = _read_fixture("test_flaky.txt")
        result = p9.classify(log)
        # Single weak match → 0.7 < floor 0.9 → unclassified
        assert result.failure_type == "unclassified"

    def test_empty_log_is_unclassified(self, p9):
        result = p9.classify("")
        assert result.failure_type == "unclassified"

    def test_no_pattern_match_explicitly_unclassified(self, p9):
        result = p9.classify("just some boring log output\nnothing to see here")
        assert result.failure_type == "unclassified"
        assert result.confidence == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Rubric ↔ markdown sync
# ─────────────────────────────────────────────────────────────────────────────
class TestRubricSync:
    def test_every_code_entry_has_markdown_section(self, p9):
        rubric_md = (_HERE.parent / "references" / "scoring-rubric.md").read_text(
            encoding="utf-8"
        )
        for entry in p9._builtin_rubric():
            assert f"`{entry.failure_type}`" in rubric_md, (
                f"rubric markdown missing section for failure type "
                f"`{entry.failure_type}`"
            )

    def test_rubric_md_lists_unclassified_terminal(self, p9):
        rubric_md = (_HERE.parent / "references" / "scoring-rubric.md").read_text(
            encoding="utf-8"
        )
        assert "`unclassified`" in rubric_md


# ─────────────────────────────────────────────────────────────────────────────
# Evaluator
# ─────────────────────────────────────────────────────────────────────────────
class TestEvaluator:
    def test_first_attempt_max_score(self, p9):
        result = p9.evaluate(
            attempt=0,
            max_attempts=5,
            classifier_confidence=1.0,
            prev_signature=None,
            curr_signature="abcd",
            prev_failure_count=None,
            curr_failure_count=3,
            stability_floor=0.3,
        )
        # No prev signature → not "changed". Budget is 1.0. Confidence bonus 0.1.
        # 0.0 (sig) + 0.0 (failures) + 0.2 (budget) + 0.1 (conf) = 0.3
        assert result.progress_score == pytest.approx(0.3)
        # Exactly at floor → not strictly stalled in this evaluator (stalled is "<")
        assert result.stalled is False

    def test_signature_change_dominates(self, p9):
        result = p9.evaluate(
            attempt=1, max_attempts=5,
            classifier_confidence=0.7,
            prev_signature="aaaa", curr_signature="bbbb",
            prev_failure_count=None, curr_failure_count=2,
            stability_floor=0.3,
        )
        # 0.4 (sig changed) + 0 + 0.2*(1-1/5)=0.16 + 0.07 = 0.63
        assert result.progress_score > 0.5
        assert result.signature_changed is True
        assert result.stalled is False

    def test_failures_decreasing(self, p9):
        result = p9.evaluate(
            attempt=2, max_attempts=5,
            classifier_confidence=0.8,
            prev_signature="x", curr_signature="x",  # not changed
            prev_failure_count=5, curr_failure_count=2,
            stability_floor=0.3,
        )
        assert result.failures_decreased is True

    def test_stalled_when_score_below_floor(self, p9):
        result = p9.evaluate(
            attempt=4, max_attempts=5,
            classifier_confidence=0.7,
            prev_signature="x", curr_signature="x",  # no change
            prev_failure_count=2, curr_failure_count=3,  # got worse
            stability_floor=0.3,
        )
        # 0 + 0 + 0.2*(1/5)=0.04 + 0.07 = 0.11 → stalled
        assert result.stalled is True
        assert result.progress_score < 0.3

    def test_budget_exhausted_at_max(self, p9):
        result = p9.evaluate(
            attempt=5, max_attempts=5,
            classifier_confidence=0.7,
            prev_signature=None, curr_signature="x",
            prev_failure_count=None, curr_failure_count=1,
            stability_floor=0.3,
        )
        assert result.budget_remaining == 0.0

    def test_stalled_for_two_cycles_helper(self, p9):
        assert p9.stalled_for_two_cycles([0.5, 0.2, 0.1], stability_floor=0.3) is True
        assert p9.stalled_for_two_cycles([0.5, 0.2, 0.4], stability_floor=0.3) is False
        assert p9.stalled_for_two_cycles([0.1], stability_floor=0.3) is False


# ─────────────────────────────────────────────────────────────────────────────
# State machine
# ─────────────────────────────────────────────────────────────────────────────
class TestStateMachine:
    def test_legal_pushed_to_watching(self, p9):
        p9.assert_legal_transition(p9.PRState.PUSHED, p9.PRState.WATCHING)

    def test_legal_watching_to_green(self, p9):
        p9.assert_legal_transition(p9.PRState.WATCHING, p9.PRState.GREEN)

    def test_idempotent_self_transition_allowed(self, p9):
        # Status refreshes that emit the same state are OK
        p9.assert_legal_transition(p9.PRState.WATCHING, p9.PRState.WATCHING)

    def test_illegal_pushed_to_merged(self, p9):
        with pytest.raises(p9.IllegalTransitionError):
            p9.assert_legal_transition(p9.PRState.PUSHED, p9.PRState.MERGED)

    def test_illegal_green_to_red_classified(self, p9):
        with pytest.raises(p9.IllegalTransitionError):
            p9.assert_legal_transition(p9.PRState.GREEN, p9.PRState.RED_CLASSIFIED)

    def test_terminal_states(self, p9):
        assert p9.is_terminal(p9.PRState.MERGED)
        assert p9.is_terminal(p9.PRState.ESCALATED)
        assert p9.is_terminal(p9.PRState.ABANDONED)
        assert not p9.is_terminal(p9.PRState.WATCHING)


# ─────────────────────────────────────────────────────────────────────────────
# Wait queue
# ─────────────────────────────────────────────────────────────────────────────
class TestWaitQueue:
    def test_priority_ordering(self, p9):
        p9.queue_push("d", "docs")
        p9.queue_push("l", "linear")
        p9.queue_push("s", "session")
        p9.queue_push("g", "graph")
        p9.queue_push("m", "memory")
        order = [it.source for it in p9.queue_list()]
        assert order == ["session", "memory", "graph", "docs", "linear"]

    def test_pop_returns_session_first(self, p9):
        p9.queue_push("low", "linear")
        p9.queue_push("high", "session")
        head = p9.queue_pop()
        assert head.source == "session"
        # Second pop pulls linear
        next_ = p9.queue_pop()
        assert next_.source == "linear"
        # Third pop empty
        assert p9.queue_pop() is None

    def test_clear_empties(self, p9):
        p9.queue_push("x", "session")
        p9.queue_push("y", "graph")
        n = p9.queue_clear()
        assert n == 2
        assert p9.queue_list() == []

    def test_invalid_source_rejected(self, p9):
        with pytest.raises(p9.P9Error):
            p9.queue_push("x", "made-up-source")


# ─────────────────────────────────────────────────────────────────────────────
# Policy loader
# ─────────────────────────────────────────────────────────────────────────────
class TestPolicy:
    def test_loads_good_policy(self, p9):
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")
        assert cfg.ci_watch.enabled is True
        assert cfg.ci_watch.max_concurrent_prs == 1
        assert cfg.ci_heal.max_attempts == 5
        assert cfg.ci_heal.stability_floor == 0.3
        assert "lint" in cfg.ci_heal.classified_failure_types

    def test_missing_ci_watch_block_fails_closed(self, p9):
        with pytest.raises(p9.PolicyError):
            p9.load_policy(_FIXTURES / "policy-missing-ci-watch.yaml")

    def test_missing_file_fails_closed(self, p9, tmp_path):
        with pytest.raises(p9.PolicyError):
            p9.load_policy(tmp_path / "no-such-file.yaml")

    def test_isolation_tier_map_has_governance_blocked(self, p9):
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")
        assert cfg.ci_watch.isolation_tier_map.governance == "blocked"


# ─────────────────────────────────────────────────────────────────────────────
# State store + JSONL corruption recovery
# ─────────────────────────────────────────────────────────────────────────────
class TestStateStore:
    def test_append_and_read_one_event(self, p9):
        evt = p9.PRStateEvent(
            ts="2026-05-04T18:00:00+00:00",
            pr=42, repo="broomva/workspace",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="w0",
        )
        p9.append_state_event(evt)
        assert p9.current_pr_state(42) == p9.PRState.WATCHING

    def test_open_prs_excludes_terminal(self, p9):
        # PR 42: PUSHED → WATCHING → GREEN → MERGE_READY → MERGED
        for prev, curr in [
            (p9.PRState.PUSHED, p9.PRState.WATCHING),
            (p9.PRState.WATCHING, p9.PRState.GREEN),
            (p9.PRState.GREEN, p9.PRState.MERGE_READY),
            (p9.PRState.MERGE_READY, p9.PRState.MERGED),
        ]:
            p9.append_state_event(p9.PRStateEvent(
                ts="2026-05-04T00:00:00+00:00",
                pr=42, repo="broomva/workspace",
                from_state=prev.value, to_state=curr.value,
                watcher_id="w42",
            ))
        # PR 43: still WATCHING
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-05-04T00:00:00+00:00",
            pr=43, repo="broomva/workspace",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="w43",
        ))
        open_ = p9.open_prs()
        assert len(open_) == 1
        assert open_[0]["pr"] == 43

    def test_jsonl_partial_last_line_recovered(self, p9, tmp_path):
        path = p9.state_jsonl()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Two valid lines, then a torn third line
        path.write_text(
            '{"a":1}\n{"a":2}\n{"a":3,', encoding="utf-8",
        )
        rows, dropped = p9.jsonl_read_all(path)
        assert dropped == 1
        assert [r["a"] for r in rows] == [1, 2]

    def test_jsonl_mid_file_corruption_raises(self, p9):
        path = p9.state_jsonl()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"a":1}\n{"corrupt":\n{"a":3}\n', encoding="utf-8",
        )
        with pytest.raises(p9.IllegalTransitionError):
            p9.jsonl_read_all(path)


# ─────────────────────────────────────────────────────────────────────────────
# Concurrency ceiling
# ─────────────────────────────────────────────────────────────────────────────
class TestConcurrency:
    def test_ceiling_blocks_above_max(self, p9):
        # Open 1 PR; ceiling default is 1
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-05-04T00:00:00+00:00",
            pr=1, repo="broomva/x",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="w1",
        ))
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")
        with pytest.raises(p9.ConcurrencyCeilingError):
            p9.enforce_concurrency_ceiling(cfg)

    def test_ceiling_allows_when_terminal_present(self, p9):
        # PR is in MERGED (terminal) — should not count toward ceiling
        for prev, curr in [
            (p9.PRState.PUSHED, p9.PRState.WATCHING),
            (p9.PRState.WATCHING, p9.PRState.GREEN),
            (p9.PRState.GREEN, p9.PRState.MERGE_READY),
            (p9.PRState.MERGE_READY, p9.PRState.MERGED),
        ]:
            p9.append_state_event(p9.PRStateEvent(
                ts="2026-05-04T00:00:00+00:00",
                pr=1, repo="broomva/x",
                from_state=prev.value, to_state=curr.value,
                watcher_id="w1",
            ))
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")
        p9.enforce_concurrency_ceiling(cfg)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# CLI smoke (build_parser + main, no subprocess spawn)
# ─────────────────────────────────────────────────────────────────────────────
class TestCLISmoke:
    def test_parser_has_all_subcommands(self, p9):
        parser = p9.build_parser()
        help_text = parser.format_help()
        for cmd in ["watch", "status", "wait-queue", "heal", "events",
                    "merge-ready", "doctor"]:
            assert cmd in help_text

    def test_main_dry_run_watch(self, p9, monkeypatch, tmp_path):
        # Skip auto repo detection
        rc = p9.main([
            "watch", "999", "--repo", "broomva/test",
            "--dry-run", "--json",
        ])
        assert rc == 0
        # State emitted
        rows, _ = p9.jsonl_read_all(p9.state_jsonl())
        assert any(r["pr"] == 999 for r in rows)

    def test_main_status_empty(self, p9, capsys):
        rc = p9.main(["status"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "no PRs in flight" in out

    def test_main_wait_queue_push_pop_list(self, p9, capsys):
        rc = p9.main(["wait-queue", "push", "--source", "session", "--item", "X"])
        assert rc == 0
        rc = p9.main(["wait-queue", "list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "[session" in out and " X" in out
        rc = p9.main(["wait-queue", "pop"])
        assert rc == 0

    def test_main_heal_classify_from_log_file(self, p9, capsys):
        rc = p9.main([
            "heal", "1", "--classify",
            "--log-file", str(_FIXTURES / "failures" / "lint.txt"),
        ])
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["failure_type"] == "lint"
