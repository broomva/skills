/**
 * Presentation helpers — pure, testable string formatting for the CLI.
 *
 * These live apart from cli.ts so the honesty rules (never imply a precision
 * the data doesn't have) are unit-testable without running the CLI.
 *
 * The core honesty rule (verified live 2026-07-02): the only live open feed —
 * GNCV via he3q-86dn — carries *municipal-centroid* coordinates, not per-station
 * ones. No open dataset has exact per-station GNCV coords (ba2i-v4xx, the
 * supposed "exact" registry, is itself centroid-based: 146 distinct points for
 * 1746 stations). So within a municipality every station shares one point and
 * the same distance. Presenting "2.6 km" per station implies a precision that
 * does not exist.
 *
 * Fail-safe rule: a distance is claimed as EXACT only when the source explicitly
 * tags `geoResolution: "station"`. Any other value — "municipality" or a missing
 * tag on a future adapter — hedges. That way a new source that forgets to set the
 * resolution can never silently defeat the honesty guarantee.
 */

import type { RankedStation } from "./types.ts";

type Located = Pick<RankedStation, "distanceKm" | "geoResolution">;

/** True only when the source vouches for exact per-station coordinates. */
function isExact(s: Located): boolean {
  return s.geoResolution === "station";
}

/** Collapse an accidental double sentence-terminator ("D.C.." → "D.C."). */
function tidy(line: string): string {
  return line.replace(/\.\.$/, ".");
}

/**
 * Human distance string that is honest about coordinate resolution.
 *   station-resolution      → "2.6 km"              (exact — vouched)
 *   municipality-resolution → "~2.6 km · municipio" (centroid approximation)
 *   unknown resolution      → "~2.6 km · aprox"     (hedged — never claim exact)
 *   no coordinates          → "dist n/a"
 */
export function formatDistance(s: Located): string {
  if (s.distanceKm === null) return "dist n/a";
  const km = s.distanceKm.toFixed(1);
  if (isExact(s)) return `${km} km`;
  if (s.geoResolution === "municipality") return `~${km} km · municipio`;
  return `~${km} km · aprox`;
}

/**
 * The final one-line recommendation, honest about resolution.
 *   exact coords    → "Go to: <name> — <price>, 2.6 km away."
 *   any hedged dist → "Cheapest: <name> — <price> in <municipality> (distance
 *                      approximate — open data has only municipal-centroid coords)."
 *   no coords       → "Cheapest: <name> — <price> in <municipality>."
 */
export function recommendationLine(best: RankedStation, priceStr: string): string {
  const where = best.municipality ? ` in ${best.municipality}` : "";
  if (isExact(best) && best.distanceKm !== null) {
    return tidy(
      `👉 Go to: ${best.stationName} — ${priceStr}, ${best.distanceKm.toFixed(1)} km away.`,
    );
  }
  if (best.distanceKm !== null) {
    return tidy(
      `👉 Cheapest: ${best.stationName} — ${priceStr}${where} (distance approximate — open data has only municipal-centroid coords).`,
    );
  }
  return tidy(`👉 Cheapest: ${best.stationName} — ${priceStr}${where}.`);
}
