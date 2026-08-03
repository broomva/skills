import { describe, expect, test } from "bun:test";
import {
  type BasketLine,
  chooseBest,
  fillToBudget,
  linePrice,
  parseBudget,
} from "../src/basket.ts";
import { basketExit, basketOptions } from "../src/cli.ts";
import type { Measure } from "../src/measure.ts";
import { renderBasket } from "../src/present.ts";
import type { Product } from "../src/types.ts";

function product(
  skuId: string,
  name: string,
  price: number,
  opts: { available?: boolean; measure?: Measure; amount?: number } = {},
): Product {
  const { available = true, measure, amount } = opts;
  const size = measure && amount ? { measure, amount } : undefined;
  return {
    productId: skuId,
    skuId,
    name,
    brand: "",
    linkText: "",
    categories: [],
    offers: [
      {
        sellerId: "1",
        sellerName: "Tiendas D1",
        price,
        listPrice: price,
        available,
        availableQuantity: available ? 10 : 0,
      },
    ],
    size,
    unitPrice: size && price > 0 ? Math.round(price / size.amount) : undefined,
    warnings: [],
  };
}

const line = (over: Partial<BasketLine> & { term: string }): BasketLine => ({
  status: "filled",
  compared: 1,
  matched: 1,
  ...over,
});

describe("chooseBest", () => {
  test("picks best VALUE, not the cheapest pack", () => {
    // The rice case the whole per-unit feature exists for: the 500 g bag is the
    // cheapest pack and the worst buy.
    const pick = chooseBest([
      product("small", "ARROZ ESTÁNDAR 500 GRS", 155_000, { measure: "kg", amount: 0.5 }),
      product("big", "ARROZ ECONÓMICO 2000 GRS", 555_000, { measure: "kg", amount: 2 }),
    ]);
    expect(pick?.skuId).toBe("big");
  });

  test("ignores what D1 cannot supply here", () => {
    const pick = chooseBest([
      product("gone", "ARROZ BARATÍSIMO", 100_000, {
        available: false,
        measure: "kg",
        amount: 1,
      }),
      product("here", "ARROZ NORMAL", 300_000, { measure: "kg", amount: 1 }),
    ]);
    expect(pick?.skuId).toBe("here");
  });

  test("a price of 0 is 'no offer here', never the best buy", () => {
    // Deliberately sizeless, so the pack-price fallback is the path under test.
    // With a size, `unitPrice` is already undefined for an unpriced product and
    // the assertion would pass without the availability-and-price filter ever
    // running — it did, until a mutation showed the guard could be deleted with
    // the suite green. Sizeless, a $0 product sorts FIRST by pack price, which
    // is exactly the "$ 0 is not free" failure.
    const pick = chooseBest([
      product("noprice", "SIN OFERTA", 0),
      product("real", "CON PRECIO", 400_000),
    ]);
    expect(pick?.skuId).toBe("real");
  });

  test("does not blend measures — a $/unit bottle cannot beat a $/L oil", () => {
    // Observed live: an $8,990 empty bottle ranked among per-litre oil prices.
    //
    // The bottle is priced so its $/unit is the LOWEST number in the set. That
    // is the point: blending measures would rank it first on a number that
    // means nothing next to the others. An earlier fixture had the bottle
    // dearest, so removing the measure filter changed no result and the
    // assertion proved nothing.
    const pick = chooseBest([
      product("bottle", "BOTELLA PARA ACEITE", 100_000, { measure: "unit", amount: 1 }),
      product("oil3", "ACEITE 3000 ML", 2_050_000, { measure: "L", amount: 3 }),
      product("oil900", "ACEITE 900 ML", 695_000, { measure: "L", amount: 0.9 }),
    ]);
    // Two products are measured in L against one in units, so L is dominant and
    // the bottle is not a candidate at all — despite the smallest per-unit.
    expect(pick?.skuId).toBe("oil3");
  });

  test("falls back to pack price only when NOTHING publishes a size", () => {
    const pick = chooseBest([
      product("a", "COSA CARA", 900_000),
      product("b", "COSA BARATA", 300_000),
    ]);
    expect(pick?.skuId).toBe("b");
  });

  test("prefers a comparable answer over an incomparable cheaper one", () => {
    // The sizeless product is cheaper per pack, but cannot be compared on value.
    // Ranking it first would be the mixed-measure failure by another route.
    const pick = chooseBest([
      product("nosize", "GENÉRICO", 100_000),
      product("sized", "ARROZ 1 KG", 300_000, { measure: "kg", amount: 1 }),
    ]);
    expect(pick?.skuId).toBe("sized");
  });

  test("nothing eligible yields undefined rather than a phantom line", () => {
    expect(chooseBest([])).toBeUndefined();
    expect(chooseBest([product("x", "AGOTADO", 100_000, { available: false })])).toBeUndefined();
  });
});

