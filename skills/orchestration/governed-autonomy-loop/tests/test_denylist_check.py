"""Unit tests for the tracker-denylist coverage check.

The regression this pins: when the tracker gains a write tool (or a Kanon
cutover swaps the MCP behind the name), a denylist that isn't re-derived fails
OPEN. The check must flag exactly the uncovered tools in each denylist.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import denylist_check as dc  # noqa: E402

_REPO = Path(__file__).resolve().parent.parent


def _spec(surface, gov, arc):
    return {"write_surface": surface, "governor_dry_denylist": gov, "arc_denylist": arc}


def test_uncovered_reports_missing_sorted():
    assert dc.uncovered(["a", "b", "c"], ["a"]) == ["b", "c"]


def test_check_pass_when_both_cover():
    ok, report = dc.check(_spec(["a", "b"], ["a", "b"], ["a", "b"]))
    assert ok
    assert report["governor_uncovered"] == []
    assert report["arc_uncovered"] == []


def test_check_fails_when_governor_gap():
    ok, report = dc.check(_spec(["a", "b"], ["a"], ["a", "b"]))
    assert not ok
    assert report["governor_uncovered"] == ["b"]


def test_check_fails_when_arc_gap():
    # The exact fail-open a new tracker write tool creates.
    ok, report = dc.check(_spec(["save_x", "save_new"], ["save_x", "save_new"], ["save_x"]))
    assert not ok
    assert report["arc_uncovered"] == ["save_new"]


def test_shipped_linear_adapter_passes():
    # The reference tracker adapter this skill ships must itself be complete.
    spec = json.loads((_REPO / "templates" / "denylist.linear.json").read_text())
    ok, report = dc.check(spec)
    assert ok, report
    assert report["write_surface_size"] == 21


def test_shipped_adapter_covers_create_initiative_label():
    # Regression: the reference tick.sh DRY_FLAGS omitted create_initiative_label;
    # the shipped adapter must NOT (this is the fail-open the check exists to catch).
    spec = json.loads((_REPO / "templates" / "denylist.linear.json").read_text())
    assert "mcp__linear-server__create_initiative_label" in spec["governor_dry_denylist"]
    assert "mcp__linear-server__create_initiative_label" in spec["arc_denylist"]
