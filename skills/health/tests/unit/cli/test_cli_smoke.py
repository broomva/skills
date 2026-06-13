"""Smoke tests for the Typer surface.

Because the adapters (Garmin source, SQLite repo wiring, filesystem token
store, prompt MFA, token-bucket rate limiter, Obsidian projection) are
owned by other streams, this test installs lightweight stand-in modules
into ``sys.modules`` before importing the app. The CLI under test is the
real CLI — only the adapter classes are stubbed.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from broomva_health.domain.errors import AuthRequired
from broomva_health.domain.results import SourceStatus, SyncResult, TokenBundle
from broomva_health.domain.source import Source

# ---------------------------------------------------------------------------
# Adapter stubs.
# ---------------------------------------------------------------------------


class _StubTokenStore:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._bundles: dict[tuple[Source, str], TokenBundle] = {}

    def get(self, source: Source, profile: str = "default") -> TokenBundle | None:
        return self._bundles.get((source, profile))

    def put(self, bundle: TokenBundle) -> None:
        self._bundles[(bundle.source, bundle.profile)] = bundle

    def delete(self, source: Source, profile: str = "default") -> None:
        self._bundles.pop((source, profile), None)

    def list_profiles(self, source: Source) -> list[str]:
        return sorted({profile for src, profile in self._bundles if src == source})


class _StubRateLimiter:
    def __init__(
        self,
        min_interval_s: int = 900,
        clock: object | None = None,
        state_path: object | None = None,
        on_429_backoff_s: float = 1800.0,
    ) -> None:
        self.min_interval_s = min_interval_s
        self.clock = clock
        self.state_path = state_path
        self.on_429_backoff_s = on_429_backoff_s
        self._snapshot: dict[str, str] = {}

    def acquire(self, key: str) -> None:
        return None

    def record_success(self, key: str) -> None:
        return None

    def record_429(self, key: str, retry_after_s: float | None = None) -> None:
        return None

    def snapshot(self) -> dict[str, str]:
        return dict(self._snapshot)


class _StubMFA:
    def prompt(self, source: str) -> str:
        return "000000"


class _StubProjection:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def emit_daily(self, day, projection):
        return self._root / f"{day.isoformat()}.md"


class _StubGarmin:
    """Minimal TraceSource for tests — every operation is a no-op."""

    def __init__(self, **_: object) -> None:
        # Accept paths= / cli_path= so build_sources can construct it for
        # either the library or cli backend.
        pass

    @property
    def name(self) -> Source:
        return Source.GARMIN

    def authenticate(self, **_: object) -> None:
        return None

    def sync(self, **_: object) -> SyncResult:
        now = datetime.now(tz=UTC)
        return SyncResult(
            source=Source.GARMIN,
            started_at=now,
            finished_at=now,
            samples_ingested=0,
            workouts_ingested=0,
            errors=[],
            rate_limit_remaining_s=None,
        )

    def backfill(self, **_: object):  # pragma: no cover — not exercised here
        raise NotImplementedError

    def status(self, *, token_store, profile: str = "default") -> SourceStatus:
        bundle = token_store.get(Source.GARMIN, profile)
        kwargs: dict[str, object] = {
            "source": Source.GARMIN,
            "token_valid": bundle is not None,
        }
        # Pydantic v2 + the domain's lambda-style validators have a quirk
        # where passing explicit None for an Optional datetime trips the
        # validator's arg-binding. Only set when a real value exists.
        if bundle is not None and bundle.expires_at is not None:
            kwargs["token_expires_at"] = bundle.expires_at
        return SourceStatus(**kwargs)


class _StubSQLiteRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def migrate(self) -> int:
        return 0

    def upsert_quantity(self, samples) -> int:
        return len(samples)

    def upsert_category(self, samples) -> int:
        return len(samples)

    def upsert_correlation(self, samples) -> int:
        return len(samples)

    def upsert_workout(self, workouts) -> int:
        return len(workouts)

    def last_sample_ts(self, source, metric):
        return None

    def query_quantity(self, source, metric, start, end):
        return []

    def query_workouts(self, source, start, end):
        return []

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Module-level fixture — installs stubs into sys.modules + tmp paths.
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_adapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Install adapter stand-in modules into sys.modules for the duration."""

    monkeypatch.setenv("BROOMVA_HEALTH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("BROOMVA_HEALTH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BROOMVA_HEALTH_VAULT_DIR", str(tmp_path / "vault"))

    def _install(name: str, **attrs: object) -> None:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    _install(
        "broomva_health.adapters.token_stores.filesystem",
        FilesystemTokenStore=_StubTokenStore,
    )
    _install(
        "broomva_health.adapters.rate_limiters.token_bucket",
        TokenBucketRateLimiter=_StubRateLimiter,
    )
    _install("broomva_health.adapters.mfa.prompt", PromptMFAProvider=_StubMFA)
    _install(
        "broomva_health.adapters.projections.obsidian",
        ObsidianDailyNoteProjection=_StubProjection,
    )
    _install("broomva_health.adapters.sources.garmin", GarminTraceSource=_StubGarmin)
    _install(
        "broomva_health.adapters.sources.garmin_cli",
        GarminCliTraceSource=_StubGarmin,
        map_context=lambda *a, **k: ([], []),
    )
    _install(
        "broomva_health.adapters.sources.garmin_native",
        GarminNativeTraceSource=_StubGarmin,
    )
    _install(
        "broomva_health.adapters.repositories.sqlite",
        SQLiteTraceRepository=_StubSQLiteRepository,
    )

    # Make sure cli.app picks up the fresh adapter modules — if it was
    # imported in a previous test, the cached Container.build closure has
    # already captured the original (real) modules, so we reload it.
    # `_registry` must reload FIRST so its module-level GarminTraceSource /
    # GarminCliTraceSource names rebind to the stubs above.
    for module_name in [
        "broomva_health.adapters.sources._registry",
        "broomva_health.cli.container",
        "broomva_health.cli.app",
        "broomva_health.cli.auth",
        "broomva_health.cli.sync",
        "broomva_health.cli.status",
        "broomva_health.cli.doctor",
        "broomva_health.cli.context",
    ]:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])

    yield

    # Clean the stub modules so other test files (which may rely on the
    # real adapters once they ship) start from a clean slate.
    for name in (
        "broomva_health.adapters.token_stores.filesystem",
        "broomva_health.adapters.rate_limiters.token_bucket",
        "broomva_health.adapters.mfa.prompt",
        "broomva_health.adapters.projections.obsidian",
        "broomva_health.adapters.sources.garmin",
        "broomva_health.adapters.sources.garmin_cli",
        "broomva_health.adapters.sources.garmin_native",
        "broomva_health.adapters.sources._registry",
        "broomva_health.adapters.repositories.sqlite",
    ):
        sys.modules.pop(name, None)


