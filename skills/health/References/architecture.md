# Architecture — hex (ports & adapters) deep-dive

## Why hex

The Health skill is **hexagonal** in the Alistair Cockburn 2005 sense: a pure domain at the center, a `ports` ring around it (Protocol interfaces), `adapters` outside that (concrete implementations), and an `application` layer composing ports into use cases. The CLI is the only impure entry point.

Cockburn's original: https://alistair.cockburn.us/hexagonal-architecture/ (originally "Hexagonal architecture", later re-described as "Ports & Adapters" because nothing about it is actually a hexagon — the six sides are arbitrary).

We get two things from this:

1. **Testability** — the domain and use cases have zero I/O. Every test runs in milliseconds against in-memory fakes. The Garmin adapter is the only place we mock network. The repository adapter is the only place we touch SQLite.
2. **Extensibility** — a new source (Apple Health, Whoop, Oura, CGM) drops in as a single file in `adapters/sources/` plus one line in `_registry.py`. The application layer doesn't change. The CLI doesn't change. The domain doesn't change.

The 2005 paper is short; read it if you haven't.

---

## Dependency arrow

```
cli/  ─→  application/  ─→  ports/  ←─  adapters/
                                                ├─ sources/
                                                ├─ repositories/
                                                ├─ projections/
                                                ├─ token_stores/
                                                ├─ rate_limiters/
                                                └─ mfa/
domain/   ←  ←  ←   (everything imports domain; domain imports nothing else)
synthesis/  ←  application uses synthesis; synthesis uses domain only
config/     ←  cli uses config; nothing else does
migrations/ ←  adapters/repositories/ uses migrations
```

Read the arrows: `A → B` means "A imports B".

Inversion holds:
- `application/` imports `ports/` + `domain/` + `synthesis/`. It does **not** import any adapter.
- `adapters/` import `ports/` + `domain/`. They do **not** import each other.
- `domain/` imports nothing from `ports/`, `adapters/`, `application/`, or `cli/`. It's purely terminal.
- `cli/` imports everything — it's the composition root.

If a `git grep "import broomva_health.adapters" src/broomva_health/application/` ever returns a hit, that's a P20-class break. Fix it.

---

## The `TraceSource` protocol

This is the source-extensibility seam. Defined in `src/broomva_health/ports/source.py`:

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

Adapter contract:
- Every operation MUST acquire from `rate_limiter` before any network I/O.
- Every operation MUST persist updated tokens via `token_store` on success.
- `status` MUST NOT raise — it returns a populated `SourceStatus` even when authentication is broken.
- `authenticate` may call `mfa.prompt(source)` to get a one-time code.

Adding a source is **only** the question "can this be a TraceSource?". If you can answer yes, the source belongs in this codebase. If you can't, it doesn't — and the friction surfaces the design issue.

---

## Use cases as separate classes — why

```python
@dataclass(frozen=True)
class SyncSourceUseCase:
    source: TraceSource
    repo: TraceRepository
    token_store: TokenStore
    rate_limiter: RateLimiter
    mfa: MFAProvider

    def execute(self, *, since=None, profile="default") -> SyncResult:
        ...
```

Each use case is a frozen dataclass with **constructor injection**. Why not just `def sync(source, repo, ...)`?

1. **Dependency inversion** — the use case depends on Protocol-typed ports, not concrete classes. Tests inject fakes (`InMemoryRepository`, `NullRateLimiter`, `EnvMFAProvider`, …). Production injects real adapters. The use case is identical.
2. **Composition root explicit** — the CLI's container (`cli/container.py`) is the one place where concrete dependencies meet abstract ports. The wiring is visible and reviewable.
3. **Frozen + immutable** — use cases are values, not stateful objects. Two parallel syncs (e.g. Garmin + Apple) construct two separate use cases; no shared state.
4. **Naming** — `SyncSourceUseCase.execute(...)` reads better than `sync_source(source, repo, ...)` and the docstring goes on the class.

The four v1 use cases:
- `SyncSourceUseCase` — incremental pull
- `BackfillSourceUseCase` — historical pull over a date range
- `HealthStatusUseCase` — reflexive snapshot across all sources
- `RenderDailyNoteUseCase` — emit a `DailyProjection` for a date

---

## File layout

| Layer | Directory | Purpose |
|---|---|---|
| domain | `src/broomva_health/domain/` | Pure Pydantic v2 — samples, metrics, source enum, results, errors, workout, device, time |
| ports | `src/broomva_health/ports/` | Protocol interfaces — `TraceSource`, `TraceRepository`, `ProjectionTarget`, `RateLimiter`, `TokenStore`, `MFAProvider`, `Clock` |
| application | `src/broomva_health/application/` | Use cases — `SyncSourceUseCase`, `BackfillSourceUseCase`, `HealthStatusUseCase`, `RenderDailyNoteUseCase` |
| adapters | `src/broomva_health/adapters/` | Concrete implementations behind ports |
| adapters/sources | `src/broomva_health/adapters/sources/` | One file per source: `garmin.py` (v1), `apple.py`, `whoop.py`, `oura.py`, `cgm.py` (v2+) |
| adapters/repositories | `src/broomva_health/adapters/repositories/` | `sqlite.py` (default), `sqlcipher.py` (v1.1 extra) |
| adapters/projections | `src/broomva_health/adapters/projections/` | `obsidian.py` (default), `healthos.py` (when healthOS subscribes) |
| adapters/token_stores | `src/broomva_health/adapters/token_stores/` | `filesystem.py` (default), `keychain.py` (optional `[keychain]` extra) |
| adapters/rate_limiters | `src/broomva_health/adapters/rate_limiters/` | `token_bucket.py` (default) |
| adapters/mfa | `src/broomva_health/adapters/mfa/` | `prompt.py`, `env.py`, `keychain.py` |
| adapters/clock | `src/broomva_health/adapters/clock.py` | `SystemClock`, `FakeClock` (tests) |
| synthesis | `src/broomva_health/synthesis/` | Derived views — `hrv.py`, `training_load.py`, `vo2max.py`. Stdlib-only. |
| migrations | `src/broomva_health/migrations/` | Numbered SQL + idempotent runner |
| config | `src/broomva_health/config/` | `HealthPaths`, `HealthSettings` (TOML + env) |
| cli | `src/broomva_health/cli/` | Typer surface (entry point), `formatters.py` (uniform `--format` flag) |

