#!/usr/bin/env python3
"""Mutation check for scripts/checkable.py.

Four kinds of mutant, one at a time:

  refusal    a statement that records a refusal (`add(...)`, `invalid(...)`)
             is replaced by `pass`
  condition  the test of an `if` or `elif` is negated
  pattern    a module-level `re.compile(...)` pattern is replaced by one that
             matches anything
  accept     a function that answers a yes-or-no question about a value is
             made to answer the permissive way for every value

The first two are applied in the functions that decide something: shape,
check, replay, pin_state, index_report and route. What this does not mutate:
operators inside one condition, comprehension filters, the tables of allowed
values, and the code in main. A mutant is killed only when pytest exits 1, which
means a test failed. Any other status (a collection error, an interrupted
run) is reported as an error and fails this check, because it is not
evidence that a test noticed the change.

    python3 tests/mutate.py            # exit 0 when every mutant is killed
    python3 tests/mutate.py --list     # print the mutation sites and stop
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
DECIDERS = ("shape", "check", "replay", "pin_state", "index_report", "route")
REFUSERS = ("add", "invalid")
# Each of these answers a question about one value. The mutant makes it give
# the permissive answer always: `True` for a shape predicate, `None` (no
# problem) for a gate, and the same text for every statement for the pin.
ALWAYS = {
    "_text": "True",
    "_id": "True",
    "_origin": "True",
    "_performer": "True",
    "_date": "True",
    "_whole": "True",
    "_mapping": "True",
    "_mappings": "True",
    "gate_problem": "None",
    "pinned_text": "''",
    "_no_duplicate_keys": "dict(pairs)",
}

# The suite runs on a copy outside the repository, so the settings that make
# CI require the repository's roster do not apply to it.
SUITE_ENV = {k: v for k, v in os.environ.items() if not k.startswith("CHECKABLE_REQUIRE_")}
SUITE_ENV["PYTHONDONTWRITEBYTECODE"] = "1"

# The timing tests exercise _run, which is not mutated, and they dominate the
# suite's run time.
SUITE_ARGS = ["-q", "-x", "-p", "no:cacheprovider", "-k", "not timeout"]


def sites(source: str) -> list[dict]:
    """Every mutation site, each with the lines that replace its span."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    found: list[dict] = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef) or function.name not in DECIDERS:
            continue
        for node in ast.walk(function):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                called = node.value.func
                if isinstance(called, ast.Name) and called.id in REFUSERS:
                    indent = lines[node.lineno - 1][: node.col_offset]
                    found.append(
                        {
                            "kind": "refusal",
                            "function": function.name,
                            "line": node.lineno,
                            "start": (node.lineno, 0),
                            "end": (node.end_lineno, len(lines[node.end_lineno - 1].rstrip("\n"))),
                            "text": f"{indent}pass",
                        }
                    )
            if isinstance(node, ast.If):
                test = node.test
                original = ast.get_source_segment(source, test)
                found.append(
                    {
                        "kind": "condition",
                        "function": function.name,
                        "line": test.lineno,
                        "start": (test.lineno, test.col_offset),
                        "end": (test.end_lineno, test.end_col_offset),
                        "text": f"not ({original})",
                    }
                )
    for node in tree.body:
        # ID = re.compile(r"...")
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            if ast.unparse(call.func) == "re.compile" and call.args:
                pattern = call.args[0]
                found.append(
                    {
                        "kind": "pattern",
                        "function": ast.unparse(node.targets[0]),
                        "line": pattern.lineno,
                        "start": (pattern.lineno, pattern.col_offset),
                        "end": (pattern.end_lineno, pattern.end_col_offset),
                        "text": 'r"(?s).*"',
                    }
                )
        if isinstance(node, ast.FunctionDef) and node.name in ALWAYS:
            first, last = node.body[0], node.body[-1]
            indent = lines[first.lineno - 1][: len(lines[first.lineno - 1]) - len(lines[first.lineno - 1].lstrip())]
            found.append(
                {
                    "kind": "accept",
                    "function": node.name,
                    "line": node.lineno,
                    "start": (first.lineno, 0),
                    "end": (last.end_lineno, len(lines[last.end_lineno - 1].rstrip("\n"))),
                    "text": f"{indent}return {ALWAYS[node.name]}",
                }
            )
    missing = sorted(set(ALWAYS) - {s["function"] for s in found if s["kind"] == "accept"})
    if missing:
        raise SystemExit(f"mutate.py names functions the checker no longer has: {', '.join(missing)}")
    found.sort(key=lambda s: (s["start"], s["kind"]))
    return found


