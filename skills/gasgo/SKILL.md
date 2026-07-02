---
name: gasgo
version: 0.1.0
source: https://github.com/broomva/skills/tree/main/skills/gasgo
description: Answer "where should I go right now for the best gas deal in Colombia?" — an engine over live, per-station Colombian fuel-price open data (SICOM GNCV via datos.gov.co Socrata, plus historical gasoline/diesel). Ranks nearby stations by a price + distance cost model and returns a best-deal recommendation with an explicit freshness verdict (🟢 live GNCV vs 🟡 historical gasoline/diesel). Dependency-free bun core. USE WHEN the user asks where to buy the cheapest gas/fuel/GNCV near a Colombian location, wants to compare station prices, or wants to build/extend fuel-price ingestion. NOT FOR non-Colombian markets or real-time gasoline/diesel (open data is GNCV-only live; gasoline/diesel is frozen ≈2022 until the SICOM-consulta/Google-Places adapters land).
author: broomva
license: MIT
tags: [colombia, fuel, gas-prices, gncv, socrata, datos-gov-co, sicom, open-data, geo-ranking, adapter-pattern]
---

# gasgo — best gas deal near me (Colombia)

Engine that answers **"where should I go right now for the best gas deal?"** using
live per-station Colombian fuel-price open data.

## Install

```bash
npx skills add broomva/skills --skill gasgo
```

## Invoke

```bash
bun run src/cli.ts where --city bogota --product gncv --radius 20 --top 5
bun run src/cli.ts where --lat 4.65 --lng -74.08 --product gncv
bun run src/cli.ts where --city medellin --product corriente --municipality medellin --json
```

Programmatic:

```ts
import { bestDeal } from "./src/engine.ts";
const res = await bestDeal({ at: { lat: 4.65, lng: -74.08 }, product: "GNCV" });
```

- **Products:** `gncv` (live) · `corriente` · `extra` · `diesel` · `biodiesel` (historical)
- **Cities:** bogota · medellin · cali · barranquilla · cucuta · bucaramanga · pereira
- Set `SODA_APP_TOKEN` to lift the anonymous Socrata rate limit.

See `README.md` for the data-source table, ranking model, gotchas, and roadmap.

## Tests

```bash
bun test   # geo, date-gotcha, ranking (10/10)
```
