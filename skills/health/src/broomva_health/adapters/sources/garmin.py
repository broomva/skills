"""Garmin Connect trace source adapter.

Built on `garminconnect >= 0.3.3` (PyPI package; GitHub repo is
`cyberjunky/python-garminconnect`; 0.3.3 is the current latest — there is
no 0.3.4). May 2026 substrate — the upstream `matin/garth` was deprecated
2026-03-28 after Cloudflare's WAF killed the mobile-SSO endpoint. Auth
contract: `Garmin(prompt_mfa=...).login(tokenstore=<dir>) -> (needs_mfa, _)`;
the library (via its inner garth client's `dump(dir)`) persists garth's
**two-file** format — `oauth1_token.json` + `oauth2_token.json` — into the
tokenstore dir (NOT a single `garmin_tokens.json`; that assumption was the
BRO-1552 false-negative). The library wraps Garmin's web API with
`curl_cffi` Chrome-TLS impersonation; we wrap *that* with the TraceSource
protocol so the rest of the codebase sees a stable interface even as the
upstream library churns.

Discipline:

- Every public method acquires from the rate limiter BEFORE any network I/O.
- Tokens are persisted by the library itself into the tokenstore dir as garth's
  `oauth1_token.json` + `oauth2_token.json`; `_read_persisted_tokens` validates
  that two-file format (falling back to the legacy `garmin_tokens.json`). The
  default `native` backend speaks the same two-file format directly.
- Library exceptions never escape — they map to domain `HealthError` subtypes
  (`AuthRequired`, `MFANeeded`, `RateLimited`, `SourceUnavailable`).
- The `garminconnect` import is lazy: tests inject a `client_factory` and
  never need the real library on the path.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from broomva_health.config.paths import HealthPaths
from broomva_health.domain.device import Device
from broomva_health.domain.errors import (
    AuthRequired,
    MFANeeded,
    RateLimited,
    SourceUnavailable,
)
from broomva_health.domain.metrics import MetricCode, canonical_unit
from broomva_health.domain.results import (
    BackfillResult,
    SourceStatus,
    SyncResult,
    TokenBundle,
)
from broomva_health.domain.samples import (
    CategorySample,
    CorrelationSample,  # noqa: F401 — re-export for downstream symmetry
    QuantitySample,
)
from broomva_health.domain.source import Source
from broomva_health.domain.time import ensure_utc, utc_now
from broomva_health.domain.workout import Workout
from broomva_health.ports.mfa import MFAProvider
from broomva_health.ports.rate_limiter import RateLimiter
from broomva_health.ports.repository import TraceRepository
from broomva_health.ports.token_store import TokenStore

__all__ = ["GarminTraceSource"]

logger = logging.getLogger(__name__)

_RATE_LIMIT_KEY = "garmin:sync"
_DEFAULT_429_RETRY_AFTER_S = 900.0  # 15 min — matches min_interval setpoint
_GARMIN_DEVICE_MANUFACTURER = "garmin"
_GARMIN_LIB_TOKEN_FILE = "garmin_tokens.json"  # legacy single-file (rare/older builds)
_GARTH_OAUTH2_FILE = "oauth2_token.json"  # garth's actual dump format (oauth1 + oauth2)

# Auth-retry guard. Garmin 429s are account+IP-scoped and *compound* with every
# retry (see References/rate-limit-discipline.md — observed 48-72h lockouts).
# After a failed `auth login` we refuse re-auth for a cooldown window so the
# skill can't amplify a lockout the way a human hammering the command does.
_AUTH_COOLDOWN_FILE = "garmin_auth_cooldown.json"
_AUTH_COOLDOWN_FAIL_S = 60.0  # generic failed auth — short breather
_AUTH_COOLDOWN_429_S = 900.0  # detected 429 — full rate-limit window
_AUTH_COOLDOWN_WALL_S = 21600.0  # 6h — ACCOUNT_LOCKED / CAPTCHA need human browser action

# Garmin escalates repeated failed logins from 429 → account-lock / CAPTCHA.
# These are hard walls: NO headless client can clear them — they require an
# interactive browser login at connect.garmin.com (a password reset also
# clears them). We classify them so the CLI gives an actionable message
# instead of dumping the library's raw responseStatus dict.
_LOGIN_WALL_SIGNATURES: dict[str, tuple[str, ...]] = {
    "captcha": ("CAPTCHA_REQUIRED",),
    "account_locked": ("ACCOUNT_LOCKED", "generalLoginAccountLocked"),
}

# A real garmin_tokens.json carries base64 OAuth1/OAuth2 material (hundreds of
# bytes). Anything shorter (0 bytes, whitespace, "{}") means login returned
# without actually obtaining tokens — the live-dogfood false-positive mode.
_MIN_TOKEN_BYTES = 50


# ---------- Library wiring (lazy) ----------


def _default_client_factory() -> Any:
    """Return the real `garminconnect.Garmin` class, lazily imported.

    Wrapping the import so the unit-test path can construct this module
    without `garminconnect` installed.
    """
    try:
        import garminconnect
    except ImportError as exc:  # pragma: no cover — branch only when lib missing in prod
        raise SourceUnavailable(
            "garminconnect is not installed; "
            "run `pip install '.[garmin]'` from skills/Health/ "
            "(PyPI: garminconnect; GitHub: cyberjunky/python-garminconnect)"
        ) from exc
    return garminconnect.Garmin


def _is_auth_exception(exc: BaseException) -> bool:
    """True if exc is the library's auth-rejection exception (lazy-import safe)."""
    try:
        import garminconnect
    except ImportError:
        return False
    auth_exc = getattr(garminconnect, "GarminConnectAuthenticationError", None)
    return auth_exc is not None and isinstance(exc, auth_exc)


