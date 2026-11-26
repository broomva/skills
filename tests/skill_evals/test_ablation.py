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


# ---------------------------------------------------------------------------
# round-3: the guard closed one polarity and left its mirror open
# ---------------------------------------------------------------------------


def test_checks_that_ALWAYS_fail_cannot_support_a_retirement():
    """The mirror of the round-2 finding, and it was still open.

    A check failing in EVERY trial of BOTH arms is exactly as non-discriminating as
    one that always passes — but it satisfies a failure-count gate, so lift came out
    0.0 with a narrow interval and the verdict was `retire-candidate` on a run where
    the present arm passed NOTHING. The rendered report said "the base model does
    about as well without it".

    Reachable without exotic input: `run_checks` records `passed=False` for a check
    that RAISES, so one buggy predicate in CHECK_REGISTRY turns a sweep into "retire
    everything"; and an environment-invariant failure (the jail denying a tool the
    skill needs) produces the same shape with nothing broken.
    """
    v = A.decide_verdict(A.ArmStats(36, 0, 36, check_failures=36),
                         A.ArmStats(36, 0, 0, check_failures=36), min_trials=10)
    assert v["verdict"] == A.VERDICT_WEAK_CHECKS
    assert v["skill_lift"] is None
    assert "always fails" in v["why"]


def test_a_skill_that_never_fires_is_a_trigger_problem_not_a_check_problem():
    """Gate ORDER. The weak-checks gate used to sit above the trigger gate, so an
    operator whose description was dead got told to strengthen their checks — the
    opposite remedy."""
    v = A.decide_verdict(A.ArmStats(36, 36, 0, check_failures=4),
                         A.ArmStats(36, 30, 0, check_failures=6), min_trials=10)
    assert v["verdict"] == A.VERDICT_NO_TRIGGER


def test_retirement_survives_both_polarity_guards():
    """THE control. Two guards that between them make retirement impossible would be
    as wrong as none. A skill whose checks demonstrably both pass and fail, with the
    arms level, is still a retire-candidate."""
    v = A.decide_verdict(A.ArmStats(90, 80, 90, check_failures=10),
                         A.ArmStats(90, 80, 0, check_failures=10), min_trials=10)
    assert v["verdict"] == A.VERDICT_RETIRE
    assert v["skill_lift"] == 0.0


def test_load_bearing_survives_both_polarity_guards():
    v = A.decide_verdict(A.ArmStats(90, 88, 90, check_failures=4),
                         A.ArmStats(90, 5, 0, check_failures=85), min_trials=10)
    assert v["verdict"] == A.VERDICT_LOAD_BEARING
    assert v["skill_lift"] > 0.9


# ---------------------------------------------------------------------------
# the noise band (BRO-4110): a description beside the verdict, never a test
# ---------------------------------------------------------------------------

import contextlib  # noqa: E402
import io  # noqa: E402
import itertools  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import patch  # noqa: E402

DECISIVE = {A.VERDICT_LOAD_BEARING, A.VERDICT_RETIRE}
RANK = {A.VERDICT_LOAD_BEARING: 2, A.VERDICT_RETIRE: 2}  # everything else ranks 0


def prompts_report(per_prompt, *, error_prompts=(), order=None):
    """A report with one positive case per entry of `per_prompt` = [(passes, n), ...]."""
    cases = []
    for i, (passes, n) in enumerate(per_prompt):
        if i in error_prompts:
            results = [{"outcome": "ERROR"}] * n
        else:
            results = ([trial("PASS", [chk("x", passed=True)], triggered=True)] * passes
                       + [trial("FAIL", [chk("x", passed=False)], triggered=True)] * (n - passes))
        cases.append({"case_id": f"p{i}", "should_trigger": True, "results": results})
    if order is not None:
        cases = [cases[i] for i in order]
    return report(cases=cases)


def band_compare(present, absent, replicate, *, replicate_errors=(), **kw):
    return A.compare(prompts_report(present), prompts_report(absent), non_pass=NON_PASS,
                     min_trials=10,
                     replicate_report=prompts_report(replicate, error_prompts=replicate_errors),
                     **kw)


def plain_compare(present, absent, **kw):
    return A.compare(prompts_report(present), prompts_report(absent), non_pass=NON_PASS,
                     min_trials=10, **kw)


