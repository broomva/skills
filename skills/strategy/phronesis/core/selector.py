"""framework_selector — proposes 2-4 FrameworkSelection picks per engagement.

P7 enforcement: caps active frameworks at ≤5. Each pick carries
human-readable rationale grounded in the framework's purpose.

Algorithm:
1. Map scope_keywords to category coverage (e.g., "maturity assessment" → maturity).
2. Default: at least maturity + prioritization for any AI/digital engagement.
3. For each needed category, pick the industry-preferred framework. Fall back
   to a default if the industry isn't pre-mapped.
4. Skip D-scope frameworks (Phase-2 stubs).
5. Cap at `cap` (default 4); hard cap 5 (P7).
6. Emit FrameworkSelection with rationale + appropriate stage attachment.
"""

from __future__ import annotations

from core.frameworks import load_all
from core.types import FrameworkSelection

_KEYWORD_TO_CATEGORY: dict[str, str] = {
    "maturity assessment": "maturity",
    "maturity": "maturity",
    "ai maturity": "maturity",
    "digital maturity": "maturity",
    "ideation": "ideation",
    "use case ideation": "ideation",
    "use case prioritization": "prioritization",
    "prioritization": "prioritization",
    "roi": "roi",
    "roi modeling": "roi",
    "roi model": "roi",
    "roadmap": "strategy",
    "innovation roadmap": "strategy",
    "pilot": "ai-lifecycle",
    "ai pilot": "ai-lifecycle",
    "pilot plan": "ai-lifecycle",
}

_INDUSTRY_PREFERENCES: dict[str, dict[str, str]] = {
    "banking": {
        "maturity": "mit-cisr-digital",
        "ideation": "jobs-to-be-done",
        "prioritization": "rice",
        "roi": "unit-economics",
        "strategy": "three-horizons",
        "ai-lifecycle": "quantumblack-ml",
    },
    "energy-utilities": {
        "maturity": "gartner-ai",
        "ideation": "value-prop-canvas",
        "prioritization": "rice",
        "roi": "real-options",
        "strategy": "wardley-mapping",
        "ai-lifecycle": "andrew-ng-pipeline",
    },
    "fin-services": {
        "maturity": "mit-cisr-digital",
        "prioritization": "rice",
        "roi": "unit-economics",
        "strategy": "three-horizons",
        "ai-lifecycle": "quantumblack-ml",
    },
    "insurance": {
        "maturity": "mit-cisr-digital",
        "prioritization": "rice",
        "roi": "npv-dcf",
        "strategy": "three-horizons",
        "ai-lifecycle": "quantumblack-ml",
    },
    "construction": {
        "maturity": "gartner-ai",
        "ideation": "value-prop-canvas",
        "prioritization": "ice",
        "roi": "unit-economics",
        "strategy": "three-horizons",
        "ai-lifecycle": "andrew-ng-pipeline",
    },
    # Engagement-driven addition (BRO-1032). AI-infra / runtime / library /
    # chip-design tenants. Surfaced by Broomva Silicon engagement 2026-05-07.
    # Maturity → CHAOSS (OSS project health, not enterprise digital maturity).
    # Strategy → Wardley (tech-evolution explicit).
    # ROI → real-options (option-value framings dominate deep-tech bets).
    "tech": {
        "maturity": "chaoss",
        "ideation": "value-prop-canvas",
        "prioritization": "rice",
        "roi": "real-options",
        "strategy": "wardley-mapping",
        "ai-lifecycle": "quantumblack-ml",
    },
}

_DEFAULT_PREFERENCES: dict[str, str] = {
    "maturity": "mit-cisr-digital",
    "ideation": "jobs-to-be-done",
    "prioritization": "rice",
    "roi": "unit-economics",
    "strategy": "three-horizons",
    "ai-lifecycle": "quantumblack-ml",
}


def _category_to_stage(category: str) -> str:
    return {
        "maturity": "scan",
        "ideation": "ideate",
        "prioritization": "prioritize",
        "roi": "prioritize",
        "strategy": "roadmap",
        "ai-lifecycle": "roadmap",
    }.get(category, "scan")


def propose_frameworks(
    industry: str,
    maturity_band: str,
    scope_keywords: list[str],
    cap: int = 4,
) -> list[FrameworkSelection]:
    """Return 2-4 FrameworkSelection picks ranked by category coverage.

    P7: hard cap at 5 even if caller passes higher. D-scope frameworks
    are excluded — they exist only as relationship targets in Phase 1.
    """
    all_fws = load_all()
    prefs = _INDUSTRY_PREFERENCES.get(industry, _DEFAULT_PREFERENCES)

    needed_categories: set[str] = set()
    for kw in scope_keywords:
        cat = _KEYWORD_TO_CATEGORY.get(kw.lower().strip())
        if cat:
            needed_categories.add(cat)

    # Default coverage: every AI/digital engagement gets at least maturity +
    # prioritization, even if the scope statement doesn't name them.
    needed_categories |= {"maturity", "prioritization"}

    picks: list[FrameworkSelection] = []
    seen_slugs: set[str] = set()
    # Stable iteration order for deterministic selection
    for cat in sorted(needed_categories):
        slug = prefs.get(cat) or _DEFAULT_PREFERENCES.get(cat)
        if not slug or slug in seen_slugs:
            continue
        fw = all_fws.get(slug)
        if fw is None or fw.is_d_scope:
            continue
        rationale = (
            f"{fw.name} ({fw.source_firm}, {fw.source_year}) — chosen for "
            f"{industry} at {maturity_band} maturity because "
            f"{fw.purpose.split('.')[0].strip()}."
        )
        picks.append(
            FrameworkSelection(
                framework_ref=f"framework:{slug}",
                selected_at_stage=_category_to_stage(cat),
                rationale=rationale,
                selected_by="phronesis-selector-v1",
            )
        )
        seen_slugs.add(slug)
        if len(picks) >= cap:
            break

    # P7 hard cap — never exceed 5 active frameworks per engagement.
    return picks[: min(cap, 5)]
