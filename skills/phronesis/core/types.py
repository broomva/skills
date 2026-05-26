"""phronesis.core.types — typed primitives at the substrate layer.

Layers:
- Layer 1: Atomic primitives (Citation, Score, Finding, Recommendation, AdoptionMetric, etc.)
- Layer 2: Deliverable-specific aggregates (UseCase, MaturityDimension, RoiCell, ...)
- Layer 3: Event-sourced journal (JournalEvent, EventKind)
- Layer 4: Review gate (StageReview)
- Layer 5: Engagement context (TenantContext, FrameworkSelection)

Each primitive is a Pydantic model designed to translate cleanly to a Rust struct
in Phase 3 (no Python-isms — explicit enums, Decimal for money, datetime for time,
no dict for variant types).

Principles enforced:
- P3 (citations first-class): Finding, Recommendation, BaselineSection, StrategicThesis
  require non-empty evidence: list[Citation].
- P8 (specificity): Recommendation requires value, value_basis, owner,
  timeline_weeks, success_metric, success_target, kill_criterion.
- L1 (StrategicThesis): typed primitive, mandatory at Stage 1.
- L4 (AdoptionMetric): required field on PilotDesign and Recommendation.
- L5 (BaselineSection): required field on PilotDesign.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

import ulid as _ulid
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _new_event_id() -> str:
    """Generate a new ULID string for journal events.

    Wraps ulid-py's factory because `ulid.ULID()` is a class constructor that
    expects a buffer argument (ULID extends MemoryView), which trips Pydantic
    coercion. Callers should rely on `JournalEvent`'s default_factory rather
    than constructing event_ids by hand.
    """
    return str(_ulid.new())


def _utcnow() -> datetime:
    """Timezone-aware UTC now. Used as default_factory for event timestamps."""
    return datetime.now(UTC)


# ----------------------------------------------------------------------------
# Layer 1 — Atomic primitives
# ----------------------------------------------------------------------------


class Citation(BaseModel):
    """A reference to evidence supporting a claim. P3.

    kind:
      - "evidence":  tenant interview, document, telemetry. ref like "interview:cfo:Q3"
      - "framework": references a framework primitive. ref like "framework:rice"
      - "entity":    references a knowledge graph entity. ref like "entity:concept/jtbd"
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["evidence", "framework", "entity"]
    ref: str
    excerpt: str | None = None
    confidence: Literal["high", "medium", "low"]


class Score(BaseModel):
    """A scored value along a dimension, with rationale and evidence.

    Used by frameworks (e.g., RICE produces a Score with dimension='rice-score').
    `value` must lie within the inclusive `scale` interval — out-of-range
    scores are rejected at construction so silently-wrong rubrics can't
    propagate into deliverables.
    """

    dimension: str
    value: float
    scale: tuple[float, float]
    rubric_ref: str
    rationale: str
    evidence: list[Citation] = Field(default_factory=list)

    @field_validator("scale")
    @classmethod
    def scale_is_ordered(cls, v: tuple[float, float]) -> tuple[float, float]:
        lo, hi = v
        if lo >= hi:
            raise ValueError(f"Score.scale must be (lo, hi) with lo < hi; got ({lo}, {hi})")
        return v

    @model_validator(mode="after")
    def value_within_scale(self) -> Score:
        lo, hi = self.scale
        if not (lo <= self.value <= hi):
            raise ValueError(
                f"Score.value={self.value} is outside scale [{lo}, {hi}] "
                f"on dimension={self.dimension!r}"
            )
        return self


class Finding(BaseModel):
    """A claim made by the engagement. The atomic unit of analysis.

    P3: evidence MUST be non-empty.
    """

    title: str
    body: str
    severity: Literal["critical", "major", "minor", "informational"]
    confidence: Literal["high", "medium", "low"]
    evidence: list[Citation]

    @field_validator("evidence")
    @classmethod
    def must_have_evidence(cls, v: list[Citation]) -> list[Citation]:
        if not v:
            raise ValueError("Finding requires non-empty evidence (P3 — citations first-class)")
        return v


