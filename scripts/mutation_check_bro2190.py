#!/usr/bin/env python3
"""Mutation proof for the BRO-2190 tier gate.

Guards, each closing a named prior failure:
  * clean-tree assert BEFORE the first mutation (a revert-to-HEAD run destroys
    uncommitted work, and every later mutation then patches a reverted file)
  * assert the anchor matches EXACTLY ONCE (a stale regex no-ops -> false SURVIVED)
  * record WHICH tests failed, so a mutant that merely CRASHES the suite is not
    scored as a behavioural kill (false KILLED)
  * audit that every mutant's named target test EXISTS, before running anything —
    a renamed target used to surface only afterwards as MISSED (M63), and a deleted
    one only as a mutant that died to something else
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
     "test_measurement_fields_are_checked_structurally_only"),
    # M3 (admission outcome polarity) was retired in round 3: the hits-based branch it
    # mutated no longer exists, and the property it covered — a rejection blocks — is
    # now carried by M32 against the raw-text scan that replaced it.
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
    ("M15 empty rubric file accepted",
     '    if not body:\n        return "evals/rubric.md has no content below its heading — an empty rubric grades nothing"',
     '    if False:\n        return "evals/rubric.md has no content below its heading — an empty rubric grades nothing"',
     "test_heading_only_rubric_does_not_count"),
    ("M16 held-out counts every file again (.gitkeep, README)",
     '            if not f.is_file() or f.name.startswith(".") or f.suffix not in _CASE_EXTS:',
     '            if not f.is_file():',
     "test_gitkeep_and_readme_are_not_held_out_cases"),
    ("M17 empty script accepted as a deterministic core",
     '    empty_code = [c for c in code if not _has_executable_content(skill_dir / c)]',
     '    empty_code = []',
     "test_empty_script_is_not_a_deterministic_core"),
    ("M18 unparseable eval artifacts become invisible instead of failing closed",
     '        if isinstance(data, _Unparseable):\n            bad.append(data)',
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
     '    md = re.sub(r"(?ms)^[ \\t]*(?:```|~~~).*\\Z", "", md)',
     '    pass',
     "test_unterminated_fence_still_hides_a_reference"),
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
    # M29 retired: it mutated `_substantive` to `txt.strip()` on the held-out FILE
    # path. Now that _substantive IS an emptiness check, the two are identical and
    # the mutant is a no-op. The property it guarded is covered by
    # test_an_empty_held_out_case_file_is_not_a_case via M16's sibling checks.
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
    # M35 (.match vs .search on _PLACEHOLDER_RE) retired in the final round: that
    # call site moved into _is_placeholder, whose two behaviours — requiring an
    # actual token, and the residue rule — are covered by M39 and M40.
    ("M36 unterminated HTML comment not stripped",
     '    md = re.sub(r"(?s)<!--.*\\Z", "", md)',
     '    pass',
     "test_unterminated_html_comment_reference_does_not_break_step_1c"),

    # --- final verify round --------------------------------------------------


    # --- the simplification: prose heuristics deleted ------------------------
    # Eleven mutants were retired with the code they targeted (M4, M14, M25, M37,
    # M39-M45). They mutated placeholder and admission-prose heuristics that produced
    # a new false-reject class every round; the properties that survive are below.
    ("M46 declared rejection stops blocking",
     '    if outcome == "rejected":',
     '    if False:',
     "test_declared_outcome_rejected_blocks"),
    ("M47 a missing outcome field is accepted",
     '    if not outcome:',
     '    if False:',
     "test_frontmatter_without_an_outcome_key_fails"),
    ("M48 any outcome value accepted",
     '    if outcome not in ("admitted", "rejected"):',
     '    if False:',
     "test_invalid_outcome_value_fails"),
    ("M49 an empty admission body accepted",
     '    if not body.strip():',
     '    if False:',
     "test_declared_outcome_with_an_empty_body_fails"),
    ("M50 _substantive accepts blank strings again",
     '    return isinstance(x, str) and bool(x.strip())',
     '    return isinstance(x, str)',
     "test_measurement_fields_are_checked_structurally_only"),

    # --- round 6: the substance floor, and the frontmatter contract ----------
    # M51 retired: unifying the frontmatter matcher made its target — the
    # `if m else raw` fallback — unreachable, so no input could kill it. The
    # branch was deleted and replaced by an explicit early return; a mutant that
    # can never die is dishonest bookkeeping, not coverage.
    ("M52 a UTF-8 BOM hides frontmatter again",
     '_FRONTMATTER_RE = re.compile(r"^\\ufeff?---[ \\t]*\\n(.*?)\\n---[ \\t]*(?:\\n|$)", re.DOTALL)',
     '_FRONTMATTER_RE = re.compile(r"^---[ \\t]*\\n(.*?)\\n---[ \\t]*(?:\\n|$)", re.DOTALL)',
     "test_bom_reaches_the_second_frontmatter_parser_too"),
    ("M53 the stdlib fallback stops stripping YAML comments",
     '                val = re.split(r"\\s+#", val, 1)[0].strip()',
     '                pass',
     "test_the_documented_template_parses_without_pyyaml"),
    ("M54 duplicate outcome declarations accepted",
     '    if declared is not None and declared > 1:',
     '    if False:',
     "test_duplicate_contradictory_outcome_declarations_fail"),
    ("M55 outcome key matched case-sensitively again",
     '    present = [v for k, v in fm.items() if str(k).strip().lower() == "outcome"]',
     '    present = [v for k, v in fm.items() if str(k) == "outcome"]',
     "test_outcome_key_is_matched_case_insensitively"),
    ("M56 step 1c fails OPEN on an unreadable templates artifact",
     '            if raw_y is None:\n                issues.append(f"{y.relative_to(skill_dir)} is unreadable — "\n                              "references cannot be verified")\n                raw_y = ""',
     '            raw_y = raw_y or ""',
     "test_unreadable_template_reference_fails_step_1c_closed"),
    ("M57 an unreadable eval artifact becomes invisible again",
     '    if txt is None:\n        return _Unparseable(path)  # unreadable is UNVERIFIED, not absent',
     '    if txt is None:\n        return None',
     "test_unreadable_eval_artifact_is_reported_as_unverifiable_not_absent"),

    # --- round 7: one matcher, and the sibling sites -------------------------
    ("M59 empty-outcome message unreachable — the author is told nothing was typed",
     '    if present and outcome in ("", "none", "null"):',
     '    if False:',
     "test_empty_outcome_value_reports_what_the_author_typed"),


    # M58/M60/M61/M62 retired with the line-based key walker they targeted; the
    # property they approximated is now answered by the YAML parser itself.
    ("M63 duplicate detection guesses instead of using the parser",
     'approximating it.\n    """\n    if yaml is None:\n        return None',
     'approximating it.\n    """\n    if yaml is None:\n        return 0',
     "test_duplicate_tier_check_degrades_without_pyyaml_rather_than_guessing"),
    ("M64 duplicate keys collapse (safe_load) instead of composing the node tree",
     '        node = yaml.compose(block)\n    except Exception:\n        return None',
     '        node = yaml.compose("a: 1")\n    except Exception:\n        return None',
     "test_duplicate_top_level_outcome_declarations_fail"),
    
    ("M66 tier J passes frontmatter it cannot parse (the final false accept)",
     '    if yaml is None:\n        return ("tier J\'s admission record is a YAML contract and this build has no "',
     '    if False:\n        return ("tier J\'s admission record is a YAML contract and this build has no "',
     "test_tier_j_refuses_to_pass_frontmatter_it_cannot_parse"),
    ("M67 structured values stop counting as values",
     '        return any(_substantive(v, _seen) for v in (x.values() if isinstance(x, dict) else x))',
     '        return False',
     "test_structured_values_are_substantive"),

    # --- round 11: the false ACCEPT that the round-10 fix created -------------
    # M69 is M67's INVERSE, and the reason both must exist. Round 10 fixed a false
    # REJECT by making containers truthy; that shipped a false ACCEPT nobody caught
    # because every mutant pointed the same way. Mutate a predicate in BOTH
    # directions or it only proves half of it.
    ("M69 hollow containers count as content again (the round-10 regression)",
     '        return any(_substantive(v, _seen) for v in (x.values() if isinstance(x, dict) else x))',
     '        return bool(x)',
     "test_a_hollow_tier_j_core_does_not_pass"),
    ("M70 fence padding admits control characters again",
     '_FRONTMATTER_RE = re.compile(r"^\\ufeff?---[ \\t]*\\n(.*?)\\n---[ \\t]*(?:\\n|$)", re.DOTALL)',
     '_FRONTMATTER_RE = re.compile(r"^\\ufeff?---[^\\S\\n]*\\n(.*?)\\n---[^\\S\\n]*(?:\\n|$)", re.DOTALL)',
     "test_fence_padding_accepts_typed_whitespace_and_rejects_control_characters"),
    ("M71 the cycle/depth guard reports present instead of absent",
     '            # an unverified artifact is reported, never thrown. Found in P20 round 13.\n            return False',
     '            # an unverified artifact is reported, never thrown. Found in P20 round 13.\n            return True',
     "test_substantive_terminates_on_a_cyclic_structure"),

    # --- round 12 -------------------------------------------------------------
    # M72 is the one round 11 MISSED. Round 11 tightened BOTH fences but tested only
    # the opening one, so a mutant loosening the CLOSING fence survived the whole
    # 175-test suite. A fix applied at two sites needs a proof at two sites.
    ("M72 the CLOSING fence re-admits control characters",
     '\\n---[ \\t]*(?:\\n|$)"',
     '\\n---[^\\S\\n]*(?:\\n|$)"',
     "test_fence_padding_accepts_typed_whitespace_and_rejects_control_characters"),
    ("M73 a duplicate declaration is accepted (last-wins)",
     '    dup = _duplicate_top_level_key_issue(skill_dir / "SKILL.md")\n    if dup:\n        return None, False, dup',
     '    dup = None',
     "test_a_duplicate_tier_declaration_is_ambiguous_not_last_wins"),
    ("M74 the duplicate-key check narrows back to `tier:` alone",
     '    status, dupes = _duplicate_top_level_keys(m.group(1))',
     '    status, dupes = _duplicate_top_level_keys(m.group(1))\n    dupes = [d for d in dupes if d[0] == "tier"]',
     "test_any_duplicated_top_level_key_is_ambiguous_not_just_tier"),
    ("M75 the duplicate scan guesses when it cannot parse",
     '    if yaml is None:\n        return "no-parser", []',
     '    if yaml is None:\n        return "ok", [("tier", 2)]',
     "test_duplicate_tier_check_degrades_without_pyyaml_rather_than_guessing"),
        # M77 retired in round 15 with the branch it named: the `status == "unparseable"`
    # arm was deleted once `_frontmatter_disagreement_issue` shadowed it.
    
    # --- round 13, Strata B ---------------------------------------------------
    ("M78 frontmatter keys are matched case-sensitively again",
     '    want = key.strip().lower()\n    for k, v in fm.items():\n        if str(k).strip().lower() == want:',
     '    want = key\n    for k, v in fm.items():\n        if str(k) == want:',
     "test_frontmatter_keys_are_matched_case_insensitively"),
    ("M79 the nesting cap is removed and deep values raise instead of failing closed",
     '        if id(x) in _seen or len(_seen) >= _MAX_NESTING:',
     '        if id(x) in _seen:',
     "test_absurdly_nested_values_fail_closed_instead_of_raising"),
    ("M80 the nesting cap is so low it rejects ordinary nesting",
     '_MAX_NESTING = 100',
     '_MAX_NESTING = 2',
     "test_absurdly_nested_values_fail_closed_instead_of_raising"),

    # M65/M76 retired in round 15. Both anchored on branches that
    # `_frontmatter_disagreement_issue` now shadows: `compose` is a strict prefix of
    # `safe_load`, so a block compose rejects is one safe_load rejects, which the
    # disagreement check refuses first. Both SURVIVED, and this file's standard is that
    # a mutant which cannot die is dishonest bookkeeping — so the branches were deleted
    # rather than the mutants kept.

    # --- round 14: the refusal keyed on the wrong parser ----------------------
    ("M81 the tier gate stops refusing when the two readers disagree",
     '    disagreement = _frontmatter_disagreement_issue(path, "SKILL.md frontmatter")\n    if disagreement:\n        return disagreement',
     '    disagreement = None',
     "test_a_yaml_tag_cannot_hide_a_tier_declaration"),
    ("M82 the admission gate stops refusing when the two readers disagree",
     '    disagreement = _frontmatter_disagreement_issue(f, "evals/admission.md frontmatter")\n    if disagreement:\n        return disagreement',
     '    disagreement = None',
     "test_a_yaml_tag_cannot_hide_a_rejected_admission"),
    ("M83 the fallback is keyed on compose again instead of safe_load",
     '    try:\n        data = yaml.safe_load(block)\n    except Exception:\n        return FM_FALLBACK, _scan_frontmatter(block)',
     '    try:\n        data = yaml.compose(block) and yaml.safe_load(block)\n    except Exception:\n        return FM_YAML, _scan_frontmatter(block)',
     "test_a_yaml_tag_cannot_hide_a_tier_declaration"),
    ("M84 a non-mapping frontmatter is treated as if YAML accepted it",
     '    return FM_FALLBACK, _scan_frontmatter(block)\n\n\ndef parse_frontmatter',
     '    return FM_YAML, _scan_frontmatter(block)\n\n\ndef parse_frontmatter',
     "test_parse_frontmatter_status_names_which_reader_answered"),
    ("M85 an empty block is misreported as a parse failure",
     '    if data is None and not block.strip():',
     '    if False:',
     "test_parse_frontmatter_status_names_which_reader_answered"),

    # --- round 15 -------------------------------------------------------------
    ("M86 duplicate keys in a YAML eval artifact are resolved last-wins again",
     '        dup = _duplicate_key_in_node(txt)\n        if dup:',
     '        dup = None\n        if dup:',
     "test_a_duplicate_key_in_an_eval_artifact_cannot_hide_a_self_judging_declaration"),
    ("M87 duplicate keys in a JSON eval artifact are resolved last-wins again",
     '            return json.loads(txt, object_pairs_hook=_no_duplicate_pairs)',
     '            return json.loads(txt)',
     "test_a_duplicate_key_in_an_eval_artifact_cannot_hide_a_self_judging_declaration"),
    ("M88 the duplicate-key refusal fires on artifacts with no duplicates",
     '        if k in seen:\n            raise _DuplicateKey(k)',
     '        if True:\n            raise _DuplicateKey(k)',
     "test_a_clean_eval_artifact_still_passes"),
    ("M89 the step-1 name report goes back to a case-sensitive read",
     "f\"name={_fm(fm, 'name')} (skills.sh-parseable)\"",
     "f\"name={fm['name']} (skills.sh-parseable)\"",
     "test_a_capitalised_name_key_reports_instead_of_raising"),
    ("M90 skill.json recursion is uncaught again",
     '        except (ValueError, OSError, RecursionError):',
     '        except (ValueError, OSError):',
     "test_deeply_nested_artifacts_report_rather_than_throw"),
    ("M91 the json eval arm stops catching recursion",
     '        except RecursionError:\n            # json.loads recurses',
     '        except UnicodeDecodeError:\n            # json.loads recurses',
     "test_deeply_nested_artifacts_report_rather_than_throw"),
    ("M93 the skill.json reference walk loses its depth cap",
     '            if depth > _MAX_NESTING:\n                return  # same cap, same reason: report, never throw',
     '            if False:\n                return  # same cap, same reason: report, never throw',
     "test_deeply_nested_artifacts_report_rather_than_throw"),
    ("M92 camelCase negative polarity is dropped again",
     '_NEGATIVE_KEYS = {"should_not_trigger", "shouldNotTrigger", "should_not_fire",',
     '_NEGATIVE_KEYS = {"should_not_trigger", "should_not_fire",',
     "test_camelcase_negative_polarity_is_recognised"),
    ("M68 opening fence stops tolerating trailing whitespace",
     '_FRONTMATTER_RE = re.compile(r"^\\ufeff?---[ \\t]*\\n(.*?)\\n---[ \\t]*(?:\\n|$)", re.DOTALL)',
     '_FRONTMATTER_RE = re.compile(r"^\\ufeff?---\\n(.*?)\\n---[ \\t]*(?:\\n|$)", re.DOTALL)',
     "test_trailing_whitespace_on_the_opening_fence_is_accepted"),
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
print(f"baseline: green, clean tree")

# Target-test-exists audit. The arc's write-ups have claimed this ran "before it" for
# several rounds; it did not. Only the anchor count was audited, so a target test that
# was RENAMED surfaced after the fact as MISSED (M63, round 12) and a target that was
# DELETED could only surface as a mutant that died to something else. Collect the real
# test-id set once and check every mutant names one.
_collected = subprocess.run([sys.executable, "-m", "pytest", str(TESTS), "-q", "--collect-only"],
                            cwd=REPO, capture_output=True, text=True)
_known = {line.split("::")[-1].split("[")[0].strip()
          for line in _collected.stdout.splitlines() if "::" in line}
_ghosts = sorted({expect for _, _, _, expect in MUTANTS if expect not in _known})
if _ghosts:
    print(f"  !! {len(_ghosts)} mutant(s) name a test that does not exist: {', '.join(_ghosts)}")
    sys.exit(1)
print(f"target-test audit: {len(MUTANTS)} mutants, every named test exists\n")

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
