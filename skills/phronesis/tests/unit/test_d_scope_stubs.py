"""D-scope framework stubs — Phase 2 placeholders. B.15 acceptance.

Stubs satisfy _schema.yaml so framework_selector + relationship-resolution
can refer to them without requiring full Phase-2 implementations.
"""

from __future__ import annotations

import pytest

from core.frameworks import load_all

pytestmark = pytest.mark.unit


_EXPECTED_D_SCOPE_SLUGS = {
    "where-to-play-how-to-win",
    "five-forces",
    "mckinsey-7s",
    "forrester-data",
    "lean-canvas",
    "business-model-canvas",
    "cost-of-delay",
    "owner-earnings",
    "ms-responsible-ai",
    "google-pair",
    "kotter-8-steps",
    "adkar",
    "mckinsey-influence",
}


class TestDScopeStubs:
    def test_all_13_stubs_load(self):
        registry = load_all()
        d_scope_count = sum(1 for f in registry.values() if f.is_d_scope)
        assert d_scope_count == 13

    def test_d_scope_slugs_match_expected(self):
        registry = load_all()
        actual = {f.id for f in registry.values() if f.is_d_scope}
        assert actual == _EXPECTED_D_SCOPE_SLUGS

    def test_d_scope_stubs_marked_correctly(self):
        registry = load_all()
        for slug in _EXPECTED_D_SCOPE_SLUGS:
            fw = registry[slug]
            assert fw.is_d_scope is True, f"{slug} should be is_d_scope=true"
            assert "DEFERRED" in fw.purpose

    def test_phase_1_frameworks_not_d_scope(self):
        registry = load_all()
        phase_1_slugs = {
            "rice",
            "ice",
            "wsjf",
            "three-horizons",
            "wardley-mapping",
            "mit-cisr-digital",
            "gartner-ai",
            "chaoss",  # BRO-1033 — Phase 2 addition for OSS-building tenants
            "jobs-to-be-done",
            "value-prop-canvas",
            "unit-economics",
            "npv-dcf",
            "real-options",
            "quantumblack-ml",
            "andrew-ng-pipeline",
        }
        for slug in phase_1_slugs:
            fw = registry[slug]
            assert fw.is_d_scope is False, f"{slug} should not be d_scope"

    def test_total_framework_count_is_28(self):
        registry = load_all()
        # 15 Phase-1 (14 original + chaoss) + 13 D-scope
        assert len(registry) == 28
