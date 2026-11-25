#!/usr/bin/env python3
"""Mutation check: remove each refusal in the checker, one at a time, and
expect the suite to fail every time. A suite that still passes with a refusal
removed is not testing that refusal.

    python3 tests/mutate.py        # exit 0 when every mutant is killed
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
REFUSAL = re.compile(r'add\("(C\d)", "FAIL",')


def run_suite(copy: Path) -> int:
    # No bytecode cache: two mutants of the same length written in the same
    # second would otherwise share one cached module, and a result would be
    # credited to the wrong refusal.
    for cache in copy.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    return subprocess.run(
        [sys.executable, "-B", "-m", "pytest", str(copy / "tests" / "test_checkable.py"), "-q", "-x", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    ).returncode


def main() -> int:
    survivors = []
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "checkable"
        shutil.copytree(SKILL, copy, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        target = copy / "scripts" / "checkable.py"
        original = target.read_text(encoding="utf-8")
        # Three clean runs first: a suite that fails now and then would report
        # a kill it did not earn.
        if any(run_suite(copy) != 0 for _ in range(3)):
            print("the unmutated suite fails at least once in three runs; nothing can be concluded")
            return 2
        sites = list(REFUSAL.finditer(original))
        if not sites:
            print("no refusal found to remove; the pattern no longer matches the checker")
            return 2
        for site in sites:
            line = original.count("\n", 0, site.start()) + 1
            mutant = original[: site.start()] + "(lambda *a: None)(" + original[site.start() + len("add(") :]
            target.write_text(mutant, encoding="utf-8")
            if run_suite(copy) == 0:
                survivors.append(f"{site.group(1)} at line {line}")
        target.write_text(original, encoding="utf-8")
    killed = len(sites) - len(survivors)
    print(f"{killed}/{len(sites)} mutants killed")
    for survivor in survivors:
        print(f"  survived: {survivor}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
