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


# --- v1.0.2: HTML-comment stripping + case-scoped negative constraint (BRO-1685) ---
def test_echoed_html_comment_does_not_trip_forbidden():
    # an echoed template comment containing a forbidden word must NOT fail the gate
    out = "Follow-up: recheck in one week.\n<!-- if senior (>8y) add a bloodwork line -->"
    ok, _, _ = s.assess_output(out, {"required": ["one week"], "forbidden": ["bloodwork"]})
    assert ok


def test_negative_constraint_in_body_fails():
    # the real senior-rule violation: 'bloodwork' in the actual body MUST fail
    out = "Follow-up: recheck in one week; recommend baseline bloodwork."
    ok, _, r = s.assess_output(out, {"required": ["one week"], "forbidden": ["bloodwork"]})
    assert not ok and "forbidden" in r
