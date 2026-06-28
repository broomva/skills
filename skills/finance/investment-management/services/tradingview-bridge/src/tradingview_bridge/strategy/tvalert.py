"""Signal → TVAlert — the live execution adapter.

Converts a strategy Signal into the TVAlert the bridge/operator already speaks,
so a strategy runs live through the exact pipeline a TradingView Pine alert
would. ``hold`` produces no alert (None). Short entries map to ``sell``; the
operator/broker decides whether that opens a short or reduces a long.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..schemas import AssetClass, TVAlert
from .types import Signal

# Strategy action → TVAlert action. `hold` has no live representation.
_ACTION_MAP: dict[str, str] = {
    "enter_long": "buy",
    "enter_short": "sell",
    "exit": "close",
}


def signal_to_tvalert(
    signal: Signal,
    *,
    symbol: str,
    asset_class: AssetClass,
    strategy_name: str,
    secret: str,
    alert_id: str,
    time: datetime | None = None,
) -> TVAlert | None:
    """Build a TVAlert from a Signal, or None for ``hold``."""
    action = _ACTION_MAP.get(signal.action)
    if action is None:
        return None
    return TVAlert(
        alert_id=alert_id,
        secret=secret,  # pydantic coerces str -> SecretStr
        strategy_name=strategy_name,
        asset_class=asset_class,
        symbol=symbol,
        action=action,  # constrained to buy/sell/close by _ACTION_MAP values
        size=signal.size,
        size_type=signal.size_type,
        time=time or datetime.now(tz=UTC),
        metadata=dict(signal.metadata),
    )
