"""Tests for config/paths.py."""

from __future__ import annotations

import stat
from pathlib import Path

from broomva_health.config.paths import HealthPaths


def test_discover_defaults_to_home_layout(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("BROOMVA_HEALTH_CONFIG_DIR", raising=False)
    monkeypatch.delenv("BROOMVA_HEALTH_DATA_DIR", raising=False)
    monkeypatch.delenv("BROOMVA_HEALTH_VAULT_DIR", raising=False)
    paths = HealthPaths.discover(home=tmp_path)
    assert paths.config_dir == tmp_path / ".config" / "broomva-health"
    assert paths.data_dir == tmp_path / "broomva" / "health"
    assert paths.vault_dir == tmp_path / "broomva-vault"
    assert paths.vault_health_dir == tmp_path / "broomva-vault" / "07-Health"


def test_env_override(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BROOMVA_HEALTH_CONFIG_DIR", str(tmp_path / "custom-config"))
    monkeypatch.setenv("BROOMVA_HEALTH_DATA_DIR", str(tmp_path / "custom-data"))
    monkeypatch.setenv("BROOMVA_HEALTH_VAULT_DIR", str(tmp_path / "custom-vault"))
    paths = HealthPaths.discover(home=tmp_path)
    assert paths.config_dir == tmp_path / "custom-config"
    assert paths.data_dir == tmp_path / "custom-data"


def test_ensure_creates_dirs(tmp_path: Path) -> None:
    paths = HealthPaths(
        config_dir=tmp_path / "cfg",
        data_dir=tmp_path / "data",
        vault_dir=tmp_path / "vault",
    )
    paths.ensure()
    assert paths.config_dir.is_dir()
    assert paths.traces_dir.is_dir()
    assert paths.exports_dir.is_dir()
    assert paths.tokens_dir.is_dir()
    assert paths.vault_health_dir.is_dir()


def test_tokens_dir_is_700(tmp_path: Path) -> None:
    paths = HealthPaths(
        config_dir=tmp_path / "cfg",
        data_dir=tmp_path / "data",
        vault_dir=tmp_path / "vault",
    )
    paths.ensure()
    mode = stat.S_IMODE(paths.tokens_dir.stat().st_mode)
    assert mode == 0o700


def test_trace_db_for_source(tmp_path: Path) -> None:
    paths = HealthPaths(
        config_dir=tmp_path / "cfg",
        data_dir=tmp_path / "data",
        vault_dir=tmp_path / "vault",
    )
    assert paths.trace_db_for("garmin") == tmp_path / "data" / "traces" / "garmin.db"
