"""Stage 5 Roadmap — gates: ≥1 step + ≥1 baseline (L5); pilot can't start
without captured baseline (no retroactive baselines)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.engagement import Engagement, EngagementJournal
from core.types import (
    AdoptionMetric,
    BaselineSection,
    Citation,
    EventKind,
    Finding,
    PilotDesign,
    RoadmapStep,
    TenantContext,
)
from stages.roadmap import RoadmapStage

pytestmark = pytest.mark.unit


@pytest.fixture
def tenant() -> TenantContext:
    return TenantContext(
        tenant_slug="acme",
        name="Acme",
        industry="banking",
        region="CO",
        revenue_band="100M-1B",
        headcount_band="500-5000",
        sponsor="x",
        sponsor_role="CDO",
        engagement_scope="s",
        starts_at=datetime(2026, 5, 6, tzinfo=UTC),
        target_duration_weeks=8,
    )


@pytest.fixture
def engagement(tenant: TenantContext) -> Engagement:
    e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
    # Seed thesis_id so conclude() doesn't trip its own guard
    e.emit(
        EventKind.STRATEGIC_THESIS_DECLARED,
        "intake",
        {
            "thesis_id": "01HZ000",
            "economic_lever": "x",
            "lever_kind": "cost",
            "magnitude_estimate": "1",
            "horizon": "h1-now",
            "owner": "x",
        },
    )
    return e


@pytest.fixture
def step() -> RoadmapStep:
    return RoadmapStep(
        id="rs-h1-pilot",
        title="Tier-1 deflection pilot",
        horizon="h1-now",
        quarter="2026-Q3",
        related_use_cases=["uc-1"],
        related_recommendations=["rec-1"],
        dependencies=[],
        owner="VP Operations",
        success_gate=">=35% deflection sustained 4 weeks",
    )


@pytest.fixture
def baseline() -> BaselineSection:
    cite = Citation(kind="evidence", ref="data:tickets:Q1", confidence="high")
    return BaselineSection(
        metric_name="Tier-1 ticket volume",
        baseline_value=Decimal("11700"),
        baseline_window="2026-Q1 production",
        baseline_data_source="Ticketing audit log",
        baseline_measurement_date=datetime(2026, 4, 1, tzinfo=UTC),
        captured_by="VP Ops",
        evidence=[cite],
    )


@pytest.fixture
def adoption() -> AdoptionMetric:
    return AdoptionMetric(
        metric_name="Reps using AI assist",
        target_value=">=85% by week 12",
        measurement_method="UI telemetry",
        owner="Head of CS",
    )


@pytest.fixture
def pilot(adoption: AdoptionMetric, baseline: BaselineSection) -> PilotDesign:
    cite = Citation(kind="evidence", ref="i:cdo:Q2", confidence="high")
    return PilotDesign(
        use_case_id="uc-1",
        hypothesis="Spanish-LLM deflection lifts efficiency 30%+",
        null_hypothesis="No significant deflection lift at p<0.05",
        duration_weeks=8,
        cohort_definition="Internal CS reps",
        success_criteria=[">=35% deflection by week 8"],
        kill_criterion="<15% deflection by week 4",
        learning_objectives=["Validate deflection rate"],
        risks=[
            Finding(
                title="Adoption risk",
                body="Reps may not use the assist surface",
                severity="major",
                confidence="medium",
                evidence=[cite],
            )
        ],
        cost_estimate=Decimal("80000"),
        adoption_metric=adoption,
        baseline=[baseline],
        evidence=[cite],
    )


class TestRoadmapStage:
    def test_propose_step_emits_event(self, engagement: Engagement, step: RoadmapStep):
        stage = RoadmapStage()
        stage.run(engagement)
        stage.propose_roadmap_step(engagement, step)
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.ROADMAP_STEP_PROPOSED in kinds

    def test_capture_baseline_emits_event(self, engagement: Engagement, baseline: BaselineSection):
        stage = RoadmapStage()
        stage.run(engagement)
        stage.capture_baseline(engagement, baseline)
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.BASELINE_CAPTURED in kinds
        assert "Tier-1 ticket volume" in engagement.state().baselines_captured

    def test_design_pilot_blocks_without_captured_baseline_L5(
        self, engagement: Engagement, pilot: PilotDesign
    ):
        """L5: cannot start pilot without prior BASELINE_CAPTURED for each metric."""
        stage = RoadmapStage()
        stage.run(engagement)
        with pytest.raises(ValueError, match="L5 BASELINE_REQUIRED"):
            stage.design_pilot(engagement, pilot)

    def test_design_pilot_passes_after_baseline_captured(
        self,
        engagement: Engagement,
        pilot: PilotDesign,
        baseline: BaselineSection,
    ):
        stage = RoadmapStage()
        stage.run(engagement)
        stage.capture_baseline(engagement, baseline)
        eid = stage.design_pilot(engagement, pilot)
        assert isinstance(eid, str)
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.PILOT_STARTED in kinds

    def test_render_deliverables(self, engagement: Engagement):
        stage = RoadmapStage()
        stage.run(engagement)
        stage.render_deliverables(
            engagement,
            slugs=["innovation-roadmap", "pilot-plan"],
            output_dir="/tmp",
        )
        rendered = engagement.state().deliverables_rendered
        assert "innovation-roadmap" in rendered
        assert "pilot-plan" in rendered

    def test_conclude_emits_terminal_event(
        self,
        engagement: Engagement,
        step: RoadmapStep,
        baseline: BaselineSection,
    ):
        stage = RoadmapStage()
        stage.run(engagement)
        stage.propose_roadmap_step(engagement, step)
        stage.capture_baseline(engagement, baseline)
        stage.conclude(
            engagement,
            top_pilot="uc-1",
            deliverable_slugs=["innovation-roadmap"],
        )
        assert engagement.state().is_concluded is True

    def test_conclude_blocks_without_thesis(self, tenant: TenantContext):
        e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        stage = RoadmapStage()
        with pytest.raises(ValueError, match="no StrategicThesis"):
            stage.conclude(e, top_pilot="x", deliverable_slugs=[])

    def test_review_blocks_without_step(self, engagement: Engagement):
        stage = RoadmapStage()
        stage.run(engagement)
        with pytest.raises(ValueError, match="at least one RoadmapStep"):
            stage.request_review(engagement, "s")

    def test_review_blocks_without_baseline_L5(self, engagement: Engagement, step: RoadmapStep):
        stage = RoadmapStage()
        stage.run(engagement)
        stage.propose_roadmap_step(engagement, step)
        with pytest.raises(ValueError, match="L5 BASELINE_REQUIRED"):
            stage.request_review(engagement, "s")

    def test_review_passes_with_step_and_baseline(
        self,
        engagement: Engagement,
        step: RoadmapStep,
        baseline: BaselineSection,
    ):
        stage = RoadmapStage()
        stage.run(engagement)
        stage.propose_roadmap_step(engagement, step)
        stage.capture_baseline(engagement, baseline)
        stage.request_review(engagement, "Roadmap + baseline ready for sign-off")
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.STAGE_REVIEW_REQUESTED in kinds

    def test_class_vars_correct(self):
        assert RoadmapStage.SLUG == "roadmap"
        assert RoadmapStage.NEXT_STAGE is None  # terminal
