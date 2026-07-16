/**
 * Source adapters. Each returns normalized `Observation[]` for a product.
 *
 * Registry of datasets (verified live on datos.gov.co, 2026-07-02):
 *   he3q-86dn  GNCV per-station, AUTOMATED/LIVE, 2022→2026, municipal coords.
 *   gjy9-tpph  gasoline/diesel per-station monthly avg — FROZEN at 2022.
 *   x6id-4v3g  gasoline/diesel per-station — FROZEN 2015–2018 (deep history).
 *
 * The GNCV adapter is the live path. Gasoline/diesel adapters are honest
 * about their staleness via `isLive: false` so the engine can flag it.
 */

import { parseSocrataDate, toIsoDate } from "../dates.ts";
import { normalizeProduct } from "../products.ts";
import type { Observation, Product } from "../types.ts";
import { type SocrataOptions, socrataFetch } from "./socrata.ts";

export const DATASETS = {
  gncvLive: "he3q-86dn",
  gasolineMonthly: "gjy9-tpph",
  gasolineHistory: "x6id-4v3g",
} as const;

// The full GNCV dataset is ~11k rows; one request covers it. If it ever grows
// past this, add keyset pagination on fecha_precio (see roadmap in README).
const MAX_ROWS = 50000;

/**
 * Parse a COP price string to a number, defensively.
 * Observed values are plain integers ("2611"), but guard the Colombian
 * thousands-dot ("12.345" → 12345) and comma-decimal ("12345,67") cases so a
 * text column can't silently produce a 1000×-too-low price. (Cross-review #6.)
 */
export function parseCop(raw: string | undefined): number {
  if (raw === undefined || raw === null) return Number.NaN;
  const s = String(raw).trim();
  if (/^\d{1,3}(\.\d{3})+$/.test(s)) return Number(s.replace(/\./g, "")); // 12.345 → 12345
  if (/^\d+,\d+$/.test(s)) return Number(s.replace(",", ".")); // 12345,67 → 12345.67
  return Number(s);
}

function stationKey(o: Observation): string {
  return `${o.stationName}|${o.municipality ?? ""}|${o.address ?? ""}`;
}

/**
 * Keep only the newest observation per station (by ISO observedAt).
 * Prevents a station's old cheap month from competing with its recent price.
 * (Cross-review #4.) observedAt is zero-padded ISO, so string compare is safe.
 */
export function dedupeLatestPerStation(observations: Observation[]): Observation[] {
  const best = new Map<string, Observation>();
  for (const o of observations) {
    const k = stationKey(o);
    const cur = best.get(k);
    if (!cur || o.observedAt > cur.observedAt) best.set(k, o);
  }
  return [...best.values()];
}

interface GncvRow {
  fecha_precio?: string;
  anio_precio?: string;
  departamento_eds?: string;
  municipio_eds?: string;
  nombre_comercial_eds?: string;
  precio_promedio_publicado?: string;
  tipo_combustible?: string;
  codigo_municipio_dane?: string;
  latitud_municipio?: string;
  longitud_municipio?: string;
}

/**
 * Live GNCV per-station prices from he3q-86dn.
 *
 * Fetches the whole (small) dataset and selects the GLOBAL latest date
 * client-side. This is robust to (a) non-padded dates and (b) a freshly-landed
 * partition whose rows momentarily lack a usable date — we fall back to the
 * newest date that actually has data instead of reporting "no data".
 * (Cross-review #1 + #2 + #7.)
 */
export async function fetchGncvLive(opts: SocrataOptions = {}): Promise<Observation[]> {
  const rows = await socrataFetch<GncvRow>(DATASETS.gncvLive, { $limit: MAX_ROWS }, opts);
  const dated = rows
    .filter((r) => r.fecha_precio)
    .map((r) => ({ r, t: parseSocrataDate(r.fecha_precio as string).getTime() }))
    .filter((x) => Number.isFinite(x.t)); // one malformed date must not poison the max
  if (dated.length === 0) return [];
  const maxT = Math.max(...dated.map((x) => x.t));
  const latest = dated.filter((x) => x.t === maxT).map((x) => x.r);
  return latest.flatMap(gncvRowToObservation);
}

function gncvRowToObservation(r: GncvRow): Observation[] {
  const price = parseCop(r.precio_promedio_publicado);
  const name = r.nombre_comercial_eds?.trim();
  if (!name || !Number.isFinite(price) || price <= 0) return [];
  const lat = r.latitud_municipio ? Number(r.latitud_municipio) : undefined;
  const lng = r.longitud_municipio ? Number(r.longitud_municipio) : undefined;
  return [
    {
      source: `socrata:${DATASETS.gncvLive}`,
      stationName: name,
      daneCode: r.codigo_municipio_dane,
      municipality: r.municipio_eds?.trim(),
      department: r.departamento_eds?.trim(),
      lat: Number.isFinite(lat) ? lat : undefined,
      lng: Number.isFinite(lng) ? lng : undefined,
      product: "GNCV",
      priceCop: price,
      observedAt: r.fecha_precio ? toIsoDate(r.fecha_precio) : `${r.anio_precio}-01-01`,
      isLive: true,
      geoResolution: "municipality",
    },
  ];
}

interface GasolineRow {
  periodo?: string;
  mes?: string;
  departamento?: string;
  municipio?: string;
  codigo_municipio?: string;
  nombre_comercial?: string;
  bandera?: string;
  direccion?: string;
  producto?: string;
  precio?: string;
  estado?: string;
}

/**
 * Gasoline/diesel per-station prices from gjy9-tpph (monthly avg).
 * NOTE: frozen ≈2022 — returned with isLive:false. No coordinates (text
 * address only), so the engine ranks these by price within a municipality.
 * Deduped to the newest month per station so a station's stale cheap month
 * can't win the ranking. (Cross-review #4.)
 */
export async function fetchGasolineMonthly(
  product: Product,
  opts: SocrataOptions = {},
): Promise<Observation[]> {
  const rows = await socrataFetch<GasolineRow>(DATASETS.gasolineMonthly, { $limit: MAX_ROWS }, opts);
  const all = rows.flatMap((r) => gasolineRowToObservation(r, product));
  return dedupeLatestPerStation(all);
}

function gasolineRowToObservation(r: GasolineRow, want: Product): Observation[] {
  const canonical = r.producto ? normalizeProduct(r.producto) : null;
  if (canonical !== want) return [];
  const price = parseCop(r.precio);
  const name = r.nombre_comercial?.trim();
  if (!name || !Number.isFinite(price) || price <= 0) return [];
  const month = (r.mes ?? "1").padStart(2, "0");
  return [
    {
      source: `socrata:${DATASETS.gasolineMonthly}`,
      stationName: name,
      brand: r.bandera?.trim(),
      address: r.direccion?.trim(),
      daneCode: r.codigo_municipio,
      municipality: r.municipio?.trim(),
      department: r.departamento?.trim(),
      product: canonical,
      priceCop: price,
      observedAt: `${r.periodo ?? "2022"}-${month}-01`,
      isLive: false,
    },
  ];
}

/**
 * Fetch observations for a product from the best available source.
 * GNCV → live; gasoline/diesel → monthly (historical).
 */
export async function fetchObservations(
  product: Product,
  opts: SocrataOptions = {},
): Promise<Observation[]> {
  if (product === "GNCV") return fetchGncvLive(opts);
  return fetchGasolineMonthly(product, opts);
}
