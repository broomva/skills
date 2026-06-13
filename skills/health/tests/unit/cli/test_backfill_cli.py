"""Unit tests for the `health backfill` CLI date-resolution helpers.

Pure-function coverage for `--from` / `--months` / `--days` start resolution —
no container or network needed.
"""

from __future__ import annotations

from datetime import date

import pytest
import typer

from broomva_health.cli.backfill import _months_ago, _resolve_start


def test_months_ago_simple() -> None:
    assert _months_ago(date(2026, 6, 12), 10) == date(2025, 8, 12)


def test_months_ago_crosses_year() -> None:
    assert _months_ago(date(2026, 2, 15), 3) == date(2025, 11, 15)


def test_months_ago_clamps_to_month_length() -> None:
    # 31 Mar minus 1 month → Feb has no 31st → clamp to 28 (2026 is not a leap year).
    assert _months_ago(date(2026, 3, 31), 1) == date(2026, 2, 28)


def test_resolve_start_from_date() -> None:
    start = _resolve_start(
        from_date="2025-08-12", months=None, days=None, end=date(2026, 6, 12)
    )
    assert start == date(2025, 8, 12)


def test_resolve_start_months() -> None:
    start = _resolve_start(from_date=None, months=10, days=None, end=date(2026, 6, 12))
    assert start == date(2025, 8, 12)


def test_resolve_start_days() -> None:
    start = _resolve_start(from_date=None, months=None, days=14, end=date(2026, 6, 12))
    assert start == date(2026, 5, 29)


def test_resolve_start_requires_one() -> None:
    with pytest.raises(typer.BadParameter, match="one of --from"):
        _resolve_start(from_date=None, months=None, days=None, end=date(2026, 6, 12))


def test_resolve_start_rejects_multiple() -> None:
    with pytest.raises(typer.BadParameter, match="only one of"):
        _resolve_start(from_date="2025-08-12", months=10, days=None, end=date(2026, 6, 12))


def test_resolve_start_rejects_nonpositive_months() -> None:
    with pytest.raises(typer.BadParameter, match="must be positive"):
        _resolve_start(from_date=None, months=0, days=None, end=date(2026, 6, 12))
