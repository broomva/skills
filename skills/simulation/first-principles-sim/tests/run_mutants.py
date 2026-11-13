#!/usr/bin/env python3
"""Mutation-test sim_audit.py against its own test suite.

The skill asks every simulation for small changes that must turn a test red.
This applies the same standard to the audit, and more strictly: most mutants
are generated from the source, not chosen by hand.

Generated, one per source line that qualifies:

  cond      every single-line `if` / `elif` forced true, and forced false
  status    every FAIL, WARN or SKIP result reported as PASS
  pattern   every alternative of the assertion pattern removed
  element   every element of a one-line constant tuple or set removed

Listed by hand in CURATED: changes those four cannot express.

    python3 tests/run_mutants.py            # everything
    python3 tests/run_mutants.py --list     # print the mutants and stop
    python3 tests/run_mutants.py strict     # only names containing "strict"

Exit 0 when every mutant is killed or is listed in EQUIVALENT with a reason.
Exit 1 when one survives, when a curated mutant no longer applies, or when an
EQUIVALENT entry is killed or matches nothing (the list has gone stale).

A mutant counts as killed when pytest exits 1 (a test failed). Each mutated
file is compiled first, so a syntax error is reported as BROKEN, not as a
kill. A mutant can still die because the change raised an exception the tests
tripped over, not because a test checked the behaviour.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SOURCE = SKILL / "scripts" / "sim_audit.py"

# (name, find, replace). `find` must occur exactly once in sim_audit.py.
CURATED: list[tuple[str, str, str]] = [
    # The command line
    ("json ok always true", '"ok": not failed', '"ok": True'),
    ("a failing audit exits 0", "return 1 if failed else 0", "return 0"),
    ("strict flag ignored", "failed = audit.failed(args.strict)", "failed = audit.failed(False)"),
    ("timeout flag ignored", "timeout=args.timeout,", "timeout=DEFAULT_TIMEOUT,"),
    ("run-gates flag ignored", "run_gates=args.run_gates,", "run_gates=False,"),
    ("run-tests flag ignored", "run_tests=args.run_tests,", "run_tests=False,"),
    ("run-report flag ignored", "run_report=args.run_report,", "run_report=False,"),
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
    ("a ledger error exits 1", "        return 2\n\n    if not args.package.is_dir():", "        return 1\n\n    if not args.package.is_dir():"),
    ("json drops the subject", '"subject": self.subject,', '"subject": "",'),
    # Running commands
    (
        "commands run in the package itself",
        "            copy_package(package, copy, ledger.links)",
        "            copy = package",
    ),
    (
        "the report runs in the package itself",
        "code, report = run(command, copy, timeout)",
        "code, report = run(command, package, timeout)",
    ),
    (
        "the report ignores the timeout",
        "code, report = run(command, copy, timeout)",
        "code, report = run(command, copy, DEFAULT_TIMEOUT)",
    ),
    (
        "mutated file not restored",
        '            target.write_text(original, encoding="utf-8")\n        if code == 0:',
        "            pass\n        if code == 0:",
    ),
    (
        "a mutation's own command ignored",
        'command = mutation.get("command", ledger.commands.get("test"))',
        'command = ledger.commands.get("test")',
    ),
    ("ledger link list ignored", "links=tuple(links),", "links=DEFAULT_LINKS,"),
    ("default link list emptied", '_string_list(data, "link", list(DEFAULT_LINKS))', '_string_list(data, "link", [])'),
    ("caches and .git copied", "skipped = [n for n in names if n in STALE]", "skipped = []"),
    (
        "linked names skipped at every depth",
        "skipped += [n for n in names if n in links]",
        "pass\n        skipped += [n for n in names if n in links]",
    ),
    ("timeout leaves children running", "os.killpg(process.pid, signal.SIGKILL)", "process.kill()"),
    ("bytecode caching left on", '"PYTHONDONTWRITEBYTECODE": "1"', '"PYTHONDONTWRITEBYTECODE": ""'),
    ("standard error searched", "stderr=subprocess.DEVNULL,", "stderr=subprocess.STDOUT,"),
    ("undecodable output crashes", '        errors="replace",\n        env=', "        env="),
    (
        "run-mutations does not run the suite",
        "run_tests = run_tests or run_mutations",
        "run_tests = bool(run_tests)",
    ),
    (
        "gates alone make no copy",
        "if run_tests or run_report or run_gates:",
        "if run_tests or run_report:",
    ),
    (
        "paths may leave the package",
        "    if target != package and package not in target.parents:\n        return None",
        "    if False:\n        return None",
    ),
    # References and quoted values
    ("header one line longer", "HEADER_LINES = 40", "HEADER_LINES = 41"),
    ("header one line shorter", "HEADER_LINES = 40", "HEADER_LINES = 39"),
    ("plain http refused", 'URL = re.compile(r"https?://', 'URL = re.compile(r"https://'),
    ("any scheme accepted", 'URL = re.compile(r"https?://', 'URL = re.compile(r"\\w+://'),
    ("any month accepted", "-(0[1-9]|1[0-2])-", "-(\\d\\d)-"),
    ("any day accepted", "-(0[1-9]|[12]\\d|3[01])\\b", "-(\\d\\d)\\b"),
    ("date may sit inside a longer number", 'DATE = re.compile(r"\\b(19|20)', 'DATE = re.compile(r"(19|20)'),
    (
        "a comment counts as reading",
        'code = "\\n".join(code_text(p) for p in sorted(readers))',
        'code = "\\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(readers))',
    ),
    ("gates cannot read references", "readers = set(checks)", "readers = set()"),
    ("data files count as readers", "and p.suffix.lower() not in DATA_SUFFIXES", ""),
    ("only the last doc is searched", "docs += path.read_text", "docs = path.read_text"),
    (
        "report match ignores case",
        "if q not in report]",
        "if q.lower() not in report.lower()]",
    ),
    (
        "docs match ignores case",
        "if q not in docs]",
        "if q.lower() not in docs.lower()]",
    ),
    # The assertion detector
    ("gates are not checks", "checks = tests + gate_files(package, ledger, audit)", "checks = list(tests)"),
    ("silent test files pass", "silent = [f for f in tests if not has_assertion(f, ledger.assertion)]", "silent = []"),
    ("definitions count as assertions", "if not DEFINITION.match(line)]", "]"),
    ("console.assert counts", "(?<!console\\.)\\bassert", "\\bassert"),
    ("@testset counts", '    r"|@test\\b"\n', '    r"|@test"\n'),
    ("exit(0) counts", "(exit|Exit)\\s*\\(\\s*[1-9]", "(exit|Exit)\\s*\\(\\s*[0-9]"),
    ("exitCode = 0 counts", "exitCode\\s*=\\s*[1-9]", "exitCode\\s*=\\s*[0-9]"),
    ("expected( counts", "(_\\w+|[A-Z]\\w*)?\\s*\\(", "\\w*\\s*\\("),
    ("require.resolve counts", "|Len)\\w*\\s*\\(", "|Len|resolve)\\w*\\s*\\("),
    ("any use of should counts", "should\\s+(be|equal|eq)\\b", "should\\b"),
    ("URLs stripped as comments", 're.sub(r"(?<!:)//.*$", "", line)', 're.sub(r"//.*$", "", line)'),
    ("inline block comments kept", '            line = re.sub(r"/\\*.*?\\*/", "", line)', "            pass"),
    ("trailing // comment kept", '            line = re.sub(r"(?<!:)//.*$", "", line)', "            pass"),
    ("trailing # comment kept", '            line = re.sub(r"\\s#.*$", "", line)', "            pass"),
    ("trailing -- comment kept", '            line = re.sub(r"--.*$", "", line)', "            pass"),
    ("custom assertion ignored", 'assertion = re.compile(tests["assertion"])', 'assertion = re.compile(tests["assertion"]) and ASSERTION'),
    ("EXPECT_ not recognised", "(EXPECT|ASSERT|REQUIRE|CHECK)(_", "(ASSERT|REQUIRE|CHECK)(_"),
    ("ASSERT_ not recognised", "(EXPECT|ASSERT|REQUIRE|CHECK)(_", "(EXPECT|REQUIRE|CHECK)(_"),
    ("REQUIRE not recognised", "(EXPECT|ASSERT|REQUIRE|CHECK)(_", "(EXPECT|ASSERT|CHECK)(_"),
    ("CHECK not recognised", "(EXPECT|ASSERT|REQUIRE|CHECK)(_", "(EXPECT|ASSERT|REQUIRE)(_"),
    ("strictEqual not recognised", "(strictEqual|deepStrictEqual|", "(deepStrictEqual|"),
    ("deepStrictEqual not recognised", "|deepStrictEqual|", "|"),
    ("deepEqual not recognised", "|deepEqual|", "|"),
    ("notStrictEqual not recognised", "|notStrictEqual|", "|"),
    ("notEqual not recognised", "|notEqual)", ")"),
    ("pytest.fail not recognised", "pytest\\.(raises|fail)", "pytest\\.(raises)"),
    ("pytest.raises not recognised", "pytest\\.(raises|fail)", "pytest\\.(fail)"),
    ("exit( not recognised", "\\b(exit|Exit)\\s", "\\b(Exit)\\s"),
    ("Exit( not recognised", "\\b(exit|Exit)\\s", "\\b(exit)\\s"),
    ("panic without ! not recognised", "panic!?\\s*\\(", "panic!\\s*\\("),
    # coverage
    ("conservation counts as an anchor", '{"reference", "independent"},', '{"reference", "independent", "conservation"},'),
    ("independent is not an anchor", '{"reference", "independent"},', '{"reference"},'),
    ("reference is not an anchor", '{"reference", "independent"},', '{"independent"},'),
    ("a reference stands in for a control", '{"control"},', '{"control", "reference"},'),
    ("a prediction stands in for a limit", '{"convention", "omitted"},', '{"convention", "omitted", "prediction"},'),
    ("convention is not a limit", '{"convention", "omitted"},', '{"omitted"},'),
    ("omitted is not a limit", '{"convention", "omitted"},', '{"convention"},'),
    # the ledger
    ("default tests dir changed", 'tests.get("dir", "test")', 'tests.get("dir", "tests")'),
    ("default doc changed", '_string_list(data, "docs", ["README.md"])', '_string_list(data, "docs", ["DOCS.md"])'),
    ("default glob lost", '["*.test.*", "test_*.py", "*_test.*"]', '["test_*.py", "*_test.*"]'),
    ("a mutation needs no replace", '("claim", "file", "find", "replace")', '("claim", "file", "find")'),
    ("a mutation needs no find", '("claim", "file", "find", "replace")', '("claim", "file", "replace")'),
    ("a mutation needs no file", '("claim", "file", "find", "replace")', '("claim", "find", "replace")'),
    ("a mutation needs no claim", '("claim", "file", "find", "replace")', '("file", "find", "replace")'),
    ("mutations of rejected claims accepted", "valid_claims = {c[\"id\"] for c in claims}", "valid_claims = seen"),
]

# Mutants the tests cannot kill because the change does not alter behaviour.
# name -> why. An entry that is killed, or that matches no mutant, fails the run.
EQUIVALENT: dict[str, str] = {}

CONSTANT = re.compile(r"^([A-Z_]+) = ([({])(.*)([)}])$")
SKIP_CONSTANTS = {"KINDS"}


def generated(source: str) -> list[tuple[str, int, str | None]]:
    """(name, line index, replacement line or None to delete)."""
    lines = source.split("\n")
    seen: Counter[str] = Counter()
    out: list[tuple[str, int, str | None]] = []

    def add(kind: str, index: int, replacement: str | None, label: str = "") -> None:
        key = f"{kind}: {lines[index].strip()}{label}"
        seen[key] += 1
        name = key if seen[key] == 1 else f"{key} (occurrence {seen[key]})"
        out.append((name, index, replacement))

    in_assertion = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        indent = line[: len(line) - len(line.lstrip())]

        match = re.match(r"^(if|elif) .+:$", stripped)
        if match and not stripped.startswith("if __name__"):
            for value in ("True", "False"):
                add("cond", index, f"{indent}{match.group(1)} {value}:", f" -> {value}")

        if "audit.add(" in line or re.fullmatch(r"(FAIL|WARN|SKIP),", stripped):
            for status in ("FAIL", "WARN", "SKIP"):
                if re.search(rf"\b{status},", line):
                    add("status", index, re.sub(rf"\b{status},", "PASS,", line, count=1), f" {status}")

        if stripped.startswith("ASSERTION = re.compile("):
            in_assertion = True
        elif in_assertion and stripped == ")":
            in_assertion = False
        elif in_assertion and stripped.startswith('r"|'):
            add("pattern", index, None)

        constant = CONSTANT.match(line)
        if constant and constant.group(1) not in SKIP_CONSTANTS:
            elements = re.findall(r'"[^"]*"', constant.group(3))
            for element in elements:
                rest = [e for e in elements if e != element]
                body = ", ".join(rest) + ("," if len(rest) == 1 and constant.group(2) == "(" else "")
                add(
                    "element",
                    index,
                    f"{constant.group(1)} = {constant.group(2)}{body}{constant.group(4)}",
                    f" without {element}",
                )
    return out


def all_mutants() -> tuple[list[tuple[str, str]], list[str]]:
    """((name, mutated source) for every mutant, problems)."""
    source = SOURCE.read_text(encoding="utf-8")
    mutants: list[tuple[str, str]] = []
    problems: list[str] = []
    for name, find, replace in CURATED:
        count = source.count(find)
        if count != 1:
            problems.append(f"STALE      {name}: `find` occurs {count} times")
            continue
        mutants.append((name, source.replace(find, replace)))
    lines = source.split("\n")
    for name, index, replacement in generated(source):
        changed = lines[:index] + ([] if replacement is None else [replacement]) + lines[index + 1 :]
        mutants.append((name, "\n".join(changed)))
    names = Counter(name for name, _ in mutants)
    problems += [f"DUPLICATE  {name}" for name, count in names.items() if count > 1]
    return mutants, problems


def run_mutant(mutant: tuple[str, str]) -> tuple[str, str]:
    name, mutated = mutant
    try:
        compile(mutated, "sim_audit.py", "exec")
    except SyntaxError as exc:
        return name, f"BROKEN: {exc.msg}"
    with tempfile.TemporaryDirectory(prefix="sim-audit-mutant-") as scratch:
        copy = Path(scratch) / "skill"
        shutil.copytree(SKILL, copy, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        (copy / "scripts" / "sim_audit.py").write_text(mutated, encoding="utf-8")
        try:
            done = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/test_sim_audit.py", "-x", "-q",
                 "-p", "no:cacheprovider"],
                cwd=copy,
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            return name, "killed"
    if done.returncode == 0:
        return name, "SURVIVED"
    if done.returncode == 1:
        return name, "killed"
    return name, f"ERROR: pytest exited {done.returncode}: {done.stdout[-300:]}"


def main(argv: list[str]) -> int:
    mutants, problems = all_mutants()
    if "--list" in argv:
        for name, _ in mutants:
            print(name)
        print(f"{len(mutants)} mutants")
        return 0
    chosen = [m for m in mutants if not argv or any(a in m[0] for a in argv)]
    workers = int(os.environ.get("MUTANT_WORKERS", os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = dict(pool.map(run_mutant, chosen))

    names = {name for name, _ in mutants}
    for name in EQUIVALENT:
        if name not in names:
            problems.append(f"STALE      EQUIVALENT entry matches no mutant: {name}")
        elif outcomes.get(name) == "killed":
            problems.append(f"STALE      EQUIVALENT entry is killed: {name}")
    excused = 0
    for name, outcome in outcomes.items():
        if outcome == "killed":
            continue
        if outcome == "SURVIVED" and name in EQUIVALENT:
            excused += 1
            continue
        problems.append(f"{outcome:<10} {name}")

    for problem in problems:
        print(problem)
    killed = sum(outcome == "killed" for outcome in outcomes.values())
    print(f"{killed} of {len(outcomes)} mutants killed, {excused} excused as equivalent")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
