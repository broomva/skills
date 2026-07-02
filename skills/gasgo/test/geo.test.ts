import { expect, test } from "bun:test";
import { haversineKm } from "../src/geo.ts";

test("haversine: zero distance", () => {
  expect(haversineKm({ lat: 4.65, lng: -74.08 }, { lat: 4.65, lng: -74.08 })).toBeCloseTo(0, 5);
});

test("haversine: Bogotá centro → El Dorado airport ≈ 13 km", () => {
  const centro = { lat: 4.6533, lng: -74.0836 };
  const eldorado = { lat: 4.7016, lng: -74.1469 };
  const d = haversineKm(centro, eldorado);
  expect(d).toBeGreaterThan(8);
  expect(d).toBeLessThan(14);
});

test("haversine: symmetric", () => {
  const a = { lat: 6.2442, lng: -75.5812 };
  const b = { lat: 3.4516, lng: -76.532 };
  expect(haversineKm(a, b)).toBeCloseTo(haversineKm(b, a), 6);
});
