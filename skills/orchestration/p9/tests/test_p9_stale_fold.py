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
import json
import os
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


def _event(p9, frm, to, watcher_id, *, pid=0, guarded=False, expect=None):
    """`guarded=True` expects `expect` (default: this event's own watcher)."""
    kw = {}
    if guarded:
        kw["expect_owner"] = watcher_id if expect is None else expect
    return p9.append_state_event(p9.PRStateEvent(
        ts=p9._utcnow(), pr=PR, repo=REPO,
        from_state=frm, to_state=to,
        watcher_id=watcher_id, session_id=SESSION, extra={"pid": pid},
    ), **kw)


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

    def test_a_guarded_write_with_no_prior_row_is_refused(self, p9):
        """Fail-closed: a writer with no row cannot prove it owns the key.

        An earlier revision failed *open* here ("nothing to be stale
        against"), which contradicted the contract one line above it: if the
        log was rotated or truncated while an orphan watcher ran, that watcher
        would recreate the key with a terminal fold.
        """
        assert _event(p9, p9.PRState.PUSHED.value,
                      p9.PRState.WATCHING.value, "w1", guarded=True) is False


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


OTHER_REPO = "broomva/other"


class TestCasKeyIsRepoAndPr:
    """The CAS owner lookup keys on ``(repo, pr)``, not the bare number.

    BRO-1988 established that identity; a guard that forgets it would let one
    repo's watcher reject another repo's fold for the same PR number. Every
    other test here runs in a single repo, so that mutation is unreachable
    from them — this is the case that reaches it.
    """

    @staticmethod
    def _ev(p9, repo, frm, to, wid, *, guarded=False, pid=0):
        kw = {"expect_owner": wid} if guarded else {}
        return p9.append_state_event(p9.PRStateEvent(
            ts=p9._utcnow(), pr=PR, repo=repo,
            from_state=frm, to_state=to, watcher_id=wid,
            session_id=SESSION, extra={"pid": pid},
        ), **kw)

    def test_another_repos_row_does_not_reject_this_folds(self, p9):
        W = p9.PRState.WATCHING.value
        A = p9.PRState.ABANDONED.value
        P = p9.PRState.PUSHED.value
        # Same PR number, two repos, two watchers. Order matters: the OTHER
        # repo's row is written LAST, so a lookup that ignores repo reads
        # `w-here` as the owner and wrongly rejects `w-there`'s own fold.
        # Written the other way round, both implementations agree and the test
        # proves nothing — which is how the first version of it let the mutant
        # survive.
        self._ev(p9, OTHER_REPO, P, W, "w-there", pid=2222)
        self._ev(p9, REPO, P, W, "w-here", pid=1111)
        assert self._ev(p9, OTHER_REPO, W, A, "w-there", guarded=True) is True
        # And the other repo's watcher is untouched.
        assert p9.current_pr_state(PR, REPO) is p9.PRState.WATCHING

    def test_this_repos_stale_fold_is_still_rejected(self, p9):
        """Negative control: the repo filter must not make the guard vacuous."""
        W = p9.PRState.WATCHING.value
        A = p9.PRState.ABANDONED.value
        P = p9.PRState.PUSHED.value
        self._ev(p9, REPO, P, W, "w1", pid=1111)
        self._ev(p9, OTHER_REPO, P, W, "w-there", pid=3333)
        self._ev(p9, REPO, W, A, "watch-supersede")
        self._ev(p9, REPO, P, W, "w2", pid=2222)
        assert self._ev(p9, REPO, W, A, "w1", guarded=True) is False


def _cas_contender(scripts, home, wid, q):
    """Run in a CHILD PROCESS — must re-import p9 with its own env."""
    import os
    import sys as _sys
    _sys.path.insert(0, scripts)
    os.environ.update(BROOMVA_P9_HOME=home, BROOMVA_P9_REPO=REPO,
                      BROOMVA_P9_SESSION=SESSION)
    for m in ("p9",):
        _sys.modules.pop(m, None)
    import p9 as mod
    q.put((wid, mod.append_state_event(mod.PRStateEvent(
        ts=mod._utcnow(), pr=PR, repo=REPO,
        from_state=mod.PRState.WATCHING.value,
        to_state=mod.PRState.ABANDONED.value,
        watcher_id=wid, session_id=SESSION, extra={}),
        expect_owner=wid)))   # each claims to own the key itself


