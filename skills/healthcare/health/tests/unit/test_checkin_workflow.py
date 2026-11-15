"""Contract tests for Workflows/CheckIn.md (BRO-3751).

The check-in is a documented agent protocol, not code, so these tests pin the parts an
edit must not quietly lose: safety comes before anything else, every option label has
one score, storage stays in the 0700 data directory, and writes are locked and atomic.
"""
from __future__ import annotations

import re
from pathlib import Path

DOC = (Path(__file__).resolve().parents[2] / "Workflows" / "CheckIn.md").read_text()
SKILL = (Path(__file__).resolve().parents[2] / "SKILL.md").read_text()


def _protocol_steps() -> list[str]:
    body = DOC.split("## Protocol", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^(\d+)\. \*\*(.+?)\*\*", body, re.M)


def test_safety_is_step_zero_and_precedes_snapshot():
    steps = _protocol_steps()
    assert steps[0][0] == "0" and "Safety" in steps[0][1]
    assert steps[1][0] == "1" and "Snapshot" in steps[1][1]
    first = DOC.split("0. **Safety before anything.**", 1)[1].split("1. **Snapshot", 1)[0]
    assert "no sync" in first and "no storage" in first


def test_every_option_label_has_exactly_one_score():
    table = {
        "Body": ["Strong 8", "Okay 5", "Tired or heavy 3", "Unwell 1"],
        "Mind": ["Calm, clear 8", "Okay 5", "Stressed or anxious 3", "Low or flat 2"],
        "Spirit": ["Yes 8", "Partly 5", "Disconnected 2", "Hard to say: no score"],
    }
    for dim, cells in table.items():
        row = re.search(rf"^\s*\| {dim} \| (.+) \|$", DOC, re.M)
        assert row, f"no score row for {dim}"
        assert [c.strip() for c in row.group(1).split("·")] == cells


def test_storage_is_the_owner_only_data_dir_and_writes_are_atomic():
    storage = DOC.split("## Storage", 1)[1].split("\n## ", 1)[0]
    for needle in ("BROOMVA_HEALTH_DATA_DIR", "0700", "0600", "flock", "os.replace", "fsync",
                   "not inside a git work tree", "cloud-synced", "write nothing"):
        assert needle in storage, needle


def test_emergency_route_has_a_fallback_when_location_is_unknown():
    safety = DOC.split("## Safety lines", 1)[1].split("\n## ", 1)[0]
    assert "emergency number" in safety and "findahelpline.com" in safety


def test_skill_routes_to_checkin():
    assert "[CheckIn](Workflows/CheckIn.md)" in SKILL
    assert "| **CheckIn** |" in SKILL


def test_hopelessness_stops_the_protocol_at_step_zero():
    first = DOC.split("0. **Safety before anything.**", 1)[1].split("1. **Snapshot", 1)[0]
    assert "hopelessness" in first and "stop the protocol" in first


def test_user_defined_item_is_optional_with_a_first_use_setup():
    ask = DOC.split("2. **Ask", 1)[1].split("3. **Record", 1)[0]
    assert "optional" in ask and "ask three questions" in ask
    assert "first check-in" in ask and "scores" in ask and "brief" in ask