def test_without_a_replicate_nothing_changes_and_noise_is_null():
    cmp = plain_compare([(3, 3)] * 10, [(0, 3)] * 10)
    assert cmp["noise"] is None
    assert "  replicate    not run (--noise-band adds it)" in A.format_comparison(cmp)


VERDICT_KEYS = ("verdict", "why", "skill_lift", "skill_lift_ci", "end_to_end_lift",
                "present", "absent", "leaked_baseline_trials")


def test_the_band_never_changes_the_verdict():
    """The contract after five P20 rounds (D8): the band describes, it never decides.
    Every verdict field is identical with and without it, over seeded random prompt
    sets with errors in any arm and over every two-prompt clustered outcome."""
    outcomes = [(0, 3), (1, 3), (2, 3), (3, 3), (0, 1), (1, 1), (5, 20)]
    rng = random.Random(4110)

    def errs(n):
        return tuple(i for i in range(n) if rng.random() < 0.3)
    cases = []
    for _ in range(600):
        n = rng.randint(1, 8)
        cases.append(([rng.choice(outcomes) for _ in range(n)],
                      [rng.choice(outcomes) for _ in range(n)],
                      [rng.choice(outcomes) for _ in range(n)], errs(n), errs(n), errs(n)))
    clustered = [(0, 12), (12, 12)]
    for P in itertools.product(clustered, repeat=2):
        for B in itertools.product(clustered, repeat=2):
            for R_ in itertools.product(clustered, repeat=2):
                cases.append((list(P), list(B), list(R_), (), (), ()))
    for P, B, R_, pe, be, re_ in cases:
        p, b = prompts_report(P, error_prompts=pe), prompts_report(B, error_prompts=be)
        plain = A.compare(p, b, non_pass=NON_PASS, min_trials=10)
        banded = A.compare(p, b, non_pass=NON_PASS, min_trials=10,
                           replicate_report=prompts_report(R_, error_prompts=re_))
        assert {k: banded[k] for k in VERDICT_KEYS} == {k: plain[k] for k in VERDICT_KEYS}, (P, B, R_)


def test_the_replicate_row_is_the_whole_arm():
    """P20 continuation r5: an earlier version silently dropped replicate trials on
    prompts the present arm could not grade. The row now matches its neighbours."""
    P = [(3, 3)] * 4
    p = prompts_report(P, error_prompts=(0,))
    cmp = A.compare(p, prompts_report(P), non_pass=NON_PASS, min_trials=1,
                    replicate_report=prompts_report(P))
    assert cmp["noise"]["replicate"]["graded_positive_trials"] == 12


def test_the_band_computes_no_number_across_the_arms():
    """D11's reversal (continuation review before round 6): the noise dict carries the
    replicate arm and its attempts, nothing derived from present and replicate together."""
    cmp = band_compare([(9, 10)] * 3, [(0, 10)] * 3, [(6, 10)] * 3)
    assert set(cmp["noise"]) == {"replicate", "replicate_attempts", "replicate_errors"}
    assert cmp["noise"]["replicate"] == A.arm_stats(prompts_report([(6, 10)] * 3), NON_PASS).to_dict()


def test_the_report_describes_and_does_not_test():
    """No p-value, threshold, NOTE, gap or verdict language comes from the band."""
    text = A.format_comparison(band_compare([(3, 3)] * 10, [(0, 3)] * 10, [(2, 3)] * 10))
    assert re.search(r"(?m)^  replicate\s+30\s+30\s+0\.67\s+1\.00$", text), text
    assert "Not tested (BRO-4140)" in text
    for word in ("p=", "NOTE", "confirmed", "drifted", "noisy", "gap", "minus"):
        assert word not in text, word


def test_end_to_end_lift_is_untouched_by_the_band():
    P, B = [(3, 3)] * 10, [(0, 3)] * 10
    p, b = prompts_report(P), prompts_report(B)
    p["aggregate"] = {"positive": {"pass_rate": 0.9}}
    with_band = A.compare(p, b, non_pass=NON_PASS, min_trials=10,
                          replicate_report=prompts_report(P))
    without = A.compare(p, b, non_pass=NON_PASS, min_trials=10)
    assert with_band["end_to_end_lift"] == without["end_to_end_lift"] is not None