class TestCasUnderRealConcurrency:
    """The guard's whole claim is atomicity against *other processes*.

    In-process tests cannot observe that: they never contend for the flock.
    This spawns real processes so the lock is actually exercised.
    """

    def test_exactly_one_contender_wins_and_no_row_is_torn(self, p9, tmp_path):
        import multiprocessing as mp

        p9.append_state_event(p9.PRStateEvent(
            ts=p9._utcnow(), pr=PR, repo=REPO,
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id="w-owner", session_id=SESSION, extra={"pid": 1}))

        scripts = str(_HERE.parent / "scripts")
        home = str(tmp_path)
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        # 12 contenders, exactly one of which is the genuine owner.
        names = ["w-owner"] + [f"w{i}" for i in range(1, 12)]
        procs = [ctx.Process(target=_cas_contender,
                             args=(scripts, home, n, q)) for n in names]
        for pr_ in procs:
            pr_.start()
        for pr_ in procs:
            pr_.join(timeout=60)

        results = [q.get() for _ in names]
        winners = sorted(w for w, ok in results if ok)
        assert winners == ["w-owner"], (
            f"expected only the owner to win the CAS, got {winners}")

        rows, dropped = p9.jsonl_read_all(p9.state_jsonl())
        assert dropped == 0, "a concurrent write tore a row"
        assert len(rows) == 2, f"expected arm + one fold, got {len(rows)} rows"


class TestEverySnapshotDerivedTransitionIsGuarded:
    """``cmd_watch`` was not the only read-then-append transition.

    Each of these reads a row (or a state) and appends a result some time
    later; if the key changed hands in between, the append buries a live
    owner. The windows differ in width — ``merge-ready`` straddles a network
    round-trip, which is the widest one in the file.
    """

    @staticmethod
    def _arm(p9, wid, *, pid, repo=REPO, pr=PR):
        p9.append_state_event(p9.PRStateEvent(
            ts="2020-01-01T00:00:00+00:00", pr=pr, repo=repo,
            from_state=p9.PRState.PUSHED.value,
            to_state=p9.PRState.WATCHING.value,
            watcher_id=wid, session_id=SESSION, extra={"pid": pid}))

    def test_reap_does_not_fold_a_replacement_it_never_saw(self, p9, monkeypatch):
        """`reap` reads a dead watcher's row, then writes. A `watch --adopt`
        landing in between must not be folded terminal on the dead pid."""
        self._arm(p9, "w-dead", pid=999999)          # long-dead pid, aged row

        real = p9.open_prs
        def racing_open_prs(*a, **kw):
            rows = real(*a, **kw)
            # The replacement lands after reap took its snapshot.
            self._arm(p9, "w-live", pid=os.getpid())
            monkeypatch.setattr(p9, "open_prs", real)
            return rows
        monkeypatch.setattr(p9, "open_prs", racing_open_prs)

        p9.reap_stale_watchers(grace_seconds=0, reconcile=False)
        assert p9.current_pr_state(PR, REPO) is p9.PRState.WATCHING, (
            "reap folded the live replacement it never observed")
        assert p9.latest_row(PR, REPO)["watcher_id"] == "w-live"

    def test_merge_ready_refuses_when_the_key_changed_hands(self, p9,
                                                            monkeypatch, capsys):
        """The verdict is a network call; a re-arm during it must not be
        overwritten with MERGE_READY."""
        self._arm(p9, "w1", pid=1111)
        p9.append_state_event(p9.PRStateEvent(
            ts=p9._utcnow(), pr=PR, repo=REPO,
            from_state=p9.PRState.WATCHING.value,
            to_state=p9.PRState.GREEN.value,
            watcher_id="w1", session_id=SESSION, extra={}))

        def racing_verdict(pr_, repo_):
            # A SECOND `merge-ready` lands while we are talking to GitHub and
            # takes the key. GREEN -> MERGE_READY is the only legal move out
            # of GREEN, so this is what the race actually looks like.
            p9.append_state_event(p9.PRStateEvent(
                ts=p9._utcnow(), pr=PR, repo=REPO,
                from_state=p9.PRState.GREEN.value,
                to_state=p9.PRState.MERGE_READY.value,
                watcher_id="merge-ready-other", session_id=SESSION, extra={}))
            return {"ready": True, "reason": "ok", "state": "CLEAN",
                    "unresolved_threads": 0}
        monkeypatch.setattr(p9, "merge_ready_verdict", racing_verdict)

        rc = p9.main(["merge-ready", str(PR), "--repo", REPO])
        assert rc == p9.EXIT_DEGRADED
        assert "changed hands" in capsys.readouterr().err
        rows = [r for r in p9.jsonl_read_all(p9.state_jsonl())[0]
                if r["pr"] == PR]
        assert [r["watcher_id"] for r in rows][-1] == "merge-ready-other", (
            "a second MERGE_READY was appended on top of the one that won the "
            "race — two actors would each believe they authorized the merge")

    def test_the_ordinary_paths_still_work(self, p9, monkeypatch):
        """Negative control: the guards must not break the uncontended case."""
        self._arm(p9, "w1", pid=1111)
        p9.append_state_event(p9.PRStateEvent(
            ts=p9._utcnow(), pr=PR, repo=REPO,
            from_state=p9.PRState.WATCHING.value,
            to_state=p9.PRState.GREEN.value,
            watcher_id="w1", session_id=SESSION, extra={}))
        monkeypatch.setattr(p9, "merge_ready_verdict",
                            lambda *a: {"ready": True, "reason": "ok",
                                        "state": "CLEAN",
                                        "unresolved_threads": 0})
        assert p9.main(["merge-ready", str(PR), "--repo", REPO]) == p9.EXIT_OK
        assert p9.current_pr_state(PR, REPO) is p9.PRState.MERGE_READY


