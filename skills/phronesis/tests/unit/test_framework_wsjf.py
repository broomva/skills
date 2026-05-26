"""WSJF framework — Phase-1 B.3 instantiation. Mirrors test_framework_rice.py."""

from __future__ import annotations

import pytest

from core.frameworks import FRAMEWORKS_ROOT, Framework, load_framework

pytestmark = pytest.mark.unit


@pytest.fixture
def wsjf() -> Framework:
    return load_framework(FRAMEWORKS_ROOT / "prioritization" / "wsjf.yaml")


class TestWsjfFramework:
    def test_loads_and_validates(self, wsjf: Framework):
        assert wsjf.id == "wsjf"
        assert wsjf.category == "prioritization"
        assert "Reinertsen" in wsjf.source_citation
        assert (
            "cost_of_delay" in wsjf.scoring_rubric["formula"].lower()
            or "user_business_value" in wsjf.scoring_rubric["formula"]
        )

    def test_when_to_use_count_in_range(self, wsjf: Framework):
        assert 3 <= len(wsjf.when_to_use) <= 5

    def test_when_not_to_use_count_in_range(self, wsjf: Framework):
        assert 2 <= len(wsjf.when_not_to_use) <= 3

    def test_relationships_reference_real_slugs(self, wsjf: Framework):
        # Cross-check that relationship targets exist in our roadmap
        # (Phase-1 + D-scope known slugs).
        known_slugs = {
            "rice",
            "ice",
            "wsjf",
            "cost-of-delay",
            "real-options",
            "jobs-to-be-done",
            "value-prop-canvas",
            "impact-effort-matrix-deliverable",
        }
        for rel in wsjf.relationships.values():
            for target in rel:
                assert target in known_slugs, f"Relationship target {target!r} not in known slugs"

    def test_output_shape_typed(self, wsjf: Framework):
        assert wsjf.output_shape["type"] == "Score"

    def test_appears_in_load_all(self):
        from core.frameworks import load_all

        registry = load_all()
        assert "wsjf" in registry

    def test_not_d_scope(self, wsjf: Framework):
        assert wsjf.is_d_scope is False
