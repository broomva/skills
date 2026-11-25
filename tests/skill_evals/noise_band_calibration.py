#!/usr/bin/env python3
"""Calibration of the --noise-band verdict under clustered trials (BRO-4110).

Regenerates the numbers quoted in ablation.py's docstring and the README:

    python3 tests/skill_evals/noise_band_calibration.py

Each simulated prompt has its own difficulty (uniform 0.2-0.8). With probability
`corr` a trial copies the prompt's shared outcome, otherwise it is an independent
coin, so corr=1.0 is perfect clustering and corr=0.0 is independent trials. The
three arms are independent draws; `effect` is added to the with-skill pass rate.
The table prints the share of each verdict without and with the noise band.
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
SCENARIOS = [  # (prompts, trials per prompt, true effect, within-prompt correlation)
    (10, 12, 0.0, 1.0), (10, 12, 0.0, 0.5), (11, 3, 0.0, 0.5), (11, 3, 0.0, 0.0),
    (10, 12, 0.2, 1.0), (11, 3, 0.3, 0.5), (30, 3, 0.15, 0.5),
]


def report(rates, trials, rng, corr):
    cases = []
    for i, p in enumerate(rates):
        shared = rng.random() < p
        results = []
        for _ in range(trials):
            ok = shared if rng.random() < corr else rng.random() < p
            results.append({"outcome": "PASS" if ok else "FAIL", "triggered": True,
                            "checks": [{"check_id": "x", "passed": ok, "skipped": False}]})
        cases.append({"case_id": f"c{i}", "should_trigger": True, "results": results})
    return {"skill": "sim", "cases": cases}


def run(prompts, trials, effect, corr, sims=2000, seed=7):
    rng = random.Random(seed)
    without, with_band = collections.Counter(), collections.Counter()
    for _ in range(sims):
        base = [rng.uniform(0.2, 0.8) for _ in range(prompts)]
        skill = [min(1.0, b + effect) for b in base]
        P, B, R = (report(r, trials, rng, corr) for r in (skill, base, skill))
        without[A.compare(P, B, non_pass=NON_PASS, min_trials=10)["verdict"]] += 1
        with_band[A.compare(P, B, non_pass=NON_PASS, min_trials=10,
                            replicate_report=R)["verdict"]] += 1
    share = lambda c: {k: round(v / sims, 3) for k, v in sorted(c.items())}  # noqa: E731
    print(f"prompts={prompts} trials/prompt={trials} effect={effect:+.2f} corr={corr}")
    print(f"   without band: {share(without)}")
    print(f"   with band   : {share(with_band)}")


if __name__ == "__main__":
    for scenario in SCENARIOS:
        run(*scenario)
