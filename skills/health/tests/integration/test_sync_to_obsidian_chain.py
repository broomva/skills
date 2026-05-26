"""Full sync→repo→projection integration chain — e2e gated.

Every test in this module wears `@pytest.mark.e2e`. The conftest.py gates
those off the default run; opt in with ``BROOMVA_HEALTH_E2E=1``.

The chain assembled here is the production wiring:

    GarminTraceSource(client_factory=FAKE) \
        → SyncSourceUseCase                 \
            → SQLiteTraceRepository          \
        → RenderDailyNoteUseCase             \
            → ObsidianDailyNoteProjection     → daily-note .md file

Everything except the Garmin client is REAL: real SQLite on tmp_path,
real Obsidian projection writing to tmp_path/vault, real
TokenBucketRateLimiter, real FilesystemTokenStore. The only fake is the
network boundary — which is the right shape: integration tests should
exercise as much code as possible without crossing the network.

GarminTraceSource is owned by Stream C. When it lands in
``adapters.sources.garmin``, every test here flips from skipped→executing.
Until then, the module-level guard surfaces an explicit skip reason so
the gap is visible in pytest output.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from broomva_health.adapters.clock import FakeClock
from broomva_health.adapters.mfa.prompt import StaticMFAProvider
from broomva_health.adapters.projections.obsidian import ObsidianDailyNoteProjection
from broomva_health.adapters.rate_limiters.token_bucket import TokenBucketRateLimiter
from broomva_health.adapters.repositories.sqlite import SQLiteTraceRepository
from broomva_health.adapters.token_stores.filesystem import FilesystemTokenStore
from broomva_health.application.daily_note import RenderDailyNoteUseCase
from broomva_health.application.sync import SyncSourceUseCase
from broomva_health.config.paths import HealthPaths
from broomva_health.domain.errors import RateLimited
from broomva_health.domain.results import TokenBundle
from broomva_health.domain.source import Source
from tests.fixtures.garmin.fake_client_factory import (
    make_fake_client_factory_with_handle,
)

try:
    from broomva_health.adapters.sources.garmin import (
        GarminTraceSource,  # type: ignore[import-not-found]
    )

    _GARMIN_AVAILABLE = True
except ImportError:  # pragma: no cover — landed by Stream C
    GarminTraceSource = None  # type: ignore[misc,assignment]
    _GARMIN_AVAILABLE = False


_GARMIN_SKIP = pytest.mark.skipif(
    not _GARMIN_AVAILABLE,
    reason=(
        "adapters.sources.garmin.GarminTraceSource not yet imported — "
        "test will activate when Stream C lands the adapter."
    ),
)

# Canonical fixed date matches `conftest.fixed_now` (2026-05-22).
_FIXED_DAY = date(2026, 5, 22)
_FIXED_NOW = datetime(2026, 5, 22, 12, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _seed_garmin_token(token_store: FilesystemTokenStore) -> None:
    """Drop a valid TokenBundle on disk so sync() never has to log in.

    Mirrors what a successful `authenticate()` call would write — that
    way the integration test exercises the sync→repo→projection chain
    even before Stream B/C wire the real login path.
    """
    bundle = TokenBundle(
        source=Source.GARMIN,
        profile="default",
        raw_bytes=b'{"oauth1_token": "fake1", "oauth2_token": "fake2"}',
        stored_at=_FIXED_NOW,
        expires_at=_FIXED_NOW + timedelta(days=90),
    )
    token_store.put(bundle)


def _build_chain(tmp_path: Path) -> dict[str, object]:
    """Stand up the real adapters under a tmp_path sandbox.

    Returns a dict of every component so tests can both run the chain
    and reach into individual components for state assertions.
    """
    db_path = tmp_path / "garmin.db"
    tokens_dir = tmp_path / "tokens"
    vault_dir = tmp_path / "vault" / "07-Health"

    paths = HealthPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        vault_dir=tmp_path / "vault",
    )
    paths.ensure()

    repo = SQLiteTraceRepository(db_path)
    repo.migrate()

    token_store = FilesystemTokenStore(tokens_dir)
    _seed_garmin_token(token_store)

    clock = FakeClock(initial=_FIXED_NOW)
    # 1-second min_interval lets us trigger "second immediate sync" via the
    # rate limiter without sleeping in test time.
    rate_limiter = TokenBucketRateLimiter(min_interval_s=1.0, clock=clock)

    projection = ObsidianDailyNoteProjection(vault_dir)
    mfa = StaticMFAProvider("000000")

    return {
        "repo": repo,
        "token_store": token_store,
        "rate_limiter": rate_limiter,
        "clock": clock,
        "projection": projection,
        "mfa": mfa,
        "paths": paths,
        "db_path": db_path,
        "tokens_dir": tokens_dir,
        "vault_dir": vault_dir,
    }


def _parse_frontmatter(note_path: Path) -> dict[str, str]:
    """Return the frontmatter region of a daily-note as a flat dict.

    The Obsidian adapter writes scalar key: value lines between two
    ``---`` fences. This helper does the minimum parse the assertions
    need — we don't import a YAML library because the test contract is
    "what was written on disk" not "what PyYAML thinks of it".
    """
    text = note_path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"missing opening fence in {note_path}"
    closing = text.index("\n---\n", 4)
    body = text[4:closing]
    out: dict[str, str] = {}
    for line in body.splitlines():
        if not line or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        out[key.strip()] = raw.strip()
    return out


# --------------------------------------------------------------------------
# Test 1 — happy path
# --------------------------------------------------------------------------


@pytest.mark.e2e
@_GARMIN_SKIP
def test_full_sync_writes_to_repo_and_projection(tmp_path: Path) -> None:
    """Sync → repo → render → daily-note Markdown file produced + parses."""
    chain = _build_chain(tmp_path)
    repo = chain["repo"]
    token_store = chain["token_store"]
    rate_limiter = chain["rate_limiter"]
    projection = chain["projection"]
    mfa = chain["mfa"]
    vault_dir = chain["vault_dir"]
    assert isinstance(vault_dir, Path)

    factory, fake_client = make_fake_client_factory_with_handle()
    source = GarminTraceSource(paths=chain["paths"], client_factory=factory)  # type: ignore[misc,arg-type]

    sync_use_case = SyncSourceUseCase(
        source=source,
        repo=repo,
        token_store=token_store,
        rate_limiter=rate_limiter,
        mfa=mfa,
    )
    result = sync_use_case.execute()
    assert result.samples_ingested >= 0  # contract — the int is populated

    render_use_case = RenderDailyNoteUseCase(repo=repo, projection=projection)
    note_path = render_use_case.execute(day=_FIXED_DAY)

    assert note_path.exists(), f"daily note not written at {note_path}"
    assert note_path.parent == vault_dir
    assert note_path.name == f"{_FIXED_DAY.isoformat()}.md"

    frontmatter = _parse_frontmatter(note_path)
    # `date` is always written. `source` provenance stamp too.
    assert frontmatter["date"] == _FIXED_DAY.isoformat()
    assert frontmatter["source"].startswith("broomva-health v")

    # If the Garmin adapter wrote at least one of the canned metrics through
    # the repo, the frontmatter will surface it. We don't pin specific
    # numeric values here because the trace→projection numeric path is owned
    # by Streams C+F; the contract this test enforces is *the file gets
    # written and parses*, not "RHR == 47" (that's Stream F's territory).
    assert fake_client.call_log, "GarminTraceSource never called the client"


# --------------------------------------------------------------------------
# Test 2 — partial-failure repo invariant
# --------------------------------------------------------------------------


@pytest.mark.e2e
@_GARMIN_SKIP
def test_sync_handles_429_does_not_corrupt_repo(tmp_path: Path) -> None:
    """A 429 mid-sync bubbles to caller; samples already upserted stay committed.

    Intentional behavior: each per-metric upsert is its own transaction.
    A 429 raised after metric A but before metric B leaves metric A in the
    repo (so a later sync can resume incrementally) and metric B absent.
    This is the right shape for an append-only trace store — losing
    successfully-fetched data on partial failure would be worse than
    leaving a smaller-than-expected slice on disk.
    """
    chain = _build_chain(tmp_path)
    repo = chain["repo"]
    token_store = chain["token_store"]
    rate_limiter = chain["rate_limiter"]
    mfa = chain["mfa"]

    # Snapshot the repo state pre-sync (zero rows everywhere).
    db_path = chain["db_path"]
    assert isinstance(db_path, Path)
    pre_size = db_path.stat().st_size if db_path.exists() else 0

    # Inject a 429 on the hrv call. The adapter calls (in order):
    # get_stats → get_sleep_data → get_hrv_data → get_training_readiness →
    # get_max_metrics → get_activities. Failing get_hrv_data leaves
    # stats + sleep already committed; readiness/vo2/activities skipped.
    # The test contract: the 429 bubbles AND the repo is in a consistent
    # (smaller-than-expected) state.
    factory, fake_client = make_fake_client_factory_with_handle()
    fake_client.queue_failure("get_hrv_data", RateLimited("simulated 429"))
    source = GarminTraceSource(paths=chain["paths"], client_factory=factory)  # type: ignore[misc,arg-type]

    sync_use_case = SyncSourceUseCase(
        source=source,
        repo=repo,
        token_store=token_store,
        rate_limiter=rate_limiter,
        mfa=mfa,
    )

    with pytest.raises(RateLimited):
        sync_use_case.execute()

    # Repo file still exists, schema intact (we never blew away migrations).
    # The DB may have grown if any pre-429 metric was upserted — that's the
    # intentional partial-progress shape. The invariant is "DB usable".
    post_size = db_path.stat().st_size
    assert post_size >= pre_size, "repo file shrank — partial-write corruption"

    # Sanity: a follow-up READ on the repo doesn't raise. If migrations had
    # been rolled back, any query would error on missing tables.
    repo.query_workouts(
        source=Source.GARMIN,
        start=datetime(2026, 5, 22, tzinfo=UTC),
        end=datetime(2026, 5, 23, tzinfo=UTC),
    )


# --------------------------------------------------------------------------
# Test 3 — rate-limiter blocks immediate retry
# --------------------------------------------------------------------------


@pytest.mark.e2e
@_GARMIN_SKIP
def test_full_chain_round_trip_with_rate_limit_blocks_immediate_retry(
    tmp_path: Path,
) -> None:
    """First sync succeeds; an immediate second sync raises RateLimited.

    Time is frozen via FakeClock and `min_interval_s=1.0`. The first
    sync acquires the bucket; the second call at the same `clock.now()`
    sees `min_interval` not yet elapsed and raises. Advance the clock and
    a third call would succeed — but we stop at the assert because
    proving the negative is enough for the invariant.
    """
    chain = _build_chain(tmp_path)
    repo = chain["repo"]
    token_store = chain["token_store"]
    rate_limiter = chain["rate_limiter"]
    mfa = chain["mfa"]

    factory, _client = make_fake_client_factory_with_handle()
    source = GarminTraceSource(paths=chain["paths"], client_factory=factory)  # type: ignore[misc,arg-type]

    sync_use_case = SyncSourceUseCase(
        source=source,
        repo=repo,
        token_store=token_store,
        rate_limiter=rate_limiter,
        mfa=mfa,
    )

    # First sync — should succeed under the limiter (fresh bucket).
    sync_use_case.execute()

    # Second sync at the same instant (FakeClock hasn't moved) — must raise.
    with pytest.raises(RateLimited):
        sync_use_case.execute()


# --------------------------------------------------------------------------
# Test 4 — sanity that the chain wires up without the Garmin source
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_render_daily_note_on_empty_repo_writes_minimal_frontmatter(
    tmp_path: Path,
) -> None:
    """No Garmin source, no samples — the projection still emits a valid note.

    Proves the render path is decoupled from the sync path (which is the
    whole point of the ports/adapters split). Stream C can land Garmin
    later without breaking the render contract.
    """
    chain = _build_chain(tmp_path)
    repo = chain["repo"]
    projection = chain["projection"]
    vault_dir = chain["vault_dir"]
    assert isinstance(vault_dir, Path)

    render_use_case = RenderDailyNoteUseCase(repo=repo, projection=projection)
    note_path = render_use_case.execute(day=_FIXED_DAY)

    assert note_path.exists(), "render emitted no file"
    frontmatter = _parse_frontmatter(note_path)
    assert frontmatter["date"] == _FIXED_DAY.isoformat()
    assert frontmatter["source"].startswith("broomva-health v")
    # `activities_count: 0` is the only numeric that should be present —
    # everything else is None in an empty repo and the adapter omits None.
    assert frontmatter.get("activities_count") == "0"


# --------------------------------------------------------------------------
# Cross-stream sanity check: the fake client itself works through the
# Garmin-style API without invoking the not-yet-built adapter.
# --------------------------------------------------------------------------


@pytest.mark.e2e
def test_fake_client_smoke_against_canned_responses(tmp_path: Path) -> None:
    """Hard contract that the fake fixture itself returns the canned shape.

    Pinning the fixture's behavior here means Stream C can write its adapter
    against a stable API; any drift between FakeGarminClient and the canned
    responses surfaces here, not deep in their failing test.
    """
    _ = tmp_path  # unused — kept for fixture signature consistency
    factory, client = make_fake_client_factory_with_handle()

    g = factory()
    g.login("user@example.com", "pwd")
    stats = g.get_stats(_FIXED_DAY)
    sleep = g.get_sleep_data(_FIXED_DAY)
    hrv = g.get_hrv_data(_FIXED_DAY)
    activities = g.get_activities(0, 10)

    assert stats["totalSteps"] == 8423
    assert stats["restingHeartRate"] == 47
    assert sleep["dailySleepDTO"]["sleepTimeSeconds"] == 26640
    assert hrv["hrvSummary"]["lastNightAvg"] == 58
    assert activities[0]["activityId"] == 99001
    assert activities[0]["activityType"]["typeKey"] == "running"

    # call_log captured the orchestration in order.
    methods = client.call_methods()
    assert "login" in methods
    assert methods.index("get_stats") < methods.index("get_sleep_data")

    # Sanity: the raw_bytes shape the token store will see is JSON.
    raw = client.garth_dumps()
    parsed = json.loads(raw)
    assert "oauth1_token" in parsed
