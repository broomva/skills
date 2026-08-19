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
    # --- round 0: the original tier dispatch -------------------------------
    ("M1 cross-model judge check inverted",
     'same = [u for u in unders if u.lower() == jm.strip().lower()]',
     'same = [u for u in unders if u.lower() != jm.strip().lower()]',
     "test_tier_j_self_judging_fails"),
    ("M2 agreement_measured requirement removed",
     'elif not _substantive(measured.get("value")) or not _substantive(measured.get("method")):',
     'elif False:',
     "test_placeholder_measurement_is_not_a_measurement"),
    ("M3 admission outcome polarity flipped",
     'if any(h != "admitted" for h in hits):',
     'if any(h == "admitted" for h in hits):',
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
     '    if code:\n        return TIER_D, False, "inferred: ships scripts/ code"\n    if (skill_dir / "evals").is_dir():\n        return TIER_L, False, "inferred: has evals"\n    return None, False,',
     "test_trigger_eval_alone_does_not_infer_a_lens"),
    ("M7 require_tests routed through latent_only again",
     '    require_tests = bool(code)',
     '    require_tests = bool(code) and not latent_only',
     "test_latent_only_plus_scripts_still_requires_tests"),
    ("M8 unclassified skill passes step 2",
     '    if tier is None:\n        add(2, "Tier + core", FAIL,',
     '    if tier is None:\n        add(2, "Tier + core", PASS,',
     "test_unclassifiable_skill_still_fails"),

    # --- round 1: every fix made in response to the two adversarial strata ---
    ("M9 syntax check pushed back inside the tier-D branch (THE regression)",
     '    broken = [(c, e) for c in code if (e := _script_syntax_error(skill_dir / c))]',
     '    broken = [(c, e) for c in code if tier == TIER_D and (e := _script_syntax_error(skill_dir / c))]',
     "test_syntax_check_applies_to_every_tier_not_just_d"),
    ("M10 polarity satisfied by key presence rather than a real boolean",
     '            if ks in _POSITIVE_KEYS and isinstance(v, bool):',
     '            if ks in _POSITIVE_KEYS:',
     "test_null_valued_trigger_key_does_not_satisfy_tier_l"),
    ("M11 one polarity accepted for tier L",
     '    if pos and neg:\n        return None',
     '    if pos or neg:\n        return None',
     "test_positive_only_routing_eval_fails_tier_l"),
    ("M12 _dig_all reverted to first-match-wins",
     '    return [(f, data[key]) for f, data in blobs if key in data]',
     '    return [(f, data[key]) for f, data in blobs if key in data][:1]',
     "test_two_judge_configs_are_ambiguous_not_first_wins"),
    ("M13 missing execution_contract degrades to a warning again",
     '        fails.append("no execution_contract.model in evals/ — nothing to compare judge.model "\n                     "against, so cross-model distinctness cannot be established")',
     '        warns.append("no execution_contract.model")',
     "test_missing_execution_contract_fails_rather_than_warns"),
    ("M14 a measured value of 0 treated as no measurement (truthiness)",
     '    if _is_num(x):\n        return True',
     '    if _is_num(x):\n        return bool(x)',
     "test_a_measured_agreement_of_zero_is_a_real_measurement"),
    ("M15 empty rubric file accepted",
     '    if not body:\n        return "evals/rubric.md has no content below its heading — an empty rubric grades nothing"',
     '    if False:\n        return "evals/rubric.md has no content below its heading — an empty rubric grades nothing"',
     "test_heading_only_rubric_does_not_count"),
    ("M16 held-out counts every file again (.gitkeep, README)",
     '            if not f.is_file() or f.name.startswith(".") or f.suffix not in _CASE_EXTS:',
     '            if not f.is_file():',
     "test_gitkeep_and_readme_are_not_held_out_cases"),
    ("M17 empty script accepted as a deterministic core",
     '    empty_code = [c for c in code if not (_read(skill_dir / c) or "").strip()]',
     '    empty_code = []',
     "test_empty_script_is_not_a_deterministic_core"),
    ("M18 unparseable eval artifacts become invisible instead of failing closed",
     '        if isinstance(data, _Unparseable):\n            bad.append(f)',
     '        if isinstance(data, _Unparseable):\n            pass',
     "test_unparseable_eval_artifact_fails_closed_for_tier_j"),
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

killed = survived = stale = 0
for name, old, new, expect in MUTANTS:
    src = GATE.read_text(encoding="utf-8")
    n = src.count(old)
    if n != 1:
        # NOT a `continue`. Dropping a stale mutant from both numerator and
        # denominator lets the script report "7/7 killed" while one mutant never
        # ran — a proof that quietly shrinks its own denominator.
        print(f"  !! {name}: anchor matched {n}x — STALE, coverage NOT demonstrated")
        stale += 1
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

total = len(MUTANTS)
print(f"\n{killed}/{total} mutants killed"
      + (f"; {survived} SURVIVED" if survived else "")
      + (f"; {stale} STALE (anchor no longer matches — coverage unproven)" if stale else ""))
sys.exit(0 if (survived == 0 and stale == 0 and killed == total) else 1)
