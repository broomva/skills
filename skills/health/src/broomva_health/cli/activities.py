"""``health activities`` — workout queries (stub in v1)."""

from __future__ import annotations

import typer

__all__ = ["app"]


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Workout queries — not yet wired in v1 (see Workflows/Activities.md).",
)


@app.callback()
def activities_root(ctx: typer.Context) -> None:  # noqa: ARG001
    """Stub: activities subcommand is not implemented in v1.

    Use ``health context`` for an aggregated dump that includes recent
    activities while this surface is being designed. See Workflows/Activities.md.
    """

    typer.secho(
        "activities is not implemented in v1 — see Workflows/Activities.md",
        fg=typer.colors.YELLOW,
    )
