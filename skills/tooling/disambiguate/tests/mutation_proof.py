"""Mutation proof: revert each fix, assert its test fails.

Run with `python3 tests/mutation_proof.py`. Exits non-zero if any mutation
survives.

A green suite says the assertions ran, not that they discriminate. An
adversarial review found two regression tests here that passed with the
mechanism they claimed to cover deleted — one because the verbs it named had
been added to the very list it was proving unnecessary, the other because its
fixtures never reached the branch under test. Both looked correct on the page.

So each entry below reverts one fix on a COPY of the source and asserts the
corresponding test fails. A survivor is a test that cannot tell the fix from
its absence.

Round 2's sharpest finding was that two regression tests passed with the
mechanism they claimed to cover deleted. This harness reverts each fix on a
COPY and asserts the corresponding test fails. A survivor is a fake test.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
WORK = Path(tempfile.mkdtemp(prefix=f"mut_disamb_{os.getpid()}_"))
SCRIPT = WORK / "scripts" / "disambiguate.py"
PRISTINE = (SRC / "scripts" / "disambiguate.py").read_text()

MUTATIONS = [
    # --- round 1 ---
    ("comparative guard removed",
     "test_comparative_guard_is_load_bearing",
     " and not COMPARATIVE_GUARD.search(low[: comp.start()])",
     ""),
    ("glossary boundary fix reverted",
     "test_glossary_term_beside_a_hyphenated_compound",
     r'r"(?<![\w-])(?<!\d )(?<!\d)" + re.escape(term) + r"(?![\w-])"',
     r'r"(?<!\w)" + re.escape(term) + r"(?!\w)"'),
    # --- round 2 ---
    ("unbalanced fence strips anyway",
     "test_unbalanced_fence_strips_nothing_and_says_so",
     "        return set(), False",
     "        pass"),
    ("preposition branch restored",
     "test_noun_plus_preposition_is_not_a_command",
     'if tokens[1].strip(".,:;").lower() in DETERMINERS:',
     'if tokens[1].strip(".,:;").lower() in DETERMINERS | {"to", "from", "into", "with", "for", "on", "at", "in"}:'),
    ("structural fallback deleted",
     "test_structural_fallback_recognizes_verbs_outside_the_list",
     '    if len(tokens) >= 2 and w not in FUNCTION_WORDS and re.fullmatch(r"[a-z][a-z-]*", w):',
     "    if False:"),
    ("drift bare-form check removed",
     "test_drift_requires_the_bare_head_to_appear_alone",
     "if len(variants) >= 3 and bare_form:",
     "if len(variants) >= 3:"),
    # --- round 3 ---
    ("descriptive stack terminators widened to bare stems",
     "test_descriptive_stack_survives_a_homograph_modifier",
     "        stack_terminators = VERB_FORMS\n\n    stack_tokens",
     "        stack_terminators = VERB_FORMS | IMPERATIVE_HINT\n\n    stack_tokens"),
    ("bare stems terminate behind a command",
     "test_plural_noun_inside_a_commanded_stack",
     "        stack_terminators = {v for v in VERB_FORMS\n                             if v.endswith((\"ed\", \"ing\", \"ies\", \"ied\"))}",
     "        stack_terminators = VERB_FORMS | IMPERATIVE_HINT"),
    ("declarative -s terminator removed",
     "test_declarative_finite_verb_ends_a_noun_run",
     '        finite_s = (not commanding and lw.endswith("s") and not lw.endswith("ss")\n                    and len(lw) > 3)',
     "        finite_s = False"),
    ("plural-subject gate removed",
     "test_reduced_relative_clause_is_not_a_command",
     '            if w.endswith("s") and not w.endswith("ss") and w not in IMPERATIVE_HINT:\n                return False',
     "            if False:\n                return False"),
    ("hyphenated verbs blocked again",
     "test_hyphenated_verb_is_a_command",
     'and re.fullmatch(r"[a-z][a-z-]*", w):',
     "and w.isalpha():"),
    ("E3 word gate back to three",
     "test_e3_fires_on_a_one_word_object",
     "        if tail and before >= 2:",
     "        if tail and before >= 3:"),
    ("E3 takes the first marker regardless",
     "test_e3_skips_a_marker_that_is_too_early",
     "            if len(re.findall(r\"[A-Za-z][A-Za-z'-]*\", body_nostep[: m.start()])) >= 2:\n                tail = m\n                break",
     "            tail = m\n            break"),
]


def run(test: str) -> str:
    """PASS, FAIL, or ERROR for one selector.

    A round-3 review found the earlier version treated any non-zero exit as a
    kill, so a mutation that made the module unimportable (pytest exit 2,
    "1 error") was scored a successful kill. Collection failure proves nothing
    about the test's discrimination, so it is now its own outcome.
    """
    # A mutation that does not change the file's SIZE (">= 2" -> ">= 3") can
    # land in the same mtime second, leaving a .pyc that Python still considers
    # valid — so neither the mutation nor the restore takes effect and the
    # result is attributed to the wrong source.
    for cache in WORK.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider", "-k", test],
                       cwd=WORK, capture_output=True, text=True, env=env)
    if "no tests ran" in r.stdout or "no tests ran" in r.stderr:
        return "ERROR"
    if r.returncode >= 2:
        return "ERROR"
    return "PASS" if r.returncode == 0 else "FAIL"


def main() -> int:
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(SRC, WORK, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))

    base = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider"],
                          cwd=WORK, capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    print("baseline:", base.stdout.strip().splitlines()[-1])
    print()

    problems = []
    for name, test, old, new in MUTATIONS:
        SCRIPT.write_text(PRISTINE)

        # The target test must PASS on pristine source. Without this a
        # permanently-broken test is indistinguishable from a working one, and
        # every mutation against it reports a kill it never earned.
        baseline_outcome = run(test)
        if baseline_outcome != "PASS":
            print(f"  BASELINE-{baseline_outcome:<11}  {name}  "
                  f"(target test does not pass on unmutated source)")
            problems.append(name)
            continue

        body = SCRIPT.read_text()
        occurrences = body.count(old)
        if occurrences == 0:
            print(f"  ANCHOR-MISSING       {name}  (mutation could not be applied)")
            problems.append(name)
            continue
        if occurrences > 1:
            print(f"  ANCHOR-AMBIGUOUS     {name}  ({occurrences} matches; "
                  f"the mutation would be positional)")
            problems.append(name)
            continue

        SCRIPT.write_text(body.replace(old, new, 1))
        outcome = run(test)
        label = {"FAIL": "killed", "PASS": "SURVIVED (fake test)",
                 "ERROR": "ERROR (not a kill)"}[outcome]
        print(f"  {label:<20}  {name}")
        if outcome != "FAIL":
            problems.append(name)

    SCRIPT.write_text(PRISTINE)
    shutil.rmtree(WORK, ignore_errors=True)
    print()
    if problems:
        print(f"FAIL — {len(problems)} mutation(s) did not cleanly kill: {problems}")
        return 1
    print(f"PASS — all {len(MUTATIONS)} mutations killed their test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