def test_a_margin_above_one_is_refused():
    with pytest.raises(SystemExit) as exc:
        R.main(["--skill-dir", str(FIXTURE / "skill"),
                "--prompts", str(FIXTURE / "evals/prompts.json"), "--cli", "/bin/true",
                "--no-version-check", "--ablate", "--dry-run", "--ablation-margin", "1.1"])
    assert exc.value.code == 2


def test_a_non_finite_margin_is_refused_before_any_arm_runs():
    with pytest.raises(SystemExit) as exc:
        R.main(["--skill-dir", str(FIXTURE / "skill"),
                "--prompts", str(FIXTURE / "evals/prompts.json"), "--cli", "/bin/true",
                "--no-version-check", "--ablate", "--noise-band", "--dry-run",
                "--ablation-margin", "nan"])
    assert exc.value.code == 2


def test_exit_four_does_not_read_as_a_threshold_failure():
    text = R.format_report([], R.aggregate([], case_threshold=R.DEFAULT_CASE_THRESHOLD),
                           mode="live", skill="demo", threshold=0.8,
                           exit_code=R.EXIT_ABLATION_UNUSABLE)
    assert "-> PASS (exit 4)" in text


# --- the runner: the replicate arm as it is actually wired ---------------------------

FIXTURE = Path("tests/skill_evals/fixtures/harness-selftest")
BASE_ARGS = ["--skill-dir", str(FIXTURE / "skill"), "--prompts", str(FIXTURE / "evals/prompts.json"),
             "--cli", "/bin/true", "--no-version-check", "--ablate", "--json", "--trials", "4"]


def stubbed_main(tmp_path, *args, write_during=None, actions=None, outcome=None,
                 baseline_outcome=None):
    """Run R.main with every trial stubbed; record each arm's config. A real
    RealStateWatch watches one file that `write_during` (an arm number) touches."""
    watched = tmp_path / "state"
    watched.write_text("before")
    arms = []
    real_run_suite, real_watch = R.run_suite, R.jail_mod.RealStateWatch

    def case_runner(runner, case, cfg):
        o = (baseline_outcome if not cfg.visibility.expects_visible and baseline_outcome
             else outcome) or R.PASS
        trials = [R.TrialResult(case.id, t, o, triggered=cfg.visibility.expects_visible,
                                checks=[{"check_id": "x", "passed": o == R.PASS}])
                  for t in range(1, cfg.trials + 1)]
        return R.CaseResult(case.id, case.should_trigger, case.origin, trials=trials)

    def suite(runner, prompts, cfg):
        arms.append({"visibility": cfg.visibility.id, "cases": [c.id for c in prompts.cases],
                     "positives_only": all(c.should_trigger for c in prompts.cases),
                     "jobs": cfg.jobs, "keep_workspaces": cfg.keep_workspaces})
        if write_during == len(arms):
            watched.write_text(f"written during arm {len(arms)}")
        if actions and len(arms) in actions:
            actions[len(arms)](watched)
        return real_run_suite(runner, prompts, cfg)

    out = io.StringIO()
    with patch.object(R, "run_suite", suite), patch.object(R, "run_case", case_runner), \
         patch.object(R.jail_mod, "RealStateWatch", lambda: real_watch(paths=(str(watched),))), \
         patch.object(R.jail_mod, "prepare_jail"), \
         patch.object(R.jail_mod, "verify_jail", return_value=SimpleNamespace(holds=True)), \
         patch.object(R.jail_mod, "auth_material_missing", return_value=False), \
         contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = R.main(BASE_ARGS + list(args))
    return rc, json.loads(out.getvalue()), arms


def test_the_replicate_runs_the_positives_with_the_skill_present(tmp_path):
    """P20 round 1: none of this was pinned; six wiring mutations survived."""
    rc, rep, arms = stubbed_main(tmp_path, "--noise-band", "--jobs", "3",
                                 "--ablate-baseline", "bare")
    assert len(arms) == 3
    present, baseline, replicate = arms
    assert replicate["visibility"] == present["visibility"] == "present"
    assert replicate["positives_only"] is True
    assert set(replicate["cases"]) < set(present["cases"])
    assert replicate["jobs"] == 3
    assert rep["ablation"]["noise"] is not None
    assert rep["ablation"]["noise"]["replicate"]["graded_positive_trials"] == 4 * len(replicate["cases"])
    assert rep["ablation_replicate_arm"]["meta"]["arm"] == "present-replicate"


