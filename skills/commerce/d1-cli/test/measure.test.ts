import { describe, expect, test } from "bun:test";
import { formatUnitPrice, parseUnitSize, unitPrice } from "../src/measure.ts";
import { formatCOP } from "../src/money.ts";

describe("parseUnitSize", () => {
  test("grams normalize to kg", () => {
    expect(parseUnitSize("Gr", "500")).toEqual({ measure: "kg", amount: 0.5 });
    expect(parseUnitSize("g", "2000")).toEqual({ measure: "kg", amount: 2 });
  });

  test("millilitres normalize to litres", () => {
    expect(parseUnitSize("Ml", "900")).toEqual({ measure: "L", amount: 0.9 });
    expect(parseUnitSize("cc", "1500")).toEqual({ measure: "L", amount: 1.5 });
  });

  test("case does not matter — D1 is inconsistent about it", () => {
    expect(parseUnitSize("GR", "500")).toEqual(parseUnitSize("gr", "500"));
  });

  test("a Colombian thousands separator is not a decimal point", () => {
    // "1.000 G" is one kilogram, not one gram. Reading it as 1 would report a
    // price per kg that is 1000x too high and rank it last.
    expect(parseUnitSize("Gr", "1.000")).toEqual({ measure: "kg", amount: 1 });
  });

  test("a decimal comma parses", () => {
    expect(parseUnitSize("Kg", "1,5")).toEqual({ measure: "kg", amount: 1.5 });
  });

  test("unknown or missing data yields undefined, never a guess", () => {
    // A fabricated size produces a confidently wrong $/kg, which is worse than
    // admitting the comparison cannot be made.
    expect(parseUnitSize(undefined, "500")).toBeUndefined();
    expect(parseUnitSize("Gr", undefined)).toBeUndefined();
    expect(parseUnitSize("furlong", "3")).toBeUndefined();
    expect(parseUnitSize("Gr", "0")).toBeUndefined();
    expect(parseUnitSize("Gr", "abc")).toBeUndefined();
  });
});

describe("unitPrice", () => {
  test("reproduces the ranking inversion this feature exists for", () => {
    // Measured live. Ranking by pack price puts the 500 g bag first; by value
    // it is third, and the real winner is a pack three times the price.
    const cheapPack = unitPrice(155_000, parseUnitSize("Gr", "500")); // $1,550
    const bestValue = unitPrice(555_000, parseUnitSize("Gr", "2000")); // $5,550
    expect(cheapPack).toBe(310_000); // $3,100/kg
    expect(bestValue).toBe(277_500); // $2,775/kg
    expect(bestValue ?? 0).toBeLessThan(cheapPack ?? 0);
    // ...while costing more per pack, which is exactly the trap.
    expect(555_000).toBeGreaterThan(155_000);
  });

  test("is undefined when the size is unknown", () => {
    expect(unitPrice(100_000, undefined)).toBeUndefined();
  });

  test("formats with the measure attached", () => {
    const p = unitPrice(555_000, parseUnitSize("Gr", "2000"));
    expect(formatUnitPrice(formatCOP(p ?? 0), "kg")).toBe("$ 2.775/kg");
  });
});
