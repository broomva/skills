"""``health daily-note`` — project a day's metrics to an Obsidian daily note.

Renders ``<vault>/07-Health/YYYY-MM-DD.md`` (YAML frontmatter + prose) from the
trace store via :class:`RenderDailyNoteUseCase`. Writing command, so it ensures
the data/vault dirs exist first (the container deliberately does not).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

import typer

from broomva_health.application.daily_note import RenderDailyNoteUseCase
from broomva_health.cli.formatters import format_value
from broomva_health.domain.source import Source

if TYPE_CHECKING:
    from broomva_health.cli.container import Container

__all__ = ["app"]


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Render a day's metrics to an Obsidian daily-note (vault frontmatter).",
)


def _container_from_ctx(ctx: typer.Context) -> Container:
    container = ctx.obj["container"] if ctx.obj else None
    if container is None:
        raise typer.BadParameter("CLI was not initialized — container missing")
    return container  # type: ignore[no-any-return]


@app.callback()
def daily_note_root(
    ctx: typer.Context,
    date_opt: str | None = typer.Option(
        None, "--date", help="Day to render (ISO YYYY-MM-DD). Default: today (local)."
    ),
    source: Source | None = typer.Option(
        None, "--source", "-s", help="Source repo to read (default: garmin / first registered)."
    ),
) -> None:
    """Write the Obsidian daily-note for ``--date`` and print its path."""

    if ctx.invoked_subcommand is not None:
        return

    container = _container_from_ctx(ctx)
    fmt = ctx.obj["format"]
    fields = ctx.obj["fields"]

    if container.projection is None:
        raise typer.BadParameter(
            "no Obsidian projection available (vault adapter failed to load)."
        )
    if not container.sources:
        raise typer.BadParameter("no sources registered — nothing to render.")

    # Writing command: create data + vault dirs (the container intentionally won't).
    container.paths.ensure()

    local_today = container.clock.now().astimezone().date()
    if date_opt:
        try:
            day = (
                datetime.fromisoformat(date_opt).date()
                if "T" in date_opt
                else date.fromisoformat(date_opt)
            )
        except ValueError as exc:
            raise typer.BadParameter(
                f"--date must be ISO YYYY-MM-DD; got {date_opt!r}: {exc}"
            ) from exc
    else:
        day = local_today

    # The use case queries the repo source-agnostically (source=None); v1 is
    # Garmin-only, so read the Garmin repo (or the first registered source).
    if source is not None and source not in container.sources:
        typer.secho(
            f"Source '{source.value}' is not registered.", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=1)
    src = (
        source
        if source is not None
        else (Source.GARMIN if Source.GARMIN in container.sources else next(iter(container.sources)))
    )
    repo = container.repository_for(src)
    path = RenderDailyNoteUseCase(repo=repo, projection=container.projection).execute(day=day)

    typer.echo(format_value({"date": day.isoformat(), "path": str(path)}, fmt, fields=fields))
