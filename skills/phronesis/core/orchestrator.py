"""Render orchestrator — produces all 7 deliverables for an Engagement.

The orchestrator runs the linter BEFORE persisting deliverables. If
`lint_result.has_errors == True`, the function returns the rendered
markdown in-memory but does NOT write to disk. Caller must inspect the
LintResult and decide whether to re-render after fixes or override.

This is the M3 acceptance gate: the bision-prevention release-gate test
(Phase E) drives an engagement end-to-end, calls render_all(), and
asserts `lint_result.has_errors == False` on the canonical synthetic
fixture.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.engagement import Engagement
from core.linter import LintResult, lint_engagement
from core.render import render

DELIVERABLE_SLUGS: tuple[str, ...] = (
    "maturity-report",
    "capability-heatmap",
    "use-case-dossier",
    "impact-effort-matrix",
    "roi-model",
    "innovation-roadmap",
    "pilot-plan",
)

# Per-deliverable context builders. Each returns the dict that the
# corresponding Jinja2 template expects. Phase 1 builders pull from the
# engagement state + journal events; M4 will plumb richer context (typed
# aggregates) once stages produce them in-memory rather than via journal-only.
ContextBuilder = Callable[[Engagement, dict[str, Any]], dict[str, Any]]


def _base_context(eng: Engagement, extras: dict[str, Any]) -> dict[str, Any]:
    """Common fields every deliverable can rely on."""
    return {
        "tenant": eng.tenant,
        "generated_at": extras.get("generated_at", "TBD"),
    }


def render_all(
    engagement: Engagement,
    output_dir: Path,
    *,
    extra_context: dict[str, Any] | None = None,
    write: bool = True,
) -> tuple[dict[str, Path], LintResult]:
    """Render all 7 deliverables for an engagement.

    Args:
        engagement: the Engagement aggregate (tenant + journal).
        output_dir: where rendered markdown lands (created if missing).
        extra_context: optional caller-provided context that Phase 1 stages
            can't yet derive from journal alone (rendered ROI cells with
            sensitivity bands, RICE-ranked use cases for impact-effort, etc.).
        write: when False, render in-memory but don't persist (preview mode).

    Returns:
        (slug → output Path, LintResult). If `lint_result.has_errors == True`
        AND `write == True`, this function STILL writes the files but the
        caller is expected to inspect lint_result before treating them as
        publication-ready. Use `write=False` to preview without writing.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    extras = extra_context or {}
    contexts = _build_all_contexts(engagement, extras)

    paths: dict[str, Path] = {}
    for slug, ctx in contexts.items():
        rendered = render(slug, ctx)
        path = output_dir / f"{slug}.md"
        if write:
            path.write_text(rendered)
        paths[slug] = path

    lint_result = lint_engagement(engagement)
    return paths, lint_result


def render_with_gate(
    engagement: Engagement,
    output_dir: Path,
    *,
    extra_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Path], LintResult]:
    """Lint-GATED render: writes ONLY if zero L-errors.

    This is the publication path. If L1-L5 + P3/P7/P8 lint clean, every
    deliverable is written to output_dir. Otherwise output_dir is left
    untouched (no partial state) and the caller gets back the LintResult
    to surface to the user.
    """
    extras = extra_context or {}
    # Lint first — cheaper than rendering.
    lint_result = lint_engagement(engagement)
    if lint_result.has_errors:
        return {}, lint_result

    output_dir.mkdir(parents=True, exist_ok=True)
    contexts = _build_all_contexts(engagement, extras)
    paths: dict[str, Path] = {}
    for slug, ctx in contexts.items():
        rendered = render(slug, ctx)
        path = output_dir / f"{slug}.md"
        path.write_text(rendered)
        paths[slug] = path
    return paths, lint_result


def _build_all_contexts(eng: Engagement, extras: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build per-deliverable context dicts from engagement + extras.

    Phase 1 contract: callers supply the typed-primitive lists via
    `extra_context` because the journal stores serialized dicts not
    Pydantic objects. M4+ may move this assembly into the stages
    themselves, with the orchestrator just orchestrating.
    """
    base = _base_context(eng, extras)

    # Each deliverable picks its required keys from extras. Missing keys
    # surface via Jinja2 strict-undefined at render time — orchestrator
    # doesn't second-guess templates.
    contexts: dict[str, dict[str, Any]] = {}
    for slug in DELIVERABLE_SLUGS:
        ctx = {**base, **extras}
        contexts[slug] = ctx
    return contexts


# Convenience helpers for callers building extra_context -------------------


def build_roi_totals(roi_cells: list[Any]) -> dict[str, Decimal]:
    """Sum up Year-1 totals across RoiCells. Used to populate the
    `total_revenue` / `total_investment` / `total_net` keys for
    templates/roi-model.md.j2."""
    if not roi_cells:
        return {
            "total_revenue": Decimal("0"),
            "total_investment": Decimal("0"),
            "total_net": Decimal("0"),
        }
    return {
        "total_revenue": sum((c.revenue_impact for c in roi_cells), start=Decimal("0")),
        "total_investment": sum((c.investment for c in roi_cells), start=Decimal("0")),
        "total_net": sum((c.net for c in roi_cells), start=Decimal("0")),
    }
