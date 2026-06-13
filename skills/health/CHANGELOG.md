# Changelog

All notable changes to the `health` skill are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versioning is per-skill within the `broomva/skills` monorepo; releases are tagged
`health-vX.Y.Z`.

## [Unreleased]

## [0.9.0] — 2026-06-13

### Added

- **`health series` command** — structured metric time-series, the retrieval
  layer between `context` (latest-in-window snapshot) and `raw` (verbatim JSON).
  Un-bucketed returns every sample (uncapped); `--bucket day|week|month|quarter|year`
  with `--agg mean|sum|min|max|first|last|count` computes processed/enriched
  aggregates at query time.

## [0.8.0] — 2026-06-12

### Added

- **Lossless raw-passthrough layer** — a `raw_document` store (migration `003`)
  persists every upstream response verbatim alongside the curated structured
  metrics, so the agent can reach any field the mapping drops (Garmin's daily
  summary is ~94 fields where ~5 are typed; sleep carries `sleepLevels`/`hrvData`;
  stress carries the intraday array).
- **`health raw` command** — emits verbatim documents for a date range,
  optionally filtered by `--endpoint`; uncapped within range.
- `RawDocument` domain model + `TraceRepository.upsert_raw_document` /
  `query_raw_documents`. Raw is captured on every `sync` and `backfill`.

## [0.7.0] — 2026-06-12

### Added

- **`health synthesis` command** — exposes the derived-metrics service over the
  CLI (HRV-CV, Coggan CTL/ATL/TSB, VO2max quarterly arc, recovery composite),
  computed by traversing the full trace history. Also added as a `synthesis`
  section to the `context` document.

### Fixed

- SKILL.md advertised `context --metric … --bucket …` flags that never existed;
  replaced with the real `health synthesis` interface. Documented that the
  per-metric `health`/`training`/`weight` query commands are v1 stubs.

### Known limitations

- CTL/ATL/TSB read `0` until per-activity TSS is derived (Garmin's activity
  *summary* omits it).

## [0.6.0] — 2026-06-12

### Added

- `health backfill --months N` / `--days N` conveniences alongside `--from/--to`.

### Fixed

- **Historical backfill correctness (4 bugs):** activities now backfill via a
  date-ranged windowed search (was re-pulling the recent set every day); each
  day is explicitly anchored so historical days with empty body-battery no longer
  collapse onto today's upsert key; `end_ts` is clamped to the day boundary; and
  backfill is decoupled from the 15-minute sync poll-floor (it no longer dies on
  day 2 / blocks after a recent sync), pacing itself gently instead.

## [0.5.0] — 2026-06-12

### Added

- **Complete daily ingest (+7 metrics):** stress, SpO2, respiration, sleep-score,
  weight / BMI / body-fat / lean-mass, hydration — 10 → 17 daily metric types.

## [0.4.1] — 2026-06-12

### Security

- **Relocated the biometric trace store out of the workspace git repo** to a
  dedicated `~/broomva-health/` (mode `0700`), a sibling of the Obsidian vault.
  `doctor` warns + prints a migration command if data is found in the old
  in-repo location.

## [0.4.0] — 2026-06-12

### Added

- **In-house native Garmin backend (`native`, default)** — calls Garmin's
  `connectapi` directly through `garth`, riding an existing OAuth token (no
  fresh-login Cloudflare wall). Owns aggregation, mapping, and token lifecycle;
  `health auth import` bootstraps from an existing garth token.

## [0.3.0] — 2026-06-12

### Added

- **`GarminCliTraceSource` (`cli` backend)** — delegates to the maintained
  `eddmann/garmin-connect` CLI as a backend option, with a shared context mapper.
- Backend selection via `[garmin] backend` config (`native` | `cli` | `library`).

## [0.2.3] — earlier

### Added

- Initial skill: hexagonal architecture (domain → ports → application → adapters
  → CLI), Pydantic v2 domain models + `MetricCode` registry, SQLite trace
  repository with migrations, token-bucket rate limiter, filesystem token store,
  `sync` / `backfill` / `status` / `doctor` / `context` commands, Obsidian
  daily-note projection, and the synthesis modules (HRV-CV, CTL/ATL/TSB,
  VO2max arc, recovery).

[Unreleased]: https://github.com/broomva/skills/compare/health-v0.9.0...HEAD
[0.9.0]: https://github.com/broomva/skills/releases/tag/health-v0.9.0
[0.8.0]: https://github.com/broomva/skills/releases/tag/health-v0.8.0
[0.7.0]: https://github.com/broomva/skills/releases/tag/health-v0.7.0
[0.6.0]: https://github.com/broomva/skills/releases/tag/health-v0.6.0
[0.5.0]: https://github.com/broomva/skills/releases/tag/health-v0.5.0
[0.4.1]: https://github.com/broomva/skills/releases/tag/health-v0.4.1
[0.4.0]: https://github.com/broomva/skills/releases/tag/health-v0.4.0
[0.3.0]: https://github.com/broomva/skills/releases/tag/health-v0.3.0
