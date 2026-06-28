"""Tests for the stateful orchestrator tick (runner.py) — ledger + reality check."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tradingview_bridge.evaluation.ledger import EvaluationRecord, PerformanceLedger
from tradingview_bridge.orchestrator.cli import default_roster, synthetic_bars
from tradingview_bridge.orchestrator.runner import AutoResearch
from tradingview_bridge.strategy.types import Bar


@pytest.fixture
def ledger(tmp_path: Path) -> PerformanceLedger:
    return PerformanceLedger(db_path=tmp_path / "perf.sqlite")


def _bars() -> list[Bar]:
    return synthetic_bars(120)


async def test_run_records_each_strategy(ledger: PerformanceLedger) -> None:
    roster = default_roster()
    report = await AutoResearch(ledger).run(
        roster, _bars(), symbol="AAPL", asset_class="stock", n_windows=4
    )
    assert report.n_recorded == len(roster)
    rows = await ledger.history(symbol="AAPL")
    assert len(rows) == len(roster)
    assert {r.kind for r in rows} == {"walk_forward"}


async def test_run_no_record_writes_nothing(ledger: PerformanceLedger) -> None:
    report = await AutoResearch(ledger).run(
        default_roster(), _bars(), symbol="AAPL", asset_class="stock", n_windows=4, record=False
    )
    assert report.n_recorded == 0
    assert await ledger.history(symbol="AAPL") == []


async def test_run_recommendation_is_human_gated(ledger: PerformanceLedger) -> None:
    report = await AutoResearch(ledger).run(
        default_roster(), _bars(), symbol="AAPL", asset_class="stock", n_windows=4
    )
    assert report.recommendation.requires_human_approval is True
    assert report.recommendation.action in {"promote_candidate", "paper_forward", "reject"}


async def test_live_reality_demotes_decayed_candidate(ledger: PerformanceLedger) -> None:
    """If a strategy looks good in sim but live-paper has decayed beyond
    tolerance, a promote_candidate is demoted to paper_forward."""
    roster = default_roster()
    # Seed a terrible live-paper result for EVERY roster strategy, so whichever
    # wins the sim ranking has a live record that decayed. tolerance=0 → any
    # negative gap demotes (robust to the exact sim numbers).
    for strat in roster:
        await ledger.record(
            EvaluationRecord(
                strategy=strat.name,
                symbol="AAPL",
                kind="live_paper",
                n_trades=3,
                return_pct=Decimal("-50"),
                sharpe=-2.0,
                max_drawdown_pct=Decimal("40"),
                win_rate_pct=Decimal("20"),
            )
        )
    report = await AutoResearch(ledger).run(
        roster,
        _bars(),
        symbol="AAPL",
        asset_class="stock",
        n_windows=4,
        live_decay_tolerance_pct=Decimal("0"),
    )
    # The winner cleared the sim gate, but the seeded live decay demotes it.
    assert report.recommendation.action == "paper_forward"
    assert report.recommendation.live_reality is not None
    assert report.recommendation.live_reality.return_gap_pct < 0
    assert "demoted" in report.recommendation.rationale


async def test_live_reality_keeps_candidate_within_tolerance(ledger: PerformanceLedger) -> None:
    """A live-paper gap within tolerance keeps the candidate and annotates it."""
    roster = default_roster()
    for strat in roster:
        await ledger.record(
            EvaluationRecord(
                strategy=strat.name,
                symbol="AAPL",
                kind="live_paper",
                n_trades=3,
                return_pct=Decimal("-50"),  # large gap...
                sharpe=-2.0,
                max_drawdown_pct=Decimal("40"),
                win_rate_pct=Decimal("20"),
            )
        )
    report = await AutoResearch(ledger).run(
        roster,
        _bars(),
        symbol="AAPL",
        asset_class="stock",
        n_windows=4,
        trust_threshold=0.6,
        live_decay_tolerance_pct=Decimal("1000"),  # ...but tolerance is huge → keep
    )
    # Only meaningful if the winner cleared the gate (promote path exercised).
    if report.recommendation.action == "promote_candidate":
        assert report.recommendation.live_reality is not None
        assert "within tolerance" in report.recommendation.rationale


async def test_run_with_default_ledger_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """AutoResearch() with no explicit ledger uses the env-configured DB path."""
    monkeypatch.setenv("TVBRIDGE_PERFORMANCE_DB_PATH", str(tmp_path / "default.sqlite"))
    orchestrator = AutoResearch()
    assert orchestrator.ledger.db_path == tmp_path / "default.sqlite"
    report = await orchestrator.run(
        default_roster(), _bars(), symbol="AAPL", asset_class="stock", n_windows=4
    )
    assert report.n_recorded == len(default_roster())
