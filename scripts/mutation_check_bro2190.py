#!/usr/bin/env python3
"""Mutation proof for the BRO-2190 tier gate.

Guards, each closing a named prior failure:
  * clean-tree assert BEFORE the first mutation (a revert-to-HEAD run destroys
    uncommitted work, and every later mutation then patches a reverted file)
  * assert the anchor matches EXACTLY ONCE (a stale regex no-ops -> false SURVIVED)
  * record WHICH tests failed, so a mutant that merely CRASHES the suite is not
    scored as a behavioural kill (false KILLED)
"""
import subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "skills/tooling/skillify/scripts/skillify_check.py"
TESTS = REPO / "skills/tooling/skillify/tests"

def sh(*a, **kw):
    return subprocess.run(a, cwd=REPO, capture_output=True, text=True, **kw)

def clean_tree() -> bool:
    r = sh("git", "-c", "core.fsmonitor=false", "status", "--porcelain")
    return r.stdout.strip() == ""

MUTANTS = [
    ("M1 cross-model judge check inverted",
     'if jm.strip().lower() == under.strip().lower():',
     'if jm.strip().lower() != under.strip().lower():',
     "test_tier_j_self_judging_fails"),
    ("M2 agreement_measured requirement removed",
     'elif not isinstance(measured, dict) or not measured.get("value") or not measured.get("method"):',
     'elif False:',
     "test_tier_j_floor_without_measurement_fails"),
    ("M3 admission outcome polarity flipped",
     'if m.group(1).lower() == "rejected":',
     'if m.group(1).lower() == "admitted":',
     "test_tier_j_admission_rejected_fails"),
    ("M4 missing-outcome admission accepted",
     '        return ("evals/admission.md records no outcome — needs a line like "\n                "`Outcome: admitted` (or `rejected`)")',
     '        return None',
     "test_tier_j_admission_without_an_outcome_fails"),
    ("M5 judge execution reported as PASS (the anti-vacuity mutation)",
     'add("2j*", "Judge execution", SKIP,',
     'add("2j*", "Judge execution", PASS,',
     "test_judge_execution_is_never_reported_as_a_pass"),
    ("M6 tier L inferred from a trigger eval again",
     '    if code:\n        return TIER_D, False, "inferred: ships scripts/ code"\n    return None, False,',
     '    if code:\n        return TIER_D, False, "inferred: ships scripts/ code"\n    if any(_is_trigger_eval(skill_dir / f) for f in _eval_files(skill_dir)):\n        return TIER_L, False, "inferred: trigger eval"\n    return None, False,',
     "test_trigger_eval_alone_does_not_infer_a_lens"),
    ("M7 require_tests routed through latent_only again",
     '    require_tests = bool(code)',
     '    require_tests = bool(code) and not latent_only',
     "test_latent_only_plus_scripts_still_requires_tests"),
    ("M8 unclassified skill passes step 2",
     '    if tier is None:\n        add(2, "Tier + core", FAIL,',
     '    if tier is None:\n        add(2, "Tier + core", PASS,',
     "test_unclassifiable_skill_still_fails"),
]

def run_tests():
    r = subprocess.run([sys.executable, "-m", "pytest", str(TESTS), "-q", "--tb=no"],
                       cwd=REPO, capture_output=True, text=True)
    failed = [l.split("::")[-1].split()[0] for l in r.stdout.splitlines()
              if l.startswith("FAILED")]
    errored = any(l.startswith("ERROR") for l in r.stdout.splitlines())
    return r.returncode, failed, errored

if not clean_tree():
    sys.exit("ABORT: tree is dirty — a revert-to-HEAD run would destroy uncommitted work")

rc, failed, err = run_tests()
if rc != 0:
    sys.exit(f"ABORT: baseline suite is not green ({failed})")
print(f"baseline: green, clean tree\n")

killed = survived = 0
for name, old, new, expect in MUTANTS:
    src = GATE.read_text(encoding="utf-8")
    n = src.count(old)
    if n != 1:
        print(f"  !! {name}: anchor matched {n}x — STALE, not a result")
        continue
    GATE.write_text(src.replace(old, new), encoding="utf-8")
    rc, failed, err = run_tests()
    sh("git", "checkout", "--", str(GATE.relative_to(REPO)))
    assert clean_tree(), "revert failed"
    if rc == 0:
        print(f"  SURVIVED  {name}")
        survived += 1
    elif err:
        print(f"  !! CRASH   {name} — suite errored, not a behavioural kill")
        survived += 1
    else:
        hit = expect in failed
        print(f"  KILLED    {name}")
        print(f"            by {len(failed)} test(s); targeted test {'HIT' if hit else 'MISSED -> suspect'}: {expect}")
        if not hit:
            print(f"            actual: {failed[:4]}")
        killed += 1

print(f"\n{killed}/{killed+survived} mutants killed")
sys.exit(0 if survived == 0 else 1)
