"""Domain error hierarchy.

All errors carry stable string identifiers (`code`) so the CLI layer can
map them to deterministic exit codes without string-matching messages.
"""

from __future__ import annotations

__all__ = [
    "AuthRequired",
    "ConfigError",
    "HealthError",
    "MFANeeded",
    "ProjectionError",
    "RateLimited",
    "RepositoryError",
    "SourceUnavailable",
    "SyncFailed",
]


class HealthError(Exception):
    """Base for every domain-raised error."""

    code: str = "health_error"
    exit_code: int = 1

    def __init__(self, message: str = "", **context: object) -> None:
        super().__init__(message)
        self.context = context

    def __repr__(self) -> str:
        ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
        return f"{type(self).__name__}({self.args[0]!r}{', ' + ctx if ctx else ''})"


class AuthRequired(HealthError):
    """The source has no valid token; the user must re-run `health auth login`."""

    code = "auth_required"
    exit_code = 2  # matches eddmann CLI convention


class MFANeeded(HealthError):
    """The source returned a step-up MFA challenge mid-login."""

    code = "mfa_needed"
    exit_code = 2


class RateLimited(HealthError):
    """The source rate-limited us; retry after `retry_after_s` seconds."""

    code = "rate_limited"
    exit_code = 1

    def __init__(self, message: str = "", *, retry_after_s: float | None = None) -> None:
        super().__init__(message, retry_after_s=retry_after_s)
        self.retry_after_s = retry_after_s


class SourceUnavailable(HealthError):
    """The source library failed in a way that isn't auth/rate-limit."""

    code = "source_unavailable"


class RepositoryError(HealthError):
    """The trace repository raised an error (disk full, schema mismatch...)."""

    code = "repository_error"


class ProjectionError(HealthError):
    """A projection target (Obsidian, healthOS feed) failed."""

    code = "projection_error"


class ConfigError(HealthError):
    """Misconfiguration — bad TOML, missing required env, broken paths."""

    code = "config_error"


class SyncFailed(HealthError):
    """Aggregate failure surface raised by use cases."""

    code = "sync_failed"
