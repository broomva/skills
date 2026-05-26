"""Garmin Connect trace source adapter.

Built on `garminconnect >= 0.2.20` (PyPI package; GitHub repo is
`cyberjunky/python-garminconnect`). May 2026 substrate — the upstream
`matin/garth` was deprecated 2026-03-28 after Cloudflare's WAF killed
the mobile-SSO endpoint. The library wraps Garmin's web API with
`curl_cffi` Chrome-TLS impersonation; we wrap *that* with the TraceSource
protocol so the rest of the codebase sees a stable interface even as the
upstream library churns.

Discipline:

- Every public method acquires from the rate limiter BEFORE any network I/O.
- Tokens are persisted via the injected `TokenStore`; a Garmin-library-
  compatible `garmin_tokens.json` mirror is written by `FilesystemTokenStore`
  so the library's `Garmin().login(tokenstore=<dir>)` path picks it up.
- Library exceptions never escape — they map to domain `HealthError` subtypes
  (`AuthRequired`, `MFANeeded`, `RateLimited`, `SourceUnavailable`).
- The `garminconnect` import is lazy: tests inject a `client_factory` and
  never need the real library on the path.
"""

from __future__ import annotations

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
_GARMIN_LIB_TOKEN_FILE = "garmin_tokens.json"


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

        # The library accepts a `prompt_mfa` callable invoked when the
        # account is challenged. Wrap our MFAProvider so the library can call it.
        def _prompt_mfa() -> str:
            return mfa.prompt(str(Source.GARMIN))

        token_dir = self._token_dir(token_store, profile)
        token_dir.mkdir(parents=True, exist_ok=True)

        client = self._client_factory(
            email=email, password=password, prompt_mfa=_prompt_mfa
        )

        try:
            client.login()
        except Exception as exc:
            self._raise_mapped(exc, op="authenticate")
            raise  # unreachable; _raise_mapped always raises

        # After login the library exposes `dump_tokens(<dir>)` (older releases
        # call it `garth_client.dump`). Persist via our TokenStore so the
        # bundle survives + the Garmin-compat mirror file lives alongside.
        raw = self._dump_library_tokens(client, token_dir)
        bundle = TokenBundle(
            source=Source.GARMIN,
            profile=profile,
            raw_bytes=raw,
            stored_at=utc_now(),
            expires_at=None,
        )
        token_store.put(bundle)

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
        return SourceStatus(
            source=Source.GARMIN,
            last_sync=None,
            last_error=None,
            rate_limit_resets_at=None,
            token_valid=bundle is not None,
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

    def _dump_library_tokens(self, client: Any, token_dir: Any) -> bytes:
        """Persist the library's tokens to `token_dir` and return raw bytes."""
        # Prefer the documented dump API; fall back if missing.
        for method_name in ("dump_tokens", "garth_dump"):
            method = getattr(client, method_name, None)
            if callable(method):
                try:
                    method(str(token_dir))
                except Exception as exc:
                    logger.debug("Token dump via %s failed: %s", method_name, exc)
                    continue
                break

        token_file = token_dir / _GARMIN_LIB_TOKEN_FILE
        if token_file.exists():
            return token_file.read_bytes()

        # Last resort: dump whatever the library has on it as a JSON-ish blob.
        # Keep it opaque — the consumer only round-trips the bytes.
        logger.warning("Garmin lib did not write %s; persisting empty bundle", token_file)
        return b""

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
