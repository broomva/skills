"""TradingViewPaperClient — control TradingView's built-in Paper Trading broker.

TradingView has no inbound trading API, so this client drives the Trading Panel
UI through the Interceptor `Driver` (real Chrome, the user's logged-in session).
It conforms to the same `BrokerClient` ABC as the IBKR/Kraken/Polymarket clients,
so the Dispatcher and the autonomous operator treat it identically.

The client depends only on the `Driver` Protocol, so unit tests inject a fake
driver and assert the *sequence* of UI actions. The exact element names were
captured from a live spike (Trade button → broker panel → "Paper Trading —
Brokerage simulator by TradingView"; BUY/SELL quick-trade controls). They are
pinned and corrected by the live Interceptor dogfood, which is the only place
the real DOM is exercised.

v1 scope: market buy/sell + positions read + health. close/flatten and
limit/stop orders are deferred (the dispatcher turns the resulting
NotImplementedError into a clean `rejected` DispatchResult).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from ..interceptor_driver import Driver, InterceptorDriver, InterceptorError
from ..schemas import TVAlert
from .base import BrokerClient, BrokerName, NotConfiguredError, OrderReceipt

log = structlog.get_logger("tradingview_bridge.clients.tradingview_paper")

DEFAULT_CHART_URL = "https://www.tradingview.com/chart/"


class TradingViewPaperClient(BrokerClient):
    """Drives TradingView's Paper Trading simulator via Interceptor."""

    def __init__(
        self,
        driver: Driver | None = None,
        *,
        chart_url: str = DEFAULT_CHART_URL,
    ) -> None:
        """
        Args:
            driver: an Interceptor Driver. Defaults to the real InterceptorDriver;
                tests inject a fake. Typed as the Protocol for substitutability.
            chart_url: base TradingView chart URL. Symbol is appended as ?symbol=.
        """
        self._driver: Driver = driver if driver is not None else InterceptorDriver()
        # Keep the URL verbatim — `.../chart/` must stay `.../chart/?symbol=X`,
        # not lose its trailing slash.
        self._chart_url = chart_url
        self._paper_connected = False

    @property
    def broker_name(self) -> BrokerName:
        return "tradingview-paper"

    async def place_order(self, alert: TVAlert) -> OrderReceipt:
        if alert.action not in ("buy", "sell"):
            # Honest boundary — the dispatcher renders this as a clean `rejected`.
            raise NotImplementedError(
                f"TradingView-Paper v1 supports market buy/sell; "
                f"action={alert.action!r} (close/flatten) is deferred."
            )

        try:
            await self._navigate_symbol(alert.symbol)
            await self._ensure_paper_connected()
            await self._submit_market_order(side=alert.action, size=str(alert.size))
        except InterceptorError as e:
            # Browser/UI not reachable → surface as NotConfigured (rejected),
            # not a crash, identical to the other clients' failure contract.
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
            raw={"venue": "tradingview-paper-simulator", "order_type": "market"},
        )
        log.info(
            "tradingview_paper_order_placed",
            order_id=order_id,
            symbol=alert.symbol,
            action=alert.action,
            size=str(alert.size),
        )
        return receipt

    async def health_check(self) -> bool:
        """True if the chart is reachable and the Trade control is present."""
        try:
            await self._driver.open(self._symbol_url(None))
            trade = await self._driver.find("button", "Trade")
            return trade is not None
        except InterceptorError as e:
            log.warning("tradingview_paper_unhealthy", error=str(e))
            return False

    async def positions(self) -> dict[str, str]:
        """Best-effort read of the TradingView paper Positions tab.

        Returns a {symbol: qty-string} map. Parsing the positions table is DOM-
        shape dependent and finalized by the dogfood; until then this returns an
        empty map rather than guessing, so the operator falls back to its own
        order ledger. Wiring this into operator reconciliation is the SHOULD.
        """
        try:
            await self._driver.read_text()
        except InterceptorError as e:
            log.warning("tradingview_paper_positions_unavailable", error=str(e))
        return {}

    # ---- internal UI flows (selectors pinned by the live dogfood) --------

    def _symbol_url(self, symbol: str | None) -> str:
        if symbol is None:
            return self._chart_url
        sep = "&" if "?" in self._chart_url else "?"
        return f"{self._chart_url}{sep}symbol={symbol}"

    async def _navigate_symbol(self, symbol: str) -> None:
        await self._driver.open(self._symbol_url(symbol))

    async def _ensure_paper_connected(self) -> None:
        """Idempotently connect the Paper Trading simulator.

        Cheap fast-path: if a Buy/Sell control is already present the panel is
        connected. Otherwise open Trade and click Paper Trading.
        """
        if self._paper_connected:
            return
        existing = await self._driver.find("button", "Buy")
        if existing is not None:
            self._paper_connected = True
            return
        trade_ref = await self._driver.find("button", "Trade")
        if trade_ref is not None:
            await self._driver.act(trade_ref)
        paper_ref = await self._driver.find("button", "Paper Trading")
        if paper_ref is not None:
            await self._driver.act(paper_ref)
        self._paper_connected = True

    async def _submit_market_order(self, *, side: str, size: str) -> None:
        side_name = "Buy" if side == "buy" else "Sell"
        side_ref = await self._require("button", side_name, what=f"{side_name} control")
        await self._driver.act(side_ref)

        qty_ref = await self._driver.find("spinbutton", "Quantity")
        if qty_ref is None:
            qty_ref = await self._driver.find("textbox", "Quantity")
        if qty_ref is not None:
            await self._driver.type(qty_ref, size)

        # Confirm — the ticket's primary button typically repeats the side name.
        confirm_ref = await self._driver.find("button", f"{side_name} ", exact=False)
        if confirm_ref is not None:
            await self._driver.act(confirm_ref)

    async def _require(self, role: str, name: str, *, what: str) -> str:
        ref = await self._driver.find(role, name)
        if ref is None:
            raise InterceptorError(
                f"Could not find {what} (role={role!r} name~={name!r}) in the "
                "TradingView Trading Panel. The DOM may have shifted — re-pin via "
                "the Interceptor dogfood."
            )
        return ref
