"""phronesis bookkeep — extract knowledge-graph candidates from an engagement.

Usage:

  phronesis bookkeep <tenant_slug>

Drives the M7 extraction pipeline against a concluded engagement,
producing:
  - JSON queue records under
    `<PHRONESIS_EXTRACTION_QUEUE_ROOT>/<tenant_slug>/`
    (default `~/.config/phronesis/extraction-queue/`),
  - markdown entity-page stubs under
    `<PHRONESIS_ENTITY_GRAPH_ROOT>/{industry-pattern,framework-refinement}/`
    (default `~/broomva/research/entities/`) for candidates that score
    ≥5/9 on the bookkeeping P8 Nous gate.

Flags:
  --dry-run        Show what would be queued; never touch disk.
  --queue-root     Override the queue directory (else env / default).
  --entity-graph-root  Override the entity-graph directory.

The CLI command is a thin wrapper — the canonical reflexive trigger fires
automatically when `ENGAGEMENT_CONCLUDED` is emitted (per
`feedback_bookkeeping_reflexive.md`). This command is for re-runs +
operator inspection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from runners.cli.io import load_engagement


@click.command(name="bookkeep")
@click.argument("tenant_slug")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Compute extraction result but do NOT persist anything.",
)
@click.option(
    "--queue-root",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Override the review-queue root directory.",
)
@click.option(
    "--entity-graph-root",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Override the entity-graph root directory.",
)
@click.option(
    "--show-low-score",
    is_flag=True,
    help="Include below-threshold candidates in the output summary.",
)
def bookkeep(
    tenant_slug: str,
    dry_run: bool,
    queue_root: Path | None,
    entity_graph_root: Path | None,
    show_low_score: bool,
) -> None:
    """Extract anonymized knowledge-graph candidates from an engagement.

    Example:
        phronesis bookkeep tropico-renovables
        phronesis bookkeep acme-bank --dry-run
        phronesis bookkeep nova-construction \\
            --queue-root /tmp/queue \\
            --entity-graph-root /tmp/entities
    """
    # Late import keeps `phronesis --help` fast — extraction depends on
    # the whole engagement model + anonymizer.
    from core.extraction.pipeline import extract_and_queue

    try:
        engagement = load_engagement(tenant_slug)
    except FileNotFoundError as exc:
        click.echo(click.style(f"[error] {exc}", fg="red"), err=True)
        sys.exit(1)

    state = engagement.state()
    if not state.is_concluded:
        click.echo(
            click.style(
                f"[warn] {tenant_slug!r} is not concluded "
                f"(current_stage={state.current_stage}). "
                "Extraction will still run but candidate quality is "
                "best-effort. Press Ctrl-C to abort.",
                fg="yellow",
            ),
            err=True,
        )

    # Dry-run: redirect everything to a tmp dir, never persist.
    if dry_run:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            result = extract_and_queue(
                engagement,
                queue_root=tmp_root / "queue",
                entity_graph_root=tmp_root / "entities",
            )
            _print_summary(result, dry_run=True)
            if show_low_score:
                _print_queue_listing(result)
        return

    result = extract_and_queue(
        engagement,
        queue_root=queue_root,
        entity_graph_root=entity_graph_root,
    )
    _print_summary(result, dry_run=False)
    if show_low_score:
        _print_queue_listing(result)

    if result.leaks:
        click.echo(
            click.style(
                f"\n[BLOCK] Anonymization leaks detected — {len(result.leaks)} "
                "candidate(s) carried tenant markers post-redaction. They were "
                "NOT queued. Tighten core.anonymize policy + redact_terms.",
                fg="red",
                bold=True,
            ),
            err=True,
        )
        for slug, markers in result.leaks:
            click.echo(f"  [{slug}] markers: {markers}", err=True)
        sys.exit(2)


def _print_summary(result, *, dry_run: bool) -> None:  # type: ignore[no-untyped-def]
    """Print a one-screen extraction summary."""
    header = "[dry-run] " if dry_run else ""
    click.echo(f"{header}Engagement: {result.engagement_slug}")
    click.echo(f"  Industry-pattern candidates:    {result.industry_pattern_candidates}")
    click.echo(f"  Framework-refinement candidates: {result.framework_refinement_candidates}")
    click.echo(f"  Total candidates:                {result.total_candidates}")
    click.echo(
        "  Promoted (score ≥5/9):           " + click.style(str(result.promoted_count), fg="green")
    )
    click.echo(
        "  Queued for review (score <5/9):  " + click.style(str(result.queued_count), fg="yellow")
    )
    if result.leaks:
        click.echo(
            "  Leaked candidates:               "
            + click.style(str(len(result.leaks)), fg="red", bold=True)
        )


def _print_queue_listing(result) -> None:  # type: ignore[no-untyped-def]
    """Print per-file listing of queued + promoted records."""
    if result.promotion_paths:
        click.echo("\nPromoted entity stubs:")
        for path in result.promotion_paths:
            click.echo(f"  {path}")
    if result.queue_paths:
        click.echo("\nQueue records:")
        for path in result.queue_paths:
            click.echo(f"  {path}")


__all__ = ["bookkeep"]
