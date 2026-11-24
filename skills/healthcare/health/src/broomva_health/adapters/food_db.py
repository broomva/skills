"""Local food-composition table: SQLite + an FTS5 index, built from public tables.

Nothing here touches the network. ``import_usda`` reads USDA FoodData Central
CSV releases the user downloaded (https://fdc.nal.usda.gov/download-datasets):
Foundation Foods, SR Legacy and FNDDS. ``import_csv`` adds a hand-made table,
for example regional staples missing from USDA, with the columns
``food_id, description, kcal, protein_g, fat_g, carbs_g, fiber_g, sugars_g``.

All values are per 100 g. Re-importing a source replaces that source's rows.
"""

from __future__ import annotations

import contextlib
import csv
import math
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
# Connecting words that food descriptions rarely contain ("rice and beans", "arroz con pollo").
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {"a", "an", "and", "of", "or", "the", "with", "con", "de", "del", "el", "en", "la", "y"}
)

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
        os.chmod(path.parent, 0o700)
        try:  # create it private before SQLite ever opens it; another process may win the race
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
        except FileExistsError:
            pass
        if path.is_symlink():
            raise ValueError(f"{path} is a symlink; refusing to write health data through it")
        os.chmod(path, 0o600)  # also tightens a table created by an older version
        # Autocommit mode: writes take an explicit BEGIN IMMEDIATE (see _replace).
        self._conn = sqlite3.connect(path, isolation_level=None)
        try:
            self._conn.executescript(_SCHEMA)
        except BaseException:
            self._conn.close()  # a corrupt file must not leak the connection
            raise

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
            legacy = _legacy_numbers(release / "nutrient.csv")
            values = _usda_values(release / "food_nutrient.csv", names.keys(), legacy)
            found = 0
            for fdc_id, description in names.items():
                picked = _pick(values.get(fdc_id, {}))
                if picked:
                    foods[fdc_id] = (description, picked)
                    found += 1
            if names and not found:
                # Foods but no usable values: a broken or unmapped release. Refuse the whole
                # import rather than silently dropping this release from the table.
                raise ValueError(f"{release}: {len(names)} foods but no usable nutrient values")
        if not foods:
            # Never replace the table with nothing: a wrong folder must not wipe it.
            raise ValueError(f"no importable foods under {root}: nothing was changed")
        rows = [(f"usda:{fid}", desc, nut) for fid, (desc, nut) in foods.items()]
        return self._replace("usda", rows)

    def import_csv(self, path: Path, *, source: str) -> int:
        """Import a hand-made per-100 g table. Ids without a ``source:`` prefix get one."""
        if not _SOURCE.match(source) or source == "usda":
            raise ValueError(
                f"source must be lowercase letters, digits, '-' or '_' and not 'usda', got {source!r}"
            )
        rows: list[tuple[str, str, dict[str, float]]] = []
        seen: set[str] = set()
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
                if food_id in seen:
                    raise ValueError(f"{path}:{line}: duplicate food_id {food_id!r}")
                seen.add(food_id)
                rows.append((food_id, description, nutrients))
        if not rows:
            raise ValueError(f"{path} has no rows: nothing was changed")
        return self._replace(source, rows)

    def _replace(self, source: str, rows: list[tuple[str, str, dict[str, float]]]) -> int:
        # BEGIN IMMEDIATE takes the write lock before reading the old ids, so two imports
        # of one source cannot interleave and leave search rows for deleted foods.
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            # One set delete: food_id is UNINDEXED in FTS, so a per-id delete scans the
            # whole index each time (quadratic; 8 s instead of 0.02 s for a USDA re-import).
            self._conn.execute(
                "DELETE FROM foods_fts WHERE food_id IN (SELECT food_id FROM foods WHERE source = ?)",
                (source,),
            )
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
            self._conn.execute("COMMIT")
        except BaseException:
            if self._conn.in_transaction:
                with contextlib.suppress(sqlite3.Error):  # keep the original error
                    self._conn.execute("ROLLBACK")
            raise
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
        words = [w for w in words if w not in _STOPWORDS] or words
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


def _require(reader: csv.DictReader[str], required: set[str], path: Path) -> None:
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"{path} is not a FoodData Central file: lacks {', '.join(sorted(missing))}"
        )


def _usda_foods(food_csv: Path) -> dict[str, str]:
    with food_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        _require(reader, {"fdc_id", "data_type", "description"}, food_csv)
        return {
            row["fdc_id"]: row["description"].strip()
            for row in reader
            if row.get("data_type") in USDA_DATA_TYPES and row.get("description")
        }


def _legacy_numbers(nutrient_csv: Path) -> dict[str, str]:
    """Map legacy nutrient numbers (``208``) to FoodData Central ids (``1008``).

    FNDDS releases key ``food_nutrient.csv`` by the legacy number; the release's own
    ``nutrient.csv`` carries both, so the mapping comes from the release, not from us.
    """
    if not nutrient_csv.exists():
        return {}
    with nutrient_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        _require(reader, {"id", "nutrient_nbr"}, nutrient_csv)
        out: dict[str, str] = {}
        for row in reader:
            nbr = (row.get("nutrient_nbr") or "").strip()
            if nbr.endswith(".0"):
                nbr = nbr[:-2]
            nid = (row.get("id") or "").strip()
            if not nbr or nid not in _WANTED:
                continue  # only the nutrients we import; others cannot shadow them
            if out.get(nbr, nid) != nid:
                raise ValueError(
                    f"{nutrient_csv}: legacy number {nbr} maps to both {out[nbr]} and {nid}"
                )
            out[nbr] = nid
        return out


def _usda_values(
    nutrient_csv: Path, fdc_ids: Iterable[str], legacy: dict[str, str] | None = None
) -> dict[str, dict[str, float]]:
    wanted_foods = set(fdc_ids)
    legacy = legacy or {}
    out: dict[str, dict[str, float]] = {}
    with nutrient_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        _require(reader, {"fdc_id", "nutrient_id", "amount"}, nutrient_csv)
        for row in reader:
            nid = row["nutrient_id"]
            if nid not in _WANTED:
                nid = legacy.get(nid, nid)
            if nid in _WANTED and row["fdc_id"] in wanted_foods and row.get("amount"):
                try:
                    amount = float(row["amount"])
                except ValueError:
                    continue
                if math.isfinite(amount):
                    out.setdefault(row["fdc_id"], {})[nid] = amount
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
