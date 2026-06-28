"""EngagementJournal aggregate + replay → state function (Gap #12 + #13)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.engagement import Engagement, EngagementJournal
from core.types import EventKind, JournalEvent, TenantContext

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


def _ev(kind: EventKind, stage: str = "intake", **payload: object) -> JournalEvent:
    """Test helper — construct a JournalEvent with auto-generated id/timestamp."""
    return JournalEvent(kind=kind, actor="t", stage=stage, payload=payload)


# ----------------------------------------------------------------------------
# A.4 — EngagementJournal + replay
# ----------------------------------------------------------------------------


class TestEngagementJournal:
    def test_empty_journal_replays_to_initial_state(self, tenant: TenantContext) -> None:
        j = EngagementJournal(tenant=tenant, events=[])
        s = j.replay()
        assert s.current_stage == "intake"
        assert s.thesis_id is None
        assert s.use_cases == {}
        assert s.is_concluded is False
        assert s.review_pending is None


# ----------------------------------------------------------------------------
# A.5 — Full replay sequence
# ----------------------------------------------------------------------------


class TestReplaySequence:
    def test_thesis_event_sets_thesis_id(self, tenant: TenantContext) -> None:
        j = EngagementJournal(
            tenant=tenant,
            events=[
                _ev(
                    EventKind.STRATEGIC_THESIS_DECLARED,
                    stage="intake",
                    thesis_id="01HZ000",
                    economic_lever="x",
                    lever_kind="cost",
                    magnitude_estimate="100",
                    horizon="h1-now",
                    owner="x",
                ),
            ],
        )
        s = j.replay()
        assert s.thesis_id == "01HZ000"

    def test_intake_completed_sets_frameworks(self, tenant: TenantContext) -> None:
        j = EngagementJournal(
            tenant=tenant,
            events=[
                _ev(
                    EventKind.INTAKE_COMPLETED,
                    stage="intake",
                    thesis_id="t1",
                    frameworks_selected=["mit-cisr-digital", "rice"],
                ),
            ],
        )
        s = j.replay()
        assert s.frameworks_active == ["mit-cisr-digital", "rice"]

    def test_review_approved_advances_through_stages(self, tenant: TenantContext) -> None:
        # STAGE_REVIEW_APPROVED's payload requires `stage` field — distinct
        # from the JournalEvent's own `stage` field (which is metadata).
        events = []
        for stage in ["intake", "scan", "ideate", "prioritize", "roadmap"]:
            events.append(
                JournalEvent(
                    kind=EventKind.STAGE_REVIEW_APPROVED,
                    actor="t",
                    stage=stage,
                    payload={"stage": stage, "reviewer": "x", "notes": None},
                )
            )
        j = EngagementJournal(tenant=tenant, events=events)
        s = j.replay()
        assert s.current_stage == "concluded"

    def test_engagement_concluded_sets_flag(self, tenant: TenantContext) -> None:
        j = EngagementJournal(
            tenant=tenant,
            events=[
                _ev(
                    EventKind.ENGAGEMENT_CONCLUDED,
                    stage="roadmap",
                    stages_approved=5,
                    thesis_id="t1",
                    top_pilot="uc-x",
                    deliverable_slugs=[],
                ),
            ],
        )
        s = j.replay()
        assert s.is_concluded is True
        assert s.current_stage == "concluded"

    def test_use_cases_accumulate(self, tenant: TenantContext) -> None:
        j = EngagementJournal(
            tenant=tenant,
            events=[
                _ev(
                    EventKind.USE_CASE_PROPOSED,
                    stage="ideate",
                    use_case_id="uc-1",
                    expected_value="100",
                    cost_estimate="10",
                    ideation_source="business-pain",
                    data_readiness_band="pilot-ready",
                ),
                _ev(
                    EventKind.USE_CASE_PROPOSED,
                    stage="ideate",
                    use_case_id="uc-2",
                    expected_value="200",
                    cost_estimate="20",
                    ideation_source="data-opportunity",
                    data_readiness_band="needs-prep",
                ),
                _ev(
                    EventKind.USE_CASE_PRIORITIZED,
                    stage="prioritize",
                    use_case_id="uc-1",
                    rice_score=14.9,
                    year1_net="90",
                    rank=1,
                ),
            ],
        )
        s = j.replay()
        assert "uc-1" in s.use_cases and "uc-2" in s.use_cases
        assert s.use_cases_prioritized == ["uc-1"]

    def test_review_request_then_approve_clears_pending(self, tenant: TenantContext) -> None:
        j = EngagementJournal(
            tenant=tenant,
            events=[
                JournalEvent(
                    kind=EventKind.STAGE_REVIEW_REQUESTED,
                    actor="t",
                    stage="intake",
                    payload={
                        "stage": "intake",
                        "reviewer": "x",
                        "summary": "s",
                        "artifacts": [],
                        "deadline": None,
                    },
                ),
                JournalEvent(
                    kind=EventKind.STAGE_REVIEW_APPROVED,
                    actor="t",
                    stage="intake",
                    payload={"stage": "intake", "reviewer": "x", "notes": None},
                ),
            ],
        )
        s = j.replay()
        assert s.review_pending is None
        assert s.current_stage == "scan"


# ----------------------------------------------------------------------------
# A.6 — Replay properties (idempotency + non-mutation)
# ----------------------------------------------------------------------------


class TestReplayProperties:
    def test_replay_is_idempotent(self, tenant: TenantContext) -> None:
        """Calling replay() twice produces equal states — required for
        resume/audit semantics. Phase 3 lago invariant."""
        j = EngagementJournal(
            tenant=tenant,
            events=[
                _ev(
                    EventKind.STRATEGIC_THESIS_DECLARED,
                    stage="intake",
                    thesis_id="t1",
                    economic_lever="x",
                    lever_kind="cost",
                    magnitude_estimate="1",
                    horizon="h1-now",
                    owner="x",
                ),
                _ev(
                    EventKind.INTAKE_COMPLETED,
                    stage="intake",
                    thesis_id="t1",
                    frameworks_selected=["rice"],
                ),
                _ev(
                    EventKind.MATURITY_DIMENSION_SCORED,
                    stage="scan",
                    dimension_name="d1",
                    current_value=2.0,
                    target_value=4.0,
                    framework_ref="cisr",
                    gap_summary="g",
                ),
            ],
        )
        s1 = j.replay()
        s2 = j.replay()
        assert s1.model_dump() == s2.model_dump()

    def test_replay_does_not_mutate_journal(self, tenant: TenantContext) -> None:
        events_before = [
            _ev(
                EventKind.ENGAGEMENT_STARTED,
                stage="intake",
                tenant_slug="t",
                scope="s",
                sponsor="x",
                target_duration_weeks=1,
            ),
        ]
        j = EngagementJournal(tenant=tenant, events=list(events_before))
        j.replay()
        assert j.events == events_before

    def test_apply_does_not_mutate_input_state(self, tenant: TenantContext) -> None:
        """The internal _apply function must be pure — no in-place mutation."""
        from core.engagement import EngagementState, _apply

        s_in = EngagementState()
        ev = _ev(
            EventKind.STRATEGIC_THESIS_DECLARED,
            stage="intake",
            thesis_id="t1",
            economic_lever="x",
            lever_kind="cost",
            magnitude_estimate="1",
            horizon="h1-now",
            owner="x",
        )
        s_out = _apply(s_in, ev)
        assert s_in.thesis_id is None  # unchanged
        assert s_out.thesis_id == "t1"  # new state has the change


# ----------------------------------------------------------------------------
# A.7 — Engagement aggregate root
# ----------------------------------------------------------------------------


class TestEngagement:
    def test_engagement_root_initial_state(self, tenant: TenantContext) -> None:
        e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        s = e.state()
        assert s.current_stage == "intake"
        assert e.tenant.tenant_slug == tenant.tenant_slug

    def test_emit_appends_to_journal(self, tenant: TenantContext) -> None:
        e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        eid = e.emit(
            EventKind.ENGAGEMENT_STARTED,
            "intake",
            {"tenant_slug": "x", "scope": "y", "sponsor": "z", "target_duration_weeks": 1},
        )
        assert len(e.journal.events) == 1
        assert e.journal.events[0].kind == EventKind.ENGAGEMENT_STARTED
        assert e.journal.events[0].event_id == eid

    def test_emit_returns_unique_event_ids(self, tenant: TenantContext) -> None:
        e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        ids = []
        for _ in range(3):
            ids.append(
                e.emit(
                    EventKind.ENGAGEMENT_STARTED,
                    "intake",
                    {"tenant_slug": "x", "scope": "y", "sponsor": "z", "target_duration_weeks": 1},
                )
            )
        assert len(set(ids)) == 3

    def test_emit_state_advances_after_emit(self, tenant: TenantContext) -> None:
        e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        e.emit(
            EventKind.STRATEGIC_THESIS_DECLARED,
            "intake",
            {
                "thesis_id": "t1",
                "economic_lever": "x",
                "lever_kind": "cost",
                "magnitude_estimate": "100",
                "horizon": "h1-now",
                "owner": "x",
            },
        )
        assert e.state().thesis_id == "t1"

    def test_emit_rejects_payload_not_matching_kind(self, tenant: TenantContext) -> None:
        """Phase A.3 + A.7 wired together — emit() validates payload via
        JournalEvent's model_validator before appending."""
        e = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            # Missing target_duration_weeks
            e.emit(
                EventKind.ENGAGEMENT_STARTED,
                "intake",
                {"tenant_slug": "x", "scope": "y", "sponsor": "z"},
            )
        # Journal must remain empty — bad emit must not append.
        assert e.journal.events == []
