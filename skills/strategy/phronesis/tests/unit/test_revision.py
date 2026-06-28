"""Revision protocol — STAGE_REVIEW_REVISED retracts later events on the
same stage and re-opens the stage for re-execution. Closes Gap #19."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.engagement import Engagement, EngagementJournal
from core.revision import retract_to_revision_point
from core.types import EventKind, TenantContext

pytestmark = pytest.mark.unit


@pytest.fixture
def tenant() -> TenantContext:
    return TenantContext(
        tenant_slug="acme",
        name="Acme",
        industry="banking",
        region="CO",
        revenue_band="<10M",
        headcount_band="50-500",
        sponsor="x",
        sponsor_role="CDO",
        engagement_scope="s",
        starts_at=datetime(2026, 5, 6, tzinfo=UTC),
        target_duration_weeks=1,
    )


class TestRevision:
    def test_revision_retracts_later_events_on_same_stage(self, tenant: TenantContext) -> None:
        # Build: thesis declared (intake) → 3 maturity dims (scan) → revised (scan).
        # After retract: thesis stays, maturity dims dropped, revision marker stays.
        e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        e.emit(
            EventKind.STRATEGIC_THESIS_DECLARED,
            "intake",
            {
                "thesis_id": "t1",
                "economic_lever": "x",
                "lever_kind": "cost",
                "magnitude_estimate": "1",
                "horizon": "h1-now",
                "owner": "x",
            },
        )
        for i in range(3):
            e.emit(
                EventKind.MATURITY_DIMENSION_SCORED,
                "scan",
                {
                    "dimension_name": f"d{i}",
                    "current_value": 1.0,
                    "target_value": 4.0,
                    "framework_ref": "cisr",
                    "gap_summary": "g",
                },
            )
        e.emit(
            EventKind.STAGE_REVIEW_REVISED,
            "scan",
            {
                "stage": "scan",
                "reviewer": "x",
                "revisions_requested": ["redo dim 1"],
                "original_event_id": "01HZ...",
            },
        )
        assert len(e.journal.events) == 5  # thesis + 3 dims + revised

        removed = retract_to_revision_point(e, "scan")
        assert removed == 3  # 3 maturity dims

        kinds = [ev.kind for ev in e.journal.events]
        assert EventKind.STRATEGIC_THESIS_DECLARED in kinds
        assert EventKind.MATURITY_DIMENSION_SCORED not in kinds
        # Revision marker preserved (audit trail per P5)
        assert EventKind.STAGE_REVIEW_REVISED in kinds

    def test_revision_does_not_touch_other_stages(self, tenant: TenantContext) -> None:
        e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        e.emit(
            EventKind.STRATEGIC_THESIS_DECLARED,
            "intake",
            {
                "thesis_id": "t1",
                "economic_lever": "x",
                "lever_kind": "cost",
                "magnitude_estimate": "1",
                "horizon": "h1-now",
                "owner": "x",
            },
        )
        e.emit(
            EventKind.MATURITY_DIMENSION_SCORED,
            "scan",
            {
                "dimension_name": "d1",
                "current_value": 1.0,
                "target_value": 4.0,
                "framework_ref": "cisr",
                "gap_summary": "g",
            },
        )
        e.emit(
            EventKind.STAGE_REVIEW_REVISED,
            "scan",
            {
                "stage": "scan",
                "reviewer": "x",
                "revisions_requested": ["redo"],
                "original_event_id": "x",
            },
        )

        retract_to_revision_point(e, "scan")

        # Intake event survives.
        assert any(ev.kind == EventKind.STRATEGIC_THESIS_DECLARED for ev in e.journal.events)

    def test_revision_preserves_all_review_markers(self, tenant: TenantContext) -> None:
        """STAGE_REVIEW_REQUESTED and STAGE_REVIEW_APPROVED must survive
        retract — they're the audit trail of who reviewed when."""
        e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        e.emit(
            EventKind.STAGE_REVIEW_REQUESTED,
            "scan",
            {"stage": "scan", "reviewer": "x", "summary": "s", "artifacts": [], "deadline": None},
        )
        e.emit(
            EventKind.MATURITY_DIMENSION_SCORED,
            "scan",
            {
                "dimension_name": "d1",
                "current_value": 1.0,
                "target_value": 4.0,
                "framework_ref": "cisr",
                "gap_summary": "g",
            },
        )
        e.emit(
            EventKind.STAGE_REVIEW_REVISED,
            "scan",
            {
                "stage": "scan",
                "reviewer": "x",
                "revisions_requested": ["redo"],
                "original_event_id": "x",
            },
        )

        retract_to_revision_point(e, "scan")

        kinds = [ev.kind for ev in e.journal.events]
        assert EventKind.STAGE_REVIEW_REQUESTED in kinds
        assert EventKind.STAGE_REVIEW_REVISED in kinds
        assert EventKind.MATURITY_DIMENSION_SCORED not in kinds

    def test_revision_returns_count_of_retracted_events(self, tenant: TenantContext) -> None:
        e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        for i in range(5):
            e.emit(
                EventKind.USE_CASE_PROPOSED,
                "ideate",
                {
                    "use_case_id": f"uc-{i}",
                    "expected_value": "100",
                    "cost_estimate": "10",
                    "ideation_source": "business-pain",
                    "data_readiness_band": "pilot-ready",
                },
            )
        e.emit(
            EventKind.STAGE_REVIEW_REVISED,
            "ideate",
            {
                "stage": "ideate",
                "reviewer": "x",
                "revisions_requested": ["broader source mix"],
                "original_event_id": "x",
            },
        )

        removed = retract_to_revision_point(e, "ideate")
        assert removed == 5  # 5 use cases

    def test_replay_after_revision_drops_retracted_state(self, tenant: TenantContext) -> None:
        """Replay over the trimmed journal must reflect the rolled-back state."""
        e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        e.emit(
            EventKind.USE_CASE_PROPOSED,
            "ideate",
            {
                "use_case_id": "uc-1",
                "expected_value": "100",
                "cost_estimate": "10",
                "ideation_source": "business-pain",
                "data_readiness_band": "pilot-ready",
            },
        )
        # Confirm state has the use case
        assert "uc-1" in e.state().use_cases

        e.emit(
            EventKind.STAGE_REVIEW_REVISED,
            "ideate",
            {
                "stage": "ideate",
                "reviewer": "x",
                "revisions_requested": ["redo"],
                "original_event_id": "x",
            },
        )
        retract_to_revision_point(e, "ideate")

        # After retract + replay, use case is gone from state.
        assert "uc-1" not in e.state().use_cases
