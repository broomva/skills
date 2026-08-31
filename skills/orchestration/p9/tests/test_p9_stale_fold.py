"""The late-fold race: a superseded watcher's terminal write buries a live one.

BRO-2374. This is the defect that stalled broomva/skills#202 (BRO-2305) at
3/10 over two P20 rounds, and the reason its round-2 verdict named the exit
criterion as *"an atomic generation-and-process-identity protocol that rejects
stale folds"*.

The sequence, all legal transitions, no corruption anywhere:

1. watcher ``w1`` arms PR 42          -> row (WATCHING, w1)
2. ``--force`` supersedes it          -> row (ABANDONED, watch-supersede)
   and ``w2`` arms as the replacement -> row (WATCHING, w2)
3. ``w1``'s orphaned process finally exits and folds its own arm
                                      -> row (ABANDONED, w1)

Step 3 is a **stale write**. ``open_prs`` keys by ``(repo_key, pr)`` and keeps
the *last* row, so w1's late ABANDONED buries w2's live WATCHING. The key then
looks terminal, the ceiling counts zero, and it admits another watcher while
w2 is still running — unbounded accumulation on one PR.

Every individual write here is valid and legally ordered. The defect is that an
append-only log with last-row-wins semantics has **nowhere to express "write
only if the latest row for this key is still mine"**. That is a property of the
store, not of the supersede path, which is why fixing it inside ``--force``
(the approach #202 tried) relocated the failure instead of closing it.

The guard belongs in ``append_state_event`` — the one chokepoint all ten
writers pass through — as a compare-and-swap performed under a single lock
acquisition: read the latest row for the key and append only if this writer
still owns it.

The guard landed in ``append_state_event(only_if_owner=True)``: the read and
the append share one lock acquisition, and the write is dropped when the
latest row for the key carries a different ``watcher_id``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_FIXTURES = _HERE / "fixtures"
sys.path.insert(0, str(_HERE.parent / "scripts"))

REPO = "broomva/test"
PR = 42
SESSION = "S"


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    monkeypatch.setenv("BROOMVA_P9_REPO", REPO)
    monkeypatch.setenv("BROOMVA_P9_SESSION", SESSION)
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


def _event(p9, frm, to, watcher_id, *, pid=0, guarded=False):
    return p9.append_state_event(p9.PRStateEvent(
        ts=p9._utcnow(), pr=PR, repo=REPO,
        from_state=frm, to_state=to,
        watcher_id=watcher_id, session_id=SESSION, extra={"pid": pid},
    ), only_if_owner=guarded)


def _replay_supersede(p9, *, guarded):
    """Arm w1, supersede it, arm w2, then let w1's orphan fold late.

    ``guarded`` selects how the *last* write is made — the one ``cmd_watch``
    performs when its `gh` child finally exits. Everything before it is the
    ordinary unguarded path, because superseding is the one write whose whole
    purpose is to take the key from another watcher.

    Returns whether that final write landed.
    """
    W = p9.PRState.WATCHING.value
    A = p9.PRState.ABANDONED.value
    P = p9.PRState.PUSHED.value
    _event(p9, P, W, "w1", pid=1111)
    _event(p9, W, A, "watch-supersede")
    _event(p9, P, W, "w2", pid=2222)
    return _event(p9, W, A, "w1", guarded=guarded)   # <- the late fold


class TestGuardedFold:
    """What ``cmd_watch`` actually does: fold with ``only_if_owner=True``."""

    def test_late_fold_does_not_bury_the_live_watcher(self, p9):
        written = _replay_supersede(p9, guarded=True)
        assert written is False, "a superseded watcher's fold was accepted"
        live = [r for r in p9.open_prs(SESSION) if r["watcher_id"] == "w2"]
        assert live, (
            "w2 is still running (pid 2222) but a superseded watcher's late "
            "fold removed it from open_prs")

    def test_ceiling_still_counts_the_live_watcher(self, p9):
        _replay_supersede(p9, guarded=True)
        policy = p9.load_policy()
        with pytest.raises(p9.ConcurrencyCeilingError):
            p9.enforce_concurrency_ceiling(policy, session_id=SESSION, repo=REPO)

    def test_the_owner_can_still_fold_its_own_arm(self, p9):
        """The guard must not block the ordinary case it shares a path with."""
        W = p9.PRState.WATCHING.value
        A = p9.PRState.ABANDONED.value
        P = p9.PRState.PUSHED.value
        _event(p9, P, W, "w1", pid=1111)
        assert _event(p9, W, A, "w1", guarded=True) is True
        assert p9.open_prs(SESSION) == []

    def test_a_first_write_with_no_prior_row_is_not_stale(self, p9):
        """No row for the key means nothing to be stale against."""
        assert _event(p9, p9.PRState.PUSHED.value,
                      p9.PRState.WATCHING.value, "w1", guarded=True) is True


class TestUnguardedFoldStillRaces:
    """The guard is opt-in, and that is deliberate — pin what that costs.

    ``only_if_owner`` defaults to False so the supersede path, which exists to
    take a key from another watcher, keeps working. The price is that a caller
    that forgets the flag reproduces the original race, so it is pinned here
    rather than left as an unstated assumption.
    """

    def test_unguarded_late_fold_still_buries_the_live_watcher(self, p9):
        written = _replay_supersede(p9, guarded=False)
        assert written is True
        assert p9.open_prs(SESSION) == [], (
            "expected the unguarded path to still lose w2 — if this now holds "
            "the row, the guard became the default and this test is the stale one")


class TestNotADurabilityBug:
    def test_the_race_needs_no_corruption_to_occur(self, p9):
        """Guard against misreading this as a durability bug.

        Every row is valid JSON written through the normal path, and every
        transition is legal — ``append_state_event`` asserts that. A fix aimed
        at write durability or corruption recovery would not touch this defect.
        """
        _replay_supersede(p9, guarded=False)
        rows, dropped = p9.jsonl_read_all(p9.state_jsonl())
        assert dropped == 0
        assert len(rows) == 4
        assert [r["watcher_id"] for r in rows] == [
            "w1", "watch-supersede", "w2", "w1"]


class TestCmdWatchWiring:
    """The guard must be *wired in* at the fold, not merely available.

    Every other test here calls ``append_state_event`` directly, so a mutant
    that drops ``only_if_owner=True`` from ``cmd_watch`` would survive all of
    them. This drives the real command through a real fold.
    """

    @staticmethod
    def _superseding_proc(p9, rc=0):
        """A `gh` stand-in that loses the key while it is still running.

        ``wait()`` writes the supersede + replacement rows before returning,
        which is exactly the ordering that makes the caller's fold stale: the
        watcher was alive when it took the key and is not when it gives it up.
        """
        class _Proc:
            pid = 99999

            def wait(self_inner):
                for frm, to, wid, pid in (
                    (p9.PRState.WATCHING.value, p9.PRState.ABANDONED.value,
                     "watch-supersede", 0),
                    (p9.PRState.PUSHED.value, p9.PRState.WATCHING.value,
                     "w-replacement", 2222),
                ):
                    p9.append_state_event(p9.PRStateEvent(
                        ts=p9._utcnow(), pr=PR, repo=REPO,
                        from_state=frm, to_state=to, watcher_id=wid,
                        session_id=SESSION, extra={"pid": pid}))
                return rc

            def terminate(self_inner):
                pass

        return _Proc()

    def test_watch_drops_its_fold_when_superseded_mid_run(self, p9, monkeypatch,
                                                          capsys):
        monkeypatch.setattr(p9.subprocess, "Popen",
                            lambda *a, **kw: self._superseding_proc(p9))
        rc = p9.main(["watch", str(PR), "--repo", REPO])

        assert rc == p9.EXIT_DEGRADED, (
            "a watcher whose fold was rejected reported success")
        assert "superseded" in capsys.readouterr().err, (
            "the dropped fold was silent — that is the termination "
            "invariant's blind spot")

        live = [r for r in p9.open_prs(SESSION)
                if r["watcher_id"] == "w-replacement"]
        assert live, "cmd_watch's stale fold buried the live replacement"

    def test_watch_folds_normally_when_it_keeps_the_key(self, p9, monkeypatch):
        """The wiring must not break the ordinary path it sits on."""
        class _Proc:
            pid = 99999
            def wait(self_inner):
                return 0
            def terminate(self_inner):
                pass

        monkeypatch.setattr(p9.subprocess, "Popen", lambda *a, **kw: _Proc())
        assert p9.main(["watch", str(PR), "--repo", REPO]) == p9.EXIT_OK
        assert p9.current_pr_state(PR, REPO) is p9.PRState.GREEN
