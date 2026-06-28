"""Shared pytest fixtures for the Health skill test suite."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from broomva_health.config.paths import HealthPaths
from broomva_health.config.settings import HealthSettings


@pytest.fixture
def fixed_now() -> datetime:
    """A stable UTC instant used across deterministic tests."""
    return datetime(2026, 5, 22, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def tmp_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HealthPaths]:
    """Discover paths under a tmp dir so tests never touch the real filesystem."""
    monkeypatch.setenv("BROOMVA_HEALTH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BROOMVA_HEALTH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BROOMVA_HEALTH_VAULT_DIR", str(tmp_path / "vault"))
    paths = HealthPaths.discover(home=tmp_path)
    paths.ensure()
    return paths


@pytest.fixture
def tmp_settings(monkeypatch: pytest.MonkeyPatch) -> HealthSettings:
    """A HealthSettings instance with safe defaults; ignores user TOML."""
    for var in list(os.environ):
        if var.startswith("BROOMVA_HEALTH_") and var not in {
            "BROOMVA_HEALTH_CONFIG_DIR",
            "BROOMVA_HEALTH_DATA_DIR",
            "BROOMVA_HEALTH_VAULT_DIR",
        }:
            monkeypatch.delenv(var, raising=False)
    return HealthSettings()


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip @pytest.mark.e2e tests unless BROOMVA_HEALTH_E2E=1."""
    if os.environ.get("BROOMVA_HEALTH_E2E") == "1":
        return
    skip_e2e = pytest.mark.skip(reason="set BROOMVA_HEALTH_E2E=1 to run e2e")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)
