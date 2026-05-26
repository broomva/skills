"""Stage 3 — Use-Case Ideation.

Consumes maturity output + JTBD/VPC frameworks; produces UseCases with
explicit ideation_source (L2) and data_readiness (L3). Sponsor prunes to
~10-15 viable candidates before transition to Stage 4 (Prioritization).

Gate (L2): at least 3 distinct ideation sources across proposed use cases,
AND no more than 50% of cases sourced from NOVELTY. Bision Failure 2
(87% observed) — casos mal priorizados, elección por novedad.
"""

from __future__ import annotations

from collections import Counter
from typing import ClassVar

from core.engagement import Engagement
from core.types import EventKind, IdeationSource, UseCase
from stages.base import StageBase


class IdeationStage(StageBase):
    """Stage 3 — Use-Case Ideation: surface candidate AI/data initiatives."""

    SLUG: ClassVar[str] = "ideate"
    NEXT_STAGE: ClassVar[str] = "prioritize"

    NOVELTY_SHARE_LIMIT: ClassVar[float] = 0.5
    MIN_DISTINCT_SOURCES: ClassVar[int] = 3

    def run(self, engagement: Engagement, **inputs: object) -> None:
        """No-op marker (see scan.py)."""

    def propose_use_case(self, engagement: Engagement, uc: UseCase) -> str:
        """Emit USE_CASE_PROPOSED for one candidate."""
        return engagement.emit(
            EventKind.USE_CASE_PROPOSED,
            "ideate",
            {
                "use_case_id": uc.id,
                "expected_value": str(uc.expected_value),
                "cost_estimate": str(uc.cost_estimate),
                "ideation_source": uc.ideation_source.value,
                "data_readiness_band": uc.data_readiness.readiness_band,
            },
        )

    def request_review(self, engagement: Engagement, summary: str) -> None:
        """Emit STAGE_REVIEW_REQUESTED.

        L2 GATE: ideation diversity rule. Reject if:
          - no use cases proposed, OR
          - fewer than MIN_DISTINCT_SOURCES distinct ideation sources, OR
          - NOVELTY share > NOVELTY_SHARE_LIMIT (50%)
        """
        state = engagement.state()
        if not state.use_cases:
            raise ValueError(
                "Stage 3 review gate: at least one UseCase must be proposed "
                "before requesting review. Call propose_use_case() first."
            )

        sources = [uc.get("ideation_source") for uc in state.use_cases.values()]
        sources_counter = Counter(s for s in sources if isinstance(s, str))
        distinct = len(sources_counter)
        novelty_share = sources_counter.get(IdeationSource.NOVELTY.value, 0) / len(state.use_cases)

        if distinct < self.MIN_DISTINCT_SOURCES:
            raise ValueError(
                f"L2 DIVERSE_IDEATION_SOURCES — only {distinct} distinct ideation "
                f"sources across {len(state.use_cases)} use cases (min "
                f"{self.MIN_DISTINCT_SOURCES}). Bision Failure 2 (87% observed): "
                "casos mal priorizados — broaden source mix."
            )
        if novelty_share > self.NOVELTY_SHARE_LIMIT:
            raise ValueError(
                f"L2 DIVERSE_IDEATION_SOURCES — NOVELTY share {novelty_share:.0%} "
                f"exceeds {self.NOVELTY_SHARE_LIMIT:.0%} limit. Bision Failure 2: "
                "elección por novedad. Surface business-pain / data-opportunity / "
                "regulatory-pressure / competitive-response candidates."
            )

        engagement.emit(
            EventKind.STAGE_REVIEW_REQUESTED,
            "ideate",
            {
                "stage": "ideate",
                "reviewer": engagement.tenant.sponsor,
                "summary": summary,
                "artifacts": ["ideate/use-case-dossier.md"],
                "deadline": None,
            },
        )
