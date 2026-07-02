import { expect, test } from "bun:test";
import { dedupeLatestPerStation, parseCop } from "../src/sources/adapters.ts";
import type { Observation } from "../src/types.ts";

function obs(name: string, observedAt: string, priceCop: number, municipality = "BOGOTA D.C."): Observation {
  return {
    source: "test",
    stationName: name,
    municipality,
    product: "GASOLINA_CORRIENTE",
    priceCop,
    observedAt,
    isLive: false,
  };
}

test("dedupeLatestPerStation keeps the newest month per station (#4)", () => {
  const input = [
    obs("EDS A", "2022-01-01", 8000), // old cheap month — must NOT win
    obs("EDS A", "2022-11-01", 9500), // newest for A
    obs("EDS B", "2022-11-01", 9600),
  ];
  const out = dedupeLatestPerStation(input);
  expect(out).toHaveLength(2);
  const a = out.find((o) => o.stationName === "EDS A");
  expect(a?.observedAt).toBe("2022-11-01");
  expect(a?.priceCop).toBe(9500);
});

test("dedupeLatestPerStation treats different municipalities as different stations", () => {
  const input = [
    obs("EDS X", "2022-11-01", 9000, "BOGOTA D.C."),
    obs("EDS X", "2022-11-01", 9200, "MEDELLIN"),
  ];
  expect(dedupeLatestPerStation(input)).toHaveLength(2);
});

test("parseCop: plain integers unaffected", () => {
  expect(parseCop("2611")).toBe(2611);
  expect(parseCop("9860")).toBe(9860);
});

test("parseCop: Colombian thousands-dot normalized (#6)", () => {
  expect(parseCop("12.345")).toBe(12345);
  expect(parseCop("1.234.567")).toBe(1234567);
});

test("parseCop: comma decimal normalized", () => {
  expect(parseCop("12345,67")).toBeCloseTo(12345.67, 2);
});

test("parseCop: junk → NaN (dropped by caller guard)", () => {
  expect(Number.isNaN(parseCop(undefined))).toBe(true);
  expect(Number.isNaN(parseCop("n/a"))).toBe(true);
});