# ----------------------------------------------------------------------------
# Bision-failure-prevention support primitives
# ----------------------------------------------------------------------------


class IdeationSource(StrEnum):
    """How a use-case candidate was surfaced. Supports L2 (ideation diversity).

    Bision Failure 2 (87% observed): Casos de uso mal priorizados — elección por
    novedad, no por impacto. L2 warns when >50% of use cases are NOVELTY-sourced.
    """

    BUSINESS_PAIN = "business-pain"
    DATA_OPPORTUNITY = "data-opportunity"
    REGULATORY_PRESSURE = "regulatory-pressure"
    COMPETITIVE_RESPONSE = "competitive-response"
    NOVELTY = "novelty"


class DataReadinessAssessment(BaseModel):
    """Per-use-case data dependency readiness. Supports L3.

    Bision Failure 3 (74% observed): Datos no preparados. L3 rejects pilots with
    `readiness_band == "blocking"` AND no prep_phase AND horizon == "h1-now".
    """

    use_case_id: str
    data_dependencies: list[str]
    weakest_dependency_state: Literal["absent", "ad-hoc", "defined", "managed", "optimizing"]
    readiness_band: Literal["pilot-ready", "needs-prep", "blocking"]
    prep_phase_required: bool
    prep_phase_estimated_weeks: int | None = None
    prep_phase_owner: str | None = None


class AdoptionMetric(BaseModel):
    """Adoption metric, distinct from technical metric. Supports L4.

    Bision Failure 4 (61% observed): Desconexión negocio-tecnología — modelos con
    precisión alta y baja adopción. L4 rejects PilotDesign or Recommendation
    without an AdoptionMetric.
    """

    metric_name: str
    target_value: str
    measurement_method: str
    owner: str  # NOT the technical owner


class BaselineSection(BaseModel):
    """Baseline captured before pilot starts. Supports L5.

    Bision Failure 5 (48% observed): Sin medición de ROI — sin baseline al inicio,
    no hay defensa al final. L5 rejects PilotDesign without >=1 BaselineSection
    per success criterion. The journal must record BASELINE_CAPTURED before
    PILOT_STARTED — no retroactive baselines.

    Greenfield pilots (BRO-1034): when no incumbent metric exists (e.g., a
    brand-new product line with zero production traffic), set
    `is_greenfield=True`. The L5 invariant becomes "declare zero-state
    explicitly" rather than "capture incumbent metric" — protecting against
    the subtler failure where a team SAYS they have a baseline but it's `0`
    because they didn't measure. baseline_value still required (use Decimal("0")
    for greenfield) so renderers and downstream tooling have a numeric value.
    """

    metric_name: str
    baseline_value: Decimal
    baseline_window: str
    baseline_data_source: str
    baseline_measurement_date: datetime
    captured_by: str
    evidence: list[Citation]
    is_greenfield: bool = False

    @field_validator("evidence")
    @classmethod
    def must_have_evidence(cls, v: list[Citation]) -> list[Citation]:
        if not v:
            raise ValueError(
                "BaselineSection requires non-empty evidence (P3 — citations first-class)"
            )
        return v


class StrategicThesis(BaseModel):
    """The economic lever that justifies the engagement. Supports L1.

    Bision Failure 1 (100% observed): Sin tesis estratégica — "hagamos algo de IA",
    sin palanca económica clara. L1 blocks every stage past Stage 1 without a
    StrategicThesis event in the journal.

    A strategic thesis answers: "What economic lever justifies this engagement?"
    Vague answers ("improve operations", "do AI better") are rejected.
    """

    thesis_id: str = Field(default_factory=_new_event_id)
    economic_lever: str
    lever_kind: Literal["revenue", "cost", "risk", "speed", "strategic-option"]
    magnitude_estimate: Decimal
    magnitude_basis: str
    strategic_horizon: Literal["h1-now", "h2-next", "h3-later"]
    decision_rights_owner: str
    measured_in: str
    evidence: list[Citation]

    @field_validator("evidence")
    @classmethod
    def must_have_evidence(cls, v: list[Citation]) -> list[Citation]:
        if not v:
            raise ValueError(
                "StrategicThesis requires non-empty evidence (P3 — citations first-class)"
            )
        return v


