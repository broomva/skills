"""``health backfill`` — bounded historical pull from a source."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

import typer

from broomva_health.application.backfill import BackfillSourceUseCase
from broomva_health.cli.formatters import format_value
from broomva_health.domain.errors import HealthError
from broomva_health.domain.source import Source

if TYPE_CHECKING:
    from broomva_health.cli.container import Container

__all__ = ["app"]


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help=(
        "Historical backfill over [--from, --to] (inclusive). "
        "Prefer the source's bulk-export (Garmin: 'Export Your Data') "
        "for cold-start ingest; this path is the API-driven fallback."
    ),
)


def _container_from_ctx(ctx: typer.Context) -> Container:
    container = ctx.obj["container"] if ctx.obj else None
    if container is None:
        raise typer.BadParameter("CLI was not initialized — container missing")
    return container  # type: ignore[no-any-return]


def _parse_date(raw: str, *, flag: str) -> date:
    try:
        return datetime.fromisoformat(raw).date() if "T" in raw else date.fromisoformat(raw)
    except ValueError as exc:
        raise typer.BadParameter(
            f"{flag} must be an ISO date (YYYY-MM-DD); got {raw!r}: {exc}"
        ) from exc


@app.callback()
def backfill_root(
    ctx: typer.Context,
    from_date: str = typer.Option(
        ...,
        "--from",
        help="Inclusive start date for the backfill range (ISO YYYY-MM-DD).",
    ),
    to_date: str | None = typer.Option(
        None,
        "--to",
        help="Inclusive end date for the backfill range (default: today, UTC).",
    ),
    source: Source | None = typer.Option(
        None, "--source", "-s", help="Source to backfill (default: all registered)."
    ),
    profile: str = typer.Option("default", "--profile", "-p"),
) -> None:
    """Run a historical backfill against one or more registered sources.

    The Garmin adapter walks the range day-by-day and acquires the rate
    limiter per day, so a 30-day backfill at the default 15-min interval
    takes ~7.5 hours wall-clock. For large ranges (>14 days) prefer the
    GDPR ``Export Your Data`` tarball — see ``References/garmin-api-landscape-2026.md``.
    """

    if ctx.invoked_subcommand is not None:
        return

    container = _container_from_ctx(ctx)

    start = _parse_date(from_date, flag="--from")
    end = _parse_date(to_date, flag="--to") if to_date else datetime.now().date()
    if end < start:
        raise typer.BadParameter(f"--to ({end}) precedes --from ({start})")

    targets: list[Source]
    if source is not None:
        if source not in container.sources:
            typer.secho(
                f"Source '{source.value}' is not registered.", fg=typer.colors.RED, err=True
            )
            raise typer.Exit(code=1)
        targets = [source]
    else:
        targets = list(container.sources.keys())

    results: list[object] = []
    had_error = False
    last_exc: HealthError | None = None
    for src in targets:
        trace_source = container.sources[src]
        repo = container.repository_for(src)
        use_case = BackfillSourceUseCase(
            source=trace_source,
            repo=repo,
            token_store=container.token_store,
            rate_limiter=container.rate_limiter,
            mfa=container.mfa,
        )
        try:
            result = use_case.execute(start=start, end=end, profile=profile)
            results.append(result)
            if result.errors:
                had_error = True
        except HealthError as exc:
            had_error = True
            last_exc = exc
            results.append(
                {
                    "source": src.value,
                    "error": exc.code,
                    "message": str(exc),
                    "context": exc.context,
                }
            )

    fmt = ctx.obj["format"]
    fields = ctx.obj["fields"]
    typer.echo(format_value(results, fmt, fields=fields))
    if had_error:
        raise typer.Exit(code=last_exc.exit_code if last_exc is not None else 1)
