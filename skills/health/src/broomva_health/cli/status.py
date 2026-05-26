"""``health status`` subcommand — reflexive snapshot of every source."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import typer

from broomva_health.application.status import HealthStatusUseCase
from broomva_health.cli.formatters import format_value

if TYPE_CHECKING:
    from broomva_health.cli.container import Container

__all__ = ["app"]


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Reflexive snapshot — token validity + recent rate-limit state.",
)


def _container_from_ctx(ctx: typer.Context) -> Container:
    container = ctx.obj["container"] if ctx.obj else None
    if container is None:
        raise typer.BadParameter("CLI was not initialized — container missing")
    return container  # type: ignore[no-any-return]


def _rate_limiter_snapshot(container: Container) -> dict[str, Any]:
    """Best-effort introspection of the in-memory rate limiter.

    The ``RateLimiter`` protocol intentionally exposes no state-snapshot
    method (per process state lives elsewhere); we fall back to ``vars(...)``
    for whatever the concrete adapter chose to expose. Empty in a fresh
    invocation — that's expected — the doctor command is the persistent
    state check.
    """

    limiter = container.rate_limiter
    snapshot = getattr(limiter, "snapshot", None)
    if callable(snapshot):
        try:
            value = snapshot()
            return value if isinstance(value, dict) else {"snapshot": value}
        except Exception:
            return {}
    state = getattr(limiter, "_state", None)
    if isinstance(state, dict):
        return {key: str(value) for key, value in state.items()}
    return {}


@app.callback()
def status_root(
    ctx: typer.Context,
    profile: str = typer.Option("default", "--profile", "-p"),
) -> None:
    """Print per-source token validity + recent rate-limit cooldown state."""

    if ctx.invoked_subcommand is not None:
        return

    container = _container_from_ctx(ctx)
    use_case = HealthStatusUseCase(
        sources=list(container.sources.values()), token_store=container.token_store
    )
    statuses = use_case.execute(profile=profile)
    payload: dict[str, Any] = {
        "sources": [s.model_dump(mode="json") for s in statuses],
        "rate_limiter": _rate_limiter_snapshot(container),
    }
    fmt = ctx.obj["format"]
    fields = ctx.obj["fields"]
    typer.echo(format_value(payload, fmt, fields=fields))
