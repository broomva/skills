"""Run this skill's Node suites under pytest.

The skill is JavaScript, and its real tests are `node --test` files. The
skillify gate's `--run-tests` runs pytest, so each suite gets one pytest test
that runs it and asserts on its exit status. Node is required by the skill
itself, so a missing `node` is a failure here, never a skip.
"""

from __future__ import annotations

import glob
import shutil
import subprocess
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
HOST = SKILL / "assets" / "host"


def run_node(args: list[str], cwd: Path) -> None:
    node = shutil.which("node")
    assert node, "node is not on PATH; this skill needs Node 22 or newer"
    result = subprocess.run([node, *args], cwd=cwd, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, f"node {' '.join(args)} exited {result.returncode}\n{result.stdout[-3000:]}\n{result.stderr[-2000:]}"


def test_ana_cli_suite() -> None:
    run_node(["--test", "tests/ana.test.mjs"], SKILL)


def test_host_kit_unit_suite() -> None:
    files = sorted(glob.glob(str(HOST / "test" / "*.test.js")))
    assert len(files) >= 5, f"expected the host kit's test files, found {files}"
    run_node(["--test", *files], HOST)


def test_every_guard_is_enforced_by_a_test() -> None:
    # Removes each guard in a copy and requires the unit tests to fail.
    run_node(["scripts/mutants.mjs"], HOST)
