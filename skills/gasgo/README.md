# gasgo ⛽

**Where should I go right now for the best gas deal in Colombia?** — an engine over
live, per-station Colombian fuel-price open data.

Dependency-free core (bun + global `fetch`). No install needed to run.

```bash
bun run src/cli.ts where --city bogota --product gncv --radius 20 --top 5
```

```
⛽ gasgo — GNCV (gas natural vehicular) near Bogotá
   candidates: 65 · avg $2.734/m³ · observed 2026-07-01
   🟢 LIVE — Live automated feed (SICOM GNCV via datos.gov.co).

👉 1. ESTACIÓN DE SERVICIO PATIO USME
      $2.611/m³ · 2.6 km · BOGOTA, D.C. · saves $1.230/tank
```

## Data sources (verified live 2026-07-02)

The engine is built on the **adapter pattern** — each source normalizes to one
canonical `Observation`. The ranking core never learns a source's name.

| Source (`src/sources`) | Dataset | Fuel | Freshness | Coords |
|---|---|---|---|---|
| `he3q-86dn` (live) | SICOM GNCV via datos.gov.co (AUTOMATED) | GNCV | 🟢 **daily-ish, current** | municipal centroid |
| `gjy9-tpph` | Precio mes combustible | Gasolina/Diésel | 🟡 frozen ≈2022 | none (text address) |
| `x6id-4v3g` | Precios Combustibles | Gasolina/Diésel | 🟡 frozen 2015–2018 | none |
| SICOM *consulta* | internal endpoint | Gasolina/Diésel | 🔜 roadmap (live) | — |
| Google Places `fuelOptions` | licensed API | all | 🔜 roadmap (licensed) | station-exact |

**The core finding:** for **gasoline & diesel** there is *no* frequently-updated
open per-station feed — the open automated feed exists only for **GNCV**. gasgo
is honest about this: gasoline/diesel results are flagged `🟡 HISTORICAL`.

> ⚠️ **Socrata gotcha (encoded in `src/dates.ts`):** datos.gov.co `updatedAt`
> metadata lies (a dataset "updated 2025" can hold only 2018 data), and dates are
> non-zero-padded (`2025-9-01`) so lexical sorting is wrong. Always assert
> `max(<date field>)` and parse before comparing.

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

1. **SICOM consulta adapter** — reverse-engineer the live per-station gasoline/diesel
   endpoint (Interceptor capture) → close the gasoline/diesel liveness gap.
2. **Google Places `fuelOptions` adapter** — licensed, station-exact coords + `updateTime`.
3. **`ba2i-v4xx` station-registry join** — upgrade GNCV coords from municipal centroid to exact pump.
4. Caching layer + scheduled refresh (Railway).

Tracked in Linear **BRO-1658**.
