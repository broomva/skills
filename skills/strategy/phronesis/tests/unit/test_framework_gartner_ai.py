"""Gartner AI Maturity framework — Phase-1 B.7 instantiation."""

from __future__ import annotations

import pytest

from core.frameworks import FRAMEWORKS_ROOT, Framework, load_framework

pytestmark = pytest.mark.unit


@pytest.fixture
def fw() -> Framework:
    return load_framework(FRAMEWORKS_ROOT / "maturity" / "gartner-ai.yaml")


class TestGartnerAiFramework:
    def test_loads_and_validates(self, fw: Framework):
        assert fw.id == "gartner-ai"
        assert fw.category == "maturity"
        assert fw.source_firm == "Gartner"
        assert fw.source_year == 2024

    def test_when_to_use_count_in_range(self, fw: Framework):
        assert 3 <= len(fw.when_to_use) <= 5

    def test_when_not_to_use_count_in_range(self, fw: Framework):
        assert 2 <= len(fw.when_not_to_use) <= 3

    def test_relationships_complete(self, fw: Framework):
        assert "mit-cisr-digital" in fw.relationships["similar_to"]
        assert "quantumblack-ml" in fw.relationships["use_with"]

    def test_output_shape_typed(self, fw: Framework):
        assert fw.output_shape["type"] == "MaturityDimension"

    def test_appears_in_load_all(self):
        from core.frameworks import load_all

        assert "gartner-ai" in load_all()

    def test_not_d_scope(self, fw: Framework):
        assert fw.is_d_scope is False
