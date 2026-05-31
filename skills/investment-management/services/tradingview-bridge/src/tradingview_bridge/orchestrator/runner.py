"""runner — the orchestrator's stateful tick: evaluate, record, rank, recommend.

``AutoResearch.run`` is one tick of the agent's slow loop. It composes the pure
core (research.py) with the PerformanceLedger:

  1. evaluate every strategy (walk-forward + score)
  2. record each evaluation to the ledger, so trends accrue across ticks
  3. rank → recommend (the pure decision)
  4. *reality check*: for a ``promote_candidate``, consult the ledger's
     sim-vs-live gap. If the strategy looked great in simulation but has actually
     decayed in live-paper beyond tolerance, demote it to ``paper_forward``.

Step 4 is what closes the loop: measurements feed decisions, and decisions are
tempered by what live-paper actually did. The reality check can only ever
*weaken* a recommendation — it never promotes past the human gate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import structlog

from ..evaluation.ledger import EvaluationRecord, PerformanceLedger
from ..schemas import AssetClass
from ..strategy.base import Strategy
from ..strategy.types import Bar
from .research import DEFAULT_TRUST_THRESHOLD, evaluate_all, rank, recommend
from .types import AllocationRecommendation, Leaderboard, StrategyEvaluation

log = structlog.get_logger("tradingview_bridge.orchestrator.runner")

# How far live-paper return may fall below sim before a candidate is demoted.
# A return gap (live - sim) more negative than -tolerance means the backtest
# edge did not survive contact with reality.
DEFAULT_LIVE_DECAY_TOLERANCE_PCT = Decimal("10")


@dataclass(frozen=True)
class ResearchReport:
    """The full output of one orchestrator tick."""

    symbol: str
    leaderboard: Leaderboard
    recommendation: AllocationRecommendation
    n_recorded: int


def _to_record(evaluation: StrategyEvaluation, symbol: str) -> EvaluationRecord:
    """Project a walk-forward evaluation into a ledger row (kind=walk_forward)."""
    wf = evaluation.walk_forward
    return EvaluationRecord(
        strategy=evaluation.strategy,
        symbol=symbol,
        kind="walk_forward",
        n_trades=wf.full.n_trades,
        return_pct=wf.mean_return_pct,
        sharpe=wf.mean_sharpe,
        max_drawdown_pct=wf.worst_window_drawdown_pct,
        win_rate_pct=wf.full.win_rate_pct,
        consistency_pct=wf.consistency_pct,
    )


class AutoResearch:
    """The agent's slow loop, made concrete and persistent."""

    def __init__(self, ledger: PerformanceLedger | None = None) -> None:
        self._ledger = ledger or PerformanceLedger()

    @property
    def ledger(self) -> PerformanceLedger:
        return self._ledger

    async def run(
        self,
        strategies: Sequence[Strategy],
        bars: list[Bar],
        *,
        symbol: str,
        asset_class: AssetClass,
        n_windows: int = 5,
        periods_per_year: int = 252,
        trust_threshold: float = DEFAULT_TRUST_THRESHOLD,
        record: bool = True,
        live_decay_tolerance_pct: Decimal = DEFAULT_LIVE_DECAY_TOLERANCE_PCT,
    ) -> ResearchReport:
        """Run one orchestration tick → a ResearchReport."""
        evaluations = evaluate_all(
            strategies,
            bars,
            symbol=symbol,
            asset_class=asset_class,
            n_windows=n_windows,
            periods_per_year=periods_per_year,
        )
        n_recorded = 0
        if record:
            for evaluation in evaluations:
                await self._ledger.record(_to_record(evaluation, symbol))
                n_recorded += 1

        board = rank(evaluations, symbol=symbol)
        rec = recommend(board, trust_threshold=trust_threshold)
        rec = await self._apply_live_reality(rec, symbol, live_decay_tolerance_pct)

        log.info(
            "research_tick",
            symbol=symbol,
            n_strategies=len(evaluations),
            n_recorded=n_recorded,
            action=rec.action,
            strategy=rec.strategy,
            confidence=round(rec.confidence, 3),
        )
        return ResearchReport(
            symbol=symbol, leaderboard=board, recommendation=rec, n_recorded=n_recorded
        )

    async def _apply_live_reality(
        self,
        rec: AllocationRecommendation,
        symbol: str,
        tolerance: Decimal,
    ) -> AllocationRecommendation:
        """Temper a candidate against live-paper history. Can only weaken, never strengthen."""
        if rec.action != "promote_candidate" or rec.strategy is None:
            return rec
        gap = await self._ledger.compare_sim_vs_live(rec.strategy, symbol=symbol)
        if gap is None:
            return rec  # no live-paper measurement yet — nothing to temper with

        if gap.return_gap_pct < -tolerance:
            return AllocationRecommendation(
                symbol=rec.symbol,
                action="paper_forward",
                strategy=rec.strategy,
                confidence=rec.confidence,
                trust_threshold=rec.trust_threshold,
                rationale=(
                    f"{rec.strategy} cleared the sim trust gate but live-paper underperformed "
                    f"by {gap.return_gap_pct:.2f}% (beyond the {tolerance}% tolerance) — demoted "
                    f"to paper_forward until the sim-vs-live gap closes"
                ),
                live_reality=gap,
            )
        return AllocationRecommendation(
            symbol=rec.symbol,
            action=rec.action,
            strategy=rec.strategy,
            confidence=rec.confidence,
            trust_threshold=rec.trust_threshold,
            rationale=f"{rec.rationale} (live gap {gap.return_gap_pct:.2f}% within tolerance)",
            live_reality=gap,
        )
