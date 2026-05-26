"""framework_selector — propose 2-4 frameworks given engagement context.

P7 enforcement: caps at 5 active. Each pick carries rationale. D-scope
frameworks are excluded.
"""

from __future__ import annotations

import pytest

from core.frameworks import load_all
from core.selector import propose_frameworks
from core.types import FrameworkSelection

pytestmark = pytest.mark.unit


class TestProposeFrameworks:
    def test_returns_2_to_4_frameworks_default_cap(self):
        picks = propose_frameworks(
            industry="banking",
            maturity_band="defined",
            scope_keywords=["maturity assessment", "use case prioritization"],
        )
        assert 2 <= len(picks) <= 4
        assert all(isinstance(p, FrameworkSelection) for p in picks)

    def test_capped_at_5_even_with_max_keywords(self):
        # Even passing every category keyword + cap=10, P7 limits to 5.
        picks = propose_frameworks(
            industry="banking",
            maturity_band="defined",
            scope_keywords=["maturity", "ideation", "prioritization", "roi", "roadmap", "ai pilot"],
            cap=10,
        )
        assert len(picks) <= 5

    def test_each_pick_carries_rationale(self):
        picks = propose_frameworks(
            industry="banking",
            maturity_band="defined",
            scope_keywords=["maturity assessment"],
        )
        for p in picks:
            assert p.rationale and len(p.rationale) > 30
            assert p.selected_at_stage in ("scan", "ideate", "prioritize", "roadmap")
            assert p.selected_by == "phronesis-selector-v1"

    def test_picks_have_unique_framework_refs(self):
        picks = propose_frameworks(
            industry="banking",
            maturity_band="defined",
            scope_keywords=["maturity", "ideation", "prioritization", "roi"],
        )
        refs = [p.framework_ref for p in picks]
        assert len(set(refs)) == len(refs)


class TestIndustrySpecificPreferences:
    def test_banking_picks_mit_cisr_digital(self):
        picks = propose_frameworks(
            industry="banking",
            maturity_band="defined",
            scope_keywords=["maturity assessment"],
        )
        refs = [p.framework_ref for p in picks]
        assert "framework:mit-cisr-digital" in refs

    def test_energy_utilities_picks_real_options_and_wardley(self):
        picks = propose_frameworks(
            industry="energy-utilities",
            maturity_band="defined",
            scope_keywords=["roi modeling", "roadmap"],
            cap=5,
        )
        refs = [p.framework_ref for p in picks]
        assert "framework:real-options" in refs
        assert "framework:wardley-mapping" in refs

    def test_unknown_industry_falls_back_to_defaults(self):
        # No 'retail' in _INDUSTRY_PREFERENCES — should still produce picks.
        picks = propose_frameworks(
            industry="retail",
            maturity_band="ad-hoc",
            scope_keywords=["maturity assessment", "ideation"],
        )
        assert len(picks) >= 2

    def test_tech_picks_chaoss_for_maturity(self):
        # BRO-1032 — tech industry must pick CHAOSS for maturity assessment,
        # not the default mit-cisr-digital. CHAOSS measures OSS-project
        # health (the right axis); MIT CISR measures enterprise digital
        # maturity (the wrong axis for AI-building tenants).
        picks = propose_frameworks(
            industry="tech",
            maturity_band="defined",
            scope_keywords=["maturity assessment"],
        )
        refs = [p.framework_ref for p in picks]
        assert "framework:chaoss" in refs
        assert "framework:mit-cisr-digital" not in refs

    def test_tech_picks_wardley_and_real_options(self):
        # BRO-1032 — Wardley + real-options are the strategic-positioning
        # frameworks that surfaced when Broomva Silicon ran without them.
        picks = propose_frameworks(
            industry="tech",
            maturity_band="defined",
            scope_keywords=["roadmap", "roi modeling"],
            cap=5,
        )
        refs = [p.framework_ref for p in picks]
        assert "framework:wardley-mapping" in refs
        assert "framework:real-options" in refs


class TestDScopeExclusion:
    def test_d_scope_frameworks_excluded(self):
        """The selector must never propose a D-scope framework."""
        registry = load_all()
        d_scope_slugs = {f.id for f in registry.values() if f.is_d_scope}
        # Try every industry × every keyword combo; assert no D-scope leaks.
        for industry in [
            "banking",
            "energy-utilities",
            "fin-services",
            "insurance",
            "construction",
            "tech",
            "retail",
            "other",
        ]:
            picks = propose_frameworks(
                industry=industry,
                maturity_band="defined",
                scope_keywords=[
                    "maturity",
                    "ideation",
                    "prioritization",
                    "roi",
                    "roadmap",
                    "ai pilot",
                ],
                cap=5,
            )
            for p in picks:
                slug = p.framework_ref.removeprefix("framework:")
                assert slug not in d_scope_slugs, (
                    f"D-scope framework {slug} leaked through selector for industry={industry}"
                )


class TestDefaultCoverage:
    def test_minimal_scope_still_picks_maturity_and_prioritization(self):
        # Even with empty scope_keywords, defaults provide maturity +
        # prioritization coverage.
        picks = propose_frameworks(
            industry="banking",
            maturity_band="defined",
            scope_keywords=[],
        )
        categories = {
            load_all()[p.framework_ref.removeprefix("framework:")].category for p in picks
        }
        assert "maturity" in categories
        assert "prioritization" in categories