# ----------------------------------------------------------------------------
# Recommendation (P8 + L4 enforcement)
# ----------------------------------------------------------------------------


class Recommendation(BaseModel):
    """A specific, quantified, owned, time-bound recommendation. P8 + L4.

    P8 (specificity): every Recommendation MUST be quantified, owned, and
    time-bound. Missing any required field → Pydantic ValidationError.
    The renderer-time linter additionally rejects vague verbs in title and
    description ("explore", "consider", "investigate", "look into") — that
    rule lives in core.linter (M3) since it's content-level, not type-level.

    L4 (Bision Failure 4): adoption_metric is required, distinct from
    success_metric (which can be technical).
    """

    title: str
    description: str
    value: Decimal
    value_basis: str
    value_currency: str = "USD"
    owner: str
    timeline_weeks: int
    success_metric: str
    success_target: str
    kill_criterion: str
    adoption_metric: AdoptionMetric  # L4
    dependencies: list[str] = Field(default_factory=list)
    evidence: list[Citation]

    @field_validator("evidence")
    @classmethod
    def must_have_evidence(cls, v: list[Citation]) -> list[Citation]:
        if not v:
            raise ValueError(
                "Recommendation requires non-empty evidence (P3 — citations first-class)"
            )
        return v


# ----------------------------------------------------------------------------
# Layer 2 — Deliverable-specific aggregates
# ----------------------------------------------------------------------------


class MaturityDimension(BaseModel):
    """A scored dimension of org maturity. Used by maturity-report deliverable.

    Both `current_score` and `target_score` must carry evidence — a target
    without justification is wishful thinking, not a strategic claim. The
    target's evidence is typically a benchmark, regulatory deadline, peer
    comparison, or thesis-derived horizon (e.g., "must reach managed by
    2027-Q1 to qualify for FFR market"). P3 transitive enforcement.
    """

    name: str
    framework_ref: str
    current_score: Score
    target_score: Score
    gap_summary: str
    key_actions: list[str]
    evidence: list[Citation]

    @model_validator(mode="after")
    def both_scores_must_have_evidence(self) -> MaturityDimension:
        if not self.current_score.evidence:
            raise ValueError(
                f"MaturityDimension {self.name!r}: current_score.evidence is "
                "empty (P3 — citations first-class)"
            )
        if not self.target_score.evidence:
            raise ValueError(
                f"MaturityDimension {self.name!r}: target_score.evidence is "
                "empty — targets without evidence are wishful thinking. "
                "Cite a benchmark, regulatory deadline, peer comparison, or "
                "thesis-derived horizon."
            )
        return self


class CapabilityCell(BaseModel):
    """A capability gap assessment. Used by capability-heatmap deliverable."""

    capability: str
    category: Literal["data", "talent", "tooling", "governance", "process"]
    current_state: Literal["absent", "ad-hoc", "defined", "managed", "optimizing"]
    target_state: Literal["absent", "ad-hoc", "defined", "managed", "optimizing"]
    criticality: Literal["foundational", "important", "nice-to-have"]
    evidence: list[Citation]


