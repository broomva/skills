"""Stage 2 — Maturity Scan.

Consumes selected maturity frameworks + interview transcripts; produces
MaturityDimension scores and CapabilityCells. Reviewed by stakeholders
who validate the gap framing before transition to Stage 3 (Ideation).

Gate: at least one MaturityDimension scored before request_review.
"""

from __future__ import annotations

from typing import ClassVar

from core.engagement import Engagement
from core.types import EventKind, MaturityDimension
from stages.base import StageBase


class MaturityScanStage(StageBase):
    """Stage 2 — Maturity Scan: score current vs target on selected frameworks."""

    SLUG: ClassVar[str] = "scan"
    NEXT_STAGE: ClassVar[str] = "ideate"

    def run(self, engagement: Engagement, **inputs: object) -> None:
        """Stage 2 has no init event of its own — work begins with score_dimension.

        Phase-1 stages stay declarative: callers invoke score_dimension() once
        per framework dimension. Stage 2's "run" is a no-op marker that lets
        a CLI driver detect the stage entered.
        """
        # No-op marker. Future revisions may emit STAGE_ENTERED for richer audit.

    def score_dimension(self, engagement: Engagement, dim: MaturityDimension) -> str:
        """Emit MATURITY_DIMENSION_SCORED for one scored dimension.

        Returns the event_id.
        """
        return engagement.emit(
            EventKind.MATURITY_DIMENSION_SCORED,
            "scan",
            {
                "dimension_name": dim.name,
                "current_value": dim.current_score.value,
                "target_value": dim.target_score.value,
                "framework_ref": dim.framework_ref,
                "gap_summary": dim.gap_summary,
            },
        )

    def request_review(self, engagement: Engagement, summary: str) -> None:
        """Emit STAGE_REVIEW_REQUESTED.

        Gate: at least one MATURITY_DIMENSION_SCORED event must exist in the
        journal at this stage.
        """
        state = engagement.state()
        if not state.maturity_dimensions:
            raise ValueError(
                "Stage 2 review gate: at least one MaturityDimension must be "
                "scored before requesting review. Call score_dimension() first."
            )

        engagement.emit(
            EventKind.STAGE_REVIEW_REQUESTED,
            "scan",
            {
                "stage": "scan",
                "reviewer": engagement.tenant.sponsor,
                "summary": summary,
                "artifacts": [
                    "scan/maturity-report.md",
                    "scan/capability-heatmap.md",
                ],
                "deadline": None,
            },
        )
