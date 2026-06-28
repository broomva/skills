"""CHAOSS framework — Phase-1 maturity framework for OSS-building tenants.

Engagement-driven addition (BRO-1033). Mirrors test_framework_mit_cisr_digital.py.
"""

from __future__ import annotations

import pytest

from core.frameworks import FRAMEWORKS_ROOT, Framework, load_framework

pytestmark = pytest.mark.unit


@pytest.fixture
def fw() -> Framework:
    return load_framework(FRAMEWORKS_ROOT / "maturity" / "chaoss.yaml")


class TestChaossFramework:
    def test_loads_and_validates(self, fw: Framework):
        assert fw.id == "chaoss"
        assert fw.category == "maturity"
        assert "Linux Foundation" in fw.source_firm
        assert fw.source_year == 2017

    def test_when_to_use_count_in_range(self, fw: Framework):
        assert 3 <= len(fw.when_to_use) <= 5

    def test_when_not_to_use_count_in_range(self, fw: Framework):
        assert 2 <= len(fw.when_not_to_use) <= 3

    def test_relationships_complete(self, fw: Framework):
        # Cross-references the other two maturity frameworks (similar_to)
        # and Wardley + real-options (use_with — co-applied for tech tenants)
        assert "mit-cisr-digital" in fw.relationships["similar_to"]
        assert "gartner-ai" in fw.relationships["similar_to"]
        assert "wardley-mapping" in fw.relationships["use_with"]
        assert "real-options" in fw.relationships["use_with"]
        assert "maturity-report-deliverable" in fw.relationships["upstream_from"]

    def test_output_shape_typed(self, fw: Framework):
        assert fw.output_shape["type"] == "MaturityDimension"

    def test_appears_in_load_all(self):
        from core.frameworks import load_all

        assert "chaoss" in load_all()

    def test_not_d_scope(self, fw: Framework):
        assert fw.is_d_scope is False

    def test_dimensions_oss_native(self, fw: Framework):
        # The 5 dimensions are the marker that this framework measures the
        # right thing for OSS-building tenants vs the wrong-axis MIT CISR
        # measurement that surfaced the gap in the Broomva Silicon engagement.
        expected = {
            "contributor-diversity",
            "release-cadence",
            "code-review-depth",
            "downstream-adoption",
            "governance-maturity",
        }
        assert set(fw.dimensions) == expected
