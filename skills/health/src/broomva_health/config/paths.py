"""Filesystem path discovery — XDG / macOS-aware, override-friendly."""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = ["DEFAULT_VAULT_SUBDIR", "HealthPaths"]


DEFAULT_VAULT_SUBDIR: Final[str] = "07-Health"


@dataclass(frozen=True)
class HealthPaths:
    """Resolved filesystem layout for the Health skill.

    Defaults (macOS / Linux):
      config_dir       ~/.config/broomva-health/
      data_dir         ~/broomva/health/
      traces_dir       ~/broomva/health/traces/
      synthesis_db     ~/broomva/health/synthesis.db
      exports_dir      ~/broomva/health/exports/
      tokens_dir       ~/.config/broomva-health/tokens/
      vault_dir        ~/broomva-vault/
      vault_health_dir ~/broomva-vault/07-Health/
      config_file      ~/.config/broomva-health/config.toml

    Override any path via env var: `BROOMVA_HEALTH_CONFIG_DIR`,
    `BROOMVA_HEALTH_DATA_DIR`, `BROOMVA_HEALTH_VAULT_DIR`.
    """

    config_dir: Path
    data_dir: Path
    vault_dir: Path

    @classmethod
    def discover(cls, *, home: Path | None = None) -> HealthPaths:
        home = home or Path.home()
        config_dir = _env_path("BROOMVA_HEALTH_CONFIG_DIR", home / ".config" / "broomva-health")
        data_dir = _env_path("BROOMVA_HEALTH_DATA_DIR", home / "broomva" / "health")
        vault_dir = _env_path("BROOMVA_HEALTH_VAULT_DIR", home / "broomva-vault")
        return cls(config_dir=config_dir, data_dir=data_dir, vault_dir=vault_dir)

    # --- derived paths ---
    @property
    def traces_dir(self) -> Path:
        return self.data_dir / "traces"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def synthesis_db(self) -> Path:
        return self.data_dir / "synthesis.db"

    @property
    def tokens_dir(self) -> Path:
        return self.config_dir / "tokens"

    @property
    def state_file(self) -> Path:
        return self.config_dir / "state.json"

    @property
    def vault_health_dir(self) -> Path:
        return self.vault_dir / DEFAULT_VAULT_SUBDIR

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    def trace_db_for(self, source_name: str) -> Path:
        """Per-source trace DB path: traces_dir/<source>.db."""
        return self.traces_dir / f"{source_name}.db"

    def ensure(self) -> None:
        """Create all needed directories (idempotent)."""
        for path in (
            self.config_dir,
            self.data_dir,
            self.traces_dir,
            self.exports_dir,
            self.tokens_dir,
            self.vault_health_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(self.tokens_dir, 0o700)


def _env_path(key: str, default: Path) -> Path:
    value = os.environ.get(key)
    return Path(value).expanduser() if value else default
