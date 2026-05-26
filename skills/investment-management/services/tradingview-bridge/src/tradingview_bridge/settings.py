"""Settings — pydantic-settings, env-loaded, paper-only enforced.

The single source of truth for runtime configuration. All consumers import
`get_settings()` rather than reading os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# TradingView's currently published webhook source IPs.
# Verify periodically: https://www.tradingview.com/support/solutions/43000529348/
DEFAULT_TV_ALLOWED_IPS: tuple[str, ...] = (
    "52.89.214.238",
    "34.212.75.30",
    "54.218.53.128",
    "52.32.178.7",
)


class Settings(BaseSettings):
    """Runtime configuration. Loaded from environment variables.

    All env vars use the `TVBRIDGE_` prefix.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TVBRIDGE_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    trading_mode: Literal["paper", "live"] = Field(
        default=...,  # required
        description="Must be 'paper' in PR 1. Service exits 1 at startup otherwise.",
    )

    tv_webhook_secret: SecretStr = Field(
        default=...,  # required
        description="Shared secret Pine Script alerts must include in body.secret.",
    )

    tv_allowed_ips: tuple[str, ...] = Field(
        default=DEFAULT_TV_ALLOWED_IPS,
        description="Source IPs allowed to POST /webhook.",
    )

    rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        le=10_000,
        description="Per-IP rate limit on /webhook. PR 2 wires the limiter.",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="structlog level.",
    )

    trust_forwarded_for: bool = Field(
        default=False,
        description=(
            "If true, use X-Forwarded-For for source IP check. "
            "Enable when running behind a reverse proxy / Cloudflare Tunnel."
        ),
    )

    broker_mode: Literal["mock", "real-paper"] = Field(
        default="mock",
        description=(
            "Broker dispatch mode. 'mock' (default) routes every alert to a "
            "MockClient that records orders in-memory — used by all tests and "
            "local dev. 'real-paper' attempts to connect to IBKR TWS (paper "
            "port), Kraken sandbox, and Polymarket CLOB; requires broker-"
            "specific env vars per README."
        ),
    )

    db_path: str | None = Field(
        default=None,
        description=(
            "Path to SQLite idempotency DB. Default: "
            "~/.tradingview-bridge/idempotency.sqlite. Tests override via "
            "a tmp_path fixture."
        ),
    )

    @field_validator("tv_allowed_ips", mode="before")
    @classmethod
    def _split_csv(cls, v: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
        """Accept comma-separated string from env vars."""
        if isinstance(v, str):
            return tuple(ip.strip() for ip in v.split(",") if ip.strip())
        return tuple(v)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Re-evaluated only on process restart."""
    return Settings()


class PaperOnlyViolation(SystemExit):
    """Raised at startup if TRADING_MODE != paper. Hard exit, no recovery."""

    def __init__(self, mode: str) -> None:
        super().__init__(
            f"PR 1 enforces paper-only mode. Got TVBRIDGE_TRADING_MODE={mode!r}. "
            "Set TVBRIDGE_TRADING_MODE=paper or wait for PR 2+ which gates live access."
        )


def assert_paper_only(settings: Settings | None = None) -> None:
    """Raise PaperOnlyViolation if trading_mode != 'paper'.

    Called at FastAPI startup. PR 1 has no code path that executes orders,
    so even if this check were bypassed no order would ship — but the check
    exists to make the safety stance structural and obvious.
    """
    s = settings or get_settings()
    if s.trading_mode != "paper":
        raise PaperOnlyViolation(s.trading_mode)
