"""Three Horizons framework — Phase-1 B.4 instantiation."""

from __future__ import annotations

import pytest

from core.frameworks import FRAMEWORKS_ROOT, Framework, load_framework

pytestmark = pytest.mark.unit


@pytest.fixture
def th() -> Framework:
    return load_framework(FRAMEWORKS_ROOT / "strategy" / "three-horizons.yaml")


class TestThreeHorizonsFramework:
    def test_loads_and_validates(self, th: Framework):
        assert th.id == "three-horizons"
        assert th.category == "strategy"
        assert "McKinsey" in th.source_firm
        assert th.source_year == 1999

    def test_when_to_use_count_in_range(self, th: Framework):
        assert 3 <= len(th.when_to_use) <= 5

    def test_when_not_to_use_count_in_range(self, th: Framework):
        assert 2 <= len(th.when_not_to_use) <= 3

    def test_relationships_complete(self, th: Framework):
        assert len(th.relationships.get("use_with", [])) >= 1
        assert "innovation-roadmap-deliverable" in th.relationships["upstream_from"]

    def test_output_shape_typed(self, th: Framework):
        assert th.output_shape["type"] == "RoadmapStep"

    def test_appears_in_load_all(self):
        from core.frameworks import load_all

        assert "three-horizons" in load_all()

    def test_not_d_scope(self, th: Framework):
        assert th.is_d_scope is False
