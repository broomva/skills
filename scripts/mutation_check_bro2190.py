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
    # M3 (admission outcome polarity) was retired in round 3: the hits-based branch it
    # mutated no longer exists, and the property it covered — a rejection blocks — is
    # now carried by M32 against the raw-text scan that replaced it.
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
     "test_non_boolean_trigger_values_do_not_establish_polarity"),
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
     "test_non_case_files_with_content_are_not_held_out_cases"),
    ("M17 empty script accepted as a deterministic core",
     '    empty_code = [c for c in code if not _has_executable_content(skill_dir / c)]',
     '    empty_code = []',
     "test_empty_script_is_not_a_deterministic_core"),
    ("M18 unparseable eval artifacts become invisible instead of failing closed",
     '        if isinstance(data, _Unparseable):\n            bad.append(f)',
     '        if isinstance(data, _Unparseable):\n            pass',
     "test_unparseable_eval_artifact_fails_closed_for_tier_j"),

    # --- round 2: the second adversarial pass ------------------------------
    ("M19 comment-only script accepted as a deterministic core",
     '        if not t.startswith(_COMMENT_PREFIXES):\n            return True',
     '        return True',
     "test_comment_only_shell_script_is_not_a_deterministic_core"),
    ("M20 polarity read recursively from the whole document again",
     '    pos = neg = False\n    for k, v in data.items():',
     '    pos = neg = False\n    def _w(n):\n        nonlocal pos, neg\n        if isinstance(n, dict):\n            a, b = _case_polarity(n)\n            pos, neg = pos or a, neg or b\n            for vv in n.values(): _w(vv)\n        elif isinstance(n, list):\n            for vv in n: _w(vv)\n    _w(data)\n    for k, v in data.items():',
     "test_unrelated_nested_metadata_does_not_supply_polarity"),
    ("M21 malformed judge declarations dropped from the ambiguity count",
     '    if len(judges) > 1:',
     '    if len([j for j in judges if isinstance(j[1], dict)]) > 1:',
     "test_malformed_decoy_judge_still_counts_as_ambiguity"),
    ("M22 NaN accepted as an agreement floor",
     '            and math.isfinite(x))',
     '            and True)',
     "test_nan_agreement_floor_is_not_a_number"),
    ("M23 held-out marker object with no input accepted",
     '                     and any(_substantive(c.get(k)) for k in ("prompt", "input", "case", "text")))',
     '                     and True)',
     "test_held_out_marker_object_without_an_input_is_not_a_case"),
    ("M24 only ``` fences stripped from the admission record",
     '    md = re.sub(r"(?ms)^[ \\t]*(?:```|~~~).*\\Z", "", md)  # unterminated fence',
     '    pass  # unterminated fence',
     "test_tilde_and_unterminated_fences_hide_an_example_outcome"),
    ("M25 a bare verdict accepted as an admission record",
     '    if len("".join(prose).strip()) < 40:',
     '    if False:',
     "test_admission_verdict_without_a_record_is_not_enough"),
    ("M26 invalid UTF-8 crashes the gate again",
     '        text = md_path.read_text(encoding="utf-8", errors="replace")',
     '        text = md_path.read_text(encoding="utf-8")',
     "test_invalid_utf8_in_skill_md_fails_closed_without_a_traceback"),

    # --- round 3 -----------------------------------------------------------
    ("M27 tier L requires booleans again (rejects the real roles/*.eval.yaml shape)",
     '        if isinstance(v, list) and v:',
     '        if False:',
     "test_tier_l_accepts_the_real_roles_eval_shape"),
    ("M28 one self-contradictory case satisfies both polarities",
     '            if cp and cn:\n                continue  # one case cannot be both; it asserts nothing',
     '            pass',
     "test_one_self_contradictory_case_does_not_satisfy_both_polarities"),
    ("M29 held-out FILE path drops the placeholder guard again (the one-site fix)",
     '            txt = _read(f)\n            if _substantive(txt):',
     '            txt = _read(f)\n            if txt and txt.strip():',
     "test_placeholder_held_out_case_file_is_not_a_case"),
    ("M30 extensionless python script counted but not syntax-checked",
     '    if interp in _PY_INTERPRETERS:',
     '    if False:',
     "test_extensionless_python_script_is_syntax_checked"),
    ("M31 shebang interpreter matched by substring again (fish/zsh)",
     '    if interp in _SH_INTERPRETERS:',
     '    if "sh" in interp:',
     "test_fish_shebang_is_not_checked_with_bash"),
    # M32 (raw-substring rejection scan) retired in the verify round: the scan it
    # mutated was replaced by a labelled-verdict scan after it produced a false
    # FAIL on ordinary prose. M37 mutates the replacement.
    ("M33 top-level-list eval artifacts become invisible again",
     '        elif isinstance(data, list):',
     '        elif False:',
     "test_top_level_list_eval_is_visible_not_invisible"),

    # --- verify round -------------------------------------------------------
    ("M38 python AST emptiness check always reports content",
     '        return bool(body)',
     '        return True',
     "test_comment_only_script_is_not_a_deterministic_core"),
    ("M34 docstring-only script accepted as a deterministic core",
     '            body = body[1:]  # drop the module docstring',
     '            pass',
     "test_docstring_only_script_is_not_a_deterministic_core"),
    ("M35 placeholder matched only at position 0 again (.match vs .search)",
     '        return bool(t) and not _PLACEHOLDER_RE.search(t)',
     '        return bool(t) and not _PLACEHOLDER_RE.match(t)',
     "test_placeholder_anywhere_in_the_value_is_caught"),
    ("M36 unterminated HTML comment not stripped",
     '    md = re.sub(r"(?s)<!--.*\\Z", "", md)  # unterminated HTML comment',
     '    pass  # unterminated HTML comment',
     "test_unterminated_html_comment_hides_an_example_outcome"),
    ("M37 rejection scanned as a bare word again (the false-FAIL regression)",
     '    for m in _OUTCOME_LABEL_RE.finditer(raw):',
     '    for m in re.finditer(r"(rejected)", raw, re.IGNORECASE):',
     "test_ordinary_prose_mentioning_rejection_is_not_a_rejected_verdict"),
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

killed = survived = stale = missed = 0
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
    elif expect not in failed:
        # The mutant died, but NOT to the test that claims to cover it. That is
        # unproven coverage, not a kill: the named test passes for some other
        # reason and the predicate is guarded by something incidental.
        print(f"  MISSED    {name}")
        print(f"            died, but targeted test did NOT fail: {expect}")
        print(f"            actual: {failed[:4]}")
        missed += 1
    else:
        print(f"  KILLED    {name}  (by {len(failed)} test(s))")
        killed += 1

total = len(MUTANTS)
print(f"\n{killed}/{total} mutants killed"
      + (f"; {survived} SURVIVED" if survived else "")
      + (f"; {missed} MISSED (died to the wrong test — coverage unproven)" if missed else "")
      + (f"; {stale} STALE (anchor no longer matches — coverage unproven)" if stale else ""))
sys.exit(0 if killed == total else 1)
