"""Phronesis M7 — extraction pipeline.

Transforms a concluded engagement journal into anonymized knowledge-graph
candidates that flow through the bookkeeping P8 review queue and land as
entity pages in `research/entities/{industry-pattern,framework-refinement}/`.

Hook point: `ENGAGEMENT_CONCLUDED` event (per `feedback_bookkeeping_reflexive.md`)
triggers `extract_and_queue(engagement)`. Each emitted candidate carries:
  - anonymized text (per `core/anonymize.py::AnonymizationPolicy`),
  - candidate entity slug + type (industry-pattern / framework-refinement),
  - provenance pointing back to the engagement journal,
  - bookkeeping P8 score (novelty + specificity + relevance).

Candidates score ≥5/9 land in `research/entities/`. Below-threshold candidates
go to the review queue at `~/.config/phronesis/extraction-queue/` for human
inspection. We never file entities directly — every candidate flows through
the bookkeeping gate per the anti-pattern in `feedback_bookkeeping_reflexive.md`.

The 14-canary-token release gate runs against the anonymizer output via
`tests/integration/test_anonymization_canary.py`. A leaking token blocks
the push.
"""

from __future__ import annotations

from core.extraction.anonymizer import (
    EngagementAnonymizer,
    anonymize_engagement_text,
)
from core.extraction.candidates import (
    ExtractionCandidate,
    extract_framework_refinements,
    extract_industry_patterns,
)
from core.extraction.pipeline import (
    ENTITY_GRAPH_ROOT,
    EXTRACTION_QUEUE_ROOT,
    ExtractionResult,
    extract_and_queue,
    on_engagement_concluded,
)

__all__ = [
    "EXTRACTION_QUEUE_ROOT",
    "ENTITY_GRAPH_ROOT",
    "EngagementAnonymizer",
    "ExtractionCandidate",
    "ExtractionResult",
    "anonymize_engagement_text",
    "extract_and_queue",
    "extract_framework_refinements",
    "extract_industry_patterns",
    "on_engagement_concluded",
]
