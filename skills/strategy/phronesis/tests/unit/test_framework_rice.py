"""RICE framework — Phase-1 prioritization. Worked example for B.2-B.14.

Each new Phase-1 framework gets a sibling test file:
tests/unit/test_framework_<slug>.py with the same five tests:
  1. loads_and_validates
  2. when_to_use_count_in_range
  3. when_not_to_use_count_in_range
  4. relationships_complete
  5. output_shape_typed
"""

from __future__ import annotations

import pytest

from core.frameworks import FRAMEWORKS_ROOT, Framework, load_framework

pytestmark = pytest.mark.unit


@pytest.fixture
def rice() -> Framework:
    return load_framework(FRAMEWORKS_ROOT / "prioritization" / "rice.yaml")


class TestRiceFramework:
    def test_loads_and_validates(self, rice: Framework):
        assert rice.id == "rice"
        assert rice.category == "prioritization"
        assert rice.source_firm == "Intercom"
        assert rice.source_year == 2016
        assert rice.scoring_rubric["formula"] == "(reach × impact × confidence) / effort"
        assert rice.scoring_rubric["output_unit"] == "rice-score"

    def test_when_to_use_count_in_range(self, rice: Framework):
        # Schema requires 3-5 conditions
        assert 3 <= len(rice.when_to_use) <= 5

    def test_when_not_to_use_count_in_range(self, rice: Framework):
        assert 2 <= len(rice.when_not_to_use) <= 3

    def test_relationships_complete(self, rice: Framework):
        # Phase-1 frameworks should populate at least similar_to + use_with —
        # those drive framework_selector cross-suggestion behavior in B.16-B.20.
        assert len(rice.relationships.get("similar_to", [])) >= 1
        assert len(rice.relationships.get("use_with", [])) >= 1

    def test_output_shape_typed(self, rice: Framework):
        # Output shape must reference one of the 8 typed primitives.
        assert rice.output_shape["type"] == "Score"

    def test_rice_appears_in_load_all(self):
        from core.frameworks import load_all

        registry = load_all()
        assert "rice" in registry
        assert registry["rice"].name == "RICE Scoring"

    def test_rice_is_not_d_scope(self, rice: Framework):
        assert rice.is_d_scope is False