describe("fillToBudget", () => {
  test("the ceiling is hard — a line that would exceed it is left out", () => {
    const plan = fillToBudget(
      [line({ term: "aceite", price: 2_050_000 }), line({ term: "huevos", price: 165_000 })],
      2_100_000,
    );
    expect(plan.total).toBe(2_050_000);
    expect(plan.remaining).toBe(50_000);
    expect(plan.lines.map((l) => l.status)).toEqual(["filled", "over-budget"]);
    // The whole point: never over the stated budget.
    expect(plan.total).toBeLessThanOrEqual(plan.budget);
  });

  test("one item too expensive does not strand everything after it", () => {
    // A fill that stopped at the first miss would drop the two cheap lines that
    // fit perfectly well, and report a smaller basket than the budget buys.
    const plan = fillToBudget(
      [
        line({ term: "caviar", price: 9_000_000 }),
        line({ term: "arroz", price: 555_000 }),
        line({ term: "leche", price: 309_000 }),
      ],
      1_000_000,
    );
    expect(plan.lines.map((l) => l.status)).toEqual(["over-budget", "filled", "filled"]);
    expect(plan.total).toBe(864_000);
  });

  test("fills in the order the shopper wrote, not cheapest-first", () => {
    // Reordering by value would spend the budget on whatever is cheapest per kg,
    // which is a different request than the one the list expresses.
    const plan = fillToBudget(
      [line({ term: "first", price: 700_000 }), line({ term: "second", price: 700_000 })],
      1_000_000,
    );
    expect(plan.lines[0]?.status).toBe("filled");
    expect(plan.lines[1]?.status).toBe("over-budget");
  });

  test("a term nothing was found for stays unfilled and costs nothing", () => {
    const plan = fillToBudget(
      [line({ term: "unicornio", status: "no-match" }), line({ term: "arroz", price: 555_000 })],
      1_000_000,
    );
    expect(plan.lines[0]?.status).toBe("no-match");
    expect(plan.total).toBe(555_000);
  });

  test("a substitute line counts toward the total like any other", () => {
    const plan = fillToBudget(
      [line({ term: "pan", price: 195_000, status: "filled-by-substitute" })],
      1_000_000,
    );
    expect(plan.total).toBe(195_000);
  });

  test("an empty list spends nothing", () => {
    const plan = fillToBudget([], 1_000_000);
    expect(plan.total).toBe(0);
    expect(plan.remaining).toBe(1_000_000);
  });
});

describe("parseBudget", () => {
  test("reads pesos and returns hundredths, matching every other price", () => {
    expect(parseBudget("50000")).toBe(5_000_000);
    // Colombian thousands separators are how a person actually types it.
    expect(parseBudget("50.000")).toBe(5_000_000);
    expect(parseBudget("$ 50.000")).toBe(5_000_000);
  });

  test("refuses a budget that cannot buy anything", () => {
    // Rejected rather than defaulted: a basket built to a budget nobody set is
    // a claim about a shop the caller never asked for.
    expect(() => parseBudget("abc")).toThrow();
    expect(() => parseBudget("0")).toThrow();
    expect(() => parseBudget("-500")).toThrow();
    expect(() => parseBudget(undefined)).toThrow();
    expect(() => parseBudget(true)).toThrow();
  });
});

describe("basketExit", () => {
  test("3 when nothing fit, because a retry never changes that", () => {
    // Exit 1 across this CLI means "D1 refused or was unreachable; retry may
    // help". A budget that buys none of the list never becomes affordable on a
    // retry, so an agent with a retry-on-1 policy would loop forever.
    expect(basketExit(0)).toBe(3);
  });

  test("0 for a partially filled basket, which is a real answer", () => {
    expect(basketExit(1)).toBe(0);
    expect(basketExit(9)).toBe(0);
  });
});

describe("basketOptions", () => {
  test("forwards the region, without which the whole basket is national", () => {
    // Dropping this silently prices every line against a catalogue nobody can
    // buy from. No network-free test of the command body can observe it.
    const o = basketOptions({ count: "20" }, { id: "v2.ABC" }, "1");
    expect(o.regionId).toBe("v2.ABC");
    expect(o.salesChannel).toBe("1");
    expect(o.count).toBe(20);
  });

  test("rejects a count that would silently clamp to one", () => {
    expect(() => basketOptions({ count: "0" }, undefined, "1")).toThrow();
  });
});

