"""Tests for the qlib-backed bar source + the shared resolver (barsource.py).

CI never installs pyqlib, so the conversion is tested with a fake qlib injected
into sys.modules; the "not installed" path is tested against the genuine absence.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingview_bridge import barsource
from tradingview_bridge.barsource import bars_from_qlib, resolve_bars

_NAN = float("nan")
# The "not installed" path can only be exercised when qlib is genuinely absent
# (the CI condition). Locally pyqlib may be installed for the live dogfood.
_QLIB_INSTALLED = importlib.util.find_spec("qlib") is not None


def _install_fake_qlib(
    monkeypatch: pytest.MonkeyPatch, rows: list[tuple[tuple[str, datetime], dict[str, float]]]
) -> None:
    """Inject a fake `qlib` + `qlib.data.D` whose features() returns ``rows``."""

    class _Features:
        def iterrows(self) -> object:
            return iter(rows)

    class _D:
        def features(
            self,
            instruments: object,
            fields: object,
            start_time: object,
            end_time: object,
            freq: object,
        ) -> _Features:
            return _Features()

    fake_qlib = types.ModuleType("qlib")
    fake_qlib.init = lambda **_kw: None  # type: ignore[attr-defined]
    fake_qlib_data = types.ModuleType("qlib.data")
    fake_qlib_data.D = _D()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "qlib", fake_qlib)
    monkeypatch.setitem(sys.modules, "qlib.data", fake_qlib_data)
    barsource._QLIB_INITIALIZED.clear()


@pytest.mark.skipif(_QLIB_INSTALLED, reason="qlib installed; not-installed path can't be exercised")
def test_bars_from_qlib_not_installed_raises() -> None:
    """qlib is absent in CI → a clear, actionable RuntimeError (not a bare ImportError)."""
    with pytest.raises(RuntimeError, match="pyqlib"):
        bars_from_qlib("SH600000", start="2020-01-01", end="2020-12-31")


def test_bars_from_qlib_converts_ohlcv(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        (
            ("SH600000", datetime(2020, 1, 2)),
            {"$open": 1.0, "$high": 1.2, "$low": 0.9, "$close": 1.1, "$volume": 1000.0},
        ),
        (
            ("SH600000", datetime(2020, 1, 3)),
            {"$open": 1.1, "$high": 1.3, "$low": 1.0, "$close": 1.25, "$volume": 1500.0},
        ),
    ]
    _install_fake_qlib(monkeypatch, rows)
    bars = bars_from_qlib("SH600000", start="2020-01-01", end="2020-01-31", provider_uri="fake://t")
    assert len(bars) == 2
    assert bars[0].open == Decimal("1.0")
    assert bars[0].close == Decimal("1.1")
    assert bars[0].volume == Decimal("1000.0")
    assert bars[0].ts.tzinfo is not None  # tz-attached
    assert bars[1].close == Decimal("1.25")


def test_bars_from_qlib_skips_nan_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        (
            ("SH600000", datetime(2020, 1, 2)),
            {"$open": 1.0, "$high": 1.2, "$low": 0.9, "$close": _NAN, "$volume": _NAN},
        ),
        (
            ("SH600000", datetime(2020, 1, 3)),
            {"$open": 1.1, "$high": 1.3, "$low": 1.0, "$close": 1.25, "$volume": 1500.0},
        ),
    ]
    _install_fake_qlib(monkeypatch, rows)
    bars = bars_from_qlib("SH600000", start="2020-01-01", end="2020-01-31", provider_uri="fake://t")
    assert len(bars) == 1  # the NaN-close (suspended) day is skipped
    assert bars[0].close == Decimal("1.25")


def test_bars_from_qlib_all_nan_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        (
            ("SH600000", datetime(2020, 1, 2)),
            {"$open": _NAN, "$high": _NAN, "$low": _NAN, "$close": _NAN, "$volume": _NAN},
        ),
    ]
    _install_fake_qlib(monkeypatch, rows)
    with pytest.raises(ValueError, match="no usable bars"):
        bars_from_qlib("SH600000", start="2020-01-01", end="2020-01-31", provider_uri="fake://t")


# --- resolve_bars precedence: qlib > csv > synthetic -----------------------


def test_resolve_bars_synthetic_default() -> None:
    assert len(resolve_bars(synthetic_n=50)) == 50


def test_resolve_bars_csv(tmp_path: Path) -> None:
    p = tmp_path / "b.csv"
    p.write_text("close\n100\n101\n")
    bars = resolve_bars(bars_csv=str(p))
    assert [b.close for b in bars] == [Decimal("100"), Decimal("101")]


def test_resolve_bars_qlib_takes_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """qlib wins over csv + synthetic when given (verified via the fake)."""
    rows = [
        (
            ("SH600000", datetime(2020, 1, 2)),
            {"$open": 7.0, "$high": 7.0, "$low": 7.0, "$close": 7.0, "$volume": 1.0},
        ),
    ]
    _install_fake_qlib(monkeypatch, rows)
    csv_path = tmp_path / "ignored.csv"
    csv_path.write_text("close\n100\n101\n")
    bars = resolve_bars(qlib="SH600000", bars_csv=str(csv_path), synthetic_n=10)
    assert len(bars) == 1  # the qlib row, not the 2 csv rows or 10 synthetic
    assert bars[0].close == Decimal("7.0")
