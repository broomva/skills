"""Tests for the `health series` aggregation helpers.

The pure logic (`_bucket_key` calendar bucketing + `_aggregate` reducers) is the
risk surface; the query glue is proven by dogfood. Covered here exhaustively.
"""

from __future__ import annotations

from datetime import date

from broomva_health.cli.series import Agg, Bucket, _aggregate, _bucket_key


def test_bucket_key_day() -> None:
    assert _bucket_key(date(2026, 6, 12), Bucket.day) == "2026-06-12"


def test_bucket_key_week() -> None:
    # 2026-06-12 falls in ISO week 24 (verified against the real dataset).
    assert _bucket_key(date(2026, 6, 12), Bucket.week) == "2026-W24"


def test_bucket_key_month() -> None:
    assert _bucket_key(date(2026, 6, 12), Bucket.month) == "2026-06"
    assert _bucket_key(date(2026, 1, 5), Bucket.month) == "2026-01"  # zero-padded


def test_bucket_key_quarter() -> None:
    assert _bucket_key(date(2026, 1, 15), Bucket.quarter) == "2026-Q1"
    assert _bucket_key(date(2026, 4, 1), Bucket.quarter) == "2026-Q2"
    assert _bucket_key(date(2026, 9, 30), Bucket.quarter) == "2026-Q3"
    assert _bucket_key(date(2026, 12, 31), Bucket.quarter) == "2026-Q4"


def test_bucket_key_year() -> None:
    assert _bucket_key(date(2026, 6, 12), Bucket.year) == "2026"


def test_bucket_keys_sort_chronologically() -> None:
    # Zero-padding guarantees lexicographic == chronological ordering.
    keys = [
        _bucket_key(date(2026, 2, 1), Bucket.month),
        _bucket_key(date(2026, 11, 1), Bucket.month),
        _bucket_key(date(2025, 12, 1), Bucket.month),
    ]
    assert sorted(keys) == ["2025-12", "2026-02", "2026-11"]


def test_aggregate_all_reducers() -> None:
    v = [10.0, 20.0, 30.0]  # chronological order
    assert _aggregate(v, Agg.mean) == 20.0
    assert _aggregate(v, Agg.sum) == 60.0
    assert _aggregate(v, Agg.min) == 10.0
    assert _aggregate(v, Agg.max) == 30.0
    assert _aggregate(v, Agg.first) == 10.0
    assert _aggregate(v, Agg.last) == 30.0
    assert _aggregate(v, Agg.count) == 3.0


def test_aggregate_single_value() -> None:
    assert _aggregate([42.0], Agg.mean) == 42.0
    assert _aggregate([42.0], Agg.count) == 1.0
