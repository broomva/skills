"""Nutrition: domain maths, the local food table, the private meal log and the CLI."""

from __future__ import annotations

import csv
import json
import stat
from datetime import date, time
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from broomva_health.adapters.food_db import FoodTable
from broomva_health.adapters.repositories.meals import MealLog
from broomva_health.cli.app import app
from broomva_health.config.paths import HealthPaths
from broomva_health.domain.nutrition import Food, Meal, MealItem, Nutrients, parse_item_spec

_LS, _PS = chr(0x2028), chr(0x2029)  # line / paragraph separators

RICE = Food(
    food_id="usda:1",
    source="usda",
    description="Rice, white, cooked",
    per_100g=Nutrients(kcal=130, protein_g=2.4, fat_g=0.2, carbs_g=28.6, fiber_g=0.4),
)
OIL = Food(
    food_id="usda:2",
    source="usda",
    description="Oil, olive",
    per_100g=Nutrients(kcal=884, fat_g=100),
)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# --- domain ------------------------------------------------------------------


def test_item_scales_per_100g_values() -> None:
    item = MealItem.of(RICE, 180)
    assert item.nutrients.kcal == pytest.approx(234)
    assert item.nutrients.carbs_g == pytest.approx(51.48)
    assert item.nutrients.sugars_g is None


def test_meal_totals_and_band() -> None:
    meal = Meal.build(
        [MealItem.of(RICE, 180), MealItem.of(OIL, 10, hidden=True)], day=date(2026, 1, 2)
    )
    assert meal.totals.kcal == pytest.approx(234 + 88.4)
    assert meal.totals.fat_g == pytest.approx(0.36 + 10)
    assert meal.low.kcal == pytest.approx(round(322.4 * 0.7, 1))
    assert meal.high.kcal == pytest.approx(round(322.4 * 1.3, 1))
    assert meal.items[1].hidden is True


def test_meal_needs_items_and_known_kind() -> None:
    with pytest.raises(ValueError, match="at least one item"):
        Meal.build([], day=date(2026, 1, 2))
    with pytest.raises(ValidationError):
        Meal.build([MealItem.of(RICE, 100)], day=date(2026, 1, 2), kind="brunch")


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("usda:171413=10", ("usda:171413", 10.0, False)),
        ("+usda:171413=7.5", ("usda:171413", 7.5, True)),
        (" co:arepa-blanca=90 ", ("co:arepa-blanca", 90.0, False)),
    ],
)
def test_parse_item_spec(spec: str, expected: tuple[str, float, bool]) -> None:
    assert parse_item_spec(spec) == expected


