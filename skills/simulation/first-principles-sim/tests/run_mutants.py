#!/usr/bin/env python3
"""Mutation-test sim_audit.py against its own test suite.

The skill asks every simulation for small changes that must turn a test red.
This applies the same standard to the audit, and more strictly: most mutants
are generated from the source, not chosen by hand.

Generated, one per source line that qualifies:

  cond      every single-line `if` / `elif` forced true, and forced false
  status    every FAIL, WARN or SKIP result reported as PASS
  pattern   every entry of the assertion pattern list removed
  alt       every alternative inside a group of an assertion pattern removed
  element   every element of a constant tuple or set removed
  entry     every claim kind removed

Listed by hand in CURATED: changes those four cannot express.

    python3 tests/run_mutants.py            # everything
    python3 tests/run_mutants.py --list     # print the mutants and stop
    python3 tests/run_mutants.py strict     # only names containing "strict"

The tests are run on the unchanged script first, and nothing else runs unless
they pass.

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
# Not listed: passing `ignore_dangling_symlinks=True` to copytree again. Whether
# that drops a relative link depends on the Python version (older ones judge the
# link from the working directory), so the mutant would be killed on some
# interpreters only. The behaviour has its own test.
#
# Also not listed: ignoring the text of an f-string. Before Python 3.12 an
# f-string is one STRING token, so the mutant would survive on 3.11 only.
CURATED: list[tuple[str, str, str]] = [
    ('json ok always true', '"ok": not failed', '"ok": True'),
    ('a failing audit exits 0', 'return 1 if failed else 0', 'return 0'),
    ('strict flag ignored', 'failed = audit.failed(args.strict)', 'failed = audit.failed(False)'),
    ('timeout flag ignored', 'timeout=args.timeout,', 'timeout=DEFAULT_TIMEOUT,'),
    ('run-gates flag ignored', 'run_gates=args.run_gates,', 'run_gates=False,'),
    ('run-tests flag ignored', 'run_tests=args.run_tests,', 'run_tests=False,'),
    ('run-report flag ignored', 'run_report=args.run_report,', 'run_report=False,'),
    ('strict lets a skip through', 'bad = {FAIL, WARN, SKIP} if strict else {FAIL}', 'bad = {FAIL, WARN} if strict else {FAIL}'),
    ('strict lets a warning through', 'bad = {FAIL, WARN, SKIP} if strict else {FAIL}', 'bad = {FAIL, SKIP} if strict else {FAIL}'),
    ('package path not resolved', '    package = package.resolve()\n    ledger = load_ledger(package)', '    ledger = load_ledger(package)'),
    ('a ledger error exits 1', '        return 2\n\n    if not args.package.is_dir():', '        return 1\n\n    if not args.package.is_dir():'),
    ('json drops the subject', '"subject": self.subject,', '"subject": "",'),
    ('commands run in the package itself', '            copy_package(package, copy, ledger.links)', '            copy = package'),
    ('the report runs in the package itself', 'code, report = run(command, copy, timeout)', 'code, report = run(command, package, timeout)'),
    ('the report ignores the timeout', 'code, report = run(command, copy, timeout)', 'code, report = run(command, copy, DEFAULT_TIMEOUT)'),
    ("a mutation's own command ignored", 'command = mutation.get("command", ledger.commands.get("test"))', 'command = ledger.commands.get("test")'),
    ('ledger link list ignored', 'links=tuple(links),', 'links=DEFAULT_LINKS,'),
    ('default link list emptied', '_string_list(data, "link", list(DEFAULT_LINKS))', '_string_list(data, "link", [])'),
    ('caches and .git copied', 'skipped = [n for n in names if n in STALE]', 'skipped = []'),
    ('timeout leaves children running', 'os.killpg(process.pid, signal.SIGKILL)', 'process.kill()'),
    ('bytecode caching left on', '"PYTHONDONTWRITEBYTECODE": "1"', '"PYTHONDONTWRITEBYTECODE": ""'),
    ('standard error searched', 'stderr=subprocess.DEVNULL,', 'stderr=subprocess.STDOUT,'),
    ('undecodable output crashes', '        errors="replace",\n        env=', '        env='),
    ('run-mutations does not run the suite', 'run_tests = run_tests or run_mutations', 'run_tests = bool(run_tests)'),
    ('gates alone make no copy', 'if run_tests or run_report or run_gates:', 'if run_tests or run_report:'),
    ('paths may leave the package', '    if target != package and package not in target.parents:\n        return None', '    if False:\n        return None'),
    ('header one line longer', 'HEADER_LINES = 40', 'HEADER_LINES = 41'),
    ('header one line shorter', 'HEADER_LINES = 40', 'HEADER_LINES = 39'),
    ('plain http refused', 'URL = re.compile(r"https?://', 'URL = re.compile(r"https://'),
    ('any scheme accepted', 'URL = re.compile(r"https?://', 'URL = re.compile(r"\\w+://'),
    ('a comment counts as reading', 'code = "\\n".join(code_text(p) for p in sorted(readers))', 'code = "\\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(readers))'),
    ('only the last doc is searched', 'docs += path.read_text', 'docs = path.read_text'),
    ('report match ignores case', 'if q not in report]', 'if q.lower() not in report.lower()]'),
    ('docs match ignores case', 'if q not in docs]', 'if q.lower() not in docs.lower()]'),
    ('gates are not checks', 'checks = tests + gate_files(package, ledger, audit)', 'checks = list(tests)'),
    ('silent test files pass', 'silent = [f for f in tests if not has_assertion(f, ledger.assertion)]', 'silent = []'),
    ('console.assert counts', '(?<!console\\.)\\bassert', '\\bassert'),
    ('exitCode = 0 counts', 'exitCode\\s*=\\s*[1-9]', 'exitCode\\s*=\\s*[0-9]'),
    ('expected( counts', '(_\\w+|[A-Z]\\w*)?\\s*\\(', '\\w*\\s*\\('),
    ('require.resolve counts', '|Len)\\w*\\s*\\(', '|Len|resolve)\\w*\\s*\\('),
    ('any use of should counts', 'should\\s+(be|equal|eq)\\b', 'should\\b'),
    ('URLs stripped as comments', 're.sub(r"(?<!:)//.*$", "", line)', 're.sub(r"//.*$", "", line)'),
    ('trailing // comment kept', '            line = re.sub(r"(?<!:)//.*$", "", line)', '            pass'),
    ('trailing -- comment kept', '            line = re.sub(r"--.*$", "", line)', '            pass'),
    ('custom assertion ignored', 'assertion = re.compile(tests["assertion"])', 'assertion = re.compile(tests["assertion"]) and ASSERTION'),
    ('EXPECT_ not recognised', '(EXPECT|ASSERT|REQUIRE|CHECK)(_', '(ASSERT|REQUIRE|CHECK)(_'),
    ('ASSERT_ not recognised', '(EXPECT|ASSERT|REQUIRE|CHECK)(_', '(EXPECT|REQUIRE|CHECK)(_'),
    ('REQUIRE not recognised', '(EXPECT|ASSERT|REQUIRE|CHECK)(_', '(EXPECT|ASSERT|CHECK)(_'),
    ('CHECK not recognised', '(EXPECT|ASSERT|REQUIRE|CHECK)(_', '(EXPECT|ASSERT|REQUIRE)(_'),
    ('strictEqual not recognised', '(strictEqual|deepStrictEqual|', '(deepStrictEqual|'),
    ('deepStrictEqual not recognised', '|deepStrictEqual|', '|'),
    ('deepEqual not recognised', '|deepEqual|', '|'),
    ('notStrictEqual not recognised', '|notStrictEqual|', '|'),
    ('notEqual not recognised', '|notEqual)', ')'),
    ('exit( not recognised', '\\b(exit|Exit)\\s', '\\b(Exit)\\s'),
    ('Exit( not recognised', '\\b(exit|Exit)\\s', '\\b(exit)\\s'),
    ('panic without ! not recognised', 'panic!?\\s*\\(', 'panic!\\s*\\('),
    ('conservation counts as an anchor', '{"reference", "independent"},', '{"reference", "independent", "conservation"},'),
    ('independent is not an anchor', '{"reference", "independent"},', '{"reference"},'),
    ('reference is not an anchor', '{"reference", "independent"},', '{"independent"},'),
    ('a reference stands in for a control', '{"control"},', '{"control", "reference"},'),
    ('a prediction stands in for a limit', '{"convention", "omitted"},', '{"convention", "omitted", "prediction"},'),
    ('convention is not a limit', '{"convention", "omitted"},', '{"omitted"},'),
    ('omitted is not a limit', '{"convention", "omitted"},', '{"convention"},'),
    ('default tests dir changed', 'tests.get("dir", "test")', 'tests.get("dir", "tests")'),
    ('default doc changed', '_string_list(data, "docs", ["README.md"])', '_string_list(data, "docs", ["DOCS.md"])'),
    ('default glob lost', '["*.test.*", "test_*.py", "*_test.*"]', '["test_*.py", "*_test.*"]'),
    ('a mutation needs no replace', '("claim", "file", "find", "replace")', '("claim", "file", "find")'),
    ('a mutation needs no find', '("claim", "file", "find", "replace")', '("claim", "file", "replace")'),
    ('a mutation needs no file', '("claim", "file", "find", "replace")', '("claim", "find", "replace")'),
    ('a mutation needs no claim', '("claim", "file", "find", "replace")', '("file", "find", "replace")'),
    ('mutations of rejected claims accepted', 'valid_claims = {c["id"] for c in claims}', 'valid_claims = seen'),
    ('two occurrences of find accepted', 'if count != 1:', 'if count not in (1, 2):'),
    ('invalid dates accepted', '            date(int(year), int(month), int(day))\n', '            pass\n'),
    ('first year not enforced', 'if FIRST_YEAR <= int(year) <= LAST_YEAR:', 'if int(year) <= LAST_YEAR:'),
    ('last year not enforced', 'if FIRST_YEAR <= int(year) <= LAST_YEAR:', 'if FIRST_YEAR <= int(year):'),
    ('date may sit inside a longer number', 'DATE = re.compile(r"\\b(\\d{4})', 'DATE = re.compile(r"(\\d{4})'),
    ('an invalid date ends the search', '        except ValueError:\n            continue\n        if FIRST_YEAR', '        except ValueError:\n            break\n        if FIRST_YEAR'),
    ('symlinks kept as links', 'ignore=ignore, symlinks=False)', 'ignore=ignore, symlinks=True)'),
    ('files named like a link are skipped', 'if n in links and (package / n).is_dir()]', 'if n in links]'),
    ('duplicate link names crash', 'if source.is_dir() and not os.path.lexists(destination / name):', 'if source.is_dir():'),
    ('reference tables may be mutated', '        if table is not None and table.exists():\n            protected.append(table)', '        pass'),
    ('support paths may be mutated', 'protected = [*checks, *support]', 'protected = [*checks]'),
    ('support paths are not readers', 'for place in [tests_dir, *support]:', 'for place in [tests_dir]:'),
    ('test files in subdirectories not scanned', 'for path in sorted(root.rglob("*"))', 'for path in sorted(root.glob("*"))'),
    ('reference matched by stem', 'if path.name not in code:', 'if path.stem not in code:'),
    ('multi-line block comments kept', '        text = re.sub(r"/\\*.*?\\*/", "", text, flags=re.S)\n', '        text = re.sub(r"/\\*.*?\\*/", "", text)\n'),
    ('block comment strip is greedy', '        text = re.sub(r"/\\*.*?\\*/", "", text, flags=re.S)\n', '        text = re.sub(r"/\\*.*\\*/", "", text, flags=re.S)\n'),
    ('an unclosed block comment is code', '        text = re.sub(r"/\\*(?:(?!\\*/).)*\\Z", "", text, flags=re.S)\n', ''),
    ("the ledger's pattern is ignored for claims", '        if not has_assertion(path, ledger.assertion):\n            audit.add("claims"', '        if not has_assertion(path):\n            audit.add("claims"'),
    ('quotes on unchecked claims ignored', 'quotes = [(c["id"], q) for c in claims for q in c.get("quoted", [])]', 'quotes = [(c["id"], q) for c in claims if c["kind"] in CHECKED_KINDS for q in c.get("quoted", [])]'),
    ('quoted values stripped before matching the report', 'if q not in report]', 'if q.strip() not in report]'),
    ('quoted values stripped before matching the docs', 'if q not in docs]', 'if q.strip() not in docs]'),
    ('report output truncated', 'unprinted = [', 'report = report[:10000]\n    unprinted = ['),
    ('suite exit 2 is green', '    if code == 0:\n        audit.add("suite", PASS', '    if code in (0, 2):\n        audit.add("suite", PASS'),
    ('mutations of unchecked claims rejected', 'valid_claims = {c["id"] for c in claims}', 'valid_claims = {c["id"] for c in claims if c["kind"] in CHECKED_KINDS}'),
    ('text report shows PASS on every row', 'lines.append(f"{result.status:<4} {result.check:<10}{subject} {result.detail}")', 'lines.append(f"{PASS:<4} {result.check:<10}{subject} {result.detail}")'),
    ('text report drops the subject', 'subject = f" [{result.subject}]" if result.subject else ""', 'subject = ""'),
    ('text report tallies no failures', 'for s in (PASS, WARN, SKIP, FAIL)}', 'for s in (PASS, WARN, SKIP)} | {FAIL: 0}'),
    ('unexpected errors are tracebacks', '    except (OSError, ValueError) as exc:\n        return refuse', '    except ZeroDivisionError as exc:\n        return refuse'),
    ('a path with a NUL crashes', '    except (OSError, ValueError):\n        return None', '    except ZeroDivisionError:\n        return None'),
    ('a mutation in a cache is accepted', 'if any(part in STALE for part in relative.parts):', 'if False:'),
    ('default glob loses test_*.py', '["*.test.*", "test_*.py", "*_test.*"]', '["*.test.*", "*_test.*"]'),
    ('default glob loses *_test.*', '["*.test.*", "test_*.py", "*_test.*"]', '["*.test.*", "test_*.py"]'),
    ('default glob loses *.test.*', '["*.test.*", "test_*.py", "*_test.*"]', '["test_*.py", "*_test.*"]'),
    ('a whole definition line is dropped', '(assert|expect)\\w*\\s*\\("', '(assert|expect).*"'),
    ('shell exit 0 counts', 'r"\\bexit\\s+[1-9]",', 'r"\\bexit\\s+[0-9]",'),
    ('@testset counts', 'r"@test\\b",', 'r"@test",'),
    ('trailing # comment kept', '            line = strip_hash_comment(line)\n', '            pass\n'),
    ('any # starts a comment', 'line = strip_hash_comment(line)', 'line = line.split("#")[0]'),
    ('a # after $ is a comment', ' and not (index > 0 and line[index - 1] == "$")', ''),
    ('an escaped quote ends the string', 'if char == quote and not escaped:', 'if char == quote:'),
    ('a registered table may read itself', 'readers = {p for p in readers if not any(t is not None and _same(p, t) for t in tables)}', 'pass'),
    ('any file beside the tests is a reader', 'if p.is_file() and is_source(p))', 'if p.is_file())'),
    ('suffix case matters for readers', 'suffix = path.suffix.lower()\n    return suffix in SLASH_COMMENTS', 'suffix = path.suffix\n    return suffix in SLASH_COMMENTS'),
    ('internal symlinks copied as separate files', '                internal.append((link, target))\n                skipped.append(name)', '                pass'),
    ('duplicate YAML keys accepted', '                _unique_pairs([(key, None) for key in keys if isinstance(key, (str, int, float))])\n', ''),
    ('duplicate JSON keys accepted', 'json.loads(text, object_pairs_hook=_unique_pairs)', 'json.loads(text)'),
    ('internal links are absolute', 'os.path.relpath(aim, copied.parent)', 'aim'),
    ('linked names skipped at every depth', '        if here.resolve() == package:\n            skipped += [n for n in names if n in links and (package / n).is_dir()]', '        skipped += [n for n in names if n in links]'),
    ('any backslash escapes a quote', '% 2 == 1\n        if quote:', '>= 1\n        if quote:'),
    ('a python string loses its quotes', 'keep = \'""\' if token.type == tokenize.STRING else ""', 'keep = ""'),
    ('python comments are not removed', '            lines[row - 1] = lines[row - 1][:column]\n', '            pass\n'),
    ('python that does not tokenize is left unstripped', '        return None\n    middle =', '        return text\n    middle ='),
    ('python strings still count as code', 'code_text(path, strings=False)', 'code_text(path)'),
    ('file names in strings are lost to the reference check', 'code = "\\n".join(code_text(p) for p in sorted(readers))', 'code = "\\n".join(code_text(p, strings=False) for p in sorted(readers))'),
    ('helpers in subdirectories are not readers', 'else place.rglob("*")', 'else place.glob("*")'),
    ('exit with a message not recognised', '([rbfuRBFU]{0,2}[\'\\"]|[1-9])', '([1-9])'),
    ('exit with a prefixed string not recognised', '[rbfuRBFU]{0,2}', ''),
    ('exit(0) counts', '[\'\\"]|[1-9])",', '[\'\\"]|[0-9])",'),
    ('gates and tests of any kind name a table', 'readers = {p for p in checks if is_source(p)}', 'readers = set(checks)'),
    ('caches are scanned for tests', '        and not any(part in STALE for part in path.relative_to(root).parts)\n', ''),
    ('mutations start from the copy the suite ran in', '        copy_package(package, fresh, ledger.links)\n        try:', '        shutil.copytree(copy, fresh, symlinks=True)\n        try:'),
    ('only the first mutation runs', 'in enumerate(applicable):', 'in enumerate(applicable[:1]):'),
    ('a second gate on one file replaces the first', '        if gate["file"] in gates:\n            raise LedgerError(', '        if False:\n            raise LedgerError('),
    ('read-only sources crash', '            target.chmod(target.stat().st_mode | stat.S_IWUSR)\n', ''),
]

# Mutants the tests cannot kill because the change does not alter behaviour.
# name -> why. An entry that is killed, or that matches no mutant, fails the run.
EQUIVALENT: dict[str, str] = {}

CONSTANT = re.compile(r"^([A-Z_]+) = ([({])(.*)([)}])$")
SKIP_CONSTANTS = {"KINDS"}
GROUP = re.compile(r"\(([^()?]*\|[^()]*)\)")


def without_alternative(line: str, group: re.Match, index: int) -> str:
    parts = group.group(1).split("|")
    kept = "|".join(parts[:index] + parts[index + 1 :])
    return line[: group.start(1)] + kept + line[group.end(1) :]


def generated(source: str) -> list[tuple[str, str]]:
    """(name, mutated source) for every mutant derived from the source."""
    lines = source.split("\n")
    seen: Counter[str] = Counter()
    out: list[tuple[str, str]] = []

    def add(kind: str, index: int, replacement: str | None, label: str = "") -> None:
        key = f"{kind}: {lines[index].strip()}{label}"
        seen[key] += 1
        name = key if seen[key] == 1 else f"{key} (occurrence {seen[key]})"
        changed = lines[:index] + ([] if replacement is None else [replacement]) + lines[index + 1 :]
        out.append((name, "\n".join(changed)))

    block = ""  # the multi-line constant we are inside, if any
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

        opened = re.match(r"^([A-Z_]+) = [({]$", line)
        if opened:
            block = opened.group(1)
        elif block and re.match(r"^[)}]", line):
            block = ""
        elif block == "ASSERTIONS" and stripped.startswith('r"'):
            add("pattern", index, None)
        elif block.endswith("_KINDS") and stripped.startswith('"'):
            add("entry", index, None)
        elif block and block not in SKIP_CONSTANTS and block != "ASSERTIONS":
            for element in re.findall(r'"[^"]*",?\s?', line):
                add("element", index, line.replace(element, "", 1), f" without {element.strip()}")

        if block == "ASSERTIONS" or (stripped.startswith('r"') and "(def|function" in stripped):
            for group in GROUP.finditer(line):
                for number, alternative in enumerate(group.group(1).split("|")):
                    add("alt", index, without_alternative(line, group, number), f" without {alternative}")

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
    mutants += generated(source)
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
            return name, "TIMEOUT: the tests did not finish, so nothing was observed"
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
    # A suite that is already red fails for every mutant, and every mutant
    # would be counted as killed. Nothing below means anything without this.
    baseline = run_mutant(("the unchanged script", SOURCE.read_text(encoding="utf-8")))[1]
    if baseline != "SURVIVED":
        print(f"BASELINE   the tests do not pass on the unchanged script ({baseline}); no mutant was run")
        return 1
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
