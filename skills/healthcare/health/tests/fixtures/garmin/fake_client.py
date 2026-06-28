"""FakeGarminClient — stand-in for `garminconnect.Garmin` in tests.

Mirrors the subset of the `garminconnect.Garmin` public API the
`GarminTraceSource` adapter relies on. Records every method call in
`self.call_log` so tests can assert on the orchestration order/args, and
exposes `raise_on_call` so a test can inject a specific exception on a
named method (e.g. simulating a 429 mid-sync).

Constructor signature is keyword-only so tests can override one canned
response without re-specifying the whole bundle.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any

from tests.fixtures.garmin.canned_responses import (
    ACTIVITIES_LAST_10,
    ACTIVITY_99001_DETAIL,
    ACTIVITY_99001_SPLITS,
    BODY_BATTERY_2026_05_22,
    HRV_2026_05_22,
    RHR_2026_05_22,
    SLEEP_2026_05_22,
    STATS_2026_05_22,
    TR_2026_05_22,
    VO2_2026_05_22,
)

__all__ = ["FakeGarminClient"]


class FakeGarminClient:
    """A minimal `garminconnect.Garmin`-shaped fake.

    All methods record `(method_name, args, kwargs)` into `call_log` so
    tests can assert on call order. Inject `raise_on_call={"get_stats": exc}`
    to make a specific method raise once.

    The class is intentionally NOT a Protocol implementation — adapters
    accept it via duck-typing (a `client_factory` callable that returns
    "something with these methods"). This matches the `python-garminconnect`
    library shape, which has no Protocol of its own.
    """

    def __init__(
        self,
        *,
        stats: dict[str, Any] | None = None,
        sleep: dict[str, Any] | None = None,
        rhr: dict[str, Any] | None = None,
        hrv: dict[str, Any] | None = None,
        training_readiness: list[dict[str, Any]] | None = None,
        max_metrics: list[dict[str, Any]] | None = None,
        body_battery: list[dict[str, Any]] | None = None,
        activities: list[dict[str, Any]] | None = None,
        activity_detail: dict[str, Any] | None = None,
        activity_splits: dict[str, Any] | None = None,
        activity_blob: bytes | None = None,
        raise_on_call: dict[str, Exception] | None = None,
    ) -> None:
        self._stats = stats if stats is not None else STATS_2026_05_22
        self._sleep = sleep if sleep is not None else SLEEP_2026_05_22
        self._rhr = rhr if rhr is not None else RHR_2026_05_22
        self._hrv = hrv if hrv is not None else HRV_2026_05_22
        self._tr = training_readiness if training_readiness is not None else TR_2026_05_22
        self._max = max_metrics if max_metrics is not None else VO2_2026_05_22
        self._bb = body_battery if body_battery is not None else BODY_BATTERY_2026_05_22
        self._activities = activities if activities is not None else ACTIVITIES_LAST_10
        self._activity_detail = (
            activity_detail if activity_detail is not None else ACTIVITY_99001_DETAIL
        )
        self._activity_splits = (
            activity_splits if activity_splits is not None else ACTIVITY_99001_SPLITS
        )
        self._activity_blob = activity_blob if activity_blob is not None else b""
        self._raise_on_call = dict(raise_on_call) if raise_on_call else {}
        self.call_log: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        # Mirror Garmin().display_name for adapters that read it post-login.
        self.display_name: str | None = None
        self.full_name: str | None = None
        # Token store dir the adapter may set after login().
        self.garth: Any = None

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _maybe_raise(self, method: str) -> None:
        """Raise the queued exception for `method` exactly once, if any."""
        if method in self._raise_on_call:
            exc = self._raise_on_call.pop(method)
            raise exc

    def _record(self, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self.call_log.append((method, args, kwargs))

    # ------------------------------------------------------------------ #
    # Auth surface
    # ------------------------------------------------------------------ #

    def login(self, *args: Any, **kwargs: Any) -> tuple[str, str]:
        """Mirror `Garmin.login()` — returns (oauth1_token, oauth2_token) tuple.

        Realistic shape: the live library returns garth tokens; we return
        deterministic placeholders so adapter code that captures-and-stores
        them sees a stable value.
        """
        self._record("login", args, kwargs)
        self._maybe_raise("login")
        self.display_name = "broomva"
        self.full_name = "Carlos Escobar"
        return ("fake-oauth1-token", "fake-oauth2-token")

    def garth_dumps(self) -> str:
        """Serialize tokens — mirrors the helper our adapter likely uses."""
        self._record("garth_dumps", (), {})
        self._maybe_raise("garth_dumps")
        return '{"oauth1_token": "fake-oauth1", "oauth2_token": "fake-oauth2"}'

    # ------------------------------------------------------------------ #
    # Daily-summary / wellness endpoints
    # ------------------------------------------------------------------ #

    def get_stats(self, day: date_type | str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._record("get_stats", (day, *args), kwargs)
        self._maybe_raise("get_stats")
        return self._stats

    def get_user_summary(
        self, day: date_type | str, *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        self._record("get_user_summary", (day, *args), kwargs)
        self._maybe_raise("get_user_summary")
        return self._stats

    def get_sleep_data(
        self, day: date_type | str, *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        self._record("get_sleep_data", (day, *args), kwargs)
        self._maybe_raise("get_sleep_data")
        return self._sleep

    def get_rhr_day(self, day: date_type | str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._record("get_rhr_day", (day, *args), kwargs)
        self._maybe_raise("get_rhr_day")
        return self._rhr

    def get_hrv_data(self, day: date_type | str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._record("get_hrv_data", (day, *args), kwargs)
        self._maybe_raise("get_hrv_data")
        return self._hrv

    def get_training_readiness(
        self, day: date_type | str, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        self._record("get_training_readiness", (day, *args), kwargs)
        self._maybe_raise("get_training_readiness")
        return self._tr

    def get_max_metrics(
        self, day: date_type | str, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        self._record("get_max_metrics", (day, *args), kwargs)
        self._maybe_raise("get_max_metrics")
        return self._max

    def get_body_battery(
        self,
        start: date_type | str,
        end: date_type | str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        self._record("get_body_battery", (start, end, *args), kwargs)
        self._maybe_raise("get_body_battery")
        return self._bb

    # ------------------------------------------------------------------ #
    # Activities
    # ------------------------------------------------------------------ #

    def get_activities(
        self, start: int = 0, limit: int = 20, *args: Any, **kwargs: Any
    ) -> list[dict[str, Any]]:
        self._record("get_activities", (start, limit, *args), kwargs)
        self._maybe_raise("get_activities")
        return self._activities[start : start + limit]

    def get_activity(self, activity_id: int, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._record("get_activity", (activity_id, *args), kwargs)
        self._maybe_raise("get_activity")
        return self._activity_detail

    def get_activity_splits(
        self, activity_id: int, *args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        self._record("get_activity_splits", (activity_id, *args), kwargs)
        self._maybe_raise("get_activity_splits")
        return self._activity_splits

    def download_activity(
        self, activity_id: int, *, dl_fmt: Any = None, **kwargs: Any
    ) -> bytes:
        self._record("download_activity", (activity_id,), {"dl_fmt": dl_fmt, **kwargs})
        self._maybe_raise("download_activity")
        return self._activity_blob

    # ------------------------------------------------------------------ #
    # Test-helper accessors
    # ------------------------------------------------------------------ #

    def calls_to(self, method: str) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
        """Return only the (args, kwargs) for invocations of `method`."""
        return [(a, kw) for (m, a, kw) in self.call_log if m == method]

    def call_methods(self) -> list[str]:
        """Ordered list of method names invoked — useful for sequence asserts."""
        return [m for (m, _a, _kw) in self.call_log]

    def queue_failure(self, method: str, exc: Exception) -> None:
        """Add a one-shot failure for `method` (clears after first call)."""
        self._raise_on_call[method] = exc
