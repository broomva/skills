"""Per-EventKind typed payload schemas (Gap #11 from Tropico engagement).

Replaces the loose `dict[str, object]` shape on JournalEvent.payload with a
discriminated registry so replay and renderers can rely on stable field names.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from core.events import (
    BaselineCapturedPayload,
    DeliverableRenderedPayload,
    DocumentIngestedPayload,
    EngagementConcludedPayload,
    EngagementStartedPayload,
    IntakeCompletedPayload,
    InterviewLoggedPayload,
    MaturityDimensionScoredPayload,
    PilotStartedPayload,
    RoadmapStepProposedPayload,
    StageReviewApprovedPayload,
    StageReviewRequestedPayload,
    StageReviewRevisedPayload,
    StrategicThesisDeclaredPayload,
    UseCasePrioritizedPayload,
    UseCaseProposedPayload,
    payload_for,
)
from core.types import EventKind

pytestmark = pytest.mark.unit


class TestEngagementStartedPayload:
    def test_valid_payload(self):
        p = EngagementStartedPayload(
            tenant_slug="acme-bank",
            scope="AI maturity + Tier-1 deflection — 8w pilot",
            sponsor="Carolina Pérez",
            target_duration_weeks=8,
        )
        assert p.tenant_slug == "acme-bank"
        assert p.target_duration_weeks == 8

    def test_missing_required_rejected(self):
        with pytest.raises(ValidationError, match="tenant_slug"):
            EngagementStartedPayload(  # type: ignore[call-arg]
                scope="x", sponsor="y", target_duration_weeks=1
            )

    def test_payload_for_returns_correct_class(self):
        cls = payload_for(EventKind.ENGAGEMENT_STARTED)
        assert cls is EngagementStartedPayload


class TestAllPayloadsRegistered:
    """After Phase A.2, every EventKind must resolve via payload_for()."""

    def test_all_kinds_have_payloads(self):
        for kind in EventKind:
            cls = payload_for(kind)
            assert issubclass(cls, BaseModel)

    def test_kind_count_matches_registry(self):
        from core.events import _REGISTRY

        assert len(_REGISTRY) == len(list(EventKind))


class TestRemainingPayloads:
    """One positive + one rejection test per remaining payload kind."""

    def test_intake_completed(self):
        p = IntakeCompletedPayload(thesis_id="t1", frameworks_selected=["rice"])
        assert p.thesis_id == "t1"
        with pytest.raises(ValidationError, match="thesis_id"):
            IntakeCompletedPayload(frameworks_selected=[])  # type: ignore[call-arg]

    def test_interview_logged(self):
        p = InterviewLoggedPayload(
            interviewee="CFO Mauricio López",
            role="CFO",
            transcript_ref="interviews/cfo.md",
            key_findings=["Tier-1 cost is the lever"],
        )
        assert p.role == "CFO"

    def test_document_ingested_kind_constrained(self):
        DocumentIngestedPayload(path="x", kind="data", summary="y")
        with pytest.raises(ValidationError, match="kind"):
            DocumentIngestedPayload(path="x", kind="random", summary="y")  # type: ignore[arg-type]

    def test_strategic_thesis_declared(self):
        p = StrategicThesisDeclaredPayload(
            thesis_id="t1",
            economic_lever="x",
            lever_kind="cost",
            magnitude_estimate="100000",
            horizon="h1-now",
            owner="x",
        )
        assert p.lever_kind == "cost"

    def test_maturity_dimension_scored(self):
        p = MaturityDimensionScoredPayload(
            dimension_name="Data Architecture",
            current_value=2.0,
            target_value=4.0,
            framework_ref="cisr",
            gap_summary="g",
        )
        assert p.target_value == 4.0

    def test_use_case_proposed(self):
        p = UseCaseProposedPayload(
            use_case_id="uc-1",
            expected_value="100",
            cost_estimate="10",
            ideation_source="business-pain",
            data_readiness_band="pilot-ready",
        )
        assert p.use_case_id == "uc-1"

    def test_use_case_prioritized(self):
        p = UseCasePrioritizedPayload(
            use_case_id="uc-1",
            rice_score=14.9,
            year1_net="90",
            rank=1,
        )
        assert p.rank == 1

    def test_roadmap_step_proposed(self):
        p = RoadmapStepProposedPayload(
            step_id="rs-1",
            horizon="h1-now",
            quarter="2026-Q3",
            owner="VP Ops",
            success_gate="≥3% CF improvement",
        )
        assert p.horizon == "h1-now"

    def test_baseline_captured(self):
        p = BaselineCapturedPayload(
            metric_name="P95 latency",
            baseline_value="4.2",
            captured_by="VP Ops",
            measurement_date="2026-04-01",
        )
        assert p.measurement_date == "2026-04-01"

    def test_pilot_started(self):
        p = PilotStartedPayload(
            use_case_id="uc-1",
            pilot_design_ref="pd-1",
            start_date="2026-Q3",
            duration_weeks=16,
        )
        assert p.duration_weeks == 16

    def test_deliverable_rendered(self):
        p = DeliverableRenderedPayload(
            slug="maturity-report",
            output_path="/tmp/x.md",
            linter_passed=True,
            lint_warnings=[],
        )
        assert p.linter_passed is True

    def test_stage_review_requested(self):
        p = StageReviewRequestedPayload(
            stage="intake",
            reviewer="x",
            summary="s",
            artifacts=["intake/thesis.md"],
            deadline=None,
        )
        assert p.deadline is None

    def test_stage_review_approved(self):
        p = StageReviewApprovedPayload(stage="intake", reviewer="x", notes="ok")
        assert p.notes == "ok"

    def test_stage_review_revised(self):
        p = StageReviewRevisedPayload(
            stage="scan",
            reviewer="x",
            revisions_requested=["redo dim 1"],
            original_event_id="01HZ...",
        )
        assert p.revisions_requested == ["redo dim 1"]

    def test_engagement_concluded(self):
        p = EngagementConcludedPayload(
            stages_approved=5,
            thesis_id="t1",
            top_pilot="uc-1",
            deliverable_slugs=["maturity-report", "roi-model"],
        )
        assert p.stages_approved == 5
