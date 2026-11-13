#!/usr/bin/env python3
"""Mutation-test sim_audit.py against its own test suite.

The skill asks every simulation for one-line changes that must turn a test
red. This applies the same standard to the audit: each entry below breaks one
documented behaviour of sim_audit.py, and tests/test_sim_audit.py must fail.

    python3 tests/run_mutants.py            # all mutants, four at a time
    python3 tests/run_mutants.py strict     # only mutants whose name contains "strict"

Exit 0 when every mutant is killed, 1 when one survives or no longer applies.
Each mutant runs in its own temporary copy of the skill.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SOURCE = SKILL / "scripts" / "sim_audit.py"

# (name, find, replace). `find` must occur exactly once in sim_audit.py.
MUTANTS: list[tuple[str, str, str]] = [
    # The command line
    ("strict flag ignored", "failed = audit.failed(args.strict)", "failed = audit.failed(False)"),
    ("json ok always true", '{"ok": not failed, "results"', '{"ok": True, "results"'),
    ("a failing audit exits 0", "return 1 if failed else 0", "return 0"),
    (
        "timeout flag ignored",
        "args.package, args.run_tests, args.run_report, args.run_mutations, args.timeout",
        "args.package, args.run_tests, args.run_report, args.run_mutations, DEFAULT_TIMEOUT",
    ),
    (
        "strict lets a skip through",
        "bad = {FAIL, WARN, SKIP} if strict else {FAIL}",
        "bad = {FAIL, WARN} if strict else {FAIL}",
    ),
    (
        "strict lets a warning through",
        "bad = {FAIL, WARN, SKIP} if strict else {FAIL}",
        "bad = {FAIL, SKIP} if strict else {FAIL}",
    ),
    (
        "package path not resolved",
        "    package = package.resolve()\n    ledger = load_ledger(package)",
        "    ledger = load_ledger(package)",
    ),
    (
        "a ledger error exits 1",
        "        return 2\n\n    if not args.package.is_dir():",
        "        return 1\n\n    if not args.package.is_dir():",
    ),
    (
        "json silent on a ledger error",
        '        if args.json:\n            print(json.dumps({"ok": False, "error"',
        '        if False:\n            print(json.dumps({"ok": False, "error"',
    ),
    # Running commands
    (
        "commands run in the package itself",
        "            copy_package(package, copy, ledger.links)",
        "            copy = package",
    ),
    (
        "mutated file not restored",
        '        finally:\n            target.write_text(original, encoding="utf-8")',
        "        finally:\n            pass",
    ),
    (
        "paths may leave the package",
        "    if target != package and package not in target.parents:\n        return None",
        "    if False:\n        return None",
    ),
    (
        "a mutation's own command ignored",
        'command = mutation.get("command", ledger.commands.get("test"))',
        'command = ledger.commands.get("test")',
    ),
    ("ledger link list ignored", "links=tuple(links),", "links=DEFAULT_LINKS,"),
    (".git copied", 'skipped = [n for n in names if n == ".git"]', "skipped = []"),
    (
        "linked directories copied instead",
        "        if source.is_dir():\n            os.symlink",
        "        if False:\n            os.symlink",
    ),
    (
        "timeout leaves children running",
        "os.killpg(process.pid, signal.SIGKILL)",
        "process.kill()",
    ),
    # Not listed: turning bytecode caching back on. Its effect depends on two
    # same-length writes landing within one second, so a mutant would be killed
    # only some of the time.
    ("standard error searched", "stderr=subprocess.DEVNULL,", "stderr=subprocess.STDOUT,"),
    (
        "run-mutations does not run the suite",
        "run_tests = run_tests or run_mutations",
        "run_tests = bool(run_tests)",
    ),
    # suite
    ("a red suite passes", '    if code == 0:\n        audit.add("suite", PASS', '    if True:\n        audit.add("suite", PASS'),
    ("an unrun suite passes", 'audit.add("suite", SKIP,', 'audit.add("suite", PASS,'),
    (
        "suite without a command is a warning",
        'audit.add("suite", FAIL, "--run-tests given but',
        'audit.add("suite", WARN, "--run-tests given but',
    ),
    # mutations
    ("duplicate mutation ids allowed", "if mid in seen_mutations:", "if False:"),
    (
        "mutation with no command is a warning",
        'audit.add("mutations", FAIL, "no `command` and no `commands.test`", mid)',
        'audit.add("mutations", WARN, "no `command` and no `commands.test`", mid)',
    ),
    (
        "missing mutation file is a warning",
        """audit.add("mutations", FAIL, f"{mutation['file']} does not exist in the package", mid)""",
        """audit.add("mutations", WARN, f"{mutation['file']} does not exist in the package", mid)""",
    ),
    (
        "a mutation may change a test",
        '        if path in checks:\n            audit.add(\n                "mutations",',
        '        if False:\n            audit.add(\n                "mutations",',
    ),
    (
        "a mutation may change a linked directory",
        "if relative.parts[0] in ledger.links:",
        "if False:",
    ),
    ("an ambiguous find allowed", "if count != 1:", "if count < 1:"),
    (
        "a survivor passes",
        '        if code == 0:\n            audit.add(\n                "mutations",\n                FAIL,',
        '        if code == 0:\n            audit.add(\n                "mutations",\n                PASS,',
    ),
    (
        "a timeout counts as killed",
        '        elif code == 124:\n            audit.add("mutations", FAIL,',
        '        elif code == 124:\n            audit.add("mutations", PASS,',
    ),
    ("a red baseline ignored", "if baselines[command] != 0:", "if False:"),
    (
        "no mutations is a warning",
        '            FAIL,\n            "no mutations:',
        '            WARN,\n            "no mutations:',
    ),
    (
        "unrun mutations pass",
        '                SKIP,\n                f"{len(applicable)} mutations apply',
        '                PASS,\n                f"{len(applicable)} mutations apply',
    ),
    ("mutation of an unknown claim allowed", 'if entry["claim"] not in valid_claims:', "if False:"),
    # references
    ("header may be anywhere", "HEADER_LINES = 40", "HEADER_LINES = 100000"),
    (
        "data files count as readers",
        "if p.is_file() and p.suffix.lower() not in DATA_SUFFIXES",
        "if p.is_file()",
    ),
    (
        "a comment counts as reading",
        'code = "\\n".join(code_text(p) for p in sorted(readers))',
        'code = "\\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(readers))',
    ),
    ("no URL needed", "if not URL.search(head):", "if False:"),
    ("no date needed", "if not DATE.search(head):", "if False:"),
    ("an unread table passes", "if path.name not in code:", "if False:"),
    ("an unused table passes", "if rid not in used:", "if False:"),
    (
        "a citation is not needed",
        "if not isinstance(source, str) or not source.strip():",
        "if False:",
    ),
    (
        "an unknown reference id passes",
        "if not isinstance(rid, str) or rid not in references:",
        "if False:",
    ),
    # quoted
    (
        "a missing doc is a warning",
        'audit.add("quoted", FAIL, f"doc {name} does not exist in the package")',
        'audit.add("quoted", WARN, f"doc {name} does not exist in the package")',
    ),
    (
        "run-report without a command is a warning",
        'audit.add("quoted", FAIL, "--run-report given but',
        'audit.add("quoted", WARN, "--run-report given but',
    ),
    (
        "a failing report ignored",
        '    if code != 0:\n        audit.add("quoted", FAIL, f"report command exited',
        '    if False:\n        audit.add("quoted", FAIL, f"report command exited',
    ),
    (
        "an unprinted number is a warning",
        """audit.add("quoted", FAIL, f"{quote!r} is not in the report output", cid)""",
        """audit.add("quoted", WARN, f"{quote!r} is not in the report output", cid)""",
    ),
    (
        "an undocumented number is a warning",
        """audit.add("quoted", FAIL, f"{quote!r} is in the ledger but not in the docs", cid)""",
        """audit.add("quoted", WARN, f"{quote!r} is in the ledger but not in the docs", cid)""",
    ),
    (
        "quoted values of any type accepted",
        "if not isinstance(quoted, list) or not all(isinstance(q, str) and q.strip() for q in quoted):",
        "if False:",
    ),
    ("an unrun report passes", 'audit.add("quoted", SKIP,', 'audit.add("quoted", PASS,'),
    # The assertion detector
    (
        "a claim's test need not assert",
        '        if not has_assertion(path, ledger.assertion):\n            audit.add("claims", FAIL',
        '        if False:\n            audit.add("claims", FAIL',
    ),
    (
        "a claim's test may be any file",
        '        if path not in checks:\n            audit.add(\n                "claims",',
        '        if False:\n            audit.add(\n                "claims",',
    ),
    ("gates ignored", "checks = tests + gate_files(package, ledger, audit)", "checks = list(tests)"),
    (
        "silent test files pass",
        "silent = [f for f in tests if not has_assertion(f, ledger.assertion)]",
        "silent = []",
    ),
    (
        "no test files is a warning",
        'audit.add("asserting", FAIL, "no test files found',
        'audit.add("asserting", WARN, "no test files found',
    ),
    (".should not recognised", '    r"|\\.should\\b"\n', ""),
    ("ASSERT_ not recognised", "(EXPECT|ASSERT|REQUIRE|CHECK)", "(EXPECT|REQUIRE|CHECK)"),
    ("REQUIRE not recognised", "(EXPECT|ASSERT|REQUIRE|CHECK)", "(EXPECT|ASSERT|CHECK)"),
    ("@test not recognised", '    r"|@test\\b"\n', ""),
    ("Assert. not recognised", '    r"|\\bAssert\\.\\w+\\s*\\("\n', ""),
    ("exitCode not recognised", '    r"|\\bprocess\\.exitCode\\s*=\\s*[1-9]"\n', ""),
    ("strictEqual not recognised", "(strictEqual|deepStrictEqual|", "(deepStrictEqual|"),
    ("console.assert counts", "(?<!console\\.)\\bassert", "\\bassert"),
    ("@testset counts", '    r"|@test\\b"\n', '    r"|@test"\n'),
    ("exit(0) counts", "exit)\\s*\\(\\s*[1-9]", "exit)\\s*\\(\\s*[0-9]"),
    ("URLs stripped as comments", 're.sub(r"(?<!:)//.*$", "", line)', 're.sub(r"//.*$", "", line)'),
    (
        "trailing // comment kept",
        '            line = re.sub(r"(?<!:)//.*$", "", line)',
        "            pass",
    ),
    ("trailing # comment kept", '            line = re.sub(r"\\s#.*$", "", line)', "            pass"),
    ("# lines kept", 'if hashes and stripped.startswith("#"):', "if False:"),
    (
        "// lines kept",
        'if slashes and stripped.startswith(("//", "/*", "*")):',
        "if False:",
    ),
    (
        "custom assertion ignored",
        'assertion = re.compile(tests["assertion"])',
        'assertion = re.compile(tests["assertion"]) and ASSERTION',
    ),
    (
        "unmutated claim passes",
        '                WARN,\n                f"{kind}: {test} asserts, but',
        '                PASS,\n                f"{kind}: {test} asserts, but',
    ),
    # coverage
    (
        "conservation counts as an anchor",
        '{"reference", "independent"},',
        '{"reference", "independent", "conservation"},',
    ),
    ("a control is not needed", '{"control"},', '{"control", "reference"},'),
    ("a limit is not needed", '{"convention", "omitted"},', '{"convention", "omitted", "prediction"},'),
    # the ledger
    (
        "an empty ledger is a warning",
        'audit.add("ledger", FAIL, "the ledger has no valid claims")',
        'audit.add("ledger", WARN, "the ledger has no valid claims")',
    ),
    ("two ledgers accepted", "if len(found) > 1:", "if False:"),
    (
        "link paths accepted",
        'if name in {".", ".."} or "/" in name or "\\\\" in name:',
        "if False:",
    ),
    (
        "commands of any type accepted",
        'raise LedgerError("`commands` must map names to command strings")',
        "pass",
    ),
    ("tests of any type accepted", 'raise LedgerError("`tests` must be a mapping")', "tests = {}"),
    ("unknown kinds accepted", 'if entry.get("kind") not in KINDS:', "if False:"),
    ("duplicate claim ids accepted", "        if cid in seen:", "        if False:"),
    (
        "duplicate reference ids accepted",
        '        if entry["id"] in references:',
        "        if False:",
    ),
    (
        "identical find and replace accepted",
        'if entry["find"] == entry["replace"]:',
        "if False:",
    ),
    (
        "a missing gate is ignored",
        'audit.add("ledger", FAIL, "gate file does not exist inside the package", name)',
        "pass",
    ),
]


def run_mutant(mutant: tuple[str, str, str]) -> tuple[str, str]:
    name, find, replace = mutant
    source = SOURCE.read_text(encoding="utf-8")
    count = source.count(find)
    if count != 1:
        return name, f"STALE: `find` occurs {count} times"
    with tempfile.TemporaryDirectory(prefix="sim-audit-mutant-") as scratch:
        copy = Path(scratch) / "skill"
        shutil.copytree(
            SKILL, copy, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache")
        )
        (copy / "scripts" / "sim_audit.py").write_text(
            source.replace(find, replace), encoding="utf-8"
        )
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_sim_audit.py", "-x", "-q",
             "-p", "no:cacheprovider"],
            cwd=copy,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )  # fmt: skip
    if done.returncode == 0:
        return name, "SURVIVED"
    if done.returncode == 1:
        return name, "killed"
    return name, f"ERROR: pytest exited {done.returncode}: {done.stdout[-300:]}"


def main(argv: list[str]) -> int:
    chosen = [m for m in MUTANTS if not argv or any(a in m[0] for a in argv)]
    if len({m[0] for m in MUTANTS}) != len(MUTANTS):
        print("duplicate mutant names")
        return 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(run_mutant, chosen))
    bad = [(name, outcome) for name, outcome in outcomes if outcome != "killed"]
    for name, outcome in bad:
        print(f"{outcome:<10} {name}")
    print(f"{len(outcomes) - len(bad)} of {len(outcomes)} mutants killed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
