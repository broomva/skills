"""ICE framework — Phase-1 B.2 instantiation. Mirrors test_framework_rice.py."""

from __future__ import annotations

import pytest

from core.frameworks import FRAMEWORKS_ROOT, Framework, load_framework

pytestmark = pytest.mark.unit


@pytest.fixture
def ice() -> Framework:
    return load_framework(FRAMEWORKS_ROOT / "prioritization" / "ice.yaml")


class TestIceFramework:
    def test_loads_and_validates(self, ice: Framework):
        assert ice.id == "ice"
        assert ice.category == "prioritization"
        assert ice.source_firm == "GrowthHackers (Sean Ellis)"
        assert ice.source_year == 2009

    def test_when_to_use_count_in_range(self, ice: Framework):
        assert 3 <= len(ice.when_to_use) <= 5

    def test_when_not_to_use_count_in_range(self, ice: Framework):
        assert 2 <= len(ice.when_not_to_use) <= 3

    def test_relationships_complete(self, ice: Framework):
        assert "rice" in ice.relationships["similar_to"]
        assert "wsjf" in ice.relationships["similar_to"]

    def test_output_shape_typed(self, ice: Framework):
        assert ice.output_shape["type"] == "Score"

    def test_appears_in_load_all(self):
        from core.frameworks import load_all

        registry = load_all()
        assert "ice" in registry

    def test_not_d_scope(self, ice: Framework):
        assert ice.is_d_scope is False
