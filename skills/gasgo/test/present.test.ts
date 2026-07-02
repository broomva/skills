import { expect, test } from "bun:test";
import { formatDistance, recommendationLine } from "../src/present.ts";
import type { RankedStation } from "../src/types.ts";

function ranked(partial: Partial<RankedStation>): RankedStation {
  return {
    source: "test",
    stationName: "S",
    product: "GNCV",
    priceCop: 2611,
    observedAt: "2026-07-01",
    isLive: true,
    distanceKm: 2.6,
    effectiveCostForTank: 26110,
    savingsVsAvgCop: 1230,
    rank: 1,
    ...partial,
  };
}

test("formatDistance: exact station coords show a plain distance", () => {
  expect(formatDistance(ranked({ geoResolution: "station", distanceKm: 2.6 }))).toBe("2.6 km");
});

test("formatDistance: municipal centroid is flagged approximate", () => {
  // The honesty rule: municipal-centroid distances are shared by every station
  // in the municipality, so they must not read as exact.
  expect(formatDistance(ranked({ geoResolution: "municipality", distanceKm: 2.6 }))).toBe(
    "~2.6 km · municipio",
  );
});

test("formatDistance: no coordinates → dist n/a", () => {
  expect(formatDistance(ranked({ geoResolution: undefined, distanceKm: null }))).toBe("dist n/a");
});

test("formatDistance: fail-safe — a distance with UNKNOWN resolution is hedged, never exact", () => {
  // A future adapter that sets coords but forgets geoResolution must not get a
  // free pass to claim exactness.
  expect(formatDistance(ranked({ geoResolution: undefined, distanceKm: 2.6 }))).toBe(
    "~2.6 km · aprox",
  );
});

test("recommendationLine: exact coords claim a real distance", () => {
  const line = recommendationLine(
    ranked({ geoResolution: "station", distanceKm: 2.6, stationName: "PATIO USME" }),
    "$2.611/m³",
  );
  expect(line).toContain("Go to: PATIO USME");
  expect(line).toContain("2.6 km away");
});

test("recommendationLine: municipal coords hedge the distance claim", () => {
  const line = recommendationLine(
    ranked({
      geoResolution: "municipality",
      distanceKm: 2.6,
      stationName: "PATIO USME",
      municipality: "BOGOTA, D.C.",
    }),
    "$2.611/m³",
  );
  expect(line).not.toContain("km away"); // no false precision
  expect(line).toContain("Cheapest: PATIO USME");
  expect(line).toContain("BOGOTA, D.C.");
  expect(line.toLowerCase()).toContain("approximate");
});

test("recommendationLine: coord-less makes a price-only claim in the municipality", () => {
  const line = recommendationLine(
    ranked({
      geoResolution: undefined,
      distanceKm: null,
      stationName: "INVEREPE",
      municipality: "BOGOTA  D.C.",
    }),
    "$8.595/gal",
  );
  expect(line).not.toContain("km");
  expect(line).toContain("Cheapest: INVEREPE");
  expect(line).toContain("BOGOTA  D.C.");
  // A municipality that already ends in "." must not produce a doubled period.
  expect(line.endsWith("..")).toBe(false);
  expect(line.endsWith(".")).toBe(true);
});

test("recommendationLine: a municipal candidate WITHOUT a distance makes no approximate-distance claim", () => {
  // geoResolution municipality but distanceKm null (a station missing coords):
  // must fall to the plain price claim, not imply an approximate distance.
  const line = recommendationLine(
    ranked({ geoResolution: "municipality", distanceKm: null, municipality: "CALI" }),
    "$2.700/m³",
  );
  expect(line.toLowerCase()).not.toContain("approximate");
  expect(line).toContain("in CALI");
});