def apply(source: str, site: dict) -> str:
    lines = source.splitlines(keepends=True)
    (start_line, start_col), (end_line, end_col) = site["start"], site["end"]
    # ast columns are UTF-8 byte offsets.
    head = lines[start_line - 1].encode()[:start_col].decode()
    tail = lines[end_line - 1].encode()[end_col:].decode()
    return "".join(lines[: start_line - 1]) + head + site["text"] + tail + "".join(lines[end_line:])


def run_suite(copy: Path) -> int:
    # No bytecode cache: two mutants of the same length written in the same
    # second would otherwise share one cached module, and a result would be
    # credited to the wrong site.
    for cache in copy.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    return subprocess.run(
        [sys.executable, "-B", "-m", "pytest", str(copy / "tests" / "test_checkable.py"), *SUITE_ARGS],
        capture_output=True,
        text=True,
        env=SUITE_ENV,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--list", action="store_true", help="print the mutation sites and stop")
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()

    original = (SKILL / "scripts" / "checkable.py").read_text(encoding="utf-8")
    all_sites = sites(original)
    if args.list:
        for site in all_sites:
            print(f"{site['kind']:<9} {site['function']}:{site['line']}")
        print(f"{len(all_sites)} sites")
        return 0
    if not all_sites:
        print("no mutation site found; the checker's shape no longer matches this script")
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        copies = []
        for worker in range(max(1, args.workers)):
            copy = Path(tmp) / f"w{worker}" / "checkable"
            shutil.copytree(SKILL, copy, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
            copies.append(copy)
        # Three clean runs first: a suite that fails now and then would report
        # a kill it did not earn.
        for _ in range(3):
            status = run_suite(copies[0])
            if status != 0:
                print(f"the unmutated suite exits {status}; nothing can be concluded")
                return 2

        def judge(job: tuple[int, dict]) -> tuple[dict, int]:
            number, site = job
            copy = copies[number % len(copies)]
            return site, _mutant_status(copy, original, site)

        # One mutant per copy at a time: a worker owns its copy for the whole run.
        results: list[tuple[dict, int]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(copies)) as pool:
            queues = [[(n, s) for n, s in enumerate(all_sites) if n % len(copies) == w] for w in range(len(copies))]
            futures = [pool.submit(lambda jobs=jobs: [judge(job) for job in jobs]) for jobs in queues]
            for future in futures:
                results.extend(future.result())

    survived = [site for site, status in results if status == 0]
    errors = [(site, status) for site, status in results if status not in (0, 1)]
    killed = sum(1 for _, status in results if status == 1)
    print(f"{killed}/{len(all_sites)} mutants killed")
    for site in sorted(survived, key=lambda s: s["start"]):
        print(f"  survived: {site['kind']} in {site['function']} at line {site['line']}")
    for site, status in sorted(errors, key=lambda e: e[0]["start"]):
        print(f"  error (pytest exit {status}, not a kill): {site['kind']} in {site['function']} at line {site['line']}")
    return 1 if survived or errors else 0


def _mutant_status(copy: Path, original: str, site: dict) -> int:
    target = copy / "scripts" / "checkable.py"
    target.write_text(apply(original, site), encoding="utf-8")
    try:
        return run_suite(copy)
    finally:
        target.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
