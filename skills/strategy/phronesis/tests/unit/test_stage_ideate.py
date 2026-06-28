"""Stage 3 Ideation — L2 gate: diversity + ≤50% NOVELTY."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.engagement import Engagement, EngagementJournal
from core.types import (
    Citation,
    DataReadinessAssessment,
    EventKind,
    IdeationSource,
    Score,
    TenantContext,
    UseCase,
)
from stages.ideate import IdeationStage

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


def _make_uc(uc_id: str, source: IdeationSource) -> UseCase:
    cite = Citation(kind="evidence", ref="i:cdo:Q2", confidence="high")
    return UseCase(
        id=uc_id,
        problem="p",
        hypothesis="h",
        solution_summary="s",
        expected_value=Decimal("100000"),
        cost_estimate=Decimal("10000"),
        cost_breakdown={"x": Decimal("1000")},
        data_required=["d"],
        capabilities_required=["c"],
        risks=[],
        framework_lens=["rice"],
        score_impact=Score(
            dimension="impact",
            value=5.0,
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
            weakest_dependency_state="defined",
            readiness_band="pilot-ready",
            prep_phase_required=False,
        ),
        evidence=[cite],
    )


class TestIdeationStage:
    def test_propose_use_case_emits_event(self, engagement: Engagement):
        stage = IdeationStage()
        stage.run(engagement)
        uc = _make_uc("uc-1", IdeationSource.BUSINESS_PAIN)
        eid = stage.propose_use_case(engagement, uc)
        assert isinstance(eid, str) and len(eid) == 26
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.USE_CASE_PROPOSED in kinds

    def test_review_blocks_with_zero_use_cases(self, engagement: Engagement):
        stage = IdeationStage()
        stage.run(engagement)
        with pytest.raises(ValueError, match="at least one UseCase"):
            stage.request_review(engagement, "s")

    def test_review_blocks_with_too_few_distinct_sources_L2(self, engagement: Engagement):
        """L2: need ≥3 distinct ideation sources across the proposed set."""
        stage = IdeationStage()
        stage.run(engagement)
        # 3 use cases, only 2 distinct sources
        stage.propose_use_case(engagement, _make_uc("uc-1", IdeationSource.BUSINESS_PAIN))
        stage.propose_use_case(engagement, _make_uc("uc-2", IdeationSource.BUSINESS_PAIN))
        stage.propose_use_case(engagement, _make_uc("uc-3", IdeationSource.DATA_OPPORTUNITY))
        with pytest.raises(ValueError, match="L2 DIVERSE_IDEATION_SOURCES"):
            stage.request_review(engagement, "s")

    def test_review_blocks_high_novelty_share_L2(self, engagement: Engagement):
        """L2: NOVELTY share > 50% rejected (Bision Failure 2).

        Use 5 cases with 3 distinct sources (passes diversity check) and
        3 NOVELTY (60%, fails share check). This isolates the share rule
        from the diversity rule.
        """
        stage = IdeationStage()
        stage.run(engagement)
        stage.propose_use_case(engagement, _make_uc("uc-1", IdeationSource.BUSINESS_PAIN))
        stage.propose_use_case(engagement, _make_uc("uc-2", IdeationSource.DATA_OPPORTUNITY))
        stage.propose_use_case(engagement, _make_uc("uc-3", IdeationSource.NOVELTY))
        stage.propose_use_case(engagement, _make_uc("uc-4", IdeationSource.NOVELTY))
        stage.propose_use_case(engagement, _make_uc("uc-5", IdeationSource.NOVELTY))
        with pytest.raises(ValueError, match="NOVELTY share"):
            stage.request_review(engagement, "s")

    def test_review_passes_with_diverse_sources(self, engagement: Engagement):
        stage = IdeationStage()
        stage.run(engagement)
        stage.propose_use_case(engagement, _make_uc("uc-1", IdeationSource.BUSINESS_PAIN))
        stage.propose_use_case(engagement, _make_uc("uc-2", IdeationSource.DATA_OPPORTUNITY))
        stage.propose_use_case(engagement, _make_uc("uc-3", IdeationSource.REGULATORY_PRESSURE))
        stage.propose_use_case(engagement, _make_uc("uc-4", IdeationSource.COMPETITIVE_RESPONSE))
        stage.request_review(engagement, "Diverse candidate set ready")
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.STAGE_REVIEW_REQUESTED in kinds

    def test_class_vars_correct(self):
        assert IdeationStage.SLUG == "ideate"
        assert IdeationStage.NEXT_STAGE == "prioritize"
