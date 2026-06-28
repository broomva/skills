"""``health weight`` — weight + body-composition queries (stubs in v1)."""

from __future__ import annotations

import typer

__all__ = ["app"]


app = typer.Typer(
    no_args_is_help=True,
    help="Weight + body composition (list / get / log).",
)


_NOT_IMPL_MSG = "{name} is not implemented in v1 — see Workflows/Weight.md"


def _stub(name: str) -> None:
    typer.secho(_NOT_IMPL_MSG.format(name=name), fg=typer.colors.YELLOW)


@app.command("list")
def list_cmd() -> None:
    """Stub: weight list is not implemented in v1."""
    _stub("weight list")


@app.command("get")
def get_cmd() -> None:
    """Stub: weight get is not implemented in v1."""
    _stub("weight get")


@app.command("log")
def log_cmd() -> None:
    """Stub: weight log (manual entry) is not implemented in v1."""
    _stub("weight log")
