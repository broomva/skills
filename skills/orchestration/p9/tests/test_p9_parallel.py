"""Parallel-session safety tests for p9 (BRO-1529).

The single global state namespace used to collide whenever two agent sessions
ran concurrently: a global concurrency ceiling, bare-PR-number identity, and a
"context-scoped" wait-queue that was actually global. These tests pin the fix:
session-scoped identity, (repo, pr) keying, per-session ceiling, scoped queue,
liveness reaping, and watcher de-dup.
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
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    # Hermetic repo identity (BRO-1988): pin a REAL repo — the regime
    # production actually runs in. Pinning tests to repo-less ("" / `-`) is
    # what hid the rearm mis-attribution blocker: the guard under test only
    # misbehaves once an ambient repo resolves.
    monkeypatch.setenv("BROOMVA_P9_REPO", "broomva/test")
    # Ensure no leaked session id from the ambient environment.
    monkeypatch.delenv("BROOMVA_P9_SESSION", raising=False)
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


def _watching(p9, pr, repo, session_id, *, pid=0, ts=None):
    """Append a WATCHING row directly for a given session."""
    p9.append_state_event(p9.PRStateEvent(
        ts=ts or p9._utcnow(), pr=pr, repo=repo,
        from_state=p9.PRState.PUSHED.value,
        to_state=p9.PRState.WATCHING.value,
        watcher_id=f"w{pr}", session_id=session_id,
        extra={"pid": pid},
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Session identity
# ─────────────────────────────────────────────────────────────────────────────
class TestSessionIdentity:
    def test_env_takes_precedence(self, p9, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_SESSION", "  agent-7 ")
        assert p9.current_session_id() == "agent-7"

    def test_fallback_is_stable_across_calls(self, p9):
        a = p9.current_session_id()
        b = p9.current_session_id()
        assert a == b
        assert a.startswith("default-")
        # Persisted to disk so a *separate* invocation resolves the same id.
        assert p9.session_default_id_path().read_text(encoding="utf-8").strip() == a

    def test_distinct_sessions_distinct_ids(self, p9, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        a = p9.current_session_id()
        monkeypatch.setenv("BROOMVA_P9_SESSION", "B")
        b = p9.current_session_id()
        assert a == "A" and b == "B"


# ─────────────────────────────────────────────────────────────────────────────
# Per-session ceiling (the headline collision)
# ─────────────────────────────────────────────────────────────────────────────
class TestPerSessionCeiling:
    def test_two_sessions_each_get_a_slot_under_ceiling_one(self, p9):
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")  # max_concurrent_prs=1
        _watching(p9, 100, "broomva/life", "A")
        # Session B is unaffected by A's in-flight PR.
        p9.enforce_concurrency_ceiling(cfg, session_id="B")  # must not raise
        # But A's own second watch is blocked.
        with pytest.raises(p9.ConcurrencyCeilingError):
            p9.enforce_concurrency_ceiling(cfg, session_id="A")

    def test_legacy_global_count_preserved_when_session_none(self, p9):
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")
        _watching(p9, 1, "broomva/x", "")  # legacy row, no session
        with pytest.raises(p9.ConcurrencyCeilingError):
            p9.enforce_concurrency_ceiling(cfg)  # session_id=None → counts all

    def test_legacy_row_does_not_block_a_real_session(self, p9):
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")
        _watching(p9, 1, "broomva/x", "")  # orphan with no owner
        p9.enforce_concurrency_ceiling(cfg, session_id="A")  # must not raise

    def test_cli_watch_two_sessions_then_self_block(self, p9, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        assert p9.main(["watch", "100", "--repo", "broomva/life", "--dry-run"]) == 0
        monkeypatch.setenv("BROOMVA_P9_SESSION", "B")
        assert p9.main(["watch", "200", "--repo", "broomva/life", "--dry-run"]) == 0
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        assert p9.main(
            ["watch", "101", "--repo", "broomva/life", "--dry-run"]
        ) == p9.EXIT_CONCURRENCY_CEILING


# ─────────────────────────────────────────────────────────────────────────────
# (repo, pr) composite identity
# ─────────────────────────────────────────────────────────────────────────────
class TestCompositeIdentity:
    def test_same_pr_number_two_repos_no_collision(self, p9):
        _watching(p9, 42, "broomva/life", "A")
        _watching(p9, 42, "broomva/broomva.tech", "A")
        open_ = p9.open_prs()
        assert len(open_) == 2
        repos = sorted(r["repo"] for r in open_)
        assert repos == ["broomva/broomva.tech", "broomva/life"]

    def test_current_pr_state_disambiguates_by_repo(self, p9):
        _watching(p9, 42, "broomva/life", "A")
        p9.append_state_event(p9.PRStateEvent(
            ts=p9._utcnow(), pr=42, repo="broomva/life",
            from_state=p9.PRState.WATCHING.value, to_state=p9.PRState.GREEN.value,
            watcher_id="w42", session_id="A",
        ))
        _watching(p9, 42, "broomva/broomva.tech", "A")
        assert p9.current_pr_state(42, "broomva/life") == p9.PRState.GREEN
        assert p9.current_pr_state(42, "broomva/broomva.tech") == p9.PRState.WATCHING


# ─────────────────────────────────────────────────────────────────────────────
# Wait-queue session scoping
# ─────────────────────────────────────────────────────────────────────────────
class TestQueueScoping:
    def test_pop_is_session_isolated(self, p9):
        p9.queue_push("A work", "graph", session_id="A")
        p9.queue_push("B work", "graph", session_id="B")
        a = p9.queue_pop("A")
        assert a is not None and a.item == "A work"
        # B's item is untouched.
        b_items = p9.queue_list("B")
        assert [it.item for it in b_items] == ["B work"]
        # A's queue is now empty (it never saw B's item).
        assert p9.queue_list("A") == []

    def test_list_all_sessions_sees_everything(self, p9):
        p9.queue_push("A work", "graph", session_id="A")
        p9.queue_push("B work", "graph", session_id="B")
        items = p9.queue_list(all_sessions=True)
        assert {it.item for it in items} == {"A work", "B work"}

    def test_legacy_unowned_items_visible_to_all(self, p9):
        p9.queue_push("legacy", "graph", session_id="")  # no owner
        assert [it.item for it in p9.queue_list("A")] == ["legacy"]
        assert [it.item for it in p9.queue_list("B")] == ["legacy"]

    def test_clear_is_exact_owner_only(self, p9):
        p9.queue_push("A work", "graph", session_id="A")
        p9.queue_push("B work", "graph", session_id="B")
        p9.queue_push("legacy", "graph", session_id="")
        removed = p9.queue_clear("A")
        assert removed == 1
        remaining = {it.item for it in p9.queue_list(all_sessions=True)}
        assert remaining == {"B work", "legacy"}  # B + legacy preserved


# ─────────────────────────────────────────────────────────────────────────────
# Wait-queue TTL / terminal-PR pruning
# ─────────────────────────────────────────────────────────────────────────────
class TestQueuePruning:
    def test_terminal_pr_item_pruned(self, p9):
        # PR 7 reaches a terminal state; a queue item tagged for it is moot.
        for prev, curr in [
            (p9.PRState.PUSHED, p9.PRState.WATCHING),
            (p9.PRState.WATCHING, p9.PRState.GREEN),
            (p9.PRState.GREEN, p9.PRState.MERGE_READY),
            (p9.PRState.MERGE_READY, p9.PRState.MERGED),
        ]:
            p9.append_state_event(p9.PRStateEvent(
                ts=p9._utcnow(), pr=7, repo="broomva/life",
                from_state=prev.value, to_state=curr.value,
                watcher_id="w7", session_id="A",
            ))
        p9.queue_push("moot", "graph", pr=7, repo="broomva/life", session_id="A")
        p9.queue_push("live", "graph", pr=8, repo="broomva/life", session_id="A")
        items = p9.queue_list("A")
        assert [it.item for it in items] == ["live"]

    def test_terminal_check_is_repo_scoped(self, p9):
        # PR 7 is terminal in life, but a queue item tagged for the SAME
        # number in a different repo must NOT be pruned (identity is (repo,pr)).
        for prev, curr in [
            (p9.PRState.PUSHED, p9.PRState.WATCHING),
            (p9.PRState.WATCHING, p9.PRState.GREEN),
            (p9.PRState.GREEN, p9.PRState.MERGE_READY),
            (p9.PRState.MERGE_READY, p9.PRState.MERGED),
        ]:
            p9.append_state_event(p9.PRStateEvent(
                ts=p9._utcnow(), pr=7, repo="broomva/life",
                from_state=prev.value, to_state=curr.value,
                watcher_id="w7", session_id="A",
            ))
        p9.queue_push("other-repo", "graph", pr=7,
                      repo="broomva/broomva.tech", session_id="A")
        p9.queue_push("no-repo", "graph", pr=7, session_id="A")  # repo unknown
        items = {it.item for it in p9.queue_list("A")}
        assert items == {"other-repo", "no-repo"}  # neither pruned

    def test_ttl_prunes_aged_items(self, p9, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_QUEUE_TTL_DAYS", "1")
        # Manually write an item created 3 days ago.
        old = p9.WaitQueueItem(
            id="old123", source="graph", item="stale",
            created_at="2026-01-01T00:00:00+00:00", session_id="A",
        )
        p9.jsonl_append(p9.wait_queue_jsonl(), old.to_jsonl(), p9.queue_lock_path())
        p9.queue_push("fresh", "graph", session_id="A")
        assert [it.item for it in p9.queue_list("A")] == ["fresh"]


# ─────────────────────────────────────────────────────────────────────────────
# Liveness reaping
# ─────────────────────────────────────────────────────────────────────────────
class TestReaping:
    def test_dead_pid_aged_row_reaped(self, p9):
        _watching(p9, 42, "broomva/life", "A", pid=999999,
                  ts="2026-01-01T00:00:00+00:00")  # aged, dead pid
        reaped = p9.reap_stale_watchers(reconcile=False)
        assert len(reaped) == 1
        assert p9.current_pr_state(42, "broomva/life") == p9.PRState.ABANDONED
        # Slot is freed.
        assert p9.open_prs() == []

    def test_live_pid_not_reaped(self, p9):
        _watching(p9, 42, "broomva/life", "A", pid=os.getpid(),
                  ts="2026-01-01T00:00:00+00:00")  # aged BUT alive
        reaped = p9.reap_stale_watchers(reconcile=False)
        assert reaped == []
        assert p9.current_pr_state(42, "broomva/life") == p9.PRState.WATCHING

    def test_fresh_dead_row_within_grace_not_reaped(self, p9):
        _watching(p9, 42, "broomva/life", "A", pid=999999)  # ts=now → fresh
        reaped = p9.reap_stale_watchers(reconcile=False)  # default grace 120s
        assert reaped == []

    def test_grace_zero_reaps_immediately(self, p9):
        _watching(p9, 42, "broomva/life", "A", pid=999999)  # fresh
        reaped = p9.reap_stale_watchers(reconcile=False, grace_seconds=0.0)
        assert len(reaped) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Watcher de-dup
# ─────────────────────────────────────────────────────────────────────────────
class TestWatcherDedup:
    def test_live_watcher_refused(self, p9, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        _watching(p9, 42, "broomva/life", "A", pid=os.getpid())  # alive
        rc = p9.main(["watch", "42", "--repo", "broomva/life", "--dry-run"])
        assert rc == p9.EXIT_DEGRADED

    def test_force_supersedes_live_watcher(self, p9, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        _watching(p9, 42, "broomva/life", "A", pid=os.getpid())
        rc = p9.main(["watch", "42", "--repo", "broomva/life", "--dry-run", "--force"])
        assert rc == 0

    def test_dead_fresh_row_needs_adopt(self, p9, monkeypatch):
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        _watching(p9, 42, "broomva/life", "A", pid=999999)  # dead but fresh
        # Without --adopt: refused (fold may still land).
        assert p9.main(
            ["watch", "42", "--repo", "broomva/life", "--dry-run"]
        ) == p9.EXIT_DEGRADED
        # With --adopt: supersede and re-watch.
        assert p9.main(
            ["watch", "42", "--repo", "broomva/life", "--dry-run", "--adopt"]
        ) == 0


# ─────────────────────────────────────────────────────────────────────────────
# heal --apply (serialized via heal.lock)
# ─────────────────────────────────────────────────────────────────────────────
class TestHealApply:
    def test_apply_dry_run_shows_command(self, p9, capsys):
        rc = p9.main(["heal", "42", "--apply", "--dry-run", "--log-file",
                      str(_FIXTURES / "failures" / "lint.txt")])
        assert rc == 0
        out = capsys.readouterr().out
        assert '"would_run"' in out and '"applied": false' in out

    def test_apply_refuses_unclassifiable(self, p9, capsys):
        rc = p9.main(["heal", "42", "--apply", "--log-file",
                      str(_FIXTURES / "failures" / "unclassified.txt")])
        assert rc == p9.EXIT_DEGRADED
        out = capsys.readouterr().out
        assert "escalate" in out

    # Run-scoped heals (runner_admission_timeout). policy-good.yaml predates the
    # type, so these tests pin a policy that allows it unless they test refusal.
    @pytest.fixture
    def allow_admission(self, monkeypatch, tmp_path):
        pol = tmp_path / "policy.yaml"
        pol.write_text((_FIXTURES / "policy-good.yaml").read_text().replace(
            "classified_failure_types: [lint, format, test_flaky, codegen_drift, import_missing]",
            "classified_failure_types: [lint, runner_admission_timeout]"))
        assert "runner_admission_timeout" in pol.read_text()
        monkeypatch.setenv("BROOMVA_P9_POLICY", str(pol))

    _ADMISSION = str(_FIXTURES / "failures" / "runner_admission_timeout.txt")

    def test_run_scoped_heal_refuses_without_run_id(self, p9, capsys, allow_admission):
        rc = p9.main(["heal", "42", "--apply", "--dry-run", "--log-file", self._ADMISSION])
        assert rc == p9.EXIT_DEGRADED
        assert "needs the failing run id" in capsys.readouterr().out

    def test_policy_that_omits_the_type_refuses(self, p9, capsys):
        # policy-good.yaml lists the five original types only.
        rc = p9.main(["heal", "42", "--apply", "--dry-run", "--run-id", "111",
                      "--log-file", self._ADMISSION])
        assert rc == p9.EXIT_DEGRADED
        assert "does not allow 'runner_admission_timeout'" in capsys.readouterr().out

    def test_run_scoped_heal_expands_each_run_id(self, p9, capsys, allow_admission):
        rc = p9.main(["heal", "42", "--apply", "--dry-run", "--repo", "o/r",
                      "--run-id", "111", "--run-id", "222", "--log-file", self._ADMISSION])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["would_run"] == ["gh run rerun 111 --failed --repo o/r",
                                    "gh run rerun 222 --failed --repo o/r"]

    def test_run_scoped_heal_runs_every_run_and_reports_failure(
            self, p9, monkeypatch, capsys, allow_admission):
        import subprocess as _sp
        ran = []

        def fake_run(cmd, *a, **kw):
            if isinstance(cmd, str) and cmd.startswith("gh run rerun"):
                ran.append(cmd)
                return _sp.CompletedProcess(cmd, 1 if "111" in cmd else 0)
            raise AssertionError(f"unexpected command {cmd!r}")

        monkeypatch.setattr(p9.subprocess, "run", fake_run)
        rc = p9.main(["heal", "42", "--apply", "--run-id", "111", "--run-id", "222",
                      "--log-file", self._ADMISSION])
        assert ran == ["gh run rerun 111 --failed", "gh run rerun 222 --failed"]
        assert rc == p9.EXIT_DEGRADED
        assert json.loads(capsys.readouterr().out)["heal_exit_code"] == 1

    def test_live_ids_flow_into_apply(self, p9, monkeypatch, capsys, allow_admission):
        log = (_FIXTURES / "failures" / "runner_admission_timeout.txt").read_text()
        monkeypatch.setattr(p9, "_gh_log_failed",
                            lambda pr, repo: ({"111": log, "222": log}, None))
        rc = p9.main(["heal", "42", "--repo", "o/r", "--apply", "--dry-run"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["source"] == "live" and out["run_ids"] == ["111", "222"]
        assert out["would_run"] == ["gh run rerun 111 --failed --repo o/r",
                                    "gh run rerun 222 --failed --repo o/r"]

    def test_one_timeout_does_not_mask_a_real_failure(self, p9, monkeypatch, capsys,
                                                      allow_admission):
        # Run 111 timed out on admission; run 222 has a type error. Classified
        # together, the 0.8 admission match used to win and "heal" the PR.
        admission = (_FIXTURES / "failures" / "runner_admission_timeout.txt").read_text()
        type_err = (_FIXTURES / "failures" / "type.txt").read_text()
        monkeypatch.setattr(p9, "_gh_log_failed",
                            lambda pr, repo: ({"111": admission, "222": type_err}, None))
        rc = p9.main(["heal", "42", "--repo", "o/r", "--apply", "--dry-run"])
        assert rc == p9.EXIT_DEGRADED
        out = json.loads(capsys.readouterr().out)
        assert out["classified"] is False and out["commands"] == []
        assert "111=runner_admission_timeout" in out["rationale"]
        assert "222=type" in out["rationale"]

    def test_fetch_failure_is_reported_not_unclassified(self, p9, monkeypatch, capsys):
        monkeypatch.setattr(p9, "_gh_log_failed",
                            lambda pr, repo: ({}, "gh pr checks failed: HTTP 401"))
        rc = p9.main(["heal", "42", "--repo", "o/r", "--classify"])
        assert rc == p9.EXIT_DEGRADED
        out = json.loads(capsys.readouterr().out)
        assert out["failure_type"] == "unavailable" and "HTTP 401" in out["reason"]

    def test_classify_shows_expanded_commands(self, p9, monkeypatch, capsys):
        log = (_FIXTURES / "failures" / "runner_admission_timeout.txt").read_text()
        monkeypatch.setattr(p9, "_gh_log_failed", lambda pr, repo: ({"111": log}, None))
        assert p9.main(["heal", "42", "--repo", "o/r", "--classify"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["commands"] == ["gh run rerun 111 --failed --repo o/r"]

    def test_live_mode_reads_the_prs_failing_runs(self, p9, monkeypatch):
        import subprocess as _sp
        checks = json.dumps([
            {"bucket": "fail", "link": "https://github.com/o/r/actions/runs/111/job/9"},
            {"bucket": "pass", "link": "https://github.com/o/r/actions/runs/333/job/1"},
            {"bucket": "fail", "link": "https://github.com/o/r/actions/runs/111/job/10"},
            {"bucket": "fail", "link": "https://github.com/o/r/actions/runs/222/job/3"},
            {"bucket": "fail", "link": "https://github.com/other/repo/actions/runs/999/job/1"},
            {"bucket": "fail", "link": "https://evil.example/o/r/actions/runs/888/"},
            {"bucket": "fail", "link": "https://coderabbit.ai/x"},
        ])
        seen = []

        def fake_run(cmd, *a, **kw):
            seen.append(cmd)
            if cmd[:3] == ["gh", "pr", "checks"]:
                return _sp.CompletedProcess(cmd, 1, stdout=checks, stderr="")
            if cmd[:3] == ["gh", "run", "view"]:
                return _sp.CompletedProcess(cmd, 0, stdout=f"log of {cmd[3]}", stderr="")
            raise AssertionError(f"unexpected command {cmd!r}")

        monkeypatch.setattr(p9.subprocess, "run", fake_run)
        logs, err = p9._gh_log_failed(42, "o/r")
        assert err is None
        assert logs == {"111": "log of 111", "222": "log of 222"}
        assert ["gh", "pr", "checks", "42", "--json", "bucket,link", "--repo", "o/r"] in seen

    def test_classify_without_tty_still_reads_the_pr(self, p9, monkeypatch, capsys):
        # Agents run with a non-TTY stdin; that must not replace the live read.
        import io
        monkeypatch.setattr(p9.sys, "stdin", io.StringIO(""))
        log = (_FIXTURES / "failures" / "runner_admission_timeout.txt").read_text()
        monkeypatch.setattr(p9, "_gh_log_failed", lambda pr, repo: ({"111": log}, None))
        assert p9.main(["heal", "42", "--repo", "o/r", "--classify"]) == 0
        assert json.loads(capsys.readouterr().out)["failure_type"] == "runner_admission_timeout"

    def test_log_file_dash_reads_stdin(self, p9, monkeypatch, capsys):
        import io
        log = (_FIXTURES / "failures" / "lint.txt").read_text()
        monkeypatch.setattr(p9.sys, "stdin", io.StringIO(log))
        assert p9.main(["heal", "42", "--classify", "--log-file", "-"]) == 0
        assert json.loads(capsys.readouterr().out)["failure_type"] == "lint"

    def test_apply_runs_under_lock(self, p9, monkeypatch):
        # Stub the heal command to a trivially-true classified result by
        # pointing the classifier at lint and replacing the heal exec with `true`.
        import subprocess as _sp
        orig_run = _sp.run

        captured = {}

        def fake_run(cmd, *a, **kw):
            if cmd == "bun run lint:fix":
                captured["ran"] = True
                return _sp.CompletedProcess(cmd, 0)
            return orig_run(cmd, *a, **kw)

        monkeypatch.setattr(p9.subprocess, "run", fake_run)
        rc = p9.main(["heal", "42", "--apply", "--log-file",
                      str(_FIXTURES / "failures" / "lint.txt")])
        assert rc == 0
        assert captured.get("ran") is True
