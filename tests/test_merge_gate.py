"""Tests for the Merge Gate's step in .github/workflows/merge-gate.yml (BRO-2678).

Copilot code review is advisory: its check fails on the reviewer's own quota and
says nothing about the code. The step drops that check only when the run behind
it is GitHub's dynamic Copilot workflow for this head. Every case runs the step
script as it is in the workflow file, with a fake `gh` answering from fixtures
through real jq, and every "not gated" case is paired with a look-alike that
must still block.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "merge-gate.yml"
STEP = "Require all other checks green (or skipped)"
SHA = "a" * 40
COPILOT = "copilot-pull-request-reviewer"
COPILOT_RUN = {"event": "dynamic", "path": "dynamic/agents/copilot-pull-request-reviewer",
               "head_sha": SHA}

FAKE_GH = r"""#!/usr/bin/env bash
endpoint=""; filter="."
while [ $# -gt 0 ]; do
  case "$1" in
    api|--paginate) ;;
    --jq) filter="$2"; shift ;;
    *) endpoint="$1" ;;
  esac
  shift
done
case "$endpoint" in
  */check-runs) f="$FAKE/check-runs.json" ;;
  */status) f="$FAKE/status.json" ;;
  */actions/runs/*) f="$FAKE/run.${endpoint##*/}.json" ;;
  *) echo "unexpected gh api $endpoint" >&2; exit 3 ;;
esac
[ -f "$f" ] || { echo "gh: Not Found (HTTP 404)" >&2; exit 1; }
jq -r "$filter" "$f"
"""


def step_script() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text())
    return next(s["run"] for s in doc["jobs"]["gate"]["steps"] if s.get("name") == STEP)


def check(name: str, conclusion: str | None = "success", status: str = "completed",
          app: str = "github-actions", run_id: int | None = None) -> dict:
    url = f"https://github.com/o/r/actions/runs/{run_id}/job/9" if run_id else None
    return {"name": name, "status": status, "conclusion": conclusion,
            "app": {"slug": app}, "details_url": url}


GREEN = [check("lint"), check("pytest (Python 3.12)")]


def run_gate(checks: list[dict], runs: dict[int, dict] | None = None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="merge-gate-") as t:
        fake = Path(t)
        bin_dir = fake / "bin"
        bin_dir.mkdir()
        for name, body in (("gh", FAKE_GH), ("sleep", "#!/bin/sh\nexit 0\n")):
            p = bin_dir / name
            p.write_text(body)
            p.chmod(p.stat().st_mode | stat.S_IEXEC)
        (fake / "check-runs.json").write_text(json.dumps({"check_runs": checks}))
        (fake / "status.json").write_text(json.dumps({"state": "success"}))
        for rid, run in (runs or {}).items():
            (fake / f"run.{rid}.json").write_text(json.dumps(run))
        env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE": str(fake),
               "GH_TOKEN": "x", "REPO": "o/r", "SHA": SHA}
        r = subprocess.run(["bash", "-c", step_script()], env=env,
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout + r.stderr


def blocked(out: str) -> list[str]:
    return [line.strip()[2:] for line in out.splitlines() if line.strip().startswith("- ")]


def test_all_green_passes():
    code, out = run_gate(GREEN)
    assert code == 0, out
    assert "Merge Gate PASS" in out


def test_copilots_quota_failure_does_not_block():
    code, out = run_gate(GREEN + [check(COPILOT, "failure", run_id=7)], {7: COPILOT_RUN})
    assert code == 0, out
    assert "advisory, not gated" in out


def test_a_running_copilot_review_is_not_waited_for():
    code, out = run_gate(GREEN + [check(COPILOT, None, status="in_progress", run_id=7)],
                         {7: COPILOT_RUN})
    assert code == 0, out
    assert "waiting:" not in out


def test_a_real_failure_still_blocks_beside_copilot():
    code, out = run_gate(GREEN + [check("lint-catalog", "failure"),
                                  check(COPILOT, "failure", run_id=7)], {7: COPILOT_RUN})
    assert code == 1, out
    assert blocked(out) == ["lint-catalog"]


def test_a_failed_check_is_named_whole():
    code, out = run_gate([check("lint"), check("pytest (Python 3.12)", "failure")])
    assert code == 1, out
    assert blocked(out) == ["pytest (Python 3.12)"]


@pytest.mark.parametrize("label,checks,runs", [
    ("a PR job named like Copilot",
     [check(COPILOT, "failure", run_id=8)],
     {8: {"event": "pull_request", "path": ".github/workflows/x.yml", "head_sha": SHA}}),
    ("Copilot's run for another head",
     [check(COPILOT, "failure", run_id=7)],
     {7: {**COPILOT_RUN, "head_sha": "b" * 40}}),
    ("a run lookup that fails",
     [check(COPILOT, "failure", run_id=404)], {}),
    ("no run behind the check",
     [check(COPILOT, "failure")], {}),
    ("the same name from another app",
     [check(COPILOT, "failure", app="some-app", run_id=7)], {7: COPILOT_RUN}),
])
def test_a_look_alike_still_blocks(label, checks, runs):
    code, out = run_gate(GREEN + checks, runs)
    assert code == 1, f"{label}: {out}"
    assert blocked(out) == [COPILOT], f"{label}: {out}"


def test_the_token_can_read_the_run_behind_the_check():
    # The fake gh cannot answer 403; without actions: read the lookup fails in
    # CI, the row is kept, and Copilot blocks exactly as before.
    doc = yaml.safe_load(WORKFLOW.read_text())
    assert (doc.get("permissions") or {}).get("actions") == "read"
