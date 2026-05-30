"""Signal → TVAlert adapter tests (the live path)."""

from __future__ import annotations

from decimal import Decimal

from tradingview_bridge.strategy.tvalert import signal_to_tvalert
from tradingview_bridge.strategy.types import Signal


def _convert(action: str, **kw: object):  # type: ignore[no-untyped-def]
    sig = Signal(action=action, size=Decimal("3"))  # type: ignore[arg-type]
    return signal_to_tvalert(
        sig,
        symbol="AAPL",
        asset_class="stock",
        strategy_name="s",
        secret="x",
        alert_id="a1",
        **kw,  # type: ignore[arg-type]
    )


def test_enter_long_maps_to_buy() -> None:
    alert = _convert("enter_long")
    assert alert is not None
    assert alert.action == "buy"
    assert alert.symbol == "AAPL"
    assert alert.size == Decimal("3")


def test_enter_short_maps_to_sell() -> None:
    alert = _convert("enter_short")
    assert alert is not None
    assert alert.action == "sell"


def test_exit_maps_to_close() -> None:
    alert = _convert("exit")
    assert alert is not None
    assert alert.action == "close"


def test_hold_produces_no_alert() -> None:
    assert _convert("hold") is None


def test_asset_class_passes_through() -> None:
    sig = Signal(action="enter_long")
    alert = signal_to_tvalert(
        sig,
        symbol="BTC/USD",
        asset_class="crypto",
        strategy_name="s",
        secret="x",
        alert_id="a1",
    )
    assert alert is not None
    assert alert.asset_class == "crypto"
