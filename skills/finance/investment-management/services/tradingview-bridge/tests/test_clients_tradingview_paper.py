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
from tradingview_bridge.interceptor_driver import InterceptorError, find_ref
from tradingview_bridge.schemas import TVAlert


class FakeDriver:
    """Records calls. Dual-mode `find`:

    - if `find_returns` is non-empty, pop scripted values in order (precise
      control for the place/submit flows);
    - else resolve against `tree` via the real `find_ref` (realistic for the
      list/close/cancel flows that parse the tree).
    """

    def __init__(
        self,
        find_returns: list[str | None] | None = None,
        tree: str = "",
    ) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._find_returns = list(find_returns or [])
        self._tree = tree
        self.raise_on_open = False

    async def open(self, url: str, *, reuse: bool = True) -> str:
        self.calls.append(("open", url))
        if self.raise_on_open:
            raise InterceptorError("browser unreachable")
        return ""

    async def read_tree(self) -> str:
        self.calls.append(("read_tree",))
        return self._tree

    async def read_text(self) -> str:
        self.calls.append(("read_text",))
        return ""

    async def find(self, role: str, name: str, *, exact: bool = False) -> str | None:
        self.calls.append(("find", role, name))
        if self._find_returns:
            return self._find_returns.pop(0)
        return find_ref(self._tree, role, name, exact=exact)

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


# ---- double-submit guard ------------------------------------------------


@pytest.mark.asyncio
async def test_no_double_submit_when_quick_button_places_immediately() -> None:
    """If the quick Buy button places the order (no ticket opens), the client
    must NOT click a second time."""
    # _ensure Buy -> e-quick (connected); _require Buy -> e-quick; qty -> None;
    # submit "Buy " -> None (no ticket)
    driver = FakeDriver(find_returns=["e-quick", "e-quick", None, None])
    client = TradingViewPaperClient(driver)
    await client.place_order(_alert(action="buy"))
    assert driver.acted() == ["e-quick"]  # exactly one click, no double-fire


@pytest.mark.asyncio
async def test_submits_ticket_when_distinct_from_quick_button() -> None:
    driver = FakeDriver(find_returns=["e-quick", "e-quick", "e-qty", "e-submit"])
    client = TradingViewPaperClient(driver)
    await client.place_order(_alert(action="buy"))
    assert driver.acted() == ["e-quick", "e-submit"]


# ---- order management: close / cancel / flatten / list ------------------

POSITIONS_TREE = """
[e1|tab|Positions 2]
[e2|tab|Orders]
[e10|columnheader|Symbol]
[e11|cell|NASDAQ:AAPL]
[e12|cell|FX_IDC:USDCOP]
[e20|button|Close]
[e21|button|Protect Position…]
[e22|button|Close account manager]
"""

ORDERS_TREE = """
[e1|tab|Positions 1]
[e2|tab|Orders 1]
[e10|cell|NASDAQ:AAPL]
[e30|button|Buy 1 AAPL @ 312.06 LIMIT]
[e31|button|Cancel]
[e32|button|Modify Order…]
"""


def _connected(driver: FakeDriver) -> TradingViewPaperClient:
    c = TradingViewPaperClient(driver)
    c._paper_connected = True  # skip the connect flow (tested separately)
    return c


@pytest.mark.asyncio
async def test_list_positions_parses_symbol_cells() -> None:
    client = _connected(FakeDriver(tree=POSITIONS_TREE))
    positions = await client.list_positions()
    assert set(positions) == {"NASDAQ:AAPL", "FX_IDC:USDCOP"}


@pytest.mark.asyncio
async def test_list_orders_returns_symbols_when_count_positive() -> None:
    client = _connected(FakeDriver(tree=ORDERS_TREE))  # tab "Orders 1"
    orders = await client.list_orders()
    assert "NASDAQ:AAPL" in orders


@pytest.mark.asyncio
async def test_list_orders_ignores_ticket_button_when_count_zero() -> None:
    """Regression (live finding): the order-entry ticket submit button reads as
    'Buy N SYM @ price' but is NOT a working order. With 'Orders' count 0, the
    list must be empty even though the ticket button is present."""
    tree = (
        "[e1|tab|Positions 1]\n"
        "[e2|tab|Orders]\n"  # no count → 0 working orders
        "[e30|button|Buy  1,000 USDCOP @ 3,667.7 LIMIT]\n"  # the ticket button
        "[e31|cell|FX_IDC:USDCOP]\n"
    )
    client = _connected(FakeDriver(tree=tree))
    assert await client.list_orders() == []


@pytest.mark.asyncio
async def test_close_position_selects_row_and_clicks_close() -> None:
    driver = FakeDriver(tree=POSITIONS_TREE)
    client = _connected(driver)
    assert await client.close_position("AAPL") is True
    acted = driver.acted()
    assert "e11" in acted  # selected the NASDAQ:AAPL row
    assert "e20" in acted  # clicked the exact "Close" button (not "Close account manager")


@pytest.mark.asyncio
async def test_close_uses_exact_close_not_substring() -> None:
    """Close must resolve the exact 'Close' button, never 'Close account manager'."""
    driver = FakeDriver(tree=POSITIONS_TREE)
    client = _connected(driver)
    await client.close_position("AAPL")
    # e22 is "Close account manager" — must never be clicked
    assert "e22" not in driver.acted()


@pytest.mark.asyncio
async def test_cancel_order_clicks_cancel() -> None:
    driver = FakeDriver(tree=ORDERS_TREE)
    client = _connected(driver)
    assert await client.cancel_order("AAPL") is True
    assert "e31" in driver.acted()  # the Cancel button


@pytest.mark.asyncio
async def test_close_action_via_place_order() -> None:
    driver = FakeDriver(tree=POSITIONS_TREE)
    client = _connected(driver)
    receipt = await client.place_order(_alert(action="close", symbol="AAPL"))
    assert receipt.action == "close"
    assert receipt.raw["order_type"] == "close"
    assert "e20" in driver.acted()


@pytest.mark.asyncio
async def test_flatten_closes_all_positions() -> None:
    driver = FakeDriver(tree=POSITIONS_TREE)
    client = _connected(driver)
    closed = await client.flatten()
    assert closed == 2  # both NASDAQ:AAPL and FX_IDC:USDCOP


@pytest.mark.asyncio
async def test_flatten_action_via_place_order() -> None:
    driver = FakeDriver(tree=POSITIONS_TREE)
    client = _connected(driver)
    receipt = await client.place_order(_alert(action="flatten", symbol="AAPL"))
    assert receipt.action == "flatten"
    assert receipt.raw["order_type"] == "flatten"


@pytest.mark.asyncio
async def test_close_position_no_open_position_raises() -> None:
    # tree with a Positions tab but no Close button → InterceptorError → NotConfigured
    tree = "[e1|tab|Positions]\n[e2|tab|Orders]"
    driver = FakeDriver(tree=tree)
    client = _connected(driver)
    with pytest.raises(InterceptorError):
        await client.close_position("AAPL")


@pytest.mark.asyncio
async def test_close_action_no_position_becomes_rejected() -> None:
    """Through place_order, a missing Close control surfaces as NotConfigured."""
    tree = "[e1|tab|Positions]\n[e2|tab|Orders]"
    driver = FakeDriver(tree=tree)
    client = _connected(driver)
    with pytest.raises(NotConfiguredError):
        await client.place_order(_alert(action="close", symbol="AAPL"))


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
