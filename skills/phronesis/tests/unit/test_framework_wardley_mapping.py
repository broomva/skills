"""Wardley Mapping framework — Phase-1 B.5 instantiation."""

from __future__ import annotations

import pytest

from core.frameworks import FRAMEWORKS_ROOT, Framework, load_framework

pytestmark = pytest.mark.unit


@pytest.fixture
def wm() -> Framework:
    return load_framework(FRAMEWORKS_ROOT / "strategy" / "wardley-mapping.yaml")


class TestWardleyMappingFramework:
    def test_loads_and_validates(self, wm: Framework):
        assert wm.id == "wardley-mapping"
        assert wm.category == "strategy"
        assert wm.source_firm == "Simon Wardley"

    def test_when_to_use_count_in_range(self, wm: Framework):
        assert 3 <= len(wm.when_to_use) <= 5

    def test_when_not_to_use_count_in_range(self, wm: Framework):
        assert 2 <= len(wm.when_not_to_use) <= 3

    def test_relationships_complete(self, wm: Framework):
        assert "three-horizons" in wm.relationships["similar_to"]
        assert "capability-heatmap-deliverable" in wm.relationships["upstream_from"]

    def test_output_shape_typed(self, wm: Framework):
        assert wm.output_shape["type"] == "CapabilityCell"

    def test_appears_in_load_all(self):
        from core.frameworks import load_all

        assert "wardley-mapping" in load_all()

    def test_not_d_scope(self, wm: Framework):
        assert wm.is_d_scope is False
