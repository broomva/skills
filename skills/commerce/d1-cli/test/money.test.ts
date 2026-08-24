import { describe, expect, test } from "bun:test";
import { discountPercent, formatCOP, sum, toHundredths, toPesos } from "../src/money.ts";

describe("VTEX hundredths conversion", () => {
  test("the checkout wire value for a COP 3,500 product reads as 3,500", () => {
    // SKU 262, Leche Entera Latti 900 ml. The orderForm reports 350000.
    expect(toPesos(350_000)).toBe(3500);
    expect(formatCOP(350_000)).toBe("$ 3.500");
  });

  test("round-trips", () => {
    for (const pesos of [0, 1, 999, 3500, 13_500, 1_234_567]) {
      expect(toPesos(toHundredths(pesos))).toBe(pesos);
    }
  });

  test("survives non-finite input rather than emitting NaN into a total", () => {
    expect(toPesos(Number.NaN)).toBe(0);
    expect(toHundredths(Number.POSITIVE_INFINITY)).toBe(0);
    expect(sum([100, Number.NaN, 200])).toBe(300);
  });
});

describe("Colombian formatting", () => {
  test("groups thousands with dots, not commas", () => {
    expect(formatCOP(100)).toBe("$ 1");
    expect(formatCOP(99_900)).toBe("$ 999");
    expect(formatCOP(100_000)).toBe("$ 1.000");
    expect(formatCOP(1_350_000)).toBe("$ 13.500");
    expect(formatCOP(123_456_700)).toBe("$ 1.234.567");
  });

  test("negatives keep the sign outside the symbol", () => {
    expect(formatCOP(-350_000)).toBe("-$ 3.500");
  });
});

describe("discountPercent", () => {
  test("reports a real discount", () => {
    expect(discountPercent(75_000, 100_000)).toBe(25);
  });

  test("is zero when there is no discount", () => {
    expect(discountPercent(100_000, 100_000)).toBe(0);
    expect(discountPercent(100_000, 0)).toBe(0);
  });

  test("never reports a negative saving when selling price exceeds list", () => {
    // Upstream does occasionally emit this; showing "-20% off" would be worse
    // than showing nothing.
    expect(discountPercent(120_000, 100_000)).toBe(0);
  });
});
