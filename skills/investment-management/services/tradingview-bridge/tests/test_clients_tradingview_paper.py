"""TradingViewPaperClient tests — driven by a scripted fake Interceptor driver.

CI has no browser, so these tests inject a FakeDriver whose `find` returns are
scripted per call. They assert the *sequence* of UI actions the client issues
(navigate → connect → side → qty → confirm). The real DOM interaction is pinned
by the live Interceptor dogfood.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradingview_bridge.clients.base import NotConfiguredError
from tradingview_bridge.clients.tradingview_paper import TradingViewPaperClient
from tradingview_bridge.interceptor_driver import InterceptorError
from tradingview_bridge.schemas import TVAlert


class FakeDriver:
    """Records calls; `find` pops scripted return values in order."""

    def __init__(self, find_returns: list[str | None] | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._find_returns = list(find_returns or [])
        self.raise_on_open = False

    async def open(self, url: str, *, reuse: bool = True) -> str:
        self.calls.append(("open", url))
        if self.raise_on_open:
            raise InterceptorError("browser unreachable")
        return ""

    async def read_tree(self) -> str:
        self.calls.append(("read_tree",))
        return ""

    async def read_text(self) -> str:
        self.calls.append(("read_text",))
        return ""

    async def find(self, role: str, name: str, *, exact: bool = False) -> str | None:
        self.calls.append(("find", role, name))
        return self._find_returns.pop(0) if self._find_returns else None

    async def act(self, ref: str) -> None:
        self.calls.append(("act", ref))

    async def type(self, ref: str, value: str) -> None:
        self.calls.append(("type", ref, value))

    async def screenshot(self, path: str) -> None:
        self.calls.append(("screenshot", path))

    def acted(self) -> list[str]:
        return [c[1] for c in self.calls if c[0] == "act"]


def _alert(action: str = "buy", symbol: str = "AAPL", size: str = "10") -> TVAlert:
    return TVAlert(
        alert_id="tv-1",
        secret="x",
        strategy_name="s",
        asset_class="stock",
        symbol=symbol,
        action=action,  # type: ignore[arg-type]
        size=Decimal(size),
        time="2026-05-30T00:00:00Z",  # type: ignore[arg-type]
    )


def test_broker_name() -> None:
    assert TradingViewPaperClient(FakeDriver()).broker_name == "tradingview-paper"


@pytest.mark.asyncio
async def test_buy_already_connected_sequence() -> None:
    # find #1 ensure_paper "Buy" -> connected; #2 side "Buy"; #3 qty; #4 confirm
    driver = FakeDriver(find_returns=["e-buy", "e-buy", "e-qty", "e-confirm"])
    client = TradingViewPaperClient(driver)
    receipt = await client.place_order(_alert(action="buy", symbol="AAPL", size="10"))

    assert receipt.broker == "tradingview-paper"
    assert receipt.paper is True
    assert receipt.order_id.startswith("tvpaper-")
    assert receipt.symbol == "AAPL"
    # navigated to the symbol, set qty, confirmed
    assert ("open", "https://www.tradingview.com/chart/?symbol=AAPL") in driver.calls
    assert ("type", "e-qty", "10") in driver.calls
    assert "e-confirm" in driver.acted()


@pytest.mark.asyncio
async def test_sell_routes_to_sell_control() -> None:
    driver = FakeDriver(find_returns=["e-sell", "e-sell", "e-qty", "e-confirm"])
    client = TradingViewPaperClient(driver)
    await client.place_order(_alert(action="sell"))
    # the side lookup asked for the Sell control
    assert ("find", "button", "Sell") in driver.calls


@pytest.mark.asyncio
async def test_connect_flow_when_not_connected() -> None:
    # #1 "Buy" -> None (not connected); #2 "Trade" -> e-trade; #3 "Paper Trading"
    # -> e-paper; #4 side "Buy" -> e-buy; #5 qty; #6 confirm
    driver = FakeDriver(find_returns=[None, "e-trade", "e-paper", "e-buy", "e-qty", "e-confirm"])
    client = TradingViewPaperClient(driver)
    await client.place_order(_alert(action="buy"))
    acted = driver.acted()
    assert "e-trade" in acted  # opened the Trade panel
    assert "e-paper" in acted  # connected Paper Trading
    assert "e-confirm" in acted


@pytest.mark.asyncio
async def test_close_action_deferred() -> None:
    client = TradingViewPaperClient(FakeDriver())
    with pytest.raises(NotImplementedError, match="deferred"):
        await client.place_order(_alert(action="close"))


@pytest.mark.asyncio
async def test_flatten_action_deferred() -> None:
    client = TradingViewPaperClient(FakeDriver())
    with pytest.raises(NotImplementedError):
        await client.place_order(_alert(action="flatten"))


@pytest.mark.asyncio
async def test_browser_error_becomes_not_configured() -> None:
    driver = FakeDriver()
    driver.raise_on_open = True
    client = TradingViewPaperClient(driver)
    with pytest.raises(NotConfiguredError, match="Interceptor"):
        await client.place_order(_alert(action="buy"))


@pytest.mark.asyncio
async def test_missing_side_control_raises_not_configured() -> None:
    # connected fast-path passes (Buy present for ensure), but the side lookup
    # in _submit returns None -> InterceptorError -> NotConfiguredError
    driver = FakeDriver(find_returns=["e-buy", None])
    client = TradingViewPaperClient(driver)
    with pytest.raises(NotConfiguredError):
        await client.place_order(_alert(action="buy"))


@pytest.mark.asyncio
async def test_health_check_true_when_trade_present() -> None:
    driver = FakeDriver(find_returns=["e-trade"])
    assert await TradingViewPaperClient(driver).health_check() is True


@pytest.mark.asyncio
async def test_health_check_false_when_trade_absent() -> None:
    driver = FakeDriver(find_returns=[None])
    assert await TradingViewPaperClient(driver).health_check() is False


@pytest.mark.asyncio
async def test_health_check_false_on_browser_error() -> None:
    driver = FakeDriver()
    driver.raise_on_open = True
    assert await TradingViewPaperClient(driver).health_check() is False


@pytest.mark.asyncio
async def test_symbol_navigation_appends_query() -> None:
    driver = FakeDriver(find_returns=["e-buy", "e-buy", "e-qty", "e-confirm"])
    client = TradingViewPaperClient(driver)
    await client.place_order(_alert(symbol="BTCUSD"))
    assert ("open", "https://www.tradingview.com/chart/?symbol=BTCUSD") in driver.calls


# ---- dispatcher routing: tradingview-paper mode bypasses asset routing ----


class _StubTVClient:
    """Minimal BrokerClient stand-in that records what it was asked to place."""

    def __init__(self) -> None:
        self.placed: list[str] = []

    @property
    def broker_name(self) -> str:
        return "tradingview-paper"

    async def place_order(self, alert: TVAlert):  # type: ignore[no-untyped-def]
        from datetime import UTC, datetime

        from tradingview_bridge.clients.base import OrderReceipt

        self.placed.append(alert.symbol)
        return OrderReceipt(
            broker="tradingview-paper",
            order_id="tvpaper-stub",
            alert_id=alert.alert_id,
            symbol=alert.symbol,
            action=alert.action,
            size=alert.size,
            submitted_at=datetime.now(tz=UTC),
            paper=True,
        )

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_dispatcher_routes_all_asset_classes_to_tv_paper() -> None:
    from tradingview_bridge.dispatch import Dispatcher

    stub = _StubTVClient()
    disp = Dispatcher(
        broker_mode="tradingview-paper",
        clients_override={"tradingview-paper": stub},  # type: ignore[dict-item]
    )
    # A crypto alert would normally route to kraken — in tv-paper mode it must
    # go to the single TradingView Paper client instead.
    result = await disp.dispatch(_alert(action="buy", symbol="BTCUSD"))
    assert result.broker == "tradingview-paper"
    assert result.status == "accepted"
    assert stub.placed == ["BTCUSD"]
