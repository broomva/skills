"""``health sync`` subcommand — incremental pull across registered sources."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import typer

from broomva_health.application.sync import SyncSourceUseCase
from broomva_health.cli.formatters import format_value
from broomva_health.domain.errors import HealthError
from broomva_health.domain.source import Source

if TYPE_CHECKING:
    from broomva_health.cli.container import Container

__all__ = ["app"]


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Pull incremental samples + workouts from each registered source.",
)


def _container_from_ctx(ctx: typer.Context) -> Container:
    container = ctx.obj["container"] if ctx.obj else None
    if container is None:
        raise typer.BadParameter("CLI was not initialized — container missing")
    return container  # type: ignore[no-any-return]


def _parse_since(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    try:
        # Accept date (YYYY-MM-DD) or full ISO datetime.
        if len(raw) == 10:
            return datetime.fromisoformat(f"{raw}T00:00:00+00:00")
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise typer.BadParameter(
            f"--since must be an ISO date (YYYY-MM-DD) or ISO datetime; got {raw!r}: {exc}"
        ) from exc


@app.callback()
def sync_root(
    ctx: typer.Context,
    source: Source | None = typer.Option(
        None, "--source", "-s", help="Sync only this source (default: all registered)."
    ),
    profile: str = typer.Option("default", "--profile", "-p"),
    since: str | None = typer.Option(
        None, "--since", help="Override the incremental cursor (ISO date or datetime)."
    ),
) -> None:
    """Pull incremental samples + workouts from each registered source.

    Exit 0 if every source succeeded; 1 if any source raised an error or
    returned a result with non-empty ``errors``.
    """

    if ctx.invoked_subcommand is not None:
        return

    container = _container_from_ctx(ctx)
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

    since_dt = _parse_since(since)
    results = []
    had_error = False
    for src in targets:
        trace_source = container.sources[src]
        repo = container.repository_for(src)
        use_case = SyncSourceUseCase(
            source=trace_source,
            repo=repo,
            token_store=container.token_store,
            rate_limiter=container.rate_limiter,
            mfa=container.mfa,
        )
        try:
            result = use_case.execute(since=since_dt, profile=profile)
            results.append(result)
            if not result.succeeded:
                had_error = True
        except HealthError as exc:
            had_error = True
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
        raise typer.Exit(code=1)
