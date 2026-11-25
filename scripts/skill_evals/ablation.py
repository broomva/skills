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

THE NOISE BAND (``--noise-band``, BRO-4110) — a measurement, not a verdict
--------------------------------------------------------------------------
The interval above treats every trial as an independent coin, but ``--trials``
repeats each prompt and a prompt's trials pass or fail together, so that interval is
too narrow. ``--noise-band`` adds a second, identical with-skill arm (the replicate)
and REPORTS, beside the verdict:

* the lift across prompts: the mean per-prompt difference and a sign-flip p-value;
* the A/A drift: the same for the two identical with-skill arms.

It never changes the verdict. Four P20 rounds tried to let it (a point-estimate gap,
a union of intervals, downgrade-only sign-flip gates); each time a reachable input
made the gate wrong, because the arms run one after another (a shift on one whole arm
reads as an effect), trials per prompt can differ (which breaks the sign symmetry the
test needs), and prompts can carry trigger checks only. Making verdicts react to noise
belongs with interleaving the arms (BRO-4140). Until then the band shows a reader when
the verdict outruns the prompt-level evidence: the report says so in words when the
verdict is load-bearing but the prompt-level p is not below 0.025, or when the
drift's p is below 0.05. The idea of an A/A band is Uber's (2026-11-23 post on skill
evals).

A missing or unusable measurement serialises ``skill_lift: null``, never ``0.0``.
A defaulted zero reads as perfect absorption, which is the single most dangerous
vacuity available here.
"""

from __future__ import annotations

import functools
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
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

#: The levels at which the report adds an advisory note (it changes no verdict).
ALPHA_ONE_SIDED = Fraction(1, 40)   # 0.025
ALPHA_DRIFT = Fraction(1, 20)       # 0.05, two-sided
#: Past this many distinct partial sums the exact enumeration gives way to a seeded
#: Monte Carlo estimate, so unequal graded counts cannot blow up memory.
EXACT_STATE_CAP = 200_000
MONTE_CARLO_DRAWS = 20_000


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


# ---------------------------------------------------------------------------
# the noise band — exact sign-flip tests over prompts (BRO-4110)
# ---------------------------------------------------------------------------


def prompt_rates(report: dict[str, Any], non_pass: Sequence[str]) -> dict[str, Fraction]:
    """{prompt id: exact outcome pass rate} over positive cases with a graded trial."""
    out: dict[str, Fraction] = {}
    for i, case in enumerate(report.get("cases") or []):
        if not case.get("should_trigger"):
            continue
        key = str(case.get("case_id") or case.get("id") or f"#{i}")
        st = arm_stats({"cases": [case]}, non_pass)
        if st.graded_positive_trials:
            out[key] = Fraction(st.outcome_passes, st.graded_positive_trials)
    return out


def _sign_flip_sums(nums: Sequence[int]) -> dict[int, int] | None:
    """Distribution of the signed sum over all 2^n sign vectors; None past the cap."""
    dist: dict[int, int] = {0: 1}
    for a in nums:
        if 2 * len(dist) > EXACT_STATE_CAP:  # checked BEFORE the next map is built
            return None
        nxt: dict[int, int] = defaultdict(int)
        for total, count in dist.items():
            nxt[total + a] += count
            nxt[total - a] += count
        dist = nxt
    return dist


def sign_flip_p(diffs: Sequence[Fraction], tail: str) -> Fraction:
    """Sign-flip p-value that per-prompt differences are centred on zero.

    tail="greater": evidence the centre is above zero; "two": either way. Exact by
    enumeration in integers scaled to the common denominator; past EXACT_STATE_CAP a
    seeded Monte Carlo estimate (hits+1)/(draws+1), which never reports p = 0.
    """
    if not diffs:
        return Fraction(1)
    den = math.lcm(*(d.denominator for d in diffs))
    # Sorted, so the seeded Monte Carlo branch does not depend on report order.
    nums = sorted(int(d * den) for d in diffs)
    obs = sum(nums)

    def hit(total: int) -> bool:
        return total >= obs if tail == "greater" else abs(total) >= abs(obs)

    dist = _sign_flip_sums(nums)
    if dist is not None:
        return Fraction(sum(c for t, c in dist.items() if hit(t)), 2 ** len(nums))
    import random
    rng = random.Random(0)
    hits = sum(1 for _ in range(MONTE_CARLO_DRAWS)
               if hit(sum(a if rng.random() < 0.5 else -a for a in nums)))
    return Fraction(hits + 1, MONTE_CARLO_DRAWS + 1)


@dataclass(frozen=True)
class NoiseBand:
    lift_diffs: tuple[Fraction, ...]    # present - absent, prompts graded in both
    drift_diffs: tuple[Fraction, ...]   # present - replicate, prompts graded in both
    replicate: ArmStats                 # the replicate on the prompts shared with present

    @staticmethod
    def _mean(diffs) -> float | None:
        return float(sum(diffs) / len(diffs)) if diffs else None

    @functools.cached_property
    def p_lift(self) -> Fraction:
        return sign_flip_p(self.lift_diffs, "greater")

    @functools.cached_property
    def p_drift(self) -> Fraction | None:
        return sign_flip_p(self.drift_diffs, "two") if len(self.drift_diffs) >= 2 else None

    @property
    def drifted(self) -> bool | None:
        p = self.p_drift
        return None if p is None else p < ALPHA_DRIFT

    def to_dict(self) -> dict[str, Any]:
        def f(x):
            return None if x is None else round(float(x), 4)
        mean = self._mean
        return {
            "replicate": self.replicate.to_dict(),
            "lift_prompts": len(self.lift_diffs),
            "lift_prompt_mean": f(mean(self.lift_diffs)),
            "p_lift": f(self.p_lift),
            "drift_prompts": len(self.drift_diffs),
            "drift_prompt_mean": f(mean(self.drift_diffs)),
            "p_drift": f(self.p_drift),
            "drifted": self.drifted,
            # Exact (Fraction) comparisons, so a rounded display cannot cross a level.
            "lift_confirmed": bool(self.lift_diffs) and self.p_lift < ALPHA_ONE_SIDED,
        }


def noise_band(present: dict, absent: dict, replicate: dict,
               non_pass: Sequence[str]) -> NoiseBand:
    """Pair prompts by id. The lift uses prompts graded in present and absent; the
    drift uses prompts graded in present and replicate. Neither restricts the other.
    The replicate's trial count is taken on the shared prompts only: trials on a prompt
    the present arm did not grade are no A/A evidence."""
    p, a, r = (prompt_rates(x, non_pass) for x in (present, absent, replicate))
    rep_shared = {"cases": [c for i, c in enumerate(replicate.get("cases") or [])
                            if str(c.get("case_id") or c.get("id") or f"#{i}") in p]}
    return NoiseBand(
        lift_diffs=tuple(p[k] - a[k] for k in p if k in a),
        drift_diffs=tuple(p[k] - r[k] for k in p if k in r),
        replicate=arm_stats(rep_shared, non_pass),
    )


def compare(
    present_report: dict[str, Any],
    absent_report: dict[str, Any],
    *,
    non_pass: Sequence[str],
    builtin_names: Iterable[str] = (),
    min_trials: int = ABLATION_MIN_TRIALS,
    margin: float = ABLATION_MARGIN,
    replicate_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The full two-arm comparison, as it lands in the JSON report.

    ``replicate_report`` (``--noise-band``) adds the prompt-level measurement under
    ``noise``; it never changes the verdict.
    """
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
    band = None
    if replicate_report is not None:  # reported beside the verdict; never changes it
        band = noise_band(present_report, absent_report, replicate_report, non_pass)
    return {
        "skill": skill,
        "present": present.to_dict(),
        "absent": absent.to_dict(),
        "leaked_baseline_trials": leaked,
        "noise": None if band is None else band.to_dict(),
        **verdict,
    }


