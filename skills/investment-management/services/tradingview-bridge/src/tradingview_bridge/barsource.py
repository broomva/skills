"""Bar sources — synthetic, CSV, and (optional) qlib-backed real market data.

Extracted from orchestrator/cli so the orchestrator, optimizer, and roster CLIs
can all build bars from one place without importing each other (which would risk a
dependency cycle now that the orchestrator reads the roster).

Three sources, increasing in realism:
  - synthetic_bars — deterministic, no deps (the default; reproducible).
  - bars_from_csv — a flat CSV with a 'close' column.
  - bars_from_qlib — real OHLCV from a local qlib data provider (the optional
    `pyqlib` extra; the "data-layer graft"). Their point-in-time data, our pipeline.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from .strategy.types import Bar

_BASE_TS = datetime(2026, 1, 1, tzinfo=UTC)


def synthetic_bars(n: int = 200) -> list[Bar]:
    """A deterministic four-regime series (uptrend → chop → downtrend → recovery).

    Deterministic on purpose: the same n always yields the same bars, so a CLI run
    is reproducible and the strategies genuinely differ across regimes (which makes
    a leaderboard or an optimization meaningful rather than a coin-flip).
    """
    closes: list[float] = []
    price = 100.0
    for i in range(n):
        frac = i / n
        if frac < 0.25:
            price *= 1.012
        elif frac < 0.5:
            price += 1.5 if (i % 6) < 3 else -1.5
        elif frac < 0.75:
            price *= 0.99
        else:
            price *= 1.008
        # Deterministic per-bar jitter (cycles -2..+2, no RNG → still reproducible)
        # so bar-to-bar returns vary and Sharpe lands in a realistic range rather
        # than the near-infinite values a perfectly smooth synthetic trend yields.
        price += ((i * 7) % 5) - 2.0
        price = max(5.0, price)
        closes.append(round(price, 2))
    return [
        Bar(
            ts=_BASE_TS + timedelta(days=i),
            open=Decimal(str(c)),
            high=Decimal(str(c)),
            low=Decimal(str(c)),
            close=Decimal(str(c)),
        )
        for i, c in enumerate(closes)
    ]


def _cell(row: dict[str, str], key: str, default: Decimal) -> Decimal:
    raw = row.get(key)
    return Decimal(raw) if raw else default


def bars_from_csv(path: Path) -> list[Bar]:
    """Load bars from a CSV with a required ``close`` column (OHLCV optional)."""
    bars: list[Bar] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for i, row in enumerate(reader):
            close = Decimal(row["close"])
            bars.append(
                Bar(
                    ts=_BASE_TS + timedelta(days=i),
                    open=_cell(row, "open", close),
                    high=_cell(row, "high", close),
                    low=_cell(row, "low", close),
                    close=close,
                )
            )
    if not bars:
        raise ValueError(f"no rows with a 'close' column found in {path}")
    return bars


# --- qlib-backed real market data (optional `pyqlib` extra) ----------------

_QLIB_INITIALIZED: set[str] = set()
_QLIB_FIELDS = ["$open", "$high", "$low", "$close", "$volume"]


def _import_qlib() -> tuple[Any, Any]:
    """Lazy-import qlib so the core package never depends on the heavy `pyqlib`.

    Raises a clear, actionable error (not a bare ImportError) when the optional
    extra isn't installed — mirroring the optional-broker pattern.
    """
    try:
        import qlib
        from qlib.data import D
    except ImportError as exc:  # pragma: no cover - exercised in CI (qlib absent)
        raise RuntimeError(
            "bars_from_qlib requires the optional 'pyqlib' dependency, which is not "
            "installed. Install it with `uv pip install pyqlib` (or `pip install "
            "tradingview-bridge[qlib]`) and prepare a qlib data directory "
            "(e.g. `python scripts/get_data.py qlib_data --region cn`)."
        ) from exc
    return qlib, D


def default_qlib_provider_uri() -> str:
    """The standard local qlib data directory (CN sample data lives here)."""
    return str(Path.home() / ".qlib" / "qlib_data" / "cn_data")


def bars_from_qlib(
    instrument: str,
    *,
    start: str,
    end: str,
    provider_uri: str | None = None,
    freq: str = "day",
) -> list[Bar]:
    """Load real OHLCV bars for one ``instrument`` from a local qlib data provider.

    The data-layer graft: reads ``$open/$high/$low/$close/$volume`` via qlib's
    point-in-time data layer and converts to our ``Bar`` list, so the existing
    walk-forward / score / optimize / roster pipeline runs on real market data.

    Args:
        instrument: a qlib instrument id, e.g. ``"SH600000"`` (csi300 sample data).
        start / end: ISO dates (``"YYYY-MM-DD"``).
        provider_uri: qlib data dir (default ``~/.qlib/qlib_data/cn_data``).
        freq: bar frequency (``"day"``).

    Raises RuntimeError if ``pyqlib`` isn't installed; ValueError if the query
    returns no usable bars (bad instrument / empty range).
    """
    qlib, d_api = _import_qlib()
    provider = provider_uri or default_qlib_provider_uri()
    if provider not in _QLIB_INITIALIZED:
        qlib.init(provider_uri=provider, region="cn")
        _QLIB_INITIALIZED.add(provider)

    frame = d_api.features([instrument], _QLIB_FIELDS, start_time=start, end_time=end, freq=freq)
    bars: list[Bar] = []
    for index, row in frame.iterrows():
        # MultiIndex (instrument, datetime); we only need the timestamp.
        ts = index[-1] if isinstance(index, tuple) else index
        close = row["$close"]
        if close is None or close != close:  # skip suspended / NaN days (NaN != NaN)
            continue
        when = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
        bars.append(
            Bar(
                ts=when,
                open=_qlib_dec(row["$open"], close),
                high=_qlib_dec(row["$high"], close),
                low=_qlib_dec(row["$low"], close),
                close=Decimal(str(close)),
                volume=_qlib_dec(row.get("$volume") if hasattr(row, "get") else row["$volume"], 0),
            )
        )
    if not bars:
        raise ValueError(
            f"qlib returned no usable bars for {instrument!r} in [{start}, {end}] "
            f"(provider={provider}). Check the instrument id and that the date range "
            f"is covered by the prepared data."
        )
    bars.sort(key=lambda b: b.ts)
    return bars


def _qlib_dec(value: Any, default: Any) -> Decimal:
    """qlib float (or NaN) → Decimal, falling back to ``default`` on NaN/None."""
    if value is None or value != value:  # NaN != NaN
        return Decimal(str(default))
    return Decimal(str(value))


# --- shared resolver: the source precedence the CLIs use -------------------


def resolve_bars(
    *,
    qlib: str | None = None,
    qlib_start: str = "2010-01-01",
    qlib_end: str = "2020-09-25",
    bars_csv: str | None = None,
    synthetic_n: int = 200,
) -> list[Bar]:
    """Pick a bar source by precedence: qlib instrument > CSV file > synthetic.

    Shared by the `research` and `optimize` CLIs so the --qlib / --bars-csv /
    synthetic fallback behaves identically everywhere.
    """
    if qlib:
        return bars_from_qlib(qlib, start=qlib_start, end=qlib_end)
    if bars_csv:
        return bars_from_csv(Path(bars_csv).expanduser())
    return synthetic_bars(synthetic_n)
