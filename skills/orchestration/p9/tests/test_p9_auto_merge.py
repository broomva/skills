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


HEAD = "d" * 40


def _gh_pr(cmd, *, branch, files, merge_state="CLEAN", head=HEAD, verdict_head=HEAD,
           renamed=None):
    """Answer the reads `p9 auto-merge` makes about one PR, or None.

    - `gh pr view -q`: branch, head and changedFiles (the listing header);
    - `gh api --paginate .../files`: the complete TSV listing, with pre-rename
      paths (BRO-2591), which gh pr view caps at 100 and cannot show;
    - `gh pr view --json mergeable,...`: the merge predicate, re-read at merge
      time since BRO-2591."""
    renamed = renamed or {}
    if cmd[:3] == ["gh", "pr", "view"] and "-q" in cmd:
        return _FakeRun(stdout=json.dumps(
            {"branch": branch, "head": head, "changed": len(files)}))
    if cmd[:3] == ["gh", "api", "--paginate"]:
        return _FakeRun(stdout="".join(
            f"{f}\t{renamed.get(f, '')}\tmodified\t5\n" for f in files))
    if cmd[:3] == ["gh", "pr", "view"]:
        v = {"mergeable": "MERGEABLE", "mergeStateStatus": merge_state,
             "reviewDecision": ""}
        if verdict_head:
            v["headRefOid"] = verdict_head
        return _FakeRun(stdout=json.dumps(v))
    if cmd[:3] == ["gh", "api", "graphql"]:
        return _FakeRun(returncode=1)
    return None


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
            r = _gh_pr(cmd, branch="docs/typo", files=["README.md"])
            assert r is not None, f"unexpected call {cmd[:4]}"
            return r

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
            return _gh_pr(cmd, branch="docs/cleanup",
                          files=["docs/x.md", "CLAUDE.md"]) or _FakeRun(returncode=1)

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
            r = _gh_pr(cmd, branch="docs/something", files=["docs/y.md"])
            if r is not None:
                return r
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
        assert merge_calls[0][merge_calls[0].index("--match-head-commit") + 1] == HEAD
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
            r = _gh_pr(cmd, branch="docs/whatever", files=["docs/z.md"])
            if r is not None:
                return r
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

    def _run(self, p9_am, monkeypatch, pr, **kw):
        _seed_merge_ready(p9_am, pr)
        calls = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "merge"]:
                return _FakeRun(returncode=0)
            return _gh_pr(cmd, branch="docs/ok", files=["docs/a.md"], **kw) \
                or _FakeRun(returncode=1)

        monkeypatch.setattr(p9_am.subprocess, "run", fake_run)
        rc = p9_am.main(["auto-merge", str(pr), "--repo", "broomva/test"])
        return rc, [c for c in calls if c[:3] == ["gh", "pr", "merge"]]

    @pytest.mark.parametrize("merge_state", ["BLOCKED", "BEHIND", "DRAFT", "UNKNOWN"])
    def test_stale_merge_ready_row_does_not_merge(self, p9_am, monkeypatch, merge_state):
        rc, merges = self._run(p9_am, monkeypatch, 600, merge_state=merge_state)
        assert rc == p9_am.EXIT_AUTO_MERGE_BLOCKED and not merges

    def test_clean_pr_merges_pinned(self, p9_am, monkeypatch):
        rc, merges = self._run(p9_am, monkeypatch, 601)
        assert rc == p9_am.EXIT_OK
        assert merges[0][merges[0].index("--match-head-commit") + 1] == HEAD

    def test_unreadable_head_sha_does_not_merge_unpinned(self, p9_am, monkeypatch):
        rc, merges = self._run(p9_am, monkeypatch, 602, verdict_head=None)
        assert rc == p9_am.EXIT_AUTO_MERGE_BLOCKED and not merges

    def test_head_moved_between_reads_does_not_merge(self, p9_am, monkeypatch):
        # The rules judged the files at HEAD; the verdict saw another head.
        rc, merges = self._run(p9_am, monkeypatch, 603, verdict_head="e" * 40)
        assert rc == p9_am.EXIT_AUTO_MERGE_BLOCKED and not merges


class TestCompleteFileList:
    """The listing is the paginated REST one, with pre-rename paths; a short or
    failed listing refuses rather than judging part of the diff."""

    def _run(self, p9_am, monkeypatch, pr, *, files, changed=None, rows=None, renamed=None):
        _seed_merge_ready(p9_am, pr)
        calls = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "merge"]:
                return _FakeRun(returncode=0)
            if cmd[:3] == ["gh", "pr", "view"] and "-q" in cmd and changed is not None:
                return _FakeRun(stdout=json.dumps(
                    {"branch": "docs/big", "head": HEAD, "changed": changed}))
            if cmd[:3] == ["gh", "api", "--paginate"] and rows is not None:
                return rows
            return _gh_pr(cmd, branch="docs/big", files=files, renamed=renamed) \
                or _FakeRun(returncode=1)

        monkeypatch.setattr(p9_am.subprocess, "run", fake_run)
        rc = p9_am.main(["auto-merge", str(pr), "--repo", "broomva/test"])
        return rc, [c for c in calls if c[:3] == ["gh", "pr", "merge"]]

    def test_governance_file_past_the_first_100_is_seen(self, p9_am, monkeypatch):
        files = [f"docs/f{i}.md" for i in range(100)] + ["CLAUDE.md"]
        rc, merges = self._run(p9_am, monkeypatch, 610, files=files)
        assert rc == p9_am.EXIT_AUTO_MERGE_BLOCKED and not merges

    def test_renaming_a_governance_file_away_is_seen(self, p9_am, monkeypatch):
        rc, merges = self._run(p9_am, monkeypatch, 613, files=["docs/AGENTS.md"],
                               renamed={"docs/AGENTS.md": "AGENTS.md"})
        assert rc == p9_am.EXIT_AUTO_MERGE_BLOCKED and not merges

    def test_failed_listing_refuses(self, p9_am, monkeypatch):
        rc, merges = self._run(p9_am, monkeypatch, 611, files=["docs/a.md"],
                               rows=_FakeRun(returncode=1))
        assert rc != p9_am.EXIT_OK and not merges
        assert p9_am.current_pr_state(611) == p9_am.PRState.MERGE_READY

    def test_short_listing_refuses(self, p9_am, monkeypatch):
        # 150 rows for a 300-file PR: judging them would leave 150 unseen.
        files = [f"docs/f{i}.md" for i in range(150)]
        rc, merges = self._run(p9_am, monkeypatch, 612, files=files, changed=300)
        assert rc != p9_am.EXIT_OK and not merges
        assert p9_am.current_pr_state(612) == p9_am.PRState.MERGE_READY
