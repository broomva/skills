"""Stage 4 — Prioritization.

Consumes UseCases + RICE/ICE/WSJF + ROI frameworks; produces ranked Scores,
RoiCells, and the Impact-Effort Matrix deliverable. CFO validates ROI
assumptions and picks top 3-5 before transition to Stage 5 (Roadmap).

Gate: at least one USE_CASE_PRIORITIZED event with rice_score before review.
"""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from core.engagement import Engagement
from core.types import EventKind, RoiCell
from stages.base import StageBase


class PrioritizationStage(StageBase):
    """Stage 4 — Prioritization: rank top use cases via RICE/ICE/WSJF + ROI."""

    SLUG: ClassVar[str] = "prioritize"
    NEXT_STAGE: ClassVar[str] = "roadmap"

    def run(self, engagement: Engagement, **inputs: object) -> None:
        """No-op marker."""

    def prioritize_use_case(
        self,
        engagement: Engagement,
        *,
        use_case_id: str,
        rice_score: float,
        roi_cell: RoiCell,
        rank: int,
    ) -> str:
        """Emit USE_CASE_PRIORITIZED with RICE score + Year-1 net + rank."""
        return engagement.emit(
            EventKind.USE_CASE_PRIORITIZED,
            "prioritize",
            {
                "use_case_id": use_case_id,
                "rice_score": rice_score,
                "year1_net": str(roi_cell.net),
                "rank": rank,
            },
        )

    def render_impact_effort_matrix(self, engagement: Engagement, output_path: str) -> str:
        """Emit DELIVERABLE_RENDERED for the Impact-Effort Matrix.

        M3 will wire the actual Jinja2 renderer. Phase 1 just emits the
        event so replay can reconstruct the timeline.
        """
        return engagement.emit(
            EventKind.DELIVERABLE_RENDERED,
            "prioritize",
            {
                "slug": "impact-effort-matrix",
                "output_path": output_path,
                "linter_passed": True,
                "lint_warnings": [],
            },
        )

    def request_review(self, engagement: Engagement, summary: str) -> None:
        """Emit STAGE_REVIEW_REQUESTED.

        Gate: at least one use case prioritized.
        """
        state = engagement.state()
        if not state.use_cases_prioritized:
            raise ValueError(
                "Stage 4 review gate: at least one use case must be prioritized "
                "before requesting review. Call prioritize_use_case() first."
            )

        engagement.emit(
            EventKind.STAGE_REVIEW_REQUESTED,
            "prioritize",
            {
                "stage": "prioritize",
                "reviewer": engagement.tenant.sponsor,
                "summary": summary,
                "artifacts": [
                    "prioritize/impact-effort-matrix.md",
                    "prioritize/roi-model.md",
                ],
                "deadline": None,
            },
        )

    @staticmethod
    def compute_year1_net(revenue_impact: Decimal, investment: Decimal) -> Decimal:
        """Helper: Year-1 net cash flow. Used by callers to build RoiCell."""
        return revenue_impact - investment
