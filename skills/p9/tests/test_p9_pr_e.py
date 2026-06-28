"""Tests for PR E — watcher state-folding, abandon, cleanup, str-path policy.

Closes the bugs surfaced in the fresh-session test:
  B1: --background flag mismatch with reflexive-rule guidance.
  B2: detached watcher never folds exit into state transition.
  B3: no terminal subcommand for orphaned PRs (closed externally).
  B5: load_policy crashes on str input.
"""

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
def p9(tmp_path, monkeypatch):
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


# ─────────────────────────────────────────────────────────────────────────────
# B5: load_policy accepts str path
# ─────────────────────────────────────────────────────────────────────────────
def test_load_policy_accepts_str(p9):
    cfg = p9.load_policy(str(_FIXTURES / "policy-good.yaml"))
    assert cfg.ci_watch.enabled is True


def test_load_policy_accepts_path(p9):
    cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")
    assert cfg.ci_watch.enabled is True


# ─────────────────────────────────────────────────────────────────────────────
# B2: cmd_watch folds gh exit into state transition
# ─────────────────────────────────────────────────────────────────────────────
class _FakeProc:
    def __init__(self, returncode: int):
        self._rc = returncode
        self.pid = 12345

    def wait(self):
        return self._rc


class TestWatchFold:
    def test_foreground_green_writes_watching_then_green(self, p9, monkeypatch):
        monkeypatch.setattr(p9, "spawn_watcher",
                            lambda *a, **kw: _FakeProc(returncode=0))
        rc = p9.main(["watch", "100", "--repo", "broomva/test"])
        assert rc == 0
        assert p9.current_pr_state(100) == p9.PRState.GREEN
        # State.jsonl should hold both events
        rows, _ = p9.jsonl_read_all(p9.state_jsonl())
        states = [(r["from_state"], r["to_state"]) for r in rows if r["pr"] == 100]
        assert ("PUSHED", "WATCHING") in states
        assert ("WATCHING", "GREEN") in states

    def test_foreground_red_writes_red_unclassified(self, p9, monkeypatch):
        monkeypatch.setattr(p9, "spawn_watcher",
                            lambda *a, **kw: _FakeProc(returncode=1))
        rc = p9.main(["watch", "200", "--repo", "broomva/test"])
        assert rc == 0
        assert p9.current_pr_state(200) == p9.PRState.RED_UNCLASSIFIED

    def test_detach_skips_fold(self, p9, monkeypatch):
        called = []
        class _NeverWait:
            pid = 99
            def wait(self):
                called.append("wait")  # should NOT happen
                return 0
        monkeypatch.setattr(p9, "spawn_watcher",
                            lambda *a, **kw: _NeverWait())
        rc = p9.main(["watch", "300", "--repo", "broomva/test", "--detach"])
        assert rc == 0
        assert called == []  # detach must not block
        assert p9.current_pr_state(300) == p9.PRState.WATCHING

    def test_background_alias_is_foreground(self, p9, monkeypatch):
        # B1 fix: --background must not error and must behave like default
        monkeypatch.setattr(p9, "spawn_watcher",
                            lambda *a, **kw: _FakeProc(returncode=0))
        rc = p9.main(["watch", "400", "--repo", "broomva/test", "--background"])
        assert rc == 0
        assert p9.current_pr_state(400) == p9.PRState.GREEN

    def test_block_alias_is_foreground(self, p9, monkeypatch):
        monkeypatch.setattr(p9, "spawn_watcher",
                            lambda *a, **kw: _FakeProc(returncode=0))
        rc = p9.main(["watch", "401", "--repo", "broomva/test", "--block"])
        assert rc == 0
        assert p9.current_pr_state(401) == p9.PRState.GREEN

    def test_dry_run_emits_watching_only(self, p9):
        rc = p9.main(["watch", "500", "--repo", "broomva/test", "--dry-run"])
        assert rc == 0
        assert p9.current_pr_state(500) == p9.PRState.WATCHING


