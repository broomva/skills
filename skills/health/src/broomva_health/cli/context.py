"""``health context`` subcommand — LLM-optimized aggregated dump.

Builds a single document with the user's recent profile, stats, health,
training, weight, and activities. Designed to be piped into an agent
session as one-shot context. For v1 the implementation queries the local
trace DB only — no live source calls — so it's always cheap to run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import typer

from broomva_health.cli.formatters import format_value
from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.source import Source

if TYPE_CHECKING:
    from broomva_health.cli.container import Container
    from broomva_health.ports.repository import TraceRepository

__all__ = ["app"]


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Aggregated LLM-optimized health context (single document).",
)


_LATEST_METRICS: tuple[tuple[str, MetricCode], ...] = (
    ("hrv_overnight_ms", MetricCode.HRV_OVERNIGHT),
    ("rhr_bpm", MetricCode.RESTING_HEART_RATE),
    ("body_battery", MetricCode.BODY_BATTERY),
    ("vo2_max", MetricCode.VO2_MAX),
    ("training_readiness", MetricCode.TRAINING_READINESS),
    ("stress", MetricCode.STRESS),
    ("sleep_score", MetricCode.SLEEP_SCORE),
    ("sleep_seconds", MetricCode.SLEEP_DURATION),
    ("weight_kg", MetricCode.WEIGHT_KG),
)


def _container_from_ctx(ctx: typer.Context) -> Container:
    container = ctx.obj["container"] if ctx.obj else None
    if container is None:
        raise typer.BadParameter("CLI was not initialized — container missing")
    return container  # type: ignore[no-any-return]


def _latest_sample(
    repo: TraceRepository,
    metric: MetricCode,
    window: timedelta,
    *,
    now: datetime,
) -> dict[str, Any] | None:
    start = now - window
    samples = repo.query_quantity(source=None, metric=metric, start=start, end=now)
    if not samples:
        return None
    latest = max(samples, key=lambda s: s.end_ts)
    return {
        "value": latest.value,
        "unit": latest.unit,
        "ts": latest.end_ts.isoformat(),
        "source": latest.source.value,
    }


def _focus_set(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {token.strip() for token in raw.split(",") if token.strip()}


@app.callback()
def context_root(
    ctx: typer.Context,
    focus: str | None = typer.Option(
        None,
        "--focus",
        help="CSV of section names to include (default: all). "
        "Sections: profile, stats, health, training, weight, activities.",
    ),
    activities: int = typer.Option(
        5, "--activities", min=0, max=100, help="Number of recent activities to include."
    ),
    no_health: bool = typer.Option(
        False, "--no-health", help="Skip the 'health' section."
    ),
    no_weight: bool = typer.Option(
        False, "--no-weight", help="Skip the 'weight' section."
    ),
    profile: str = typer.Option("default", "--profile", "-p"),
    window_days: int = typer.Option(
        14, "--window-days", min=1, max=365, help="Look-back window for 'latest' queries."
    ),
) -> None:
    """Emit a single aggregated context document, source-agnostic."""

    if ctx.invoked_subcommand is not None:
        return

    container = _container_from_ctx(ctx)
    fmt = ctx.obj["format"]
    fields = ctx.obj["fields"]
    now = container.clock.now()
    window = timedelta(days=window_days)

    focus_filter = _focus_set(focus)
    document: dict[str, Any] = {
        "generated_at": now.astimezone(UTC).isoformat(),
        "profile": profile,
        "window_days": window_days,
    }

    def section_enabled(name: str, *, force_off: bool = False) -> bool:
        if force_off:
            return False
        if focus_filter is None:
            return True
        return name in focus_filter

    # Per-source latest-sample snapshot is what the 'health' and 'weight'
    # sections aggregate over. We collect repositories lazily — that means
    # we never open the Whoop DB if the user said --focus health,training.
    sources = list(container.sources.keys())

    if section_enabled("profile"):
        document["profile_info"] = {
            "registered_sources": [src.value for src in sources],
            "data_dir": str(container.paths.data_dir),
            "vault_dir": str(container.paths.vault_dir),
        }

    if section_enabled("stats"):
        stats: dict[str, Any] = {}
        for src in sources:
            try:
                repo = container.repository_for(src)
            except Exception as exc:
                stats[src.value] = {"error": str(exc)}
                continue
            try:
                last_sync = repo.last_sample_ts(src, MetricCode.HEART_RATE)
            except Exception:
                last_sync = None
            stats[src.value] = {
                "last_heart_rate_sample": last_sync.isoformat() if last_sync else None,
            }
        document["stats"] = stats

    if section_enabled("health", force_off=no_health):
        health: dict[str, Any] = {}
        for label, metric in _LATEST_METRICS:
            if label == "weight_kg":
                continue  # weight has its own section
            collected: dict[str, Any] = {}
            for src in sources:
                try:
                    repo = container.repository_for(src)
                except Exception:
                    continue
                latest = _latest_sample(repo, metric, window, now=now)
                if latest is not None:
                    collected[src.value] = latest
            if collected:
                health[label] = collected
        document["health"] = health

    if section_enabled("training"):
        training: dict[str, Any] = {}
        for label, metric in (
            ("training_readiness", MetricCode.TRAINING_READINESS),
            ("ctl", MetricCode.TRAINING_LOAD_CTL),
            ("atl", MetricCode.TRAINING_LOAD_ATL),
            ("tsb", MetricCode.TRAINING_LOAD_TSB),
            ("vo2_max", MetricCode.VO2_MAX),
            ("fitness_age", MetricCode.FITNESS_AGE),
        ):
            collected = {}
            for src in sources:
                try:
                    repo = container.repository_for(src)
                except Exception:
                    continue
                latest = _latest_sample(repo, metric, window, now=now)
                if latest is not None:
                    collected[src.value] = latest
            if collected:
                training[label] = collected
        document["training"] = training

    if section_enabled("weight", force_off=no_weight):
        weight: dict[str, Any] = {}
        for label, metric in (
            ("weight_kg", MetricCode.WEIGHT_KG),
            ("body_fat_pct", MetricCode.BODY_FAT_PCT),
            ("lean_mass_kg", MetricCode.LEAN_MASS_KG),
            ("bmi", MetricCode.BMI),
        ):
            collected = {}
            for src in sources:
                try:
                    repo = container.repository_for(src)
                except Exception:
                    continue
                latest = _latest_sample(repo, metric, window, now=now)
                if latest is not None:
                    collected[src.value] = latest
            if collected:
                weight[label] = collected
        document["weight"] = weight

    if section_enabled("activities") and activities > 0:
        activities_payload: list[dict[str, Any]] = []
        for src in sources:
            try:
                repo = container.repository_for(src)
            except Exception:
                continue
            try:
                workouts = repo.query_workouts(
                    source=src, start=now - window, end=now
                )
            except Exception:
                continue
            workouts.sort(key=lambda w: w.start_ts, reverse=True)
            for workout in workouts[:activities]:
                activities_payload.append(
                    {
                        "source": workout.source.value,
                        "activity_id": workout.activity_id,
                        "activity_type": workout.activity_type,
                        "start_ts": workout.start_ts.isoformat(),
                        "duration_s": workout.duration_s,
                        "distance_m": workout.distance_m,
                        "kcal": workout.kcal,
                        "avg_hr": workout.avg_hr,
                        "training_effect": workout.training_effect,
                    }
                )
        document["activities"] = activities_payload[:activities]

    # If the user gave focus, drop sections that weren't requested AND were
    # not auto-populated. (Top-level metadata keys always stay.)
    if focus_filter is not None:
        meta_keys = {"generated_at", "profile", "window_days"}
        document = {
            key: value
            for key, value in document.items()
            if key in meta_keys or key.replace("_info", "") in focus_filter or key in focus_filter
        }

    typer.echo(format_value(document, fmt, fields=fields))


# Suppress unused-import warning for Source (used in the registered-sources path
# of profile_info via container.sources keys, which are typed `Source`).
_unused = Source
