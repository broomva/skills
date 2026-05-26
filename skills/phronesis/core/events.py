"""Typed payloads for each EventKind. Closes Gap #11 from the Tropico
Renovables synthetic engagement (2026-05-06).

JournalEvent.payload was originally `dict[str, object]` — accepted any dict.
The replay function (Phase A.4) and renderers (M3) need stable, typed field
shapes, so each EventKind now has a Pydantic class registered here. The
JournalEvent model_validator (Phase A.3) re-validates `payload` against the
declared kind's schema at construction.

Phase 3 mapping: this registry mirrors lago's `enum E { Started{...}, ... }`
shape for clean transcription to Rust.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.types import EventKind


class EngagementStartedPayload(BaseModel):
    """ENGAGEMENT_STARTED — emitted exactly once when an Engagement is created."""

    tenant_slug: str
    scope: str
    sponsor: str
    target_duration_weeks: int


class IntakeCompletedPayload(BaseModel):
    """INTAKE_COMPLETED — Stage 1 closes after thesis declared + frameworks selected."""

    thesis_id: str
    frameworks_selected: list[str]


class InterviewLoggedPayload(BaseModel):
    """INTERVIEW_LOGGED — sponsor / SME interview captured during intake."""

    interviewee: str
    role: str
    transcript_ref: str
    key_findings: list[str]


class DocumentIngestedPayload(BaseModel):
    """DOCUMENT_INGESTED — internal doc consumed during intake (data, regs, prior reports)."""

    path: str
    kind: Literal["interview", "data", "regulatory", "report"]
    summary: str


class StrategicThesisDeclaredPayload(BaseModel):
    """STRATEGIC_THESIS_DECLARED — L1 milestone event."""

    thesis_id: str
    economic_lever: str
    lever_kind: str
    magnitude_estimate: str  # str-encoded Decimal for journal portability
    horizon: str
    owner: str


class MaturityDimensionScoredPayload(BaseModel):
    """MATURITY_DIMENSION_SCORED — emitted once per scored dimension in Stage 2."""

    dimension_name: str
    current_value: float
    target_value: float
    framework_ref: str
    gap_summary: str


class UseCaseProposedPayload(BaseModel):
    """USE_CASE_PROPOSED — surfaced during Stage 3 ideation."""

    use_case_id: str
    expected_value: str  # str-encoded Decimal
    cost_estimate: str
    ideation_source: str
    data_readiness_band: str


class UseCasePrioritizedPayload(BaseModel):
    """USE_CASE_PRIORITIZED — ranked + ROI-modeled in Stage 4."""

    use_case_id: str
    rice_score: float
    year1_net: str  # str-encoded Decimal
    rank: int


class RoadmapStepProposedPayload(BaseModel):
    """ROADMAP_STEP_PROPOSED — one step in Stage 5 Three-Horizons plan."""

    step_id: str
    horizon: str
    quarter: str
    owner: str
    success_gate: str


class BaselineCapturedPayload(BaseModel):
    """BASELINE_CAPTURED — L5 enforcement; must precede PILOT_STARTED."""

    metric_name: str
    baseline_value: str  # str-encoded Decimal
    captured_by: str
    measurement_date: str  # ISO 8601


class PilotStartedPayload(BaseModel):
    """PILOT_STARTED — L5 gate fires here; baseline must already be captured."""

    use_case_id: str
    pilot_design_ref: str
    start_date: str
    duration_weeks: int


class DeliverableRenderedPayload(BaseModel):
    """DELIVERABLE_RENDERED — emitted by render orchestrator (M3)."""

    slug: str
    output_path: str
    linter_passed: bool
    lint_warnings: list[str]


class StageReviewRequestedPayload(BaseModel):
    """STAGE_REVIEW_REQUESTED — sponsor gate. P5 enforcement."""

    stage: str
    reviewer: str
    summary: str
    artifacts: list[str]
    deadline: str | None = None


class StageReviewApprovedPayload(BaseModel):
    """STAGE_REVIEW_APPROVED — gate cleared, advances current_stage."""

    stage: str
    reviewer: str
    notes: str | None = None


class StageReviewRevisedPayload(BaseModel):
    """STAGE_REVIEW_REVISED — sponsor sends stage back. Triggers retract_to_revision_point (A.8)."""

    stage: str
    reviewer: str
    revisions_requested: list[str]
    original_event_id: str


class EngagementConcludedPayload(BaseModel):
    """ENGAGEMENT_CONCLUDED — terminal event. Stages all approved + deliverables rendered."""

    stages_approved: int
    thesis_id: str
    top_pilot: str
    deliverable_slugs: list[str]


_REGISTRY: dict[EventKind, type[BaseModel]] = {
    EventKind.ENGAGEMENT_STARTED: EngagementStartedPayload,
    EventKind.INTAKE_COMPLETED: IntakeCompletedPayload,
    EventKind.INTERVIEW_LOGGED: InterviewLoggedPayload,
    EventKind.DOCUMENT_INGESTED: DocumentIngestedPayload,
    EventKind.STRATEGIC_THESIS_DECLARED: StrategicThesisDeclaredPayload,
    EventKind.MATURITY_DIMENSION_SCORED: MaturityDimensionScoredPayload,
    EventKind.USE_CASE_PROPOSED: UseCaseProposedPayload,
    EventKind.USE_CASE_PRIORITIZED: UseCasePrioritizedPayload,
    EventKind.ROADMAP_STEP_PROPOSED: RoadmapStepProposedPayload,
    EventKind.BASELINE_CAPTURED: BaselineCapturedPayload,
    EventKind.PILOT_STARTED: PilotStartedPayload,
    EventKind.DELIVERABLE_RENDERED: DeliverableRenderedPayload,
    EventKind.STAGE_REVIEW_REQUESTED: StageReviewRequestedPayload,
    EventKind.STAGE_REVIEW_APPROVED: StageReviewApprovedPayload,
    EventKind.STAGE_REVIEW_REVISED: StageReviewRevisedPayload,
    EventKind.ENGAGEMENT_CONCLUDED: EngagementConcludedPayload,
}


def payload_for(kind: EventKind) -> type[BaseModel]:
    """Return the typed payload class for an EventKind.

    Raises KeyError if the kind has no registered payload schema. After
    Phase A.2, all 16 EventKinds are registered and this never raises in
    practice.
    """
    return _REGISTRY[kind]
