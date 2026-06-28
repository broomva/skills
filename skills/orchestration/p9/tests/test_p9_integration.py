"""Integration tests for p9 — full lifecycle scenarios.

These tests exercise the complete state machine through realistic flows:
push → watch → green/red → heal → merge-ready. External `gh` calls are
mocked at the subprocess level (tests do not hit GitHub).
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
_FIXTURES = _HERE / "fixtures"
sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    """Fresh p9 import with tmpdir state and good policy fixture."""
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


class _FakePopen:
    """Minimal Popen stand-in that exits with a configured code."""

    def __init__(self, returncode: int = 0):
        self._returncode = returncode
        self.pid = 99999  # always alive from kill(0)'s perspective

    def poll(self):
        return self._returncode

    def wait(self):
        return self._returncode


class _FakeRun:
    """Configurable stand-in for subprocess.run."""

    def __init__(self, *, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


# ─────────────────────────────────────────────────────────────────────────────
# Full happy-path lifecycle
# ─────────────────────────────────────────────────────────────────────────────
class TestHappyPath:
    def test_full_lifecycle_via_state_events(self, p9):
        """PUSHED → WATCHING → GREEN → MERGE_READY → MERGED, end-to-end."""
        # 1. watch (dry-run avoids real subprocess)
        rc = p9.main(["watch", "100", "--repo", "broomva/test", "--dry-run", "--json"])
        assert rc == 0
        assert p9.current_pr_state(100) == p9.PRState.WATCHING

        # 2. simulate green
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-05-04T19:00:00+00:00",
            pr=100, repo="broomva/test",
            from_state=p9.PRState.WATCHING.value,
            to_state=p9.PRState.GREEN.value,
            watcher_id="w100",
        ))

        # 3. merge-ready (CLI command). --no-verify: this is a state-machine
        # lifecycle test, not a gh-verdict test (the merge_ready_verdict gate is
        # covered in test_p9_merge_verdict.py).
        rc = p9.main(["merge-ready", "100", "--repo", "broomva/test", "--no-verify"])
        assert rc == 0
        assert p9.current_pr_state(100) == p9.PRState.MERGE_READY

        # 4. simulate metalayer merge
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-05-04T19:01:00+00:00",
            pr=100, repo="broomva/test",
            from_state=p9.PRState.MERGE_READY.value,
            to_state=p9.PRState.MERGED.value,
            watcher_id="w100",
        ))

        # 5. PR is no longer in flight
        assert all(r["pr"] != 100 for r in p9.open_prs())

    def test_merge_ready_rejects_non_green(self, p9, capsys):
        """merge-ready requires the PR to be in GREEN state."""
        # PR in WATCHING state, not GREEN
        p9.append_state_event(p9.PRStateEvent(
            ts="2026-05-04T19:00:00+00:00",
            pr=200, repo="broomva/test",
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="w200",
        ))
        rc = p9.main(["merge-ready", "200", "--repo", "broomva/test"])
        assert rc == p9.EXIT_DEGRADED
        # No transition to MERGE_READY
        assert p9.current_pr_state(200) == p9.PRState.WATCHING


# ─────────────────────────────────────────────────────────────────────────────
# Self-heal flow
# ─────────────────────────────────────────────────────────────────────────────
class TestHealFlow:
    def test_classify_lint_log_via_cli(self, p9, capsys):
        rc = p9.main([
            "heal", "300", "--classify",
            "--log-file", str(_FIXTURES / "failures" / "lint.txt"),
        ])
        assert rc == 0
        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["failure_type"] == "lint"
        assert result["classified"] is True
        assert result["heal_command"] is not None

    def test_classify_unclassified_returns_no_heal(self, p9, capsys):
        rc = p9.main([
            "heal", "301", "--classify",
            "--log-file", str(_FIXTURES / "failures" / "unclassified.txt"),
        ])
        assert rc == 0
        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["failure_type"] == "unclassified"
        assert result["heal_command"] is None

    def test_heal_attempt_counter_via_state_events(self, p9):
        """After multiple failed heal cycles, evaluator stalls and forces ESCALATED."""
        scores = []
        prev_sig = None
        for attempt in range(1, 4):
            curr_sig = "stuck-signature"  # not changing → no progress
            ev = p9.evaluate(
                attempt=attempt,
                max_attempts=5,
                classifier_confidence=0.7,
                prev_signature=prev_sig,
                curr_signature=curr_sig,
                prev_failure_count=3,
                curr_failure_count=3,  # not decreasing
                stability_floor=0.3,
            )
            scores.append(ev.progress_score)
            prev_sig = curr_sig
        # After 3 attempts with no signature change and no failure decrease,
        # last two scores should be below floor → stall trigger.
        assert p9.stalled_for_two_cycles(scores, stability_floor=0.3)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-PR concurrency
# ─────────────────────────────────────────────────────────────────────────────
class TestMultiPR:
    def test_max_one_blocks_second_watch(self, p9, capsys, tmp_path, monkeypatch):
        # Default policy fixture has max_concurrent_prs=1
        rc = p9.main(["watch", "400", "--repo", "broomva/test", "--dry-run"])
        assert rc == 0

        rc = p9.main(["watch", "401", "--repo", "broomva/test", "--dry-run"])
        assert rc == p9.EXIT_CONCURRENCY_CEILING

    def test_max_two_allows_pair(self, p9, tmp_path, monkeypatch):
        # Write a per-test policy with max_concurrent_prs=2
        pol = tmp_path / "policy-2.yaml"
        pol.write_text((_FIXTURES / "policy-good.yaml").read_text(encoding="utf-8")
                       .replace("max_concurrent_prs: 1",
                                "max_concurrent_prs: 2"), encoding="utf-8")
        monkeypatch.setenv("BROOMVA_P9_POLICY", str(pol))
        # Re-import to pick up env
        if "p9" in sys.modules:
            del sys.modules["p9"]
        p9b = importlib.import_module("p9")

        assert p9b.main(["watch", "500", "--repo", "broomva/test", "--dry-run"]) == 0
        assert p9b.main(["watch", "501", "--repo", "broomva/test", "--dry-run"]) == 0
        # Third blocked
        assert p9b.main(
            ["watch", "502", "--repo", "broomva/test", "--dry-run"]
        ) == p9b.EXIT_CONCURRENCY_CEILING


# ─────────────────────────────────────────────────────────────────────────────
# Wait-queue end-to-end
# ─────────────────────────────────────────────────────────────────────────────
class TestWaitQueueLifecycle:
    def test_full_drain_cycle(self, p9, capsys):
        # Push from each source
        for src in ["session", "memory", "graph", "docs", "linear"]:
            rc = p9.main(["wait-queue", "push", "--source", src, "--item", f"task-{src}"])
            assert rc == 0
            capsys.readouterr()  # drain output

        # List in priority order
        rc = p9.main(["wait-queue", "list", "--json"])
        assert rc == 0
        items = json.loads(capsys.readouterr().out)
        sources = [it["source"] for it in items]
        assert sources == ["session", "memory", "graph", "docs", "linear"]

        # Drain all via pop
        for expected in sources:
            rc = p9.main(["wait-queue", "pop"])
            assert rc == 0
            head = json.loads(capsys.readouterr().out)
            assert head["source"] == expected

        # Empty
        rc = p9.main(["wait-queue", "pop"])
        assert rc == 0
        assert "(empty)" in capsys.readouterr().out

    def test_clear_drops_all(self, p9, capsys):
        for src in ["session", "memory", "graph"]:
            p9.main(["wait-queue", "push", "--source", src, "--item", "x"])
            capsys.readouterr()
        rc = p9.main(["wait-queue", "clear"])
        assert rc == 0
        assert "cleared 3 item" in capsys.readouterr().out


# ─────────────────────────────────────────────────────────────────────────────
# Events tail with --since filter
# ─────────────────────────────────────────────────────────────────────────────
class TestEventsTail:
    def test_tail_returns_state_jsonl_rows(self, p9, capsys):
        p9.main(["watch", "600", "--repo", "broomva/test", "--dry-run"])
        capsys.readouterr()
        rc = p9.main(["events", "tail"])
        assert rc == 0
        out = capsys.readouterr().out.strip().splitlines()
        assert any("PUSHED" in line for line in out)
        assert any("WATCHING" in line for line in out)


# ─────────────────────────────────────────────────────────────────────────────
# Doctor degraded states
# ─────────────────────────────────────────────────────────────────────────────
class TestDoctor:
    def test_doctor_passes_with_good_setup(self, p9, capsys):
        rc = p9.main(["doctor"])
        # gh may or may not be authed in test env — we accept either ok or
        # degraded for non-policy reasons. Policy MUST be ok.
        out = capsys.readouterr().out
        assert "policy:" not in out  # no policy issues
        assert rc in (p9.EXIT_OK, p9.EXIT_DEGRADED)

    def test_doctor_fails_closed_on_missing_policy_block(
        self, tmp_path, monkeypatch, capsys,
    ):
        monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
        monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-missing-ci-watch.yaml"))
        if "p9" in sys.modules:
            del sys.modules["p9"]
        mod = importlib.import_module("p9")
        rc = mod.main(["doctor"])
        out = capsys.readouterr().out
        assert "policy:" in out
        assert rc == mod.EXIT_POLICY_ERROR


# ─────────────────────────────────────────────────────────────────────────────
# Subprocess-level mock of `gh` for spawn_watcher
# ─────────────────────────────────────────────────────────────────────────────
class TestSubprocessIntegration:
    def test_spawn_watcher_dry_run_returns_none(self, p9):
        proc = p9.spawn_watcher(700, "broomva/test", dry_run=True)
        assert proc is None

    def test_spawn_watcher_real_call_uses_gh_pr_checks_watch(self, p9, monkeypatch):
        captured = {}

        def fake_popen(cmd, *args, **kwargs):
            captured["cmd"] = cmd
            captured["new_session"] = kwargs.get("start_new_session")
            return _FakePopen(returncode=0)

        monkeypatch.setattr(p9.subprocess, "Popen", fake_popen)
        proc = p9.spawn_watcher(800, "broomva/test")
        assert proc is not None
        assert captured["cmd"][:5] == ["gh", "pr", "checks", "800", "--watch"]
        assert "--repo" in captured["cmd"] and "broomva/test" in captured["cmd"]
        assert captured["new_session"] is True

    def test_doctor_handles_gh_missing(self, p9, monkeypatch, capsys):
        def fake_run(cmd, *args, **kwargs):
            raise FileNotFoundError("gh not found")
        monkeypatch.setattr(p9.subprocess, "run", fake_run)
        rc = p9.main(["doctor"])
        out = capsys.readouterr().out
        assert "gh CLI not installed" in out
        assert rc == p9.EXIT_DEGRADED  # not ok, but not policy fail-closed
