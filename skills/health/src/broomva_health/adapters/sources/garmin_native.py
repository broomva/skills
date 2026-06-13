"""In-house Garmin source — garth directly, riding an existing token.

This is the **owned** backend: we call Garmin's `connectapi` endpoints
ourselves through ``garth`` (the auth + transport engine, pinned MIT), own the
aggregation + mapping + token lifecycle, and depend on no external binary.

Why garth (and why it works despite the "deprecated" banner)
------------------------------------------------------------
``garth``'s deprecation only affects *fresh* logins (Garmin's Cloudflare SSO
wall). **Riding an existing OAuth1/OAuth2 token still works**: ``garth.resume``
loads the token, the short-lived OAuth2 bearer auto-refreshes off the ~1-year
OAuth1 token via the DI endpoint (not Cloudflare-walled), and ``connectapi``
reads flow normally. This is exactly how eddmann's CLI stays logged in — we
reuse the same flow and the same token, in our own code.

Token bootstrap: ``health auth import`` copies an existing garth token
(``oauth1_token.json`` + ``oauth2_token.json``, e.g. from
``~/.config/garmin-connect-cli/tokens/``) into our store. From then on we own
it — ``garth.save`` persists refreshes.

Fork-escape-hatch: garth is unmaintained; if it ever vanishes from PyPI, vendor
it (it is small + MIT). When the OAuth1 token eventually expires (~1 year), a
fresh login is required — use the `library` (maintained garminconnect/diauth)
or `browser` (Interceptor) backend for that re-auth, then import again.

Endpoints (verified live against connectapi):
- /usersummary-service/usersummary/daily?calendarDate=DATE
- /sleep-service/sleep/dailySleepData?date=DATE&nonSleepBufferMinutes=60
- /hrv-service/hrv/DATE
- /wellness-service/wellness/bodyBattery/reports/daily?startDate=DATE&endDate=DATE
- /metrics-service/metrics/maxmet/latest/DATE   (VO2max)
- /metrics-service/metrics/trainingreadiness/DATE
- /activitylist-service/activities/search/activities?limit=N&start=0
"""

from __future__ import annotations

import logging
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from broomva_health.adapters.sources._mapping import map_context
from broomva_health.config.paths import HealthPaths
from broomva_health.domain.errors import AuthRequired, SourceUnavailable
from broomva_health.domain.results import BackfillResult, SourceStatus, SyncResult
from broomva_health.domain.source import Source
from broomva_health.domain.time import utc_now
from broomva_health.ports.mfa import MFAProvider
from broomva_health.ports.rate_limiter import RateLimiter
from broomva_health.ports.repository import TraceRepository
from broomva_health.ports.token_store import TokenStore

__all__ = ["GarminNativeTraceSource"]

logger = logging.getLogger(__name__)

_RATE_LIMIT_KEY = "garmin:native:sync"
_TOKEN_SUBDIR = "garmin-garth"
_TOKEN_FILES = ("oauth1_token.json", "oauth2_token.json")
_DEFAULT_IMPORT_DIR = "~/.config/garmin-connect-cli/tokens"
_ACTIVITY_LIMIT = 10


def _local_today() -> date:
    """The user's local calendar date — Garmin keys daily data by it, not UTC."""
    return datetime.now().astimezone().date()


