"""Runtime settings — loaded from TOML + env (env wins)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["HealthSettings", "load_settings"]


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class HealthSettings(BaseSettings):
    """User-tunable settings.

    Resolution order (lowest → highest precedence):
      1. defaults defined on the model
      2. TOML at `~/.config/broomva-health/config.toml`
      3. environment variables prefixed `BROOMVA_HEALTH_`
      4. constructor kwargs

    Example `config.toml`:

        default_profile = "broomva"
        rate_limit_min_interval_s = 900
        log_level = "INFO"
        encrypt_db = false

        [garmin]
        email = "me@example.com"
    """

    model_config = SettingsConfigDict(
        env_prefix="BROOMVA_HEALTH_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    default_profile: str = Field(default="default", min_length=1)
    log_level: LogLevel = "INFO"
    encrypt_db: bool = Field(
        default=False,
        description="Reserved for v1.1 SQLCipher integration; ignored in v1",
    )
    rate_limit_min_interval_s: int = Field(default=900, ge=60, le=86400)
    e2e: bool = Field(
        default=False,
        description="Set true (or BROOMVA_HEALTH_E2E=1) to enable e2e tests + real Garmin calls",
    )

    # Per-source bags — populated from [garmin], [whoop], [oura], [cgm] tables
    garmin: dict[str, Any] = Field(default_factory=dict)
    apple_health: dict[str, Any] = Field(default_factory=dict)
    whoop: dict[str, Any] = Field(default_factory=dict)
    oura: dict[str, Any] = Field(default_factory=dict)
    cgm: dict[str, Any] = Field(default_factory=dict)

    @field_validator("default_profile", mode="after")
    @classmethod
    def _profile_ascii(cls, value: str) -> str:
        if not value.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"profile must be alnum/_/-, got {value!r}")
        return value


def load_settings(config_file: Path | None) -> HealthSettings:
    """Load settings from TOML (if present) merged with env + defaults."""
    data: dict[str, Any] = {}
    if config_file is not None and config_file.exists():
        with config_file.open("rb") as fh:
            data = tomllib.load(fh)
    return HealthSettings(**data)
