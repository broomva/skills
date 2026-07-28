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

import pytest

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


def stats(n, passes, triggers=None, fails=None):
    """`fails` defaults to n - passes: a trial that did not pass its outcome checks
    did so BECAUSE a check failed, which is what gives the suite discriminating
    power. Pass fails=0 explicitly to model checks that never fail anywhere."""
    return A.ArmStats(graded_positive_trials=n, outcome_passes=passes,
                      trigger_events=n if triggers is None else triggers,
                      check_failures=(n - passes) if fails is None else fails)


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


# ---------------------------------------------------------------------------
# the prompt-set shape that would bias a lift upward
# ---------------------------------------------------------------------------


def test_a_positive_made_only_of_trigger_checks_is_flagged():
    """In the baseline those checks are skipped, leaving nothing runnable — so the
    case can never pass the baseline and the lift is inflated toward load-bearing.
    Zero of the 72 committed positive cases are like this; the warning keeps it so."""
    doc = {
        "skill": "demo", "version": 1,
        "cases": [
            {"id": "p1", "prompt": "do a thing", "should_trigger": True,
             "expected_checks": ["skill_triggered"]},
            {"id": "n1", "prompt": "a near miss", "should_trigger": False,
             "expected_checks": ["final_answer_non_empty"]},
        ],
    }
    errors, warnings = R.validate_prompt_set(doc)
    assert not errors, errors
    assert any("bias the lift upward" in w for w in warnings), warnings


def test_a_positive_with_a_real_outcome_check_is_not_flagged():
    """FALSE-POSITIVE control — mixing a trigger check with an outcome check is the
    normal shape and must stay quiet."""
    doc = {
        "skill": "demo", "version": 1,
        "cases": [
            {"id": "p1", "prompt": "do a thing", "should_trigger": True,
             "expected_checks": ["skill_triggered", "final_answer_non_empty"]},
            {"id": "n1", "prompt": "a near miss", "should_trigger": False,
             "expected_checks": ["final_answer_non_empty"]},
        ],
    }
    _errors, warnings = R.validate_prompt_set(doc)
    assert not any("bias the lift upward" in w for w in warnings), warnings


# ---------------------------------------------------------------------------
# defects found by cross-review of PR #114
# ---------------------------------------------------------------------------


def test_the_numerator_is_arm_symmetric():
    """THE blocker. The present arm was graded on a strict SUPERSET of the absent
    arm's checks — it had to fire AND satisfy the outcome checks, while the baseline
    only had to satisfy the outcome checks. Every present-arm trial where the skill
    did not fire became a lift PENALTY.

    Reproduced on `kg`'s real committed shape: 9 positive cases, every one asserting
    ['skill_triggered','final_answer_non_empty','no_permission_denials'], at the
    default --trials 3 = 27 graded trials per arm. A skill firing on 22/27 (81% —
    clearing the harness's OWN 0.80 threshold) against a baseline that trivially
    satisfies the two weak outcome checks scored `retire-candidate`.
    """
    kg_checks = ["skill_triggered", "final_answer_non_empty", "no_permission_denials"]

    def present_trial(fired: bool):
        return trial("PASS" if fired else "FAIL", [
            chk("skill_triggered", passed=fired),
            chk("final_answer_non_empty", passed=True),
            chk("no_permission_denials", passed=True),
        ], triggered=fired)

    def absent_trial():
        return trial("PASS", [
            chk("skill_triggered", skipped=True),
            chk("final_answer_non_empty", passed=True),
            chk("no_permission_denials", passed=True),
        ])

    present = report(skill="kg", cases=[case(True,
        [present_trial(True)] * 22 + [present_trial(False)] * 5)], positive_pass_rate=22 / 27)
    absent = report(skill="kg", cases=[case(True, [absent_trial()] * 27)])

    cmp = A.compare(present, absent, non_pass=NON_PASS, min_trials=10)
    assert cmp["verdict"] != A.VERDICT_RETIRE, (
        "a skill passing its own eval gate must not be recommended for deletion")
    # kg's remaining checks cannot tell the arms apart once the trigger check is
    # excluded from both, so the honest verdict is weak-checks and there is NO number.
    assert cmp["verdict"] == A.VERDICT_WEAK_CHECKS, cmp
    assert cmp["skill_lift"] is None, cmp
    # the trigger signal is not lost — it is reported on its own axis
    assert cmp["present"]["trigger_rate"] == pytest.approx(22 / 27)
    assert kg_checks  # documents the real shape this reconstructs


def test_a_present_trial_failing_only_the_trigger_check_does_not_depress_lift():
    """The minimal form of the same defect."""
    fired = trial("PASS", [chk("skill_triggered", passed=True), chk("x", passed=True)],
                  triggered=True)
    missed = trial("FAIL", [chk("skill_triggered", passed=False), chk("x", passed=True)])
    absent = trial("PASS", [chk("skill_triggered", skipped=True), chk("x", passed=True)])

    assert A.outcome_passed(fired) is True
    assert A.outcome_passed(missed) is True, "outcome quality was identical; only the trigger differed"
    assert A.outcome_passed(absent) is True


