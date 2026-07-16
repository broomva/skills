# gasgo ⛽

**Where should I go right now for the best gas deal in Colombia?** — an engine over
live, per-station Colombian fuel-price open data.

Dependency-free core (bun + global `fetch`). No install needed to run.

```bash
bun run src/cli.ts where --city bogota --product gncv --radius 20 --top 5
```

```
⛽ gasgo — GNCV (gas natural vehicular) near Bogotá
   candidates: 24 · avg $2.734/m³ · observed 2026-07-01
   🟢 LIVE — Live automated feed (SICOM GNCV via datos.gov.co). Coordinates are
   municipal centroids (no open per-station coords), so distances are approximate
   and ranking within a municipality is by price.

👉 1. ESTACIÓN DE SERVICIO PATIO USME
      $2.611/m³ · ~2.6 km · municipio · BOGOTA, D.C. · saves $1.230/tank

   👉 Cheapest: ESTACIÓN DE SERVICIO PATIO USME — $2.611/m³ in BOGOTA, D.C.
      (distance approximate — open data has only municipal-centroid coords).
```

## Data sources (verified live 2026-07-02)

The engine is built on the **adapter pattern** — each source normalizes to one
canonical `Observation`. The ranking core never learns a source's name.

| Source (`src/sources`) | Dataset | Fuel | Freshness | Coords |
|---|---|---|---|---|
| `he3q-86dn` (live) | SICOM GNCV via datos.gov.co (AUTOMATED) | GNCV | 🟢 **daily-ish, current** (obs. 2026-07-01) | municipal centroid |
| `gjy9-tpph` | Precio mes combustible | Gasolina/Diésel | 🟡 frozen ≈2022, **Bogotá-only** | none (text address) |
| `x6id-4v3g` | Precios Combustibles | Gasolina/Diésel | 🟡 frozen 2015–2018 | none |
| SICOM *consulta* (birest) | `eds.sicom.gov.co/.../precios/<code>` | Gasolina/Diésel | ⛔ **empty as of 2026-07-02** (see below) | none |
| `ba2i-v4xx` registry | station registry | — | current | ⚠️ **municipal centroid, not exact** |
| Google Places `fuelOptions` | licensed API | all | 🔜 roadmap (needs API key) | station-exact |

**The core finding:** for **gasoline & diesel** there is *no* frequently-updated
open per-station feed — the only open automated feed is **GNCV** (`he3q-86dn`).
gasgo is honest about this: gasoline/diesel results are flagged `🟡 HISTORICAL`,
and even GNCV distances are shown as approximate (see *Coordinate resolution*).

**Two roadmap premises were empirically disproven (2026-07-02):**

- **SICOM *consulta* is not a live feed.** The `consulta de precios` page drives
  `https://eds.sicom.gov.co/eds/api/v1/birest/precios/<code>` — **quarterly** CSV
  dumps (`BANDERA,NOMBRE COMERCIAL,PRODUCTO,FECHA REGISTRO,DEPARTAMENTO,MUNICIPIO,VALOR PRECIO`),
  newest code = 2024 Q2. All 26 quarter codes currently return an **empty CSV
  (85 bytes, header only)** — a clean `200 OK` with `content-length: 85`, so the
  backend data layer is empty, not blocked. Even when populated it is quarterly
  (≤ 2024 Q2), *not* live. Code map: 2018 `1/2/3/4` · 2019 `10/20/30/40` · 2020
  `100/200/300/400` · then `+1` per year on the last digit (2024 = `104/204`).
- **`ba2i-v4xx` has no exact pump coordinates.** Only 146 distinct `(lat,lng)`
  pairs across 1746 stations; 483 share Bogotá's centroid `(4.64925,-74.107)` —
  the *same* value `he3q-86dn` already uses. Joining it upgrades nothing.

So the only paths to fresher/exact data need an external prerequisite: a working
SICOM birest (upstream fix) or a licensed **Google Places `fuelOptions`** key.

### Coordinate resolution

The one live feed (GNCV) carries **municipal-centroid** coordinates, so every
station in a municipality shares one point and one distance. gasgo does not fake
precision it doesn't have: municipal distances render as `~2.6 km · municipio`,
the recommendation says *"Cheapest in `<municipality>`"* rather than "N km away",
and within a municipality the ranking is honestly **by price**. Coord-less
historical sources show `dist n/a`.

> ⚠️ **Socrata gotcha (encoded in `src/dates.ts`):** datos.gov.co `updatedAt`
> metadata lies (`gjy9-tpph` reports `updatedAt=2026-05-18` but every row is
> `periodo=2022`), and dates are non-zero-padded (`2025-9-01`) so lexical sorting
> is wrong. Always assert `max(<date field>)` and parse before comparing.
>
> ⚠️ **Product-label gotcha (encoded in `src/products.ts`):** `"BIODIESEL"`
> contains the substring `"DIESEL"`, so the BIODIESEL check must precede the
> ACPM/DIESEL check or 533 biodiesel rows get silently misfiled as diesel.

## Architecture

```
CLI ─▶ engine.bestDeal(query)
          ├─ sources/adapters.fetchObservations(product)   ← Socrata SODA
          │     └─ sources/socrata.socrataFetch(id, soql)
          └─ rank.rankStations(observations, query)         ← price + distance
                └─ geo.haversineKm()
```

Ranking cost model — a cheaper station far away isn't always the better deal:

```
effectiveCostForTank = priceCop * tankUnits + 2 * distanceKm * costPerKmCop
```

## CLI

```
gasgo where --city <name> --product <p> [--radius km] [--top n]
            [--tank units] [--cost-per-km cop] [--municipality name] [--json]
            [--lat n --lng n]   # instead of --city
```

- **Products:** `gncv` (live) · `corriente` · `extra` · `diesel` · `biodiesel` (historical)
- **Cities:** bogota · medellin · cali · barranquilla · cucuta · bucaramanga · pereira

Set `SODA_APP_TOKEN` (free from datos.gov.co) to lift the anonymous rate limit.

## Test

```bash
bun test          # unit: geo, dates (the gotcha), ranking
```

## Roadmap

Ordered by *value ÷ blocker*. The 2026-07-02 probes (above) reset the top items:

1. **Google Places `fuelOptions` adapter** — the only path to *both* exact
   per-station coords *and* fresher gasoline/diesel. **Blocked on:** a licensed
   API key + a CO-coverage probe (~20 Bogotá/Medellín/Cúcuta stations) before
   committing. Emits `Observation` with `geoResolution: "station"`.
2. **SICOM birest adapter** — fetch the newest non-empty `precios/<code>` quarter
   → `Observation` (`isLive:false`, `observedAt` from `FECHA REGISTRO`), fall back
   to the 2022 Socrata data otherwise. **Blocked on:** the endpoint returning rows
   (empty for every quarter as of 2026-07-02). Even unblocked it is quarterly
   (≤ 2024 Q2), not live — a *fresher-historical* upgrade, not a liveness fix.
3. **Caching layer + scheduled refresh** (Railway) — persist the live GNCV feed
   and serve a small API/dashboard.

**Dropped:** the `ba2i-v4xx` station-registry join — the registry is
municipal-centroid, not exact-pump, so it adds no coordinate precision (proven
2026-07-02).

Tracked in Linear **BRO-1658** (v0.1) → **BRO-1660** (v0.2).
