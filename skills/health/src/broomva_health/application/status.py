"""Health-status use case — reflexive snapshot across all registered sources."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from broomva_health.domain.results import SourceStatus
from broomva_health.ports.source import TraceSource
from broomva_health.ports.token_store import TokenStore

__all__ = ["HealthStatusUseCase"]


@dataclass(frozen=True)
class HealthStatusUseCase:
    sources: Iterable[TraceSource]
    token_store: TokenStore

    def execute(self, *, profile: str = "default") -> list[SourceStatus]:
        return [s.status(token_store=self.token_store, profile=profile) for s in self.sources]
