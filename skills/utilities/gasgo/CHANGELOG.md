# Changelog

All notable changes to the **gasgo** skill are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/); versioning: [SemVer](https://semver.org).

## [0.2.0] — 2026-07-02

### Added
- **Honest coordinate resolution.** The one live open feed (GNCV) carries
  municipal-centroid coordinates, so every station in a municipality shares one
  point and one distance. New `src/present.ts` (`formatDistance`,
  `recommendationLine`, `isMunicipalOnly`) renders municipal distances as
  `~2.6 km · municipio`, makes the recommendation say "Cheapest in
  `<municipality>`" instead of a false "N km away", and the freshness note now
  states that intra-municipality ranking is by price. Coord-less historical
  sources show `dist n/a`.
- Tests: 32 total (+15) — `present.test.ts`, `products.test.ts`, `engine.test.ts`.

### Fixed
- **Biodiesel misclassification.** `"BIODIESEL"` contains the substring
  `"DIESEL"`, so the DIESEL-first classifier silently refiled every biodiesel row
  as ACPM/diesel (533 `BIODIESEL EXTRA` rows in `gjy9-tpph`; `--product biodiesel`
  returned nothing). The BIODIESEL check now precedes ACPM/DIESEL.

### Notes (data reality, verified live 2026-07-02)
- **SICOM *consulta* is not a live feed.** `eds.sicom.gov.co/eds/api/v1/birest/precios/<code>`
  serves quarterly CSV dumps (newest = 2024 Q2); all 26 quarter codes currently
  return an empty CSV (85 bytes, header only). Even when populated it is quarterly,
  not live. Reverse-engineered spec recorded in `README.md`.
- **`ba2i-v4xx` registry is municipal-centroid, not exact-pump** (146 distinct
  points / 1746 stations; 483 share Bogotá's centroid). Registry-join roadmap item
  dropped — it adds no coordinate precision.
- **`gjy9-tpph` historical gasoline/diesel is Bogotá-only** (all rows `BOGOTA D.C.`,
  `periodo=2022`), dominated by `OXIGENADA` variants.
- Forward paths (both externally blocked): Google Places `fuelOptions` (needs a
  licensed key) or a recovered SICOM birest endpoint. Tracked in BRO-1660.

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
- Hardened via P20 cross-model adversarial review (4 blocking findings fixed).