def test_a_real_outcome_failure_still_counts():
    """FALSE-POSITIVE control: excluding the trigger check must not blunt the
    measurement of the checks that DO differ between arms."""
    good = trial("PASS", [chk("skill_triggered", passed=True), chk("x", passed=True)],
                 triggered=True)
    bad = trial("FAIL", [chk("skill_triggered", passed=True), chk("x", passed=False)],
                triggered=True)
    assert A.outcome_passed(good) is True
    assert A.outcome_passed(bad) is False

    present = report(cases=[case(True, [good] * 30)], positive_pass_rate=1.0)
    absent = report(cases=[case(True, [
        trial("FAIL", [chk("skill_triggered", skipped=True), chk("x", passed=False)])] * 30)])
    cmp = A.compare(present, absent, non_pass=NON_PASS, min_trials=10)
    assert cmp["skill_lift"] == 1.0
    assert cmp["verdict"] == A.VERDICT_LOAD_BEARING


def test_ablate_refuses_replay():
    """Both arms would replay the SAME fixtures, so the baseline is 100% LEAKED by
    construction — the flag advertised a mode that could never produce a number."""
    rc = R.main([
        "--skill-dir", "tests/skill_evals/fixtures/harness-selftest/skill",
        "--prompts", "tests/skill_evals/fixtures/harness-selftest/evals/prompts.json",
        "--replay", "tests/skill_evals/fixtures/harness-selftest",
        "--allow-synthetic-fixtures", "--ablate",
    ])
    assert rc == R.EXIT_USAGE


def test_ablate_refuses_record():
    """Fixtures are stored per CASE, not per ARM, so the absent arm overwrote the
    present arm's transcripts — destroying the live evidence just paid for and
    turning every positive into INVISIBLE on replay."""
    rc = R.main([
        "--skill-dir", "tests/skill_evals/fixtures/harness-selftest/skill",
        "--prompts", "tests/skill_evals/fixtures/harness-selftest/evals/prompts.json",
        "--cli", "/bin/true", "--no-version-check", "--ablate", "--record", "/tmp/never-written",
    ])
    assert rc == R.EXIT_USAGE
    assert not Path("/tmp/never-written").exists()


def test_ablate_dry_run_still_works():
    """FALSE-POSITIVE control for the two refusals: the live path is untouched."""
    rc = R.main([
        "--skill-dir", "tests/skill_evals/fixtures/harness-selftest/skill",
        "--prompts", "tests/skill_evals/fixtures/harness-selftest/evals/prompts.json",
        "--cli", "/bin/true", "--no-version-check", "--ablate", "--dry-run",
    ])
    assert rc == R.EXIT_OK


# ---------------------------------------------------------------------------
# round-2: the false retire survived the first fix, one operating point away
# ---------------------------------------------------------------------------


def test_checks_that_never_fail_cannot_support_a_retirement():
    """The first fix moved the false retire from --trials 3 to --trials 4 — and the
    README recommends ~30 trials per arm, so the RECOMMENDED operating point was the
    false-retire regime.

    Once `skill_triggered` is (correctly) excluded from both arms, kg's committed
    prompt set asserts only "a non-empty final answer" and "no permission denials",
    which an uninstalled baseline satisfies trivially. Lift is then exactly 0.0
    regardless of how well the skill works, and the interval narrows below the margin
    at n/arm >= 36. A lift of zero from checks that never failed is a tautology, not
    evidence of absorption.
    """
    for n in (36, 45, 90):
        v = A.decide_verdict(stats(n, n, fails=0), stats(n, n, triggers=0, fails=0),
                             min_trials=10)
        assert v["verdict"] == A.VERDICT_WEAK_CHECKS, (n, v)
        assert v["skill_lift"] is None, "and it must not publish a number"


def test_retirement_is_still_reachable_on_discriminating_evidence():
    """FALSE-POSITIVE control, and the one that matters: the guard must not make
    retirement impossible — only unearned retirement."""
    present = A.ArmStats(90, 80, 90, check_failures=10)
    absent = A.ArmStats(90, 80, 0, check_failures=10)
    v = A.decide_verdict(present, absent, min_trials=10)
    assert v["verdict"] == A.VERDICT_RETIRE
    assert v["skill_lift"] == 0.0


def test_a_load_bearing_skill_is_unaffected():
    present = A.ArmStats(90, 88, 90, check_failures=4)
    absent = A.ArmStats(90, 5, 0, check_failures=85)
    v = A.decide_verdict(present, absent, min_trials=10)
    assert v["verdict"] == A.VERDICT_LOAD_BEARING
    assert v["skill_lift"] > 0.9


def test_check_failures_are_counted_from_the_graded_checks_only():
    """A skipped check is not a failure, and neither is a trigger check excluded in
    both arms — or the counter would report discriminating power that is not there."""
    rep = report(cases=[case(True, [
        trial("PASS", [chk("skill_triggered", passed=False), chk("x", passed=True)]),
        trial("PASS", [chk("skill_triggered", skipped=True), chk("x", passed=True)]),
        trial("FAIL", [chk("x", passed=False)]),
    ])])
    st = A.arm_stats(rep, NON_PASS)
    assert st.check_failures == 1, "only the real outcome-check failure counts"