def _p(value: float | None) -> str:
    """'=0.031', or '<0.001' rather than a rounded '=0.000' for a tiny estimate."""
    if value is None:
        return "=n/a"
    return "<0.001" if value < 0.001 else f"={value:.3f}"


def noise_notes(cmp: dict[str, Any]) -> list[str]:
    """Plain-words advisories from the band. They change no verdict (see above)."""
    noise = cmp.get("noise") or {}
    notes = []
    if cmp.get("verdict") == VERDICT_LOAD_BEARING and not noise.get("lift_confirmed"):
        notes.append("the lift is not confirmed across prompts; repeated trials of one "
                     "prompt are not independent evidence")
    if noise.get("drifted"):
        notes.append("the two identical with-skill arms drifted apart; the runs "
                     "themselves moved, so read every number above with caution")
    return notes


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
    ]
    noise = cmp.get("noise")
    if noise:
        r = noise["replicate"]
        lines.append(
            f"  {'replicate':10}{r['graded_positive_trials']:>8}"
            f"{rate(r['outcome_pass_rate']):>9}{rate(r['trigger_rate']):>9}"
        )
    lines.append("-" * 68)
    if cmp.get("skill_lift") is None:
        lines.append(f"  skill lift   NOT MEASURED — {cmp['verdict']}")
    else:
        lo, hi = cmp["skill_lift_ci"]
        lines.append(f"  skill lift   {cmp['skill_lift']:+.2f}  95% CI [{lo:+.2f}, {hi:+.2f}]")
        if cmp.get("end_to_end_lift") is not None:
            lines.append(f"  end-to-end   {cmp['end_to_end_lift']:+.2f}  (trigger-inclusive)")
    if noise:
        if noise["lift_prompt_mean"] is not None:
            lines.append(
                f"  by prompt    lift {noise['lift_prompt_mean']:+.2f}  sign-flip "
                f"p{_p(noise['p_lift'])} over {noise['lift_prompts']} prompts")
        if noise["p_drift"] is not None:
            lines.append(
                f"  A/A drift    {noise['drift_prompt_mean']:+.2f}  sign-flip "
                f"p{_p(noise['p_drift'])} over {noise['drift_prompts']} prompts "
                "(two identical with-skill arms)")
        for note in noise_notes(cmp):
            lines.append(f"  NOTE         {note}")
        if noise["p_drift"] is None:
            lines.append("  A/A drift    NOT MEASURED (fewer than 2 prompts graded in both "
                         "with-skill arms)")
    else:
        lines.append("  A/A drift    NOT MEASURED (run with --noise-band)")
    lines.append(f"  VERDICT      {cmp['verdict']}")
    lines.append(f"               {cmp['why']}")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "ABLATION_MARGIN",
    "ABLATION_MIN_TRIALS",
    "ArmStats",
    "NoiseBand",
    "noise_notes",
    "arm_stats",
    "compare",
    "decide_verdict",
    "format_comparison",
    "newcombe_difference",
    "noise_band",
    "sign_flip_p",
    "outcome_passed",
    "wilson_interval",
]