def _runner() -> CliRunner:
    return CliRunner()


def _get_app():
    from broomva_health.cli.app import app

    return app


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


def test_help_returns_usage(stub_adapters: None) -> None:
    result = _runner().invoke(_get_app(), ["--help"])
    assert result.exit_code == 0, result.stdout
    assert "Usage:" in result.stdout


def test_version_flag_prints_version(stub_adapters: None) -> None:
    """`health --version` must print the package __version__.

    Asserts dynamically against the imported value rather than a hardcoded
    string — version-bumps shouldn't have to touch this test (the lesson
    surfaced by the /dogfood-caught v0.2.1 CI failure when 0.1.0 was hardcoded).
    """
    from broomva_health import __version__

    result = _runner().invoke(_get_app(), ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
    # Sanity: the version string is non-empty + SemVer-shaped (X.Y.Z[.…]).
    # Split into separate asserts so ruff PT018 stays happy.
    assert __version__, "package __version__ must be non-empty"
    assert __version__[0].isdigit(), f"version must start with a digit: {__version__!r}"
    assert "." in __version__, f"version must contain '.': {__version__!r}"


def test_sync_help(stub_adapters: None) -> None:
    """`health sync --help` lists the documented flags.

    Strips ANSI control sequences before substring matching — Typer/rich
    pretty-formatting wraps long option names across border characters,
    which broke a naive `in result.stdout` check (caught by /dogfood on
    the v0.2.1 CI run).
    """
    import re

    result = _runner().invoke(_get_app(), ["sync", "--help"])
    assert result.exit_code == 0
    # Strip ANSI CSI sequences + box-drawing border characters so we
    # match on the underlying flag tokens, not on rich's render.
    cleaned = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", result.stdout)
    cleaned = re.sub(r"[│┃┆┇┊┋║|]", " ", cleaned)
    assert "Usage:" in cleaned
    assert "--source" in cleaned or "--since" in cleaned, (
        f"Expected --source or --since in cleaned help output; got:\n{cleaned[:500]}"
    )


def test_doctor_runs_without_traceback(stub_adapters: None) -> None:
    result = _runner().invoke(_get_app(), ["--format", "human", "doctor"])
    # doctor MAY exit non-zero if a hard check (no config file) becomes FAIL,
    # but it must NEVER raise a Python exception out the top.
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        f"doctor raised: {result.exception!r}\nstdout: {result.stdout}"
    )
    assert "doctor" in result.stdout or "OK" in result.stdout or "WARN" in result.stdout


def test_auth_status_json_is_valid_and_exits_2_when_no_tokens(
    stub_adapters: None,
) -> None:
    result = _runner().invoke(_get_app(), ["--format", "json", "auth", "status"])
    # No tokens were written → AuthRequired → exit code 2.
    assert result.exit_code == 2, (
        f"expected 2 (auth_required), got {result.exit_code}\n"
        f"stdout: {result.stdout}"
    )
    # stdout has the JSON payload followed by the error line printed to
    # stderr — but Typer's CliRunner (typer 0.25) merges streams. Split the
    # first JSON document out of the combined buffer.
    payload_str = result.stdout.split("\n[")[0] if result.stdout.startswith("[") else (
        result.stdout.split("error[")[0].rstrip()
    )
    payload = json.loads(payload_str)
    assert isinstance(payload, list)
    assert all(item["token_valid"] is False for item in payload)


def test_auth_required_maps_to_exit_code_two(
    stub_adapters: None,
) -> None:
    """Confirm the exit-code mapping: AuthRequired.exit_code == 2 propagates."""

    # auth status with no tokens is the natural trigger for AuthRequired —
    # this asserts the mapping is wired end-to-end. We also assert the
    # AuthRequired class itself carries exit_code 2 so the mapping isn't a
    # coincidence.
    assert AuthRequired().exit_code == 2

    result = _runner().invoke(_get_app(), ["auth", "status"])
    assert result.exit_code == 2
