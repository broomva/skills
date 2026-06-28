"""phronesis CLI — consultant-in-the-loop runtime (Phase 1 minimum).

Phase 1 commands (this file):
  init            create a new engagement scaffold under engagements/<slug>/
  status          load journal.jsonl + print derived state
  lint            run L1-L5 + P3/P7/P8 linter on the persisted journal
  render          render all 7 deliverables via the orchestrator (lint-gated)

NOT yet wired in CLI (Phase 1 ships them via the Python API):
  intake / scan / ideate / prioritize / roadmap / review
The stage commands need richer per-stage input parsing (interview transcripts,
framework-selection slates, RoiCell construction) that lands in M4. For now,
construct stages programmatically:

    from stages.intake import IntakeStage
    from runners.cli.io import load_engagement
    eng = load_engagement("tropico-renovables")
    intake = IntakeStage()
    intake.declare_thesis(eng, my_thesis)

Pause/replay/audit/bookkeep — Phase 2 (M5/M7).

Persistence layout per engagement (P6 — gitignored):
  engagements/<slug>/
    tenant.yaml          tenant context (created by `init`)
    journal.jsonl        append-only event log
    deliverables/        rendered .md files (created by `render`)
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import click

from runners.cli.commands.bookkeep import bookkeep as bookkeep_cmd
from runners.cli.io import (
    ENGAGEMENTS_ROOT,
    journal_path,
    load_engagement,
    save_tenant,
)


@click.group()
@click.version_option(package_name="phronesis", message="%(version)s")
def cli() -> None:
    """phronesis — AI-native advisory practice CLI.

    Run `phronesis <command> --help` for command-specific guidance.
    """


cli.add_command(bookkeep_cmd)


@cli.command()
@click.argument("tenant_slug")
@click.option("--name", required=True, help="Tenant display name")
@click.option(
    "--industry",
    type=click.Choice(
        [
            "banking",
            "insurance",
            "fin-services",
            "construction",
            "real-estate",
            "retail",
            "healthcare",
            "energy-utilities",
            "other",
        ]
    ),
    required=True,
)
@click.option("--region", required=True, help="ISO 3166-1 alpha-2 (e.g. CO, MX)")
@click.option(
    "--revenue-band",
    type=click.Choice(["<10M", "10-100M", "100M-1B", "1B+"]),
    required=True,
)
@click.option(
    "--headcount-band",
    type=click.Choice(["<50", "50-500", "500-5000", "5000+"]),
    required=True,
)
@click.option("--sponsor", required=True, help="Sponsor name (CDO/COO/CFO equivalent)")
@click.option("--sponsor-role", required=True, help="Sponsor's role title")
@click.option("--scope", required=True, help="One-paragraph engagement scope")
@click.option(
    "--target-duration-weeks",
    type=int,
    required=True,
    help="Target engagement length in weeks",
)
def init(
    tenant_slug: str,
    name: str,
    industry: str,
    region: str,
    revenue_band: str,
    headcount_band: str,
    sponsor: str,
    sponsor_role: str,
    scope: str,
    target_duration_weeks: int,
) -> None:
    """Create a new engagement scaffold.

    Example:
        phronesis init tropico-renovables \\
            --name "Tropico Renovables S.A.S." \\
            --industry energy-utilities --region CO \\
            --revenue-band "<10M" --headcount-band "50-500" \\
            --sponsor "Catalina Vélez" --sponsor-role COO \\
            --scope "62 MW renewable portfolio" \\
            --target-duration-weeks 10
    """
    # Late import keeps `phronesis --help` fast.
    from core.engagement import Engagement, EngagementJournal
    from core.types import EventKind, TenantContext

    tenant_dir = ENGAGEMENTS_ROOT / tenant_slug
    if tenant_dir.exists():
        click.echo(
            f"Engagement '{tenant_slug}' already exists at {tenant_dir}. "
            "Aborting to protect the existing journal.",
            err=True,
        )
        sys.exit(1)

    tenant = TenantContext(
        tenant_slug=tenant_slug,
        name=name,
        industry=industry,  # type: ignore[arg-type]
        region=region,
        revenue_band=revenue_band,  # type: ignore[arg-type]
        headcount_band=headcount_band,  # type: ignore[arg-type]
        sponsor=sponsor,
        sponsor_role=sponsor_role,
        engagement_scope=scope,
        starts_at=datetime.now(UTC),
        target_duration_weeks=target_duration_weeks,
    )
    save_tenant(tenant_slug, tenant)

    eng = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
    eng.emit(
        EventKind.ENGAGEMENT_STARTED,
        "intake",
        {
            "tenant_slug": tenant_slug,
            "scope": scope,
            "sponsor": sponsor,
            "target_duration_weeks": target_duration_weeks,
        },
    )
    eng.journal.save_jsonl(journal_path(tenant_slug))

    click.echo(f"Created engagement '{tenant_slug}' at {tenant_dir}")
    click.echo(f"  tenant.yaml   {ENGAGEMENTS_ROOT / tenant_slug / 'tenant.yaml'}")
    click.echo(f"  journal.jsonl {journal_path(tenant_slug)}")
    click.echo("Next: declare a strategic thesis. Phase 1 — use the Python API:")
    click.echo("  from stages.intake import IntakeStage")
    click.echo("  intake = IntakeStage()")
    click.echo("  intake.declare_thesis(eng, my_thesis)")


@cli.command()
@click.argument("tenant_slug")
def status(tenant_slug: str) -> None:
    """Print derived engagement state from the journal."""
    eng = load_engagement(tenant_slug)
    s = eng.state()
    click.echo(f"Engagement: {tenant_slug}")
    click.echo(f"  Tenant:        {eng.tenant.name} ({eng.tenant.industry}/{eng.tenant.region})")
    click.echo(f"  Sponsor:       {eng.tenant.sponsor} ({eng.tenant.sponsor_role})")
    click.echo(f"  Current stage: {s.current_stage}")
    click.echo(f"  Concluded:     {s.is_concluded}")
    declared = "declared" if s.thesis_id else "NOT declared"
    click.echo(f"  Thesis:        {declared} (id={s.thesis_id})")
    click.echo(f"  Frameworks:    {', '.join(s.frameworks_active) or '(none)'}")
    click.echo(f"  Maturity dims: {len(s.maturity_dimensions)}")
    click.echo(f"  Use cases:     {len(s.use_cases)} ({len(s.use_cases_prioritized)} prioritized)")
    click.echo(f"  Baselines:     {len(s.baselines_captured)}")
    click.echo(f"  Deliverables:  {len(s.deliverables_rendered)}")
    if s.review_pending:
        click.echo(f"  Review pending: {s.review_pending}")
    click.echo(f"  Journal events: {len(eng.journal.events)}")


@cli.command(name="lint")
@click.argument("tenant_slug")
@click.option(
    "--strict",
    is_flag=True,
    help="Exit non-zero if any L-rule fires (CI / pre-push gate mode).",
)
def lint_cmd(tenant_slug: str, strict: bool) -> None:
    """Run the L1-L5 linter on the persisted journal."""
    from core.linter import lint_engagement

    eng = load_engagement(tenant_slug)
    result = lint_engagement(eng)

    if not result.violations:
        click.echo(click.style(f"[ok] {tenant_slug} lints clean", fg="green"))
        return

    for v in result.violations:
        sev_color = "red" if v.severity == "error" else "yellow"
        click.echo(
            click.style(f"  [{v.severity.upper()} {v.rule}]", fg=sev_color)
            + f" {v.location}: {v.message}"
        )

    if strict and result.has_errors:
        l_error_count = sum(len(result.errors_for_rule(r)) for r in ("L1", "L2", "L3", "L4", "L5"))
        click.echo(
            click.style(
                f"\n[BLOCK] {l_error_count} L-rule errors. Fix before publishing.",
                fg="red",
                bold=True,
            ),
            err=True,
        )
        sys.exit(1)


@cli.command()
@click.argument("tenant_slug")
@click.option(
    "--all",
    "render_all_flag",
    is_flag=True,
    default=True,
    help="Render all 7 deliverables (default behavior).",
)
@click.option(
    "--ungated",
    is_flag=True,
    help="Skip the lint gate and render even with errors (debugging).",
)
def render(tenant_slug: str, render_all_flag: bool, ungated: bool) -> None:
    """Render all 7 deliverables to engagements/<slug>/deliverables/.

    Default (gated) mode runs the linter first and writes ONLY if zero
    L-errors. Use --ungated to render anyway (for debugging).

    Phase 1 limitation: deliverables need rich typed-primitive context
    (the journal stores serialized dicts, not Pydantic objects). Until
    M4 plumbs context-from-journal extraction, the CLI renders against
    the engagement's tenant + thesis ONLY. Other sections render with
    placeholder content. Use the Python API + render orchestrator
    directly with `extra_context=` for full deliverables.
    """
    from core.orchestrator import render_all as _render_all
    from core.orchestrator import render_with_gate

    eng = load_engagement(tenant_slug)

    out_dir = ENGAGEMENTS_ROOT / tenant_slug / "deliverables"
    extras = _bootstrap_render_context(eng)

    if ungated:
        paths, lint_result = _render_all(eng, out_dir, extra_context=extras)
        click.echo(f"Rendered {len(paths)} files (UNGATED — inspect before publishing).")
    else:
        paths, lint_result = render_with_gate(eng, out_dir, extra_context=extras)
        if not paths:
            click.echo(
                click.style(
                    "[BLOCK] Lint gate fired — no deliverables written.",
                    fg="red",
                    bold=True,
                ),
                err=True,
            )
            for v in lint_result.violations:
                click.echo(f"  [{v.severity.upper()} {v.rule}] {v.message}", err=True)
            sys.exit(1)

    for slug, path in sorted(paths.items()):
        click.echo(f"  {slug:<24} -> {path}")
    click.echo(
        f"\nLint: {len(lint_result.violations)} violations, has_errors={lint_result.has_errors}"
    )


def _bootstrap_render_context(eng):  # type: ignore[no-untyped-def]
    """Phase 1 stub context: extract what we can from the journal.

    M4 will replace this with a proper context-from-journal extractor that
    reconstitutes typed primitives. For now we surface the limitation
    explicitly via placeholder values for sections the journal can't
    reconstitute (use_cases, dimensions, roi_cells, etc.).
    """
    from decimal import Decimal

    from core.types import (
        Citation,
        StrategicThesis,
    )

    state = eng.state()

    placeholder_cite = Citation(
        kind="evidence",
        ref="cli-placeholder",
        excerpt="Phase 1 CLI cannot reconstitute typed primitives from journal alone",
        confidence="low",
    )
    placeholder_thesis = StrategicThesis(
        economic_lever="(thesis from journal not yet reconstituted in CLI — see M4)",
        lever_kind="cost",
        magnitude_estimate=Decimal("1"),
        magnitude_basis="placeholder",
        strategic_horizon="h1-now",
        decision_rights_owner=eng.tenant.sponsor,
        measured_in="USD/yr",
        evidence=[placeholder_cite],
    )
    return {
        "thesis": placeholder_thesis,
        "dimensions": [],
        "capabilities": [],
        "use_cases": [],
        "frameworks_applied": state.frameworks_active,
        "ranked": [],
        "top_n": 0,
        "roi_cells": [],
        "discount_rate": Decimal("0.14"),
        "total_revenue": Decimal("0"),
        "total_investment": Decimal("0"),
        "total_net": Decimal("0"),
        "assumptions": [],
        "roadmap_steps": [],
        "pilot": None,
        "generated_at": datetime.now(UTC).date().isoformat(),
    }


if __name__ == "__main__":
    cli()
