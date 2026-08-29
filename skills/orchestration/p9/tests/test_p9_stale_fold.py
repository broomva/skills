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

``xfail(strict=True)`` is deliberate: when the CAS guard lands, this test
starts passing and *strict* xfail turns that into a failure, so the marker
cannot outlive the bug.
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


def _event(p9, frm, to, watcher_id, *, pid=0):
    p9.append_state_event(p9.PRStateEvent(
        ts=p9._utcnow(), pr=PR, repo=REPO,
        from_state=frm, to_state=to,
        watcher_id=watcher_id, session_id=SESSION, extra={"pid": pid},
    ))


def _replay_supersede(p9):
    """Arm w1, supersede it, arm w2, then let w1's orphan fold late."""
    W = p9.PRState.WATCHING.value
    A = p9.PRState.ABANDONED.value
    P = p9.PRState.PUSHED.value
    _event(p9, P, W, "w1", pid=1111)
    _event(p9, W, A, "watch-supersede")
    _event(p9, P, W, "w2", pid=2222)
    _event(p9, W, A, "w1")          # <- the stale write


@pytest.mark.xfail(strict=True, reason="BRO-2374: no CAS on terminal folds")
def test_late_fold_does_not_bury_the_live_watcher(p9):
    _replay_supersede(p9)
    live = [r for r in p9.open_prs(SESSION) if r["watcher_id"] == "w2"]
    assert live, (
        "w2 is still running (pid 2222) but a superseded watcher's late fold "
        "removed it from open_prs"
    )


@pytest.mark.xfail(strict=True, reason="BRO-2374: no CAS on terminal folds")
def test_ceiling_still_counts_the_live_watcher_after_a_late_fold(p9):
    _replay_supersede(p9)
    policy = p9.load_policy()
    with pytest.raises(p9.ConcurrencyCeilingError):
        p9.enforce_concurrency_ceiling(policy, session_id=SESSION, repo=REPO)


def test_the_race_needs_no_corruption_to_occur(p9):
    """Guard against misreading this as a durability bug.

    Every row above is valid JSON written through the normal path, and every
    transition is legal — ``append_state_event`` asserts that. A fix aimed at
    write durability or corruption recovery would not touch this defect.
    """
    _replay_supersede(p9)
    rows, dropped = p9.jsonl_read_all(p9.state_jsonl())
    assert dropped == 0
    assert len(rows) == 4
    assert [r["watcher_id"] for r in rows] == [
        "w1", "watch-supersede", "w2", "w1"]
