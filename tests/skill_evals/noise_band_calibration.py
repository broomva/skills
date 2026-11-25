#!/usr/bin/env python3
"""Calibration of the --noise-band verdict under clustered trials (BRO-4110).

Regenerates the numbers quoted in ablation.py's docstring and the README:

    python3 tests/skill_evals/noise_band_calibration.py

Each simulated prompt has its own difficulty (uniform 0.2-0.8). With probability
`copy` a trial copies the prompt's shared outcome, otherwise it is an independent
coin: copy=1.0 is perfect clustering, copy=0.0 independent trials (copy=0.5 gives a
within-prompt trial correlation of about 0.25, not 0.5). The three arms are
independent draws; `effect` is added to the with-skill rate and clipped at 1.0, so
the realised mean lift is printed beside the nominal one.
The table prints the plain verdict shares, and how often the band's report note
flags a load-bearing verdict as not confirmed across prompts (the band changes no
verdict; see ablation.py).
Seeded, so the output is reproducible. Not a test: the assertion lives in
test_ablation.py::test_clustered_trials_do_not_manufacture_a_lift.
"""
from __future__ import annotations

import collections
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from skill_evals import ablation as A  # noqa: E402

NON_PASS = ["ERROR", "TIMEOUT", "LEAKED", "INVISIBLE", "NOT_COMPARABLE"]
SCENARIOS = [  # (prompts, trials per prompt, nominal effect, copy probability)
    (10, 12, 0.0, 1.0), (10, 12, 0.0, 0.5), (11, 3, 0.0, 0.5), (11, 3, 0.0, 0.0),
    (3, 12, 0.0, 1.0), (6, 12, 0.0, 1.0),
    (10, 12, 0.2, 1.0), (11, 3, 0.3, 0.5), (30, 3, 0.15, 0.5),
]


def report(rates, trials, rng, copy):
    cases = []
    for i, p in enumerate(rates):
        shared = rng.random() < p
        results = []
        for _ in range(trials):
            ok = shared if rng.random() < copy else rng.random() < p
            results.append({"outcome": "PASS" if ok else "FAIL", "triggered": True,
                            "checks": [{"check_id": "x", "passed": ok, "skipped": False}]})
        cases.append({"case_id": f"c{i}", "should_trigger": True, "results": results})
    return {"skill": "sim", "cases": cases}


def run(prompts, trials, effect, copy, sims=2000, seed=7):
    rng = random.Random(seed)
    without = collections.Counter()
    flagged = drift_notes = 0
    realised = 0.0
    for _ in range(sims):
        base = [rng.uniform(0.2, 0.8) for _ in range(prompts)]
        skill = [min(1.0, b + effect) for b in base]
        realised += sum(s - b for s, b in zip(skill, base)) / prompts
        P, B, R = (report(r, trials, rng, copy) for r in (skill, base, skill))
        cmp = A.compare(P, B, non_pass=NON_PASS, min_trials=10, replicate_report=R)
        without[cmp["verdict"]] += 1
        if cmp["verdict"] == A.VERDICT_LOAD_BEARING and not cmp["noise"]["lift_confirmed"]:
            flagged += 1
        drift_notes += bool(cmp["noise"]["drifted"])
    share = lambda c: {k: round(v / sims, 3) for k, v in sorted(c.items())}  # noqa: E731
    print(f"prompts={prompts} trials/prompt={trials} effect={effect:+.2f} "
          f"(realised {realised / sims:+.3f}) copy={copy}")
    lb = without.get(A.VERDICT_LOAD_BEARING, 0)
    print(f"   verdicts    : {share(without)}")
    print(f"   load-bearing flagged by the band: {flagged}/{lb}"
          f"   drift notes: {drift_notes / sims:.3f}")


if __name__ == "__main__":
    for scenario in SCENARIOS:
        run(*scenario)
