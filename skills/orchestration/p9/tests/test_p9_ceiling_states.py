"""BRO-2305 — the ceiling bounds watcher work in flight, not open PRs.

Reproduced live 2026-08-24 against the real state store:

  `p9 watch 432 --repo broomva/workspace` refused with
  `max_concurrent_prs=1 already in flight (1 open ... in broomva/workspace)`
  because `broomva/workspace#433` sat in **GREEN** and open — P20-blocked at
  3/10, so it would not merge for days. `p9 cleanup` could not free it: the
  PR is genuinely open, so cleanup correctly reported
  `still OPEN; leaving as GREEN` → `drained 0`.

  Since `watch` is the only transition into GREEN, the entire lifecycle was
  unreachable for that repo. `p9 watch` refuses LOUDLY — exit
  ``EXIT_CONCURRENCY_CEILING`` (5) on a distinct code, message on stderr. An
  earlier draft of this file said it "exits 0 without arming"; that was wrong
  and is pinned below rather than restated, because a claim about an exit code
  with no test behind it is how the wrong number survived review in the first
  place.

Root cause: `open_prs()` drops a row only when `is_terminal()`, and GREEN and
MERGE_READY are not terminal. The state machine had no value meaning
*"watching is over, the PR is still open"*, so it conflated the **watch**
lifecycle with the **PR** lifecycle.

The red states stay counted on purpose. GREEN/MERGE_READY mean *success
awaiting an external gate*; RED_* means *a failure needing attention*, and
refusing to watch new work while something is broken is deliberate
back-pressure that `test_p9_visibility.py` already pins.

This is BRO-1988's failure on a different axis. That ticket's own rationale
applies verbatim: an unreachable lifecycle is a worse failure than one extra
concurrent watcher.

These tests pin both directions — the parked states must not hold a slot, and
the states p9 still owns must continue to hold one. The ceiling is scoped, not
deleted.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
_FIXTURES = _HERE / "fixtures"
sys.path.insert(0, str(_SCRIPTS))

WORKSPACE = "broomva/workspace"
AMBIENT = "broomva/ambient"


@pytest.fixture()
def p9(tmp_path, monkeypatch):
    """Fresh p9 with tmpdir state and max_concurrent_prs=1."""
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(_FIXTURES / "policy-good.yaml"))
    monkeypatch.setenv("BROOMVA_P9_REPO", AMBIENT)
    monkeypatch.delenv("BROOMVA_P9_SESSION", raising=False)
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


def _event(p9, pr, repo, prev, curr, *, session_id="A"):
    p9.append_state_event(p9.PRStateEvent(
        ts=p9._utcnow(), pr=pr, repo=repo,
        from_state=prev.value, to_state=curr.value,
        watcher_id=f"w{pr}", session_id=session_id,
    ))


def _park(p9, pr, repo, target, *, session_id="A"):
    """Walk the real transition graph until the row rests in ``target``.

    Deliberately not a direct write: the path into a state is part of what is
    under test, and a hand-forged row could rest somewhere production can
    never reach.
    """
    S = p9.PRState
    paths = {
        S.PUSHED:           [],
        S.WATCHING:         [(S.PUSHED, S.WATCHING)],
        S.GREEN:            [(S.PUSHED, S.WATCHING), (S.WATCHING, S.GREEN)],
        S.MERGE_READY:      [(S.PUSHED, S.WATCHING), (S.WATCHING, S.GREEN),
                             (S.GREEN, S.MERGE_READY)],
        S.RED_CLASSIFIED:   [(S.PUSHED, S.WATCHING),
                             (S.WATCHING, S.RED_CLASSIFIED)],
        S.RED_UNCLASSIFIED: [(S.PUSHED, S.WATCHING),
                             (S.WATCHING, S.RED_UNCLASSIFIED)],
        S.HEALING:          [(S.PUSHED, S.WATCHING),
                             (S.WATCHING, S.RED_CLASSIFIED),
                             (S.RED_CLASSIFIED, S.HEALING)],
    }
    if target is S.PUSHED:
        _event(p9, pr, repo, S.PUSHED, S.PUSHED, session_id=session_id)
        return
    for prev, curr in paths[target]:
        _event(p9, pr, repo, prev, curr, session_id=session_id)
    assert p9.current_pr_state(pr, repo) is target


# ─────────────────────────────────────────────────────────────────────────────
# The predicate itself — exhaustive over the enum, so a NEW state cannot be
# added without someone deciding which side of the ceiling it falls on.
# ─────────────────────────────────────────────────────────────────────────────
class TestCountsAgainstCeiling:
    def test_every_state_is_classified_explicitly(self, p9):
        """If PRState grows a member, this test fails until it is classified.

        Without this, a new state would silently inherit `True` from the
        `not is_terminal(...)` fallback — which is exactly how GREEN came to
        pin the slot in the first place.
        """
        S = p9.PRState
        expected = {
            # p9 owns the next transition → holds a slot.
            S.PUSHED: True,
            S.WATCHING: True,
            S.HEALING: True,
            S.RED_CLASSIFIED: True,
            # Red is back-pressure, not a leak: do not start watching new work
            # while something is broken. Pinned by test_p9_visibility.py
            # TestRewatchCeiling::test_distinct_pr_still_blocked_at_ceiling.
            S.RED_UNCLASSIFIED: True,
            # p9 concluded successfully; an external actor must move → no slot.
            S.GREEN: False,
            S.MERGE_READY: False,
            # Terminal → no slot.
            S.MERGED: False,
            S.ESCALATED: False,
            S.ABANDONED: False,
        }
        assert set(expected) == set(S), (
            "PRState changed; classify the new member(s) against the ceiling"
        )
        actual = {s: p9.counts_against_ceiling(s) for s in S}
        assert actual == expected

    def test_is_terminal_is_not_widened(self, p9):
        """The fix must stay additive. `open_prs`, `cleanup`, `reap`, `status`
        and the governor all read `is_terminal`; widening it would move all of
        them at once."""
        S = p9.PRState
        terminal = {s for s in S if p9.is_terminal(s)}
        assert terminal == {S.MERGED, S.ESCALATED, S.ABANDONED}


# ─────────────────────────────────────────────────────────────────────────────
# Effect — a parked row must not hold the slot
# ─────────────────────────────────────────────────────────────────────────────
class TestParkedRowsReleaseTheSlot:
    @pytest.mark.parametrize("state_name", ["GREEN", "MERGE_READY"])
    def test_parked_row_does_not_hold_the_slot(self, p9, state_name):
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")  # max=1
        _park(p9, 433, WORKSPACE, getattr(p9.PRState, state_name))
        # Same session, same repo, different PR → must not raise.
        p9.enforce_concurrency_ceiling(cfg, session_id="A", repo=WORKSPACE)

    @pytest.mark.parametrize("state_name", ["WATCHING", "HEALING",
                                            "RED_CLASSIFIED",
                                            "RED_UNCLASSIFIED"])
    def test_owned_row_still_holds_the_slot(self, p9, state_name):
        """The ceiling is scoped, not deleted."""
        cfg = p9.load_policy(_FIXTURES / "policy-good.yaml")
        _park(p9, 433, WORKSPACE, getattr(p9.PRState, state_name))
        with pytest.raises(p9.ConcurrencyCeilingError):
            p9.enforce_concurrency_ceiling(cfg, session_id="A", repo=WORKSPACE)


# ─────────────────────────────────────────────────────────────────────────────
# The live repro, through the CLI
# ─────────────────────────────────────────────────────────────────────────────
class TestWatchCliBehindAGreenRow:
    def test_watch_arms_behind_a_green_row(self, p9, monkeypatch):
        """The exact refusal from 2026-08-24: an open GREEN #433 must not
        refuse `p9 watch 432 --repo broomva/workspace`."""
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        _park(p9, 433, WORKSPACE, p9.PRState.GREEN)
        rc = p9.main(["watch", "432", "--repo", WORKSPACE, "--dry-run"])
        assert rc == p9.EXIT_OK
        assert p9.current_pr_state(432, WORKSPACE) == p9.PRState.WATCHING
        # #433 is untouched — released from the ceiling, not from the store.
        assert p9.current_pr_state(433, WORKSPACE) == p9.PRState.GREEN

    def test_watch_still_refused_behind_a_watching_row(self, p9, monkeypatch):
        """The bound still bounds. Without this, the fix would read as
        'delete the ceiling' and pass."""
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        _park(p9, 433, WORKSPACE, p9.PRState.WATCHING)
        rc = p9.main(["watch", "432", "--repo", WORKSPACE, "--dry-run"])
        assert rc == p9.EXIT_CONCURRENCY_CEILING

    def test_two_green_rows_do_not_accumulate(self, p9, monkeypatch):
        """Several unmerged-but-green PRs is the steady state of a busy repo,
        not an edge case."""
        monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
        for pr in (433, 455, 465, 370):
            _park(p9, pr, WORKSPACE, p9.PRState.GREEN)
        assert p9.main(
            ["watch", "432", "--repo", WORKSPACE, "--dry-run"]) == p9.EXIT_OK


def test_ceiling_refusal_exit_code_is_distinct_and_loud(p9, monkeypatch, capsys):
    """The refusal is not silent, and not exit 0.

    Pins the number the module docstring names. `/autonomous` branches on this
    code to decide whether CI is actually being watched, so "which code" is
    load-bearing, not cosmetic.
    """
    monkeypatch.setenv("BROOMVA_P9_SESSION", "A")
    S = p9.PRState
    _park(p9, 900, WORKSPACE, S.WATCHING, session_id="A")

    rc = p9.main(["watch", "901", "--repo", WORKSPACE, "--dry-run"])

    assert rc == p9.EXIT_CONCURRENCY_CEILING
    assert rc == 5, "the docstring names 5; if this moves, update both"
    assert rc != 0, "exit 0 would let an arc believe CI is watched when it is not"
    assert "max_concurrent_prs" in capsys.readouterr().err
