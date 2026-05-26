"""Source registry — central factory for TraceSource adapters.

Add a new source: append a `Source.<NAME>` member, implement the adapter,
and register it here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from broomva_health.adapters.sources.garmin import GarminTraceSource
from broomva_health.config.paths import HealthPaths
from broomva_health.domain.errors import ConfigError
from broomva_health.domain.source import Source
from broomva_health.ports.source import TraceSource

__all__ = ["SOURCE_REGISTRY", "get_source"]


SOURCE_REGISTRY: Final[Mapping[Source, type]] = {
    Source.GARMIN: GarminTraceSource,
}


def get_source(source: Source, *, paths: HealthPaths) -> TraceSource:
    """Construct a TraceSource adapter for `source`.

    Raises `ConfigError` if the source is not registered.
    """
    cls = SOURCE_REGISTRY.get(source)
    if cls is None:
        raise ConfigError(
            f"no adapter registered for source {source!r}; "
            f"available: {sorted(s.value for s in SOURCE_REGISTRY)}",
            source=str(source),
        )
    return cls(paths=paths)
