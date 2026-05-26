"""``health health`` — per-metric queries (stubs in v1)."""

from __future__ import annotations

import typer

__all__ = ["app"]


app = typer.Typer(
    no_args_is_help=True,
    help="Per-metric queries (sleep / heart-rate / rhr / hrv / body-battery / stress).",
)


_NOT_IMPL_MSG = "{name} is not implemented in v1 — see Workflows/Health.md"


def _stub(name: str) -> None:
    typer.secho(_NOT_IMPL_MSG.format(name=name), fg=typer.colors.YELLOW)


@app.command("sleep")
def sleep() -> None:
    """Stub: sleep query is not implemented in v1."""
    _stub("sleep")


@app.command("heart-rate")
def heart_rate() -> None:
    """Stub: heart-rate query is not implemented in v1."""
    _stub("heart-rate")


@app.command("rhr")
def rhr() -> None:
    """Stub: resting-heart-rate query is not implemented in v1."""
    _stub("rhr")


@app.command("hrv")
def hrv() -> None:
    """Stub: HRV query is not implemented in v1."""
    _stub("hrv")


@app.command("body-battery")
def body_battery() -> None:
    """Stub: body-battery query is not implemented in v1."""
    _stub("body-battery")


@app.command("stress")
def stress() -> None:
    """Stub: stress query is not implemented in v1."""
    _stub("stress")
