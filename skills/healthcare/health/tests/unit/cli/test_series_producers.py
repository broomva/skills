"""`health series` keeps producers apart: a filter, and no pooled buckets."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from broomva_health.adapters.repositories.sqlite import SQLiteTraceRepository
from broomva_health.cli.series import app
from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.samples import QuantitySample
from broomva_health.domain.source import Source


def _steps(producer: str, value: float) -> QuantitySample:
    ts = datetime(2024, 3, 2, 14, 0, tzinfo=UTC)
    return QuantitySample(
        source=Source.APPLE_HEALTH,
        metric=MetricCode.STEPS,
        value=value,
        unit="count",
        start_ts=ts,
        end_ts=ts.replace(minute=10),
        producer=producer,
        record_key=producer,
    )


def _run(*args: str) -> dict:
    repo = SQLiteTraceRepository(Path(":memory:"))
    repo.migrate()
    repo.upsert_quantity([_steps("iPhone", 100.0), _steps("Watch", 100.0)])
    container = SimpleNamespace(
        sources={Source.APPLE_HEALTH: object()},
        repository_for=lambda _src: repo,
        clock=SimpleNamespace(now=lambda: datetime(2024, 3, 3, tzinfo=UTC)),
    )
    result = CliRunner().invoke(
        app,
        ["--metric", "steps", "--from", "2024-03-01", "--to", "2024-03-03", *args],
        obj={"container": container, "format": "json", "fields": None},
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_buckets_never_pool_two_producers() -> None:
    doc = _run("--bucket", "day", "--agg", "sum")
    assert sorted((p["producer"], p["value"]) for p in doc["points"]) == [
        ("Watch", 100.0),
        ("iPhone", 100.0),
    ]


def test_producer_filter_selects_one_stream() -> None:
    doc = _run("--bucket", "day", "--agg", "sum", "--producer", "Watch")
    assert [(p["value"], p.get("producer")) for p in doc["points"]] == [(100.0, None)]
    raw = _run("--producer", "iPhone")
    assert [p["producer"] for p in raw["points"]] == ["iPhone"]
