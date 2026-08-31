"""Positive control for the live-root watchdog in conftest.py.

The watchdog's docstring claimed it was "pinned by a mutation: disabling
`_sandbox_phronesis_roots` turns the suite red through this fixture". That was
true when run by hand and enforced by nothing in the repo — a prose claim no
test enforces, in the file whose whole purpose is not to have those.

These pin the detector's logic. They do NOT pin the fixture wiring (that is
what the by-hand mutation shows), and this file says so rather than implying
coverage it does not have.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import live_root_changes

pytestmark = pytest.mark.unit

A = Path("/live/a.md")
B = Path("/live/b.md")


class TestLiveRootChanges:
    def test_no_change_is_no_finding(self):
        assert live_root_changes({A: 1.0}, {A: 1.0}) == []

    def test_detects_a_created_file(self):
        assert live_root_changes({}, {A: 1.0}) == [A]

    def test_detects_a_modified_file(self):
        assert live_root_changes({A: 1.0}, {A: 2.0}) == [A]

    def test_detects_a_DELETED_file(self):
        """The original comparison walked `after` only, so a test that
        unlinked a live entity page passed clean."""
        assert live_root_changes({A: 1.0}, {}) == [A]

    def test_reports_each_path_once(self):
        assert live_root_changes({A: 1.0}, {A: 2.0, B: 1.0}) == sorted([A, B])

    def test_empty_both_sides(self):
        assert live_root_changes({}, {}) == []
