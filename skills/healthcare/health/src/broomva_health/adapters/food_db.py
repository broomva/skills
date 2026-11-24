"""Local food-composition table: SQLite + an FTS5 index, built from public tables.

Nothing here touches the network. ``import_usda`` reads USDA FoodData Central
CSV releases the user downloaded (https://fdc.nal.usda.gov/download-datasets):
Foundation Foods, SR Legacy and FNDDS. ``import_csv`` adds a hand-made table,
for example regional staples missing from USDA, with the columns
``food_id, description, kcal, protein_g, fat_g, carbs_g, fiber_g, sugars_g``.

All values are per 100 g. Re-importing a source replaces that source's rows.
"""

from __future__ import annotations

import csv
import os
import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from broomva_health.domain.nutrition import Food, Nutrients

__all__ = ["USDA_DATA_TYPES", "FoodTable"]

#: FoodData Central data types worth importing. Branded foods are left out: they
#: are label declarations, mostly US products, and 3 GB.
USDA_DATA_TYPES: Final[frozenset[str]] = frozenset(
    {"foundation_food", "sr_legacy_food", "survey_fndds_food"}
)

# FoodData Central nutrient ids, best first. Foundation foods often report energy
# only through the Atwater factors (2047/2048), not the classic 1008.
_NUTRIENT_IDS: Final[dict[str, tuple[str, ...]]] = {
    "kcal": ("1008", "2048", "2047"),
    "protein_g": ("1003",),
    "fat_g": ("1004",),
    "carbs_g": ("1005", "1050"),
    "fiber_g": ("1079",),
    "sugars_g": ("2000", "1063"),
}
_WANTED: Final[frozenset[str]] = frozenset(i for ids in _NUTRIENT_IDS.values() for i in ids)
_FIELDS: Final[tuple[str, ...]] = tuple(_NUTRIENT_IDS)
_SOURCE: Final = re.compile(r"^[a-z0-9_-]+$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS foods (
    food_id     TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    description TEXT NOT NULL,
    kcal REAL, protein_g REAL, fat_g REAL, carbs_g REAL, fiber_g REAL, sugars_g REAL
);
CREATE VIRTUAL TABLE IF NOT EXISTS foods_fts USING fts5(
    food_id UNINDEXED, description, tokenize = 'unicode61 remove_diacritics 2'
);
"""


class FoodTable:
    """The local food table at ``path`` (created 0600 inside a 0700 directory)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        new = not path.exists()
        self._conn = sqlite3.connect(path)
        if new:
            os.chmod(path, 0o600)
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> FoodTable:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # --- import -------------------------------------------------------------

    def import_usda(self, root: Path) -> int:
        """Import every FoodData Central CSV release found under ``root``."""
        releases = sorted(
            {p.parent for p in root.rglob("food_nutrient.csv") if (p.parent / "food.csv").exists()}
        )
        if not releases:
            raise FileNotFoundError(
                f"no FoodData Central CSV release (food.csv + food_nutrient.csv) under {root}"
            )
        foods: dict[str, tuple[str, dict[str, float]]] = {}
        for release in releases:
            names = _usda_foods(release / "food.csv")
            values = _usda_values(release / "food_nutrient.csv", names.keys())
            for fdc_id, description in names.items():
                picked = _pick(values.get(fdc_id, {}))
                if picked:
                    foods[fdc_id] = (description, picked)
        rows = [(f"usda:{fid}", desc, nut) for fid, (desc, nut) in foods.items()]
        return self._replace("usda", rows)

    def import_csv(self, path: Path, *, source: str) -> int:
        """Import a hand-made per-100 g table. Ids without a ``source:`` prefix get one."""
        if not _SOURCE.match(source) or source == "usda":
            raise ValueError(
                f"source must be lowercase letters, digits, '-' or '_' and not 'usda', got {source!r}"
            )
        rows: list[tuple[str, str, dict[str, float]]] = []
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            missing = {"food_id", "description"} - set(reader.fieldnames or ())
            if missing:
                raise ValueError(f"{path} lacks column(s): {', '.join(sorted(missing))}")
            for line, row in enumerate(reader, start=2):
                raw_id = (row.get("food_id") or "").strip()
                description = (row.get("description") or "").strip()
                if not raw_id or not description:
                    raise ValueError(f"{path}:{line}: food_id and description are required")
                food_id = raw_id if ":" in raw_id else f"{source}:{raw_id}"
                if not food_id.startswith(f"{source}:"):
                    raise ValueError(f"{path}:{line}: id {food_id!r} belongs to another source")
                nutrients: dict[str, float] = {}
                for field in _FIELDS:
                    cell = (row.get(field) or "").strip()
                    if cell:
                        try:
                            nutrients[field] = float(cell)
                        except ValueError as exc:
                            raise ValueError(
                                f"{path}:{line}: {field} is not a number: {cell!r}"
                            ) from exc
                Food(
                    food_id=food_id,
                    source=source,
                    description=description,
                    per_100g=Nutrients(**nutrients),
                )
                rows.append((food_id, description, nutrients))
        return self._replace(source, rows)

    def _replace(self, source: str, rows: list[tuple[str, str, dict[str, float]]]) -> int:
        with self._conn:
            ids = [
                r[0]
                for r in self._conn.execute("SELECT food_id FROM foods WHERE source = ?", (source,))
            ]
            self._conn.executemany("DELETE FROM foods_fts WHERE food_id = ?", ((i,) for i in ids))
            self._conn.execute("DELETE FROM foods WHERE source = ?", (source,))
            self._conn.executemany(
                f"INSERT OR REPLACE INTO foods (food_id, source, description, {', '.join(_FIELDS)}) "  # noqa: S608 — fixed column names
                f"VALUES (?, ?, ?, {', '.join('?' for _ in _FIELDS)})",
                ((fid, source, desc, *(nut.get(f) for f in _FIELDS)) for fid, desc, nut in rows),
            )
            self._conn.executemany(
                "INSERT INTO foods_fts (food_id, description) VALUES (?, ?)",
                ((fid, desc) for fid, desc, _ in rows),
            )
        return len(rows)

    # --- read ---------------------------------------------------------------

    def count(self) -> dict[str, int]:
        return dict(
            self._conn.execute("SELECT source, count(*) FROM foods GROUP BY source ORDER BY source")
        )

    def get(self, food_id: str) -> Food | None:
        row = self._conn.execute(
            f"SELECT food_id, source, description, {', '.join(_FIELDS)} FROM foods WHERE food_id = ?",  # noqa: S608
            (food_id,),
        ).fetchone()
        return _food(row) if row else None

    def find(self, query: str, *, limit: int = 10, source: str | None = None) -> list[Food]:
        """Foods whose description matches every word of ``query`` (prefix match), best first."""
        words = re.findall(r"\w+", query.lower())
        if not words:
            return []
        match = " ".join(f'"{w}"*' for w in words)
        sql = (
            f"SELECT f.food_id, f.source, f.description, {', '.join('f.' + c for c in _FIELDS)} "  # noqa: S608
            "FROM foods_fts JOIN foods f ON f.food_id = foods_fts.food_id "
            "WHERE foods_fts MATCH ? "
        )
        params: list[object] = [match]
        if source:
            sql += "AND f.source = ? "
            params.append(source)
        sql += "ORDER BY bm25(foods_fts), length(f.description) LIMIT ?"
        params.append(limit)
        return [_food(r) for r in self._conn.execute(sql, params)]