describe("renderBasket", () => {
  const plan = fillToBudget(
    [
      line({
        term: "arroz",
        price: 555_000,
        product: product("1075", "ARROZ ECONÓMICO 2000 GRS", 555_000, {
          measure: "kg",
          amount: 2,
        }),
        compared: 20,
        matched: 143,
      }),
      line({ term: "huevos", price: 900_000, compared: 5, matched: 5 }),
    ],
    600_000,
  );

  test("names what it could not fit, and why", () => {
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("Not included:");
    expect(out).toContain("huevos");
    expect(out).toContain("does not fit");
  });

  test("states that the budget was a ceiling", () => {
    // A reader who assumed best-effort would read a short basket as
    // "that is all D1 sells".
    expect(renderBasket(plan)).toContain("hard ceiling");
  });

  test("names the denominator it chose over", () => {
    // "best of 20 compared" alone reads as a survey of the shelf. Saying 143
    // matched is what makes the partiality visible.
    expect(renderBasket(plan)).toContain("of 143 D1 matched");
  });

  test("does not invent a denominator when it saw everything", () => {
    const all = fillToBudget(
      [
        line({
          term: "arroz",
          price: 555_000,
          product: product("1075", "ARROZ", 555_000, { measure: "kg", amount: 2 }),
          compared: 5,
          matched: 5,
        }),
      ],
      1_000_000,
    );
    expect(renderBasket(all)).toContain("best of 5 compared");
    expect(renderBasket(all)).not.toContain("D1 matched");
  });

  test("warns when no delivery point was resolved", () => {
    // Without a region these are national prices for a store nobody shops at.
    expect(renderBasket(plan)).toContain("NATIONAL");
    expect(renderBasket(plan, { regionId: "v2.ABC" })).not.toContain("NATIONAL");
  });

  test("says plainly when nothing fit at all", () => {
    const none = fillToBudget([line({ term: "arroz", price: 555_000 })], 10_000);
    expect(renderBasket(none)).toContain("Nothing fits this budget.");
  });

  test("names a substitute rather than swapping it in quietly", () => {
    const sub = fillToBudget(
      [
        line({
          term: "pan",
          price: 195_000,
          status: "filled-by-substitute",
          product: product("738", "TOSTADA INTEGRAL", 195_000, { measure: "kg", amount: 0.15 }),
          replaces: product("192", "PAN ARTESANAL INTEGRAL", 0, { available: false }),
        }),
      ],
      1_000_000,
    );
    const out = renderBasket(sub, { regionId: "v2.ABC" });
    expect(out).toContain("replaces");
    expect(out).toContain("PAN ARTESANAL INTEGRAL");
  });
});

describe("linePrice", () => {
  test("is undefined for a product with no real offer", () => {
    expect(linePrice(product("x", "SIN PRECIO", 0))).toBeUndefined();
  });

  test("is the price a basket line actually costs", () => {
    expect(linePrice(product("x", "ARROZ", 555_000))).toBe(555_000);
  });
});

describe("parseBudget rejects what Number() would have accepted", () => {
  test("a decimal comma is refused, not silently multiplied by ten", () => {
    // Colombians write "50,5" meaning 50.5. Stripping the comma made it 505 —
    // a 10x budget that looks entirely plausible in the output.
    expect(() => parseBudget("50,5")).toThrow(/decimal comma/);
  });

  test("hex and scientific notation are not budgets", () => {
    // `Number("0x10")` is 16 and `Number("1e5")` is 100000. Both parsed, and
    // both meant something other than what was typed.
    expect(() => parseBudget("0x10")).toThrow();
    expect(() => parseBudget("1e5")).toThrow();
  });

  test("still accepts the forms a person actually types", () => {
    expect(parseBudget("50000")).toBe(5_000_000);
    expect(parseBudget("50.000")).toBe(5_000_000);
    expect(parseBudget("$ 50.000")).toBe(5_000_000);
    expect(parseBudget("$50000")).toBe(5_000_000);
  });

  test("a malformed thousands grouping is not a number", () => {
    expect(() => parseBudget("50.00")).toThrow();
    expect(() => parseBudget("5.0000")).toThrow();
  });
});

describe("a filled line always has a price", () => {
  test("a priceless line never enters the basket at $ 0", () => {
    // The reverse of the "$ 0 is not free" defect: a line marked filled with no
    // price would render as $ 0 and add nothing to the total, describing a
    // purchase that cannot happen.
    const plan = fillToBudget(
      [line({ term: "arroz", status: "filled", price: undefined })],
      1_000_000,
    );
    expect(plan.lines[0]?.status).toBe("nothing-in-stock");
    expect(plan.total).toBe(0);
    // `$ 0` in the SUMMARY is honest — the total really is zero. The defect
    // would be a priced product row, so assert on the basket body only.
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    const body = out.slice(0, out.indexOf("0 of 1 lines"));
    expect(body).not.toContain("$ 0");
    expect(body).toContain("Nothing fits this budget.");
  });
});
