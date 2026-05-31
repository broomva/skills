"""Bar sources — synthetic + CSV bars, shared across the decision-plane CLIs.

Extracted from orchestrator/cli so the orchestrator, optimizer, and roster CLIs
can all build bars from one place without importing each other (which would risk a
dependency cycle now that the orchestrator reads the roster). Live market-data
integration (`market_data.py`) stays deferred — this module is deterministic
synthetic + flat-file CSV only.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

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
