"""Wiring container — composes adapters into the use cases.

This is the only place in the codebase where concrete adapter classes are
constructed. Use cases never know which adapter they're talking to. The
container is the seam where dependency injection happens.

Imports of adapter modules are deferred inside ``Container.build`` so that
``health --help`` works even when an optional source extra (e.g. an
unsigned Whoop SDK) is missing — only sources actually consulted bubble
the ImportError as a ``ConfigError`` with an install hint.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from broomva_health.config.paths import HealthPaths
from broomva_health.config.settings import HealthSettings
from broomva_health.domain.errors import ConfigError
from broomva_health.domain.source import Source

if TYPE_CHECKING:
    from broomva_health.ports.clock import Clock
    from broomva_health.ports.mfa import MFAProvider
    from broomva_health.ports.projection import ProjectionTarget
    from broomva_health.ports.rate_limiter import RateLimiter
    from broomva_health.ports.repository import TraceRepository
    from broomva_health.ports.source import TraceSource
    from broomva_health.ports.token_store import TokenStore

__all__ = ["Container", "SystemClock"]


class SystemClock:
    """Default ``Clock`` adapter — wraps ``datetime.now(tz=UTC)``."""

    def now(self) -> datetime:
        return datetime.now(tz=UTC)


def _install_hint(adapter_name: str, exc: ImportError) -> ConfigError:
    return ConfigError(
        (
            f"Required adapter '{adapter_name}' is not installed. "
            f"Install the matching extra (see `pyproject.toml`) or pin the "
            f"underlying SDK. Underlying ImportError: {exc}"
        ),
        adapter=adapter_name,
    )


@dataclass
class Container:
    """Concrete-adapter holder + per-source repository factory.

    Construct via ``Container.build(settings, paths)``. The factory
    instantiates a ``TokenStore``, ``RateLimiter``, ``MFAProvider``,
    ``Clock``, and the registered source adapters once; repositories are
    created lazily per ``Source`` (one DB file per source) so opening the
    Garmin DB doesn't force opening the Whoop DB on every CLI call.
    """

    paths: HealthPaths
    settings: HealthSettings
    clock: Clock
    token_store: TokenStore
    rate_limiter: RateLimiter
    mfa: MFAProvider
    sources: dict[Source, TraceSource] = field(default_factory=dict)
    projection: ProjectionTarget | None = None
    _repos: dict[Source, TraceRepository] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    # Public API.
    # ------------------------------------------------------------------

    def repository_for(self, source: Source) -> TraceRepository:
        """Return a migrated ``SQLiteTraceRepository`` for ``source``.

        First call per source opens the DB, runs ``migrate()``, and caches
        the connection. Subsequent calls return the cached repository.
        Callers should not close repositories directly — invoke
        ``container.close()`` once at shutdown instead.
        """

        if source in self._repos:
            return self._repos[source]
        try:
            from broomva_health.adapters.repositories.sqlite import (
                SQLiteTraceRepository,
            )
        except ImportError as exc:  # pragma: no cover — packaged with the project
            raise _install_hint("repositories.sqlite", exc) from exc

        db_path = self.paths.trace_db_for(source.value)
        repo = SQLiteTraceRepository(db_path)
        try:
            repo.migrate()
        except Exception as exc:
            raise ConfigError(
                f"Failed to migrate trace DB at {db_path}: {exc}",
                source=source.value,
                db_path=str(db_path),
            ) from exc
        self._repos[source] = repo
        return repo

    def close(self) -> None:
        """Close all open per-source repositories."""

        for repo in self._repos.values():
            close = getattr(repo, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    close()
        self._repos.clear()

    # ------------------------------------------------------------------
    # Factory.
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        settings: HealthSettings,
        paths: HealthPaths,
    ) -> Container:
        """Compose the standard adapter set.

        Adapter modules are imported lazily so that ``health --help`` keeps
        working when an optional extra is missing. Failed imports raise
        ``ConfigError`` with a clear install hint — never an opaque
        ``ImportError`` from deep inside the SDK.
        """

        # NB: do NOT call paths.ensure() here — Container.build runs on every
        # CLI invocation including `health --help`, and we don't want to silently
        # mkdir the user's ~/broomva-vault/ just from inspecting help text. The
        # writing commands (auth login, sync, daily-note) call paths.ensure()
        # themselves; the doctor command reports missing dirs without creating
        # them.

        clock = SystemClock()

        # --- TokenStore --------------------------------------------------
        try:
            from broomva_health.adapters.token_stores.filesystem import (
                FilesystemTokenStore,
            )
        except ImportError as exc:
            raise _install_hint("token_stores.filesystem", exc) from exc
        token_store: TokenStore = FilesystemTokenStore(paths.tokens_dir)

        # --- RateLimiter -------------------------------------------------
        try:
            from broomva_health.adapters.rate_limiters.token_bucket import (
                TokenBucketRateLimiter,
            )
        except ImportError as exc:
            raise _install_hint("rate_limiters.token_bucket", exc) from exc
        # state_path persists last_acquire_at across process restarts so cron
        # invocations honor the 15-min poll floor; without it, every fresh
        # process would start with an empty bucket and bypass the limit.
        rate_limit_state = paths.config_dir / "rate_limiter.state.json"
        rate_limiter: RateLimiter = TokenBucketRateLimiter(
            min_interval_s=settings.rate_limit_min_interval_s,
            clock=clock,
            state_path=rate_limit_state,
        )

        # --- MFA ---------------------------------------------------------
        try:
            from broomva_health.adapters.mfa.prompt import PromptMFAProvider
        except ImportError as exc:
            raise _install_hint("mfa.prompt", exc) from exc
        mfa: MFAProvider = PromptMFAProvider()

        # --- Sources -----------------------------------------------------
        # The registry is settings-aware: it picks the Garmin backend from
        # `[garmin] backend` (default 'native' — in-house garth client riding an
        # imported token; 'cli' delegates to garmin-connect; 'library' = direct
        # garminconnect import). See _registry._DEFAULT_GARMIN_BACKEND.
        try:
            from broomva_health.adapters.sources._registry import build_sources
        except ImportError as exc:
            raise _install_hint("sources._registry", exc) from exc
        sources: dict[Source, TraceSource] = build_sources(settings, paths)

        # --- ProjectionTarget (optional — v1 only used by daily-note) ---
        projection: ProjectionTarget | None = None
        try:
            from broomva_health.adapters.projections.obsidian import (
                ObsidianDailyNoteProjection,
            )

            projection = ObsidianDailyNoteProjection(paths.vault_health_dir)
        except ImportError:
            projection = None

        return cls(
            paths=paths,
            settings=settings,
            clock=clock,
            token_store=token_store,
            rate_limiter=rate_limiter,
            mfa=mfa,
            sources=sources,
            projection=projection,
        )
