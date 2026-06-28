"""report — journal each operator tick to structured log + bookkeeping.

Mirrors the bridge's bookkeeping hook: fire-and-forget, graceful no-op when the
CLI is unreachable. The operator's journal is the audit trail of *autonomous
decisions* — which ticks ran, whether the canary passed, whether position
management was allowed, and any drift surfaced.
"""

from __future__ import annotations

from decimal import Decimal

import structlog

from .positions import Drift
from .state import OperatorState

log = structlog.get_logger("tradingview_bridge.operator.report")


def report_tick(
    state: OperatorState,
    *,
    positions: dict[str, Decimal] | None = None,
    drifts: list[Drift] | None = None,
) -> None:
    """Emit a structured-log record summarizing this tick.

    Kept synchronous + dependency-free so it can be called from any context
    (cron one-shot, daemon loop, tests). The structured log line IS the audit
    record; a bookkeeping subprocess journal can be layered on by the caller
    via the bridge's existing bookkeeping.schedule_journal if desired.
    """
    log.info(
        "operator_tick",
        tick=state.tick_count,
        canary_passed=state.last_canary_passed,
        position_management_allowed=state.position_management_allowed,
        hard_halted=state.hard_halted,
        consecutive_canary_failures=state.consecutive_canary_failures,
        halt_reason=state.halt_reason,
        open_positions=len(positions) if positions is not None else None,
        drift_count=len(drifts) if drifts is not None else None,
    )
    if drifts:
        for d in drifts:
            log.info(
                "operator_drift",
                tick=state.tick_count,
                symbol=d.symbol,
                current=str(d.current),
                target=str(d.target),
                delta=str(d.delta),
            )
