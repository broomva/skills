"""Token store port — abstracts where source-auth tokens live.

Default adapter: filesystem under `~/.config/broomva-health/tokens/`.
Optional adapter: macOS Keychain (via `keyring` extra).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from broomva_health.domain.results import TokenBundle
from broomva_health.domain.source import Source

__all__ = ["TokenStore"]


@runtime_checkable
class TokenStore(Protocol):
    """Persist + retrieve opaque token bundles per (source, profile)."""

    def get(self, source: Source, profile: str = "default") -> TokenBundle | None: ...

    def put(self, bundle: TokenBundle) -> None: ...

    def delete(self, source: Source, profile: str = "default") -> None: ...

    def list_profiles(self, source: Source) -> list[str]: ...
