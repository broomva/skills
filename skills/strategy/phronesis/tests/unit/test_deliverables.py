"""Phase D.2-D.7 — six remaining deliverable templates.

Each template gets a fixture-driven render test plus a strict-undefined
test. Mirrors test_deliverable_maturity_report.py (D.1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from jinja2.exceptions import UndefinedError

from core.render import render
from core.types import (
    AdoptionMetric,
    BaselineSection,
    CapabilityCell,
    Citation,
    DataReadinessAssessment,
    Finding,
    IdeationSource,
    PilotDesign,
    RoadmapStep,
    Score,
    StrategicThesis,
    TenantContext,
    UseCase,
)

pytestmark = pytest.mark.unit


# ----------------------------------------------------------------------------
# Shared fixtures
# ----------------------------------------------------------------------------


@pytest.fixture
def cite() -> Citation:
    return Citation(kind="evidence", ref="i:coo:Q2", confidence="high")


@pytest.fixture
def tenant() -> TenantContext:
    return TenantContext(
        tenant_slug="tropico",
        name="Tropico Renovables",
        industry="energy-utilities",
        region="CO",
        revenue_band="<10M",
        headcount_band="50-500",
        sponsor="Catalina Vélez",
        sponsor_role="COO",
        engagement_scope="62 MW renewable portfolio",
        starts_at=datetime(2026, 5, 6, tzinfo=UTC),
        target_duration_weeks=10,
    )


@pytest.fixture
def thesis(cite: Citation) -> StrategicThesis:
    return StrategicThesis(
        economic_lever="Recover 4% CF on 62 MW",
        lever_kind="revenue",
        magnitude_estimate=Decimal("640000"),
        magnitude_basis="62 MW × 8760 h × 0.04 ΔCF × $79/MWh × 0.37",
        strategic_horizon="h1-now",
        decision_rights_owner="COO",
        measured_in="USD/yr",
        evidence=[cite],
    )


# ----------------------------------------------------------------------------
# D.2 — capability-heatmap
# ----------------------------------------------------------------------------


class TestCapabilityHeatmap:
    @pytest.fixture
    def context(self, tenant: TenantContext, cite: Citation):
        cells = [
            CapabilityCell(
                capability="Time-series ML pipeline",
                category="tooling",
                current_state="absent",
                target_state="defined",
                criticality="foundational",
                evidence=[cite],
            ),
            CapabilityCell(
                capability="Control-engineering team",
                category="talent",
                current_state="ad-hoc",
                target_state="managed",
                criticality="foundational",
                evidence=[cite],
            ),
            CapabilityCell(
                capability="ML model governance",
                category="governance",
                current_state="absent",
                target_state="defined",
                criticality="important",
                evidence=[cite],
            ),
        ]
        return {
            "tenant": tenant,
            "capabilities": cells,
            "generated_at": "2026-05-07",
        }

    def test_renders(self, context):
        out = render("capability-heatmap", context)
        assert "Capability Heatmap" in out
        assert "Tropico Renovables" in out

    def test_cells_in_table(self, context):
        out = render("capability-heatmap", context)
        assert "Time-series ML pipeline" in out
        assert "tooling" in out
        assert "absent" in out

    def test_foundational_gaps_highlighted(self, context):
        out = render("capability-heatmap", context)
        assert "Foundational gaps" in out
        # Two foundational + absent/ad-hoc cells present
        assert "Time-series ML pipeline" in out.split("Foundational gaps")[1]
        assert "Control-engineering team" in out.split("Foundational gaps")[1]

    def test_strict_undefined(self, context):
        bad = {**context}
        del bad["capabilities"]
        with pytest.raises(UndefinedError):
            render("capability-heatmap", bad)


# ----------------------------------------------------------------------------
# D.3 — use-case-dossier
# ----------------------------------------------------------------------------


def _make_uc(uc_id: str, source: IdeationSource, cite: Citation) -> UseCase:
    return UseCase(
        id=uc_id,
        problem=f"problem for {uc_id}",
        hypothesis=f"hypothesis for {uc_id}",
        solution_summary=f"solution for {uc_id}",
        expected_value=Decimal("420000"),
        cost_estimate=Decimal("180000"),
        cost_breakdown={"x": Decimal("180000")},
        data_required=["d"],
        capabilities_required=["c"],
        risks=[
            Finding(
                title="Vendor lock-in risk",
                body="Closed-source MPC libraries restrict ownership",
                severity="major",
                confidence="medium",
                evidence=[cite],
            )
        ],
        framework_lens=["rice"],
        score_impact=Score(
            dimension="impact",
            value=8.0,
            scale=(0.0, 10.0),
            rubric_ref="rice",
            rationale="r",
            evidence=[cite],
        ),
        score_effort=Score(
            dimension="effort",
            value=4.0,
            scale=(0.0, 10.0),
            rubric_ref="rice",
            rationale="r",
            evidence=[cite],
        ),
        ideation_source=source,
        data_readiness=DataReadinessAssessment(
            use_case_id=uc_id,
            data_dependencies=["d"],
            weakest_dependency_state="managed",
            readiness_band="pilot-ready",
            prep_phase_required=False,
        ),
        evidence=[cite],
    )


class TestUseCaseDossier:
    @pytest.fixture
    def context(self, tenant: TenantContext, thesis: StrategicThesis, cite: Citation):
        return {
            "tenant": tenant,
            "thesis": thesis,
            "use_cases": [
                _make_uc("uc-mpc-solar", IdeationSource.BUSINESS_PAIN, cite),
                _make_uc("uc-inflow-fcst", IdeationSource.DATA_OPPORTUNITY, cite),
            ],
            "generated_at": "2026-05-07",
        }

    def test_renders(self, context):
        out = render("use-case-dossier", context)
        assert "Use-Case Dossier" in out
        assert "Recover 4% CF" in out

    def test_summary_table(self, context):
        out = render("use-case-dossier", context)
        assert "uc-mpc-solar" in out
        assert "uc-inflow-fcst" in out
        assert "$420,000" in out
        assert "business-pain" in out

    def test_per_uc_detail(self, context):
        out = render("use-case-dossier", context)
        assert "Vendor lock-in risk" in out
        assert "Closed-source MPC libraries" in out

    def test_status_default_proposed(self, context):
        out = render("use-case-dossier", context)
        # status defaults to 'proposed' on construction
        assert "`proposed`" in out

    def test_strict_undefined(self, context):
        bad = {**context}
        del bad["use_cases"]
        with pytest.raises(UndefinedError):
            render("use-case-dossier", bad)


# ----------------------------------------------------------------------------
# D.4 — impact-effort-matrix
# ----------------------------------------------------------------------------


class TestImpactEffortMatrix:
    @pytest.fixture
    def context(self, tenant: TenantContext):
        return {
            "tenant": tenant,
            "frameworks_applied": ["rice", "ice"],
            "ranked": [
                {
                    "rank": 1,
                    "use_case_id": "uc-mpc-solar",
                    "rice_score": 14.9,
                    "impact": 8.5,
                    "effort": 4.0,
                    "ideation_source": "business-pain",
                    "year1_net": Decimal("240000"),
                },
                {
                    "rank": 2,
                    "use_case_id": "uc-inflow-fcst",
                    "rice_score": 8.4,
                    "impact": 6.0,
                    "effort": 5.0,
                    "ideation_source": "data-opportunity",
                    "year1_net": Decimal("35000"),
                },
                {
                    "rank": 3,
                    "use_case_id": "uc-ffr-grid",
                    "rice_score": 5.5,
                    "impact": 5.5,
                    "effort": 7.0,
                    "ideation_source": "regulatory-pressure",
                    "year1_net": Decimal("-110000"),
                },
            ],
            "top_n": 3,
            "generated_at": "2026-05-07",
        }

    def test_renders(self, context):
        out = render("impact-effort-matrix", context)
        assert "Impact-Effort Matrix" in out

    def test_ranked_list(self, context):
        out = render("impact-effort-matrix", context)
        assert "uc-mpc-solar" in out
        assert "14.9" in out
        # Top-3 section
        assert "Top-3 selected" in out

    def test_year1_net_formatted(self, context):
        out = render("impact-effort-matrix", context)
        assert "$240,000" in out

    def test_strict_undefined(self, context):
        bad = {**context}
        del bad["ranked"]
        with pytest.raises(UndefinedError):
            render("impact-effort-matrix", bad)


# ----------------------------------------------------------------------------
# D.5 — roi-model
# ----------------------------------------------------------------------------


class TestRoiModel:
    @pytest.fixture
    def context(self, tenant: TenantContext):
        from core.types import RoiCell

        cells = [
            RoiCell(
                use_case_id="uc-mpc-solar",
                year=1,
                revenue_impact=Decimal("420000"),
                cost_savings=Decimal("0"),
                investment=Decimal("180000"),
                one_time_cost=Decimal("126000"),
                recurring_cost=Decimal("54000"),
                net=Decimal("240000"),
                cumulative_net=Decimal("240000"),
                discount_rate=Decimal("0.14"),
                sensitivity_low=Decimal("144000"),
                sensitivity_high=Decimal("336000"),
                assumptions=["Bolsa price holds"],
            ),
        ]
        return {
            "tenant": tenant,
            "roi_cells": cells,
            "discount_rate": Decimal("0.14"),
            "total_revenue": Decimal("420000"),
            "total_investment": Decimal("180000"),
            "total_net": Decimal("240000"),
            "assumptions": ["Bolsa price holds at $79/MWh ±18%"],
            "generated_at": "2026-05-07",
        }

    def test_renders(self, context):
        out = render("roi-model", context)
        assert "ROI Model" in out
        assert "14.0%" in out  # discount_rate

    def test_cells_with_sensitivity(self, context):
        out = render("roi-model", context)
        assert "uc-mpc-solar" in out
        assert "$240,000" in out
        # sensitivity bands
        assert "$144,000" in out
        assert "$336,000" in out

    def test_assumptions_listed(self, context):
        out = render("roi-model", context)
        assert "Bolsa price holds at $79/MWh" in out

    def test_strict_undefined(self, context):
        bad = {**context}
        del bad["roi_cells"]
        with pytest.raises(UndefinedError):
            render("roi-model", bad)


# ----------------------------------------------------------------------------
# D.6 — innovation-roadmap
# ----------------------------------------------------------------------------


class TestInnovationRoadmap:
    @pytest.fixture
    def context(self, tenant: TenantContext, thesis: StrategicThesis):
        return {
            "tenant": tenant,
            "thesis": thesis,
            "frameworks_applied": ["three-horizons", "real-options"],
            "roadmap_steps": [
                RoadmapStep(
                    id="rs-h1-mpc",
                    title="MPC pilot",
                    horizon="h1-now",
                    quarter="2026-Q3",
                    related_use_cases=["uc-1"],
                    related_recommendations=["rec-1"],
                    dependencies=[],
                    owner="VP Ops",
                    success_gate="≥3% CF lift",
                ),
                RoadmapStep(
                    id="rs-h2-portfolio",
                    title="Portfolio rollout",
                    horizon="h2-next",
                    quarter="2026-Q4",
                    related_use_cases=["uc-1", "uc-2"],
                    related_recommendations=["rec-2"],
                    dependencies=[],
                    owner="VP Ops",
                    success_gate="Portfolio CF +3%",
                ),
                RoadmapStep(
                    id="rs-h3-grid",
                    title="FFR product",
                    horizon="h3-later",
                    quarter="2027-Q2",
                    related_use_cases=["uc-3"],
                    related_recommendations=["rec-3"],
                    dependencies=["XM FFR market live"],
                    owner="Commercial Director",
                    success_gate="FFR-qualified + first contract",
                ),
            ],
            "generated_at": "2026-05-07",
        }

    def test_renders(self, context):
        out = render("innovation-roadmap", context)
        assert "Innovation Roadmap" in out

    def test_three_horizons_sections(self, context):
        out = render("innovation-roadmap", context)
        assert "H1 — Now" in out
        assert "H2 — Next" in out
        assert "H3 — Later" in out

    def test_steps_under_correct_horizon(self, context):
        out = render("innovation-roadmap", context)
        h1_section = out.split("H1 — Now")[1].split("H2 — Next")[0]
        assert "rs-h1-mpc" in h1_section
        assert "rs-h2-portfolio" not in h1_section

    def test_strict_undefined(self, context):
        bad = {**context}
        del bad["roadmap_steps"]
        with pytest.raises(UndefinedError):
            render("innovation-roadmap", bad)


# ----------------------------------------------------------------------------
# D.7 — pilot-plan
# ----------------------------------------------------------------------------


class TestPilotPlan:
    @pytest.fixture
    def context(self, tenant: TenantContext, cite: Citation):
        adoption = AdoptionMetric(
            metric_name="Operations team accepts MPC setpoints",
            target_value=">=85% of intervals",
            measurement_method="SCADA override-flag log",
            owner="VP Operations",
        )
        baseline = BaselineSection(
            metric_name="Farm-1 capacity factor",
            baseline_value=Decimal("0.234"),
            baseline_window="2026-Q1 production",
            baseline_data_source="SCADA POI",
            baseline_measurement_date=datetime(2026, 4, 1, tzinfo=UTC),
            captured_by="VP Ops",
            evidence=[cite],
        )
        pilot = PilotDesign(
            use_case_id="uc-mpc-solar",
            hypothesis="MPC lifts Farm-1 CF from 23.4% to ≥24.1%",
            null_hypothesis="No CF lift at p<0.05",
            duration_weeks=16,
            cohort_definition="Farm-1 only (12 MW)",
            success_criteria=["Farm-1 CF ≥24.1%"],
            kill_criterion="Week-8 CF <23.5%",
            learning_objectives=["Cloud-nowcast horizon tradeoff"],
            risks=[
                Finding(
                    title="GOES-R outages",
                    body="Historical 0.8% outage rate",
                    severity="minor",
                    confidence="high",
                    evidence=[cite],
                )
            ],
            cost_estimate=Decimal("180000"),
            adoption_metric=adoption,
            baseline=[baseline],
            evidence=[cite],
        )
        return {
            "tenant": tenant,
            "pilot": pilot,
            "generated_at": "2026-05-07",
        }

    def test_renders(self, context):
        out = render("pilot-plan", context)
        assert "Pilot Plan" in out

    def test_hypothesis_and_kill_present(self, context):
        out = render("pilot-plan", context)
        assert "MPC lifts Farm-1 CF from 23.4% to ≥24.1%" in out
        assert "Week-8 CF <23.5%" in out

    def test_l4_adoption_metric_section(self, context):
        out = render("pilot-plan", context)
        assert "L4 — Adoption metric" in out
        assert "Operations team accepts MPC setpoints" in out
        assert "VP Operations" in out

    def test_l5_baseline_section(self, context):
        out = render("pilot-plan", context)
        # BRO-1035 — header now reads 'declared' (covers both incumbent +
        # greenfield) instead of 'captured' (which implied measurement only)
        assert "L5 — Baselines declared BEFORE pilot start" in out
        assert "Farm-1 capacity factor" in out
        assert "2026-04-01" in out

    def test_invariant_footer(self, context):
        out = render("pilot-plan", context)
        assert "L4 ✓" in out
        assert "L5 ✓" in out
        # BRO-1035 — footer now distinguishes greenfield vs incumbent counts
        assert "greenfield" in out and "incumbent" in out

    def test_greenfield_baseline_renders_distinctly(self, tenant: TenantContext, cite: Citation):
        """BRO-1035 — when a baseline has is_greenfield=True, render it as
        '[GREENFIELD] zero-state declared' instead of the numeric value."""
        from datetime import UTC, datetime
        from decimal import Decimal

        from core.types import AdoptionMetric, BaselineSection, Finding, PilotDesign

        adoption = AdoptionMetric(
            metric_name="External devs adopting inference-vllm",
            target_value=">=10 production deployments",
            measurement_method="GitHub deployment registry",
            owner="Founder/CEO",
        )
        greenfield_baseline = BaselineSection(
            metric_name="vLLM-backend tokens/sec on reference workload",
            baseline_value=Decimal("0"),
            baseline_window="2026-Q2 baseline (zero-state)",
            baseline_data_source="Pre-engagement assessment",
            baseline_measurement_date=datetime(2026, 5, 7, tzinfo=UTC),
            captured_by="Founder/CEO",
            evidence=[cite],
            is_greenfield=True,
        )
        pilot = PilotDesign(
            use_case_id="uc-vllm-backend",
            hypothesis="vLLM backend ships in 3 days",
            null_hypothesis="No deployments after public release",
            duration_weeks=20,
            cohort_definition="External agent-system builders",
            success_criteria=["≥10 external deployments by Q4"],
            kill_criterion="Week-12 zero deployments → kill",
            learning_objectives=["Validate trait shape generalizes to vLLM"],
            risks=[
                Finding(
                    title="Spec E shape generalizes poorly",
                    body="vLLM has paged-attention assumptions",
                    severity="major",
                    confidence="medium",
                    evidence=[cite],
                )
            ],
            cost_estimate=Decimal("60000"),
            adoption_metric=adoption,
            baseline=[greenfield_baseline],
            evidence=[cite],
        )
        context = {
            "tenant": tenant,
            "pilot": pilot,
            "generated_at": "2026-05-07",
        }
        out = render("pilot-plan", context)
        # The greenfield row substitutes the GREENFIELD marker for the value
        assert "**[GREENFIELD]** zero-state declared" in out
        # The greenfield-pilot pattern blockquote appears
        assert "Greenfield pilot" in out
        assert "1 of 1 baseline(s) declared zero-state" in out
        # Footer accounting reflects the split
        assert "1 greenfield, 0 incumbent" in out

    def test_strict_undefined(self, context):
        bad = {**context}
        del bad["pilot"]
        with pytest.raises(UndefinedError):
            render("pilot-plan", bad)
