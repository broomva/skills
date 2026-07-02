import { expect, test } from "bun:test";
import { rankObservations } from "../src/engine.ts";
import { makeQuery } from "../src/engine.ts";
import type { Observation } from "../src/types.ts";

const near = { lat: 4.65, lng: -74.08 };

function obs(partial: Partial<Observation>): Observation {
  return {
    source: "test",
    stationName: "S",
    product: "GNCV",
    priceCop: 3000,
    observedAt: "2026-06-01",
    isLive: true,
    ...partial,
  };
}

test("cheaper-and-closer wins", () => {
  const observations = [
    obs({ stationName: "Cheap Close", priceCop: 3000, lat: 4.651, lng: -74.081 }),
    obs({ stationName: "Pricey Close", priceCop: 3500, lat: 4.652, lng: -74.082 }),
  ];
  const res = rankObservations(observations, makeQuery({ at: near, product: "GNCV" }));
  expect(res.best?.stationName).toBe("Cheap Close");
  expect(res.best?.rank).toBe(1);
});

test("distance penalty can outweigh a small price edge", () => {
  const observations = [
    // 5 COP/m³ cheaper but ~40 km away
    obs({ stationName: "Cheap Far", priceCop: 2995, lat: 5.02, lng: -74.08 }),
    obs({ stationName: "Normal Near", priceCop: 3000, lat: 4.651, lng: -74.081 }),
  ];
  const q = makeQuery({ at: near, product: "GNCV", radiusKm: 60, tankUnits: 10, costPerKmCop: 350 });
  const res = rankObservations(observations, q);
  // detour to Cheap Far ≈ 2*40*350 = 28,000 COP >> tank savings of 50 COP
  expect(res.best?.stationName).toBe("Normal Near");
});

test("radius filter excludes far stations", () => {
  const observations = [
    obs({ stationName: "In", priceCop: 3000, lat: 4.66, lng: -74.09 }),
    obs({ stationName: "Out", priceCop: 100, lat: 8.0, lng: -74.0 }),
  ];
  const res = rankObservations(observations, makeQuery({ at: near, product: "GNCV", radiusKm: 10 }));
  expect(res.ranked.map((r) => r.stationName)).toEqual(["In"]);
});

test("savingsVsAvg is positive for the cheapest", () => {
  const observations = [
    obs({ stationName: "A", priceCop: 2800, lat: 4.651, lng: -74.081 }),
    obs({ stationName: "B", priceCop: 3200, lat: 4.652, lng: -74.082 }),
  ];
  const res = rankObservations(observations, makeQuery({ at: near, product: "GNCV", tankUnits: 10 }));
  expect(res.best?.savingsVsAvgCop).toBeGreaterThan(0);
});

test("candidateCount reflects the filtered set, not the raw product set (#3)", () => {
  const observations = [
    obs({ stationName: "BogA", priceCop: 9000, municipality: "BOGOTA D.C.", isLive: false, lat: undefined, lng: undefined, product: "GASOLINA_CORRIENTE" }),
    obs({ stationName: "BogB", priceCop: 9200, municipality: "BOGOTA D.C.", isLive: false, lat: undefined, lng: undefined, product: "GASOLINA_CORRIENTE" }),
    obs({ stationName: "MedC", priceCop: 8800, municipality: "MEDELLIN", isLive: false, lat: undefined, lng: undefined, product: "GASOLINA_CORRIENTE" }),
  ];
  const res = rankObservations(
    observations,
    makeQuery({ at: near, product: "GASOLINA_CORRIENTE", municipality: "bogota" }),
  );
  // 3 total in product set, but only 2 after the Bogotá filter.
  expect(res.candidateCount).toBe(2);
});

test("coord-less historical stations rank by price within a municipality", () => {
  const observations = [
    obs({ stationName: "H1", priceCop: 9800, municipality: "BOGOTA D.C.", isLive: false, lat: undefined, lng: undefined, product: "GASOLINA_CORRIENTE" }),
    obs({ stationName: "H2", priceCop: 9500, municipality: "BOGOTA D.C.", isLive: false, lat: undefined, lng: undefined, product: "GASOLINA_CORRIENTE" }),
  ];
  const res = rankObservations(
    observations,
    makeQuery({ at: near, product: "GASOLINA_CORRIENTE", municipality: "bogota" }),
  );
  expect(res.best?.stationName).toBe("H2");
  expect(res.best?.distanceKm).toBeNull();
  expect(res.freshness.isLive).toBe(false);
});
