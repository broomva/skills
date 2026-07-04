import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import smoke as s  # noqa: E402


def test_all_required_present_passes():
    ok, ratio, _ = s.assess_output(
        "Patient: Bella. Meloxicam 1.5mg. Recheck in one week.",
        {"required": ["Bella", "Meloxicam", "one week"]},
    )
    assert ok and ratio == 1.0


def test_missing_required_fails():
    ok, ratio, reason = s.assess_output("Patient: Bella.", {"required": ["Bella", "Meloxicam"]})
    assert not ok and "missing" in reason and ratio == 0.5


def test_forbidden_placeholder_fails():
    ok, _, reason = s.assess_output("Patient: <UNFILLED>", {"required": [], "forbidden": ["<UNFILLED>"]})
    assert not ok and "forbidden" in reason


def test_empty_required_passes():
    ok, ratio, _ = s.assess_output("anything", {"required": []})
    assert ok and ratio == 1.0


# --- P20 substring false-positive regression ---
def test_p20_substring_false_positive_rejected():
    # "Bella" must NOT be satisfied by "Isabella", nor "one week" by "phone weekly"
    ok, _, reason = s.assess_output("Isabella phoned weekly", {"required": ["Bella", "one week"]})
    assert not ok and "missing" in reason