# ─────────────────────────────────────────────────────────────────────────────
# B3: cmd_abandon
# ─────────────────────────────────────────────────────────────────────────────
class TestAbandon:
    def test_abandon_open_pr(self, p9):
        # Seed a WATCHING state
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-05-05T20:00:00+00:00",
            pr=600, repo="broomva/test",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="seed",
        ))
        rc = p9.main(["abandon", "600", "--reason", "test"])
        assert rc == 0
        assert p9.current_pr_state(600) == p9.PRState.ABANDONED

    def test_abandon_unknown_pr(self, p9):
        rc = p9.main(["abandon", "999"])
        assert rc == p9.EXIT_DEGRADED

    def test_abandon_idempotent_on_terminal(self, p9):
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-05-05T20:00:00+00:00",
            pr=700, repo="broomva/test",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="seed",
        ))
        # Move to terminal MERGED via the legal chain
        for prev, curr in [
            (p9.PRState.WATCHING, p9.PRState.GREEN),
            (p9.PRState.GREEN, p9.PRState.MERGE_READY),
            (p9.PRState.MERGE_READY, p9.PRState.MERGED),
        ]:
            p9.append_state_event(p9.PRStateEvent(
                ts="2026-05-05T20:00:00+00:00",
                pr=700, repo="broomva/test",
                from_state=prev.value, to_state=curr.value,
                watcher_id="seed",
            ))
        # Abandon should be no-op
        rc = p9.main(["abandon", "700"])
        assert rc == 0
        assert p9.current_pr_state(700) == p9.PRState.MERGED

    def test_abandon_from_green_legal(self, p9):
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-05-05T20:00:00+00:00",
            pr=750, repo="broomva/test",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="seed",
        ))
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-05-05T20:00:00+00:00",
            pr=750, repo="broomva/test",
            from_state=p9.PRState.WATCHING.value,
            to_state=p9.PRState.GREEN.value,
            watcher_id="seed",
        ))
        rc = p9.main(["abandon", "750"])
        assert rc == 0
        assert p9.current_pr_state(750) == p9.PRState.ABANDONED


# ─────────────────────────────────────────────────────────────────────────────
# cmd_cleanup — orphan drainer
# ─────────────────────────────────────────────────────────────────────────────
class _FakeRun:
    def __init__(self, *, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _seed_watching(p9, pr):
    p9.append_state_event(p9.PRStateEvent(
        ts="2026-05-05T20:00:00+00:00",
        pr=pr, repo="broomva/test",
        from_state=p9.PRState.PUSHED.value,
        to_state=p9.PRState.WATCHING.value,
        watcher_id="seed",
    ))


class TestCleanup:
    def test_cleanup_no_open_prs(self, p9, capsys):
        rc = p9.main(["cleanup"])
        assert rc == 0
        assert "no open PRs" in capsys.readouterr().out

    def test_cleanup_drains_merged(self, p9, monkeypatch):
        _seed_watching(p9, 800)
        monkeypatch.setattr(p9.subprocess, "run",
                            lambda *a, **kw: _FakeRun(
                                stdout=json.dumps({"state": "MERGED",
                                                   "mergedAt": "2026-05-05T19:00:00Z"})))
        rc = p9.main(["cleanup"])
        assert rc == 0
        assert p9.current_pr_state(800) == p9.PRState.ABANDONED

    def test_cleanup_drains_closed(self, p9, monkeypatch):
        _seed_watching(p9, 801)
        monkeypatch.setattr(p9.subprocess, "run",
                            lambda *a, **kw: _FakeRun(
                                stdout=json.dumps({"state": "CLOSED",
                                                   "mergedAt": None})))
        rc = p9.main(["cleanup"])
        assert rc == 0
        assert p9.current_pr_state(801) == p9.PRState.ABANDONED

    def test_cleanup_leaves_open_alone(self, p9, monkeypatch):
        _seed_watching(p9, 802)
        monkeypatch.setattr(p9.subprocess, "run",
                            lambda *a, **kw: _FakeRun(
                                stdout=json.dumps({"state": "OPEN",
                                                   "mergedAt": None})))
        rc = p9.main(["cleanup"])
        assert rc == 0
        # Untouched
        assert p9.current_pr_state(802) == p9.PRState.WATCHING

    def test_cleanup_skips_on_gh_failure(self, p9, monkeypatch, capsys):
        _seed_watching(p9, 803)
        monkeypatch.setattr(p9.subprocess, "run",
                            lambda *a, **kw: _FakeRun(returncode=1,
                                                       stderr="auth required"))
        rc = p9.main(["cleanup"])
        assert rc == 0
        # Untouched — false-positive cleanup is forbidden
        assert p9.current_pr_state(803) == p9.PRState.WATCHING
        out = capsys.readouterr().out
        assert "skipped 1" in out


# ─────────────────────────────────────────────────────────────────────────────
# State machine: new transitions for ABANDONED from any non-terminal
# ─────────────────────────────────────────────────────────────────────────────
class TestAbandonTransitions:
    @pytest.mark.parametrize("from_state", [
        "PUSHED", "WATCHING", "HEALING", "RED_CLASSIFIED",
        "RED_UNCLASSIFIED", "GREEN", "MERGE_READY",
    ])
    def test_any_non_terminal_to_abandoned_is_legal(self, p9, from_state):
        # Should not raise
        p9.assert_legal_transition(p9.PRState(from_state), p9.PRState.ABANDONED)

    def test_terminal_to_abandoned_is_illegal(self, p9):
        with pytest.raises(p9.IllegalTransitionError):
            p9.assert_legal_transition(p9.PRState.MERGED, p9.PRState.ABANDONED)
