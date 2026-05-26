"""TVAlert schema validation tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from tradingview_bridge.schemas import DispatchResult, TVAlert


def test_valid_alert_parses(valid_alert_body: dict[str, object]) -> None:
    alert = TVAlert(**valid_alert_body)
    assert alert.alert_id == "test-alert-001"
    assert alert.asset_class == "stock"
    assert alert.symbol == "AAPL"
    assert alert.action == "buy"
    assert alert.size == Decimal("10")
    assert alert.size_type == "units"


def test_secret_is_redacted_in_repr(valid_alert_body: dict[str, object]) -> None:
    alert = TVAlert(**valid_alert_body)
    rendered = repr(alert)
    assert "secret" in rendered.lower()  # field name appears
    # The actual secret value should not leak through repr
    assert "test-secret-do-not-use" not in rendered


def test_missing_required_field_fails(valid_alert_body: dict[str, object]) -> None:
    del valid_alert_body["alert_id"]
    with pytest.raises(ValidationError) as ei:
        TVAlert(**valid_alert_body)
    assert any(err["loc"] == ("alert_id",) for err in ei.value.errors())


def test_unknown_asset_class_fails(valid_alert_body: dict[str, object]) -> None:
    valid_alert_body["asset_class"] = "options"  # not in our literal
    with pytest.raises(ValidationError):
        TVAlert(**valid_alert_body)


def test_unknown_action_fails(valid_alert_body: dict[str, object]) -> None:
    valid_alert_body["action"] = "yolo"
    with pytest.raises(ValidationError):
        TVAlert(**valid_alert_body)


def test_negative_size_fails(valid_alert_body: dict[str, object]) -> None:
    valid_alert_body["size"] = "-5"
    with pytest.raises(ValidationError):
        TVAlert(**valid_alert_body)


def test_zero_size_fails(valid_alert_body: dict[str, object]) -> None:
    valid_alert_body["size"] = "0"
    with pytest.raises(ValidationError):
        TVAlert(**valid_alert_body)


@pytest.mark.parametrize(
    ("asset_class", "symbol"),
    [
        ("stock", "AAPL"),
        ("etf", "SPY"),
        ("bond", "TLT"),
        ("fx", "EURUSD"),
        ("crypto", "BTC/USD"),
        ("prediction", "0xMARKET_ID"),
    ],
)
def test_all_asset_classes_accepted(
    valid_alert_body: dict[str, object],
    asset_class: str,
    symbol: str,
) -> None:
    valid_alert_body["asset_class"] = asset_class
    valid_alert_body["symbol"] = symbol
    alert = TVAlert(**valid_alert_body)
    assert alert.asset_class == asset_class
    assert alert.symbol == symbol


def test_extra_fields_allowed(valid_alert_body: dict[str, object]) -> None:
    """Schema is extra='allow' so brokers can thread strategy-specific hints."""
    valid_alert_body["future_field_pr5"] = "anything"
    alert = TVAlert(**valid_alert_body)
    assert alert.alert_id == "test-alert-001"


def test_dispatch_result_extra_forbidden() -> None:
    """DispatchResult is extra='forbid' — strict contract back to the caller."""
    with pytest.raises(ValidationError):
        DispatchResult(  # type: ignore[call-arg]
            status="stubbed",
            broker="ibkr",
            detail="x",
            alert_id="a",
            random_extra="nope",
        )
