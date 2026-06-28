"""Tests for config/settings.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from broomva_health.config.settings import HealthSettings, load_settings


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # Clear any BROOMVA_HEALTH_* env so this test asserts model defaults only.
    for var in list(__import__("os").environ):
        if var.startswith("BROOMVA_HEALTH_"):
            monkeypatch.delenv(var, raising=False)
    s = HealthSettings()
    assert s.default_profile == "default"
    assert s.log_level == "INFO"
    assert s.encrypt_db is False
    assert s.rate_limit_min_interval_s == 900
    assert s.e2e is False


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROOMVA_HEALTH_DEFAULT_PROFILE", "broomva")
    monkeypatch.setenv("BROOMVA_HEALTH_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("BROOMVA_HEALTH_RATE_LIMIT_MIN_INTERVAL_S", "60")
    s = HealthSettings()
    assert s.default_profile == "broomva"
    assert s.log_level == "DEBUG"
    assert s.rate_limit_min_interval_s == 60


def test_toml_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("BROOMVA_HEALTH_DEFAULT_PROFILE", "BROOMVA_HEALTH_LOG_LEVEL"):
        monkeypatch.delenv(var, raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'default_profile = "fromtoml"\n'
        'log_level = "WARNING"\n'
        "[garmin]\n"
        'email = "me@example.com"\n'
    )
    s = load_settings(cfg)
    assert s.default_profile == "fromtoml"
    assert s.log_level == "WARNING"
    assert s.garmin.get("email") == "me@example.com"


def test_invalid_profile_rejected() -> None:
    with pytest.raises(ValueError, match="alnum"):
        HealthSettings(default_profile="bad name!")
