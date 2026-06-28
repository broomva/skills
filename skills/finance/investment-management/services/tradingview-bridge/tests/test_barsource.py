"""Tests for the shared bar sources (barsource.py)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tradingview_bridge.barsource import bars_from_csv, synthetic_bars


def test_synthetic_bars_deterministic_and_sized() -> None:
    a = synthetic_bars(50)
    assert len(a) == 50
    assert [b.close for b in a] == [b.close for b in synthetic_bars(50)]  # no RNG


def test_bars_from_csv_reads_close(tmp_path: Path) -> None:
    p = tmp_path / "b.csv"
    p.write_text("close\n100\n101.5\n")
    bars = bars_from_csv(p)
    assert [b.close for b in bars] == [Decimal("100"), Decimal("101.5")]
    assert bars[0].open == bars[0].high == bars[0].low == bars[0].close


def test_bars_from_csv_uses_ohlc_when_present(tmp_path: Path) -> None:
    p = tmp_path / "ohlc.csv"
    p.write_text("open,high,low,close\n99,102,98,101\n")
    bar = bars_from_csv(p)[0]
    assert (bar.open, bar.high, bar.low, bar.close) == (
        Decimal("99"),
        Decimal("102"),
        Decimal("98"),
        Decimal("101"),
    )


def test_bars_from_csv_empty_raises(tmp_path: Path) -> None:
    p = tmp_path / "e.csv"
    p.write_text("close\n")
    with pytest.raises(ValueError, match="no rows"):
        bars_from_csv(p)
