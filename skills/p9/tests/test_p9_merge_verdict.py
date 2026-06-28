"""BRO-1489 — the merge predicate is mergeStateStatus + reviewDecision +
unresolved threads, NOT the `gh pr checks --watch` exit code.

Covers: merge_ready_verdict (the predicate, which makes a `gh pr view` call plus
a best-effort `gh api graphql` thread count), cmd_merge_status (the query), and
the cmd_merge_ready verify gate. Provenance: bstack PR #78, where the watcher
exited 0 three times while the PR was UNSTABLE / had a pending bot review.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_FIXTURES = _HERE / "fixtures"


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


class _Run:
    def __init__(self, *, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _mock_gh(p9, monkeypatch, *, view=None, threads=None,
             view_rc=0, view_stderr="", view_exc=None,
             view_nonjson=False, graphql_rc=0):
    """Dispatch subprocess.run by command: `gh pr view` vs `gh api graphql`."""
    def fake(cmd, *a, **k):
        if cmd[:3] == ["gh", "pr", "view"]:
            if view_exc is not None:
                raise view_exc
            if view_nonjson:
                return _Run(stdout="not json", returncode=0)
            return _Run(stdout=json.dumps(view) if view is not None else "",
                        stderr=view_stderr, returncode=view_rc)
        if cmd[:3] == ["gh", "api", "graphql"]:
            if graphql_rc != 0:
                return _Run(stderr="graphql err", returncode=graphql_rc)
            payload = {"data": {"repository": {"pullRequest": {
                "reviewThreads": {"nodes": threads or []}}}}}
            return _Run(stdout=json.dumps(payload), returncode=0)
        return _Run(returncode=1)
    monkeypatch.setattr(p9.subprocess, "run", fake)


_CLEAN = {"mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "reviewDecision": ""}
_UNSTABLE = {"mergeable": "MERGEABLE", "mergeStateStatus": "UNSTABLE", "reviewDecision": ""}


# ── the predicate ────────────────────────────────────────────────────────────

class TestVerdict:
    def test_clean_no_threads_is_ready(self, p9, monkeypatch):
        _mock_gh(p9, monkeypatch, view=_CLEAN, threads=[])
        v = p9.merge_ready_verdict(1, "o/r")
        assert v["ready"] is True and v["state"] == "CLEAN"

    def test_unstable_no_threads_is_ready(self, p9, monkeypatch):
        # PR #78 case: required green, only a non-required bot check un-green.
        _mock_gh(p9, monkeypatch, view=_UNSTABLE, threads=[{"isResolved": True}])
        v = p9.merge_ready_verdict(1, "o/r")
        assert v["ready"] is True and v["state"] == "UNSTABLE"

    def test_unstable_with_unresolved_thread_not_ready(self, p9, monkeypatch):
        _mock_gh(p9, monkeypatch, view=_UNSTABLE,
                 threads=[{"isResolved": False}, {"isResolved": True}])
        v = p9.merge_ready_verdict(1, "o/r")
        assert v["ready"] is False and v["unresolved_threads"] == 1

    def test_clean_with_unresolved_thread_not_ready(self, p9, monkeypatch):
        _mock_gh(p9, monkeypatch, view=_CLEAN, threads=[{"isResolved": False}])
        assert p9.merge_ready_verdict(1, "o/r")["ready"] is False

    def test_changes_requested_not_ready(self, p9, monkeypatch):
        _mock_gh(p9, monkeypatch, threads=[], view={
            "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
            "reviewDecision": "CHANGES_REQUESTED"})
        assert p9.merge_ready_verdict(1, "o/r")["ready"] is False

    @pytest.mark.parametrize("state", ["BLOCKED", "DIRTY", "BEHIND", "DRAFT", "UNKNOWN"])
    def test_hard_blocking_states_not_ready(self, p9, monkeypatch, state):
        _mock_gh(p9, monkeypatch, threads=[], view={
            "mergeable": "MERGEABLE", "mergeStateStatus": state, "reviewDecision": ""})
        assert p9.merge_ready_verdict(1, "o/r")["ready"] is False

    def test_conflicting_not_ready(self, p9, monkeypatch):
        _mock_gh(p9, monkeypatch, threads=[], view={
            "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY", "reviewDecision": ""})
        assert p9.merge_ready_verdict(1, "o/r")["ready"] is False

    def test_clean_with_undeterminable_threads_still_ready(self, p9, monkeypatch):
        # graphql fails → unresolved=-1 → does NOT block (mergeStateStatus governs).
        _mock_gh(p9, monkeypatch, view=_CLEAN, graphql_rc=1)
        v = p9.merge_ready_verdict(1, "o/r")
        assert v["ready"] is True and v["unresolved_threads"] == -1

    def test_view_failure_fails_safe(self, p9, monkeypatch):
        _mock_gh(p9, monkeypatch, view_rc=1, view_stderr="no such PR")
        v = p9.merge_ready_verdict(1, "o/r")
        assert v["ready"] is False and v["state"] == "QUERY_FAILED"

    def test_gh_missing_fails_safe(self, p9, monkeypatch):
        _mock_gh(p9, monkeypatch, view_exc=FileNotFoundError("gh"))
        assert p9.merge_ready_verdict(1, "o/r")["ready"] is False

    def test_non_json_fails_safe(self, p9, monkeypatch):
        _mock_gh(p9, monkeypatch, view_nonjson=True)
        assert p9.merge_ready_verdict(1, "o/r")["ready"] is False


# ── the query subcommand ─────────────────────────────────────────────────────

class TestMergeStatus:
    def test_exit_zero_when_ready(self, p9, monkeypatch):
        _mock_gh(p9, monkeypatch, view=_CLEAN, threads=[])
        assert p9.main(["merge-status", "5", "--repo", "o/r"]) == p9.EXIT_OK

    def test_exit_degraded_when_not_ready(self, p9, monkeypatch):
        _mock_gh(p9, monkeypatch, threads=[], view={
            "mergeable": "MERGEABLE", "mergeStateStatus": "BLOCKED", "reviewDecision": ""})
        assert p9.main(["merge-status", "5", "--repo", "o/r"]) == p9.EXIT_DEGRADED

    def test_json_output(self, p9, monkeypatch, capsys):
        _mock_gh(p9, monkeypatch, view=_CLEAN, threads=[])
        p9.main(["merge-status", "5", "--repo", "o/r", "--json"])
        assert json.loads(capsys.readouterr().out)["ready"] is True


# ── the merge-ready verify gate ──────────────────────────────────────────────

def _seed_green(p9, pr):
    for prev, curr in [(p9.PRState.PUSHED, p9.PRState.WATCHING),
                       (p9.PRState.WATCHING, p9.PRState.GREEN)]:
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-06-12T00:00:00+00:00", pr=pr, repo="o/r",
            from_state=prev.value, to_state=curr.value, watcher_id="seed"))


class TestMergeReadyGate:
    def test_green_and_ready_marks_merge_ready(self, p9, monkeypatch):
        _seed_green(p9, 10)
        _mock_gh(p9, monkeypatch, view=_CLEAN, threads=[])
        assert p9.main(["merge-ready", "10", "--repo", "o/r"]) == p9.EXIT_OK
        assert p9.current_pr_state(10) == p9.PRState.MERGE_READY

    def test_green_but_not_ready_refuses(self, p9, monkeypatch):
        """The core bug: watcher said GREEN, but the PR is UNSTABLE with an open
        thread. merge-ready must REFUSE and leave the PR in GREEN."""
        _seed_green(p9, 11)
        _mock_gh(p9, monkeypatch, view=_UNSTABLE, threads=[{"isResolved": False}])
        assert p9.main(["merge-ready", "11", "--repo", "o/r"]) == p9.EXIT_DEGRADED
        assert p9.current_pr_state(11) == p9.PRState.GREEN  # NOT promoted

    def test_no_verify_bypasses(self, p9, monkeypatch):
        _seed_green(p9, 12)
        _mock_gh(p9, monkeypatch, threads=[], view={
            "mergeable": "MERGEABLE", "mergeStateStatus": "BLOCKED", "reviewDecision": ""})
        assert p9.main(["merge-ready", "12", "--repo", "o/r", "--no-verify"]) == p9.EXIT_OK
        assert p9.current_pr_state(12) == p9.PRState.MERGE_READY

    def test_gate_blocks_when_gh_unavailable(self, p9, monkeypatch):
        """Fail-safe: if the verdict query errors, merge-ready refuses."""
        _seed_green(p9, 13)
        _mock_gh(p9, monkeypatch, view_rc=1, view_stderr="gh down")
        assert p9.main(["merge-ready", "13", "--repo", "o/r"]) == p9.EXIT_DEGRADED
        assert p9.current_pr_state(13) == p9.PRState.GREEN
