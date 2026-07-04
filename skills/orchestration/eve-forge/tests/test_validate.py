import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import validate as v  # noqa: E402


def test_zero_diagnostics_with_tools_passes():
    ok, _ = v.assess_info({"diagnostics": [], "tools": ["fill_document", "send_document"]}, ["fill_document"])
    assert ok


def test_diagnostics_fail():
    ok, reason = v.assess_info({"diagnostics": ["TS2345 type error"], "tools": []})
    assert not ok and "diagnostic" in reason


def test_missing_expected_tool_fails():
    ok, reason = v.assess_info({"diagnostics": [], "tools": ["send_document"]}, ["fill_document"])
    assert not ok and "missing" in reason


def test_not_compile_ready_fails():
    ok, _ = v.assess_info({"diagnostics": [], "tools": ["x"], "ready": False})
    assert not ok


def test_tools_as_objects():
    ok, _ = v.assess_info({"diagnostics": [], "tools": [{"name": "fill_document"}]}, ["fill_document"])
    assert ok


# --- P20 fail-OPEN regression tests ---
def test_p20_ready_string_false_fails():
    ok, _ = v.assess_info({"diagnostics": [], "tools": ["x"], "ready": "false"})
    assert not ok


def test_p20_compile_zero_fails():
    ok, _ = v.assess_info({"diagnostics": [], "tools": ["x"], "compile": 0})
    assert not ok


def test_p20_errors_key_alias_fails():
    ok, reason = v.assess_info({"errors": ["boom"], "tools": ["x"]})
    assert not ok and "diagnostic" in reason