class UseCase(BaseModel):
    """A prioritized AI/data initiative candidate. Used by use-case-dossier deliverable.

    Carries the ideation_source (L2) and data_readiness (L3) for failure-mode prevention.

    `status` tracks the lifecycle through the engagement so dropped/deferred
    use cases stay in the dossier (audit trail) rather than being silently
    removed from the list:
      - "proposed":    surfaced during ideation, not yet ranked
      - "prioritized": survived RICE/ICE/WSJF, in the active set
      - "deferred":    out of scope for this engagement, parked for next cycle
      - "dropped":     ruled out at any gate (sponsor decision, kill_criterion,
                       data-readiness fail) — keep with reasoning
    """

    id: str
    problem: str
    hypothesis: str
    solution_summary: str
    expected_value: Decimal
    cost_estimate: Decimal
    cost_breakdown: dict[str, Decimal]
    data_required: list[str]
    capabilities_required: list[str]
    risks: list[Finding]
    framework_lens: list[str]
    score_impact: Score
    score_effort: Score
    ideation_source: IdeationSource  # L2
    data_readiness: DataReadinessAssessment  # L3
    status: Literal["proposed", "prioritized", "deferred", "dropped"] = "proposed"
    status_rationale: str | None = None
    evidence: list[Citation]

    @model_validator(mode="after")
    def dropped_or_deferred_requires_rationale(self) -> UseCase:
        if self.status in ("dropped", "deferred") and not self.status_rationale:
            raise ValueError(
                f"UseCase {self.id!r}: status={self.status!r} requires "
                "status_rationale (audit trail — why was this killed?)"
            )
        return self


class RoiCell(BaseModel):
    """A single year's ROI projection for a use case. Used by roi-model deliverable."""

    use_case_id: str
    year: int
    revenue_impact: Decimal
    cost_savings: Decimal
    investment: Decimal
    one_time_cost: Decimal
    recurring_cost: Decimal
    net: Decimal
    cumulative_net: Decimal
    discount_rate: Decimal
    sensitivity_low: Decimal
    sensitivity_high: Decimal
    assumptions: list[str]


class RoadmapStep(BaseModel):
    """A step in the innovation roadmap. Anchored to a Three-Horizons horizon."""

    id: str
    title: str
    horizon: Literal["h1-now", "h2-next", "h3-later"]
    quarter: str
    related_use_cases: list[str]
    related_recommendations: list[str]
    dependencies: list[str]
    owner: str
    success_gate: str


class PilotDesign(BaseModel):
    """A controlled-experiment design for a use case. Used by pilot-plan deliverable.

    L4: adoption_metric required (distinct from technical success metrics).
    L5: baseline must be non-empty (no retroactive baselines).
    """

    use_case_id: str
    hypothesis: str
    null_hypothesis: str
    duration_weeks: int
    cohort_definition: str
    success_criteria: list[str]
    kill_criterion: str
    learning_objectives: list[str]
    risks: list[Finding]
    cost_estimate: Decimal
    adoption_metric: AdoptionMetric  # L4
    baseline: list[BaselineSection]  # L5
    evidence: list[Citation]

    @field_validator("baseline")
    @classmethod
    def must_have_at_least_one_baseline(cls, v: list[BaselineSection]) -> list[BaselineSection]:
        if not v:
            raise ValueError(
                "PilotDesign requires non-empty baseline "
                "(L5 — Bision Failure 5: sin medición de ROI)"
            )
        return v


# ----------------------------------------------------------------------------
# Layer 3 — Event-sourced journal (P4)
# ----------------------------------------------------------------------------


class EventKind(StrEnum):
    """All canonical engagement journal event kinds.

    Append-only. Adding a new kind requires:
    1. Adding it here
    2. Adding a replay handler in core/engagement.py (M3)
    3. Adding it to the CLI command that emits it
    4. Adding a unit test that verifies replay reconstructs state correctly
    """

    ENGAGEMENT_STARTED = "engagement.started"
    INTAKE_COMPLETED = "intake.completed"
    INTERVIEW_LOGGED = "interview.logged"
    DOCUMENT_INGESTED = "document.ingested"
    STRATEGIC_THESIS_DECLARED = "strategic_thesis.declared"  # L1
    MATURITY_DIMENSION_SCORED = "maturity.dimension.scored"
    USE_CASE_PROPOSED = "use_case.proposed"
    USE_CASE_PRIORITIZED = "use_case.prioritized"
    ROADMAP_STEP_PROPOSED = "roadmap.step.proposed"
    BASELINE_CAPTURED = "baseline.captured"  # L5 — must precede PILOT_STARTED
    PILOT_STARTED = "pilot.started"
    DELIVERABLE_RENDERED = "deliverable.rendered"
    STAGE_REVIEW_REQUESTED = "stage.review.requested"
    STAGE_REVIEW_APPROVED = "stage.review.approved"
    STAGE_REVIEW_REVISED = "stage.review.revised"
    ENGAGEMENT_CONCLUDED = "engagement.concluded"


