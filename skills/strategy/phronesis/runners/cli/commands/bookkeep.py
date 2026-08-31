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
    from core.extraction.pipeline import (
    _resolve_entity_graph_root,
    extract_and_queue,
)

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

    # Dry-run: redirect writes to a tmp dir, never persist.
    #
    # The entity root is MIRRORED, not blanked. Redirecting it to an empty tmp
    # dir made `entity_path.exists()` always false, so dry-run reported
    # "promoted: 6" for exactly the candidates a real run reports as
    # "already on disk: 6" -- the command's whole job is to predict the real
    # run, and it predicted the opposite. Symlinking the existing per-type
    # directories preserves the exists() answer while keeping every write
    # inside the temp dir.
    if dry_run:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            tmp_entities = tmp_root / "entities"
            tmp_entities.mkdir(parents=True, exist_ok=True)
            real_entities = entity_graph_root or _resolve_entity_graph_root()
            if real_entities.exists():
                for sub in real_entities.iterdir():
                    if sub.is_dir():
                        (tmp_entities / sub.name).symlink_to(sub)
            result = extract_and_queue(
                engagement,
                queue_root=tmp_root / "queue",
                entity_graph_root=tmp_entities,
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
    # `queued_count` also counts candidates that scored >=5 but could not be
    # promoted, so subtract them: printing those under "score <5/9" states a
    # falsehood about their score.
    unpromotable = len(getattr(result, "unpromotable", []))
    skipped = len(getattr(result, "skipped_existing", []))
    click.echo(
        "  Queued for review (score <5/9):  "
        + click.style(str(result.queued_count - unpromotable), fg="yellow")
    )
    if unpromotable:
        click.echo(
            "  No self-contained claim (queued): "
            + click.style(str(unpromotable), fg="yellow")
        )
    if skipped:
        click.echo(
            "  Already on disk (left untouched): "
            + click.style(str(skipped), fg="cyan")
        )
    # Accounting invariant. Without the two lines above a re-run over a
    # populated graph printed "0 promoted, 0 queued" for six candidates and
    # six queue writes -- the refusal was invisible.
    accounted = (
        result.promoted_count + result.queued_count + skipped + len(result.leaks)
    )
    if accounted != result.total_candidates:
        click.echo(
            click.style(
                f"  [accounting] {accounted} accounted vs "
                f"{result.total_candidates} candidates -- please report this.",
                fg="red",
            ),
            err=True,
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