def test_without_the_flag_no_replicate_runs(tmp_path):
    _, rep, arms = stubbed_main(tmp_path)
    assert len(arms) == 2 and rep["ablation"]["noise"] is None


@pytest.mark.parametrize("arm", [2, 3])
def test_a_state_change_during_an_ablation_arm_is_seen(tmp_path, arm):
    """P20 round 1: the watch was read after the primary arm only, so a write during
    the baseline (pre-existing) or the replicate passed --fail-on-real-state-change."""
    rc, rep, _ = stubbed_main(tmp_path, "--noise-band", "--fail-on-real-state-change",
                              write_during=arm)
    assert rep["meta"].get("real_state_changes"), arm
    assert rc != R.EXIT_OK


def test_noise_band_without_ablate_is_refused():
    for extra in (["--dry-run"], ["--validate-only"]):
        rc = R.main([
            "--skill-dir", str(FIXTURE / "skill"), "--prompts", str(FIXTURE / "evals/prompts.json"),
            "--cli", "/bin/true", "--no-version-check", "--noise-band", *extra,
        ])
        assert rc == R.EXIT_USAGE, extra


def test_the_dry_run_counts_the_replicate_exactly(capsys):
    prompt_set = json.loads((FIXTURE / "evals/prompts.json").read_text())
    cases = prompt_set["cases"]
    positives = sum(1 for c in cases if c.get("should_trigger"))
    rc = R.main(["--skill-dir", str(FIXTURE / "skill"), "--prompts", str(FIXTURE / "evals/prompts.json"),
                 "--cli", "/bin/true", "--no-version-check", "--ablate", "--noise-band",
                 "--dry-run", "--trials", "2"])
    assert rc == R.EXIT_OK
    expected = len(cases) * 2 + positives * 2 + positives * 2
    assert f"would run {expected} trial(s)" in capsys.readouterr().out


# --- P20 round 5 on #336 (stratum A) --------------------------------------------------

def _trigger_only(n):
    return [trial("PASS", [chk("skill_triggered", passed=True)], triggered=True)] * n


def _outcome(passes, n):
    return ([trial("PASS", [chk("x", passed=True)], triggered=True)] * passes
            + [trial("FAIL", [chk("x", passed=False)], triggered=True)] * (n - passes))


def _cases(*results):
    return report(cases=[{"case_id": f"p{i}", "should_trigger": True, "results": r}
                         for i, r in enumerate(results)])


def test_a_trigger_only_replicate_row_uses_the_same_denominator_as_present():
    # The continuation review's probe 7b: the row is arm_stats(), like its neighbours,
    # so a trigger-only replicate reads as its neighbours would, and no gap line contradicts it.
    present = _cases(_trigger_only(6), _outcome(6, 6))
    replicate = _cases(_trigger_only(6), [{"outcome": "ERROR"}] * 6)
    cmp = A.compare(present, _cases(_outcome(3, 6), _outcome(3, 6)), non_pass=NON_PASS,
                    min_trials=10, replicate_report=replicate)
    assert cmp["noise"]["replicate"] == A.arm_stats(replicate, NON_PASS).to_dict()
    assert cmp["present"] == A.arm_stats(present, NON_PASS).to_dict()
    text = A.format_comparison(cmp)
    assert "  replicate    6 of 12 attempts produced no signal" in text
    assert "A/A" not in text


def test_the_replicate_row_and_its_errors_are_printed():
    cmp = band_compare([(3, 3)] * 4, [(1, 3)] * 4, [(3, 3)] * 4, replicate_errors=(0, 1, 2))
    text = A.format_comparison(cmp)
    assert re.search(r"(?m)^  replicate\s+3\s+3\s+1\.00\s+1\.00$", text), text
    assert "  replicate    9 of 12 attempts produced no signal" in text
    assert (cmp["noise"]["replicate_attempts"], cmp["noise"]["replicate_errors"]) == (12, 9)


