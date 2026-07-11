"""Unit tests for the deterministic loop state machine.

These pin the boundary conditions a prose controller silently gets wrong: the
in-flight fold (dry records, arc_exit-doesn't-free, abandoned-frees), the P5
reseed gate at each turn/generation boundary, the busy-guard order, and the
typed arc-status contract.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import loop_state as ls  # noqa: E402


# ── in_flight fold ───────────────────────────────────────────────────────────

def test_in_flight_dispatch_then_done_frees_slot():
    recs = [
        {"action": "dispatch", "ticket": "A"},
        {"action": "dispatch", "ticket": "B"},
        {"action": "reconcile_done", "ticket": "A"},
    ]
    assert ls.in_flight(recs) == {"B"}
    assert ls.in_flight_count(recs) == 1


def test_in_flight_dispatch_intent_counts():
    # An unconfirmed dispatch_intent (crash mid-dispatch) still holds a slot.
    assert ls.in_flight([{"action": "dispatch_intent", "ticket": "A"}]) == {"A"}


def test_arc_exit_does_not_free_slot():
    # Process death must NOT free the slot — bounds open-PR accumulation too.
    recs = [
        {"action": "dispatch", "ticket": "A"},
        {"action": "arc_exit", "ticket": "A"},
    ]
    assert ls.in_flight(recs) == {"A"}


def test_abandoned_frees_slot():
    recs = [
        {"action": "dispatch", "ticket": "A"},
        {"action": "abandoned", "ticket": "A", "by": "operator"},
    ]
    assert ls.in_flight(recs) == set()


def test_dry_records_never_touch_wip():
    recs = [
        {"action": "dispatch", "ticket": "A", "dry_run": True},   # dry flag
        {"action": "dispatch_dry", "ticket": "B"},                # _dry suffix
        {"action": "dispatch", "ticket": "C"},                    # the only live one
    ]
    assert ls.in_flight(recs) == {"C"}


def test_last_record_wins_left_fold():
    # done then re-dispatch (same ticket) => in flight again.
    recs = [
        {"action": "dispatch", "ticket": "A"},
        {"action": "reconcile_done", "ticket": "A"},
        {"action": "dispatch", "ticket": "A"},
    ]
    assert ls.in_flight(recs) == {"A"}


def test_in_flight_ignores_garbage_records():
    recs = ["not a dict", {"no": "ticket"}, {"action": "dispatch", "ticket": "A"}]
    assert ls.in_flight(recs) == {"A"}


# ── the P5 reseed gate ───────────────────────────────────────────────────────

def test_reseed_below_cap_resumes():
    assert ls.reseed_decision(turn=7, generation=0, cap=8, max_generations=3) == ls.RESEED_RESUME


def test_reseed_at_cap_reseeds():
    assert ls.reseed_decision(turn=8, generation=0, cap=8, max_generations=3) == ls.RESEED_RESEED


def test_reseed_above_cap_reseeds():
    assert ls.reseed_decision(turn=20, generation=2, cap=8, max_generations=3) == ls.RESEED_RESEED


def test_reseed_generations_exhausted_escalates():
    # turn past cap AND generation cap hit => runaway guard escalates (P4).
    assert ls.reseed_decision(turn=9, generation=3, cap=8, max_generations=3) == ls.RESEED_ESCALATE


def test_reseed_max_zero_never_auto_reseeds():
    # max_generations == 0 => escalate immediately at the cap.
    assert ls.reseed_decision(turn=8, generation=0, cap=8, max_generations=0) == ls.RESEED_ESCALATE


def test_reseed_coerces_bad_inputs_without_throwing():
    # A garbage knob must fall to a conservative branch, never raise inside the loop.
    assert ls.reseed_decision(turn="x", generation=None, cap=0, max_generations=-1) in (
        ls.RESEED_RESUME, ls.RESEED_RESEED, ls.RESEED_ESCALATE)
    # cap coerced to >=1, turn coerced to 0 => below cap => resume
    assert ls.reseed_decision(turn="x", generation=0, cap="y", max_generations=3) == ls.RESEED_RESUME


# ── the busy-guard ───────────────────────────────────────────────────────────

def test_busy_guard_no_session_skips_first():
    assert ls.resume_skip_reason(has_session=False, pid_alive=True, has_status=True,
                                 state="awaiting_ci") == "no_session_id"


def test_busy_guard_live_pid_is_busy():
    assert ls.resume_skip_reason(has_session=True, pid_alive=True, has_status=True,
                                 state="awaiting_ci") == "busy"


def test_busy_guard_unconfirmed_resume_intent_is_busy():
    # The BRO-1833 crash-window guard: a dead pid but an unconfirmed resume_intent
    # must still skip (never a second -r on the same session), which the pid check
    # alone misses.
    assert ls.resume_skip_reason(has_session=True, pid_alive=False, has_status=True,
                                 state="awaiting_ci", pending_resume_intent=True) == "busy"


def test_busy_guard_no_status():
    assert ls.resume_skip_reason(has_session=True, pid_alive=False, has_status=False,
                                 state=None) == "no_status"


def test_busy_guard_complete_left_for_reconcile():
    assert ls.resume_skip_reason(has_session=True, pid_alive=False, has_status=True,
                                 state="complete") == "complete"


def test_busy_guard_working_but_dead():
    # 'working' is advisory; a dead arc last seen working is not a resume candidate.
    assert ls.resume_skip_reason(has_session=True, pid_alive=False, has_status=True,
                                 state="working") == "working_but_dead"


def test_busy_guard_awaiting_ci_is_resume_candidate():
    assert ls.resume_skip_reason(has_session=True, pid_alive=False, has_status=True,
                                 state="awaiting_ci") is None


def test_busy_guard_blocked_human_is_resume_candidate():
    # blocked_human is routed (escalate), which counts as a candidate here.
    assert ls.resume_skip_reason(has_session=True, pid_alive=False, has_status=True,
                                 state="blocked_human") is None


def test_merge_not_authorized_is_a_known_reason():
    # The delegation-boundary outcome (scenario merge-not-authorized) must be a
    # recognized resume_skip reason the governor can record.
    assert "merge_not_authorized" in ls.RESUME_SKIP_REASONS


# ── the typed arc-status contract ────────────────────────────────────────────

def test_arc_status_valid_complete():
    ok, errs = ls.validate_arc_status({"state": "complete", "pr": 4729, "turn": 1})
    assert ok, errs


def test_arc_status_pr_must_be_bare_int():
    ok, errs = ls.validate_arc_status({"state": "complete", "pr": "#4729"})
    assert not ok
    assert any("pr must be a bare integer" in e for e in errs)


def test_arc_status_pr_string_rejected():
    ok, _ = ls.validate_arc_status({"state": "awaiting_ci", "pr": "4729"})
    assert not ok


def test_arc_status_pr_bool_rejected():
    # bool is an int subclass — must be rejected explicitly.
    ok, _ = ls.validate_arc_status({"state": "complete", "pr": True})
    assert not ok


def test_arc_status_needs_decision_requires_question():
    ok, errs = ls.validate_arc_status({"state": "needs_decision", "pr": 1})
    assert not ok
    assert any("question" in e for e in errs)


def test_arc_status_needs_decision_with_question_ok():
    ok, errs = ls.validate_arc_status(
        {"state": "needs_decision", "pr": 1, "question": "merge strategy?"})
    assert ok, errs


def test_arc_status_working_needs_no_pr():
    ok, errs = ls.validate_arc_status({"state": "working"})
    assert ok, errs


def test_arc_status_evidence_must_be_string():
    ok, errs = ls.validate_arc_status(
        {"state": "complete", "pr": 1, "evidence": {"nested": "object"}})
    assert not ok
    assert any("evidence" in e for e in errs)


def test_arc_status_unknown_state_rejected():
    ok, _ = ls.validate_arc_status({"state": "merged", "pr": 1})
    assert not ok


def test_arc_status_non_object_rejected():
    ok, _ = ls.validate_arc_status(["not", "an", "object"])
    assert not ok
