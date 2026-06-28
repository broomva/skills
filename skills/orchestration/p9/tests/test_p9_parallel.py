"""Parallel-session safety tests for p9 (BRO-1529).

The single global state namespace used to collide whenever two agent sessions
ran concurrently: a global concurrency ceiling, bare-PR-number identity, and a
"context-scoped" wait-queue that was actually global. These tests pin the fix:
session-scoped identity, (repo, pr) keying, per-session ceiling, scoped queue,
liveness reaping, and watcher de-dup.
"""

from __future__ import annotations

import importlib
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
