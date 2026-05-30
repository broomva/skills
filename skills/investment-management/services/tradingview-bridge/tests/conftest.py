"""Test fixtures — set env vars, reset settings cache, manage idempotency DB."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from tradingview_bridge import settings as settings_module

TEST_SECRET = "test-secret-do-not-use-in-prod-or-anywhere-real"


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Clear the lru_cache on get_settings() so each test reads fresh env."""
    settings_module.get_settings.cache_clear()
    yield
    settings_module.get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _disable_bookkeeping(_no_dotenv: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable the bookkeeping subprocess during tests.

    The bookkeeping hook fires a fire-and-forget asyncio subprocess; if the
    test event loop closes before the subprocess completes (which it usually
    does on a sub-second test), the transport leaks as ResourceWarning and
    trips pyproject.toml's `filterwarnings = ["error"]` config. Point the
    CLI resolver at a non-existent path so `_resolve_bookkeeping_cli()`
    returns None and `journal_alert` exits early before fork().

    Depends on `_no_dotenv` so this fixture runs AFTER `_no_dotenv`'s
    bulk TVBRIDGE_* env-var purge — otherwise the purge would remove our
    setenv too.
    """
    monkeypatch.setenv(
        "TVBRIDGE_BOOKKEEPING_CLI",
        "/nonexistent-bookkeeping-cli-disabled-for-tests",
    )


# Ensure tests don't pick up a real .env from the developer's machine.
@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Force settings to NOT load a .env file during tests.

    pydantic-settings looks for .env in CWD; we override by setting CWD to
    a temp dir, and unset all TVBRIDGE_* vars defensively.
    """
    monkeypatch.chdir(str(tmp_path))
    for k in list(os.environ):
        if k.startswith("TVBRIDGE_"):
            monkeypatch.delenv(k, raising=False)


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Per-test SQLite path so idempotency tests don't share state."""
    return tmp_path / "test-idempotency.sqlite"


@pytest.fixture
def tmp_orders_db_path(tmp_path: Path) -> Path:
    """Per-test order-ledger SQLite path."""
    return tmp_path / "test-orders.sqlite"


@pytest.fixture
def tmp_state_path(tmp_path: Path) -> Path:
    """Per-test operator-state JSON path."""
    return tmp_path / "operator-state.json"


@pytest.fixture
def paper_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_db_path: Path,
) -> None:
    """Default safe env — paper mode, mock broker, test secret, tmp DB."""
    monkeypatch.setenv("TVBRIDGE_TRADING_MODE", "paper")
    monkeypatch.setenv("TVBRIDGE_TV_WEBHOOK_SECRET", TEST_SECRET)
    monkeypatch.setenv("TVBRIDGE_BROKER_MODE", "mock")
    monkeypatch.setenv("TVBRIDGE_DB_PATH", str(tmp_db_path))
    # Clear .env-leaked vars defensively
    for k in ("TVBRIDGE_TV_ALLOWED_IPS", "TVBRIDGE_TRUST_FORWARDED_FOR"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env with TRADING_MODE=live — used to assert PaperOnlyViolation."""
    monkeypatch.setenv("TVBRIDGE_TRADING_MODE", "live")
    monkeypatch.setenv("TVBRIDGE_TV_WEBHOOK_SECRET", TEST_SECRET)


@pytest.fixture
def real_paper_no_creds_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_db_path: Path,
) -> None:
    """Env with TRADING_MODE=paper + BROKER_MODE=real-paper but no creds.

    Used by tests asserting clients raise NotConfiguredError.
    """
    monkeypatch.setenv("TVBRIDGE_TRADING_MODE", "paper")
    monkeypatch.setenv("TVBRIDGE_TV_WEBHOOK_SECRET", TEST_SECRET)
    monkeypatch.setenv("TVBRIDGE_BROKER_MODE", "real-paper")
    monkeypatch.setenv("TVBRIDGE_DB_PATH", str(tmp_db_path))
    # NB: no broker credentials set → real-paper clients should refuse.


@pytest.fixture
def valid_alert_body() -> dict[str, object]:
    """Canonical valid alert body for a stock buy."""
    return {
        "alert_id": "test-alert-001",
        "secret": TEST_SECRET,
        "strategy_name": "smoke-test-strategy",
        "asset_class": "stock",
        "symbol": "AAPL",
        "action": "buy",
        "size": "10",
        "size_type": "units",
        "price_hint": "180.50",
        "order_type": "market",
        "time": "2026-05-22T15:00:00Z",
        "metadata": {"timeframe": "15m"},
    }
