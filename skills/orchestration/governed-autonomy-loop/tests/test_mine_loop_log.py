"""Unit tests for the loop-log miner.

Pins: the dry-suffix fold, the reason taxonomy, the DRIFT detector (an unknown
reason a live loop emits must be flagged — the skill-self-evolution hook), and the
redaction guarantee (free text never leaves the log).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import mine_loop_log as m  # noqa: E402
import loop_state as ls    # noqa: E402


def _recs():
    return [
        {"action": "tick_fire"},
        {"action": "reconcile_skip", "ticket": "BRO-1", "reason": "no_pr"},
        {"action": "reconcile_skip", "ticket": "BRO-2", "reason": "open_pr"},
        {"action": "reconcile_skip_dry", "ticket": "BRO-3", "reason": "no_pr"},  # dry folds
        {"action": "resume_skip", "ticket": "BRO-4", "reason": "complete"},
        {"action": "dispatch", "ticket": "BRO-5"},
        {"action": "stall", "ticket": "BRO-5", "pid_alive": False,
         "last_commit_age_s": 14000, "title": "SECRET FREE TEXT"},  # untrusted free text
    ]


def test_action_histogram_folds_dry_suffix():
    h = m.action_histogram(_recs())
    assert h["reconcile_skip"] == 3        # 2 live + 1 _dry folded
    assert h["tick_fire"] == 1


def test_reason_taxonomy():
    tax = m.reason_taxonomy(_recs(), "reconcile_skip")
    assert tax["no_pr"] == 2               # incl. the _dry one
    assert tax["open_pr"] == 1


def test_unknown_reasons_empty_when_all_known():
    assert m.unknown_reasons(_recs()) == {}


def test_unknown_reasons_flags_drift():
    # A live loop emitting a reason the contract doesn't know is the drift signal.
    recs = _recs() + [{"action": "reconcile_skip", "ticket": "BRO-9", "reason": "brand_new_reason"}]
    drift = m.unknown_reasons(recs)
    assert drift == {"reconcile_skip": ["brand_new_reason"]}


def test_known_reasons_are_the_live_observed_ones():
    # The contract must contain every reason the reference loops actually emit
    # (no_pr/open_pr/recently_active/arc_live/epic_in_progress/phases_open).
    for r in ("no_pr", "open_pr", "recently_active", "arc_live",
              "epic_in_progress", "phases_open"):
        assert r in ls.RECONCILE_SKIP_REASONS


def test_decision_fixtures_ranked_and_redacted():
    fixtures = m.decision_fixtures(_recs())
    # ranked by count desc — reconcile_skip/no_pr (2) is first
    assert fixtures[0]["action"] == "reconcile_skip"
    assert fixtures[0]["reason"] == "no_pr"
    assert fixtures[0]["count"] == 2
    # the stall example must NOT carry the free-text title
    stall = next(f for f in fixtures if f["action"] == "stall")
    assert "title" not in stall["example"]
    assert stall["example"]["last_commit_age_s"] == 14000


def test_redact_strips_free_text():
    red = m._redact({"action": "reconcile_skip", "reason": "no_pr", "ticket": "BRO-1",
                     "title": "untrusted", "detail": "also untrusted"})
    assert red == {"action": "reconcile_skip", "reason": "no_pr", "ticket": "BRO-1"}


# P20 round-3 regression: a FREE-TEXT `reason` (label_apply eligibility rationale,
# derived from the untrusted unit body) must NOT leak — the exact real record from
# the Mac loop (BRO-1742). The field name `reason` is not enough; it is validated.
_LEAKY = {
    "action": "label_apply", "ticket": "BRO-1742",
    "reason": ("M0 build (provenance CLI + tests per merged spec PR #184): workspace "
               "code, CI-adjudicable, git-reversible, no deploy/spend/governance surface"),
}


def test_redact_drops_free_text_reason():
    red = m._redact(_LEAKY)
    assert red["reason"] == m._REDACTED
    assert "provenance" not in str(red)      # no untrusted text survives
    assert red["ticket"] == "BRO-1742"       # structural fields still pass through


def test_fixtures_do_not_leak_free_text_reason():
    # BOTH channels: the group key/label AND the example must be redacted.
    fixtures = m.decision_fixtures([_LEAKY])
    blob = str(fixtures)
    assert "provenance" not in blob and "git-reversible" not in blob
    assert fixtures[0]["reason"] == m._REDACTED


def test_controlled_reason_survives_redaction():
    # A real vocab reason must NOT be over-redacted.
    assert m._safe_value("reason", "no_pr") == "no_pr"
    assert m._safe_value("reason", "complete") == "complete"
    assert m._safe_value("why", "reseed_exhausted") == "reseed_exhausted"
    assert m._safe_value("state", "awaiting_ci") == "awaiting_ci"
    # a non-vocab why/state is dropped too
    assert m._safe_value("why", "some free text") == m._REDACTED


def test_empty_reason_not_over_redacted():
    # An absent-reason field ('') must render as empty, not as hidden text (P20 r4).
    assert m._safe_value("reason", "") == ""
    fixtures = m.decision_fixtures([{"action": "tick_fire"}])
    assert fixtures[0]["reason"] == ""       # not the redaction marker


def test_ticket_field_validated_as_tracker_id():
    # A ticket must be a tracker id; free text in the ticket slot is redacted too.
    assert m._safe_value("ticket", "BRO-1742") == "BRO-1742"
    assert m._safe_value("ticket", "not a ticket, free text") == m._REDACTED
    red = m._redact({"action": "reconcile_skip", "reason": "no_pr",
                     "ticket": "arbitrary free text here"})
    assert red["ticket"] == m._REDACTED


def test_summarize_structure_and_in_flight():
    rep = m.summarize(_recs())
    assert rep["total_records"] == 7
    assert rep["reconcile_skip_reasons"]["no_pr"] == 2
    # BRO-5 dispatched, never reconciled/abandoned => in flight
    assert rep["in_flight"] == ["BRO-5"]
    assert rep["unknown_reasons"] == {}


# ── --health wedge detector (BRO-1851) ───────────────────────────────────────

def test_health_flags_wedged_arc():
    # dispatched → dead (stall) → 2 ticks with no progress → WEDGED (the BRO-1481 shape).
    recs = [
        {"action": "dispatch", "ticket": "BRO-1"},
        {"action": "stall", "ticket": "BRO-1", "pid_alive": False},
        {"action": "tick_fire"},
        {"action": "tick_fire"},
    ]
    rep = m.health(recs, min_ticks=2)
    assert rep["in_flight"] == 1
    assert len(rep["wedged"]) == 1
    assert rep["wedged"][0]["ticket"] == "BRO-1"
    assert rep["wedged"][0]["last_state"] == "stall"
    assert rep["wedged"][0]["ticks_pinned"] == 2


def test_health_flags_resume_skip_no_status_wedge():
    # the exact BRO-1481 signature: arc died without writing status.
    recs = [
        {"action": "dispatch", "ticket": "BRO-1"},
        {"action": "resume_skip", "ticket": "BRO-1", "reason": "no_status"},
        {"action": "tick_fire"}, {"action": "tick_fire"}, {"action": "tick_fire"},
    ]
    rep = m.health(recs, min_ticks=2)
    assert rep["wedged"][0]["last_state"] == "resume_skip:no_status"


def test_health_ok_for_live_working_arc():
    # dispatched, no dead signal => not wedged (arc is presumably working).
    recs = [{"action": "dispatch", "ticket": "BRO-2"},
            {"action": "tick_fire"}, {"action": "tick_fire"}]
    assert m.health(recs)["wedged"] == []


def test_health_progress_clears_dead_signal():
    # a re-dispatch / resume AFTER a stall clears the dead signal — not a false wedge.
    recs = [
        {"action": "dispatch", "ticket": "BRO-3"},
        {"action": "stall", "ticket": "BRO-3"},
        {"action": "tick_fire"}, {"action": "tick_fire"},
        {"action": "resume", "ticket": "BRO-3"},   # forward progress
    ]
    assert m.health(recs, min_ticks=2)["wedged"] == []


def test_health_respects_min_ticks():
    recs = [
        {"action": "dispatch", "ticket": "BRO-4"},
        {"action": "stall", "ticket": "BRO-4"},
        {"action": "tick_fire"},                    # only 1 tick since dispatch
    ]
    assert m.health(recs, min_ticks=2)["wedged"] == []
    assert len(m.health(recs, min_ticks=1)["wedged"]) == 1


def test_health_complete_arc_not_wedged():
    # a `complete` arc (done, waiting for merge) with an EARLIER stall must NOT be
    # flagged — it mirrors the governor's Step D complete-carve-out (BRO-1483 shape).
    recs = [
        {"action": "dispatch", "ticket": "BRO-6"},
        {"action": "stall", "ticket": "BRO-6"},
        {"action": "resume_skip", "ticket": "BRO-6", "reason": "complete"},
        {"action": "tick_fire"}, {"action": "tick_fire"},
    ]
    assert m.health(recs, min_ticks=2)["wedged"] == []


def test_health_ignores_reconciled_ticket():
    # a dead arc that then reconciled is no longer in flight → not wedged.
    recs = [
        {"action": "dispatch", "ticket": "BRO-5"},
        {"action": "stall", "ticket": "BRO-5"},
        {"action": "tick_fire"}, {"action": "tick_fire"},
        {"action": "reconcile_done", "ticket": "BRO-5"},
    ]
    assert m.health(recs, min_ticks=2)["wedged"] == []
