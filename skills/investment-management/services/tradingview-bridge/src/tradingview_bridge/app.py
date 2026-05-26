"""FastAPI app — POST /webhook + GET /health.

PR 2 wires the multi-broker dispatcher, idempotency store, rate limiter,
and bookkeeping journal hook into the request pipeline.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import ValidationError

from .auth import require_valid_secret, source_ip, verify_source_ip
from .dispatch import Dispatcher
from .idempotency import IdempotencyStore, default_db_path
from .logging_setup import configure_logging
from .ratelimit import TokenBucketLimiter
from .schemas import DispatchResult, TVAlert
from .settings import assert_paper_only, get_settings

# Module-level singletons; populated in lifespan.
_dispatcher: Dispatcher | None = None
_limiter: TokenBucketLimiter | None = None
_idempotency_store: IdempotencyStore | None = None


def get_dispatcher() -> Dispatcher:
    """FastAPI dependency for the Dispatcher singleton."""
    if _dispatcher is None:
        raise RuntimeError("Dispatcher not initialized — lifespan did not run.")
    return _dispatcher


def get_limiter() -> TokenBucketLimiter:
    if _limiter is None:
        raise RuntimeError("RateLimiter not initialized — lifespan did not run.")
    return _limiter


def check_rate_limit(
    request: Request,
    limiter: TokenBucketLimiter = Depends(get_limiter),
) -> None:
    """FastAPI dependency — 429 if the request exceeds per-IP rate."""
    ip = source_ip(request)
    if not limiter.check(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {limiter.limit} requests/minute per IP.",
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Startup hook — runs paper-only assertion, wires singletons."""
    global _dispatcher, _limiter, _idempotency_store

    log = configure_logging()
    settings = get_settings()
    assert_paper_only(settings)

    db_path = Path(settings.db_path).expanduser() if settings.db_path else default_db_path()
    _idempotency_store = IdempotencyStore(db_path=db_path)
    _limiter = TokenBucketLimiter(limit_per_minute=settings.rate_limit_per_minute)
    _dispatcher = Dispatcher(
        broker_mode=settings.broker_mode,
        idempotency_store=_idempotency_store,
    )

    log.info(
        "tradingview_bridge_started",
        mode=settings.trading_mode,
        broker_mode=settings.broker_mode,
        allowed_ips=list(settings.tv_allowed_ips),
        rate_limit_per_minute=settings.rate_limit_per_minute,
        trust_forwarded_for=settings.trust_forwarded_for,
        idempotency_db=str(db_path),
    )
    yield
    log.info("tradingview_bridge_stopped")

    _dispatcher = None
    _limiter = None
    _idempotency_store = None


app = FastAPI(
    title="TradingView Bridge",
    description=(
        "Webhook receiver for TradingView Pine Script alerts. "
        "PR 2: receiver + multi-broker executor (paper-only, mock-default)."
    ),
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health(dispatcher: Dispatcher = Depends(get_dispatcher)) -> dict[str, Any]:
    """Liveness probe with per-broker connectivity status."""
    s = get_settings()
    broker_health = await dispatcher.health_check()
    return {
        "status": "ok",
        "mode": s.trading_mode,
        "broker_mode": s.broker_mode,
        "version": "0.2.0",
        "brokers": broker_health,
    }


@app.post(
    "/webhook",
    response_model=DispatchResult,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_source_ip), Depends(check_rate_limit)],
)
async def webhook(
    request: Request,
    dispatcher: Dispatcher = Depends(get_dispatcher),
) -> DispatchResult:
    """Receive a Pine Script alert; validate, authenticate, dispatch."""
    log = structlog.get_logger("tradingview_bridge.webhook")

    try:
        body = await request.json()
    except Exception as e:
        log.warning("webhook_bad_json", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is not valid JSON",
        ) from e

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Request body must be a JSON object",
        )

    provided_secret = body.get("secret")
    if not isinstance(provided_secret, str) or not provided_secret:
        log.warning("webhook_missing_secret")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or empty shared secret",
        )
    require_valid_secret(provided_secret)

    try:
        alert = TVAlert(**body)
    except ValidationError as e:
        log.info("webhook_validation_failed", errors=e.errors())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=e.errors(),
        ) from e

    return await dispatcher.dispatch(alert)
