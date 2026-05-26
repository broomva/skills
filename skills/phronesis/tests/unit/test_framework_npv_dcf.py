"""NPV/DCF framework — Phase-1 B.11 instantiation."""

from __future__ import annotations

import pytest

from core.frameworks import FRAMEWORKS_ROOT, Framework, load_framework

pytestmark = pytest.mark.unit


@pytest.fixture
def fw() -> Framework:
    return load_framework(FRAMEWORKS_ROOT / "roi" / "npv-dcf.yaml")


class TestNpvDcfFramework:
    def test_loads_and_validates(self, fw: Framework):
        assert fw.id == "npv-dcf"
        assert fw.category == "roi"
        assert "Modigliani-Miller" in fw.source_citation

    def test_when_to_use_count_in_range(self, fw: Framework):
        assert 3 <= len(fw.when_to_use) <= 5

    def test_when_not_to_use_count_in_range(self, fw: Framework):
        assert 2 <= len(fw.when_not_to_use) <= 3

    def test_relationships_complete(self, fw: Framework):
        assert "real-options" in fw.relationships["use_with"]
        assert "roi-model-deliverable" in fw.relationships["upstream_from"]

    def test_output_shape_typed(self, fw: Framework):
        assert fw.output_shape["type"] == "RoiCell"

    def test_appears_in_load_all(self):
        from core.frameworks import load_all

        assert "npv-dcf" in load_all()

    def test_not_d_scope(self, fw: Framework):
        assert fw.is_d_scope is False