class GarminNativeTraceSource:
    """In-house ``TraceSource`` backed by garth + the user's existing token."""

    #: `health auth login` skips the password prompt — this backend authenticates
    #: by importing an existing token, never by collecting credentials.
    delegated_auth: bool = True

    def __init__(
        self,
        *,
        paths: HealthPaths,
        garth_module: Any | None = None,
    ) -> None:
        self._paths = paths
        self._garth_override = garth_module

    @property
    def name(self) -> Source:
        return Source.GARMIN

    # --- TraceSource interface -------------------------------------------

    def authenticate(
        self,
        *,
        token_store: TokenStore,  # noqa: ARG002 — garth owns its token files
        mfa: MFAProvider,  # noqa: ARG002 — no interactive MFA on the token-ride path
        email: str | None = None,  # noqa: ARG002 — never collected
        password: str | None = None,  # noqa: ARG002 — never collected
        profile: str = "default",
    ) -> None:
        """Validate the imported token; instruct `auth import` if none exists."""
        if not self._has_token(profile):
            raise AuthRequired(
                "The native Garmin backend authenticates from an imported token. "
                "Run `health auth import` to copy your existing garmin-connect "
                "token (no password needed), then retry. To mint a fresh token "
                "first, use `garmin-connect auth login` or the `library` backend.",
            )
        self._resume(profile)  # raises AuthRequired if the token won't load

    def sync(
        self,
        *,
        repo: TraceRepository,
        token_store: TokenStore,  # noqa: ARG002
        rate_limiter: RateLimiter,
        since: datetime | None = None,  # noqa: ARG002 — today-only snapshot
        profile: str = "default",
    ) -> SyncResult:
        """Pull today's snapshot via connectapi and upsert into the trace DB."""
        started = utc_now()
        rate_limiter.acquire(_RATE_LIMIT_KEY)
        g = self._resume(profile)
        # Garmin keys "daily" data by the user's LOCAL calendar date, not UTC.
        # Using utc_now().date() asks for the wrong day for any user behind UTC
        # in the evening (e.g. UTC-5 after 19:00 → tomorrow's empty day).
        ctx = self._fetch_context(g, _local_today().isoformat())
        quantities, workouts = map_context(ctx, now=utc_now())
        n_q = repo.upsert_quantity(quantities) if quantities else 0
        n_w = repo.upsert_workout(workouts) if workouts else 0
        self._save(g, profile)
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
        repo: TraceRepository,
        token_store: TokenStore,  # noqa: ARG002
        rate_limiter: RateLimiter,
        start: date,
        end: date,
        profile: str = "default",
    ) -> BackfillResult:
        """Historical pull, one calendar day at a time (rate-limited per day)."""
        if end < start:
            raise SourceUnavailable(
                f"backfill end ({end.isoformat()}) precedes start ({start.isoformat()})"
            )
        g = self._resume(profile)
        n_q = n_w = 0
        errors: list[str] = []
        cur = start
        while cur <= end:
            rate_limiter.acquire(_RATE_LIMIT_KEY)
            try:
                ctx = self._fetch_context(g, cur.isoformat())
                q, w = map_context(ctx, now=utc_now())
                n_q += repo.upsert_quantity(q) if q else 0
                n_w += repo.upsert_workout(w) if w else 0
            except Exception as exc:  # one bad day shouldn't kill the run
                logger.warning("native backfill failed for %s: %s", cur, exc)
                errors.append(f"{cur.isoformat()}: {type(exc).__name__}: {exc}")
            cur += timedelta(days=1)
        self._save(g, profile)
        return BackfillResult(
            source=Source.GARMIN,
            range_start=start,
            range_end=end,
            samples_ingested=n_q,
            workouts_ingested=n_w,
            errors=errors,
        )

    def status(
        self,
        *,
        token_store: TokenStore,  # noqa: ARG002
        profile: str = "default",
    ) -> SourceStatus:
        """Reflexive snapshot — never raises; reports imported-token validity."""
        valid = False
        last_error: str | None = None
        if self._has_token(profile):
            try:
                g = self._resume(profile)
                valid = bool(getattr(g.client, "username", None))
            except (AuthRequired, SourceUnavailable) as exc:
                last_error = str(exc)[:200]
        return SourceStatus(
            source=Source.GARMIN,
            last_sync=None,
            last_error=last_error,
            rate_limit_resets_at=None,
            token_valid=valid,
            token_expires_at=None,
        )

    # --- token import (called by `health auth import`) -------------------

    def import_tokens(self, *, from_dir: str | None = None, profile: str = "default") -> int:
        """Copy an existing garth token (oauth1+oauth2) into our store + verify.

        Returns the number of token files imported (2 on success). Raises
        ``SourceUnavailable`` if the source files are missing, ``AuthRequired``
        if the imported token won't load.
        """
        src = Path(from_dir or _DEFAULT_IMPORT_DIR).expanduser()
        dst = self._token_dir(profile)
        dst.mkdir(parents=True, exist_ok=True)
        copied = 0
        for fname in _TOKEN_FILES:
            s = src / fname
            if not s.exists():
                raise SourceUnavailable(
                    f"token file not found: {s}. Point --from at a directory "
                    "containing oauth1_token.json + oauth2_token.json (e.g. "
                    "~/.config/garmin-connect-cli/tokens after `garmin-connect auth login`).",
                )
            shutil.copy2(s, dst / fname)
            try:
                (dst / fname).chmod(0o600)
            except OSError:  # pragma: no cover
                pass
            copied += 1
        # Verify the imported token actually loads.
        try:
            g = self._garth()
            g.resume(str(dst))
            _ = g.client.username
        except Exception as exc:
            raise AuthRequired(
                f"imported tokens failed to load: {exc}. The source token may be "
                "expired — re-run `garmin-connect auth login` and import again.",
            ) from exc
        return copied

    # --- internals --------------------------------------------------------

    def _garth(self) -> Any:
        if self._garth_override is not None:
            return self._garth_override
        try:
            import garth
        except ImportError as exc:  # pragma: no cover — garth is a core dep
            raise SourceUnavailable(
                "garth is not installed; it is a core dependency of broomva-health. "
                "Reinstall with `pip install -e .` from skills/health/.",
            ) from exc
        return garth

    def _token_dir(self, profile: str) -> Path:
        return self._paths.tokens_dir / _TOKEN_SUBDIR / profile

    def _has_token(self, profile: str) -> bool:
        tdir = self._token_dir(profile)
        return all((tdir / f).exists() for f in _TOKEN_FILES)

    def _resume(self, profile: str) -> Any:
        if not self._has_token(profile):
            raise AuthRequired(
                "No Garmin token for the native backend. Run `health auth import`.",
            )
        g = self._garth()
        try:
            g.resume(str(self._token_dir(profile)))
        except Exception as exc:
            raise AuthRequired(
                f"Garmin token failed to load/refresh: {exc}. Re-import "
                "(`health auth import`) or re-auth via the library/browser backend.",
            ) from exc
        return g

    def _save(self, g: Any, profile: str) -> None:
        """Persist refreshed tokens (best-effort — a failed save isn't fatal)."""
        try:
            g.save(str(self._token_dir(profile)))
        except Exception as exc:  # pragma: no cover
            logger.warning("garth token save failed: %s", exc)

    @staticmethod
    def _norm_activity(act: dict[str, Any]) -> dict[str, Any]:
        """Flatten garth's ``activityType`` dict to the typeKey string."""
        at = act.get("activityType")
        type_key = at.get("typeKey") if isinstance(at, dict) else at
        return {**act, "activityType": type_key}

    def _fetch_context(self, g: Any, date_iso: str) -> dict[str, Any]:
        """Call the connectapi endpoints and normalize to the shared context shape.

        Each endpoint is partial-tolerant: a failure logs + yields an empty
        section rather than killing the whole pull.
        """

        def call(path: str) -> Any:
            try:
                return g.connectapi(path)
            except Exception as exc:
                logger.warning("connectapi %s failed: %s", path.split("?", maxsplit=1)[0], exc)
                return None

        daily = call(f"/usersummary-service/usersummary/daily?calendarDate={date_iso}") or {}
        sleep = (
            call(f"/sleep-service/sleep/dailySleepData?date={date_iso}&nonSleepBufferMinutes=60")
            or {}
        )
        hrv = call(f"/hrv-service/hrv/{date_iso}") or {}
        bb = (
            call(
                "/wellness-service/wellness/bodyBattery/reports/daily?"
                f"startDate={date_iso}&endDate={date_iso}"
            )
            or []
        )
        vo2 = call(f"/metrics-service/metrics/maxmet/latest/{date_iso}") or {}
        readiness = call(f"/metrics-service/metrics/trainingreadiness/{date_iso}") or []
        acts = (
            call(f"/activitylist-service/activities/search/activities?limit={_ACTIVITY_LIMIT}&start=0")
            or []
        )
        stress = call(f"/wellness-service/wellness/dailyStress/{date_iso}") or {}
        spo2 = call(f"/wellness-service/wellness/daily/spo2/{date_iso}") or {}
        respiration = call(f"/wellness-service/wellness/daily/respiration/{date_iso}") or {}
        weight = call(f"/weight-service/weight/dayview/{date_iso}") or {}
        hydration = call(f"/usersummary-service/usersummary/hydration/allData/{date_iso}") or {}

        bb0 = bb[0] if isinstance(bb, list) and bb else {}
        rdy0 = readiness[0] if isinstance(readiness, list) and readiness else {}
        sleep_dto = (sleep.get("dailySleepDTO") or {}) if isinstance(sleep, dict) else {}
        sleep_score = ((sleep_dto.get("sleepScores") or {}).get("overall") or {}).get("value")
        w_avg = (weight.get("totalAverage") or {}) if isinstance(weight, dict) else {}

        def g_to_kg(grams: Any) -> float | None:
            return grams / 1000.0 if isinstance(grams, (int, float)) else None

        return {
            "today_stats": {**daily, "floorsClimbed": daily.get("floorsAscended")},
            "health": {
                "heart_rate": {"resting": daily.get("restingHeartRate")},
                "sleep": {**sleep_dto, "sleepScore": sleep_score},
                "body_battery": bb0 if isinstance(bb0, dict) else {},
                "hrv": {"lastNightAvg": (hrv.get("hrvSummary") or {}).get("lastNightAvg")},
                "stress": {"overallStressLevel": stress.get("avgStressLevel")},
                "spo2": {"average": spo2.get("averageSpO2")},
                "respiration": {"avgWaking": respiration.get("avgWakingRespirationValue")},
                "hydration": {"ml": hydration.get("valueInML")},
            },
            "training": {
                "readiness": rdy0.get("score") if isinstance(rdy0, dict) else None,
                "vo2max": (vo2.get("generic") or {}).get("vo2MaxValue")
                if isinstance(vo2, dict)
                else None,
            },
            "weight": {
                "current_kg": g_to_kg(w_avg.get("weight")),
                "bmi": w_avg.get("bmi"),
                "body_fat_pct": w_avg.get("bodyFat"),
                "lean_mass_kg": g_to_kg(w_avg.get("muscleMass")),
            },
            "recent_activities": [
                self._norm_activity(a) for a in acts if isinstance(a, dict)
            ],
        }
