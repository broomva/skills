"""Stage 5 — Roadmap Synthesis.

Consumes top use cases + Three Horizons + QuantumBlack ML lifecycle;
produces RoadmapStep[], PilotDesign[] (with BaselineSection[]), and
Recommendation[]. Sponsor approves go/no-go on roadmap + pilot kickoff.

Gates:
  - L4 ADOPTION_METRIC_REQUIRED: every PilotDesign must carry an adoption_metric
  - L5 BASELINE_REQUIRED: every PilotDesign must capture baseline BEFORE pilot start
"""

from __future__ import annotations

from typing import ClassVar

from core.engagement import Engagement
from core.types import (
    BaselineSection,
    EventKind,
    PilotDesign,
    RoadmapStep,
)
from stages.base import StageBase


class RoadmapStage(StageBase):
    """Stage 5 — Roadmap Synthesis: H1/H2/H3 plan + pilot designs + recommendations."""

    SLUG: ClassVar[str] = "roadmap"
    NEXT_STAGE: ClassVar[str | None] = None  # terminal stage

    def run(self, engagement: Engagement, **inputs: object) -> None:
        """No-op marker."""

    def propose_roadmap_step(self, engagement: Engagement, step: RoadmapStep) -> str:
        """Emit ROADMAP_STEP_PROPOSED for one Three-Horizons step."""
        return engagement.emit(
            EventKind.ROADMAP_STEP_PROPOSED,
            "roadmap",
            {
                "step_id": step.id,
                "horizon": step.horizon,
                "quarter": step.quarter,
                "owner": step.owner,
                "success_gate": step.success_gate,
            },
        )

    def capture_baseline(self, engagement: Engagement, baseline: BaselineSection) -> str:
        """Emit BASELINE_CAPTURED. L5 enforcement: must precede PILOT_STARTED.

        Returns the event_id; the typed payload encodes the BaselineSection
        fields for replay-time validation.
        """
        return engagement.emit(
            EventKind.BASELINE_CAPTURED,
            "roadmap",
            {
                "metric_name": baseline.metric_name,
                "baseline_value": str(baseline.baseline_value),
                "captured_by": baseline.captured_by,
                "measurement_date": baseline.baseline_measurement_date.isoformat(),
            },
        )

    def design_pilot(self, engagement: Engagement, pilot: PilotDesign) -> str:
        """L4 + L5 enforcement happens at PilotDesign construction.

        PilotDesign requires non-empty baseline + adoption_metric (Pydantic
        model validators). This method emits PILOT_STARTED but only after
        verifying the corresponding BASELINE_CAPTURED events exist in the
        journal — no retroactive baselines.
        """
        state = engagement.state()
        baseline_metrics = {b.metric_name for b in pilot.baseline}
        captured = set(state.baselines_captured)
        missing = baseline_metrics - captured
        if missing:
            raise ValueError(
                f"L5 BASELINE_REQUIRED — pilot {pilot.use_case_id} declares "
                f"baselines for metrics {sorted(baseline_metrics)} but the "
                f"journal only has BASELINE_CAPTURED for {sorted(captured)}. "
                f"Missing: {sorted(missing)}. Bision Failure 5 (48% observed): "
                "no retroactive baselines — capture before pilot."
            )

        return engagement.emit(
            EventKind.PILOT_STARTED,
            "roadmap",
            {
                "use_case_id": pilot.use_case_id,
                "pilot_design_ref": f"pilot:{pilot.use_case_id}",
                "start_date": "TBD",  # caller may emit a follow-up event with real date
                "duration_weeks": pilot.duration_weeks,
            },
        )

    def render_deliverables(
        self,
        engagement: Engagement,
        slugs: list[str],
        output_dir: str,
    ) -> list[str]:
        """Emit DELIVERABLE_RENDERED for each deliverable. Returns event_ids.

        M3 will wire the actual Jinja2 renderer. Phase 1 just emits events.
        """
        ids: list[str] = []
        for slug in slugs:
            ids.append(
                engagement.emit(
                    EventKind.DELIVERABLE_RENDERED,
                    "roadmap",
                    {
                        "slug": slug,
                        "output_path": f"{output_dir}/{slug}.md",
                        "linter_passed": True,
                        "lint_warnings": [],
                    },
                )
            )
        return ids

    def conclude(
        self, engagement: Engagement, *, top_pilot: str, deliverable_slugs: list[str]
    ) -> str:
        """Emit ENGAGEMENT_CONCLUDED. Terminal event."""
        state = engagement.state()
        if state.thesis_id is None:
            raise ValueError(
                "Cannot conclude engagement: no StrategicThesis recorded. Did you skip intake?"
            )
        return engagement.emit(
            EventKind.ENGAGEMENT_CONCLUDED,
            "roadmap",
            {
                "stages_approved": 5,
                "thesis_id": state.thesis_id,
                "top_pilot": top_pilot,
                "deliverable_slugs": deliverable_slugs,
            },
        )

    def request_review(self, engagement: Engagement, summary: str) -> None:
        """Emit STAGE_REVIEW_REQUESTED.

        Gate: at least one roadmap step proposed AND at least one baseline
        captured (precondition for any pilot to launch).
        """
        state = engagement.state()
        # We don't track roadmap steps in EngagementState yet; fall back to
        # journal scan. This is acceptable for Phase 1 — M3 may add a
        # roadmap_steps_proposed field to EngagementState.
        steps = [
            ev for ev in engagement.journal.events if ev.kind == EventKind.ROADMAP_STEP_PROPOSED
        ]
        if not steps:
            raise ValueError(
                "Stage 5 review gate: at least one RoadmapStep must be proposed "
                "before requesting review. Call propose_roadmap_step() first."
            )
        if not state.baselines_captured:
            raise ValueError(
                "L5 BASELINE_REQUIRED — Stage 5 review requires at least one "
                "BASELINE_CAPTURED event before any pilot can launch. Call "
                "capture_baseline() for each pilot success metric."
            )

        engagement.emit(
            EventKind.STAGE_REVIEW_REQUESTED,
            "roadmap",
            {
                "stage": "roadmap",
                "reviewer": engagement.tenant.sponsor,
                "summary": summary,
                "artifacts": [
                    "roadmap/innovation-roadmap.md",
                    "roadmap/pilot-plan.md",
                ],
                "deadline": None,
            },
        )