def test_a_replicate_cannot_undo_a_baseline_change_before_the_watch_reads(tmp_path):
    moved = tmp_path / "moved-away"
    actions = {2: lambda w: w.rename(moved), 3: lambda w: moved.rename(w)}
    rc, rep, _ = stubbed_main(tmp_path, "--noise-band", "--fail-on-real-state-change",
                              actions=actions)
    assert any(c.startswith("deleted: ") for c in rep["meta"].get("real_state_changes", [])), rep["meta"]
    assert rc == R.EXIT_BELOW_THRESHOLD


@pytest.mark.parametrize("mode", [["--list-checks"], ["--verify-jail"]])
def test_every_mode_refuses_noise_band_without_ablate(mode):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert R.main([*mode, "--noise-band"]) == R.EXIT_USAGE


@pytest.mark.parametrize("margin", ["-0.01", "-1", "1.0001", "nan", "inf"])
def test_a_margin_outside_the_unit_interval_is_refused(margin):
    with contextlib.redirect_stderr(io.StringIO()), pytest.raises(SystemExit):
        R.build_parser().parse_args(["--skill", "x", "--ablation-margin", margin])


def test_a_state_exit_keeps_the_threshold_verdict():
    agg = R.aggregate([], case_threshold=R.DEFAULT_CASE_THRESHOLD)
    text = R.format_report([], agg, mode="live", skill="s", threshold=0.8,
                           exit_code=R.EXIT_BELOW_THRESHOLD, state_exit=True)
    assert "-> PASS (exit 1)" in text
    assert "exit 1 is --fail-on-real-state-change" in text
    plain = R.format_report([], agg, mode="live", skill="s", threshold=0.8,
                            exit_code=R.EXIT_BELOW_THRESHOLD)
    assert "-> FAIL (exit 1)" in plain and "fail-on-real-state-change" not in plain


@pytest.mark.parametrize("arm", [1, 2, 3])
def test_a_state_exit_names_its_cause_in_the_report(tmp_path, arm):
    rc, rep, _ = stubbed_main(tmp_path, "--noise-band", "--fail-on-real-state-change",
                              write_during=arm)
    assert rc == R.EXIT_BELOW_THRESHOLD
    assert rep.get("exit_cause") == "real_state_change", arm


def test_a_clean_run_names_no_exit_cause(tmp_path):
    rc, rep, _ = stubbed_main(tmp_path, "--noise-band", "--fail-on-real-state-change")
    assert rc == R.EXIT_OK and "exit_cause" not in rep


def test_replicate_attempts_count_positive_cases_like_the_graded_trials():
    rep = _cases(_outcome(3, 3))
    rep["cases"].append({"case_id": "n0", "should_trigger": False, "results": _outcome(0, 3)})
    band = A.noise_band(rep, NON_PASS)
    assert (band["replicate_attempts"], band["replicate_errors"]) == (3, 0)


def test_a_row_with_no_outcome_evidence_prints_na_not_zero():
    """P20 #336 r6 stratum B: equal trial counts from different prompts made a replicate
    that ran no outcome check read 0.00 beside a present arm's 1.00."""
    present = _cases(_outcome(12, 12), [{"outcome": "ERROR"}] * 12)
    replicate = _cases([{"outcome": "ERROR"}] * 12, _trigger_only(12))
    cmp = A.compare(present, _cases(_outcome(6, 12), _outcome(6, 12)), non_pass=NON_PASS,
                    min_trials=10, replicate_report=replicate)
    assert cmp["noise"]["replicate"]["outcome_checked_trials"] == 0
    assert cmp["present"]["outcome_checked_trials"] == 12
    text = A.format_comparison(cmp)
    assert re.search(r"(?m)^  present\s+12\s+12\s+1\.00\s+1\.00$", text), text
    assert re.search(r"(?m)^  replicate\s+12\s+0\s+n/a\s+1\.00$", text), text
    assert "equal counts can cover different prompts" in text


def test_the_checked_count_never_changes_a_verdict_field():
    present = _cases(_trigger_only(6), _outcome(6, 6))
    absent = _cases(_outcome(3, 6), _outcome(3, 6))
    plain = A.compare(present, absent, non_pass=NON_PASS, min_trials=10)
    assert plain["present"]["outcome_checked_trials"] == 6
    assert plain["present"]["outcome_pass_rate"] == 0.5  # the verdict's rate is unchanged