def _tokens_look_valid(raw: bytes | None) -> bool:
    """True only if `raw` looks like real persisted Garmin tokens.

    Guards the live-dogfood false-positive: garminconnect's `login()` can
    return `(None, None)` ("clean success") yet write an empty/`{}` token file
    when a 429 left a half-session. A genuine token file is substantial JSON.
    """
    if not raw:
        return False
    text = raw.decode("utf-8", "replace").strip()
    if len(text) < _MIN_TOKEN_BYTES:
        return False
    try:
        data = json.loads(text)
    except ValueError:
        return True  # substantial non-JSON blob — opaque but present
    return bool(data)  # non-empty dict/list/str


def _is_rate_limit_error(exc: BaseException) -> bool:
    """429 may surface as an HTTPError with .response OR only in the message
    (garminconnect logs '... returned 429 ...' then raises a generic auth error)."""
    if _http_status(exc) == 429:
        return True
    return "429" in str(exc) or "rate limit" in str(exc).lower()


def _login_wall_reason(exc: BaseException) -> str | None:
    """Classify a hard login wall (CAPTCHA / account-lock) from the exc message.

    garminconnect raises a GarminConnectConnectionError whose str() embeds the
    portal `responseStatus` dict (e.g. `{'type': 'CAPTCHA_REQUIRED'}`). These
    states cannot be cleared headlessly — only by an interactive browser login.
    """
    msg = str(exc)
    for reason, signatures in _LOGIN_WALL_SIGNATURES.items():
        if any(sig in msg for sig in signatures):
            return reason
    return None


def _http_status(exc: BaseException) -> int | None:
    """Extract an HTTP status code from a `requests.HTTPError`-shaped exception."""
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) if response is not None else None


# ---------- The adapter ----------


