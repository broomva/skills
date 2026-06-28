"""Garmin source backed by eddmann's ``garmin-connect`` CLI (delegated auth).

Why this exists
---------------
The direct-library adapter (:mod:`broomva_health.adapters.sources.garmin`)
performs its own Garmin SSO login, which Garmin's Cloudflare layer walls with
``429 → ACCOUNT_LOCKED → CAPTCHA`` on repeated *fresh* logins (BRO-1252/1254).

eddmann's ``garmin-connect`` CLI wraps the same ``garminconnect`` library but
owns the **token lifecycle**: once a user has run ``garmin-connect auth login``
once, it rides a cached ~1-year OAuth1 token and refreshes the short-lived
OAuth2 bearer off the DI endpoint — never touching the walled fresh-login path.

So this adapter **delegates the entire auth problem** to a maintained tool and
reads its structured ``--format json`` output. The skill never handles the
user's Garmin credentials: ``garmin-connect auth login`` is interactive and
sends them straight to Garmin.

Contract (verified live against ``garmin-connect`` v1.x / garminconnect 0.3.3)
-----------------------------------------------------------------------------
``garmin-connect --format json auth status`` ->
    ``{"authenticated": bool, "token_dir": str, "full_name": str, ...}``

``garmin-connect --format json context`` ->
    ``{profile, today_stats, health{heart_rate, sleep, body_battery, stress},
       training, weight, recent_activities}`` (see ``_map_context``).

Exit codes (eddmann convention, mirrored by this skill): ``0`` ok,
``2`` auth-required, other non-zero = error.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from broomva_health.adapters.sources._mapping import map_context
from broomva_health.config.paths import HealthPaths
from broomva_health.domain.device import Device
from broomva_health.domain.errors import AuthRequired, SourceUnavailable
from broomva_health.domain.results import BackfillResult, SourceStatus, SyncResult
from broomva_health.domain.source import Source
from broomva_health.domain.time import utc_now
from broomva_health.ports.mfa import MFAProvider
from broomva_health.ports.rate_limiter import RateLimiter
from broomva_health.ports.repository import TraceRepository
from broomva_health.ports.token_store import TokenStore

__all__ = ["CliResult", "GarminCliTraceSource", "map_context"]

_DEFAULT_CLI = "garmin-connect"
_RATE_LIMIT_KEY = "garmin:cli:sync"
_AUTH_EXIT_CODE = 2  # eddmann + this skill: 2 == auth-required
_TIMEOUT_S = 90.0
_GARMIN_DEVICE = Device(manufacturer="garmin")


# --------------------------------------------------------------------------- #
# Runner abstraction (injectable for tests — no real CLI in CI)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CliResult:
    """Outcome of one ``garmin-connect`` invocation."""

    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str]], CliResult]


def _subprocess_runner(args: Sequence[str]) -> CliResult:
    """Default runner — shells out to the real ``garmin-connect`` binary."""
    proc = subprocess.run(  # noqa: S603 — args are a fixed CLI path + literals
        list(args),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )
    return CliResult(proc.returncode, proc.stdout, proc.stderr)




# --------------------------------------------------------------------------- #
# The adapter
# --------------------------------------------------------------------------- #


class GarminCliTraceSource:
    """``TraceSource`` that delegates to eddmann's ``garmin-connect`` CLI.

    Auth is **delegated**: this adapter never handles the user's password.
    ``authenticate`` verifies ``garmin-connect auth status`` and, if the CLI
    isn't logged in, raises ``AuthRequired`` instructing the user to run
    ``garmin-connect auth login`` once (interactive, credentials go straight
    to Garmin).
    """

    #: The CLI ``login`` command checks this to skip its ``getpass`` prompt —
    #: there is no password for this backend to collect.
    delegated_auth: bool = True

    def __init__(
        self,
        *,
        paths: HealthPaths,
        cli_path: str = _DEFAULT_CLI,
        runner: Runner | None = None,
    ) -> None:
        self._paths = paths
        self._cli_path = cli_path
        self._runner = runner or _subprocess_runner

    @property
    def name(self) -> Source:
        return Source.GARMIN

    # --- TraceSource interface -------------------------------------------

    def authenticate(
        self,
        *,
        token_store: TokenStore,  # noqa: ARG002 — delegated; eddmann owns tokens
        mfa: MFAProvider,  # noqa: ARG002 — eddmann prompts MFA itself if needed
        email: str | None = None,  # noqa: ARG002 — never used; never collected
        password: str | None = None,  # noqa: ARG002 — never used; never collected
        profile: str = "default",  # noqa: ARG002 — eddmann profile is its own config
    ) -> None:
        """Verify delegated auth; instruct the user if the CLI isn't logged in."""
        result = self._run("auth", "status", allow_auth_exit=True)
        if not (isinstance(result, dict) and result.get("authenticated")):
            raise AuthRequired(
                "Garmin auth for the `cli` backend is delegated to eddmann's "
                "`garmin-connect` CLI. Run `garmin-connect auth login` once "
                "(interactive — your credentials go directly to Garmin, never "
                "through this skill), then retry. Install it with "
                "`uv tool install garmin-connect-cli` if missing.",
            )

    def sync(
        self,
        *,
        repo: TraceRepository,
        token_store: TokenStore,  # noqa: ARG002 — delegated
        rate_limiter: RateLimiter,
        since: datetime | None = None,  # noqa: ARG002 — context is today-only
        profile: str = "default",  # noqa: ARG002 — eddmann default profile
    ) -> SyncResult:
        """Pull today's snapshot via ``context`` and upsert into the trace DB."""
        started = utc_now()
        rate_limiter.acquire(_RATE_LIMIT_KEY)
        ctx = self._run("context")
        if not isinstance(ctx, dict):
            raise SourceUnavailable(
                f"`garmin-connect context` returned {type(ctx).__name__}, expected object"
            )
        quantities, workouts = map_context(ctx, now=utc_now())
        n_q = repo.upsert_quantity(quantities) if quantities else 0
        n_w = repo.upsert_workout(workouts) if workouts else 0
        return SyncResult(
            source=Source.GARMIN,
            started_at=started,
            finished_at=utc_now(),
            samples_ingested=n_q,
            workouts_ingested=n_w,
            errors=[],
        )

    def backfill(
        self,
        *,
        repo: TraceRepository,  # noqa: ARG002
        token_store: TokenStore,  # noqa: ARG002
        rate_limiter: RateLimiter,  # noqa: ARG002
        start: date,
        end: date,
        profile: str = "default",  # noqa: ARG002
    ) -> BackfillResult:
        """Not implemented for the cli backend.

        ``context`` is a today-only snapshot. Historical backfill via per-date
        eddmann commands (``health sleep --date``, ``activities list``) is a
        follow-up; for cold-start history use Garmin's GDPR 'Export Your Data'.
        """
        raise SourceUnavailable(
            "cli backend has no historical backfill yet — it syncs today's "
            "snapshot via `context`. Track: per-date eddmann commands / GDPR export.",
            range_start=str(start),
            range_end=str(end),
        )

    def status(
        self,
        *,
        token_store: TokenStore,  # noqa: ARG002 — delegated
        profile: str = "default",  # noqa: ARG002
    ) -> SourceStatus:
        """Reflexive snapshot — never raises; reports delegated token validity."""
        valid = False
        last_error: str | None = None
        try:
            result = self._run("auth", "status", allow_auth_exit=True)
            valid = bool(isinstance(result, dict) and result.get("authenticated"))
        except SourceUnavailable as exc:  # CLI missing / not runnable
            last_error = str(exc)
        return SourceStatus(
            source=Source.GARMIN,
            last_sync=None,
            last_error=last_error,
            rate_limit_resets_at=None,
            token_valid=valid,
            token_expires_at=None,
        )

    # --- internals --------------------------------------------------------

    def _run(self, *args: str, allow_auth_exit: bool = False) -> Any:
        """Run ``garmin-connect --format json <args>`` and parse stdout JSON.

        Maps exit code ``2`` -> ``AuthRequired`` (unless ``allow_auth_exit``,
        which returns the parsed body so ``status``/``authenticate`` can read
        ``authenticated: false``), any other non-zero -> ``SourceUnavailable``.
        """
        cli = shutil.which(self._cli_path) or self._cli_path
        cmd = [cli, "--format", "json", *args]
        try:
            res = self._runner(cmd)
        except FileNotFoundError as exc:
            raise SourceUnavailable(
                f"`{self._cli_path}` not found on PATH. Install eddmann's CLI: "
                "`uv tool install garmin-connect-cli` (or `brew install "
                "eddmann/tap/garmin-connect-cli`).",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SourceUnavailable(
                f"`garmin-connect {' '.join(args)}` timed out after {_TIMEOUT_S}s"
            ) from exc

        if res.returncode == _AUTH_EXIT_CODE and not allow_auth_exit:
            raise AuthRequired(
                "`garmin-connect` is not authenticated. Run "
                "`garmin-connect auth login` once, then retry.",
            )
        if res.returncode not in (0, _AUTH_EXIT_CODE):
            detail = (res.stderr or res.stdout or "").strip()[:300]
            raise SourceUnavailable(
                f"`garmin-connect {' '.join(args)}` failed (exit {res.returncode}): {detail}"
            )
        try:
            return json.loads(res.stdout) if res.stdout.strip() else {}
        except ValueError as exc:
            raise SourceUnavailable(
                f"`garmin-connect {' '.join(args)}` returned non-JSON output: {exc}"
            ) from exc
