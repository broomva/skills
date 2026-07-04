import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import validate as v  # noqa: E402

# Captured from a REAL `eve info --json` (eve v0.19.0, dogfood BRO-1685) — the
# fidelity anchor. The v1.0.0 tests used a synthetic `{"diagnostics": []}` shape
# that never matched real eve, so the gate passed its tests yet crashed on the
# real tool (mock-fidelity-gap-false-green). These assert against the real schema.
REAL_EVE_INFO = {
    "appRoot": "/home/agent/bench/vet-clinic",
    "agentRoot": "/home/agent/bench/vet-clinic/agent",
    "layout": "nested",
    "status": "ready",
    "diagnostics": {"errors": 0, "warnings": 0},
    "model": "anthropic/claude-sonnet-5",
    "instructions": "instructions.md",
    "skills": [],
    "tools": ["fill_document", "send_document"],
    "channels": [{"name": "eve", "kind": "http", "method": "POST", "urlPath": "/eve/v1/session"}],
}
BANNER = "☰eve  v0.19.0\n"


def test_real_eve_info_ready_passes():
    ok, _ = v.assess_info(REAL_EVE_INFO, ["fill_document", "send_document"])
    assert ok


def test_parse_info_strips_banner():
    parsed = v.parse_info(BANNER + json.dumps(REAL_EVE_INFO))
    assert parsed["status"] == "ready" and parsed["tools"] == ["fill_document", "send_document"]


def test_real_diagnostics_dict_errors_fail():
    bad = dict(REAL_EVE_INFO, diagnostics={"errors": 2, "warnings": 1})
    ok, r = v.assess_info(bad)
    assert not ok and "diagnostic" in r


def test_warnings_only_still_ready():
    ok, _ = v.assess_info(dict(REAL_EVE_INFO, diagnostics={"errors": 0, "warnings": 3}))
    assert ok


def test_real_status_not_ready_fails():
    ok, r = v.assess_info(dict(REAL_EVE_INFO, status="error"))
    assert not ok and "not ready" in r


def test_missing_expected_tool_fails():
    ok, r = v.assess_info(REAL_EVE_INFO, ["nonexistent"])
    assert not ok and "missing" in r


def test_tools_as_objects():
    info = dict(REAL_EVE_INFO, tools=[{"name": "fill_document"}])
    ok, _ = v.assess_info(info, ["fill_document"])
    assert ok


# backward-compat: list-shaped diagnostics + boolean readiness still handled
def test_list_diagnostics_fail():
    ok, r = v.assess_info({"diagnostics": ["TS2345 type error"], "tools": ["x"], "status": "ready"})
    assert not ok and "diagnostic" in r


def test_ready_string_false_fails():
    ok, _ = v.assess_info({"diagnostics": {"errors": 0}, "tools": ["x"], "ready": "false"})
    assert not ok


def test_errors_key_alias_fails():
    ok, r = v.assess_info({"errors": ["boom"], "tools": ["x"]})
    assert not ok and "diagnostic" in r
