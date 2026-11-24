"""``health food`` — local food table and private meal log.

    health food import-usda ~/Downloads/fdc        # FoodData Central CSV releases
    health food import-csv staples.csv --source co # a hand-made regional table
    health food find "rice white cooked"
    health food log --meal lunch --at 13:10 \\
        --item usda:168880=180 --item usda:171477=120 --item +usda:171413=10
    health food show --days 3

Everything is local: the food table is built from files you downloaded, and
meals go to a 0600 file in the data directory. See ``Workflows/MealLog.md``.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from broomva_health.adapters.food_db import FoodTable
from broomva_health.adapters.repositories.meals import MealLog
from broomva_health.cli.formatters import format_value
from broomva_health.domain.nutrition import MEAL_KINDS, Meal, MealItem, Nutrients, parse_item_spec

if TYPE_CHECKING:
    from broomva_health.config.paths import HealthPaths

__all__ = ["app"]

app = typer.Typer(no_args_is_help=True, help="Food table and meal log (local, private).")


def _paths(ctx: typer.Context) -> HealthPaths:
    container = ctx.obj["container"] if ctx.obj else None
    if container is None:
        raise typer.BadParameter("CLI was not initialized — container missing")
    return container.paths  # type: ignore[no-any-return]


def _emit(ctx: typer.Context, data: Any) -> None:
    typer.echo(format_value(data, ctx.obj["format"], fields=ctx.obj.get("fields")))


def _unreadable(ctx: typer.Context, exc: Exception) -> str:
    return (
        f"could not read the food table {_paths(ctx).foods_db}: {exc}. Nothing was changed. "
        "Run `health food repair` to rebuild its search index from the stored foods. "
        "If that fails too, copy the file aside before anything else: it holds every "
        "source you imported (USDA and your own CSVs)."
    )


@contextmanager
def _table(ctx: typer.Context) -> Iterator[FoodTable]:
    """Open the food table; turn a locked or refused table into a clean exit 2."""
    try:
        with FoodTable(_paths(ctx).foods_db) as table:
            yield table
    except sqlite3.OperationalError as exc:
        # Only a busy or locked database means "another import". Anything else (a missing
        # index table, a damaged index) is damage, and gets the repair message below.
        code = (getattr(exc, "sqlite_errorcode", 0) or 0) & 0xFF
        if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            raise typer.BadParameter(
                f"food table unavailable: {exc} (another import running?)"
            ) from exc
        raise typer.BadParameter(_unreadable(ctx, exc)) from exc
    except sqlite3.DatabaseError as exc:
        raise typer.BadParameter(_unreadable(ctx, exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("import-usda")
def import_usda(
    ctx: typer.Context,
    root: Path = typer.Argument(
        ..., exists=True, file_okay=False, help="Folder with FoodData Central CSV releases."
    ),
) -> None:
    """Build the food table from USDA FoodData Central CSVs (Foundation, SR Legacy, FNDDS)."""
    with _table(ctx) as table:
        try:
            n = table.import_usda(root.expanduser())
        except (FileNotFoundError, ValueError) as exc:
            raise typer.BadParameter(str(exc), param_hint="ROOT") from exc
        _emit(ctx, {"imported": n, "source": "usda", "table": table.count()})


@app.command("import-csv")
def import_csv(
    ctx: typer.Context,
    path: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="CSV: food_id, description, kcal, protein_g, ..."
    ),
    source: str = typer.Option(
        ..., "--source", help="Short source name, e.g. 'co' for a Colombian table."
    ),
) -> None:
    """Add a hand-made per-100 g table; re-importing a source replaces it."""
    with _table(ctx) as table:
        try:
            n = table.import_csv(path.expanduser(), source=source)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _emit(ctx, {"imported": n, "source": source, "table": table.count()})


@app.command("find")
def find(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Words to match, e.g. 'chicken breast roasted'."),
    limit: int = typer.Option(10, "--limit", min=1, max=100),
    source: str | None = typer.Option(None, "--source", help="Only this source, e.g. 'usda'."),
) -> None:
    """Search the food table; use the returned food_id in ``health food log --item``."""
    with _table(ctx) as table:
        if not table.count():
            raise typer.BadParameter("the food table is empty: run `health food import-usda` first")
        rows = [
            {"food_id": f.food_id, "description": f.description, **_per100(f.per_100g)}
            for f in table.find(query, limit=limit, source=source)
        ]
    _emit(ctx, rows)


def _per100(n: Nutrients) -> dict[str, float | None]:
    def r(v: float | None) -> float | None:
        return None if v is None else round(v, 1)

    return {
        "kcal_100g": r(n.kcal),
        "protein_100g": r(n.protein_g),
        "fat_100g": r(n.fat_g),
        "carbs_100g": r(n.carbs_g),
    }


def _parse_time(raw: str | None) -> time | None:
    if raw is None:
        return None
    if not re.fullmatch(r"[0-9]{2}:[0-9]{2}", raw):
        raise typer.BadParameter(f"--at must be HH:MM, got {raw!r}")
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError as exc:
        raise typer.BadParameter(f"--at must be HH:MM, got {raw!r}") from exc


def _parse_day(raw: str | None) -> date:
    if raw is None:
        return date.today()
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
        raise typer.BadParameter(f"--date must be YYYY-MM-DD, got {raw!r}")
    try:
        day = date.fromisoformat(raw)
    except ValueError as exc:
        raise typer.BadParameter(f"--date must be YYYY-MM-DD, got {raw!r}") from exc
    if day > date.today():
        raise typer.BadParameter(f"--date {raw} is in the future")
    return day


@app.command("log")
def log(
    ctx: typer.Context,
    item: list[str] = typer.Option(
        ..., "--item", help="[+]source:id=grams; '+' marks a hidden item (oil, sugar)."
    ),
    meal: str | None = typer.Option(None, "--meal", help=f"One of: {', '.join(MEAL_KINDS)}."),
    at: str | None = typer.Option(None, "--at", help="Time eaten, HH:MM."),
    day: str | None = typer.Option(None, "--date", help="YYYY-MM-DD (default today)."),
    note: str | None = typer.Option(None, "--note"),
    photo: Path | None = typer.Option(
        None, "--photo", help="Copied into the private meal-photos folder."
    ),
) -> None:
    """Log one meal from its items and print the totals with the uncertainty band."""
    if meal is not None and meal not in MEAL_KINDS:
        raise typer.BadParameter(f"--meal must be one of {MEAL_KINDS}, got {meal!r}")
    items: list[MealItem] = []
    with _table(ctx) as table:
        for spec in item:
            try:
                food_id, grams, hidden = parse_item_spec(spec)
            except ValueError as exc:
                raise typer.BadParameter(str(exc), param_hint="--item") from exc
            food = table.get(food_id)
            if food is None:
                raise typer.BadParameter(
                    f"{food_id} is not in the food table (try `health food find`)",
                    param_hint="--item",
                )
            items.append(MealItem.of(food, grams, hidden=hidden))
    entry = Meal.build(items, day=_parse_day(day), at=_parse_time(at), kind=meal, note=note)
    log_store = MealLog(_paths(ctx).data_dir)
    if photo is not None:
        try:
            kept = log_store.keep_photo(photo.expanduser(), entry)
        except (FileNotFoundError, ValueError) as exc:
            raise typer.BadParameter(str(exc), param_hint="--photo") from exc
        entry = entry.model_copy(update={"photo": kept})
    try:
        try:
            log_store.append(entry)
        except ValueError as exc:  # a refused (symlinked) log
            raise typer.BadParameter(str(exc)) from exc
    except BaseException:
        if entry.photo:
            log_store.discard_photo(entry.photo)  # no orphan photo without its meal
        raise
    _emit(ctx, entry)


@app.command("repair")
def repair(ctx: typer.Context) -> None:
    """Rebuild the search index from the stored foods (no re-import, foods untouched)."""
    with _table(ctx) as table:
        n, per_source = table.rebuild_search()
        _emit(ctx, {"reindexed": n, "table": per_source})


@app.command("show")
def show(
    ctx: typer.Context,
    days: int = typer.Option(
        1, "--days", min=1, max=366, help="How many days back, including today."
    ),
    totals_only: bool = typer.Option(
        False, "--totals", help="One row per day instead of one per meal."
    ),
) -> None:
    """Meals of the last N days, or per-day totals with ``--totals``."""
    try:
        meals = MealLog(_paths(ctx).data_dir).last_days(days, today=date.today())
    except ValueError as exc:  # a refused (symlinked) log
        raise typer.BadParameter(str(exc)) from exc
    if totals_only:
        _emit(ctx, _day_totals(meals))
        return
    _emit(
        ctx,
        [
            {
                "date": m.day.isoformat(),
                "at": m.at.strftime("%H:%M") if m.at else None,
                "meal": m.kind,
                "items": "; ".join(
                    f"{'+' if i.hidden else ''}{i.description} {i.grams:g} g" for i in m.items
                ),
                **_rounded(m.totals),
                "kcal_range": _range(m.low.kcal, m.high.kcal),
                "partial": ", ".join(m.partial) or None,
            }
            for m in meals
        ],
    )


def _rounded(n: Nutrients) -> dict[str, float | None]:
    return {k: None if v is None else round(v, 1) for k, v in n.model_dump().items()}


def _range(low: float | None, high: float | None) -> str | None:
    return None if low is None or high is None else f"{low:.0f}-{high:.0f}"


def _day_totals(meals: list[Meal]) -> list[dict[str, Any]]:
    by_day: dict[date, list[Meal]] = defaultdict(list)
    for m in meals:
        by_day[m.day].append(m)
    out = []
    for d in sorted(by_day):
        total = Nutrients()
        for m in by_day[d]:
            total = total + m.totals
        low, high = total.band(by_day[d][0].uncertainty)
        partial = [
            field
            for field, value in total.model_dump().items()
            if value is not None
            and any(field in m.partial or getattr(m.totals, field) is None for m in by_day[d])
        ]
        out.append(
            {
                "date": d.isoformat(),
                "meals": len(by_day[d]),
                **_rounded(total),
                "kcal_range": _range(low.kcal, high.kcal),
                "partial": ", ".join(partial) or None,
            }
        )
    return out
