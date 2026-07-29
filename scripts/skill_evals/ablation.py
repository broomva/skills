#!/usr/bin/env python3
"""ablation — is this skill still earning its rent? (BRO-2006)

Capability skills are temporary. Every model release absorbs a little more of what
they encode, and an absorbed skill is pure cost: it pays frontmatter rent on every
turn (see ``listing.py`` — that rent is now provably rationed) while changing
nothing about the answer. We had 376 skills and no mechanism for detecting which
ones the base model had already learned.

The measurement is a two-arm run of the SAME prompt set: once with the skill
installed, once without. The difference in outcome quality is the skill's lift.

WHY THE GRADING HAS TO CHANGE, NOT JUST THE WORKSPACE
-----------------------------------------------------
In the absent arm ``should_trigger`` is meaningless — an uninstalled skill cannot
fire, and cannot over-fire either. Scoring it with the present arm's rules gives the
baseline a guaranteed zero, so every skill looks maximally load-bearing and the
sweep recommends nothing. Scoring it by ignoring the trigger assertion *silently*
gives the opposite error. So the runner grades the baseline on OUTCOME checks only,
records the skipped ones as ``passed: null``, and this module computes lift from the
check results rather than from the trial outcome.

WHAT A NUMBER FROM THIS DOES AND DOES NOT MEAN
----------------------------------------------
Three limits, all of which change what a verdict is worth, and none of which the
harness can remove:

* **The baseline is not a bare model.** The absent arm still has the CLI's built-in
  skills. Lift is marginal value over *those*, not over nothing.
* **Tool-bearing skills are not comparable.** For ``p9``, ``kg`` and ``dogfood`` the
  absent arm removes executable scripts, not just instructions, so lift approaches
  1.0 for a reason unrelated to description rent. Those verdicts are not evidence
  about absorption.
* **Absorption is a NON-INFERIORITY claim** and cannot be proven by a point estimate
  of zero. The verdict is therefore driven by a confidence interval against a
  margin, never by ``lift == 0``, and an underpowered run says so instead of
  guessing. At the default 3 trials the interval is roughly ±0.28 wide, so most
  honest verdicts will be ``indeterminate``.

A missing or unusable measurement serialises ``skill_lift: null``, never ``0.0``.
A defaulted zero reads as perfect absorption, which is the single most dangerous
vacuity available here.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from skill_evals import checks as checks_mod  # noqa: E402

#: Below this many graded positive trials per arm, say "underpowered" rather than
#: report a verdict a reader would act on.
ABLATION_MIN_TRIALS = 10

#: A skill whose lift interval sits entirely below this is a retirement candidate.
ABLATION_MARGIN = 0.10

VERDICT_NAME_COLLISION = "inconclusive-name-collision"
VERDICT_UNDERPOWERED = "inconclusive-underpowered"
VERDICT_NO_TRIGGER = "inconclusive-no-trigger"
VERDICT_WEAK_CHECKS = "inconclusive-weak-checks"
VERDICT_RETIRE = "retire-candidate"
VERDICT_LOAD_BEARING = "load-bearing"
VERDICT_INDETERMINATE = "indeterminate"


# ---------------------------------------------------------------------------
# the arm-symmetric numerator
# ---------------------------------------------------------------------------


def _check_passed(entry: dict[str, Any]) -> bool | None:
    """``None`` for a check that does not count toward the lift — neither pass nor fail.

    A trigger-dependent check is excluded in BOTH arms, not only in the one that
    marked it skipped. That is what makes the numerator arm-SYMMETRIC, and getting it
    wrong does not round the answer off — it inverts it.

    The first version excluded only what the absent arm had flagged, so the present
    arm was graded on a strict SUPERSET: it had to fire AND satisfy the outcome
    checks, while the baseline only had to satisfy the outcome checks. Every
    present-arm trial where the skill did not fire became a lift PENALTY.

    Reproduced on ``kg``'s committed prompt set — 9 positive cases, every one
    asserting ``skill_triggered`` — at default flags: a skill firing on 22 of 27
    trials (81%, which clears the harness's own 0.80 threshold) against a baseline
    that trivially satisfies "non-empty answer, no permission denials" scores lift
    **-0.19**, CI [-0.37, -0.02], verdict **retire-candidate**. A skill that passes
    its own eval gate, recommended for deletion — the one consequence this module
    exists to prevent, produced by the line named "the arm-symmetric numerator".

    Nothing is lost by excluding it: trigger behaviour is reported separately and
    correctly through :attr:`ArmStats.trigger_rate` and ``end_to_end_lift``.
    """
    if entry.get("skipped"):
        return None
    if entry.get("check_id") in checks_mod.TRIGGER_DEPENDENT_CHECKS:
        return None
    passed = entry.get("passed")
    return bool(passed) if passed is not None else None


def outcome_passed(trial: dict[str, Any]) -> bool:
    """Did every check that RAN in this trial pass?

    Computed from ``checks``, not from ``outcome``, because ``outcome`` embeds the
    trigger assertion and so is not comparable between arms — which is the whole
    difficulty of this measurement. A trial with no runnable checks is not a pass:
    it asserted nothing.
    """
    states = [_check_passed(c) for c in trial.get("checks") or []]
    ran = [s for s in states if s is not None]
    return bool(ran) and all(ran)


def _positive_trials(cases: Iterable[dict[str, Any]], non_pass: Sequence[str]) -> list[dict]:
    out: list[dict] = []
    for case in cases:
        if not case.get("should_trigger"):
            continue
        for trial in case.get("results") or []:
            if trial.get("outcome") in non_pass:
                continue  # produced no signal — an attempt, not evidence
            out.append(trial)
    return out


@dataclass(frozen=True)
class ArmStats:
    graded_positive_trials: int
    outcome_passes: int
    trigger_events: int
    #: How many graded checks FAILED in this arm. The discriminating-power counter:
    #: if no check ever failed in either arm, a lift of zero is a tautology rather
    #: than evidence of absorption.
    check_failures: int = 0

    @property
    def outcome_pass_rate(self) -> float | None:
        n = self.graded_positive_trials
        return (self.outcome_passes / n) if n else None

    @property
    def trigger_rate(self) -> float | None:
        n = self.graded_positive_trials
        return (self.trigger_events / n) if n else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "graded_positive_trials": self.graded_positive_trials,
            "outcome_passes": self.outcome_passes,
            "outcome_pass_rate": self.outcome_pass_rate,
            "trigger_rate": self.trigger_rate,
            "check_failures": self.check_failures,
        }


def arm_stats(report: dict[str, Any], non_pass: Sequence[str]) -> ArmStats:
    trials = _positive_trials(report.get("cases") or [], non_pass)
    return ArmStats(
        graded_positive_trials=len(trials),
        outcome_passes=sum(1 for t in trials if outcome_passed(t)),
        trigger_events=sum(1 for t in trials if t.get("triggered")),
        check_failures=sum(
            1 for t in trials for c in (t.get("checks") or [])
            if _check_passed(c) is False
        ),
    )


# ---------------------------------------------------------------------------
# interval — Newcombe hybrid score, on the difference of two proportions
# ---------------------------------------------------------------------------


def wilson_interval(successes: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    """95% Wilson score interval for one proportion. Pure stdlib.

    Wilson rather than the normal approximation because these samples are tiny and
    the rates sit near 0 and 1, where the normal interval runs outside [0, 1] and
    silently understates uncertainty at exactly the values a retirement decision
    turns on.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def newcombe_difference(s1: int, n1: int, s2: int, n2: int) -> tuple[float, float]:
    """95% interval for ``p1 - p2`` (Newcombe's hybrid-score method)."""
    if n1 <= 0 or n2 <= 0:
        return (-1.0, 1.0)
    p1, p2 = s1 / n1, s2 / n2
    l1, u1 = wilson_interval(s1, n1)
    l2, u2 = wilson_interval(s2, n2)
    lower = (p1 - p2) - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = (p1 - p2) + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (max(-1.0, lower), min(1.0, upper))


# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------


def decide_verdict(
    present: ArmStats,
    absent: ArmStats,
    *,
    name_collision: bool = False,
    leaked: int = 0,
    min_trials: int = ABLATION_MIN_TRIALS,
    margin: float = ABLATION_MARGIN,
) -> dict[str, Any]:
    """The verdict, and — always — the reason it is what it is.

    Ordered so that every reason a number would be untrustworthy is checked BEFORE
    the number is used. ``skill_lift`` is ``None`` for each of those, never 0.0.
    """
    def undecided(name: str, why: str) -> dict[str, Any]:
        return {"verdict": name, "why": why, "skill_lift": None, "skill_lift_ci": None,
                "end_to_end_lift": None}

    if name_collision:
        return undecided(
            VERDICT_NAME_COLLISION,
            "the skill's name is also a built-in, so the absent arm is undefined",
        )
    if leaked:
        return undecided(
            VERDICT_NAME_COLLISION if name_collision else VERDICT_UNDERPOWERED,
            f"{leaked} baseline trial(s) LEAKED — the skill was present in an arm that "
            "requires it absent, so the baseline is contaminated",
        )
    if min(present.graded_positive_trials, absent.graded_positive_trials) < min_trials:
        return undecided(
            VERDICT_UNDERPOWERED,
            f"fewer than {min_trials} graded positive trials in an arm "
            f"(present={present.graded_positive_trials}, absent={absent.graded_positive_trials}); "
            "raise --trials or add positive cases",
        )
    # Order matters: a skill that never FIRES is diagnosed as a trigger problem, not
    # as a check problem, because the remedies are opposite. This gate used to sit
    # above the trigger one and told an operator with a dead description to go
    # strengthen their checks.
    trig = present.trigger_rate
    if trig is None or trig < 0.5:
        return undecided(
            VERDICT_NO_TRIGGER,
            f"the skill fired in only {trig:.0%} of present-arm trials — an ablation "
            "cannot separate absorption from a trigger failure. Fix the description first."
            if trig is not None else "no present-arm trials",
        )

    # A retirement verdict needs the graded checks to DISCRIMINATE, and the test for
    # that is that they are NOT CONSTANT: at least one pass AND at least one failure
    # somewhere in the measurement.
    #
    # The first version asked only "did any check fail", which closes one polarity and
    # leaves its mirror wide open. A check that fails in EVERY trial of BOTH arms is
    # exactly as non-discriminating as one that always passes — and it satisfies a
    # failure-count gate, so lift comes out 0.0 with a narrow interval and the verdict
    # is retire-candidate on a run where the present arm passed NOTHING. That is
    # reachable without any exotic input: `run_checks` records `passed=False` for a
    # check that RAISES, so a single buggy predicate in CHECK_REGISTRY turns a whole
    # sweep into "retire everything"; and an environment-invariant failure (the env
    # jail denying a tool the skill needs, failing `no_permission_denials` in both
    # arms) produces the same shape with nothing broken at all.
    #
    # The main report path already carries this floor — runner.py's "ZERO POSITIVE
    # PASSES ... no --threshold lowers this floor". The verdict that recommends
    # DELETING a skill had no equivalent, which is the wrong way round.
    total_passes = present.outcome_passes + absent.outcome_passes
    total_failures = present.check_failures + absent.check_failures
    if not total_failures:
        return undecided(
            VERDICT_WEAK_CHECKS,
            "no graded check failed in either arm, so the lift is 0.0 by construction "
            "— these checks cannot tell the two arms apart. Strengthen the prompt set's "
            "expected_checks before reading this as absorption",
        )
    if not total_passes:
        return undecided(
            VERDICT_WEAK_CHECKS,
            "no graded check passed in either arm — the lift is 0.0 by construction for "
            "the mirror reason. Suspect a check that always fails (one that RAISES is "
            "recorded as failed) or an environment-invariant failure, not absorption",
        )

    lift = (present.outcome_pass_rate or 0.0) - (absent.outcome_pass_rate or 0.0)
    lo, hi = newcombe_difference(
        present.outcome_passes, present.graded_positive_trials,
        absent.outcome_passes, absent.graded_positive_trials,
    )
    result = {
        "skill_lift": round(lift, 4),
        "skill_lift_ci": [round(lo, 4), round(hi, 4)],
        "end_to_end_lift": None,
    }
    if hi < margin:
        result.update(verdict=VERDICT_RETIRE, why=(
            f"the whole 95% interval for the lift sits below the {margin} margin — the "
            "base model does about as well without it"))
    elif lo > 0:
        result.update(verdict=VERDICT_LOAD_BEARING, why=(
            "the 95% interval for the lift is entirely above zero"))
    else:
        result.update(verdict=VERDICT_INDETERMINATE, why=(
            f"the interval [{lo:.2f}, {hi:.2f}] straddles the {margin} margin; more trials "
            "are needed before this supports a decision"))
    return result


def compare(
    present_report: dict[str, Any],
    absent_report: dict[str, Any],
    *,
    non_pass: Sequence[str],
    builtin_names: Iterable[str] = (),
    min_trials: int = ABLATION_MIN_TRIALS,
    margin: float = ABLATION_MARGIN,
) -> dict[str, Any]:
    """The full two-arm comparison, as it lands in the JSON report."""
    skill = str(present_report.get("skill") or "")
    present = arm_stats(present_report, non_pass)
    absent = arm_stats(absent_report, non_pass)
    leaked = sum(
        1
        for case in absent_report.get("cases") or []
        for t in case.get("results") or []
        if t.get("outcome") == "LEAKED"
    )
    verdict = decide_verdict(
        present, absent,
        name_collision=skill in set(builtin_names),
        leaked=leaked,
        min_trials=min_trials,
        margin=margin,
    )
    # Trigger-inclusive, and reported SEPARATELY on purpose: a low end-to-end lift
    # with a high skill lift means "fix the description", not "retire the skill".
    # Collapsing the two is how an ablation recommends deleting a skill whose only
    # fault is that it does not fire.
    if verdict.get("skill_lift") is not None:
        e2e_present = (present_report.get("aggregate") or {}).get("positive", {}).get("pass_rate")
        if e2e_present is not None and absent.outcome_pass_rate is not None:
            verdict["end_to_end_lift"] = round(e2e_present - absent.outcome_pass_rate, 4)
    return {
        "skill": skill,
        "present": present.to_dict(),
        "absent": absent.to_dict(),
        "leaked_baseline_trials": leaked,
        **verdict,
    }


def format_comparison(cmp: dict[str, Any]) -> str:
    p, a = cmp["present"], cmp["absent"]

    def rate(v: float | None) -> str:
        return "  n/a" if v is None else f"{v:5.2f}"

    lines = [
        "",
        f"ABLATION  {cmp['skill']}",
        "-" * 68,
        f"  {'arm':10}{'trials':>8}{'outcome':>9}{'trigger':>9}",
        f"  {'present':10}{p['graded_positive_trials']:>8}"
        f"{rate(p['outcome_pass_rate']):>9}{rate(p['trigger_rate']):>9}",
        f"  {'absent':10}{a['graded_positive_trials']:>8}"
        f"{rate(a['outcome_pass_rate']):>9}{'  n/a':>9}",
        "-" * 68,
    ]
    if cmp.get("skill_lift") is None:
        lines.append(f"  skill lift   NOT MEASURED — {cmp['verdict']}")
    else:
        lo, hi = cmp["skill_lift_ci"]
        lines.append(f"  skill lift   {cmp['skill_lift']:+.2f}  95% CI [{lo:+.2f}, {hi:+.2f}]")
        if cmp.get("end_to_end_lift") is not None:
            lines.append(f"  end-to-end   {cmp['end_to_end_lift']:+.2f}  (trigger-inclusive)")
    lines.append(f"  VERDICT      {cmp['verdict']}")
    lines.append(f"               {cmp['why']}")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "ABLATION_MARGIN",
    "ABLATION_MIN_TRIALS",
    "ArmStats",
    "arm_stats",
    "compare",
    "decide_verdict",
    "format_comparison",
    "newcombe_difference",
    "outcome_passed",
    "wilson_interval",
]
