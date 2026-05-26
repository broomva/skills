"""StageBase — common interface for the 5 engagement stages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from core.engagement import Engagement


class StageBase(ABC):
    """Abstract base for all stage runners.

    Subclasses set:
      - `SLUG`: the stage identifier ("intake", "scan", "ideate",
        "prioritize", "roadmap")
      - `NEXT_STAGE`: which stage `STAGE_REVIEW_APPROVED` should advance to,
        or None for the terminal stage

    Subclasses implement:
      - `run(engagement, **inputs)`: the stage's primary work
      - `request_review(engagement, summary)`: emits STAGE_REVIEW_REQUESTED
        and any required gate checks (L1, L2, L4, L5)
    """

    SLUG: ClassVar[str]
    NEXT_STAGE: ClassVar[str | None]

    @abstractmethod
    def run(self, engagement: Engagement, **inputs: object) -> None:
        """Execute the stage. Mutates engagement.journal via emit() only."""
        ...

    @abstractmethod
    def request_review(self, engagement: Engagement, summary: str) -> None:
        """Emit STAGE_REVIEW_REQUESTED. Always last step before stage handoff.

        Implementations enforce the stage's L-rule gate before emitting.
        """
        ...
