"""Tests for the auto-merge actuator (PR A)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
_FIXTURES = _HERE / "fixtures"
sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def p9_am(tmp_path, monkeypatch):
    """Fresh p9 import with auto-merge policy enabled."""
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-with-auto-merge.yaml"))
    # Hermetic repo identity (BRO-1988): pin a REAL repo — the regime
    # production actually runs in. Pinning tests to repo-less ("" / `-`) is
    # what hid the rearm mis-attribution blocker: the guard under test only
    # misbehaves once an ambient repo resolves.
    monkeypatch.setenv("BROOMVA_P9_REPO", "broomva/test")
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


# ─────────────────────────────────────────────────────────────────────────────
# Policy parser
# ─────────────────────────────────────────────────────────────────────────────
class TestPolicyParse:
    def test_loads_auto_merge_block(self, p9_am):
        cfg = p9_am.load_policy(_FIXTURES / "policy-with-auto-merge.yaml")
        assert cfg.auto_merge.enabled is True
        assert cfg.auto_merge.merge_method == "squash"
        assert cfg.auto_merge.delete_branch is True
        assert cfg.auto_merge.default_action == "notify"
        assert len(cfg.auto_merge.rules) == 6

    def test_missing_auto_merge_block_disables_safely(self, p9_am):
        # Default policy fixture has no auto_merge block — should default disabled
        cfg = p9_am.load_policy(_FIXTURES / "policy-good.yaml")
        assert cfg.auto_merge.enabled is False
        assert cfg.auto_merge.rules == ()

    def test_invalid_action_rejected(self, p9_am, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "ci_watch:\n  enabled: true\n  max_concurrent_prs: 1\n"
            "  isolation_tier_map:\n    research: none\n    docs: none\n"
            "    code_independent: worktree\n    code_dependent: stacked_branch\n"
            "    governance: blocked\n"
            "ci_heal:\n  enabled: true\n  max_attempts: 5\n"
            "  stability_floor: 0.3\n  classified_failure_types: [lint]\n"
            "  escalation_channel:\n    linear_team: BRO\n"
            "    linear_label: ci-heal-escalation\n"
            "    notify_hook: x.sh\n"
            "auto_merge:\n  enabled: true\n  rules:\n"
            "    - branch_pattern: \"x/*\"\n      action: yolo\n",
            encoding="utf-8",
        )
        with pytest.raises(p9_am.PolicyError):
            p9_am.load_policy(bad)

    def test_rule_without_branch_or_path_rejected(self, p9_am, tmp_path):
        bad = tmp_path / "bad2.yaml"
        bad.write_text(
            "ci_watch:\n  enabled: true\n  max_concurrent_prs: 1\n"
            "  isolation_tier_map:\n    research: none\n    docs: none\n"
            "    code_independent: worktree\n    code_dependent: stacked_branch\n"
            "    governance: blocked\n"
            "ci_heal:\n  enabled: true\n  max_attempts: 5\n"
            "  stability_floor: 0.3\n  classified_failure_types: [lint]\n"
            "  escalation_channel:\n    linear_team: BRO\n"
            "    linear_label: ci-heal-escalation\n"
            "    notify_hook: x.sh\n"
            "auto_merge:\n  enabled: true\n  rules:\n"
            "    - action: auto\n",
            encoding="utf-8",
        )
        with pytest.raises(p9_am.PolicyError):
            p9_am.load_policy(bad)


# ─────────────────────────────────────────────────────────────────────────────
# Matcher
# ─────────────────────────────────────────────────────────────────────────────
class TestMatcher:
    def test_governance_path_always_blocks(self, p9_am):
        cfg = p9_am.load_policy(_FIXTURES / "policy-with-auto-merge.yaml")
        # Branch matches an auto rule, but PR touches CLAUDE.md → blocks
        action, reason = p9_am.match_auto_merge_action(
            cfg.auto_merge,
            branch="docs/some-update",
            paths_touched=["docs/foo.md", "CLAUDE.md"],
        )
        assert action == "require_human"
        assert "CLAUDE.md" in reason

    def test_docs_branch_auto_merges(self, p9_am):
        cfg = p9_am.load_policy(_FIXTURES / "policy-with-auto-merge.yaml")
        action, _ = p9_am.match_auto_merge_action(
            cfg.auto_merge,
            branch="docs/typo-fix",
            paths_touched=["README.md", "docs/foo.md"],
        )
        assert action == "auto"

    def test_research_branch_auto_merges(self, p9_am):
        cfg = p9_am.load_policy(_FIXTURES / "policy-with-auto-merge.yaml")
        action, _ = p9_am.match_auto_merge_action(
            cfg.auto_merge,
            branch="research/new-entity",
            paths_touched=["research/entities/concept/foo.md"],
        )
        assert action == "auto"

    def test_feat_p9_branch_auto_merges(self, p9_am):
        cfg = p9_am.load_policy(_FIXTURES / "policy-with-auto-merge.yaml")
        action, _ = p9_am.match_auto_merge_action(
            cfg.auto_merge,
            branch="feat/p9-spec",
            paths_touched=["docs/foo.md"],
        )
        assert action == "auto"

    def test_unknown_branch_falls_to_default_notify(self, p9_am):
        cfg = p9_am.load_policy(_FIXTURES / "policy-with-auto-merge.yaml")
        action, reason = p9_am.match_auto_merge_action(
            cfg.auto_merge,
            branch="feat/some-other-thing",
            paths_touched=["src/foo.ts"],
        )
        assert action == "notify"
        assert "default" in reason.lower()

    def test_path_rule_first_match_wins(self, p9_am):
        cfg = p9_am.load_policy(_FIXTURES / "policy-with-auto-merge.yaml")
        # AGENTS.md is governance-class blocked; should beat docs/* auto
        action, _ = p9_am.match_auto_merge_action(
            cfg.auto_merge,
            branch="docs/cleanup",
            paths_touched=["AGENTS.md"],
        )
        assert action == "require_human"


# ─────────────────────────────────────────────────────────────────────────────
# Subcommand integration (with subprocess mocked)
# ─────────────────────────────────────────────────────────────────────────────
class _FakeRun:
    def __init__(self, *, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _pr_view(cmd, *, branch, files, merge_state="CLEAN"):
    """`gh pr view` answers two questions: branch+files (the `-q` form) and,
    since BRO-2591, the merge predicate re-read at merge time."""
    if "-q" in cmd:
        return _FakeRun(stdout=json.dumps(
            {"branch": branch, "files": files, "changed": len(files)}))
    return _FakeRun(stdout=json.dumps(
        {"mergeable": "MERGEABLE", "mergeStateStatus": merge_state,
         "reviewDecision": "", "headRefOid": "d" * 40}))


def _seed_merge_ready(p9, pr: int):
    for prev, curr in [
        (p9.PRState.PUSHED, p9.PRState.WATCHING),
        (p9.PRState.WATCHING, p9.PRState.GREEN),
        (p9.PRState.GREEN, p9.PRState.MERGE_READY),
    ]:
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-05-05T00:00:00+00:00",
            pr=pr, repo="broomva/test",
            from_state=prev.value, to_state=curr.value,
            watcher_id="seed",
        ))


class TestCommand:
    def test_blocks_when_pr_not_merge_ready(self, p9_am, capsys):
        rc = p9_am.main(["auto-merge", "999", "--repo", "broomva/test"])
        assert rc == p9_am.EXIT_DEGRADED

    def test_dry_run_for_auto_branch(self, p9_am, monkeypatch, capsys):
        _seed_merge_ready(p9_am, 100)

        def fake_view(cmd, *args, **kwargs):
            if cmd[:3] == ["gh", "api", "graphql"]:
                return _FakeRun(returncode=1)
            assert cmd[:3] == ["gh", "pr", "view"]
            return _pr_view(cmd, branch="docs/typo", files=["README.md"])

        monkeypatch.setattr(p9_am.subprocess, "run", fake_view)

        rc = p9_am.main(["auto-merge", "100", "--repo", "broomva/test", "--dry-run"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "would merge PR #100" in out
        # Did NOT transition to MERGED in dry-run
        assert p9_am.current_pr_state(100) == p9_am.PRState.MERGE_READY

    def test_blocks_governance_path(self, p9_am, monkeypatch, capsys):
        _seed_merge_ready(p9_am, 200)

        def fake_view(cmd, *args, **kwargs):
            return _pr_view(cmd, branch="docs/cleanup", files=["docs/x.md", "CLAUDE.md"])

        monkeypatch.setattr(p9_am.subprocess, "run", fake_view)
        rc = p9_am.main(["auto-merge", "200", "--repo", "broomva/test"])
        assert rc == p9_am.EXIT_AUTO_MERGE_BLOCKED
        # Idempotent self-transition recorded with reason
        rows, _ = p9_am.jsonl_read_all(p9_am.state_jsonl())
        last = [r for r in rows if r["pr"] == 200][-1]
        assert last["to_state"] == "MERGE_READY"
        assert last["extra"]["auto_merge"]["action"] == "require_human"

    def test_auto_executes_gh_merge(self, p9_am, monkeypatch, capsys):
        _seed_merge_ready(p9_am, 300)
        calls = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "view"]:
                return _pr_view(cmd, branch="docs/something", files=["docs/y.md"])
            if cmd[:3] == ["gh", "pr", "merge"]:
                return _FakeRun(returncode=0)
            return _FakeRun(returncode=1)

        monkeypatch.setattr(p9_am.subprocess, "run", fake_run)
        rc = p9_am.main(["auto-merge", "300", "--repo", "broomva/test"])
        assert rc == 0
        # Real merge call happened, pinned to the head the verdict read
        merge_calls = [c for c in calls if c[:3] == ["gh", "pr", "merge"]]
        assert len(merge_calls) == 1
        assert "--squash" in merge_calls[0]
        assert "--delete-branch" in merge_calls[0]
        assert merge_calls[0][merge_calls[0].index("--match-head-commit") + 1] == "d" * 40
        # State transitioned to MERGED
        assert p9_am.current_pr_state(300) == p9_am.PRState.MERGED

    def test_disabled_policy_refuses(self, tmp_path, monkeypatch, capsys):
        # Use the default good policy (no auto_merge block → disabled)
        monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
        monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
        # Hermetic repo identity (BRO-1988): pin a REAL repo (see module
        # fixture) — repo-less is not the regime production runs in.
        monkeypatch.setenv("BROOMVA_P9_REPO", "broomva/test")
        if "p9" in sys.modules:
            del sys.modules["p9"]
        mod = importlib.import_module("p9")
        # seed MERGE_READY anyway
        _seed_merge_ready(mod, 400)
        rc = mod.main(["auto-merge", "400", "--repo", "broomva/test"])
        assert rc == mod.EXIT_POLICY_ERROR

    def test_external_merge_failure_reports_clean_error(self, p9_am, monkeypatch, capsys):
        _seed_merge_ready(p9_am, 500)

        def fake_run(cmd, *args, **kwargs):
            if cmd[:3] == ["gh", "pr", "view"]:
                return _pr_view(cmd, branch="docs/whatever", files=["docs/z.md"])
            if cmd[:3] == ["gh", "pr", "merge"]:
                return _FakeRun(returncode=1)
            return _FakeRun(returncode=1)

        monkeypatch.setattr(p9_am.subprocess, "run", fake_run)
        rc = p9_am.main(["auto-merge", "500", "--repo", "broomva/test"])
        assert rc == p9_am.EXIT_EXTERNAL_ERROR
        # State did NOT transition to MERGED (external failure must not lie)
        assert p9_am.current_pr_state(500) == p9_am.PRState.MERGE_READY


class TestLegacyReverifiesAtMergeTime:
    """BRO-2591: without gates, an `auto` rule still re-reads the merge
    predicate at merge time. A MERGE_READY row is history, and
    `merge-ready --no-verify` can write one for a PR that is not mergeable."""

    @pytest.mark.parametrize("merge_state", ["BLOCKED", "BEHIND", "DRAFT", "UNKNOWN"])
    def test_stale_merge_ready_row_does_not_merge(self, p9_am, monkeypatch, merge_state):
        _seed_merge_ready(p9_am, 600)
        calls = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "view"]:
                return _pr_view(cmd, branch="docs/ok", files=["docs/a.md"],
                                merge_state=merge_state)
            return _FakeRun(returncode=1)

        monkeypatch.setattr(p9_am.subprocess, "run", fake_run)
        rc = p9_am.main(["auto-merge", "600", "--repo", "broomva/test"])
        assert rc == p9_am.EXIT_AUTO_MERGE_BLOCKED
        assert not [c for c in calls if c[:3] == ["gh", "pr", "merge"]]


class TestCompleteFileList:
    """gh pr view caps `files` at 100. A path rule beyond the first page must
    not be invisible: the list is re-read paginated, or the call refuses."""

    def test_truncated_list_is_completed_and_rule_fires(self, p9_am, monkeypatch):
        _seed_merge_ready(p9_am, 610)
        first_page = [f"docs/f{i}.md" for i in range(100)]

        def fake_run(cmd, *args, **kwargs):
            if cmd[:3] == ["gh", "pr", "view"] and "-q" in cmd:
                return _FakeRun(stdout=json.dumps(
                    {"branch": "docs/big", "files": first_page, "changed": 101}))
            if cmd[:3] == ["gh", "api", "--paginate"]:
                return _FakeRun(stdout="\n".join(first_page + ["CLAUDE.md"]) + "\n")
            return _FakeRun(returncode=1)

        monkeypatch.setattr(p9_am.subprocess, "run", fake_run)
        rc = p9_am.main(["auto-merge", "610", "--repo", "broomva/test"])
        assert rc == p9_am.EXIT_AUTO_MERGE_BLOCKED   # CLAUDE.md, found on page 2

    def test_unlistable_diff_refuses(self, p9_am, monkeypatch):
        _seed_merge_ready(p9_am, 611)

        def fake_run(cmd, *args, **kwargs):
            if cmd[:3] == ["gh", "pr", "view"] and "-q" in cmd:
                return _FakeRun(stdout=json.dumps(
                    {"branch": "docs/big", "files": ["docs/a.md"], "changed": 300}))
            return _FakeRun(returncode=1)

        monkeypatch.setattr(p9_am.subprocess, "run", fake_run)
        rc = p9_am.main(["auto-merge", "611", "--repo", "broomva/test"])
        assert rc != p9_am.EXIT_OK
        assert p9_am.current_pr_state(611) == p9_am.PRState.MERGE_READY


    def test_short_paginated_list_refuses(self, p9_am, monkeypatch):
        # The REST listing came back shorter than changedFiles: judging the
        # 150 files it did return would leave 150 unseen.
        _seed_merge_ready(p9_am, 612)
        calls = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "merge"]:
                return _FakeRun(returncode=0)
            if cmd[:3] == ["gh", "pr", "view"] and "-q" in cmd:
                return _FakeRun(stdout=json.dumps(
                    {"branch": "docs/big", "files": ["docs/a.md"] * 100, "changed": 300}))
            if cmd[:3] == ["gh", "api", "--paginate"]:
                return _FakeRun(stdout="\n".join(f"docs/f{i}.md" for i in range(150)))
            if cmd[:3] == ["gh", "pr", "view"]:
                return _pr_view(cmd, branch="docs/big", files=["docs/a.md"])
            return _FakeRun(returncode=1)

        monkeypatch.setattr(p9_am.subprocess, "run", fake_run)
        rc = p9_am.main(["auto-merge", "612", "--repo", "broomva/test"])
        assert rc != p9_am.EXIT_OK
        assert not [c for c in calls if c[:3] == ["gh", "pr", "merge"]]
        assert p9_am.current_pr_state(612) == p9_am.PRState.MERGE_READY


class TestLegacyPinsTheHead:
    def test_unreadable_head_sha_does_not_merge_unpinned(self, p9_am, monkeypatch):
        _seed_merge_ready(p9_am, 620)
        calls = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "view"] and "-q" in cmd:
                return _FakeRun(stdout=json.dumps(
                    {"branch": "docs/ok", "files": ["docs/a.md"], "changed": 1}))
            if cmd[:3] == ["gh", "pr", "view"]:
                return _FakeRun(stdout=json.dumps(
                    {"mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
                     "reviewDecision": ""}))          # no headRefOid
            return _FakeRun(returncode=1)

        monkeypatch.setattr(p9_am.subprocess, "run", fake_run)
        rc = p9_am.main(["auto-merge", "620", "--repo", "broomva/test"])
        assert rc == p9_am.EXIT_AUTO_MERGE_BLOCKED
        assert not [c for c in calls if c[:3] == ["gh", "pr", "merge"]]
