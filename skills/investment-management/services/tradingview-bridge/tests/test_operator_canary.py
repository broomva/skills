"""CanaryProbe tests — the self-dogfood roundtrip check."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from tradingview_bridge.operator.canary import CANARY_SYMBOL, CanaryProbe, build_canary_alert
from tradingview_bridge.orders import CANARY_PREFIX


@dataclass
class _FakeResult:
    status: str


class _FakeDispatcher:
    """Records the alert it received and returns a configurable status."""

    def __init__(self, status: str = "accepted", raises: bool = False) -> None:
        self._status = status
        self._raises = raises
        self.received: object = None

    async def dispatch(self, alert: object) -> _FakeResult:
        self.received = alert
        if self._raises:
            raise RuntimeError("dispatch exploded")
        return _FakeResult(status=self._status)


def test_build_canary_alert_shape() -> None:
    alert = build_canary_alert(tick=42)
    assert alert.alert_id == f"{CANARY_PREFIX}-42"
    assert alert.strategy_name.startswith(CANARY_PREFIX)
    assert alert.symbol == CANARY_SYMBOL
    assert alert.action == "buy"


@pytest.mark.asyncio
async def test_canary_passes_on_accepted() -> None:
    probe = CanaryProbe(_FakeDispatcher(status="accepted"))
    result = await probe.run(tick=1)
    assert result.passed is True
    assert result.checks["dispatch"] is True


@pytest.mark.asyncio
async def test_canary_passes_on_duplicate() -> None:
    probe = CanaryProbe(_FakeDispatcher(status="duplicate"))
    result = await probe.run(tick=1)
    assert result.passed is True


@pytest.mark.asyncio
async def test_canary_fails_on_rejected() -> None:
    probe = CanaryProbe(_FakeDispatcher(status="rejected"))
    result = await probe.run(tick=1)
    assert result.passed is False
    assert result.checks["dispatch"] is False
    assert "rejected" in result.detail


@pytest.mark.asyncio
async def test_canary_never_crashes_on_dispatch_exception() -> None:
    """A canary must absorb dispatch errors and report a failure, not raise."""
    probe = CanaryProbe(_FakeDispatcher(raises=True))
    result = await probe.run(tick=1)
    assert result.passed is False
    assert "RuntimeError" in result.detail


@pytest.mark.asyncio
async def test_canary_fires_unique_alert_per_tick() -> None:
    disp = _FakeDispatcher(status="accepted")
    probe = CanaryProbe(disp)
    await probe.run(tick=1)
    first = disp.received
    await probe.run(tick=2)
    second = disp.received
    assert first is not None
    assert second is not None
    assert first.alert_id != second.alert_id  # type: ignore[attr-defined]
