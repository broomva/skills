"""``health raw`` subcommand — lossless raw-passthrough retrieval.

Emits the verbatim upstream responses (every field, nothing curated) for a date
range, so the agent can reach data the structured mapping drops — e.g. Garmin's
daily summary returns ~94 fields where we type ~5; this surfaces all 94.

Completeness over truncation: within the requested range, **every** document is
returned — there is no cap. The default range is a single day (today); widen it
with ``--from``/``--to``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import typer

from broomva_health.cli.formatters import format_value
from broomva_health.domain.source import Source

if TYPE_CHECKING:
    from broomva_health.cli.container import Container

__all__ = ["app"]


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Raw verbatim upstream responses (lossless passthrough) over a date range.",
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
def raw_root(
    ctx: typer.Context,
    from_date: str | None = typer.Option(
        None, "--from", help="Inclusive start date (ISO YYYY-MM-DD). Default: today (local)."
    ),
    to_date: str | None = typer.Option(
        None, "--to", help="Inclusive end date (ISO YYYY-MM-DD). Default: same as --from."
    ),
    endpoint: str | None = typer.Option(
        None,
        "--endpoint",
        help="Filter to one endpoint (daily_summary, sleep, hrv, stress, spo2, "
        "respiration, body_battery, vo2max, training_readiness, weight, hydration).",
    ),
    source: Source | None = typer.Option(
        None, "--source", "-s", help="Source to read (default: all registered)."
    ),
) -> None:
    """Emit verbatim upstream responses for the range — every document, uncapped."""

    if ctx.invoked_subcommand is not None:
        return

    container = _container_from_ctx(ctx)
    fmt = ctx.obj["format"]
    fields = ctx.obj["fields"]

    local_today = container.clock.now().astimezone().date()
    start = _parse_date(from_date, flag="--from") if from_date else local_today
    end = _parse_date(to_date, flag="--to") if to_date else start
    if end < start:
        raise typer.BadParameter(f"--to ({end}) precedes --from ({start})")

    targets = [source] if source is not None else list(container.sources.keys())
    docs: list[dict[str, Any]] = []
    for src in targets:
        try:
            repo = container.repository_for(src)
        except Exception:
            continue
        for doc in repo.query_raw_documents(src, start, end, endpoint):
            docs.append(
                {
                    "source": doc.source.value,
                    "calendar_date": doc.calendar_date.isoformat(),
                    "endpoint": doc.endpoint,
                    "fetched_at": doc.normalized_fetched_at().isoformat(),
                    "payload": doc.payload,
                }
            )

    typer.echo(format_value(docs, fmt, fields=fields))
