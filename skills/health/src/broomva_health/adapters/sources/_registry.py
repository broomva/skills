"""Source registry — central factory for TraceSource adapters.

Add a new source: append a `Source.<NAME>` member, implement the adapter,
and register it here.

Garmin has multiple **backends** behind the one `TraceSource` port, selected
by `[garmin] backend` in config:

- ``native``  (default — ``_DEFAULT_GARMIN_BACKEND``) — in-house: ``garth``
              rides an existing token (imported via ``health auth import``); we
              own the connectapi calls + aggregation + mapping. No external
              binary, no fresh-login wall.
- ``cli``     — delegate to eddmann's ``garmin-connect`` CLI; the CLI owns the
              token lifecycle, so the skill never handles credentials and never
              hits the walled fresh-login path.
- ``library`` — direct ``garminconnect`` import; automatable but its fresh
              SSO login is Cloudflare-walled (429 / CAPTCHA / account-lock).
- ``browser`` — (planned) Interceptor real-Chrome capture; CAPTCHA-proof but
              needs an interactive session. Not yet wired here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

from broomva_health.adapters.sources.garmin import GarminTraceSource
from broomva_health.adapters.sources.garmin_cli import GarminCliTraceSource
from broomva_health.adapters.sources.garmin_native import GarminNativeTraceSource
from broomva_health.config.paths import HealthPaths
from broomva_health.domain.errors import ConfigError
from broomva_health.domain.source import Source
from broomva_health.ports.source import TraceSource

if TYPE_CHECKING:
    from broomva_health.config.settings import HealthSettings

__all__ = ["SOURCE_REGISTRY", "build_sources", "get_source"]


#: Back-compat registry (library backend). Prefer ``build_sources`` which is
#: settings-aware and picks the Garmin backend.
SOURCE_REGISTRY: Final[Mapping[Source, type]] = {
    Source.GARMIN: GarminTraceSource,
}

_DEFAULT_GARMIN_BACKEND = "native"


def _garmin_source(settings: HealthSettings | None, paths: HealthPaths) -> TraceSource:
    """Construct the Garmin adapter for the configured backend (default ``native``).

    - ``native``  (default) — in-house: garth rides an existing token, we own
      the connectapi calls + aggregation + mapping. Bootstrap via
      ``health auth import``. No external binary, no fresh-login wall.
    - ``cli``     — delegate to eddmann's ``garmin-connect`` binary.
    - ``library`` — direct ``garminconnect`` import (diauth; fresh login may be
      Cloudflare-walled).
    - ``browser`` — (planned) Interceptor real-Chrome capture.
    """
    garmin_cfg = dict(getattr(settings, "garmin", {}) or {}) if settings else {}
    backend = str(garmin_cfg.get("backend", _DEFAULT_GARMIN_BACKEND)).lower()
    cli_path = str(garmin_cfg.get("cli_path", "garmin-connect"))

    if backend == "native":
        return GarminNativeTraceSource(paths=paths)
    if backend == "cli":
        return GarminCliTraceSource(paths=paths, cli_path=cli_path)
    if backend == "library":
        return GarminTraceSource(paths=paths)
    if backend == "browser":
        raise ConfigError(
            "garmin backend 'browser' (Interceptor) is planned but not yet wired; "
            "use 'native' (default), 'cli', or 'library'.",
            backend=backend,
        )
    raise ConfigError(
        f"unknown garmin backend {backend!r}; expected one of: native, cli, library, browser",
        backend=backend,
    )


def build_sources(
    settings: HealthSettings | None, paths: HealthPaths
) -> dict[Source, TraceSource]:
    """Construct every registered source adapter, honoring per-source backends.

    This is the settings-aware entry point the container uses. Garmin's backend
    comes from ``[garmin] backend``; other sources use their single adapter.
    """
    return {
        Source.GARMIN: _garmin_source(settings, paths),
    }


def get_source(source: Source, *, paths: HealthPaths) -> TraceSource:
    """Construct a TraceSource adapter for ``source`` (library/default backend).

    Kept for back-compat callers that don't have settings. For Garmin this
    returns the **library** backend; prefer ``build_sources`` for the
    config-selected default (``native`` — ``_DEFAULT_GARMIN_BACKEND``).
    """
    cls = SOURCE_REGISTRY.get(source)
    if cls is None:
        raise ConfigError(
            f"no adapter registered for source {source!r}; "
            f"available: {sorted(s.value for s in SOURCE_REGISTRY)}",
            source=str(source),
        )
    return cls(paths=paths)
