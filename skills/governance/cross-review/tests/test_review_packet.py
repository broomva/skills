"""Behavioral checks on actual packet validation, including malformed CLI input."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "review_packet.py"
spec = importlib.util.spec_from_file_location("review_packet", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def packet():
    p = {
        "artifact_hash": "sha256:abc",
        "primary_sources": ["raw.csv#row1"],
        "claims": [
            {
                "id": "c1",
                "claim": "target is active",
                "what_supports_it": "raw.csv#row1",
                "whats_missing": "control",
                "status": "untested",
            }
        ],
    }
    for role in ("skeptic", "believer", "refuter"):
        p[role] = {
            "dispatch_id": role,
            "fresh_context": True,
            "artifact_hash": p["artifact_hash"],
            "reviewed_claim_ids": ["c1"],
            "raw_sources_read": ["raw.csv#row1"],
            "findings": [
                {
                    "claim_id": "c1",
                    "reading": "null could be a broken apparatus",
                    "evidence": "raw.csv#row1",
                    "disposition": "open",
                    "settling_observation": "live control would falsify this reading",
                }
            ],
        }
    return p


def test_complete_packet_with_unresolved_claim_is_structurally_valid():
    module.validate(packet())  # structural validity never asserts readiness


@pytest.mark.parametrize("role", ["skeptic", "believer", "refuter"])
@pytest.mark.parametrize(
    "defect", ["settling", "inheritance", "hash", "coverage", "source"]
)
def test_each_role_must_supply_independent_falsifiable_reading(role, defect):
    p = packet()
    r = p[role]
    if defect == "settling":
        r["findings"][0]["settling_observation"] = "  "
    elif defect == "inheritance":
        r["fresh_context"] = False
    elif defect == "hash":
        r["artifact_hash"] = "different"
    elif defect == "coverage":
        r["reviewed_claim_ids"] = []
    else:
        r["raw_sources_read"] = ["summary.md"]
    with pytest.raises(ValueError):
        module.validate(p)


def test_one_dispatch_cannot_pose_as_two_independent_agents():
    for dup in ("skeptic", " skeptic "):
        p = packet()
        p["believer"]["dispatch_id"] = dup
        with pytest.raises(ValueError):
            module.validate(p)


def test_unhashable_finding_claim_id_raises_value_error():
    p = packet()
    p["skeptic"]["findings"][0]["claim_id"] = ["c1"]
    with pytest.raises(ValueError):
        module.validate(p)


@pytest.mark.parametrize("status", ["established", "contested", "untested"])
def test_ledger_states(status):
    p = packet()
    p["claims"][0]["status"] = status
    module.validate(p)


def test_unknown_state_or_claim_is_rejected():
    for key, value in [("status", "probably"), ("id", "unknown")]:
        p = packet()
        p["claims"][0][key] = value
        with pytest.raises(ValueError):
            module.validate(p)


def test_refuter_must_read_raw_sources_even_if_no_findings():
    p = packet()
    p["primary_sources"].append("figure-2.png")
    p["refuter"]["findings"] = []
    with pytest.raises(ValueError):
        module.validate(p)
    p["refuter"]["raw_sources_read"].append("figure-2.png")
    module.validate(p)


def test_cli_and_shell_gate(tmp_path):
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet()))
    shell = SCRIPT.with_name("cross-review.sh")
    result = subprocess.run(
        ["bash", str(shell), "claim-packet", str(path)], capture_output=True, text=True
    )
    assert result.returncode == 0 and json.loads(result.stdout)["valid"] is True
    path.write_text("null")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
    )
    assert result.returncode == 2 and json.loads(result.stdout)["valid"] is False


def test_cli_reads_utf8_packet_under_non_utf8_locale(tmp_path):
    p = packet()
    p["claims"][0]["claim"] = "target is \u201cactive\u201d"
    path = tmp_path / "utf8_packet.json"
    path.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
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
    assert result.returncode == 0 and json.loads(result.stdout)["valid"] is True
