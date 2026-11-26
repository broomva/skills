import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "capability_plan.py"
spec = importlib.util.spec_from_file_location("capability_plan", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def operation(tier):
    return {
        "id": tier,
        "operation": "observe target",
        "tier": tier,
        "owner": "current agent",
        "settling_observation": "raw output meets threshold",
        "catalog_ref": "tool:read",
        "input_schema_ref": "schema:read.input",
        "output_schema_ref": "schema:read.output",
        "readiness_evidence": "probe passed",
        "authorized": True,
        "substrate_ref": "environment:local",
        "missing_prerequisite": "wrapper",
        "promotion_check": "wrapper smoke passes",
        "external_executor": "owner",
        "handoff_artifact": "work-order.md",
        "return_evidence": "signed receipt",
    }


def test_open_proposals_are_preserved_but_only_catalog_work_is_dispatchable():
    plan = [operation(t) for t in ("executable_now", "request_quote", "send_out")]
    assert module.validate(plan) == ["executable_now"]


@pytest.mark.parametrize(
    "field",
    [
        "catalog_ref",
        "input_schema_ref",
        "output_schema_ref",
        "readiness_evidence",
        "authorized",
    ],
)
def test_no_hallucinated_or_unauthorized_catalog_step(field):
    op = operation("executable_now")
    del op[field]
    with pytest.raises(ValueError):
        module.validate([op])


@pytest.mark.parametrize(
    "field",
    ["id", "operation", "owner", "settling_observation"],
)
def test_common_required_fields_are_enforced(field):
    for bad in (None, "   "):
        op = operation("executable_now")
        if bad is None:
            del op[field]
        else:
            op[field] = bad
        with pytest.raises(ValueError):
            module.validate([op])


@pytest.mark.parametrize(
    "tier,field",
    [
        ("request_quote", "substrate_ref"),
        ("request_quote", "missing_prerequisite"),
        ("request_quote", "promotion_check"),
        ("send_out", "external_executor"),
        ("send_out", "handoff_artifact"),
        ("send_out", "return_evidence"),
    ],
)
def test_nonexecutable_operations_have_actionable_handoffs(tier, field):
    op = operation(tier)
    op[field] = ""
    with pytest.raises(ValueError):
        module.validate([op])


def test_unknown_or_duplicate_operations_fail():
    with pytest.raises(ValueError):
        module.validate([operation("probably_supported")])
    with pytest.raises(ValueError):
        module.validate([operation("send_out"), operation("send_out")])


def test_cli_returns_tiers_and_rejects_empty_plan(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps([operation("request_quote")]))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
    )
    assert result.returncode == 0 and json.loads(result.stdout)["executable_now"] == []
    path.write_text("[]")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
    )
    assert result.returncode == 2 and not json.loads(result.stdout)["valid"]


def test_cli_reads_utf8_plan_under_non_utf8_locale(tmp_path):
    op = operation("executable_now")
    op["id"] = "café"
    path = tmp_path / "utf8_plan.json"
    path.write_text(json.dumps([op], ensure_ascii=False), encoding="utf-8")
    env = {
        **os.environ,
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONUTF8": "0",
        "PYTHONCOERCECLOCALE": "0",
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["executable_now"] == ["café"]
