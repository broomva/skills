"""PerformanceLedger tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from sqlite3 import IntegrityError

import pytest

from tradingview_bridge.evaluation.ledger import EvaluationRecord, PerformanceLedger


def _rec(
    strategy: str = "sma",
    kind: str = "backtest",
    ret: str = "10",
    sharpe: float = 1.5,
    consistency: str | None = None,
    symbol: str = "AAPL",
    created_at: datetime | None = None,
) -> EvaluationRecord:
    extra = {} if created_at is None else {"created_at": created_at}
    return EvaluationRecord(
        strategy=strategy,
        symbol=symbol,
        kind=kind,  # type: ignore[arg-type]
        n_trades=4,
        return_pct=Decimal(ret),
        sharpe=sharpe,
        max_drawdown_pct=Decimal("5"),
        win_rate_pct=Decimal("60"),
        consistency_pct=None if consistency is None else Decimal(consistency),
        **extra,  # type: ignore[arg-type]
    )


@pytest.fixture
def ledger(tmp_path: Path) -> PerformanceLedger:
    return PerformanceLedger(db_path=tmp_path / "perf.sqlite")


@pytest.mark.asyncio
async def test_record_and_history(ledger: PerformanceLedger) -> None:
    await ledger.record(_rec())
    await ledger.record(_rec(ret="12"))
    hist = await ledger.history(strategy="sma")
    assert len(hist) == 2
    assert hist[0].return_pct == Decimal("10")
    assert hist[1].return_pct == Decimal("12")


@pytest.mark.asyncio
async def test_history_filters_by_kind(ledger: PerformanceLedger) -> None:
    await ledger.record(_rec(kind="backtest"))
    await ledger.record(_rec(kind="walk_forward", consistency="80"))
    await ledger.record(_rec(kind="live_paper"))
    assert len(await ledger.history(kind="walk_forward")) == 1
    wf = (await ledger.history(kind="walk_forward"))[0]
    assert wf.consistency_pct == Decimal("80")


@pytest.mark.asyncio
async def test_latest(ledger: PerformanceLedger) -> None:
    await ledger.record(_rec(ret="10"))
    await ledger.record(_rec(ret="20"))
    latest = await ledger.latest("sma", "backtest")
    assert latest is not None
    assert latest.return_pct == Decimal("20")


@pytest.mark.asyncio
async def test_compare_sim_vs_live(ledger: PerformanceLedger) -> None:
    await ledger.record(_rec(kind="walk_forward", ret="30", sharpe=3.0, consistency="80"))
    await ledger.record(_rec(kind="live_paper", ret="8", sharpe=0.9))
    gap = await ledger.compare_sim_vs_live("sma")
    assert gap is not None
    assert gap.sim_kind == "walk_forward"
    assert gap.sim_return_pct == Decimal("30")
    assert gap.live_return_pct == Decimal("8")
    assert gap.return_gap_pct == Decimal("-22")  # live underperformed backtest


@pytest.mark.asyncio
async def test_compare_returns_none_without_live(ledger: PerformanceLedger) -> None:
    await ledger.record(_rec(kind="backtest"))
    assert await ledger.compare_sim_vs_live("sma") is None


@pytest.mark.asyncio
async def test_compare_falls_back_to_backtest(ledger: PerformanceLedger) -> None:
    await ledger.record(_rec(kind="backtest", ret="15"))
    await ledger.record(_rec(kind="live_paper", ret="11"))
    gap = await ledger.compare_sim_vs_live("sma")
    assert gap is not None
    assert gap.sim_kind == "backtest"


@pytest.mark.asyncio
async def test_clear(ledger: PerformanceLedger) -> None:
    await ledger.record(_rec())
    await ledger.clear()
    assert await ledger.history() == []


@pytest.mark.asyncio
async def test_invalid_kind_rejected_by_db(ledger: PerformanceLedger) -> None:
    """The DB CHECK constraint refuses an out-of-vocabulary kind, so a typo
    cannot persist silently and then vanish from latest()/compare lookups."""
    with pytest.raises(IntegrityError):
        await ledger.record(_rec(kind="walkforward"))  # typo: missing underscore


@pytest.mark.asyncio
async def test_latest_is_time_ordered_not_insertion_ordered(ledger: PerformanceLedger) -> None:
    """A backfilled OLDER evaluation inserted AFTER a newer one must not be
    treated as latest — ordering is by created_at, not insertion id."""
    newer = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
    older = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    await ledger.record(_rec(ret="99", created_at=newer))  # inserted first, but newer
    await ledger.record(_rec(ret="11", created_at=older))  # inserted later, but older
    latest = await ledger.latest("sma", "backtest")
    assert latest is not None
    assert latest.return_pct == Decimal("99")  # the chronologically-latest, not last-inserted


@pytest.mark.asyncio
async def test_compare_scopes_by_symbol(ledger: PerformanceLedger) -> None:
    """sim on AAPL + live on MSFT must NOT be compared when a symbol is given —
    that cross-instrument gap would be meaningless."""
    await ledger.record(_rec(kind="walk_forward", symbol="AAPL", ret="30", consistency="80"))
    await ledger.record(_rec(kind="live_paper", symbol="MSFT", ret="8"))
    # scoped to AAPL: there is no AAPL live_paper → no comparison
    assert await ledger.compare_sim_vs_live("sma", symbol="AAPL") is None
    # add an AAPL live_paper → now it compares, and only against AAPL rows
    await ledger.record(_rec(kind="live_paper", symbol="AAPL", ret="12"))
    gap = await ledger.compare_sim_vs_live("sma", symbol="AAPL")
    assert gap is not None
    assert gap.sim_return_pct == Decimal("30")
    assert gap.live_return_pct == Decimal("12")  # AAPL's live, not MSFT's
