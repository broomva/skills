"""Tests for the Merge Gate's step in .github/workflows/merge-gate.yml (BRO-2678).

Copilot code review is advisory: its check fails on the reviewer's own quota and
says nothing about the code. The step ignores that check's verdict, while still
waiting for it to finish, only when the run behind it is GitHub's dynamic Copilot
workflow for this head. Every case runs the step script as it is in the workflow
file, with a fake `gh` answering from per-poll fixtures through real jq, and every
advisory case is paired with a look-alike that must still gate.
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

# Serves check-runs.<poll>.json (the last one once polls run out) and logs every call.
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
echo "$endpoint" >> "$FAKE/calls"
case "$endpoint" in
  */check-runs)
    n=$(grep -c '/check-runs$' "$FAKE/calls"); n=$((n - 1))
    f="$FAKE/check-runs.$n.json"
    [ -f "$f" ] || f=$(ls "$FAKE"/check-runs.*.json | sort -t. -k2 -n | tail -1) ;;
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
RUNNING = {"conclusion": None, "status": "in_progress"}


def run_gate(polls: list[list[dict]], runs: dict[int, dict] | None = None) -> tuple[int, str, list[str]]:
    """One check-run list per poll; returns (exit code, output, gh endpoints called)."""
    with tempfile.TemporaryDirectory(prefix="merge-gate-") as t:
        fake = Path(t)
        bin_dir = fake / "bin"
        bin_dir.mkdir()
        for name, body in (("gh", FAKE_GH), ("sleep", "#!/bin/sh\nexit 0\n")):
            p = bin_dir / name
            p.write_text(body)
            p.chmod(p.stat().st_mode | stat.S_IEXEC)
        for i, checks in enumerate(polls):
            (fake / f"check-runs.{i}.json").write_text(json.dumps({"check_runs": checks}))
        (fake / "status.json").write_text(json.dumps({"state": "success"}))
        (fake / "calls").write_text("")
        for rid, run in (runs or {}).items():
            (fake / f"run.{rid}.json").write_text(json.dumps(run))
        env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE": str(fake),
               "GH_TOKEN": "x", "REPO": "o/r", "SHA": SHA}
        r = subprocess.run(["bash", "-c", step_script()], env=env,
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stdout + r.stderr, (fake / "calls").read_text().split()


def blocked(out: str) -> list[str]:
    return [line.strip()[2:] for line in out.splitlines() if line.strip().startswith("- ")]


def test_all_green_passes():
    code, out, _ = run_gate([GREEN])
    assert code == 0, out
    assert "Merge Gate PASS" in out


def test_copilots_quota_failure_does_not_block():
    code, out, _ = run_gate([GREEN + [check(COPILOT, "failure", run_id=7)]], {7: COPILOT_RUN})
    assert code == 0, out
    assert "its verdict is not gated" in out
    assert "::warning::" not in out


def test_a_running_copilot_review_is_waited_for_then_not_gated():
    code, out, _ = run_gate([GREEN + [check(COPILOT, run_id=7, **RUNNING)],
                             GREEN + [check(COPILOT, "failure", run_id=7)]], {7: COPILOT_RUN})
    assert code == 0, out
    # Poll 1 recognises Copilot's run while it is still running (a tab-joined
    # read shifts a running row's fields and would only see it once finished),
    # waits for it, then poll 2 ignores its verdict.
    assert out.index("its verdict is not gated") < out.index("1 still running"), out
    assert "Merge Gate PASS" in out


def test_copilots_run_is_looked_up_once():
    code, out, calls = run_gate([GREEN + [check(COPILOT, run_id=7, **RUNNING)],
                                 GREEN + [check(COPILOT, run_id=7, **RUNNING)],
                                 GREEN + [check(COPILOT, "failure", run_id=7)]], {7: COPILOT_RUN})
    assert code == 0, out
    assert sum(c.endswith("/actions/runs/7") for c in calls) == 1, calls
    # Waited on polls 1 AND 2: a cached run id must not drop a still-running row.
    assert out.count("1 still running") == 2, out


def test_a_real_failure_still_blocks_beside_copilot():
    code, out, _ = run_gate([GREEN + [check("lint-catalog", "failure"),
                                      check(COPILOT, "failure", run_id=7)]], {7: COPILOT_RUN})
    assert code == 1, out
    assert blocked(out) == ["lint-catalog"]


def test_a_failed_check_is_named_whole():
    code, out, _ = run_gate([[check("lint"), check("pytest (Python 3.12)", "failure")]])
    assert code == 1, out
    assert blocked(out) == ["pytest (Python 3.12)"]


LOOK_ALIKES = [
    ("a PR job named like Copilot", dict(run_id=8),
     {8: {"event": "pull_request", "path": ".github/workflows/x.yml", "head_sha": SHA}}),
    ("Copilot's run for another head", dict(run_id=7), {7: {**COPILOT_RUN, "head_sha": "b" * 40}}),
    ("a run lookup that fails", dict(run_id=404), {}),
    ("no run behind the check", dict(), {}),
    ("the same name from another app", dict(app="some-app", run_id=7), {7: COPILOT_RUN}),
]


@pytest.mark.parametrize("label,kw,runs", LOOK_ALIKES, ids=[x[0] for x in LOOK_ALIKES])
def test_a_look_alike_still_blocks(label, kw, runs):
    code, out, _ = run_gate([GREEN + [check(COPILOT, "failure", **kw)]], runs)
    assert code == 1, out
    assert blocked(out) == [COPILOT], out
    if kw.get("app") != "some-app":            # another app's check is never looked up
        assert "::warning::copilot-pull-request-reviewer gates as a normal check" in out
    if label == "a run lookup that fails":     # the warning says what the lookup returned
        assert "Not Found (HTTP 404)" in out, out


def test_a_running_look_alike_is_waited_for_and_its_failure_blocks():
    look = {8: {"event": "pull_request", "path": ".github/workflows/x.yml", "head_sha": SHA}}
    code, out, _ = run_gate([GREEN + [check(COPILOT, run_id=8, **RUNNING)],
                             GREEN + [check(COPILOT, "failure", run_id=8)]], look)
    assert code == 1, out
    assert blocked(out) == [COPILOT]


def test_a_look_alike_is_warned_about_once_and_looked_up_each_poll():
    look = {8: {"event": "pull_request", "path": ".github/workflows/x.yml", "head_sha": SHA}}
    code, out, calls = run_gate([GREEN + [check(COPILOT, run_id=8, **RUNNING)]] * 3
                                + [GREEN + [check(COPILOT, "success", run_id=8)]], look)
    assert code == 0, out
    assert out.count("::warning::") == 1, out
    assert sum(c.endswith("/actions/runs/8") for c in calls) == 4, calls


def test_a_hung_copilot_run_times_out_naming_it():
    code, out, _ = run_gate([GREEN + [check(COPILOT, run_id=7, **RUNNING)]], {7: COPILOT_RUN})
    assert code == 1, out
    assert "Merge Gate timed out" in out
    assert out.strip().splitlines()[-1].strip() == f"- {COPILOT} (in_progress)", out


def test_the_job_requests_actions_read():
    # The fake gh cannot answer 403; without actions: read the lookup fails in
    # CI, the row gates as a normal check, and Copilot blocks exactly as before.
    doc = yaml.safe_load(WORKFLOW.read_text())
    assert (doc.get("permissions") or {}).get("actions") == "read"
