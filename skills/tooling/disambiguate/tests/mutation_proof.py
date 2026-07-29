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
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
WORK = Path("/tmp/mut_disamb")
SCRIPT = WORK / "scripts" / "disambiguate.py"
PRISTINE = (SRC / "scripts" / "disambiguate.py").read_text()

MUTATIONS = [
    ("fallback deleted",
     "test_structural_fallback_recognizes_verbs_outside_the_list",
     'if tokens[1].strip(".,:;").lower() in DETERMINERS:\n            return True',
     'if False:\n            return True'),
    ("preposition branch restored",
     "test_noun_plus_preposition_is_not_a_command",
     'if tokens[1].strip(".,:;").lower() in DETERMINERS:',
     'if tokens[1].strip(".,:;").lower() in DETERMINERS | {"to", "from", "into", "with", "for", "on", "at", "in"}:'),
    ("bare stems break stacks again",
     "test_noun_homograph_verbs_do_not_blind_the_stack_detector",
     "VERB_FORMS -= IMPERATIVE_HINT",
     "VERB_FORMS |= IMPERATIVE_HINT"),
    ("greedy fence pairing restored",
     "test_unbalanced_fence_strips_nothing_and_says_so",
     "    if open_at is not None:\n        # An opener with no closer. Strip nothing rather than guess.\n        return set(), False",
     "    if open_at is not None:\n        pass"),
    ("drift head-check removed",
     "test_drift_requires_the_shared_word_to_head_a_variant",
     "if len(variants) >= 3 and heads_one:",
     "if len(variants) >= 3:"),
    ("comparative guard removed",
     "test_comparative_guard_is_load_bearing",
     " and not COMPARATIVE_GUARD.search(low[: comp.start()])",
     ""),
    ("glossary hyphen fix reverted",
     "test_glossary_term_beside_a_hyphenated_compound",
     r'r"(?<![\w-])" + re.escape(term) + r"(?![\w-])"',
     r'r"(?<!\w)" + re.escape(term) + r"(?!\w)"'),
    ("E3 re-checks the closed list",
     "test_previously_blocklisted_verbs_work_as_commands",
     "    if commanding:\n        tail = re.search",
     "    if commanding and lwords and lwords[0] in IMPERATIVE_HINT:\n        tail = re.search"),
]


def run(test: str) -> bool:
    """True if the test PASSED."""
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", "-k", test],
                       cwd=WORK, capture_output=True, text=True)
    if "no tests ran" in r.stdout:
        print(f"      !! selector matched no test: {test}")
        return True
    return r.returncode == 0


def main() -> int:
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(SRC, WORK, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))

    base = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                          cwd=WORK, capture_output=True, text=True)
    print("baseline:", base.stdout.strip().splitlines()[-1])
    print()

    survivors = []
    for name, test, old, new in MUTATIONS:
        SCRIPT.write_text(PRISTINE)
        s = SCRIPT.read_text()
        if old not in s:
            print(f"  ANCHOR-MISS  {name}  (mutation could not be applied)")
            survivors.append(name)
            continue
        SCRIPT.write_text(s.replace(old, new, 1))
        passed = run(test)
        print(f"  {'SURVIVED (fake test)' if passed else 'killed':<20}  {name}")
        if passed:
            survivors.append(name)

    SCRIPT.write_text(PRISTINE)
    print()
    if survivors:
        print(f"FAIL — {len(survivors)} mutation(s) survived: {survivors}")
        return 1
    print(f"PASS — all {len(MUTATIONS)} mutations killed their test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
