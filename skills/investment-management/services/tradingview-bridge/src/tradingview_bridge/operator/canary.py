"""CanaryProbe — the self-dogfood roundtrip check.

This is P11 (Empirical Feedback Loop) crystallized into a runtime probe. Each
tick, the operator fires a synthetic ``__canary__`` alert through the REAL
dispatch pipeline and verifies it roundtrips. If it does not, the operator
halts position management (the interlock in OperatorLoop).

Two layers of check, composed:

  1. in-process dispatch (always): construct/borrow a Dispatcher, dispatch a
     canary TVAlert, assert the result is ``accepted`` (fresh) or ``duplicate``
     (replayed). This exercises routing + idempotency + the mock broker client +
     the order ledger filter — the core pipeline, with no network.

  2. HTTP health (optional augment): if a probe URL is configured, GET
     ``{url}/health`` and assert 200 with all brokers healthy. This confirms the
     *server process* is actually up and serving — the part the in-process check
     cannot see.

The canary passes iff every configured check passes. Canary alerts use a
reserved ``strategy_name`` (``__canary__``) so the order ledger never records
them as positions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import structlog

from ..orders import CANARY_PREFIX
from ..schemas import TVAlert

log = structlog.get_logger("tradingview_bridge.operator.canary")

CANARY_SYMBOL = "__CANARY__"


@dataclass
class CanaryResult:
    """Outcome of one canary run."""

    passed: bool
    detail: str
    checks: dict[str, bool] = field(default_factory=dict)


def build_canary_alert(tick: int, secret: str = "operator-canary") -> TVAlert:  # noqa: S107
    """Construct the synthetic canary alert for a given tick.

    The alert_id is unique per tick so each canary is a *fresh* dispatch
    (status ``accepted``), proving the pipeline processes new alerts — not just
    that it dedups. The strategy_name carries the canary prefix so the order
    ledger filters it out of positions.
    """
    return TVAlert(
        alert_id=f"{CANARY_PREFIX}-{tick}",
        secret=secret,  # pydantic coerces str -> SecretStr
        strategy_name=f"{CANARY_PREFIX}-operator",
        asset_class="stock",
        symbol=CANARY_SYMBOL,
        action="buy",
        size=Decimal("1"),
        size_type="units",
        time=datetime.now(tz=UTC),
    )


class CanaryProbe:
    """Fires the canary through the dispatch pipeline (+ optional HTTP health)."""

    def __init__(
        self,
        dispatcher: object,
        *,
        http_url: str | None = None,
        http_timeout_s: float = 5.0,
    ) -> None:
        """
        Args:
            dispatcher: a Dispatcher (duck-typed: must have ``async dispatch(alert)``).
                Typed as ``object`` to avoid a hard import cycle with dispatch.py.
            http_url: optional base URL of the running bridge (e.g.
                http://127.0.0.1:8787). When set, the canary also GETs /health.
            http_timeout_s: timeout for the HTTP health check.
        """
        self._dispatcher = dispatcher
        self._http_url = http_url.rstrip("/") if http_url else None
        self._http_timeout_s = http_timeout_s

    async def run(self, tick: int) -> CanaryResult:
        """Run all configured checks and return the composite result."""
        checks: dict[str, bool] = {}
        details: list[str] = []

        # --- Check 1: in-process dispatch roundtrip ---
        try:
            alert = build_canary_alert(tick)
            result = await self._dispatcher.dispatch(alert)  # type: ignore[attr-defined]
            status = getattr(result, "status", None)
            ok = status in ("accepted", "duplicate")
            checks["dispatch"] = ok
            if not ok:
                details.append(f"dispatch returned status={status!r} (expected accepted/duplicate)")
        except Exception as e:
            checks["dispatch"] = False
            details.append(f"dispatch raised {type(e).__name__}: {e}")

        # --- Check 2: HTTP /health (optional) ---
        if self._http_url is not None:
            checks["http_health"] = await self._check_http_health(details)

        passed = all(checks.values()) and len(checks) > 0
        detail = "all canary checks passed" if passed else "; ".join(details) or "canary failed"
        log.info("canary_run", tick=tick, passed=passed, checks=checks, detail=detail)
        return CanaryResult(passed=passed, detail=detail, checks=checks)

    async def _check_http_health(self, details: list[str]) -> bool:
        """GET {url}/health and assert 200 + all brokers healthy."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=self._http_timeout_s) as client:
                resp = await client.get(f"{self._http_url}/health")
            if resp.status_code != 200:
                details.append(f"/health returned {resp.status_code}")
                return False
            body = resp.json()
            brokers = body.get("brokers", {})
            if not brokers or not all(brokers.values()):
                details.append(f"/health brokers unhealthy: {brokers}")
                return False
            return True
        except Exception as e:
            details.append(f"/health check raised {type(e).__name__}: {e}")
            return False
