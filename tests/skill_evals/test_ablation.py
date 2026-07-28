"""Tests for the ablation harness (scripts/skill_evals/ablation.py, BRO-2006).

Two arms of the same prompt set — skill installed, skill not — and the difference is
the skill's lift. The danger here is not a crash; it is a plausible number that
recommends deleting a load-bearing skill. So the tests are weighted toward the ways
a lift can be wrong while looking fine:

* a contaminated baseline scores like the skill added nothing (LEAKED);
* a trigger-dependent check counted either way biases the baseline in a known
  direction (skipped, ``passed: None``);
* a point estimate of zero is not evidence of absorption (interval + margin);
* and any unusable measurement must serialise ``None``, never ``0.0`` — a defaulted
  zero reads as perfect absorption.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skill_evals import ablation as A  # noqa: E402
from skill_evals import runner as R  # noqa: E402

NON_PASS = sorted(R.NON_PASS_ERRORS)


def trial(outcome="PASS", checks=(), triggered=False):
    return {"outcome": outcome, "checks": list(checks), "triggered": triggered}


def chk(cid="c", passed=True, skipped=False):
    return {"check_id": cid, "passed": None if skipped else passed, "skipped": skipped}


def report(skill="demo", cases=(), positive_pass_rate=None):
    agg = {"positive": {"pass_rate": positive_pass_rate}} if positive_pass_rate is not None else {}
    return {"skill": skill, "cases": list(cases), "aggregate": agg}


def case(should_trigger=True, results=()):
    return {"should_trigger": should_trigger, "results": list(results)}


# ---------------------------------------------------------------------------
# the arm-symmetric numerator
# ---------------------------------------------------------------------------


def test_outcome_pass_ignores_skipped_checks():
    assert A.outcome_passed(trial(checks=[chk(passed=True), chk("t", skipped=True)])) is True


def test_a_skipped_check_is_not_counted_as_a_failure():
    """Counting it failed zeroes the baseline — lift too high, which is the original
    vacuity: every skill looks load-bearing and nothing is ever retired."""
    assert A.outcome_passed(trial(checks=[chk("t", skipped=True), chk(passed=True)])) is True


def test_a_trial_with_no_runnable_checks_is_not_a_pass():
    """It asserted nothing. Counting it a pass inflates whichever arm it lands in."""
    assert A.outcome_passed(trial(checks=[chk("t", skipped=True)])) is False
    assert A.outcome_passed(trial(checks=[])) is False


def test_outcome_pass_is_computed_from_checks_not_from_the_outcome():
    """`outcome` embeds the trigger assertion, so it is not comparable between arms
    — which is the entire difficulty of this measurement."""
    t = trial(outcome="FAIL", checks=[chk(passed=True)])
    assert A.outcome_passed(t) is True


def test_non_signal_trials_are_excluded_from_both_arms():
    rep = report(cases=[case(results=[
        trial("PASS", [chk()]), trial("ERROR"), trial("INVISIBLE"), trial("LEAKED"),
    ])])
    stats = A.arm_stats(rep, NON_PASS)
    assert stats.graded_positive_trials == 1


def test_negative_cases_are_not_part_of_the_lift():
    rep = report(cases=[
        case(True, [trial("PASS", [chk()])]),
        case(False, [trial("PASS", [chk()])]),
    ])
    assert A.arm_stats(rep, NON_PASS).graded_positive_trials == 1


# ---------------------------------------------------------------------------
# the interval
# ---------------------------------------------------------------------------


def test_wilson_stays_inside_the_unit_interval_at_the_extremes():
    """The normal approximation runs outside [0,1] exactly where a retirement
    decision turns — at rates near 0 and 1 on tiny samples."""
    for successes, n in ((0, 5), (5, 5), (0, 1), (1, 1)):
        lo, hi = A.wilson_interval(successes, n)
        assert 0.0 <= lo <= hi <= 1.0, (successes, n, lo, hi)


def test_the_interval_narrows_as_evidence_grows():
    narrow = A.wilson_interval(50, 100)
    wide = A.wilson_interval(5, 10)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_difference_interval_brackets_the_point_estimate():
    lo, hi = A.newcombe_difference(9, 10, 2, 10)
    assert lo <= (0.9 - 0.2) <= hi


def test_difference_interval_is_uninformative_with_no_data():
    assert A.newcombe_difference(0, 0, 0, 0) == (-1.0, 1.0)


# ---------------------------------------------------------------------------
# verdicts — every path that must NOT produce a number
# ---------------------------------------------------------------------------


def stats(n, passes, triggers=None):
    return A.ArmStats(graded_positive_trials=n, outcome_passes=passes,
                      trigger_events=n if triggers is None else triggers)


def test_a_name_collision_refuses_before_spending():
    v = A.decide_verdict(stats(20, 18), stats(20, 2), name_collision=True)
    assert v["verdict"] == A.VERDICT_NAME_COLLISION
    assert v["skill_lift"] is None


def test_a_leaked_baseline_is_never_a_zero_lift_result():
    """THE dangerous one. A contaminated baseline scores like the skill added
    nothing — which is a recommendation to delete a load-bearing skill."""
    v = A.decide_verdict(stats(20, 18), stats(20, 18), leaked=3)
    assert v["skill_lift"] is None
    assert "contaminated" in v["why"]


def test_an_underpowered_run_says_so_instead_of_guessing():
    v = A.decide_verdict(stats(3, 3), stats(3, 0), min_trials=10)
    assert v["verdict"] == A.VERDICT_UNDERPOWERED
    assert v["skill_lift"] is None


def test_a_skill_that_barely_fires_cannot_be_ablated():
    """With a low trigger rate the ablation cannot separate absorption from a
    trigger failure, and the remedy for each is the opposite of the other."""
    v = A.decide_verdict(stats(20, 5, triggers=4), stats(20, 5))
    assert v["verdict"] == A.VERDICT_NO_TRIGGER
    assert v["skill_lift"] is None


def test_every_undecided_verdict_serialises_a_null_lift_not_zero():
    """A defaulted 0.0 reads as perfect absorption — the single most dangerous
    vacuity available in this module."""
    for v in (
        A.decide_verdict(stats(20, 18), stats(20, 2), name_collision=True),
        A.decide_verdict(stats(20, 18), stats(20, 18), leaked=1),
        A.decide_verdict(stats(2, 2), stats(2, 0)),
        A.decide_verdict(stats(20, 5, triggers=0), stats(20, 5)),
    ):
        assert v["skill_lift"] is None
        assert v["skill_lift_ci"] is None


# ---------------------------------------------------------------------------
# verdicts — the decidable ones
# ---------------------------------------------------------------------------


def test_a_clearly_load_bearing_skill():
    v = A.decide_verdict(stats(30, 29), stats(30, 3), min_trials=10)
    assert v["verdict"] == A.VERDICT_LOAD_BEARING
    assert v["skill_lift"] > 0.5
    assert v["skill_lift_ci"][0] > 0


def test_a_clearly_absorbed_skill_is_a_retire_candidate():
    v = A.decide_verdict(stats(60, 57), stats(60, 57), min_trials=10, margin=0.10)
    assert v["verdict"] == A.VERDICT_RETIRE
    assert v["skill_lift_ci"][1] < 0.10


def test_a_zero_point_estimate_on_thin_evidence_is_indeterminate_not_absorbed():
    """Absorption is a NON-INFERIORITY claim: it cannot be established by a point
    estimate of zero. On 12 trials per arm the interval is far too wide."""
    v = A.decide_verdict(stats(12, 10), stats(12, 10), min_trials=10, margin=0.10)
    assert v["verdict"] == A.VERDICT_INDETERMINATE
    assert v["skill_lift"] == 0.0  # the point estimate IS zero...
    assert v["skill_lift_ci"][1] > 0.10  # ...and it still does not support retiring


# ---------------------------------------------------------------------------
# end to end
# ---------------------------------------------------------------------------


def test_compare_produces_a_verdict_from_two_reports():
    present = report(
        cases=[case(True, [trial("PASS", [chk()], triggered=True) for _ in range(20)])],
        positive_pass_rate=1.0,
    )
    absent = report(cases=[case(True, [trial("FAIL", [chk(passed=False)]) for _ in range(20)])])
    cmp = A.compare(present, absent, non_pass=NON_PASS, min_trials=10)
    assert cmp["verdict"] == A.VERDICT_LOAD_BEARING
    assert cmp["present"]["graded_positive_trials"] == 20
    assert cmp["absent"]["outcome_pass_rate"] == 0.0
    assert cmp["end_to_end_lift"] is not None


def test_compare_counts_leaked_baseline_trials():
    present = report(cases=[case(True, [trial("PASS", [chk()], triggered=True)] * 20)])
    absent = report(cases=[case(True, [trial("LEAKED")] * 20)])
    cmp = A.compare(present, absent, non_pass=NON_PASS, min_trials=10)
    assert cmp["leaked_baseline_trials"] == 20
    assert cmp["skill_lift"] is None


def test_end_to_end_lift_is_reported_separately_from_skill_lift():
    """A low end-to-end lift with a high skill lift means 'fix the description',
    not 'retire the skill'. Collapsing the two is how an ablation recommends
    deleting a skill whose only fault is that it does not fire."""
    present = report(
        cases=[case(True, [trial("PASS", [chk()], triggered=True) for _ in range(20)])],
        positive_pass_rate=0.30,  # fires rarely end-to-end...
    )
    absent = report(cases=[case(True, [trial("FAIL", [chk(passed=False)]) for _ in range(20)])])
    cmp = A.compare(present, absent, non_pass=NON_PASS, min_trials=10)
    assert cmp["skill_lift"] == 1.0          # ...but when it fires it is decisive
    assert cmp["end_to_end_lift"] == 0.30
    assert cmp["verdict"] == A.VERDICT_LOAD_BEARING


def test_a_builtin_name_collision_is_detected_through_compare():
    present = report(skill="run", cases=[case(True, [trial("PASS", [chk()], triggered=True)] * 20)])
    absent = report(skill="run", cases=[case(True, [trial("PASS", [chk()])] * 20)])
    cmp = A.compare(present, absent, non_pass=NON_PASS,
                    builtin_names=R.BUILTIN_SKILL_NAMES, min_trials=10)
    assert cmp["verdict"] == A.VERDICT_NAME_COLLISION
    assert cmp["skill_lift"] is None


def test_the_report_renders_without_a_measurement():
    cmp = A.compare(report(cases=[case(True, [trial("PASS", [chk()])])]),
                    report(cases=[]), non_pass=NON_PASS)
    text = A.format_comparison(cmp)
    assert "NOT MEASURED" in text
    assert "n/a" in text
