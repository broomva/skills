#!/usr/bin/env bun
/**
 * gasgo CLI — where should I go right now for the best gas deal?
 *
 * Usage:
 *   bun run src/cli.ts where --city bogota --product gncv
 *   bun run src/cli.ts where --lat 4.65 --lng -74.1 --product gncv --radius 8 --top 5
 *   bun run src/cli.ts where --city medellin --product corriente --json
 *
 * Flags:
 *   --lat, --lng     query coordinates (or use --city)
 *   --city           preset: bogota|medellin|cali|barranquilla|cucuta|bucaramanga|pereira
 *   --product        gncv|corriente|extra|diesel|biodiesel   (default gncv — the live feed)
 *   --radius         search radius km (default 10)
 *   --top            number of recommendations (default 5)
 *   --tank           units per fill (default 10)
 *   --cost-per-km    running cost COP/km for the detour penalty (default 350)
 *   --municipality   filter by municipality name (needed for coord-less history)
 *   --json           machine-readable output
 */

import { bestDeal } from "./engine.ts";
import { normalizeProduct, productLabel, productUnit } from "./products.ts";
import type { Coord, Product } from "./types.ts";

const CITY_PRESETS: Record<string, Coord & { name: string }> = {
  bogota: { lat: 4.6533, lng: -74.0836, name: "Bogotá" },
  medellin: { lat: 6.2442, lng: -75.5812, name: "Medellín" },
  cali: { lat: 3.4516, lng: -76.532, name: "Cali" },
  barranquilla: { lat: 10.9685, lng: -74.7813, name: "Barranquilla" },
  cucuta: { lat: 7.8939, lng: -72.5078, name: "Cúcuta" },
  bucaramanga: { lat: 7.1193, lng: -73.1227, name: "Bucaramanga" },
  pereira: { lat: 4.8143, lng: -75.6946, name: "Pereira" },
};

interface Args {
  [k: string]: string | boolean;
}

function parseArgs(argv: string[]): { cmd: string; args: Args } {
  const [cmd = "where", ...rest] = argv;
  const args: Args = {};
  for (let i = 0; i < rest.length; i++) {
    const tok = rest[i];
    if (tok.startsWith("--")) {
      const key = tok.slice(2);
      const next = rest[i + 1];
      if (next === undefined || next.startsWith("--")) {
        args[key] = true;
      } else {
        args[key] = next;
        i++;
      }
    }
  }
  return { cmd, args };
}

function cop(n: number): string {
  return `$${Math.round(n).toLocaleString("es-CO")}`;
}

/**
 * Read a numeric flag safely. Returns undefined when absent; THROWS on a
 * missing value (`--radius` with no arg → boolean true) or a non-numeric value,
 * instead of silently coercing to 1 / NaN. (Cross-review #5.)
 */
function numFlag(args: Args, key: string): number | undefined {
  const v = args[key];
  if (v === undefined) return undefined;
  if (typeof v === "boolean") throw new Error(`Flag --${key} needs a numeric value.`);
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`Flag --${key} must be a number, got "${v}".`);
  return n;
}

function resolveCoord(args: Args): { at: Coord; label: string } {
  if (typeof args.city === "string") {
    const key = args.city.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    const preset = CITY_PRESETS[key];
    if (!preset) {
      throw new Error(
        `Unknown --city "${args.city}". Known: ${Object.keys(CITY_PRESETS).join(", ")}. Or pass --lat/--lng.`,
      );
    }
    return { at: { lat: preset.lat, lng: preset.lng }, label: preset.name };
  }
  const lat = numFlag(args, "lat");
  const lng = numFlag(args, "lng");
  if (lat === undefined || lng === undefined) {
    throw new Error("Provide --city <name> or --lat <n> --lng <n>.");
  }
  return { at: { lat, lng }, label: `${lat.toFixed(4)}, ${lng.toFixed(4)}` };
}

async function run(): Promise<void> {
  const { cmd, args } = parseArgs(process.argv.slice(2));
  if (cmd === "help" || args.help) {
    console.log(HELP);
    return;
  }
  if (cmd !== "where") {
    console.error(`Unknown command "${cmd}". Try: gasgo where --city bogota --product gncv`);
    process.exit(2);
  }

  const productRaw = typeof args.product === "string" ? args.product : "gncv";
  const product = normalizeProduct(productRaw) as Product | null;
  if (!product) {
    console.error(`Unknown --product "${productRaw}". Try: gncv | corriente | extra | diesel | biodiesel`);
    process.exit(2);
  }

  const { at, label } = resolveCoord(args);

  const result = await bestDeal({
    at,
    product,
    radiusKm: numFlag(args, "radius"),
    topN: numFlag(args, "top"),
    tankUnits: numFlag(args, "tank"),
    costPerKmCop: numFlag(args, "cost-per-km"),
    municipality: typeof args.municipality === "string" ? args.municipality : undefined,
  });

  if (args.json) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  const unit = productUnit(product);
  console.log(`\n⛽ gasgo — ${productLabel(product)} near ${label}`);
  console.log(`   candidates: ${result.candidateCount} · avg ${result.avgPriceCop ? cop(result.avgPriceCop) : "—"}/${unit} · observed ${result.freshness.observedAt ?? "—"}`);
  console.log(`   ${result.freshness.isLive ? "🟢 LIVE" : "🟡 HISTORICAL"} — ${result.freshness.note}`);

  if (!result.best) {
    console.log("\n   No stations found in range. Widen --radius, set --municipality, or try --city.\n");
    return;
  }

  console.log("");
  for (const s of result.ranked) {
    const dist = s.distanceKm === null ? "dist n/a" : `${s.distanceKm.toFixed(1)} km`;
    const save =
      s.savingsVsAvgCop > 0 ? `saves ${cop(s.savingsVsAvgCop)}/tank` : `${cop(-s.savingsVsAvgCop)} over avg`;
    const marker = s.rank === 1 ? "👉" : "  ";
    console.log(
      `${marker} ${s.rank}. ${s.stationName}${s.brand ? ` [${s.brand}]` : ""}`,
    );
    console.log(
      `      ${cop(s.priceCop)}/${unit} · ${dist} · ${s.municipality ?? "?"} · ${save}`,
    );
  }
  const b = result.best;
  console.log(
    `\n   👉 Go to: ${b.stationName} — ${cop(b.priceCop)}/${unit}${b.distanceKm !== null ? `, ${b.distanceKm.toFixed(1)} km away` : ""}.\n`,
  );
}

const HELP = `gasgo — best gas deal near you (Colombia, live open data)

  gasgo where --city bogota --product gncv
  gasgo where --lat 4.65 --lng -74.08 --product gncv --radius 8 --top 5
  gasgo where --city medellin --product corriente --municipality medellin --json

Products: gncv (live) | corriente | extra | diesel | biodiesel (historical)
Cities:   ${Object.keys(CITY_PRESETS).join(" | ")}
`;

run().catch((err) => {
  console.error(`gasgo error: ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
});
