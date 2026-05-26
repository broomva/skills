"""Stage 4 Prioritization — gate: ≥1 use case prioritized."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.engagement import Engagement, EngagementJournal
from core.types import EventKind, RoiCell, TenantContext
from stages.prioritize import PrioritizationStage

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
    return Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))


@pytest.fixture
def roi() -> RoiCell:
    return RoiCell(
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


class TestPrioritizationStage:
    def test_prioritize_use_case_emits_event(self, engagement: Engagement, roi: RoiCell):
        stage = PrioritizationStage()
        stage.run(engagement)
        eid = stage.prioritize_use_case(
            engagement,
            use_case_id="uc-1",
            rice_score=14.9,
            roi_cell=roi,
            rank=1,
        )
        assert isinstance(eid, str) and len(eid) == 26
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.USE_CASE_PRIORITIZED in kinds

    def test_render_impact_effort_matrix_emits_deliverable(self, engagement: Engagement):
        stage = PrioritizationStage()
        stage.run(engagement)
        stage.render_impact_effort_matrix(engagement, "/tmp/iem.md")
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.DELIVERABLE_RENDERED in kinds

    def test_review_blocks_without_prioritized_use_case(self, engagement: Engagement):
        stage = PrioritizationStage()
        stage.run(engagement)
        with pytest.raises(ValueError, match="at least one use case must be prioritized"):
            stage.request_review(engagement, "s")

    def test_review_passes_after_prioritization(self, engagement: Engagement, roi: RoiCell):
        stage = PrioritizationStage()
        stage.run(engagement)
        stage.prioritize_use_case(
            engagement,
            use_case_id="uc-1",
            rice_score=14.9,
            roi_cell=roi,
            rank=1,
        )
        stage.request_review(engagement, "Top-3 selected")
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.STAGE_REVIEW_REQUESTED in kinds

    def test_compute_year1_net_helper(self):
        net = PrioritizationStage.compute_year1_net(Decimal("420000"), Decimal("180000"))
        assert net == Decimal("240000")

    def test_class_vars_correct(self):
        assert PrioritizationStage.SLUG == "prioritize"
        assert PrioritizationStage.NEXT_STAGE == "roadmap"
