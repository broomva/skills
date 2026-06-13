"""``health backfill`` — bounded historical pull from a source."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
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


def _months_ago(anchor: date, n: int) -> date:
    """Calendar-month subtraction, clamped to the target month's last day."""
    m = anchor.month - 1 - n
    year = anchor.year + m // 12
    month = m % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(anchor.day, last))


def _resolve_start(
    *, from_date: str | None, months: int | None, days: int | None, end: date
) -> date:
    """Pick the backfill start from exactly one of --from / --months / --days."""
    given = [x is not None for x in (from_date, months, days)]
    if sum(given) > 1:
        raise typer.BadParameter("pass only one of --from, --months, --days")
    if from_date is not None:
        return _parse_date(from_date, flag="--from")
    if months is not None:
        if months <= 0:
            raise typer.BadParameter(f"--months must be positive; got {months}")
        return _months_ago(end, months)
    if days is not None:
        if days <= 0:
            raise typer.BadParameter(f"--days must be positive; got {days}")
        return end - timedelta(days=days)
    raise typer.BadParameter("provide a start: one of --from, --months, or --days")


@app.callback()
def backfill_root(
    ctx: typer.Context,
    from_date: str | None = typer.Option(
        None,
        "--from",
        help="Inclusive start date (ISO YYYY-MM-DD). Or use --months / --days.",
    ),
    months: int | None = typer.Option(
        None, "--months", help="Backfill the last N calendar months (from today)."
    ),
    days: int | None = typer.Option(
        None, "--days", help="Backfill the last N days (from today)."
    ),
    to_date: str | None = typer.Option(
        None,
        "--to",
        help="Inclusive end date for the backfill range (default: today, local).",
    ),
    source: Source | None = typer.Option(
        None, "--source", "-s", help="Source to backfill (default: all registered)."
    ),
    profile: str = typer.Option("default", "--profile", "-p"),
) -> None:
    """Run a historical backfill against one or more registered sources.

    Specify the start with exactly one of ``--from`` / ``--months`` / ``--days``
    (e.g. ``--months 10``). The Garmin native adapter fetches activities once
    for the whole window and walks daily wellness day-by-day with a gentle
    ~1s/day pace, so a 10-month range completes in minutes. For a *complete*
    multi-year cold-start, prefer the GDPR ``Export Your Data`` tarball — see
    ``References/garmin-api-landscape-2026.md``.
    """

    if ctx.invoked_subcommand is not None:
        return

    container = _container_from_ctx(ctx)

    end = _parse_date(to_date, flag="--to") if to_date else datetime.now().date()
    start = _resolve_start(from_date=from_date, months=months, days=days, end=end)
    if end < start:
        raise typer.BadParameter(f"--to ({end}) precedes start ({start})")

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