class TestRejectedFoldDoesNotSwallowTheCrash:
    """A dropped fold must not eat the exception that caused it.

    Round 1 of this change returned ``EXIT_DEGRADED`` from the rejection
    branch, which sits *above* ``if reraise is not None: raise reraise`` — so a
    watcher that crashed **and** was superseded reported a tidy degraded exit
    and lost the crash entirely. Reordering alone is invisible to every other
    test here, so it is pinned directly.
    """

    def test_a_crash_propagates_even_when_the_fold_is_rejected(self, p9,
                                                               monkeypatch):
        boom = RuntimeError("gh died")

        class _Proc:
            pid = 99999

            def wait(self_inner):
                # Lose the key first, then crash: both conditions at once.
                p9.append_state_event(p9.PRStateEvent(
                    ts=p9._utcnow(), pr=PR, repo=REPO,
                    from_state=p9.PRState.WATCHING.value,
                    to_state=p9.PRState.ABANDONED.value,
                    watcher_id="watch-supersede", session_id=SESSION, extra={}))
                p9.append_state_event(p9.PRStateEvent(
                    ts=p9._utcnow(), pr=PR, repo=REPO,
                    from_state=p9.PRState.PUSHED.value,
                    to_state=p9.PRState.WATCHING.value,
                    watcher_id="w-live", session_id=SESSION,
                    extra={"pid": 2222}))
                raise boom

            def terminate(self_inner):
                pass

        monkeypatch.setattr(p9.subprocess, "Popen", lambda *a, **kw: _Proc())
        with pytest.raises(RuntimeError, match="gh died"):
            p9.main(["watch", str(PR), "--repo", REPO])

        # ...and the live replacement is still intact.
        assert p9.latest_row(PR, REPO)["watcher_id"] == "w-live"


class TestNullOwnerRows:
    """A row may carry ``watcher_id: null``, and both sides must agree.

    Folding "no row" and "row with a null owner" into one nullable value got
    each one wrong in opposite directions: a vanished key compared equal to a
    null expectation and failed OPEN, while a stored null stringified to
    ``"None"`` and could never match the ``None`` a caller read off the row —
    making such a row permanently unreapable.
    """

    @staticmethod
    def _raw_row(p9, watcher_id, state="WATCHING"):
        """Write a row directly, bypassing the dataclass, so `watcher_id` can
        be genuinely null the way a hand-edited or older log has it."""
        row = {"ts": "2020-01-01T00:00:00+00:00", "pr": PR, "repo": REPO,
               "from_state": "PUSHED", "to_state": state,
               "watcher_id": watcher_id, "attempt": 0, "evaluator_score": None,
               "extra": {"pid": 999999}, "session_id": SESSION}
        p9.jsonl_append(p9.state_jsonl(), json.dumps(row), p9.state_lock_path())

    def test_a_null_owner_row_can_still_be_folded(self, p9):
        """The reap path must not be permanently blocked by a null owner."""
        self._raw_row(p9, None)
        row = p9.latest_row(PR, REPO)
        assert p9.append_state_event(p9.PRStateEvent(
            ts=p9._utcnow(), pr=PR, repo=REPO,
            from_state=p9.PRState.WATCHING.value,
            to_state=p9.PRState.ABANDONED.value,
            watcher_id="reap", session_id=SESSION, extra={}),
            expect_owner=p9._owner_of(row)) is True

    def test_a_missing_owner_field_normalizes_the_same_as_null(self, p9):
        assert p9._owner_of({}) == p9._owner_of({"watcher_id": None}) == ""

    def test_a_vanished_key_never_fails_open(self, p9):
        """Nothing on disk at all: no expectation may be satisfied."""
        for expectation in ("", "w1", "reap"):
            assert p9.append_state_event(p9.PRStateEvent(
                ts=p9._utcnow(), pr=PR, repo=REPO,
                from_state=p9.PRState.WATCHING.value,
                to_state=p9.PRState.ABANDONED.value,
                watcher_id="orphan", session_id=SESSION, extra={}),
                expect_owner=expectation) is False, (
                f"expect_owner={expectation!r} resurrected a key with no row")
