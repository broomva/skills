import { expect, test } from "bun:test";
import { makeQuery, rankObservations } from "../src/engine.ts";
import type { Observation } from "../src/types.ts";

const near = { lat: 4.65, lng: -74.08 };

function obs(partial: Partial<Observation>): Observation {
  return {
    source: "test",
    stationName: "S",
    product: "GNCV",
    priceCop: 2611,
    observedAt: "2026-07-01",
    isLive: true,
    ...partial,
  };
}

test("freshness note carries the municipal-centroid caveat when coords are municipal", () => {
  const observations = [
    obs({ stationName: "A", lat: 4.649, lng: -74.107, geoResolution: "municipality" }),
    obs({
      stationName: "B",
      lat: 4.649,
      lng: -74.107,
      geoResolution: "municipality",
      priceCop: 2700,
    }),
  ];
  const res = rankObservations(
    observations,
    makeQuery({ at: near, product: "GNCV", radiusKm: 20 }),
  );
  expect(res.freshness.note.toLowerCase()).toContain("municipal centroid");
  expect(res.freshness.note.toLowerCase()).toContain("by price");
});

test("freshness note omits the caveat when coordinates are exact", () => {
  const observations = [
    obs({ stationName: "A", lat: 4.651, lng: -74.081, geoResolution: "station" }),
  ];
  const res = rankObservations(observations, makeQuery({ at: near, product: "GNCV" }));
  expect(res.freshness.note.toLowerCase()).not.toContain("municipal centroid");
});

test("historical (coord-less) note stays historical and has no municipal caveat", () => {
  const observations = [
    obs({
      stationName: "H",
      isLive: false,
      lat: undefined,
      lng: undefined,
      product: "GASOLINA_CORRIENTE",
      municipality: "BOGOTA D.C.",
    }),
  ];
  const res = rankObservations(
    observations,
    makeQuery({ at: near, product: "GASOLINA_CORRIENTE", municipality: "bogota" }),
  );
  expect(res.freshness.isLive).toBe(false);
  expect(res.freshness.note.toLowerCase()).toContain("historical");
  expect(res.freshness.note.toLowerCase()).not.toContain("municipal centroid");
});
