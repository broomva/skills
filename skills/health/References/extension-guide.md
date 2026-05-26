# Extension guide — adding a new source

How to add Apple Health, Whoop, Oura, CGM, or any other source to the Health skill.

**Total work for a complete source adapter:** ~200–400 LOC + tests + docs. The hex architecture means nothing outside `adapters/sources/<name>.py` and one line in `_registry.py` should change.

---

## The six steps

### 1. Add the `Source` enum member

File: `src/broomva_health/domain/source.py`

```python
class Source(StrEnum):
    GARMIN = "garmin"
    APPLE_HEALTH = "apple_health"
    WHOOP = "whoop"
    OURA = "oura"
    CGM = "cgm"
    MANUAL = "manual"
    # NEW:
    YOUR_SOURCE = "your_source"
```

**Rules:**
- Member name: `SCREAMING_SNAKE_CASE`
- String value: `lower_snake_case` (matches SQL column convention)
- Never rename a string value without a SQL migration (the value is on disk in every sample row's `source` column).
- The Source enum is the **only** place a new source touches the domain layer.

### 2. Implement the `TraceSource` protocol

File: `src/broomva_health/adapters/sources/<your_source>.py`

The contract from `ports/source.py`:

```python
@runtime_checkable
class TraceSource(Protocol):
    @property
    def name(self) -> Source: ...
    def authenticate(self, *, token_store, mfa, email=None, password=None, profile="default") -> None: ...
    def sync(self, *, repo, token_store, rate_limiter, since=None, profile="default") -> SyncResult: ...
    def backfill(self, *, repo, token_store, rate_limiter, start, end, profile="default") -> BackfillResult: ...
    def status(self, *, token_store, profile="default") -> SourceStatus: ...
```

Adapter discipline:
- **Acquire the rate-limiter slot before any network I/O.**
- **Persist refreshed tokens via `token_store.put(...)` on success.**
- **Convert all units at the adapter boundary.** The domain only sees canonical units (see `METRIC_UNITS` in `domain/metrics.py`).
- **All datetimes UTC.** Pass naive timestamps through `domain.time.ensure_utc(...)` first.
- **`status` must never raise.** Return a populated `SourceStatus(token_valid=False, ...)` on auth failure.

### 3. Register the adapter

File: `src/broomva_health/adapters/sources/_registry.py`

```python
from broomva_health.adapters.sources.your_source import YourSource

REGISTRY: dict[Source, type[TraceSource]] = {
    Source.GARMIN: GarminSource,
    # NEW:
    Source.YOUR_SOURCE: YourSource,
}
```

This is the **only** central registration point. The CLI's container reads from `REGISTRY` to build the right adapter for the `--source` flag.

### 4. CLI passthrough (optional)

If your source has source-specific endpoints worth exposing (e.g. Garmin's per-activity FIT-file download), add a CLI subcommand under `cli/commands/<your_source>/`:

```python
@app.command("download-fit")
def download_fit(activity_id: str, format: str = "json") -> None:
    """Download the raw FIT blob for an activity (Your Source-specific)."""
    ...
```

These are escape hatches; the four base subcommands (`auth`, `sync`, `backfill`, `status`) cover 95% of use cases via the protocol.

### 5. Unit tests with a mocked client

File: `tests/adapters/sources/test_your_source.py`

```python
def test_sync_writes_quantity_samples(fake_client, in_memory_repo, fake_rate_limiter, fake_token_store):
    fake_client.set_heart_rate_response([
        {"timestamp": "2026-05-22T06:00:00Z", "value": 64.0},
    ])
    source = YourSource(client_factory=lambda: fake_client)
    result = source.sync(
        repo=in_memory_repo,
        token_store=fake_token_store,
        rate_limiter=fake_rate_limiter,
        since=None,
    )
    assert result.samples_ingested == 1
    samples = in_memory_repo.query_quantity(Source.YOUR_SOURCE, MetricCode.HEART_RATE, ...)
    assert samples[0].value == 64.0
    assert samples[0].unit == "bpm"
```

**Coverage gate:** `pyproject.toml` sets `fail_under = 75`. New adapters should meet this on their own files.

### 6. Add a reference doc under `References/`

File: `skills/Health/References/<your-source>-substrate-notes.md`

Mirror the structure of `garmin-api-landscape-2026.md`:
- Why this client library / API surface
- Auth flow specifics (OAuth? username+password+MFA? cookies?)
- Rate-limit policy + observed account-lockout history
- Coverage matrix (which `MetricCode`s does it populate?)
- Open watchlist (what could change?)

This is what the next maintainer / agent will read before touching the adapter.

---

## Worked example — minimal Whoop adapter

Here is the *minimal viable* shape of a Whoop source adapter, demonstrating the seam. (~50 LOC of the adapter — the full version would be 200+ with proper error handling and full metric coverage.)

```python
# src/broomva_health/adapters/sources/whoop.py
"""Whoop source adapter — OAuth2-based, cycles + recovery + sleep + workouts."""

from __future__ import annotations

from datetime import date, datetime, UTC
from typing import Any

import httpx  # add to optional [whoop] extra

from broomva_health.domain.errors import AuthRequired, RateLimited
from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.results import BackfillResult, SourceStatus, SyncResult
from broomva_health.domain.samples import QuantitySample
from broomva_health.domain.source import Source
from broomva_health.domain.time import ensure_utc, utc_now


class WhoopSource:
    """Whoop adapter — OAuth2 personal-tier (https://developer.whoop.com/api)."""

    def __init__(self, *, client_factory=None) -> None:
        self._client_factory = client_factory or (lambda: httpx.Client(timeout=30.0))

    @property
    def name(self) -> Source:
        return Source.WHOOP

    def authenticate(self, *, token_store, mfa, email=None, password=None, profile="default") -> None:
        # OAuth2 device-code flow; persists TokenBundle on success.
        raise NotImplementedError("Whoop adapter — OAuth flow not yet implemented")

    def sync(self, *, repo, token_store, rate_limiter, since=None, profile="default") -> SyncResult:
        rate_limiter.acquire(f"{self.name.value}:sync")

        bundle = token_store.get(self.name, profile)
        if bundle is None:
            raise AuthRequired("no Whoop token; run `health auth login --source whoop`")

        started = utc_now()
        samples: list[QuantitySample] = []

        # Pseudo: pull recovery scores since cursor
        # cursor = since or repo.last_sample_ts(self.name, MetricCode.HRV_OVERNIGHT)
        # response = self._client().get(f"https://api.prod.whoop.com/...", headers={...})
        # for cycle in response.json()["records"]:
        #     samples.append(QuantitySample(
        #         source=Source.WHOOP,
        #         metric=MetricCode.HRV_OVERNIGHT,
        #         value=float(cycle["score"]["hrv_rmssd_milli"]),  # already ms
        #         unit="ms",
        #         start_ts=ensure_utc(datetime.fromisoformat(cycle["start"])),
        #         end_ts=ensure_utc(datetime.fromisoformat(cycle["end"])),
        #     ))

        ingested = repo.upsert_quantity(samples)
        rate_limiter.record_success(f"{self.name.value}:sync")

        return SyncResult(
            source=self.name,
            started_at=started,
            finished_at=utc_now(),
            samples_ingested=ingested,
            workouts_ingested=0,
            errors=[],
            rate_limit_remaining_s=None,
        )

    def backfill(self, *, repo, token_store, rate_limiter, start, end, profile="default") -> BackfillResult:
        # Same pattern as sync, walking [start, end] in daily chunks.
        raise NotImplementedError("Whoop backfill — not yet implemented")

    def status(self, *, token_store, profile="default") -> SourceStatus:
        # MUST NOT raise. Return a populated SourceStatus even on broken auth.
        bundle = token_store.get(self.name, profile)
        return SourceStatus(
            source=self.name,
            token_valid=bundle is not None,
            token_expires_at=bundle.expires_at if bundle else None,
        )
```

Register it:

```python
# src/broomva_health/adapters/sources/_registry.py
from broomva_health.adapters.sources.whoop import WhoopSource

REGISTRY = {
    Source.GARMIN: GarminSource,
    Source.WHOOP: WhoopSource,
}
```

Run it:

```bash
health auth login --source whoop
health sync --source whoop
```

That's the seam. The application layer, the CLI's `sync` command, the format dispatchers, the daily-note projection — none of them changed.

---

## Things to think about per source

| Concern | Garmin | Apple Health | Whoop | Oura | CGM |
|---|---|---|---|---|---|
| Auth model | username+pw+MFA | local HealthKit export (no auth) | OAuth2 | OAuth2 | varies (Dexcom OAuth, Libre via shareable PIN) |
| Rate limits | 15-min floor; account-scoped 429 cascade | none (local) | documented per-endpoint | 5,000/day | per-vendor |
| HRV coverage | yes (overnight) | yes (HKQuantityTypeIdentifierHeartRateVariabilitySDNN) | yes (HRV RMSSD) | yes (HRV RMSSD) | n/a |
| Sleep stages | yes | yes (HKCategoryTypeIdentifierSleepAnalysis) | yes | yes | n/a |
| TSS / training load | yes (Garmin TSS) | only what the source app stores | "Strain" — different model | none | n/a |
| Body Battery / Recovery score | yes (opaque) | varies | yes (opaque) | yes (opaque) | n/a |
| Workouts with FIT | yes | depends on source app | no FIT, JSON only | activity summary only | n/a |

The `[MetricCode]` registry is intentionally a superset — not every source populates every metric. Adapters fill what they have.

---

## Don't break the seam

Common mistakes that break hex:

| Mistake | Fix |
|---|---|
| Importing another adapter inside your adapter (e.g. `from broomva_health.adapters.sources.garmin import ...`) | Adapters never depend on each other. If you need shared logic, put it in `domain/` (pure) or `adapters/_shared/` (concrete, but explicitly cross-adapter). |
| Calling `sqlite3.connect(...)` inside your adapter | Adapters depend on `TraceRepository` (a port), not on SQLite. The repository is injected. |
| Writing a file inside your adapter | Write the original blob via the repository's `upsert_workout(...)` (the fit_blob_sha256 is the link); the repository owns disk paths. |
| Hard-coding rate-limit timing | Use the injected `rate_limiter`. The 15-min floor is configured at the CLI's container, not in the adapter. |
| Skipping `extra="forbid"` validation by routing dict-shaped data around the domain | The whole point of the domain layer is the type wall. If the adapter receives shape the domain rejects, that's the adapter's bug — fix the conversion. |

---

## References

- [References/architecture.md](architecture.md) — full hex deep-dive
- [References/healthkit-data-model.md](healthkit-data-model.md) — sample-type shape rationale
- [References/rate-limit-discipline.md](rate-limit-discipline.md) — per-source rate-limit policy
- [References/privacy-architecture.md](privacy-architecture.md) — token store + DB encryption