---

## Walkthrough: a `health sync` call

Concrete trace of what happens when a user runs `health sync --source garmin --format json`:

1. **CLI entry** — Typer routes to `cli/commands/sync.py::sync_command(source, since, profile, format)`.
2. **Container build** — `cli/container.py::build_container(settings)` constructs:
   - `paths = HealthPaths.discover(); paths.ensure()`
   - `repo = SQLiteTraceRepository(db_path=paths.trace_db_for("garmin"))` and calls `repo.migrate()` (idempotent)
   - `token_store = FilesystemTokenStore(tokens_dir=paths.tokens_dir)` (or `KeychainTokenStore` if `[keychain]` extra installed)
   - `rate_limiter = TokenBucketRateLimiter(min_interval_s=settings.rate_limit_min_interval_s)`
   - `mfa = build_mfa_provider(settings)` (returns one of Prompt/Env/Keychain)
   - `source_adapter = source_registry.build("garmin", settings.garmin)`
3. **Use case construction** — `use_case = SyncSourceUseCase(source=source_adapter, repo=repo, token_store=token_store, rate_limiter=rate_limiter, mfa=mfa)`
4. **Execute** — `result: SyncResult = use_case.execute(since=since, profile=profile)`. Inside:
   - `rate_limiter.acquire("garmin:sync")` — blocks if we're in the 15-min cooldown
   - `source_adapter.sync(repo=repo, token_store=token_store, rate_limiter=rate_limiter, since=since, profile=profile)`:
     - Loads token via `token_store.get(Source.GARMIN, profile)`. If missing → raises `AuthRequired`.
     - Calls `garminconnect.Garmin(...).login(token=...)`. On 401 → raises `AuthRequired`.
     - Determines per-metric start_ts via `repo.last_sample_ts(Source.GARMIN, metric)`.
     - For each metric: fetches → constructs domain samples (with canonical-unit conversion at the boundary) → `repo.upsert_quantity(samples)`.
     - For workouts: `repo.upsert_workout(workouts)`.
     - Persists refreshed token via `token_store.put(...)`.
     - Returns `SyncResult(source=Source.GARMIN, started_at=..., finished_at=..., samples_ingested=..., workouts_ingested=..., errors=[], rate_limit_remaining_s=...)`
   - On `RateLimited`: `rate_limiter.record_429(key, retry_after_s=exc.retry_after_s)` and re-raise
   - On success: `rate_limiter.record_success(key)`
5. **Format** — `print(format_value(result, fmt=format))` — `format_value` calls `result.model_dump(mode="json")` then serializes per the `--format` flag.
6. **Exit** — return `0` on success. On any `HealthError`, the CLI's top-level handler maps `exc.exit_code` to the process exit code (`1` general, `2` auth-required).

The interesting properties of this trace:
- The use case (`SyncSourceUseCase.execute`) is 18 lines. All the work is in the adapter and the ports.
- Swap the adapter for `WhoopSource` (when v2 ships) and the rest of the trace is unchanged.
- Swap `SQLiteTraceRepository` for `SQLCipherTraceRepository` (v1.1) and the use case never knew.
- A test replaces the source with a fake that returns a fixed `SyncResult` and the repo with `InMemoryTraceRepository`; the test runs in 1 ms.

This is the whole point of hex.

---

## Anti-patterns (P20-class)

| Anti-pattern | Why it breaks the model |
|---|---|
| `from broomva_health.adapters.garmin import ...` inside `application/` | Application depends on adapter — violates dependency inversion |
| `print(json.dumps(...))` inside a CLI subcommand | Skips `format_value`; users with `--format csv` get JSON anyway |
| `requests.get(...)` inside `application/` | Use cases must be pure; network calls live in adapters |
| Non-canonical unit reaching `QuantitySample(unit="bpm/min")` | Adapters convert at the boundary; domain only sees canonical units |
| Reconciliation column on a sample table | Reconciliation is a projection — see [healthkit-data-model.md](healthkit-data-model.md) |
| Use case mutating state on `self` | Use cases are frozen dataclasses; `execute` is a pure function modulo I/O via ports |

Each one is a P20 (Cross-Review) blocker.

---

## References

- Alistair Cockburn, "Hexagonal Architecture" (2005): https://alistair.cockburn.us/hexagonal-architecture/
- Vaughn Vernon, *Implementing Domain-Driven Design* (Addison-Wesley, 2013) — ch. 4 "Architecture" on ports & adapters in a DDD context
- "Clean Architecture" terminology (Robert C. Martin, 2017) — substantially the same idea with different vocabulary
- Mark Seemann, *Dependency Injection Principles, Practices, and Patterns* (Manning, 2019) — the canonical reference on constructor injection