class GarminTraceSource:
    """TraceSource implementation backed by `garminconnect` (PyPI)."""

    def __init__(
        self,
        *,
        paths: HealthPaths,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._paths = paths
        # Defer the real-library import until first use — keeps construction
        # cheap and lets tests inject `client_factory` without needing
        # `garminconnect` on the path.
        self._client_factory_override = client_factory

    @property
    def _client_factory(self) -> Callable[..., Any]:
        if self._client_factory_override is not None:
            return self._client_factory_override
        return _default_client_factory()

    # --- TraceSource interface ---

    @property
    def name(self) -> Source:
        return Source.GARMIN

    def authenticate(
        self,
        *,
        token_store: TokenStore,
        mfa: MFAProvider,
        email: str | None = None,
        password: str | None = None,
        profile: str = "default",
    ) -> None:
        if email is None or password is None:
            raise AuthRequired(
                "Garmin authentication requires both email and password",
                profile=profile,
            )

        # Refuse re-auth while a prior failure's cooldown is active — hammering
        # `auth login` only extends Garmin's account-scoped 429 lockout.
        self._guard_auth_cooldown()

        # The library accepts a `prompt_mfa` callable invoked when the account
        # is challenged (TOTP / authenticator app). Constructor-passing is the
        # correct shape for garminconnect ≥ 0.3.
        def _prompt_mfa() -> str:
            return mfa.prompt(str(Source.GARMIN))

        token_dir = self._token_dir(token_store, profile)
        token_dir.mkdir(parents=True, exist_ok=True)

        client = self._client_factory(
            email=email, password=password, prompt_mfa=_prompt_mfa
        )

        # Pass `tokenstore` so the library persists tokens ITSELF via its inner
        # `client.dump(dir)` (writes garmin_tokens.json). garminconnect ≥ 0.3 has
        # no `dump_tokens`/`garth_dump` on the Garmin object — the previous code
        # called those non-existent methods and silently persisted nothing.
        try:
            result = client.login(tokenstore=str(token_dir))
        except TypeError:
            # Older shape without the `tokenstore` kwarg — fall back to bare login.
            try:
                result = client.login()
            except Exception as exc:
                self._record_auth_failure(exc)
                self._raise_mapped(exc, op="authenticate")
                raise  # unreachable; _raise_mapped always raises
        except Exception as exc:  # mapped to a domain error below
            self._record_auth_failure(exc)
            self._raise_mapped(exc, op="authenticate")
            raise  # unreachable; _raise_mapped always raises

        # login() -> (needs_mfa, _); (None, None) is a clean success. A truthy
        # first element means a deferred MFA challenge we can't satisfy here.
        needs_mfa = result[0] if isinstance(result, (tuple, list)) and result else None
        if needs_mfa:
            raise MFANeeded(
                "Garmin returned an MFA challenge that wasn't satisfied; "
                "re-run `health auth login` and enter the code when prompted.",
                profile=profile,
            )

        # CRITICAL: login() can return success WITHOUT writing real tokens when
        # a 429 leaves a half-session (the live-dogfood false-positive). Verify
        # the library actually persisted substantial token material before we
        # declare success — otherwise raise so the user sees the real failure.
        try:
            raw = self._read_persisted_tokens(token_dir)
        except AuthRequired:
            # A success-without-tokens result is almost always a silent 429 —
            # set a cooldown so a reflexive retry can't amplify the lockout.
            self._record_auth_failure()
            raise

        bundle = TokenBundle(
            source=Source.GARMIN,
            profile=profile,
            raw_bytes=raw,
            stored_at=utc_now(),
            expires_at=None,
        )
        token_store.put(bundle)
        self._clear_auth_cooldown()  # success — wipe any prior cooldown marker

    def sync(
        self,
        *,
        repo: TraceRepository,
        token_store: TokenStore,
        rate_limiter: RateLimiter,
        since: datetime | None = None,  # noqa: ARG002 — incremental key is today-only for v1
        profile: str = "default",
    ) -> SyncResult:
        started_at = utc_now()
        errors: list[str] = []
        samples_count = 0
        workouts_count = 0

        rate_limiter.acquire(_RATE_LIMIT_KEY)

        bundle = token_store.get(Source.GARMIN, profile)
        if bundle is None:
            raise AuthRequired(
                "no Garmin token bundle on disk; run `health auth login garmin`",
                profile=profile,
            )

        client = self._restore_client(token_store, profile)

        today = date.today()
        device = self._default_device()

        # ----- daily summary metrics -----
        quantity_samples: list[QuantitySample] = []
        category_samples: list[CategorySample] = []

        # stats: steps, active_kcal, resting_heart_rate, stress, body_battery
        stats = self._safe_call(
            client.get_stats, today, op="get_stats",
            rate_limiter=rate_limiter, errors=errors,
        )
        if isinstance(stats, dict):
            quantity_samples.extend(
                _stats_to_samples(stats, today, device=device)
            )

        # sleep: SLEEP_STAGE (category, per phase), SLEEP_DURATION, SLEEP_SCORE
        sleep = self._safe_call(
            client.get_sleep_data, today, op="get_sleep_data",
            rate_limiter=rate_limiter, errors=errors,
        )
        if isinstance(sleep, dict):
            q, c = _sleep_to_samples(sleep, today, device=device)
            quantity_samples.extend(q)
            category_samples.extend(c)

        # hrv: HRV_OVERNIGHT
        hrv = self._safe_call(
            client.get_hrv_data, today, op="get_hrv_data",
            rate_limiter=rate_limiter, errors=errors,
        )
        if isinstance(hrv, dict):
            quantity_samples.extend(_hrv_to_samples(hrv, today, device=device))

        # training readiness
        tr = self._safe_call(
            client.get_training_readiness, today, op="get_training_readiness",
            rate_limiter=rate_limiter, errors=errors,
        )
        if tr is not None:
            quantity_samples.extend(
                _training_readiness_to_samples(tr, today, device=device)
            )

        # vo2max
        vo2 = self._safe_call(
            client.get_max_metrics, today, op="get_max_metrics",
            rate_limiter=rate_limiter, errors=errors,
        )
        if vo2 is not None:
            quantity_samples.extend(_vo2_to_samples(vo2, today, device=device))

        # activities: last 10
        acts = self._safe_call(
            client.get_activities, 0, 10, op="get_activities",
            rate_limiter=rate_limiter, errors=errors,
        )
        workouts: list[Workout] = []
        if isinstance(acts, list):
            workouts.extend(_activities_to_workouts(acts, device=device))

        # ----- persist -----
        if quantity_samples:
            samples_count += repo.upsert_quantity(quantity_samples)
        if category_samples:
            samples_count += repo.upsert_category(category_samples)
        if workouts:
            workouts_count += repo.upsert_workout(workouts)

        rate_limiter.record_success(_RATE_LIMIT_KEY)

        finished_at = utc_now()
        return SyncResult(
            source=Source.GARMIN,
            started_at=started_at,
            finished_at=finished_at,
            samples_ingested=samples_count,
            workouts_ingested=workouts_count,
            errors=errors,
            rate_limit_remaining_s=None,
        )

    def backfill(
        self,
        *,
        repo: TraceRepository,
        token_store: TokenStore,
        rate_limiter: RateLimiter,
        start: date,
        end: date,
        profile: str = "default",
    ) -> BackfillResult:
        if end < start:
            raise SourceUnavailable(
                f"backfill end ({end.isoformat()}) precedes start ({start.isoformat()})"
            )

        bundle = token_store.get(Source.GARMIN, profile)
        if bundle is None:
            raise AuthRequired(
                "no Garmin token bundle on disk; run `health auth login garmin`",
                profile=profile,
            )

        client = self._restore_client(token_store, profile)
        device = self._default_device()
        errors: list[str] = []
        samples_total = 0
        workouts_total = 0

        # Per-day pulls: acquire the rate limiter between each day so the
        # 15-min spacing setpoint is honored — even on dense backfills.
        current = start
        while current <= end:
            rate_limiter.acquire(_RATE_LIMIT_KEY)

            quantity_samples: list[QuantitySample] = []
            category_samples: list[CategorySample] = []

            stats = self._safe_call(
                client.get_stats, current, op=f"get_stats[{current.isoformat()}]",
                rate_limiter=rate_limiter, errors=errors,
            )
            if isinstance(stats, dict):
                quantity_samples.extend(_stats_to_samples(stats, current, device=device))

            sleep = self._safe_call(
                client.get_sleep_data, current, op=f"get_sleep_data[{current.isoformat()}]",
                rate_limiter=rate_limiter, errors=errors,
            )
            if isinstance(sleep, dict):
                q, c = _sleep_to_samples(sleep, current, device=device)
                quantity_samples.extend(q)
                category_samples.extend(c)

            hrv = self._safe_call(
                client.get_hrv_data, current, op=f"get_hrv_data[{current.isoformat()}]",
                rate_limiter=rate_limiter, errors=errors,
            )
            if isinstance(hrv, dict):
                quantity_samples.extend(_hrv_to_samples(hrv, current, device=device))

            tr = self._safe_call(
                client.get_training_readiness, current,
                op=f"get_training_readiness[{current.isoformat()}]",
                rate_limiter=rate_limiter, errors=errors,
            )
            if tr is not None:
                quantity_samples.extend(
                    _training_readiness_to_samples(tr, current, device=device)
                )

            vo2 = self._safe_call(
                client.get_max_metrics, current,
                op=f"get_max_metrics[{current.isoformat()}]",
                rate_limiter=rate_limiter, errors=errors,
            )
            if vo2 is not None:
                quantity_samples.extend(_vo2_to_samples(vo2, current, device=device))

            if quantity_samples:
                samples_total += repo.upsert_quantity(quantity_samples)
            if category_samples:
                samples_total += repo.upsert_category(category_samples)

            rate_limiter.record_success(_RATE_LIMIT_KEY)
            current = current + timedelta(days=1)

        # Activities: bulk call once per chunk (limit=200) — Garmin returns
        # activity start dates so we filter to the requested window.
        rate_limiter.acquire(_RATE_LIMIT_KEY)
        acts = self._safe_call(
            client.get_activities, 0, 200, op="get_activities[backfill]",
            rate_limiter=rate_limiter, errors=errors,
        )
        if isinstance(acts, list):
            workouts = [
                w
                for w in _activities_to_workouts(acts, device=device)
                if start <= w.start_ts.date() <= end
            ]
            if workouts:
                workouts_total += repo.upsert_workout(workouts)
        rate_limiter.record_success(_RATE_LIMIT_KEY)

        return BackfillResult(
            source=Source.GARMIN,
            range_start=start,
            range_end=end,
            samples_ingested=samples_total,
            workouts_ingested=workouts_total,
            errors=errors,
        )

    def status(
        self, *, token_store: TokenStore, profile: str = "default"
    ) -> SourceStatus:
        # NO network — P15-reflex path. The CLI cross-references last_sync
        # against the repository separately.
        bundle = token_store.get(Source.GARMIN, profile)
        # token_valid is VALIDITY, not mere presence — an empty/half-written
        # bundle (the 429 false-positive) must report invalid so the user
        # isn't told they're authenticated when sync will fail.
        valid = bundle is not None and _tokens_look_valid(bundle.raw_bytes)
        return SourceStatus(
            source=Source.GARMIN,
            last_sync=None,
            last_error=None,
            rate_limit_resets_at=None,
            token_valid=valid,
            token_expires_at=bundle.expires_at if bundle is not None else None,
        )

    # --- internals ---

    def _safe_call(
        self,
        fn: Callable[..., Any],
        /,
        *args: Any,
        op: str,
        rate_limiter: RateLimiter,
        errors: list[str],
    ) -> Any:
        """Wrap one library call; map exceptions to domain errors.

        RateLimited / AuthRequired / MFANeeded ALWAYS bubble — the caller
        can't continue when the entire session is rate-limited or unauth'd.
        Other library exceptions are logged and added to `errors`, returning
        None so the partial-sync semantic holds (one bad endpoint doesn't
        kill the whole run).
        """
        try:
            return fn(*args)
        except (RateLimited, AuthRequired, MFANeeded):
            # Domain errors raised by the fake client / library wrapper —
            # let them bubble. The rate-limiter already knows about a 429.
            raise
        except Exception as exc:
            status = _http_status(exc)
            if status == 429:
                rate_limiter.record_429(_RATE_LIMIT_KEY, retry_after_s=_DEFAULT_429_RETRY_AFTER_S)
                raise RateLimited(
                    f"Garmin rate-limited on {op}", retry_after_s=_DEFAULT_429_RETRY_AFTER_S
                ) from exc
            if status in (401, 403) or _is_auth_exception(exc):
                raise AuthRequired(
                    f"Garmin auth rejected on {op}", op=op
                ) from exc
            # Non-fatal: log + add to errors, return None so the caller can
            # continue partial-sync.
            logger.warning("Garmin %s failed: %s", op, exc)
            errors.append(f"{op}: {type(exc).__name__}: {exc}")
            return None

    def _raise_mapped(self, exc: BaseException, *, op: str) -> None:
        """Translate a library exception into a HealthError. Always raises."""
        status = _http_status(exc)
        if status == 429:
            raise RateLimited(
                f"Garmin rate-limited on {op}",
                retry_after_s=_DEFAULT_429_RETRY_AFTER_S,
            ) from exc
        if status in (401, 403) or _is_auth_exception(exc):
            raise AuthRequired(f"Garmin auth rejected on {op}", op=op) from exc
        if isinstance(exc, MFANeeded):
            raise
        wall = _login_wall_reason(exc)
        if wall == "captcha":
            raise AuthRequired(
                "Garmin is demanding a CAPTCHA — NO command-line tool can solve one. "
                "Your account has been flagged by repeated login attempts. To clear it: "
                "open https://connect.garmin.com in a real browser, log in and solve the "
                "CAPTCHA (a password reset also clears the flag), then wait several hours "
                "before `health auth login`. Repeated CLI attempts only prolong this.",
                op=op,
                wall="captcha",
            ) from exc
        if wall == "account_locked":
            raise AuthRequired(
                "Garmin has LOCKED this account after too many failed logins. "
                "Open https://connect.garmin.com in a real browser and log in (or reset "
                "your password) to unlock it, then wait several hours before retrying. "
                "Do not keep running `health auth login` — each attempt extends the lock.",
                op=op,
                wall="account_locked",
            ) from exc
        raise SourceUnavailable(
            f"Garmin call {op} failed: {type(exc).__name__}: {exc}", op=op
        ) from exc

    def _token_dir(self, token_store: TokenStore, profile: str) -> Any:
        """Use the FilesystemTokenStore's exposed `profile_dir` if present."""
        if hasattr(token_store, "profile_dir"):
            return token_store.profile_dir(Source.GARMIN, profile)
        # fallback to HealthPaths layout
        return self._paths.tokens_dir / str(Source.GARMIN) / profile

    def _restore_client(self, token_store: TokenStore, profile: str) -> Any:
        """Build a logged-in client by handing the library our token dir."""
        token_dir = self._token_dir(token_store, profile)
        client = self._client_factory()
        try:
            client.login(tokenstore=str(token_dir))
        except TypeError:
            # Older library shape — `login(<dir>)`
            try:
                client.login(str(token_dir))
            except Exception as exc:
                self._raise_mapped(exc, op="restore_login")
                raise
        except Exception as exc:
            self._raise_mapped(exc, op="restore_login")
            raise
        return client

    def _read_persisted_tokens(self, token_dir: Any) -> bytes:
        """Read + validate the token material the library persisted via `login(tokenstore=)`.

        garminconnect ≥ 0.3 wraps garth, whose `dump(dir)` writes the **two-file**
        format `oauth1_token.json` + `oauth2_token.json` — NOT a single
        `garmin_tokens.json` (the original assumption here; BRO-1552). Accept the
        garth files first, fall back to the legacy single-file for any older
        library build that still emits it. The default `native` backend already
        speaks this two-file format directly; this keeps the deprecated `library`
        backend from false-failing a real login.

        Raises `AuthRequired` if no token material is present or it doesn't look
        real — the explicit guard against the false-positive where `login()`
        reports success but a 429 prevented real tokens from landing.
        """
        garth_oauth2 = token_dir / _GARTH_OAUTH2_FILE
        legacy = token_dir / _GARMIN_LIB_TOKEN_FILE
        # Prefer garth's two-file format; fall back to the legacy single file
        # when garth's is absent *or* unreadable/invalid (not just absent).
        for candidate in (garth_oauth2, legacy):
            raw = candidate.read_bytes() if candidate.exists() else b""
            if _tokens_look_valid(raw):
                return raw
        raise AuthRequired(
            "Garmin login returned but no valid tokens were written "
            f"({garth_oauth2} / {legacy} missing or empty). This is almost always a "
            "429 rate-limit that returned without raising. Do NOT retry "
            "immediately — each attempt extends Garmin's account lockout. "
            "Wait for it to clear (often hours), then `health auth login` once.",
            token_file=str(garth_oauth2),
        )

    # --- auth-retry cooldown (anti-amplification) ---

    def _auth_cooldown_path(self) -> Any:
        return self._paths.config_dir / _AUTH_COOLDOWN_FILE

    def _guard_auth_cooldown(self) -> None:
        """Raise RateLimited if a prior failed auth set a still-active cooldown."""
        path = self._auth_cooldown_path()
        if not path.exists():
            return
        try:
            until = ensure_utc(datetime.fromisoformat(json.loads(path.read_text())["until"]))
        except (OSError, ValueError, KeyError, TypeError):
            return  # unreadable marker — don't block on it
        remaining = (until - utc_now()).total_seconds()
        if remaining > 0:
            raise RateLimited(
                f"Garmin auth is cooling down for ~{int(remaining)}s after a recent "
                "failed login. Retrying now only extends Garmin's lockout — wait it out.",
                retry_after_s=float(int(remaining)),
            )

    def _record_auth_failure(self, exc: BaseException | None = None) -> None:
        """Persist a cooldown after a failed auth.

        Escalating windows: a hard wall (account-lock / CAPTCHA) needs human
        browser action so we back off for hours; a 429 gets the rate-limit
        window; anything else a short breather.
        """
        if exc is not None and _login_wall_reason(exc):
            cooldown = _AUTH_COOLDOWN_WALL_S
        elif exc is not None and _is_rate_limit_error(exc):
            cooldown = _AUTH_COOLDOWN_429_S
        else:
            cooldown = _AUTH_COOLDOWN_FAIL_S
        until = utc_now() + timedelta(seconds=cooldown)
        try:
            path = self._auth_cooldown_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"until": until.isoformat()}))
        except OSError as exc2:  # pragma: no cover — best-effort
            logger.debug("Could not write auth cooldown marker: %s", exc2)

    def _clear_auth_cooldown(self) -> None:
        try:
            self._auth_cooldown_path().unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            pass

    def _default_device(self) -> Device:
        return Device(
            manufacturer=_GARMIN_DEVICE_MANUFACTURER,
            product=None,
            hardware_id=None,
            software_version=None,
        )


