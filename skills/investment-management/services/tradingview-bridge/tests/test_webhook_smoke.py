"""End-to-end smoke tests — PR 2 wires broker clients (mock mode in CI).

These tests exercise the full pipeline:
  request → IP check → rate limit → JSON parse → secret check → schema validation
       → idempotency check → broker dispatch (MockClient) → response.

PR 2 changes from PR 1:
- happy path now returns `accepted` + `order_id` instead of `stubbed`
- new: 429 on rate-limit
- new: `duplicate` status on idempotency hit
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tradingview_bridge import app as app_module
from tradingview_bridge import settings as settings_module

TV_IP_OK = "52.89.214.238"
TV_IP_BAD = "203.0.113.42"


def _headers(ip: str = TV_IP_OK) -> dict[str, str]:
    return {"X-Forwarded-For": ip}


@pytest.fixture
def trusted_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TVBRIDGE_TRUST_FORWARDED_FOR", "true")


@pytest.fixture
def fresh_app(paper_env: None, trusted_proxy_env: None) -> Iterator[TestClient]:
    settings_module.get_settings.cache_clear()
    importlib.reload(app_module)
    with TestClient(app_module.app) as c:
        yield c


def test_health(fresh_app: TestClient) -> None:
    resp = fresh_app.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mode"] == "paper"
    assert body["broker_mode"] == "mock"
    assert body["brokers"] == {"ibkr": True, "kraken": True, "polymarket": True}


def test_webhook_happy_path_accepted(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    resp = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_OK))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["broker"] == "ibkr"
    assert body["alert_id"] == "test-alert-001"
    assert body["order_id"] is not None
    assert body["order_id"].startswith("mock-")


def test_webhook_duplicate_alert_returns_duplicate(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    """Same alert_id fired twice → second response is 'duplicate' with same order_id."""
    resp1 = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_OK))
    assert resp1.status_code == 200
    first_order = resp1.json()["order_id"]

    resp2 = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_OK))
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["status"] == "duplicate"
    assert body2["order_id"] == first_order


def test_webhook_wrong_secret(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    valid_alert_body["secret"] = "wrong-secret"
    resp = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_OK))
    assert resp.status_code == 401, resp.text


def test_webhook_missing_secret(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    del valid_alert_body["secret"]
    resp = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_OK))
    assert resp.status_code == 401


def test_webhook_wrong_ip(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    resp = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_BAD))
    assert resp.status_code == 403


def test_webhook_422_on_bad_action_with_good_secret(
    fresh_app: TestClient,
    valid_alert_body: dict[str, Any],
) -> None:
    valid_alert_body["action"] = "yolo"
    resp = fresh_app.post("/webhook", json=valid_alert_body, headers=_headers(TV_IP_OK))
    assert resp.status_code == 422


def test_webhook_400_on_bad_json(
    fresh_app: TestClient,
) -> None:
    resp = fresh_app.post(
        "/webhook",
        content=b"not json",
        headers={**_headers(TV_IP_OK), "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_webhook_429_on_rate_limit(
    paper_env: None,
    trusted_proxy_env: None,
    monkeypatch: pytest.MonkeyPatch,
    valid_alert_body: dict[str, Any],
) -> None:
    """Exceeding rate limit returns 429.

    Set the limit very low (2/min) so the test doesn't take 60+ seconds.
    The rate limiter is constructed in the lifespan from
    settings.rate_limit_per_minute, so monkeypatch the env var.
    """
    monkeypatch.setenv("TVBRIDGE_RATE_LIMIT_PER_MINUTE", "2")
    settings_module.get_settings.cache_clear()
    importlib.reload(app_module)

    with TestClient(app_module.app) as client:
        # Vary alert_id so idempotency doesn't short-circuit us before the limiter
        for i in range(2):
            body = {**valid_alert_body, "alert_id": f"rate-{i}"}
            r = client.post("/webhook", json=body, headers=_headers(TV_IP_OK))
            assert r.status_code == 200, f"request {i}: {r.text}"
        body3 = {**valid_alert_body, "alert_id": "rate-3"}
        r = client.post("/webhook", json=body3, headers=_headers(TV_IP_OK))
        assert r.status_code == 429, r.text


def test_paper_only_assertion_blocks_live(live_env: None) -> None:
    settings_module.get_settings.cache_clear()
    settings = settings_module.get_settings()
    assert settings.trading_mode == "live"
    with pytest.raises(SystemExit) as ei:
        settings_module.assert_paper_only(settings)
    assert ei.value.code is not None
    assert "paper-only" in str(ei.value).lower()


def test_paper_only_assertion_passes_in_paper(paper_env: None) -> None:
    settings_module.get_settings.cache_clear()
    settings = settings_module.get_settings()
    assert settings.trading_mode == "paper"
    settings_module.assert_paper_only(settings)
