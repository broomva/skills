"""Stage 1 Intake — must produce StrategicThesis (L1) before stage exits.

This test file is the worked template for tests/unit/test_stage_<slug>.py
(C.2-C.5). Each remaining stage gets a sibling file with similar shape:
construction, gate-passes, gate-rejects, terminal events.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.engagement import Engagement, EngagementJournal
from core.types import (
    Citation,
    EventKind,
    StrategicThesis,
    TenantContext,
)
from stages.intake import IntakeStage

pytestmark = pytest.mark.unit


@pytest.fixture
def tenant() -> TenantContext:
    return TenantContext(
        tenant_slug="acme-bank",
        name="Acme Bank",
        industry="banking",
        region="CO",
        revenue_band="100M-1B",
        headcount_band="500-5000",
        sponsor="Carolina Pérez",
        sponsor_role="CDO",
        engagement_scope="AI maturity + Tier-1 deflection — 8w pilot",
        starts_at=datetime(2026, 5, 6, tzinfo=UTC),
        target_duration_weeks=8,
    )


@pytest.fixture
def engagement(tenant: TenantContext) -> Engagement:
    return Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))


@pytest.fixture
def thesis() -> StrategicThesis:
    cite = Citation(kind="evidence", ref="interview:cdo:2026-Q2", confidence="high")
    return StrategicThesis(
        economic_lever="Reduce Tier-1 ticket cost via Spanish-LLM deflection",
        lever_kind="cost",
        magnitude_estimate=Decimal("400000"),
        magnitude_basis="12K tickets × $8 × 35% deflection × 12mo",
        strategic_horizon="h1-now",
        decision_rights_owner="Carolina Pérez (CDO)",
        measured_in="USD/yr",
        evidence=[cite],
    )


class TestIntakeStage:
    def test_run_emits_engagement_started(self, engagement: Engagement):
        stage = IntakeStage()
        stage.run(engagement)
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.ENGAGEMENT_STARTED in kinds
        # Payload comes from tenant context
        ev = engagement.journal.events[0]
        assert ev.payload["tenant_slug"] == "acme-bank"

    def test_log_interview_emits_event(self, engagement: Engagement):
        stage = IntakeStage()
        stage.run(engagement)
        eid = stage.log_interview(
            engagement,
            interviewee="CFO Mauricio López",
            role="CFO",
            transcript_ref="interviews/cfo.md",
            key_findings=["Tier-1 cost is the lever"],
        )
        assert isinstance(eid, str) and len(eid) == 26  # ULID
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.INTERVIEW_LOGGED in kinds

    def test_ingest_document_emits_event(self, engagement: Engagement):
        stage = IntakeStage()
        stage.run(engagement)
        stage.ingest_document(
            engagement,
            path="data/it-architecture.pdf",
            kind="report",
            summary="Current IT architecture overview",
        )
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.DOCUMENT_INGESTED in kinds

    def test_declare_thesis_emits_event_and_sets_state(
        self, engagement: Engagement, thesis: StrategicThesis
    ):
        stage = IntakeStage()
        stage.run(engagement)
        stage.declare_thesis(engagement, thesis)
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.STRATEGIC_THESIS_DECLARED in kinds
        # State now carries the thesis_id
        assert engagement.state().thesis_id == thesis.thesis_id

    def test_review_blocks_without_thesis_L1(self, engagement: Engagement):
        """L1 enforcement: cannot exit intake without a StrategicThesis."""
        stage = IntakeStage()
        stage.run(engagement)
        with pytest.raises(ValueError, match="L1 STRATEGIC_THESIS_REQUIRED"):
            stage.request_review(engagement, "summary text")

    def test_review_passes_with_thesis(self, engagement: Engagement, thesis: StrategicThesis):
        stage = IntakeStage()
        stage.run(engagement)
        stage.declare_thesis(engagement, thesis)
        stage.request_review(engagement, "Thesis declared, ready for sponsor sign-off")
        kinds = [e.kind for e in engagement.journal.events]
        assert EventKind.STAGE_REVIEW_REQUESTED in kinds
        assert EventKind.INTAKE_COMPLETED in kinds

    def test_intake_completed_carries_thesis_id(
        self, engagement: Engagement, thesis: StrategicThesis
    ):
        stage = IntakeStage()
        stage.run(engagement)
        stage.declare_thesis(engagement, thesis)
        stage.request_review(engagement, "ok")
        completed = next(
            e for e in engagement.journal.events if e.kind == EventKind.INTAKE_COMPLETED
        )
        assert completed.payload["thesis_id"] == thesis.thesis_id

    def test_full_intake_sequence(self, engagement: Engagement, thesis: StrategicThesis):
        """Realistic intake: run → log 2 interviews → ingest 1 doc →
        declare thesis → request review."""
        stage = IntakeStage()
        stage.run(engagement)
        stage.log_interview(
            engagement,
            interviewee="CFO Mauricio López",
            role="CFO",
            transcript_ref="interviews/cfo.md",
            key_findings=["Tier-1 cost is the lever"],
        )
        stage.log_interview(
            engagement,
            interviewee="Head of CS",
            role="Director CS",
            transcript_ref="interviews/cs.md",
            key_findings=["Spanish queries dominate Tier-1"],
        )
        stage.ingest_document(
            engagement,
            path="data/ticket-volume-2025.csv",
            kind="data",
            summary="12-month Tier-1 ticket volume baseline",
        )
        stage.declare_thesis(engagement, thesis)
        stage.request_review(engagement, "Sponsor sign-off needed")

        # 6 events total: started + 2 interviews + 1 doc + thesis + review-req + completed
        assert len(engagement.journal.events) == 7
        assert engagement.state().thesis_id == thesis.thesis_id
        assert engagement.state().review_pending == "intake"

    def test_class_vars_correct(self):
        assert IntakeStage.SLUG == "intake"
        assert IntakeStage.NEXT_STAGE == "scan"
