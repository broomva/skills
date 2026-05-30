"""OperatorLoop — the multi-rate tick loop with the dogfood-as-precondition interlock.

Each tick:
  1. fast   (every tick) — run the self-dogfood canary. If it fails, fold the
     failure into state (soft -> hard halt) and STOP. This is the interlock:
     no position management on a pipeline we cannot confirm works.
  2. medium (every `medium_every` ticks) — read positions; enforce the
     position-count cap (warn/flag; never silently exceed).
  3. slow   (every `slow_every` ticks) — compute drift vs target; report.

State is loaded at the start of each tick and saved at the end, so the loop is
restart-safe (P12): a cron firing `operate tick`, a `/loop`, or a `persist
iterate` all resume from the same on-disk state.

`run_once()` is cron/loop-friendly (one tick, return). `run_forever(interval)`
is the daemon form.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import structlog

from .canary import CanaryProbe
from .positions import Drift, PositionManager
from .report import report_tick
from .state import CanarySnapshot, OperatorState

log = structlog.get_logger("tradingview_bridge.operator.loop")


class OperatorLoop:
    """Owns the tick cadence + the interlock. Constructed once per process."""

    def __init__(
        self,
        *,
        canary: CanaryProbe,
        positions: PositionManager,
        state_path: Path,
        medium_every: int = 5,
        slow_every: int = 1440,
        max_open_positions: int = 20,
        halt_after_failures: int = 3,
    ) -> None:
        if medium_every < 1 or slow_every < 1:
            raise ValueError("medium_every and slow_every must be >= 1")
        if max_open_positions < 1:
            raise ValueError("max_open_positions must be >= 1")
        if halt_after_failures < 1:
            raise ValueError("halt_after_failures must be >= 1")
        self._canary = canary
        self._positions = positions
        self._state_path = state_path
        self._medium_every = medium_every
        self._slow_every = slow_every
        self._max_open_positions = max_open_positions
        self._halt_after_failures = halt_after_failures

    async def tick(self) -> OperatorState:
        """Run a single tick. Returns the resulting (and persisted) state."""
        state = OperatorState.load(self._state_path)
        state.tick_count += 1
        state.last_tick_ts = datetime.now(tz=UTC).isoformat()
        if state.started_at is None:
            state.started_at = state.last_tick_ts

        # --- fast: self-dogfood canary (the interlock) ---
        canary = await self._canary.run(state.tick_count)
        state.record_canary(
            CanarySnapshot(passed=canary.passed, detail=canary.detail, checks=canary.checks),
            halt_after_failures=self._halt_after_failures,
        )

        if not state.position_management_allowed:
            # INTERLOCK TRIPPED — do not touch positions this tick.
            log.warning(
                "operator_interlock_tripped",
                tick=state.tick_count,
                hard_halted=state.hard_halted,
                reason=state.halt_reason,
            )
            report_tick(state)
            state.save(self._state_path)
            return state

        # --- medium: position reconciliation + cap enforcement ---
        positions: dict[str, Decimal] = {}
        drifts: list[Drift] = []
        if state.tick_count % self._medium_every == 0:
            positions = await self._positions.net_positions()
            if len(positions) > self._max_open_positions:
                # Never silently exceed a cap (P11 no-silent-caps): flag it.
                log.warning(
                    "operator_position_cap_exceeded",
                    tick=state.tick_count,
                    open_positions=len(positions),
                    cap=self._max_open_positions,
                )
            # Reconcile the ledger (what we placed) against the real broker book.
            recon = await self._positions.reconcile()
            if recon is not None:
                log.info(
                    "operator_reconcile",
                    tick=state.tick_count,
                    matched=recon.matched,
                    ledger_only=recon.ledger_only,
                    broker_only=recon.broker_only,
                    has_drift=recon.has_drift,
                )
                if recon.has_drift:
                    # Drift is not silent — a position we did not place, or one we
                    # believe open that the broker no longer shows.
                    log.warning(
                        "operator_position_drift",
                        tick=state.tick_count,
                        ledger_only=recon.ledger_only,
                        broker_only=recon.broker_only,
                    )

        # --- slow: drift report ---
        if state.tick_count % self._slow_every == 0:
            drifts = await self._positions.drift()

        report_tick(
            state,
            positions=positions or None,
            drifts=drifts or None,
        )
        state.save(self._state_path)
        return state

    async def run_once(self) -> OperatorState:
        """Alias for one tick — the cron/loop entry."""
        return await self.tick()

    async def run_forever(self, interval_s: float) -> None:
        """Daemon form: tick, sleep, repeat. Ctrl-C / cancellation exits cleanly."""
        log.info("operator_loop_started", interval_s=interval_s, state_path=str(self._state_path))
        try:
            while True:
                await self.tick()
                await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            log.info("operator_loop_cancelled")
            raise
        finally:
            log.info("operator_loop_stopped")