@pytest.mark.parametrize(
    "spec",
    [
        "rice=10",
        "usda:1",
        "usda:1=abc",
        "usda:1=0",
        "usda:1=-5",
        "usda:1=99999",
        "usda:1=1_000",
        "usda:1=1e3",
    ],
)
def test_parse_item_spec_rejects(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_item_spec(spec)


def test_negative_nutrients_rejected() -> None:
    with pytest.raises(ValidationError):
        Nutrients(kcal=-1)


# --- food table ----------------------------------------------------------------


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def _fdc_release(root: Path) -> Path:
    """A tiny FoodData Central CSV release with the real column layout."""
    rel = root / "FoodData_Central_foundation_food_csv_test"
    _write_csv(
        rel / "food.csv",
        ["fdc_id", "data_type", "description", "food_category_id", "publication_date"],
        [
            ["10", "foundation_food", "Rice, white, long-grain, cooked", "20", "2026-01-01"],
            ["11", "sample_food", "Rice, sample lot", "20", "2026-01-01"],
            ["12", "sr_legacy_food", "Oil, olive, salad or cooking", "4", "2019-04-01"],
            ["13", "foundation_food", "Water, tap", "14", "2026-01-01"],
        ],
    )
    _write_csv(
        rel / "food_nutrient.csv",
        ["id", "fdc_id", "nutrient_id", "amount"],
        [
            ["1", "10", "2047", "131"],  # Atwater energy only, as Foundation foods often report
            ["2", "10", "1003", "2.7"],
            ["3", "10", "1050", "28.0"],  # carbohydrate by summation only
            ["4", "11", "1008", "999"],  # a sample lot: never imported
            ["5", "12", "1008", "884"],
            ["6", "12", "1004", "100"],
            ["7", "13", "1051", "99.9"],  # water: no energy or macro -> skipped
        ],
    )
    return root


def test_usda_import_picks_types_and_fallback_ids(tmp_path: Path) -> None:
    with FoodTable(tmp_path / "db" / "foods.db") as table:
        assert table.import_usda(_fdc_release(tmp_path / "fdc")) == 2
        rice = table.get("usda:10")
        assert rice is not None
        assert rice.per_100g.kcal == 131
        assert rice.per_100g.carbs_g == 28.0
        assert table.get("usda:11") is None
        assert table.get("usda:13") is None
        assert [f.food_id for f in table.find("olive oil")] == ["usda:12"]
        assert [f.food_id for f in table.find("ric cook")] == ["usda:10"]  # prefix match
        assert table.find("  ") == []
    assert _mode(tmp_path / "db" / "foods.db") == 0o600
    assert _mode(tmp_path / "db") == 0o700


def test_usda_import_requires_a_release(tmp_path: Path) -> None:
    with FoodTable(tmp_path / "foods.db") as table, pytest.raises(FileNotFoundError):
        table.import_usda(tmp_path)


def test_csv_import_replaces_its_source_only(tmp_path: Path) -> None:
    staples = tmp_path / "co.csv"
    _write_csv(
        staples,
        ["food_id", "description", "kcal", "carbs_g"],
        [["arepa", "Arepa de maíz blanco", "219", "37"]],
    )
    with FoodTable(tmp_path / "foods.db") as table:
        table.import_usda(_fdc_release(tmp_path / "fdc"))
        assert table.import_csv(staples, source="co") == 1
        assert table.find("arepa maiz")[0].food_id == "co:arepa"  # accents folded
        _write_csv(staples, ["food_id", "description", "kcal"], [["patacon", "Patacón", "300"]])
        table.import_csv(staples, source="co")
        assert table.get("co:arepa") is None
        assert table.find("arepa") == []
        assert table.count() == {"co": 1, "usda": 2}


@pytest.mark.parametrize(
    ("header", "row", "source", "message"),
    [
        (["food_id", "description", "kcal"], ["a", "A", "x"], "co", "not a number"),
        (["food_id", "description", "kcal"], ["a", "A", "-3"], "co", "negative"),
        (["food_id", "kcal"], ["a", "1"], "co", "lacks column"),
        (["food_id", "description"], ["us:a", "A"], "co", "another source"),
        (["food_id", "description"], ["a", "A"], "usda", "not 'usda'"),
    ],
)
def test_csv_import_rejects(
    tmp_path: Path, header: list[str], row: list[str], source: str, message: str
) -> None:
    path = tmp_path / "t.csv"
    _write_csv(path, header, [row])
    with FoodTable(tmp_path / "foods.db") as table, pytest.raises(ValueError, match=message):
        table.import_csv(path, source=source)


# --- meal log ------------------------------------------------------------------


def test_meal_log_is_private_and_round_trips(tmp_path: Path) -> None:
    log = MealLog(tmp_path / "data")
    meal = Meal.build([MealItem.of(RICE, 150)], day=date(2026, 3, 4), at=time(13, 5), kind="lunch")
    log.append(meal)
    log.append(meal.model_copy(update={"day": date(2026, 3, 1)}))
    assert _mode(log.path) == 0o600
    assert _mode(tmp_path / "data") == 0o700
    assert [m.day for m in log.read()] == [date(2026, 3, 1), date(2026, 3, 4)]
    assert [m.day for m in log.last_days(2, today=date(2026, 3, 4))] == [date(2026, 3, 4)]


def test_photo_is_copied_not_moved(tmp_path: Path) -> None:
    src = tmp_path / "IMG.JPG"
    src.write_bytes(b"jpeg")
    log = MealLog(tmp_path / "data")
    meal = Meal.build([MealItem.of(RICE, 150)], day=date(2026, 3, 4), at=time(8, 0))
    first, second = log.keep_photo(src, meal), log.keep_photo(src, meal)
    assert first == "meal-photos/2026-03-04-0800.jpg"
    assert second == "meal-photos/2026-03-04-0800-1.jpg"
    assert src.exists()
    assert _mode(log.data_dir / first) == 0o600
    with pytest.raises(ValueError, match="photo must be"):
        log.keep_photo(_touch(tmp_path / "x.txt"), meal)


def _touch(path: Path) -> Path:
    path.write_text("x")
    return path


# --- CLI -----------------------------------------------------------------------


def test_cli_end_to_end(tmp_paths: HealthPaths, tmp_path: Path) -> None:
    runner = CliRunner()
    fdc = _fdc_release(tmp_path / "fdc")

    empty = runner.invoke(app, ["food", "find", "rice"])
    assert empty.exit_code != 0
    assert "import-usda" in empty.output

    imported = runner.invoke(app, ["-f", "json", "food", "import-usda", str(fdc)])
    assert imported.exit_code == 0, imported.output
    assert json.loads(imported.output)["imported"] == 2

    found = runner.invoke(app, ["-f", "json", "food", "find", "rice"])
    assert json.loads(found.output)[0]["food_id"] == "usda:10"

    logged = runner.invoke(
        app,
        [
            "-f",
            "json",
            "food",
            "log",
            "--meal",
            "lunch",
            "--at",
            "13:10",
            "--item",
            "usda:10=200",
            "--item",
            "+usda:12=10",
        ],
    )
    assert logged.exit_code == 0, logged.output
    meal = json.loads(logged.output)
    assert meal["totals"]["kcal"] == pytest.approx(262 + 88.4)
    assert meal["items"][1]["hidden"] is True

    shown = runner.invoke(app, ["-f", "json", "food", "show", "--totals"])
    assert json.loads(shown.output)[0]["meals"] == 1
    assert _mode(tmp_paths.data_dir / "meals.jsonl") == 0o600


@pytest.mark.parametrize(
    "args",
    [
        ["--item", "usda:999=10"],
        ["--item", "rice=10"],
        ["--item", "usda:10=10", "--meal", "brunch"],
        ["--item", "usda:10=10", "--at", "25:00"],
        ["--item", "usda:10=10", "--date", "yesterday"],
    ],
)
def test_cli_log_rejects_bad_input_and_writes_nothing(
    tmp_paths: HealthPaths, tmp_path: Path, args: list[str]
) -> None:
    runner = CliRunner()
    runner.invoke(app, ["food", "import-usda", str(_fdc_release(tmp_path / "fdc"))])
    result = runner.invoke(app, ["food", "log", *args])
    assert result.exit_code != 0
    assert not (tmp_paths.data_dir / "meals.jsonl").exists()


# --- regressions from P20 review (each pins a behaviour a mutation survived) ---------------


def _release(root: Path, foods: list[list[str]], nutrients: list[list[str]]) -> Path:
    _write_csv(
        root / "rel" / "food.csv",
        ["fdc_id", "data_type", "description", "food_category_id", "publication_date"],
        foods,
    )
    _write_csv(
        root / "rel" / "food_nutrient.csv", ["id", "fdc_id", "nutrient_id", "amount"], nutrients
    )
    return root


def test_usda_nutrient_id_priority_and_negative_values(tmp_path: Path) -> None:
    root = _release(
        tmp_path / "fdc",
        [["20", "foundation_food", "Bean, test", "16", "2026-01-01"]],
        [
            ["1", "20", "2047", "200"],
            ["2", "20", "1008", "100"],  # classic energy wins over Atwater
            ["3", "20", "1050", "30"],
            ["4", "20", "1005", "20"],  # by-difference carbs win over by-summation
            ["5", "20", "1003", "-1"],  # a negative amount is dropped, not stored
            ["6", "20", "1004", "2"],
        ],
    )
    with FoodTable(tmp_path / "foods.db") as table:
        table.import_usda(root)
        bean = table.get("usda:20")
    assert bean is not None
    assert bean.per_100g.kcal == 100
    assert bean.per_100g.carbs_g == 20
    assert bean.per_100g.protein_g is None


def test_bad_usda_folder_is_refused_and_keeps_the_table(tmp_path: Path) -> None:
    bad = tmp_path / "bad" / "rel"
    _write_csv(bad / "food.csv", ["fdc_id", "data_type", "descr"], [["1", "foundation_food", "x"]])
    _write_csv(
        bad / "food_nutrient.csv",
        ["id", "fdc_id", "nutrient_id", "amount"],
        [["1", "1", "1008", "5"]],
    )
    only_branded = _release(
        tmp_path / "branded",
        [["5", "branded_food", "Cola", "1", "2026-01-01"]],
        [["1", "5", "1008", "40"]],
    )
    with FoodTable(tmp_path / "foods.db") as table:
        table.import_usda(_fdc_release(tmp_path / "fdc"))
        with pytest.raises(ValueError, match="lacks description"):
            table.import_usda(tmp_path / "bad")
        with pytest.raises(ValueError, match="nothing was changed"):
            table.import_usda(only_branded)
        assert table.count() == {"usda": 2}


def test_csv_import_refuses_empty_and_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "t.csv"
    with FoodTable(tmp_path / "foods.db") as table:
        _write_csv(path, ["food_id", "description", "kcal"], [])
        with pytest.raises(ValueError, match="no rows"):
            table.import_csv(path, source="co")
        _write_csv(path, ["food_id", "description", "kcal"], [["a", "A", "1"], ["a", "B", "2"]])
        with pytest.raises(ValueError, match="duplicate"):
            table.import_csv(path, source="co")
        assert table.count() == {}


def test_reimport_leaves_one_search_row_per_food(tmp_path: Path) -> None:
    with FoodTable(tmp_path / "foods.db") as table:
        table.import_usda(_fdc_release(tmp_path / "fdc"))
        table.import_usda(_fdc_release(tmp_path / "fdc"))
        assert [f.food_id for f in table.find("rice")] == ["usda:10"]


def test_find_filters_by_source_ranks_by_relevance_and_ignores_connectors(tmp_path: Path) -> None:
    path = tmp_path / "co.csv"
    _write_csv(
        path,
        ["food_id", "description", "kcal"],
        [["short", "Rice cooked", "130"], ["dense", "Rice, rice cakes", "380"]],
    )
    with FoodTable(tmp_path / "foods.db") as table:
        table.import_usda(_fdc_release(tmp_path / "fdc"))
        table.import_csv(path, source="co")
        assert {f.source for f in table.find("rice", source="co")} == {"co"}
        # bm25 puts the description that says "rice" twice first, although it is longer
        assert table.find("rice", source="co")[0].food_id == "co:dense"
        assert [f.food_id for f in table.find("rice and long grain")] == ["usda:10"]


def test_existing_loose_files_are_tightened(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir(mode=0o755)
    data.chmod(0o755)
    (data / "meals.jsonl").write_text("")
    (data / "meals.jsonl").chmod(0o644)
    (data / "foods.db").write_bytes(b"")
    (data / "foods.db").chmod(0o644)
    with FoodTable(data / "foods.db"):
        pass
    assert _mode(data / "foods.db") == 0o600
    data.chmod(0o755)
    MealLog(data).append(Meal.build([MealItem.of(RICE, 100)], day=date(2026, 3, 4)))
    assert _mode(data / "meals.jsonl") == 0o600
    assert _mode(data) == 0o700


def test_last_days_boundary(tmp_path: Path) -> None:
    log = MealLog(tmp_path / "data")
    for d in (2, 3, 4):
        log.append(Meal.build([MealItem.of(RICE, 100)], day=date(2026, 3, d)))
    assert [m.day.day for m in log.last_days(2, today=date(2026, 3, 4))] == [3, 4]


def test_unreadable_line_is_skipped(tmp_path: Path) -> None:
    log = MealLog(tmp_path / "data")
    log.append(Meal.build([MealItem.of(RICE, 100)], day=date(2026, 3, 4)))
    with log.path.open("a") as fh:
        fh.write('{"day":"2026-0\n')
    assert len(log.read()) == 1


def test_photo_never_follows_a_symlink(tmp_path: Path) -> None:
    src = _touch(tmp_path / "IMG.jpg")
    log = MealLog(tmp_path / "data")
    log.photos_dir.mkdir(parents=True)
    outside = tmp_path / "outside.jpg"
    (log.photos_dir / "2026-03-04-0800.jpg").symlink_to(outside)
    meal = Meal.build([MealItem.of(RICE, 150)], day=date(2026, 3, 4), at=time(8, 0))
    assert log.keep_photo(src, meal) == "meal-photos/2026-03-04-0800-1.jpg"
    assert not outside.exists()


def test_cli_photo_totals_and_bad_import(tmp_paths: HealthPaths, tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(app, ["food", "import-usda", str(_fdc_release(tmp_path / "fdc"))])
    photo = _touch(tmp_path / "plate.png")
    first = runner.invoke(
        app, ["-f", "json", "food", "log", "--item", "usda:10=100", "--photo", str(photo)]
    )
    assert first.exit_code == 0, first.output
    kept = json.loads(first.output)["photo"]
    assert (tmp_paths.data_dir / kept).is_file()
    assert photo.exists()
    runner.invoke(app, ["food", "log", "--item", "usda:12=10"])
    day = json.loads(runner.invoke(app, ["-f", "json", "food", "show", "--totals"]).output)[0]
    assert day["meals"] == 2
    assert day["kcal"] == pytest.approx(131 + 88.4)

    empty = tmp_path / "empty"
    empty.mkdir()
    wiped = runner.invoke(app, ["food", "import-usda", str(empty)])
    assert wiped.exit_code == 2
    assert json.loads(runner.invoke(app, ["-f", "json", "food", "find", "rice"]).output)


# --- regressions from P20 review, stratum A -----------------------------------------------


def test_fndds_legacy_nutrient_numbers_are_mapped(tmp_path: Path) -> None:
    root = _release(
        tmp_path / "fdc",
        [["30", "survey_fndds_food", "Tortilla, corn", "50", "2024-10-31"]],
        [["1", "30", "208", "218"], ["2", "30", "203", "5.7"], ["3", "30", "205", "44.6"]],
    )
    _write_csv(
        root / "rel" / "nutrient.csv",
        ["id", "name", "unit_name", "nutrient_nbr", "rank"],
        [
            ["1008", "Energy", "KCAL", "208", "300"],
            ["1003", "Protein", "G", "203", "600"],
            ["1005", "Carbohydrate, by difference", "G", "205", "1110"],
        ],
    )
    with FoodTable(tmp_path / "foods.db") as table:
        assert table.import_usda(root) == 1
        tortilla = table.get("usda:30")
    assert tortilla is not None
    assert (tortilla.per_100g.kcal, tortilla.per_100g.protein_g, tortilla.per_100g.carbs_g) == (
        218,
        5.7,
        44.6,
    )


def test_symlinked_table_or_photo_folder_is_refused(tmp_path: Path) -> None:
    (tmp_path / "elsewhere.db").write_bytes(b"")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "foods.db").symlink_to(tmp_path / "elsewhere.db")
    with pytest.raises(ValueError, match="symlink"):
        FoodTable(tmp_path / "data" / "foods.db")
    log = MealLog(tmp_path / "data")
    (tmp_path / "outside").mkdir()
    log.photos_dir.symlink_to(tmp_path / "outside")
    meal = Meal.build([MealItem.of(RICE, 100)], day=date(2026, 3, 4))
    with pytest.raises(ValueError, match="symlink"):
        log.keep_photo(_touch(tmp_path / "a.jpg"), meal)
    log.path.symlink_to(tmp_path / "outside" / "meals.jsonl")
    with pytest.raises(ValueError, match="symlink"):
        log.append(meal)
    assert list((tmp_path / "outside").iterdir()) == []


def test_line_separator_in_a_note_round_trips(tmp_path: Path) -> None:
    log = MealLog(tmp_path / "data")
    log.append(Meal.build([MealItem.of(RICE, 100)], day=date(2026, 3, 4), note=f"a{_LS}b{_PS}c"))
    (meal,) = log.read()
    assert meal.note == f"a{_LS}b{_PS}c"
    assert _LS not in log.path.read_text(encoding="utf-8")


def test_partial_totals_and_nonfinite_values(tmp_path: Path) -> None:
    unknown = Food(food_id="co:x", source="co", description="X", per_100g=Nutrients(protein_g=5))
    meal = Meal.build([MealItem.of(RICE, 100), MealItem.of(unknown, 100)], day=date(2026, 3, 4))
    assert meal.totals.kcal == 130
    assert "kcal" in meal.partial
    assert "protein_g" not in meal.partial
    with pytest.raises(ValidationError):
        Nutrients(kcal=float("inf"))
    path = tmp_path / "t.csv"
    _write_csv(path, ["food_id", "description", "kcal"], [["a", "A", "inf"]])
    with FoodTable(tmp_path / "foods.db") as table, pytest.raises(ValueError):
        table.import_csv(path, source="co")


def test_cli_cleans_up_photo_when_the_meal_cannot_be_saved(
    tmp_paths: HealthPaths, tmp_path: Path
) -> None:
    runner = CliRunner()
    runner.invoke(app, ["food", "import-usda", str(_fdc_release(tmp_path / "fdc"))])
    (tmp_paths.data_dir / "meals.jsonl").mkdir()  # append will fail
    result = runner.invoke(
        app, ["food", "log", "--item", "usda:10=100", "--photo", str(_touch(tmp_path / "p.jpg"))]
    )
    assert result.exit_code != 0
    assert list((tmp_paths.data_dir / "meal-photos").iterdir()) == []


def test_cli_stores_time_and_flags_partial_day(tmp_paths: HealthPaths, tmp_path: Path) -> None:
    runner = CliRunner()
    staples = tmp_path / "co.csv"
    _write_csv(staples, ["food_id", "description", "protein_g"], [["q", "Queso", "18"]])
    runner.invoke(app, ["food", "import-usda", str(_fdc_release(tmp_path / "fdc"))])
    runner.invoke(app, ["food", "import-csv", str(staples), "--source", "co"])
    runner.invoke(app, ["food", "log", "--item", "usda:10=100", "--at", "07:45"])
    runner.invoke(app, ["food", "log", "--item", "co:q=50"])
    meals = json.loads(runner.invoke(app, ["-f", "json", "food", "show"]).output)
    assert meals[1]["at"] == "07:45"
    day = json.loads(runner.invoke(app, ["-f", "json", "food", "show", "--totals"]).output)[0]
    assert day["kcal"] == 131
    assert "kcal" in day["partial"]


@pytest.mark.parametrize("args", [["--date", "20261124"], ["--at", "1:2"], ["--at", "7:45"]])
def test_cli_enforces_date_and_time_formats(
    tmp_paths: HealthPaths, tmp_path: Path, args: list[str]
) -> None:
    runner = CliRunner()
    runner.invoke(app, ["food", "import-usda", str(_fdc_release(tmp_path / "fdc"))])
    assert runner.invoke(app, ["food", "log", "--item", "usda:10=10", *args]).exit_code == 2


def test_usda_nonfinite_amount_is_dropped(tmp_path: Path) -> None:
    root = _release(
        tmp_path / "fdc",
        [["40", "foundation_food", "Odd, test", "1", "2026-01-01"]],
        [["1", "40", "1008", "inf"], ["2", "40", "1003", "3"]],
    )
    with FoodTable(tmp_path / "foods.db") as table:
        table.import_usda(root)
        odd = table.get("usda:40")
    assert odd is not None
    assert odd.per_100g.kcal is None
    assert odd.per_100g.protein_g == 3


def test_raw_line_separator_written_by_another_tool_still_reads(tmp_path: Path) -> None:
    log = MealLog(tmp_path / "data")
    meal = Meal.build([MealItem.of(RICE, 100)], day=date(2026, 3, 4), note=f"x{_LS}y")
    log.data_dir.mkdir(parents=True)
    log.path.write_text(json.dumps(meal.model_dump(mode="json"), ensure_ascii=False) + "\n")
    assert [m.note for m in log.read()] == [f"x{_LS}y"]
