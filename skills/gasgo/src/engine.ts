/**
 * gasgo engine — "where should I go right now for the best gas deal?"
 *
 * Pipeline: fetch (source adapter) → rank (price + distance) → result with a
 * freshness verdict. Pure orchestration; sources and ranking are separate.
 */

import { fetchObservations } from "./sources/adapters.ts";
import type { SocrataOptions } from "./sources/socrata.ts";
import { rankStations } from "./rank.ts";
import type { BestDealQuery, BestDealResult, Observation } from "./types.ts";

export const DEFAULTS = {
  radiusKm: 10,
  topN: 5,
  tankUnits: 10,
  costPerKmCop: 350,
} as const;

export function makeQuery(partial: Partial<BestDealQuery> & Pick<BestDealQuery, "at" | "product">): BestDealQuery {
  return {
    radiusKm: partial.radiusKm ?? DEFAULTS.radiusKm,
    topN: partial.topN ?? DEFAULTS.topN,
    tankUnits: partial.tankUnits ?? DEFAULTS.tankUnits,
    costPerKmCop: partial.costPerKmCop ?? DEFAULTS.costPerKmCop,
    municipality: partial.municipality,
    at: partial.at,
    product: partial.product,
  };
}

/**
 * Core entry point. Fetches from the appropriate source and ranks.
 * @param fetchOpts optional Socrata options (token, injectable fetch for tests)
 */
export async function bestDeal(
  input: Partial<BestDealQuery> & Pick<BestDealQuery, "at" | "product">,
  fetchOpts: SocrataOptions = {},
): Promise<BestDealResult> {
  const query = makeQuery(input);
  const observations = await fetchObservations(query.product, fetchOpts);
  return rankObservations(observations, query);
}

/**
 * Rank a pre-fetched observation set (used by tests and by callers that
 * cache the fetch). Kept separate so ranking is testable without network.
 */
export function rankObservations(
  observations: Observation[],
  query: BestDealQuery,
): BestDealResult {
  const { ranked, avgPriceCop, candidateCount } = rankStations(observations, query);
  const best = ranked[0] ?? null;

  const anyLive = observations.some((o) => o.isLive);
  const observedAt = best?.observedAt ?? observations[0]?.observedAt ?? null;
  const source = best?.source ?? observations[0]?.source ?? "none";
  const note = anyLive
    ? "Live automated feed (SICOM GNCV via datos.gov.co)."
    : "Historical snapshot — gasoline/diesel open data is frozen (≈2022). Treat as reference, not live. Live gasoline/diesel needs the SICOM consulta or Google Places adapter (roadmap).";

  return {
    query,
    best,
    ranked,
    avgPriceCop,
    candidateCount,
    freshness: { observedAt, isLive: anyLive, source, note },
  };
}
