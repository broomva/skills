# Changelog

All notable changes to the **gasgo** skill are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/); versioning: [SemVer](https://semver.org).

## [0.1.0] — 2026-07-02

### Added
- Initial release. Engine answering "where should I go right now for the best
  gas deal in Colombia?" over live per-station fuel-price open data.
- Socrata SODA client + source adapters (`he3q-86dn` live GNCV; `gjy9-tpph` /
  `x6id-4v3g` historical gasoline/diesel), canonical `Observation` model.
- Best-deal ranking: price + round-trip detour cost model; haversine geo.
- CLI (`src/cli.ts`) with city presets and `--json`; freshness verdict
  (🟢 live GNCV vs 🟡 historical gasoline/diesel).
- Encodes two Socrata gotchas as code: `updatedAt`-metadata-lies (assert
  `max(date)`) and non-zero-padded dates.
- Tests: 17 (geo, date parsing, ranking, dedupe, COP parsing).

### Notes
- Only GNCV has a live open feed; gasoline/diesel open data is frozen (≈2022)
  and flagged as historical. SICOM-consulta and Google Places `fuelOptions`
  adapters (live gasoline/diesel) are on the roadmap.
- Hardened via P20 cross-model adversarial review (4 blocking findings fixed).
