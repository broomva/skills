"""Candidate extraction from concluded engagement journals.

Two extractors:
  - `extract_industry_patterns()` — recurring patterns within an industry
    (e.g. "LATAM mid-market banks with no production ML score 2.0±0.3 on
    customer-facing AI maturity"). Source: maturity-dimension scores +
    findings + thesis economic_lever, grouped by `tenant.industry`.
  - `extract_framework_refinements()` — empirical adjustments to canonical
    frameworks discovered during the engagement (e.g. "RICE under-weights
    regulatory-pressure use cases in financial services — recommend +25%
    impact bonus for `regulatory-pressure` source"). Source: deltas between
    rendered ROI vs RICE rank, ideation_source distribution, observed lift
    on capability-heatmap target_score vs baseline assumptions.

Each candidate carries enough provenance to round-trip back to the
journal event(s) that produced it. We never include raw text without
anonymization — the anonymizer wrapper is applied before the candidate
ever leaves this module.

Phase 1 scope: rule-based extractors. Phase 2 will swap in LLM extractors
once a corpus of ≥3 concluded engagements per industry exists.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core.engagement import Engagement
from core.extraction.anonymizer import EngagementAnonymizer
from core.types import EventKind

EntityType = Literal["industry-pattern", "framework-refinement"]


class ExtractionCandidate(BaseModel):
    """A pre-bookkeeping candidate for a knowledge-graph entity.

    Fields mirror the bookkeeping `RawItem` shape so adapter glue stays
    minimal — `pipeline.py::_to_raw_item()` builds a bookkeeping RawItem
    directly from the candidate.

    Attributes:
        slug: kebab-case proposed entity slug (e.g.
            `latam-mid-market-banking-customer-ai-gap`).
        entity_type: which `research/entities/<type>/` directory the entity
            lands in if the bookkeeping P8 score lets it through.
        content: anonymized body text (Bloomberg industry color — no
            tenant identity).
        quote: the source phrase that surfaced the pattern (anonymized).
        title: short human-readable title for the entity page.
        provenance_event_ids: ULIDs of the journal events that produced
            this candidate. Round-trippable.
        industry: the industry signature for industry-pattern candidates
            (`tenant.industry`). None for framework-refinement candidates.
        framework_ref: the canonical framework being refined
            (e.g. `framework:rice`). None for industry-pattern candidates.
        signals: structured payload — numeric deltas, observed-vs-expected
            ratios, etc. that the bookkeeping scorer can pick up.
    """

    slug: str
    entity_type: EntityType
    content: str
    quote: str
    title: str
    provenance_event_ids: list[str]
    industry: str | None = None
    framework_ref: str | None = None
    signals: dict[str, float | str] = Field(default_factory=dict)


# ----------------------------------------------------------------------------
# Industry-pattern extraction
# ----------------------------------------------------------------------------


def extract_industry_patterns(
    engagement: Engagement,
    anonymizer: EngagementAnonymizer,
) -> list[ExtractionCandidate]:
    """Surface industry-pattern candidates from a concluded engagement.

    Phase 1 rules:
      1. Each scored maturity dimension below 2.5 on the canonical 1-5
         scale becomes a candidate ("industry X dimension Y under-developed").
      2. The strategic-thesis economic_lever becomes one industry-aware
         candidate ("industry X tenants commonly recover value via Z").

    Returns at most `n_dimensions + 1` candidates. The bookkeeping scorer
    decides which survive into `research/entities/industry-pattern/`.
    """
    candidates: list[ExtractionCandidate] = []
    industry = engagement.tenant.industry

    # Rule 1 — dimension under-development across industry.
    for ev in engagement.journal.events:
        if ev.kind != EventKind.MATURITY_DIMENSION_SCORED:
            continue
        dim_name_raw = ev.payload.get("dimension_name", "")
        current_raw = ev.payload.get("current_value", 0.0)
        target_raw = ev.payload.get("target_value", 0.0)
        gap_summary_raw = ev.payload.get("gap_summary", "")
        if not isinstance(dim_name_raw, str) or not dim_name_raw:
            continue
        try:
            current = float(current_raw) if isinstance(current_raw, (int, float, str)) else 0.0
            target = float(target_raw) if isinstance(target_raw, (int, float, str)) else 0.0
        except (TypeError, ValueError):
            continue

        if current >= 2.5:
            # Above-threshold dimensions don't surface as under-development
            # patterns; they're industry-baseline, not industry-pattern.
            continue

        gap_summary = gap_summary_raw if isinstance(gap_summary_raw, str) else ""

        body = (
            f"Industry pattern observed in {industry}: "
            f"dimension '{dim_name_raw}' scores {current:.1f}/5 against "
            f"benchmark target {target:.1f}. Observed gap: {gap_summary}. "
            f"Pattern recurs across same-industry tenants — surfaced once, "
            f"promotable when ≥3 industry-matched engagements reproduce."
        )
        quote = f"{dim_name_raw} at {current:.1f}/5: {gap_summary}"

        candidates.append(
            ExtractionCandidate(
                slug=_industry_pattern_slug(industry, dim_name_raw),
                entity_type="industry-pattern",
                content=anonymizer.redact(body),
                quote=anonymizer.redact(quote),
                title=f"{industry}: {dim_name_raw} under-development",
                provenance_event_ids=[ev.event_id],
                industry=industry,
                signals={
                    "dimension": dim_name_raw,
                    "current_score": current,
                    "target_score": target,
                    "gap_magnitude": target - current,
                },
            )
        )

    # Rule 2 — industry-aware economic lever pattern.
    thesis_ev = _find_event(engagement, EventKind.STRATEGIC_THESIS_DECLARED)
    if thesis_ev is not None:
        lever_raw = thesis_ev.payload.get("economic_lever", "")
        lever_kind_raw = thesis_ev.payload.get("lever_kind", "")
        magnitude_raw = thesis_ev.payload.get("magnitude_estimate", "")
        lever = lever_raw if isinstance(lever_raw, str) else ""
        lever_kind = lever_kind_raw if isinstance(lever_kind_raw, str) else ""
        magnitude = magnitude_raw if isinstance(magnitude_raw, str) else "0"

        if lever:
            body = (
                f"Industry pattern observed in {industry}: tenants surface "
                f"a {lever_kind} economic lever — '{lever}'. Magnitude "
                f"estimate (anonymized to band): see signals. Surfaced once; "
                f"promotion to industry-pattern entity requires ≥3 same-"
                f"industry engagements with the same lever_kind."
            )
            candidates.append(
                ExtractionCandidate(
                    slug=_industry_lever_slug(industry, lever_kind),
                    entity_type="industry-pattern",
                    content=anonymizer.redact(body),
                    quote=anonymizer.redact(lever),
                    title=f"{industry}: {lever_kind}-lever pattern",
                    provenance_event_ids=[thesis_ev.event_id],
                    industry=industry,
                    signals={
                        "lever_kind": lever_kind,
                        "magnitude_band_raw": magnitude,
                    },
                )
            )

    return candidates


# ----------------------------------------------------------------------------
# Framework-refinement extraction
# ----------------------------------------------------------------------------


def extract_framework_refinements(
    engagement: Engagement,
    anonymizer: EngagementAnonymizer,
) -> list[ExtractionCandidate]:
    """Surface framework-refinement candidates from a concluded engagement.

    Phase 1 rules:
      1. If 2+ use cases share the same `ideation_source`, surface a RICE
         refinement candidate ("source X over-represented in industry Y —
         consider weighting").
      2. If the top-ranked use case by RICE differs from the top by year1_net
         ROI, surface a delta candidate ("RICE rank vs ROI rank diverges
         for industry Y — calibrate impact weighting").
    """
    candidates: list[ExtractionCandidate] = []
    industry = engagement.tenant.industry

    # Gather use-case events with ideation source + RICE rank + ROI.
    proposed: dict[str, dict[str, object]] = {}
    prioritized: list[dict[str, object]] = []

    for ev in engagement.journal.events:
        if ev.kind == EventKind.USE_CASE_PROPOSED:
            uc_id = ev.payload.get("use_case_id")
            if isinstance(uc_id, str):
                proposed[uc_id] = {**ev.payload, "_event_id": ev.event_id}
        elif ev.kind == EventKind.USE_CASE_PRIORITIZED:
            uc_id = ev.payload.get("use_case_id")
            if isinstance(uc_id, str):
                prioritized.append({**ev.payload, "_event_id": ev.event_id})

    # Rule 1 — ideation source over-representation in same engagement.
    sources: dict[str, list[str]] = {}
    source_event_ids: dict[str, list[str]] = {}
    for uc_id, pl in proposed.items():
        source_raw = pl.get("ideation_source", "")
        if not isinstance(source_raw, str) or not source_raw:
            continue
        sources.setdefault(source_raw, []).append(uc_id)
        ev_id = pl.get("_event_id")
        if isinstance(ev_id, str):
            source_event_ids.setdefault(source_raw, []).append(ev_id)

    for source, uc_ids in sources.items():
        if len(uc_ids) < 2:
            continue
        body = (
            f"Framework refinement candidate: in this {industry} engagement, "
            f"{len(uc_ids)} of {len(proposed)} use cases originated from "
            f"ideation source '{source}'. RICE assumes uniform-priority "
            f"sourcing; over-represented sources may need explicit "
            f"weighting in same-industry calibrations. Surfaced once; "
            f"promotion to framework-refinement entity requires ≥3 "
            f"engagements showing the same source skew."
        )
        candidates.append(
            ExtractionCandidate(
                slug=_framework_rice_source_slug(industry, source),
                entity_type="framework-refinement",
                content=anonymizer.redact(body),
                quote=anonymizer.redact(f"{len(uc_ids)}/{len(proposed)} use cases from '{source}'"),
                title=f"RICE: {source} weighting in {industry}",
                provenance_event_ids=source_event_ids.get(source, []),
                framework_ref="framework:rice",
                signals={
                    "ideation_source": source,
                    "use_case_count": float(len(uc_ids)),
                    "total_proposed": float(len(proposed)),
                    "share": float(len(uc_ids)) / float(len(proposed) or 1),
                },
            )
        )

    # Rule 2 — RICE rank vs ROI year1_net divergence at rank 1.
    if prioritized:
        try:
            top_rice_uc = min(
                prioritized,
                key=_rank_key,
            )
            # Top by year1_net = max
            top_roi_uc = max(
                prioritized,
                key=lambda p: _decimal_str_to_float(p.get("year1_net", "0")),
            )
        except (TypeError, ValueError):
            top_rice_uc = None
            top_roi_uc = None

        if (
            top_rice_uc is not None
            and top_roi_uc is not None
            and top_rice_uc.get("use_case_id") != top_roi_uc.get("use_case_id")
        ):
            ev_ids = [
                eid
                for eid in (
                    _event_id_or_none(top_rice_uc),
                    _event_id_or_none(top_roi_uc),
                )
                if eid is not None
            ]
            body = (
                f"Framework refinement candidate: in this {industry} "
                f"engagement, RICE top-ranked use case differs from ROI "
                f"year-1-net top. RICE's reach×impact×confidence/effort "
                f"calculation may under-weight near-term revenue capture "
                f"in this industry. Surfaced once; promotion requires ≥3 "
                f"same-industry engagements with the same RICE/ROI rank "
                f"divergence."
            )
            candidates.append(
                ExtractionCandidate(
                    slug=_framework_rice_roi_slug(industry),
                    entity_type="framework-refinement",
                    content=anonymizer.redact(body),
                    quote=anonymizer.redact(f"RICE-top vs ROI-top diverge in {industry}"),
                    title=f"RICE: RICE-vs-ROI rank gap in {industry}",
                    provenance_event_ids=list(dict.fromkeys(ev_ids)),
                    framework_ref="framework:rice",
                    signals={
                        "industry": industry,
                        "rice_top_use_case": str(top_rice_uc.get("use_case_id", "")),
                        "roi_top_use_case": str(top_roi_uc.get("use_case_id", "")),
                    },
                )
            )

    return candidates


# ----------------------------------------------------------------------------
# Slug builders
# ----------------------------------------------------------------------------


def _industry_pattern_slug(industry: str, dimension: str) -> str:
    """Build a deterministic slug for an industry-dimension pattern.

    Format: `<industry>-<dimension-kebab>-pattern`.
    """
    return f"{_kebab(industry)}-{_kebab(dimension)}-pattern"


def _industry_lever_slug(industry: str, lever_kind: str) -> str:
    """Build a deterministic slug for an industry-lever pattern."""
    return f"{_kebab(industry)}-{_kebab(lever_kind)}-lever-pattern"


def _framework_rice_source_slug(industry: str, source: str) -> str:
    """Build a deterministic slug for a RICE source-weighting refinement."""
    return f"rice-{_kebab(source)}-weight-{_kebab(industry)}"


def _framework_rice_roi_slug(industry: str) -> str:
    """Build a deterministic slug for a RICE-vs-ROI divergence refinement."""
    return f"rice-roi-rank-gap-{_kebab(industry)}"


def _kebab(text: str) -> str:
    """Convert text to kebab-case slug."""
    out: list[str] = []
    prev_dash = False
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    slug = "".join(out).strip("-")
    return slug or "unknown"


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _find_event(engagement: Engagement, kind: EventKind):  # type: ignore[no-untyped-def]
    for ev in engagement.journal.events:
        if ev.kind == kind:
            return ev
    return None


def _decimal_str_to_float(raw: object) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return 0.0
    return 0.0


def _rank_key(payload: dict[str, object]) -> float:
    """Sort key — extract a numeric `rank` from a journal payload."""
    rank = payload.get("rank", 999)
    if isinstance(rank, (int, float, str)):
        try:
            return float(rank)
        except (TypeError, ValueError):
            return 999.0
    return 999.0


def _event_id_or_none(payload: dict[str, object]) -> str | None:
    """Return the `_event_id` from a payload only if it's a non-empty string."""
    eid = payload.get("_event_id")
    if isinstance(eid, str) and eid:
        return eid
    return None


__all__ = [
    "EntityType",
    "ExtractionCandidate",
    "extract_framework_refinements",
    "extract_industry_patterns",
]
