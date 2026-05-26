"""``health training`` — training-derived metrics (stubs in v1)."""

from __future__ import annotations

import typer

__all__ = ["app"]


app = typer.Typer(
    no_args_is_help=True,
    help="Training metrics (status / readiness / vo2max / hrv / fitness-age).",
)


_NOT_IMPL_MSG = "{name} is not implemented in v1 — see Workflows/Training.md"


def _stub(name: str) -> None:
    typer.secho(_NOT_IMPL_MSG.format(name=name), fg=typer.colors.YELLOW)


@app.command("status")
def status_cmd() -> None:
    """Stub: training-status query is not implemented in v1."""
    _stub("training status")


@app.command("readiness")
def readiness() -> None:
    """Stub: training-readiness query is not implemented in v1."""
    _stub("training readiness")


@app.command("vo2max")
def vo2max() -> None:
    """Stub: VO2max query is not implemented in v1."""
    _stub("vo2max")


@app.command("hrv")
def hrv() -> None:
    """Stub: training-HRV query is not implemented in v1."""
    _stub("training hrv")


@app.command("fitness-age")
def fitness_age() -> None:
    """Stub: fitness-age query is not implemented in v1."""
    _stub("fitness-age")
