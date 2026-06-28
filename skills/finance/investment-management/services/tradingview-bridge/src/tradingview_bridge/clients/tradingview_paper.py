"""TradingViewPaperClient — control TradingView's built-in Paper Trading broker.

TradingView has no inbound trading API, so this client drives the Trading Panel
UI through the Interceptor `Driver` (real Chrome, the user's logged-in session).
It conforms to the same `BrokerClient` ABC as the IBKR/Kraken/Polymarket clients,
so the Dispatcher and the autonomous operator treat it identically.

The client depends only on the `Driver` Protocol, so unit tests inject a fake
driver and assert the *sequence* of UI actions. Element names were captured from
live sessions (Trade → Paper Trading; quick `Buy<price>`/`Sell<price>`; ticket
submit `Buy N SYM @ price`; `Cancel` / `Modify Order…` in the Orders tab;
`Close` / `Protect Position…` in the Positions tab; positions keyed by an
`EXCHANGE:TICKER` Symbol column). Refs shift per read, so the client always
resolves controls by semantic role+name, never by hardcoded ref.

Order-management surface:
  place_order(buy/sell)  — market order via the ticket
  place_order(close)     — close the position for the alert's symbol
  place_order(flatten)   — close all open positions
  cancel_order(symbol)   — cancel working order(s)
  list_positions()       — open positions keyed by symbol
  list_orders()          — working order descriptions

Deferred: limit/stop order types, modify_order, protect (stop/TP).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

import structlog

from ..interceptor_driver import (
    Driver,
    Element,
    InterceptorDriver,
    InterceptorError,
    parse_elements,
)
from ..schemas import TVAlert
from .base import BrokerClient, BrokerName, NotConfiguredError, OrderReceipt

log = structlog.get_logger("tradingview_bridge.clients.tradingview_paper")

DEFAULT_CHART_URL = "https://www.tradingview.com/chart/"

# Position symbols render as EXCHANGE:TICKER (e.g. NASDAQ:AAPL, FX_IDC:USDCOP).
_SYMBOL_CELL_RE = re.compile(r"^[A-Z0-9_]{1,12}:[A-Z0-9_./]{1,15}$")


def _looks_like_symbol(name: str) -> bool:
    return bool(_SYMBOL_CELL_RE.match(name.strip()))


def _symbol_matches(target: str, cell_symbol: str) -> bool:
    """True if `target` (e.g. AAPL) identifies `cell_symbol` (e.g. NASDAQ:AAPL)."""
    t = target.upper().strip()
    c = cell_symbol.upper().strip()
    return t == c or c.endswith(":" + t) or t in c


class TradingViewPaperClient(BrokerClient):
    """Drives TradingView's Paper Trading simulator via Interceptor."""

    def __init__(
        self,
        driver: Driver | None = None,
        *,
        chart_url: str = DEFAULT_CHART_URL,
    ) -> None:
        self._driver: Driver = driver if driver is not None else InterceptorDriver()
        # Keep the URL verbatim — `.../chart/` must stay `.../chart/?symbol=X`.
        self._chart_url = chart_url
        self._paper_connected = False

    @property
    def broker_name(self) -> BrokerName:
        return "tradingview-paper"

    # ---- BrokerClient interface -----------------------------------------

    async def place_order(self, alert: TVAlert) -> OrderReceipt:
        try:
            await self._navigate_symbol(alert.symbol)
            await self._ensure_paper_connected()
            order_type = await self._apply_action(alert)
        except InterceptorError as e:
            raise NotConfiguredError(
                f"TradingView Paper Trading not controllable via Interceptor: {e}"
            ) from e

        order_id = f"tvpaper-{uuid.uuid4().hex[:12]}"
        receipt = OrderReceipt(
            broker="tradingview-paper",
            order_id=order_id,
            alert_id=alert.alert_id,
            symbol=alert.symbol,
            action=alert.action,
            size=alert.size,
            submitted_at=datetime.now(tz=UTC),
            paper=True,
            raw={"venue": "tradingview-paper-simulator", "order_type": order_type},
        )
        log.info(
            "tradingview_paper_order_placed",
            order_id=order_id,
            symbol=alert.symbol,
            action=alert.action,
            size=str(alert.size),
            order_type=order_type,
        )
        return receipt

    async def health_check(self) -> bool:
        try:
            await self._driver.open(self._symbol_url(None))
            return await self._driver.find("button", "Trade") is not None
        except InterceptorError as e:
            log.warning("tradingview_paper_unhealthy", error=str(e))
            return False

    # ---- order-management surface ---------------------------------------

    async def _apply_action(self, alert: TVAlert) -> str:
        """Map a TVAlert action to a UI flow. Returns the order_type recorded."""
        if alert.action in ("buy", "sell"):
            await self._submit_market_order(side=alert.action, size=str(alert.size))
            return "market"
        if alert.action == "close":
            await self.close_position(alert.symbol)
            return "close"
        if alert.action == "flatten":
            await self.flatten()
            return "flatten"
        raise NotImplementedError(f"Unhandled action {alert.action!r}")

    async def list_positions(self) -> dict[str, str]:
        """Open positions keyed by symbol (EXCHANGE:TICKER → row summary)."""
        try:
            await self._ensure_panel()
            await self._switch_tab("Positions")
            els = parse_elements(await self._driver.read_tree())
        except InterceptorError as e:
            log.warning("tradingview_paper_positions_unavailable", error=str(e))
            return {}
        return {
            e.name.strip(): "open" for e in els if e.role == "cell" and _looks_like_symbol(e.name)
        }

    async def positions(self) -> dict[str, str]:
        """Alias kept for the operator's PositionManager hook."""
        return await self.list_positions()

    async def list_orders(self) -> list[str]:
        """Symbols of *working* orders from the Orders tab.

        Gated on the `Orders N` tab count: the order-entry ticket's submit
        button also reads as `Buy N SYM @ price`, so a naive scan reports a
        phantom order when none are working. We count working orders from the
        tab label and read their symbols from row cells (role=cell), never from
        the ticket button (role=button). N == 0 → no working orders.
        """
        try:
            await self._ensure_panel()
            await self._switch_tab("Orders")
            els = parse_elements(await self._driver.read_tree())
        except InterceptorError as e:
            log.warning("tradingview_paper_orders_unavailable", error=str(e))
            return []
        if self._tab_count(els, "Orders") <= 0:
            return []
        return [e.name.strip() for e in els if e.role == "cell" and _looks_like_symbol(e.name)]

    @staticmethod
    def _tab_count(els: list[Element], prefix: str) -> int:
        """Read the integer N from a tab labelled like `Orders 2` / `Positions 1`."""
        for e in els:
            if e.role == "tab" and e.name.strip().startswith(prefix):
                m = re.search(rf"{prefix}\s+(\d+)", e.name)
                return int(m.group(1)) if m else 0
        return 0

    async def close_position(self, symbol: str) -> bool:
        """Close the open position for `symbol`. Returns True if a Close was issued."""
        await self._ensure_panel()
        await self._switch_tab("Positions")
        await self._select_row_by_symbol(symbol)
        close_ref = await self._driver.find("button", "Close", exact=True)
        if close_ref is None:
            raise InterceptorError(
                f"No Close control for position {symbol!r} in the Positions tab "
                "(no open position, or the DOM shifted)."
            )
        await self._driver.act(close_ref)
        log.info("tradingview_paper_position_closed", symbol=symbol)
        return True

    async def cancel_order(self, symbol: str | None = None) -> bool:
        """Cancel a working order (optionally selecting the row for `symbol` first)."""
        await self._ensure_panel()
        await self._switch_tab("Orders")
        if symbol is not None:
            await self._select_row_by_symbol(symbol)
        cancel_ref = await self._driver.find("button", "Cancel", exact=True)
        if cancel_ref is None:
            raise InterceptorError(
                "No Cancel control in the Orders tab (no working order, or DOM shifted)."
            )
        await self._driver.act(cancel_ref)
        log.info("tradingview_paper_order_cancelled", symbol=symbol)
        return True

    async def flatten(self) -> int:
        """Close every open position. Returns the count closed."""
        positions = await self.list_positions()
        closed = 0
        for sym in positions:
            try:
                await self.close_position(sym)
                closed += 1
            except InterceptorError as e:
                log.warning("tradingview_paper_flatten_skip", symbol=sym, error=str(e))
        log.info("tradingview_paper_flattened", closed=closed, of=len(positions))
        return closed

    # ---- internal UI flows ----------------------------------------------

    def _symbol_url(self, symbol: str | None) -> str:
        if symbol is None:
            return self._chart_url
        sep = "&" if "?" in self._chart_url else "?"
        return f"{self._chart_url}{sep}symbol={symbol}"

    async def _navigate_symbol(self, symbol: str) -> None:
        await self._driver.open(self._symbol_url(symbol))

    async def _ensure_panel(self) -> None:
        """Make sure the Trading Panel is reachable (no symbol navigation)."""
        await self._driver.open(self._symbol_url(None))
        await self._ensure_paper_connected()

    async def _ensure_paper_connected(self) -> None:
        if self._paper_connected:
            return
        if await self._driver.find("button", "Buy") is not None:
            self._paper_connected = True
            return
        trade_ref = await self._driver.find("button", "Trade")
        if trade_ref is not None:
            await self._driver.act(trade_ref)
        paper_ref = await self._driver.find("button", "Paper Trading")
        if paper_ref is not None:
            await self._driver.act(paper_ref)
        self._paper_connected = True

    async def _switch_tab(self, name: str) -> None:
        """Click the account-manager tab whose name starts with `name` (Orders/Positions)."""
        ref = await self._driver.find("tab", name)
        if ref is not None:
            await self._driver.act(ref)

    async def _select_row_by_symbol(self, symbol: str) -> None:
        """Best-effort: click the row cell matching `symbol` so per-row controls target it."""
        els = parse_elements(await self._driver.read_tree())
        for e in els:
            if e.role == "cell" and _looks_like_symbol(e.name) and _symbol_matches(symbol, e.name):
                await self._driver.act(e.ref)
                return

    async def _submit_market_order(self, *, side: str, size: str) -> None:
        """Place a market order, guarding against a double-submit.

        The quick `Buy<price>`/`Sell<price>` button arms (or, depending on the
        account's order-confirm setting, immediately places) the order. We only
        click the ticket submit if it is a DISTINCT element from the quick
        button — so if the quick button already placed the order, we never
        double-fire.
        """
        side_name = "Buy" if side == "buy" else "Sell"
        quick_ref = await self._require("button", side_name, what=f"{side_name} control")
        await self._driver.act(quick_ref)

        qty_ref = await self._driver.find("spinbutton", "Quantity")
        if qty_ref is None:
            qty_ref = await self._driver.find("textbox", "Quantity")
        if qty_ref is not None:
            await self._driver.type(qty_ref, size)

        # The ticket submit repeats the side name with a trailing space then qty
        # (e.g. "Buy 1 AAPL @ 312.06") — never matches the spaceless quick button.
        submit_ref = await self._driver.find("button", f"{side_name} ", exact=False)
        if submit_ref is not None and submit_ref != quick_ref:
            await self._driver.act(submit_ref)

    async def _require(self, role: str, name: str, *, what: str) -> str:
        ref = await self._driver.find(role, name)
        if ref is None:
            raise InterceptorError(
                f"Could not find {what} (role={role!r} name~={name!r}) in the "
                "TradingView Trading Panel. The DOM may have shifted — re-pin via "
                "the Interceptor dogfood."
            )
        return ref
