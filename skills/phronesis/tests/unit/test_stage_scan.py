"""Stage 2 Maturity Scan — gate: ≥1 dimension scored before review."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.engagement import Engagement, EngagementJournal
from core.types import (
    Citation,
    EventKind,
    MaturityDimension,
    Score,
    TenantContext,
)
from stages.scan import MaturityScanStage

pytestmark = pytest.mark.unit


@pytest.fixture
def tenant() -> TenantContext:
    return TenantContext(
        tenant_slug="acme-bank",
        name="Acme",
        industry="banking",
        region="CO",
        revenue_band="100M-1B",
        headcount_band="500-5000",
        sponsor="Carolina Pérez",
        sponsor_role="CDO",
        engagement_scope="s",
        starts_at=datetime(2026, 5, 6, tzinfo=UTC),
        target_duration_weeks=8,
    )


@pytest.fixture
def engagement(tenant: TenantContext) -> Engagement:
    return Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))


@pytest.fixture
def dim() -> MaturityDimension:
    cite = Citation(kind="evidence", ref="i:cdo:Q2", confidence="high")
    bench = Citation(kind="evidence", ref="bench:peer-2025", confidence="medium")
    return MaturityDimension(
        name="Operational backbone",
        framework_ref="framework:mit-cisr-digital",
        current_score=Score(
            dimension="cisr-ops",
            value=2.0,
            scale=(1.0, 5.0),
            rubric_ref="cisr",
            rationale="Digitized within silos",
            evidence=[cite],
        ),
        target_score=Score(
            dimension="cisr-ops",
            value=4.0,
            scale=(1.0, 5.0),
            rubric_ref="cisr",
            rationale="Industrialized + accountable target benchmarked vs peer LATAM banks",
            evidence=[bench],
        ),
        gap_summary="Move from siloed ETL to governed core",
        key_actions=["Establish data-product owners"],
        evidence=[cite],
    )


class TestMaturityScanStage:
    def test_score_dimension_emits_event(self, engagement: Engagement, dim: MaturityDimension):
        stage = MaturityScanStage()
        stage.run(engagement)
        eid = stage.score_dimension(engagement, dim)
        assert isinstance(eid, str) and len(eid) == 26
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.MATURITY_DIMENSION_SCORED in kinds

    def test_review_blocks_without_dimension(self, engagement: Engagement):
        stage = MaturityScanStage()
        stage.run(engagement)
        with pytest.raises(ValueError, match="at least one MaturityDimension"):
            stage.request_review(engagement, "summary")

    def test_review_passes_after_score(self, engagement: Engagement, dim: MaturityDimension):
        stage = MaturityScanStage()
        stage.run(engagement)
        stage.score_dimension(engagement, dim)
        stage.request_review(engagement, "Maturity baseline captured")
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.STAGE_REVIEW_REQUESTED in kinds

    def test_state_carries_scored_dimensions(self, engagement: Engagement, dim: MaturityDimension):
        stage = MaturityScanStage()
        stage.run(engagement)
        stage.score_dimension(engagement, dim)
        assert "Operational backbone" in engagement.state().maturity_dimensions

    def test_class_vars_correct(self):
        assert MaturityScanStage.SLUG == "scan"
        assert MaturityScanStage.NEXT_STAGE == "ideate"
