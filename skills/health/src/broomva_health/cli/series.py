"""``health series`` subcommand — processed/enriched metric time-series.

The retrieval layer *between* ``context`` (latest-in-window snapshot) and ``raw``
(verbatim JSON): a structured time-series for any metric over any range. Optional
query-time bucketing + aggregation (e.g. weekly-mean RHR, monthly-sum steps) is
enrichment computed on read, so the agent gets processed views without
post-processing the raw stream.

Completeness over truncation: the un-bucketed series returns every sample in the
range, uncapped.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

import typer

from broomva_health.cli.formatters import format_value
from broomva_health.domain.metrics import MetricCode, canonical_unit
from broomva_health.domain.source import Source

if TYPE_CHECKING:
    from broomva_health.cli.container import Container

__all__ = ["app"]


class Bucket(Enum):
    """Calendar bucket for aggregation."""

    day = "day"
    week = "week"
    month = "month"
    quarter = "quarter"
    year = "year"


class Agg(Enum):
    """Aggregation applied within each bucket."""

    mean = "mean"
    sum = "sum"
    min = "min"
    max = "max"
    first = "first"
    last = "last"
    count = "count"


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Structured metric time-series with optional bucketed aggregation.",
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


def _bucket_key(d: date, bucket: Bucket) -> str:
    if bucket is Bucket.day:
        return d.isoformat()
    if bucket is Bucket.week:
        iso = d.isocalendar()
        return f"{iso.year:04d}-W{iso.week:02d}"
    if bucket is Bucket.month:
        return f"{d.year:04d}-{d.month:02d}"
    if bucket is Bucket.quarter:
        return f"{d.year:04d}-Q{(d.month - 1) // 3 + 1}"
    return f"{d.year:04d}"  # Bucket.year


def _aggregate(values: list[float], how: Agg) -> float:
    """Aggregate values (input is in chronological order → first/last well-defined)."""
    if how is Agg.mean:
        return sum(values) / len(values)
    if how is Agg.sum:
        return sum(values)
    if how is Agg.min:
        return min(values)
    if how is Agg.max:
        return max(values)
    if how is Agg.count:
        return float(len(values))
    if how is Agg.first:
        return values[0]
    return values[-1]  # Agg.last


@app.callback()
def series_root(
    ctx: typer.Context,
    metric: MetricCode = typer.Option(
        ..., "--metric", "-m", help="Metric (e.g. steps, resting_heart_rate, hrv_overnight)."
    ),
    from_date: str | None = typer.Option(
        None, "--from", help="Inclusive start (ISO YYYY-MM-DD). Default: 30 days before --to."
    ),
    to_date: str | None = typer.Option(
        None, "--to", help="Inclusive end (ISO YYYY-MM-DD). Default: today (local)."
    ),
    bucket: Bucket | None = typer.Option(
        None, "--bucket", help="Aggregate into day/week/month/quarter/year buckets."
    ),
    agg: Agg = typer.Option(Agg.mean, "--agg", help="Aggregation applied when --bucket is set."),
    source: Source | None = typer.Option(
        None, "--source", "-s", help="Source (default: all registered)."
    ),
) -> None:
    """Emit a structured time-series for ``--metric`` over the range."""

    if ctx.invoked_subcommand is not None:
        return

    container = _container_from_ctx(ctx)
    fmt = ctx.obj["format"]
    fields = ctx.obj["fields"]

    local_today = container.clock.now().astimezone().date()
    end = _parse_date(to_date, flag="--to") if to_date else local_today
    start = _parse_date(from_date, flag="--from") if from_date else end - timedelta(days=30)
    if end < start:
        raise typer.BadParameter(f"--to ({end}) precedes --from ({start})")

    start_dt = datetime(start.year, start.month, start.day, tzinfo=UTC)
    # Inclusive of the end day: bound at its last microsecond so a same-day sample
    # (anchored at the day's midnight) is included but the next day's is not.
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, 999999, tzinfo=UTC)

    targets = [source] if source is not None else list(container.sources.keys())
    samples = []
    for src in targets:
        try:
            repo = container.repository_for(src)
        except Exception:
            continue
        samples.extend(repo.query_quantity(src, metric, start_dt, end_dt))
    samples.sort(key=lambda s: s.start_ts)

    unit = canonical_unit(metric)
    points: list[dict[str, Any]]
    if bucket is None:
        points = [
            {
                "ts": s.start_ts.isoformat(),
                "value": s.value,
                "unit": s.unit,
                "source": s.source.value,
            }
            for s in samples
        ]
    else:
        grouped: dict[str, list[float]] = defaultdict(list)
        for s in samples:
            grouped[_bucket_key(s.start_ts.date(), bucket)].append(s.value)
        points = [
            {"bucket": key, "value": _aggregate(vals, agg), "n": len(vals), "unit": unit}
            for key, vals in sorted(grouped.items())
        ]

    document = {
        "metric": metric.value,
        "unit": unit,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "bucket": bucket.value if bucket is not None else None,
        "agg": agg.value if bucket is not None else None,
        "count": len(points),
        "points": points,
    }
    typer.echo(format_value(document, fmt, fields=fields))