def test_the_replicate_keeps_workspaces_like_the_other_arms(tmp_path):
    _, _, arms = stubbed_main(tmp_path, "--noise-band", "--keep-workspaces")
    assert [a["keep_workspaces"] for a in arms] == [True, True, True]


def test_the_replicate_arm_report_has_no_exit_status(tmp_path):
    _, rep, _ = stubbed_main(tmp_path, "--noise-band")
    assert rep["ablation_replicate_arm"]["exit_code"] is None


@pytest.mark.parametrize("trials", ["0", "-1"])
def test_trials_must_be_at_least_one(trials):
    with contextlib.redirect_stderr(io.StringIO()), pytest.raises(SystemExit):
        R.build_parser().parse_args(["--skill", "x", "--trials", trials])


@pytest.mark.parametrize("margin", ["0", "1", "0.08"])
def test_a_margin_at_or_inside_the_unit_interval_is_accepted(margin):
    args = R.build_parser().parse_args(["--skill", "x", "--ablation-margin", margin])
    assert args.ablation_margin == float(margin)


@pytest.mark.parametrize("arm", [1, 2, 3])
def test_a_state_change_does_not_override_an_earlier_failure(tmp_path, arm):
    """Exit precedence (P20 r6 C, mutant M08): a threshold failure stays exit 1 without a
    state cause; the state rule only replaces an exit 0, in the primary arm or after it."""
    rc, rep, _ = stubbed_main(tmp_path, "--noise-band", "--fail-on-real-state-change",
                              write_during=arm, outcome=R.FAIL)
    assert rc == R.EXIT_BELOW_THRESHOLD
    assert "exit_cause" not in rep


def test_an_unusable_baseline_does_not_override_a_state_exit(tmp_path):
    """Exit precedence (mutant M09): a state exit 1 is kept, with its cause, when the
    baseline is also unusable (exit 4 only replaces an exit 0)."""
    rc, rep, _ = stubbed_main(tmp_path, "--noise-band", "--fail-on-real-state-change",
                              write_during=3, baseline_outcome="ERROR")
    assert rc == R.EXIT_BELOW_THRESHOLD
    assert rep.get("exit_cause") == "real_state_change"


@pytest.mark.parametrize("unchecked", ["present", "absent"])
@pytest.mark.parametrize("band", [False, True])
def test_an_arm_with_no_outcome_evidence_gets_no_actionable_verdict(unchecked, band):
    """Continuation review before r7: an arm whose trials ran no outcome check entered
    the lift as rate 0.0, giving load-bearing or retire-candidate on no evidence."""
    checked = _cases(_outcome(12, 12), _outcome(12, 12))
    trigger_only = _cases(_trigger_only(12), _trigger_only(12))
    absent_checked = _cases(_outcome(3, 12), _outcome(3, 12))
    present, absent = ((trigger_only, absent_checked) if unchecked == "present"
                       else (checked, trigger_only))
    cmp = A.compare(present, absent, non_pass=NON_PASS, min_trials=10,
                    replicate_report=checked if band else None)
    assert cmp["verdict"] == A.VERDICT_WEAK_CHECKS
    assert cmp["skill_lift"] is None
    assert f"no {unchecked}-arm trial ran an outcome check" in cmp["why"]
    text = A.format_comparison(cmp)
    assert "skill lift   NOT MEASURED" in text


def test_stats_built_without_counting_are_not_treated_as_unchecked():
    p = A.ArmStats(graded_positive_trials=20, outcome_passes=18, trigger_events=20, check_failures=2)
    b = A.ArmStats(graded_positive_trials=20, outcome_passes=2, trigger_events=0, check_failures=18)
    assert A.decide_verdict(p, b)["verdict"] == A.VERDICT_LOAD_BEARING


def test_a_row_built_without_counting_shows_its_rate_and_no_checked_count():
    stats = A.ArmStats(graded_positive_trials=4, outcome_passes=3, trigger_events=4).to_dict()
    cmp = {"skill": "s", "present": stats, "absent": stats, "noise": None, "skill_lift": None,
           "verdict": "v", "why": "w"}
    assert re.search(r"(?m)^  present\s+4\s+n/a\s+0\.75\s+1\.00$", A.format_comparison(cmp))