class JournalEvent(BaseModel):
    """A single event in the engagement journal. P4 — event-sourced state.

    Persistence: append-only JSONL at engagements/<tenant>/journal.jsonl
    State: derived from replay of events. Never mutated directly.

    Phase-3 mapping: this struct mirrors lago's `Record<E>` shape for clean
    transcription to Rust.
    """

    event_id: str = Field(default_factory=_new_event_id)  # ulid (sortable, time-ordered)
    timestamp: datetime = Field(default_factory=_utcnow)
    kind: EventKind
    actor: str
    stage: str
    payload: dict[str, object]
    parent_event_id: str | None = None

    @model_validator(mode="after")
    def payload_matches_kind(self) -> JournalEvent:
        """Validate payload shape against the declared kind's schema.

        Phase A.3 of M1+M2+M3 plan. Closes Gap #11 — replaces the loose
        dict[str, object] contract with per-kind typed validation. Renderers
        and replay can rely on stable field names. Imported lazily to break
        the circular dependency core.types → core.events → core.types.
        """
        from core.events import payload_for

        try:
            schema = payload_for(self.kind)
        except KeyError:
            # Unregistered kind — allow free-form for forward compatibility,
            # but this should never happen in practice once the registry is
            # complete (test_kind_count_matches_registry asserts that).
            return self
        schema.model_validate(self.payload)
        return self


# ----------------------------------------------------------------------------
# Layer 4 — Review gate (P5)
# ----------------------------------------------------------------------------


class StageReview(BaseModel):
    """The review-gate artifact at the boundary of each stage. P5.

    In autonomous mode, the runner blocks until decision == "approved".
    In CLI mode, `phronesis review <stage>` surfaces this for the consultant.
    """

    stage: Literal["intake", "scan", "ideate", "prioritize", "roadmap"]
    summary: str
    artifacts: list[str]  # paths to rendered deliverables awaiting review
    open_questions: list[str]
    proposed_next_actions: list[str]
    reviewer: str | None = None
    decision: Literal["pending", "approved", "revised"] | None = None
    reviewer_notes: str | None = None
    reviewed_at: datetime | None = None


# ----------------------------------------------------------------------------
# Layer 5 — Engagement context (P6)
# ----------------------------------------------------------------------------


class TenantContext(BaseModel):
    """Per-tenant engagement context. P6 — never in substrate repo.

    Lives at engagements/<tenant_slug>/tenant.yaml (gitignored).
    Substrate has no awareness of tenant identity — passed in at runtime.
    """

    tenant_slug: str
    name: str
    industry: Literal[
        "banking",
        "insurance",
        "fin-services",
        "construction",
        "real-estate",
        "retail",
        "healthcare",
        "energy-utilities",
        "tech",
        "other",
    ]
    region: str  # ISO 3166-1 alpha-2
    revenue_band: Literal["<10M", "10-100M", "100M-1B", "1B+"]
    headcount_band: Literal["<50", "50-500", "500-5000", "5000+"]
    sponsor: str
    sponsor_role: str
    engagement_scope: str
    starts_at: datetime
    target_duration_weeks: int


class FrameworkSelection(BaseModel):
    """A framework chosen for a particular engagement. P7.

    The skill's framework_selector primitive (M1) proposes a slate; the
    consultant approves/revises. Each selection carries rationale.
    Engagement caps at 5 (linter warning above; M3).
    """

    framework_ref: str
    selected_at_stage: str
    rationale: str
    selected_by: str
