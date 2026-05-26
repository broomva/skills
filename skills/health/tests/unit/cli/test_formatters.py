"""Unit tests for ``broomva_health.cli.formatters``."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from broomva_health.cli.formatters import FORMATS, format_value


class _Row(BaseModel):
    name: str
    value: int
    when: datetime


@pytest.fixture
def sample_models() -> list[_Row]:
    return [
        _Row(name="alpha", value=1, when=datetime(2026, 1, 1, tzinfo=UTC)),
        _Row(name="beta", value=2, when=datetime(2026, 1, 2, tzinfo=UTC)),
    ]


def test_known_formats_are_exhaustive() -> None:
    assert set(FORMATS) == {"json", "jsonl", "csv", "tsv", "human"}


def test_unknown_format_raises() -> None:
    with pytest.raises(ValueError, match="unknown format"):
        format_value({"a": 1}, "yaml")  # type: ignore[arg-type]


def test_json_roundtrip_pydantic_list(sample_models: list[_Row]) -> None:
    out = format_value(sample_models, "json")
    parsed = json.loads(out)
    assert isinstance(parsed, list)
    assert parsed[0]["name"] == "alpha"
    # datetime serialization through pydantic's json mode.
    assert parsed[0]["when"].startswith("2026-01-01")


def test_jsonl_one_line_per_item(sample_models: list[_Row]) -> None:
    out = format_value(sample_models, "jsonl")
    lines = out.strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # each line is independently parseable


def test_jsonl_single_dict_becomes_one_line() -> None:
    out = format_value({"a": 1}, "jsonl")
    assert out.strip() == json.dumps({"a": 1})


def test_csv_writes_header_and_rows(sample_models: list[_Row]) -> None:
    out = format_value(sample_models, "csv")
    reader = csv.DictReader(io.StringIO(out))
    rows = list(reader)
    assert reader.fieldnames is not None
    assert set(reader.fieldnames) >= {"name", "value", "when"}
    assert rows[0]["name"] == "alpha"
    assert rows[1]["value"] == "2"


def test_tsv_uses_tab_delimiter() -> None:
    out = format_value([{"a": 1, "b": 2}], "tsv")
    header_line = out.splitlines()[0]
    assert "\t" in header_line
    assert "," not in header_line.replace(",", "")  # no stray commas in headers


def test_csv_flattens_nested_dict() -> None:
    data = [{"k": "v", "nested": {"x": 1, "y": {"z": 9}}}]
    out = format_value(data, "csv")
    rows = list(csv.DictReader(io.StringIO(out)))
    row = rows[0]
    assert row["k"] == "v"
    assert row["nested.x"] == "1"
    assert row["nested.y.z"] == "9"


def test_csv_serializes_list_value_as_json() -> None:
    data = [{"name": "alpha", "tags": ["a", "b"]}]
    out = format_value(data, "csv")
    rows = list(csv.DictReader(io.StringIO(out)))
    assert rows[0]["tags"] == '["a", "b"]'


def test_fields_filter_drops_unlisted_keys_and_preserves_order() -> None:
    data = [{"a": 1, "b": 2, "c": 3}, {"a": 4, "b": 5, "c": 6}]
    out_csv = format_value(data, "csv", fields=["c", "a"])
    reader = csv.DictReader(io.StringIO(out_csv))
    assert reader.fieldnames == ["c", "a"]
    rows = list(reader)
    assert rows[0]["c"] == "3"
    assert rows[1]["a"] == "4"

    out_json = format_value(data, "json", fields=["c", "a"])
    parsed = json.loads(out_json)
    assert list(parsed[0].keys()) == ["c", "a"]


def test_fields_filter_inserts_empty_for_missing() -> None:
    data = [{"a": 1}]
    out = format_value(data, "json", fields=["a", "missing"])
    parsed = json.loads(out)
    assert parsed[0]["a"] == 1
    assert parsed[0]["missing"] == ""


def test_human_format_on_list_of_dicts_includes_columns() -> None:
    out = format_value([{"name": "alpha", "value": 1}], "human")
    assert "name" in out
    assert "alpha" in out


def test_human_format_on_single_dict() -> None:
    out = format_value({"k": "v"}, "human")
    assert "k" in out
    assert "v" in out


def test_human_format_on_scalar_does_not_crash() -> None:
    out = format_value("hello", "human")
    assert "hello" in out


def test_pydantic_single_model_becomes_single_dict() -> None:
    model = _Row(name="x", value=42, when=datetime(2026, 5, 1, tzinfo=UTC))
    parsed = json.loads(format_value(model, "json"))
    assert parsed["name"] == "x"
    assert parsed["value"] == 42
