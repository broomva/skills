"""PerformanceLedger tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tradingview_bridge.evaluation.ledger import EvaluationRecord, PerformanceLedger


def _rec(
    strategy: str = "sma",
    kind: str = "backtest",
    ret: str = "10",
    sharpe: float = 1.5,
    consistency: str | None = None,
) -> EvaluationRecord:
    return EvaluationRecord(
        strategy=strategy,
        symbol="AAPL",
        kind=kind,  # type: ignore[arg-type]
        n_trades=4,
        return_pct=Decimal(ret),
        sharpe=sharpe,
        max_drawdown_pct=Decimal("5"),
        win_rate_pct=Decimal("60"),
        consistency_pct=None if consistency is None else Decimal(consistency),
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
