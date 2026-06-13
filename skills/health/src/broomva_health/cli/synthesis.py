"""``health synthesis`` subcommand — derived longevity-proxy metrics.

Exposes :class:`SynthesisService` over the CLI: HRV coefficient-of-variation
(30d), Coggan CTL/ATL/TSB training-load, the VO2max quarterly arc, and a
recovery composite — each computed by *traversing* the local trace store
(not a latest-in-window snapshot, which is what ``context`` gives).

Source-agnostic: one snapshot per registered source. The math lives in
``broomva_health.synthesis`` and is exercised here against the real DB.

Note: CTL/ATL/TSB require per-activity TSS, which Garmin's activity *summary*
endpoint omits — so they read 0.0 until a TSS-derivation pass lands. HRV-CV,
the VO2max arc, and the recovery score populate from the daily wellness stream.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import typer

from broomva_health.cli.formatters import format_value
from broomva_health.synthesis.service import SynthesisService

if TYPE_CHECKING:
    from broomva_health.cli.container import Container

__all__ = ["app", "synthesis_by_source"]


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Derived metrics (HRV-CV, CTL/ATL/TSB, VO2max arc, recovery) over trace history.",
)


def _container_from_ctx(ctx: typer.Context) -> Container:
    container = ctx.obj["container"] if ctx.obj else None
    if container is None:
        raise typer.BadParameter("CLI was not initialized — container missing")
    return container  # type: ignore[no-any-return]


def _parse_on(raw: str | None, *, local_today: date) -> date:
    if not raw:
        return local_today
    try:
        return datetime.fromisoformat(raw).date() if "T" in raw else date.fromisoformat(raw)
    except ValueError as exc:
        raise typer.BadParameter(f"--on must be ISO YYYY-MM-DD; got {raw!r}: {exc}") from exc


def synthesis_by_source(container: Container, on_date: date) -> dict[str, Any]:
    """Compute a synthesis snapshot per registered source (source-agnostic math).

    Returns ``{source_value: snapshot_dict | {"error": ...}}``. Shared with the
    ``context`` command's ``synthesis`` section so both surfaces agree.
    """
    out: dict[str, Any] = {}
    for src in container.sources:
        try:
            repo = container.repository_for(src)
        except Exception as exc:  # a source whose DB won't open shouldn't kill the rest
            out[src.value] = {"error": str(exc)}
            continue
        out[src.value] = SynthesisService(repo).snapshot(on_date).model_dump(mode="json")
    return out


@app.callback()
def synthesis_root(
    ctx: typer.Context,
    on: str | None = typer.Option(
        None, "--on", help="Anchor date (ISO YYYY-MM-DD). Default: today (local)."
    ),
) -> None:
    """Emit derived synthesis metrics computed over the local trace history."""

    if ctx.invoked_subcommand is not None:
        return

    container = _container_from_ctx(ctx)
    fmt = ctx.obj["format"]
    fields = ctx.obj["fields"]
    # Garmin keys daily data by the user's LOCAL calendar date; anchor there.
    local_today = container.clock.now().astimezone().date()
    on_date = _parse_on(on, local_today=local_today)

    document: dict[str, Any] = {
        "generated_at": container.clock.now().astimezone(UTC).isoformat(),
        "on_date": on_date.isoformat(),
        "sources": synthesis_by_source(container, on_date),
    }
    typer.echo(format_value(document, fmt, fields=fields))
