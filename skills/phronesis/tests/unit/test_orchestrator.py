"""Render orchestrator tests — render_all + render_with_gate."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from core.engagement import Engagement, EngagementJournal
from core.orchestrator import (
    DELIVERABLE_SLUGS,
    build_roi_totals,
    render_all,
    render_with_gate,
)
from core.types import (
    AdoptionMetric,
    BaselineSection,
    CapabilityCell,
    Citation,
    DataReadinessAssessment,
    EventKind,
    Finding,
    IdeationSource,
    MaturityDimension,
    PilotDesign,
    RoadmapStep,
    RoiCell,
    Score,
    StrategicThesis,
    TenantContext,
    UseCase,
)

pytestmark = pytest.mark.unit


# ----------------------------------------------------------------------------
# Fixtures — minimal-but-clean Tropico engagement that lints to zero errors
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


@pytest.fixture
def clean_engagement(tenant: TenantContext, thesis: StrategicThesis) -> Engagement:
    """Engagement that lints to zero errors — for testing render_with_gate
    happy path."""
    eng = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
    eng.emit(
        EventKind.STRATEGIC_THESIS_DECLARED,
        "intake",
        {
            "thesis_id": thesis.thesis_id,
            "economic_lever": thesis.economic_lever,
            "lever_kind": thesis.lever_kind,
            "magnitude_estimate": str(thesis.magnitude_estimate),
            "horizon": thesis.strategic_horizon,
            "owner": thesis.decision_rights_owner,
        },
    )
    eng.emit(
        EventKind.INTAKE_COMPLETED,
        "intake",
        {"thesis_id": thesis.thesis_id, "frameworks_selected": ["rice"]},
    )
    return eng


@pytest.fixture
def broken_engagement(tenant: TenantContext) -> Engagement:
    """Engagement that fails L1 — INTAKE_COMPLETED with no thesis."""
    eng = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
    eng.emit(
        EventKind.INTAKE_COMPLETED,
        "intake",
        {"thesis_id": "", "frameworks_selected": []},
    )
    return eng


def _full_context(
    tenant: TenantContext, thesis: StrategicThesis, cite: Citation
) -> dict[str, object]:
    """Complete extras dict that satisfies all 7 templates' strict-undefined."""
    bench = Citation(kind="evidence", ref="bench:peer", confidence="medium")
    dim = MaturityDimension(
        name="Operational digitization",
        framework_ref="framework:gartner-ai",
        current_score=Score(
            dimension="ops",
            value=2.0,
            scale=(1.0, 5.0),
            rubric_ref="cisr",
            rationale="Open-loop",
            evidence=[cite],
        ),
        target_score=Score(
            dimension="ops",
            value=4.0,
            scale=(1.0, 5.0),
            rubric_ref="cisr",
            rationale="MPC-led",
            evidence=[bench],
        ),
        gap_summary="Open-loop dispatch",
        key_actions=["Stand up MPC"],
        evidence=[cite],
    )
    cell = CapabilityCell(
        capability="ML pipeline",
        category="tooling",
        current_state="absent",
        target_state="defined",
        criticality="foundational",
        evidence=[cite],
    )
    uc = UseCase(
        id="uc-1",
        problem="p",
        hypothesis="h",
        solution_summary="s",
        expected_value=Decimal("420000"),
        cost_estimate=Decimal("180000"),
        cost_breakdown={"x": Decimal("180000")},
        data_required=["d"],
        capabilities_required=["c"],
        risks=[],
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
        ideation_source=IdeationSource.BUSINESS_PAIN,
        data_readiness=DataReadinessAssessment(
            use_case_id="uc-1",
            data_dependencies=["d"],
            weakest_dependency_state="managed",
            readiness_band="pilot-ready",
            prep_phase_required=False,
        ),
        evidence=[cite],
    )
    roi = RoiCell(
        use_case_id="uc-1",
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
    )
    step = RoadmapStep(
        id="rs-1",
        title="MPC pilot",
        horizon="h1-now",
        quarter="2026-Q3",
        related_use_cases=["uc-1"],
        related_recommendations=["rec-1"],
        dependencies=[],
        owner="VP Ops",
        success_gate="≥3% CF lift",
    )
    adoption = AdoptionMetric(
        metric_name="MPC adoption",
        target_value=">=85%",
        measurement_method="SCADA log",
        owner="VP Ops",
    )
    baseline = BaselineSection(
        metric_name="Farm-1 CF",
        baseline_value=Decimal("0.234"),
        baseline_window="Q1",
        baseline_data_source="SCADA",
        baseline_measurement_date=datetime(2026, 4, 1, tzinfo=UTC),
        captured_by="VP Ops",
        evidence=[cite],
    )
    pilot = PilotDesign(
        use_case_id="uc-1",
        hypothesis="MPC lifts CF",
        null_hypothesis="No lift",
        duration_weeks=16,
        cohort_definition="Farm-1",
        success_criteria=["CF >=24.1%"],
        kill_criterion="<23.5%",
        learning_objectives=["validate"],
        risks=[
            Finding(
                title="risk",
                body="b",
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
        "thesis": thesis,
        "dimensions": [dim],
        "capabilities": [cell],
        "use_cases": [uc],
        "frameworks_applied": ["rice"],
        "ranked": [
            {
                "rank": 1,
                "use_case_id": "uc-1",
                "rice_score": 14.9,
                "impact": 8.0,
                "effort": 4.0,
                "ideation_source": "business-pain",
                "year1_net": Decimal("240000"),
            }
        ],
        "top_n": 1,
        "roi_cells": [roi],
        "discount_rate": Decimal("0.14"),
        **build_roi_totals([roi]),
        "assumptions": ["Bolsa price holds"],
        "roadmap_steps": [step],
        "pilot": pilot,
        "generated_at": "2026-05-07",
    }


class TestRenderAll:
    def test_all_7_deliverable_paths_returned(
        self,
        clean_engagement: Engagement,
        thesis: StrategicThesis,
        cite: Citation,
        tmp_path: Path,
        tenant: TenantContext,
    ):
        ctx = _full_context(tenant, thesis, cite)
        paths, lint = render_all(clean_engagement, tmp_path, extra_context=ctx)
        assert set(paths.keys()) == set(DELIVERABLE_SLUGS)
        assert all(p.exists() for p in paths.values())

    def test_files_written_to_output_dir(
        self,
        clean_engagement: Engagement,
        thesis: StrategicThesis,
        cite: Citation,
        tmp_path: Path,
        tenant: TenantContext,
    ):
        ctx = _full_context(tenant, thesis, cite)
        render_all(clean_engagement, tmp_path, extra_context=ctx)
        for slug in DELIVERABLE_SLUGS:
            path = tmp_path / f"{slug}.md"
            assert path.exists()
            content = path.read_text()
            assert content  # non-empty

    def test_write_false_preview_mode(
        self,
        clean_engagement: Engagement,
        thesis: StrategicThesis,
        cite: Citation,
        tmp_path: Path,
        tenant: TenantContext,
    ):
        ctx = _full_context(tenant, thesis, cite)
        paths, _ = render_all(clean_engagement, tmp_path, extra_context=ctx, write=False)
        for path in paths.values():
            assert not path.exists()

    def test_render_all_returns_lint_result(
        self,
        clean_engagement: Engagement,
        thesis: StrategicThesis,
        cite: Citation,
        tmp_path: Path,
        tenant: TenantContext,
    ):
        ctx = _full_context(tenant, thesis, cite)
        _, lint = render_all(clean_engagement, tmp_path, extra_context=ctx)
        assert not lint.has_errors


class TestRenderWithGate:
    def test_clean_engagement_writes_all_files(
        self,
        clean_engagement: Engagement,
        thesis: StrategicThesis,
        cite: Citation,
        tmp_path: Path,
        tenant: TenantContext,
    ):
        ctx = _full_context(tenant, thesis, cite)
        paths, lint = render_with_gate(clean_engagement, tmp_path, extra_context=ctx)
        assert set(paths.keys()) == set(DELIVERABLE_SLUGS)
        assert all(p.exists() for p in paths.values())
        assert not lint.has_errors

    def test_broken_engagement_writes_nothing(
        self,
        broken_engagement: Engagement,
        thesis: StrategicThesis,
        cite: Citation,
        tmp_path: Path,
        tenant: TenantContext,
    ):
        ctx = _full_context(tenant, thesis, cite)
        paths, lint = render_with_gate(broken_engagement, tmp_path, extra_context=ctx)
        assert paths == {}
        assert lint.has_errors
        # Confirm no markdown files leaked into the output dir
        assert list(tmp_path.glob("*.md")) == []


class TestBuildRoiTotals:
    def test_empty_returns_zero(self):
        totals = build_roi_totals([])
        assert totals == {
            "total_revenue": Decimal("0"),
            "total_investment": Decimal("0"),
            "total_net": Decimal("0"),
        }

    def test_single_cell(self):
        cell = RoiCell(
            use_case_id="uc-1",
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
            assumptions=[],
        )
        totals = build_roi_totals([cell])
        assert totals["total_revenue"] == Decimal("420000")
        assert totals["total_net"] == Decimal("240000")
