/**
 * Canonical types for the gasgo engine.
 *
 * The whole engine speaks one vocabulary — the `Observation` — regardless of
 * which source produced it. New sources (SICOM consulta, Google Places
 * fuelOptions, brand apps) become adapters that emit `Observation[]`; the
 * ranking core never learns their names.
 */

/** Normalized fuel product across all Colombian sources. */
export type Product =
  | "GNCV" // Gas Natural Comprimido Vehicular (compressed natural gas)
  | "GASOLINA_CORRIENTE"
  | "GASOLINA_EXTRA"
  | "ACPM_DIESEL"
  | "BIODIESEL";

export const PRODUCTS: Product[] = [
  "GNCV",
  "GASOLINA_CORRIENTE",
  "GASOLINA_EXTRA",
  "ACPM_DIESEL",
  "BIODIESEL",
];

/** A geographic point. */
export interface Coord {
  lat: number;
  lng: number;
}

/**
 * A single per-station price observation, normalized.
 * `lat`/`lng` may be undefined when a source carries only a text address.
 */
export interface Observation {
  /** e.g. "socrata:he3q-86dn" — traceable provenance. */
  source: string;
  stationName: string;
  brand?: string;
  address?: string;
  /** DANE municipality code — the cross-source join key. */
  daneCode?: string;
  municipality?: string;
  department?: string;
  lat?: number;
  lng?: number;
  product: Product;
  priceCop: number;
  /** ISO date (YYYY-MM-DD) the price was observed/reported. */
  observedAt: string;
  /**
   * Whether the source updates on an automated/live cadence.
   * true  → he3q-86dn (CNG, automated).
   * false → frozen historical snapshots (gasoline/diesel 2018/2022).
   */
  isLive: boolean;
  /** Coordinate resolution — 'station' (exact) or 'municipality' (centroid). */
  geoResolution?: "station" | "municipality";
}

/** A ranked candidate returned by the engine. */
export interface RankedStation extends Observation {
  /** Great-circle distance from the query point, km. `null` if coords absent. */
  distanceKm: number | null;
  /** priceCop * tankUnits + round-trip detour cost. Lower is better. */
  effectiveCostForTank: number;
  /** (avgPrice − priceCop) * tankUnits vs the candidate set. Positive = below average. */
  savingsVsAvgCop: number;
  /** Rank position (1 = best deal). */
  rank: number;
}

/** Query the engine answers. */
export interface BestDealQuery {
  at: Coord;
  product: Product;
  /** Search radius in km (ignored for coord-less sources). Default 10. */
  radiusKm: number;
  /** How many recommendations to return. Default 5. */
  topN: number;
  /** Units per fill (gallons for gasoline, m³ for GNCV). Default 10. */
  tankUnits: number;
  /** Running cost per km in COP, used for the detour penalty. Default 350. */
  costPerKmCop: number;
  /** Optional municipality filter (name), used by coord-less history sources. */
  municipality?: string;
}

/** Full engine answer. */
export interface BestDealResult {
  query: BestDealQuery;
  /** The winning recommendation, or null if no data. */
  best: RankedStation | null;
  ranked: RankedStation[];
  /** Candidate-set average price (COP), for context. */
  avgPriceCop: number | null;
  /** Total candidates considered after filtering. */
  candidateCount: number;
  /** Data freshness note surfaced to the user. */
  freshness: {
    observedAt: string | null;
    isLive: boolean;
    source: string;
    note: string;
  };
}
