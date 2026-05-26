"""CLI output formatters.

Every CLI subcommand routes user-visible output through `format_value` so
the `--format/-f` flag is honored uniformly. Direct `print(json.dumps(...))`
calls inside subcommands are an explicit anti-pattern.

Formats:
- ``json``  — pretty-printed (indent=2), single document
- ``jsonl`` — one compact JSON object per line (list inputs only flatten)
- ``csv``   — RFC 4180, headers from union of keys, nested dicts flattened
- ``tsv``   — same as csv with tab delimiter
- ``human`` — rich.Table for list-of-dicts, pretty repr for everything else

Pydantic ``BaseModel`` instances are converted via ``.model_dump(mode="json")``
so datetimes / UUIDs / enums become strings before serialization. Nested
dicts inside CSV/TSV rows are flattened with dotted keys (``a.b.c``).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal, get_args

from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

__all__ = ["FORMATS", "Format", "format_value"]


Format = Literal["json", "jsonl", "csv", "tsv", "human"]

FORMATS: tuple[str, ...] = tuple(get_args(Format))


# ---------------------------------------------------------------------------
# Normalization — Pydantic models → plain dicts before any serialization.
# ---------------------------------------------------------------------------


def _normalize(data: Any) -> Any:
    """Recursively coerce Pydantic models into JSON-mode primitives.

    Lists/tuples become lists. Models become dicts via ``model_dump(mode="json")``
    so datetimes serialize as ISO strings, enums as their values, etc. Plain
    dicts pass through with their values normalized. Everything else passes
    through unchanged.
    """

    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if isinstance(data, Mapping):
        return {key: _normalize(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)) and not isinstance(data, (str, bytes)):
        return [_normalize(item) for item in data]
    return data


# ---------------------------------------------------------------------------
# Flatten — for CSV/TSV — turn ``{"a": {"b": 1}}`` into ``{"a.b": 1}``.
# Lists become a JSON string (CSV is not the right format for nested arrays).
# ---------------------------------------------------------------------------


def _flatten(prefix: str, value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, Mapping):
        if not value:  # empty dict — record as empty string
            out[prefix] = ""
            return
        for key, sub in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            _flatten(child, sub, out)
    elif isinstance(value, (list, tuple)) and not isinstance(value, (str, bytes)):
        out[prefix] = json.dumps(value, default=str)
    else:
        out[prefix] = value


def _flatten_row(row: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in row.items():
        _flatten(str(key), value, flat)
    return flat


# ---------------------------------------------------------------------------
# Field filtering — applied AFTER flattening so dotted keys can be selected.
# Preserves the user-supplied ordering.
# ---------------------------------------------------------------------------


def _filter_fields(row: Mapping[str, Any], fields: Sequence[str] | None) -> dict[str, Any]:
    if not fields:
        return dict(row)
    return {key: row.get(key, "") for key in fields}


# ---------------------------------------------------------------------------
# Backends.
# ---------------------------------------------------------------------------


def _to_rows(data: Any) -> list[dict[str, Any]]:
    """Coerce into a list-of-dicts shape for tabular output. Scalars/strings
    become a single 'value' column; lists of scalars likewise."""

    if isinstance(data, Mapping):
        return [dict(data)]
    if isinstance(data, list):
        rows: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, Mapping):
                rows.append(dict(item))
            else:
                rows.append({"value": item})
        return rows
    return [{"value": data}]


def _format_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, sort_keys=False)


def _format_jsonl(data: Any) -> str:
    items = data if isinstance(data, list) else [data]
    return "\n".join(json.dumps(item, default=str, sort_keys=False) for item in items)


def _format_delimited(
    data: Any, delimiter: str, fields: Sequence[str] | None
) -> str:
    rows = _to_rows(data)
    flat_rows = [_flatten_row(row) for row in rows]
    flat_rows = [_filter_fields(row, fields) for row in flat_rows]
    # Header is the union of keys, preserving first-seen order; if fields was
    # supplied, _filter_fields has already pinned the header order for us.
    header: list[str] = []
    seen: set[str] = set()
    for row in flat_rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                header.append(key)
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=header,
        delimiter=delimiter,
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in flat_rows:
        # csv.DictWriter coerces None → empty; we want stable string repr for
        # bools / numbers, which Python's str() already provides.
        stringified = {key: ("" if value is None else value) for key, value in row.items()}
        writer.writerow(stringified)
    return buffer.getvalue().rstrip("\n") + "\n" if header else ""


def _format_human(data: Any, fields: Sequence[str] | None) -> str:
    console = Console(file=io.StringIO(), force_terminal=False, color_system=None, width=120)
    if isinstance(data, list) and data and all(isinstance(item, Mapping) for item in data):
        flat_rows = [_flatten_row(row) for row in data]
        flat_rows = [_filter_fields(row, fields) for row in flat_rows]
        header: list[str] = []
        seen: set[str] = set()
        for row in flat_rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    header.append(key)
        table = Table(show_header=True, header_style="bold")
        for column in header:
            table.add_column(column)
        for row in flat_rows:
            table.add_row(*["" if row.get(col) is None else str(row.get(col)) for col in header])
        console.print(table)
    elif isinstance(data, Mapping):
        flat = _flatten_row(data)
        flat = _filter_fields(flat, fields)
        table = Table(show_header=True, header_style="bold")
        table.add_column("key")
        table.add_column("value")
        for key, value in flat.items():
            table.add_row(str(key), "" if value is None else str(value))
        console.print(table)
    else:
        console.print(data)
    output = console.file.getvalue()  # type: ignore[union-attr]
    return output.rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def format_value(
    data: Any,
    fmt: Format,
    *,
    fields: Iterable[str] | None = None,
) -> str:
    """Serialize ``data`` as ``fmt``.

    Accepts dicts, lists of dicts, Pydantic BaseModels, lists of BaseModels,
    and primitives. Returns a single string ready for ``print()`` (no
    trailing-newline guarantee — callers append one if they want it).

    ``fields`` filters keys (post-flattening) to those listed, preserving the
    listed order. Unknown fields become empty cells.
    """

    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}; choose from {FORMATS}")
    field_list = list(fields) if fields is not None else None
    normalized = _normalize(data)

    if fmt == "json":
        if field_list:
            rows = [_filter_fields(_flatten_row(row), field_list) for row in _to_rows(normalized)]
            normalized = rows if isinstance(normalized, list) else rows[0]
        return _format_json(normalized)
    if fmt == "jsonl":
        if field_list:
            rows = [_filter_fields(_flatten_row(row), field_list) for row in _to_rows(normalized)]
            normalized = rows if isinstance(normalized, list) else rows[0]
        return _format_jsonl(normalized)
    if fmt == "csv":
        return _format_delimited(normalized, ",", field_list)
    if fmt == "tsv":
        return _format_delimited(normalized, "\t", field_list)
    if fmt == "human":
        return _format_human(normalized, field_list)
    raise AssertionError(f"unreachable format branch for {fmt!r}")  # pragma: no cover