# ---------- pure mappers (testable in isolation) ----------


def _day_window(day: date) -> tuple[datetime, datetime]:
    """UTC [00:00, 23:59:59.999999] window for a date."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1, microseconds=-1)
    return start, end


def _q(
    *,
    metric: MetricCode,
    value: float,
    day: date,
    device: Device | None = None,
    metadata: dict[str, Any] | None = None,
) -> QuantitySample:
    start, end = _day_window(day)
    return QuantitySample(
        source=Source.GARMIN,
        device=device,
        start_ts=start,
        end_ts=end,
        metadata=metadata or {},
        ingested_at=utc_now(),
        metric=metric,
        value=float(value),
        unit=canonical_unit(metric),
    )


def _cat(
    *,
    metric: MetricCode,
    category: str,
    start_ts: datetime,
    end_ts: datetime,
    device: Device | None = None,
    metadata: dict[str, Any] | None = None,
) -> CategorySample:
    return CategorySample(
        source=Source.GARMIN,
        device=device,
        start_ts=ensure_utc(start_ts),
        end_ts=ensure_utc(end_ts),
        metadata=metadata or {},
        ingested_at=utc_now(),
        metric=metric,
        category=category,
    )


def _stats_to_samples(
    stats: dict[str, Any], day: date, *, device: Device | None = None
) -> list[QuantitySample]:
    """Map a Garmin daily-stats dict to QuantitySamples.

    The library returns a flat dict with keys like `totalSteps`, `activeKilocalories`,
    `restingHeartRate`, `averageStressLevel`, `bodyBatteryMostRecentValue`. We only
    emit a sample when the value is non-null and >= 0 (Garmin uses -1 sentinels).
    """
    out: list[QuantitySample] = []
    mapping: list[tuple[MetricCode, tuple[str, ...]]] = [
        (MetricCode.STEPS, ("totalSteps",)),
        (MetricCode.ACTIVE_KCAL, ("activeKilocalories", "activeCalories")),
        (MetricCode.RESTING_HEART_RATE, ("restingHeartRate",)),
        (MetricCode.STRESS, ("averageStressLevel", "stressDuration")),
        (
            MetricCode.BODY_BATTERY,
            ("bodyBatteryMostRecentValue", "bodyBatteryHighestValue"),
        ),
    ]
    for metric, candidate_keys in mapping:
        for key in candidate_keys:
            raw = stats.get(key)
            if _valid_number(raw):
                out.append(_q(metric=metric, value=float(raw), day=day, device=device))
                break
    return out


def _sleep_to_samples(
    sleep: dict[str, Any], day: date, *, device: Device | None = None
) -> tuple[list[QuantitySample], list[CategorySample]]:
    """Map a Garmin sleep payload to (QuantitySamples, CategorySamples).

    The library returns a nested dict with `dailySleepDTO` summary + a
    `sleepLevels` list of (startGMT, endGMT, activityLevel) phases.
    """
    q: list[QuantitySample] = []
    c: list[CategorySample] = []

    summary = sleep.get("dailySleepDTO") or {}
    total = summary.get("sleepTimeSeconds") or summary.get("totalSleepSeconds")
    if _valid_number(total):
        q.append(_q(metric=MetricCode.SLEEP_DURATION, value=float(total), day=day, device=device))

    score_block = summary.get("sleepScores") or {}
    overall = score_block.get("overall") if isinstance(score_block, dict) else None
    score_val = overall.get("value") if isinstance(overall, dict) else None
    if _valid_number(score_val):
        q.append(_q(metric=MetricCode.SLEEP_SCORE, value=float(score_val), day=day, device=device))

    levels = sleep.get("sleepLevels") or []
    if isinstance(levels, list):
        for level in levels:
            if not isinstance(level, dict):
                continue
            start_raw = level.get("startGMT") or level.get("startTimeGMT")
            end_raw = level.get("endGMT") or level.get("endTimeGMT")
            activity = level.get("activityLevel")
            if start_raw is None or end_raw is None or activity is None:
                continue
            try:
                start_dt = _parse_garmin_dt(start_raw)
                end_dt = _parse_garmin_dt(end_raw)
            except (ValueError, TypeError):
                continue
            category = _sleep_phase_label(activity)
            if end_dt < start_dt:
                continue
            c.append(
                _cat(
                    metric=MetricCode.SLEEP_STAGE,
                    category=category,
                    start_ts=start_dt,
                    end_ts=end_dt,
                    device=device,
                    metadata={"activityLevel": activity},
                )
            )

    return q, c


def _hrv_to_samples(
    hrv: dict[str, Any], day: date, *, device: Device | None = None
) -> list[QuantitySample]:
    """Map Garmin HRV summary to QuantitySamples.

    The library returns `{"hrvSummary": {"lastNightAvg": 42, ...}, ...}`.
    """
    summary = hrv.get("hrvSummary") if isinstance(hrv.get("hrvSummary"), dict) else hrv
    last_night = summary.get("lastNightAvg") if isinstance(summary, dict) else None
    if _valid_number(last_night):
        return [_q(metric=MetricCode.HRV_OVERNIGHT, value=float(last_night), day=day, device=device)]
    return []


def _training_readiness_to_samples(
    tr: Any, day: date, *, device: Device | None = None
) -> list[QuantitySample]:
    """Map training-readiness payload to QuantitySamples.

    The library returns a list[dict] (one entry per measurement); we use the
    first entry's `score` (0-100).
    """
    record: dict[str, Any] | None = None
    if isinstance(tr, list) and tr:
        first = tr[0]
        if isinstance(first, dict):
            record = first
    elif isinstance(tr, dict):
        record = tr

    if record is None:
        return []
    score = record.get("score")
    if _valid_number(score):
        return [
            _q(
                metric=MetricCode.TRAINING_READINESS,
                value=float(score),
                day=day,
                device=device,
            )
        ]
    return []


def _vo2_to_samples(
    vo2: Any, day: date, *, device: Device | None = None
) -> list[QuantitySample]:
    """Map VO2max payload to QuantitySamples.

    The library returns a list of metric records; the running-flavor's
    `generic.vo2MaxValue` is the canonical user-facing VO2max number.
    """
    record: dict[str, Any] | None = None
    if isinstance(vo2, list) and vo2:
        first = vo2[0]
        if isinstance(first, dict):
            record = first
    elif isinstance(vo2, dict):
        record = vo2

    if record is None:
        return []

    # Try the common shapes the library has produced over its revisions.
    candidates: list[Any] = [
        record.get("vo2MaxValue"),
        (record.get("generic") or {}).get("vo2MaxValue") if isinstance(record.get("generic"), dict) else None,
        (record.get("vo2MaxRunning") or {}).get("vo2MaxValue") if isinstance(record.get("vo2MaxRunning"), dict) else None,
    ]
    for value in candidates:
        if _valid_number(value):
            return [_q(metric=MetricCode.VO2_MAX, value=float(value), day=day, device=device)]
    return []


def _activities_to_workouts(
    acts: list[Any], *, device: Device | None = None
) -> list[Workout]:
    """Map a Garmin activities list to Workouts."""
    out: list[Workout] = []
    for act in acts:
        if not isinstance(act, dict):
            continue
        activity_id = act.get("activityId")
        if activity_id is None:
            continue
        activity_type = act.get("activityType") or {}
        type_key = activity_type.get("typeKey") if isinstance(activity_type, dict) else None
        type_key = type_key or "unknown"

        start_raw = act.get("startTimeGMT") or act.get("startTimeLocal")
        if start_raw is None:
            continue
        try:
            start_dt = _parse_garmin_dt(start_raw)
        except (ValueError, TypeError):
            continue

        duration_raw = act.get("duration") or 0
        duration_s = int(float(duration_raw)) if _valid_number(duration_raw) else 0
        end_dt = start_dt + timedelta(seconds=duration_s) if duration_s else None

        out.append(
            Workout(
                source=Source.GARMIN,
                activity_id=str(activity_id),
                activity_type=str(type_key),
                start_ts=start_dt,
                end_ts=end_dt,
                duration_s=duration_s,
                distance_m=_maybe_float(act.get("distance")),
                kcal=_maybe_float(act.get("calories")),
                avg_hr=_maybe_float(act.get("averageHR")),
                max_hr=_maybe_float(act.get("maxHR")),
                training_effect=_maybe_float(act.get("aerobicTrainingEffect")),
                training_stress_score=_maybe_float(
                    act.get("trainingStressScore") or act.get("tss")
                ),
                device=device,
                fit_blob_sha256=None,
                raw_summary={k: v for k, v in act.items() if not isinstance(v, (bytes, bytearray))},
                ingested_at=utc_now(),
            )
        )
    return out


# ---------- shape helpers ----------


def _valid_number(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value >= 0
    return False


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return None


def _parse_garmin_dt(value: Any) -> datetime:
    """Parse a Garmin GMT timestamp into a UTC-aware datetime.

    Garmin returns multiple shapes:
    - epoch millis (int / float)
    - ISO-8601 string with 'Z' or offset
    - `"2026-05-22 13:00:00"` (naive — assume UTC for *GMT keys)
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # ms epoch
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
    if isinstance(value, str):
        cleaned = value.replace("Z", "+00:00")
        try:
            return ensure_utc(datetime.fromisoformat(cleaned))
        except ValueError:
            # space-separated naive
            return ensure_utc(datetime.strptime(value, "%Y-%m-%d %H:%M:%S"))
    raise TypeError(f"unparseable Garmin datetime: {value!r}")


def _sleep_phase_label(activity_level: Any) -> str:
    """Map Garmin's numeric activityLevel to a category label.

    Garmin's mapping (from public reverse-engineering — May 2026):
      0.0 -> deep
      1.0 -> light
      2.0 -> rem
      3.0 -> awake
    """
    try:
        n = float(activity_level)
    except (TypeError, ValueError):
        return "unknown"
    if n < 0.5:
        return "deep"
    if n < 1.5:
        return "light"
    if n < 2.5:
        return "rem"
    return "awake"
