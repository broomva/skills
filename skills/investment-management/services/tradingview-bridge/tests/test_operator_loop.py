"""OperatorLoop tests — the multi-rate tick + the dogfood-as-precondition interlock."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from tradingview_bridge.operator.canary import CanaryProbe
from tradingview_bridge.operator.loop import OperatorLoop
from tradingview_bridge.operator.positions import PositionManager
from tradingview_bridge.operator.state import OperatorState
from tradingview_bridge.orders import OrderLedger


@dataclass
class _FakeResult:
    status: str


class _ToggleDispatcher:
    """Dispatcher whose canary result is controlled by a mutable flag."""

    def __init__(self) -> None:
        self.ok = True

    async def dispatch(self, alert: object) -> _FakeResult:
        return _FakeResult(status="accepted" if self.ok else "rejected")


def _make_loop(
    dispatcher: _ToggleDispatcher,
    ledger: OrderLedger,
    state_path: Path,
    *,
    medium_every: int = 5,
    slow_every: int = 1440,
    max_open_positions: int = 20,
    halt_after_failures: int = 3,
) -> OperatorLoop:
    return OperatorLoop(
        canary=CanaryProbe(dispatcher),
        positions=PositionManager(ledger),
        state_path=state_path,
        medium_every=medium_every,
        slow_every=slow_every,
        max_open_positions=max_open_positions,
        halt_after_failures=halt_after_failures,
    )


@pytest.mark.asyncio
async def test_passing_tick_allows_management(
    tmp_orders_db_path: Path, tmp_state_path: Path
) -> None:
    disp = _ToggleDispatcher()
    loop = _make_loop(disp, OrderLedger(db_path=tmp_orders_db_path), tmp_state_path)
    state = await loop.tick()
    assert state.tick_count == 1
    assert state.last_canary_passed is True
    assert state.position_management_allowed is True


@pytest.mark.asyncio
async def test_failing_canary_trips_interlock(
    tmp_orders_db_path: Path, tmp_state_path: Path
) -> None:
    disp = _ToggleDispatcher()
    disp.ok = False
    loop = _make_loop(disp, OrderLedger(db_path=tmp_orders_db_path), tmp_state_path)
    state = await loop.tick()
    assert state.last_canary_passed is False
    assert state.position_management_allowed is False


@pytest.mark.asyncio
async def test_consecutive_failures_hard_halt(
    tmp_orders_db_path: Path, tmp_state_path: Path
) -> None:
    disp = _ToggleDispatcher()
    disp.ok = False
    loop = _make_loop(
        disp, OrderLedger(db_path=tmp_orders_db_path), tmp_state_path, halt_after_failures=2
    )
    await loop.tick()
    state = await loop.tick()
    assert state.hard_halted is True


@pytest.mark.asyncio
async def test_state_persists_across_ticks(tmp_orders_db_path: Path, tmp_state_path: Path) -> None:
    """Each tick loads + saves state — restart-safe (P12)."""
    disp = _ToggleDispatcher()
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    loop = _make_loop(disp, ledger, tmp_state_path)
    await loop.tick()
    await loop.tick()
    # A fresh loop instance (simulating a process restart) sees tick_count=2.
    loop2 = _make_loop(disp, ledger, tmp_state_path)
    state = await loop2.tick()
    assert state.tick_count == 3


@pytest.mark.asyncio
async def test_recovery_after_transient_failure(
    tmp_orders_db_path: Path, tmp_state_path: Path
) -> None:
    disp = _ToggleDispatcher()
    loop = _make_loop(
        disp, OrderLedger(db_path=tmp_orders_db_path), tmp_state_path, halt_after_failures=3
    )
    disp.ok = False
    await loop.tick()  # 1 failure, soft halt
    disp.ok = True
    state = await loop.tick()  # recovers
    assert state.position_management_allowed is True
    assert state.consecutive_canary_failures == 0


@pytest.mark.asyncio
async def test_hard_halt_blocks_until_reset(tmp_orders_db_path: Path, tmp_state_path: Path) -> None:
    disp = _ToggleDispatcher()
    loop = _make_loop(
        disp, OrderLedger(db_path=tmp_orders_db_path), tmp_state_path, halt_after_failures=2
    )
    disp.ok = False
    await loop.tick()
    await loop.tick()  # hard halt now
    disp.ok = True
    state = await loop.tick()  # canary passes but hard halt sticks
    assert state.last_canary_passed is True
    assert state.position_management_allowed is False
    # operator-acknowledged recovery
    state.reset()
    state.save(tmp_state_path)
    state2 = await loop.tick()
    assert state2.position_management_allowed is True


@pytest.mark.asyncio
async def test_position_cap_does_not_crash(tmp_orders_db_path: Path, tmp_state_path: Path) -> None:
    """Exceeding the position cap flags a warning but never raises."""
    disp = _ToggleDispatcher()
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    for i in range(3):
        await ledger.append(
            order_id=f"o{i}",
            alert_id=f"a{i}",
            strategy_name="s",
            broker="ibkr",
            asset_class="stock",
            symbol=f"SYM{i}",
            action="buy",
            size=Decimal("1"),
            paper=True,
        )
    loop = _make_loop(disp, ledger, tmp_state_path, medium_every=1, max_open_positions=2)
    state = await loop.tick()  # 3 positions > cap of 2 → warn, no crash
    assert state.position_management_allowed is True


def test_loop_rejects_bad_args(tmp_orders_db_path: Path, tmp_state_path: Path) -> None:
    disp = _ToggleDispatcher()
    ledger = OrderLedger(db_path=tmp_orders_db_path)
    with pytest.raises(ValueError, match="medium_every"):
        _make_loop(disp, ledger, tmp_state_path, medium_every=0)
    with pytest.raises(ValueError, match="max_open_positions"):
        _make_loop(disp, ledger, tmp_state_path, max_open_positions=0)


def test_state_path_is_loadable_after_tick(tmp_state_path: Path) -> None:
    """Smoke: the persisted file is valid JSON loadable into OperatorState."""
    state = OperatorState(tick_count=3)
    state.save(tmp_state_path)
    assert OperatorState.load(tmp_state_path).tick_count == 3
