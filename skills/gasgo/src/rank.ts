import { haversineKm } from "./geo.ts";
import type { BestDealQuery, Observation, RankedStation } from "./types.ts";

/**
 * Rank observations for a query into best-deal order.
 *
 * Cost model — a cheaper station far away is not always the better deal:
 *   effectiveCostForTank = priceCop * tankUnits + 2 * distanceKm * costPerKmCop
 * (the round-trip detour to reach it, valued at the driver's running cost/km).
 *
 * Observations without coordinates keep distanceKm = null and pay no detour
 * penalty (we can't compute it) — they're ranked by raw price, and the caller
 * is told coords were missing so it can require a municipality filter.
 */
export function rankStations(
  observations: Observation[],
  query: BestDealQuery,
): { ranked: RankedStation[]; avgPriceCop: number | null; candidateCount: number } {
  // 1) product filter (defensive; adapters already scope by product).
  let candidates = observations.filter((o) => o.product === query.product);

  // 2) optional municipality filter (case/accent-insensitive contains).
  if (query.municipality) {
    const want = normalize(query.municipality);
    candidates = candidates.filter(
      (o) => o.municipality && normalize(o.municipality).includes(want),
    );
  }

  // 3) attach distance; radius-filter only those that HAVE coords.
  const withDist = candidates.map((o) => {
    const distanceKm =
      o.lat !== undefined && o.lng !== undefined
        ? haversineKm(query.at, { lat: o.lat, lng: o.lng })
        : null;
    return { o, distanceKm };
  });

  const hasAnyCoords = withDist.some((x) => x.distanceKm !== null);
  const inRange = withDist.filter((x) => {
    if (x.distanceKm === null) return !hasAnyCoords; // keep coord-less only when NO coords exist at all
    return x.distanceKm <= query.radiusKm;
  });

  if (inRange.length === 0) return { ranked: [], avgPriceCop: null, candidateCount: 0 };

  // Round the average ONCE and use the same value for both the displayed avg and
  // the per-station savings, so the two are always self-consistent — otherwise a
  // sub-COP fractional avg (displayed rounded) multiplied by the tank size makes
  // "avg $2.734" and "saves $1.283" disagree with (avg − price) × tank. (P20)
  const avgPriceCop = Math.round(
    inRange.reduce((sum, x) => sum + x.o.priceCop, 0) / inRange.length,
  );

  const scored = inRange.map(({ o, distanceKm }) => {
    const detour = distanceKm === null ? 0 : 2 * distanceKm * query.costPerKmCop;
    const effectiveCostForTank = o.priceCop * query.tankUnits + detour;
    const savingsVsAvgCop = (avgPriceCop - o.priceCop) * query.tankUnits;
    return { o, distanceKm, effectiveCostForTank, savingsVsAvgCop };
  });

  scored.sort((a, b) => a.effectiveCostForTank - b.effectiveCostForTank);

  const ranked: RankedStation[] = scored.slice(0, query.topN).map((x, i) => ({
    ...x.o,
    distanceKm: x.distanceKm,
    effectiveCostForTank: Math.round(x.effectiveCostForTank),
    savingsVsAvgCop: Math.round(x.savingsVsAvgCop),
    rank: i + 1,
  }));

  // candidateCount describes the SAME set the average is computed over
  // (post municipality + radius filtering), not the raw product set. (#3)
  return { ranked, avgPriceCop, candidateCount: inRange.length };
}

function normalize(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase().trim();
}
