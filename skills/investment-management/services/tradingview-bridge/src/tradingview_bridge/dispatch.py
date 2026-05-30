"""Dispatcher — routes a validated TVAlert through idempotency + broker client.

PR 2 replaces PR 1's NotImplementedError stubs with real client-backed dispatch:

1. Route by asset_class to a broker name (pure function `route_asset_class`)
2. Idempotency check — if alert_id was seen, return the existing receipt
3. Call the broker client (mock or real-paper, depending on TVBRIDGE_BROKER_MODE)
4. Record the new (alert_id, order_id) in the idempotency store
5. Fire-and-forget bookkeeping journal entry
6. Return DispatchResult

Failure modes:
- NotConfiguredError from the client (real-paper without creds) → rejected
- Idempotency hit (alert already processed) → duplicate with existing order_id
- Bookkeeping subprocess failure → logged, never propagated
"""

from __future__ import annotations

from datetime import datetime

import aiosqlite
import structlog

from .bookkeeping import schedule_journal
from .clients import IBKRClient, KrakenClient, PolymarketClient, TradingViewPaperClient
from .clients.base import BrokerClient, BrokerName, NotConfiguredError
from .idempotency import IdempotencyRecord, IdempotencyStore
from .orders import OrderLedger
from .schemas import AssetClass, DispatchResult, TVAlert

log = structlog.get_logger("tradingview_bridge.dispatch")


def route_asset_class(asset_class: AssetClass) -> BrokerName:
    """Pure function — returns the broker name responsible for an asset class.

    Extracted so future broker additions only touch this function.
    """
    if asset_class in ("stock", "etf", "bond", "fx"):
        return "ibkr"
    if asset_class == "crypto":
        return "kraken"
    if asset_class == "prediction":
        return "polymarket"
    raise ValueError(f"Unknown asset class: {asset_class!r}")


class Dispatcher:
    """Async dispatcher backed by broker clients + optional idempotency store.

    Construct ONCE per process — owned by the FastAPI app lifespan in `app.py`.
    Tests construct fresh Dispatcher instances per case via fixtures.
    """

    def __init__(
        self,
        broker_mode: str = "mock",
        idempotency_store: IdempotencyStore | None = None,
        clients_override: dict[BrokerName, BrokerClient] | None = None,
        order_ledger: OrderLedger | None = None,
    ) -> None:
        """
        Args:
            broker_mode: "mock" or "real-paper" — see clients/base.py.
            idempotency_store: SQLite-backed dedup. None means no dedup
                (acceptable for tests that don't assert idempotency).
            clients_override: test hook — inject specific clients without
                instantiating the real classes.
            order_ledger: SQLite-backed economic record of accepted orders,
                read by the autonomous operator for position tracking. None
                disables order recording (acceptable for receiver-only tests).
                Canary orders are filtered out by the ledger itself.
        """
        self._broker_mode = broker_mode
        self._idempotency = idempotency_store
        self._order_ledger = order_ledger

        if clients_override is not None:
            self._clients: dict[BrokerName, BrokerClient] = clients_override
        elif broker_mode == "tradingview-paper":
            # TradingView Paper trades any symbol on its own chart, so a single
            # client handles every asset class — routing is bypassed below.
            self._clients = {"tradingview-paper": TradingViewPaperClient()}
        else:
            self._clients = {
                "ibkr": IBKRClient(broker_mode),
                "kraken": KrakenClient(broker_mode),
                "polymarket": PolymarketClient(broker_mode),
            }

    def _route(self, alert: TVAlert) -> BrokerName:
        """Resolve the broker for an alert.

        In tradingview-paper mode every alert goes to the single TradingView
        Paper client; otherwise route by asset class.
        """
        if self._broker_mode == "tradingview-paper":
            return "tradingview-paper"
        return route_asset_class(alert.asset_class)

    async def dispatch(self, alert: TVAlert) -> DispatchResult:
        """Route the alert through idempotency + broker + journal."""
        broker_name = self._route(alert)
        client = self._clients[broker_name]

        # Idempotency pre-check
        if self._idempotency is not None:
            existing = await self._peek_idempotency(alert.alert_id)
            if existing is not None:
                log.info(
                    "dispatch_duplicate",
                    alert_id=alert.alert_id,
                    existing_order_id=existing.order_id,
                    existing_broker=existing.broker,
                )
                return DispatchResult(
                    status="duplicate",
                    broker=broker_name,
                    alert_id=alert.alert_id,
                    order_id=existing.order_id,
                    detail=(
                        f"Alert {alert.alert_id} already processed by "
                        f"{existing.broker} (order {existing.order_id})."
                    ),
                )

        log.info(
            "alert_dispatched",
            alert_id=alert.alert_id,
            strategy=alert.strategy_name,
            asset_class=alert.asset_class,
            symbol=alert.symbol,
            action=alert.action,
            size=str(alert.size),
            broker=broker_name,
            mode=self._broker_mode,
        )

        try:
            receipt = await client.place_order(alert)
        except NotConfiguredError as e:
            log.warning(
                "broker_not_configured",
                alert_id=alert.alert_id,
                broker=broker_name,
                error=str(e),
            )
            return DispatchResult(
                status="rejected",
                broker=broker_name,
                alert_id=alert.alert_id,
                detail=str(e),
            )
        except NotImplementedError as e:
            log.info(
                "broker_not_implemented",
                alert_id=alert.alert_id,
                broker=broker_name,
                detail=str(e),
            )
            return DispatchResult(
                status="rejected",
                broker=broker_name,
                alert_id=alert.alert_id,
                detail=f"Broker {broker_name} real-paper wiring deferred: {e}",
            )

        # Record in idempotency store (after successful broker call)
        if self._idempotency is not None:
            await self._idempotency.check_or_insert(
                alert_id=alert.alert_id,
                broker=broker_name,
                order_id=receipt.order_id,
            )

        # Record in the order ledger for position tracking (canary orders are
        # filtered out inside append()). Awaited so positions stay accurate.
        if self._order_ledger is not None:
            await self._order_ledger.append(
                order_id=receipt.order_id,
                alert_id=alert.alert_id,
                strategy_name=alert.strategy_name,
                broker=broker_name,
                asset_class=alert.asset_class,
                symbol=alert.symbol,
                action=alert.action,
                size=alert.size,
                paper=receipt.paper,
            )

        # Fire-and-forget bookkeeping
        schedule_journal(alert, receipt)

        return DispatchResult(
            status="accepted",
            broker=broker_name,
            alert_id=alert.alert_id,
            order_id=receipt.order_id,
            detail=f"Order placed by {broker_name} (paper={receipt.paper}).",
        )

    async def health_check(self) -> dict[str, bool]:
        """Per-broker connectivity check for /health endpoint."""
        return {broker: await client.health_check() for broker, client in self._clients.items()}

    async def _peek_idempotency(self, alert_id: str) -> IdempotencyRecord | None:
        """Read-only check — returns existing record or None.

        We can't use check_or_insert here because we don't have the
        order_id yet. Acceptable tiny race window for PR 2's single-instance
        mode; PR 3+ would use Redis SETNX or a DB transaction.
        """
        store = self._idempotency
        if store is None:
            return None
        async with aiosqlite.connect(store._db_path) as db:
            await store._ensure_schema(db)
            cursor = await db.execute(
                "SELECT broker, order_id, created_at FROM alert_idempotency WHERE alert_id = ?",
                (alert_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return IdempotencyRecord(
                alert_id=alert_id,
                broker=row[0],
                order_id=row[1],
                created_at=datetime.fromisoformat(row[2]),
            )