def _food(row: tuple[object, ...]) -> Food:
    food_id, source, description, *values = row
    return Food(
        food_id=str(food_id),
        source=str(source),
        description=str(description),
        per_100g=Nutrients(**{f: v for f, v in zip(_FIELDS, values, strict=True) if v is not None}),
    )


def _usda_foods(food_csv: Path) -> dict[str, str]:
    with food_csv.open(newline="", encoding="utf-8") as fh:
        return {
            row["fdc_id"]: row["description"].strip()
            for row in csv.DictReader(fh)
            if row.get("data_type") in USDA_DATA_TYPES and row.get("description")
        }


def _usda_values(nutrient_csv: Path, fdc_ids: Iterable[str]) -> dict[str, dict[str, float]]:
    wanted_foods = set(fdc_ids)
    out: dict[str, dict[str, float]] = {}
    with nutrient_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (
                row["nutrient_id"] in _WANTED
                and row["fdc_id"] in wanted_foods
                and row.get("amount")
            ):
                try:
                    out.setdefault(row["fdc_id"], {})[row["nutrient_id"]] = float(row["amount"])
                except ValueError:
                    continue
    return out


def _pick(by_id: dict[str, float]) -> dict[str, float]:
    picked: dict[str, float] = {}
    for field, ids in _NUTRIENT_IDS.items():
        for nid in ids:
            if nid in by_id and by_id[nid] >= 0:
                picked[field] = by_id[nid]
                break
    has_macro = any(k in picked for k in ("kcal", "protein_g", "fat_g", "carbs_g"))
    return picked if has_macro else {}
