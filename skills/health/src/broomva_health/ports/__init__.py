"""Ports layer — protocol interfaces. All concrete deps depend on these, not on adapters."""

from __future__ import annotations

from broomva_health.ports.clock import Clock
from broomva_health.ports.mfa import MFAProvider
from broomva_health.ports.projection import ProjectionTarget
from broomva_health.ports.rate_limiter import RateLimiter
from broomva_health.ports.repository import TraceRepository
from broomva_health.ports.source import TraceSource
from broomva_health.ports.token_store import TokenStore

__all__ = [
    "Clock",
    "MFAProvider",
    "ProjectionTarget",
    "RateLimiter",
    "TokenStore",
    "TraceRepository",
    "TraceSource",
]
