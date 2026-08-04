import { describe, expect, test } from "bun:test";
import {
  type BasketLine,
  buildBasket,
  chooseBest,
  fillToBudget,
  linePrice,
  parseBudget,
} from "../src/basket.ts";
import { basketExit, basketOptions } from "../src/cli.ts";
import { D1Client } from "../src/client.ts";
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

/**
 * A basket line, defaulting to a filled one.
 *
 * The default product is load-bearing: `fillToBudget` refuses to bill a filled
 * line that names no product, so a fixture omitting it is silently downgraded
 * and stops testing what it says it tests. Pass `product: undefined` explicitly
 * to exercise that guard.
 */
const line = (over: Partial<BasketLine> & { term: string }): BasketLine => ({
  status: "filled",
  compared: 1,
  matched: 1,
  product: product("stub", "PRODUCTO", over.price ?? 100_000),
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
    expect(pick?.product.skuId).toBe("big");
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
    expect(pick?.product.skuId).toBe("here");
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
    expect(pick?.product.skuId).toBe("real");
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
    expect(pick?.product.skuId).toBe("oil3");
  });

  test("falls back to pack price only when NOTHING publishes a size", () => {
    const pick = chooseBest([
      product("a", "COSA CARA", 900_000),
      product("b", "COSA BARATA", 300_000),
    ]);
    expect(pick?.product.skuId).toBe("b");
  });

  test("prefers a comparable answer over an incomparable cheaper one", () => {
    // The sizeless product is cheaper per pack, but cannot be compared on value.
    // Ranking it first would be the mixed-measure failure by another route.
    const pick = chooseBest([
      product("nosize", "GENÉRICO", 100_000),
      product("sized", "ARROZ 1 KG", 300_000, { measure: "kg", amount: 1 }),
    ]);
    expect(pick?.product.skuId).toBe("sized");
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
    //
    // The two lines must have DIFFERENT prices and the assertion must name the
    // term. With both at 700_000 a value-sorted fill was indistinguishable from
    // an in-order one, so this test survived the very mutation it is named for.
    const plan = fillToBudget(
      [line({ term: "expensive", price: 800_000 }), line({ term: "cheap", price: 300_000 })],
      1_000_000,
    );
    expect(plan.lines.map((l) => l.term)).toEqual(["expensive", "cheap"]);
    expect(plan.lines[0]?.status).toBe("filled");
    expect(plan.lines[1]?.status).toBe("over-budget");
  });

  test("a line costing exactly what is left still fits", () => {
    // The boundary the whole feature is about. `>` -> `>=` passed the entire
    // suite before this existed, and would have refused a basket that spends
    // the budget exactly.
    const plan = fillToBudget([line({ term: "arroz", price: 100_000 })], 100_000);
    expect(plan.lines[0]?.status).toBe("filled");
    expect(plan.total).toBe(100_000);
    expect(plan.remaining).toBe(0);
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
    expect(basketExit([line({ term: "a", status: "no-match" })])).toBe(3);
  });

  test("0 for a partially filled basket, which is a real answer", () => {
    expect(basketExit([line({ term: "a" }), line({ term: "b", status: "over-budget" })])).toBe(0);
    expect(basketExit([line({ term: "a", status: "filled-by-substitute" })])).toBe(0);
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
    expect(renderBasket(none)).toContain("Nothing could go in the basket — the budget was short.");
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
    // Not "Nothing fits this budget" — nothing was rejected on PRICE here.
    expect(body).toContain("could go in the basket");
  });
});

// ---------------------------------------------------------------------------
// Defects found by the cross-model review gate (P20)
// ---------------------------------------------------------------------------

describe("the dominant measure is decided deterministically", () => {
  const bottle = product("bottle", "BOTELLA PARA ACEITE", 899_000, {
    measure: "unit",
    amount: 1,
  });
  const oil = product("oil3", "ACEITE 3000 ML", 2_050_000, { measure: "L", amount: 3 });

  test("the same set gives the same answer in either order", () => {
    // The tie-break used to fall through to Map INSERTION order, which is the
    // order `search` happened to return — and that order is computed over
    // out-of-stock products too. So a page listing sold-out bottles first could
    // put an empty bottle in the basket as the best value for "aceite".
    expect(chooseBest([bottle, oil])?.product.skuId).toBe(chooseBest([oil, bottle])?.product.skuId);
  });

  test("a tie never resolves in favour of $/unit", () => {
    // A kilogram is a kilogram across products; one "unit" of an empty bottle
    // and one "unit" of oil are not the same kind of thing, so $/unit is the
    // least defensible answer available when the count is tied.
    expect(chooseBest([bottle, oil])?.product.skuId).toBe("oil3");
    expect(chooseBest([oil, bottle])?.product.skuId).toBe("oil3");
  });
});

describe("compared counts the set actually chosen between", () => {
  test("not the page, which includes what was never a candidate", () => {
    // A page of 20 where 18 are out of stock reports a choice between 2, not
    // 20. Reporting the page was the "3 of 140" overstatement by another route.
    const page = [
      product("a", "ACEITE A", 200_000, { measure: "L", amount: 1 }),
      product("b", "ACEITE B", 300_000, { measure: "L", amount: 1 }),
      ...Array.from({ length: 18 }, (_, i) =>
        product(`gone${i}`, `ACEITE AGOTADO ${i}`, 100_000, {
          available: false,
          measure: "L",
          amount: 1,
        }),
      ),
    ];
    expect(chooseBest(page)?.compared).toBe(2);
  });

  test("and excludes products outside the winning measure", () => {
    const pick = chooseBest([
      product("oil1", "ACEITE 1 L", 200_000, { measure: "L", amount: 1 }),
      product("oil2", "ACEITE 2 L", 300_000, { measure: "L", amount: 2 }),
      product("bottle", "BOTELLA", 100_000, { measure: "unit", amount: 1 }),
    ]);
    expect(pick?.compared).toBe(2);
  });
});

describe("a pack-price pick says so", () => {
  test("chooseBest flags it", () => {
    const pick = chooseBest([
      product("big", "ARROZ 5 KG SIN PUM", 2_000_000),
      product("tiny", "ARROZ 250 GR SIN PUM", 190_000),
    ]);
    expect(pick?.byPackPrice).toBe(true);
    expect(
      chooseBest([product("sized", "ARROZ 1 KG", 300_000, { measure: "kg", amount: 1 })])
        ?.byPackPrice,
    ).toBe(false);
  });

  test("and the output does not call it the best value", () => {
    // $ 1.900 for 250 g is $ 7.600/kg against the 5 kg bag's $ 4.000/kg. Calling
    // that "best value" is the cheapest-pack-is-the-worst-buy error the unit
    // pricing feature exists to prevent.
    const plan = fillToBudget(
      [
        line({
          term: "arroz",
          price: 190_000,
          product: product("tiny", "ARROZ 250 GR SIN PUM", 190_000),
          byPackPrice: true,
        }),
      ],
      1_000_000,
    );
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("chosen on pack price");
  });
});

describe("a failed replacement lookup is not a claim about stock", () => {
  test("it says unknown, never empty", () => {
    // A bare catch turned "D1 did not answer" into "nothing is in stock here",
    // asserted from zero successful requests — and exited 3, which is
    // documented as never worth retrying.
    const plan = fillToBudget(
      [line({ term: "pan", status: "replacement-unknown", compared: 1 })],
      1_000_000,
    );
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("did not answer");
    expect(out).toContain("unknown, not empty");
  });
});

describe("the ceiling holds against arithmetic accidents", () => {
  test("a non-finite price cannot breach it", () => {
    // `sum()` coerces NaN to 0 while `spent` becomes NaN, after which every
    // `spent + price > budget` is false and every remaining line is admitted.
    // `remaining` then went negative on a documented hard ceiling.
    const plan = fillToBudget(
      [
        line({ term: "broken", price: Number.NaN }),
        line({ term: "a", price: 900_000 }),
        line({ term: "b", price: 900_000 }),
      ],
      100_000,
    );
    expect(plan.total).toBeLessThanOrEqual(plan.budget);
    expect(plan.remaining).toBeGreaterThanOrEqual(0);
    expect(plan.lines[0]?.status).toBe("nothing-in-stock");
  });

  test("a priced line that is not being filled does not consume budget", () => {
    // `spent` counted any priced line while `total` counted only filled ones,
    // so the basket refused affordable items while reporting the money as left.
    const plan = fillToBudget(
      [
        line({ term: "ghost", status: "nothing-in-stock", price: 90_000 }),
        line({ term: "real", price: 90_000 }),
      ],
      100_000,
    );
    expect(plan.lines[1]?.status).toBe("filled");
    expect(plan.total).toBe(90_000);
  });
});

describe("a numeric budget obeys the same rules as a typed one", () => {
  test("fractional pesos are refused either way", () => {
    // `parseBudget("50,5")` was refused by name for being fractional while
    // `parseBudget(50.5)` returned half a peso, and `parseBudget(0.004)`
    // returned a budget of ZERO from a positive input.
    expect(() => parseBudget(50.5)).toThrow();
    expect(() => parseBudget(0.004)).toThrow();
    expect(parseBudget(50_000)).toBe(5_000_000);
  });
});

describe("a filled line with no product is not billed", () => {
  test("it neither renders nor counts", () => {
    // Dropping it from the body alone gave an empty basket whose summary still
    // read "1 of 1 lines · $ 5.550".
    const plan = fillToBudget(
      [line({ term: "arroz", price: 555_000, product: undefined })],
      1_000_000,
    );
    // The total is the assertion that matters. Excluding it from the RENDER
    // alone still left the summary reading "0 of 1 lines · $ 5.550" — a basket
    // that bills money for a product it cannot name.
    expect(plan.total).toBe(0);
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("0 of 1 lines");
    expect(out).toContain("could go in the basket");
    expect(out).not.toContain("$ 5.550");
  });
});

// ---------------------------------------------------------------------------
// buildBasket — driven end to end against a stubbed D1
//
// Round 2 of the review found that NOTHING in this suite called `buildBasket`.
// Every fix living in it — the substitute fallback, the honest `compared`
// counts, the pack-price flag, the unreachable/empty distinction — was
// revertible with the whole suite green. That is the hole these close.
// ---------------------------------------------------------------------------

interface WireOpts {
  available?: boolean;
  price?: number;
  unit?: string;
  value?: string;
}
const wire = (id: string, name: string, o: WireOpts = {}) => ({
  productId: id,
  productName: name,
  brand: "D1",
  linkText: id,
  categories: ["/Despensa/Granos/"],
  properties: o.unit
    ? [
        { name: "Unidad De Medida", values: [o.unit] },
        { name: "Valor de Medida", values: [o.value] },
      ]
    : [],
  items: [
    {
      itemId: id,
      nameComplete: name,
      sellers: [
        {
          sellerId: "1",
          commertialOffer: {
            Price: o.price ?? 1000,
            ListPrice: o.price ?? 1000,
            AvailableQuantity: o.available === false ? 0 : 25,
          },
        },
      ],
    },
  ],
});

/** A D1Client stand-in that answers search and SKU-lookup from canned payloads. */
function fakeClient(routes: {
  search?: unknown;
  sku?: unknown;
  skuThrows?: boolean;
  searchTotal?: number;
  /** Category sweep payload — `substitute` searches by FACET PATH, not query. */
  sweep?: unknown;
  sweepTotal?: number;
}) {
  const impl = (async (url: string) => {
    const u = new URL(String(url));
    if (u.pathname.includes("catalog_system")) {
      if (routes.skuThrows) throw new Error("ECONNRESET");
      return new Response(JSON.stringify(routes.sku ?? []), { status: 200 });
    }
    if (u.pathname.includes("intelligent-search/product_search")) {
      // A facet path is appended to the endpoint; a term search has none. That
      // is the only way to tell the category sweep from the shopper's own
      // query, and without it the sweep just replays the out-of-stock term and
      // the whole substitute path stays untested.
      const isSweep =
        u.pathname.replace(/\/api\/io\/_v\/api\/intelligent-search\/product_search\/?/, "") !== "";
      const products = ((isSweep && routes.sweep ? routes.sweep : routes.search) ??
        []) as unknown[];
      const total = isSweep
        ? (routes.sweepTotal ?? products.length)
        : (routes.searchTotal ?? products.length);
      return new Response(JSON.stringify({ products, recordsFiltered: total }), { status: 200 });
    }
    return new Response("[]", { status: 200 });
  }) as unknown as typeof fetch;
  return new D1Client({ fetchImpl: impl });
}

/** The catalog_system shape for a source SKU, so `findSubstitutes` can resolve it. */
const sourceSku = (id: string, name: string) => [
  {
    productId: id,
    productName: name,
    categories: ["/Panadería/Integral/"],
    items: wire(id, name, { available: false, price: 4000 }).items,
  },
];

describe("buildBasket", () => {
  test("fills a term with the best value it can actually buy", async () => {
    const plan = await buildBasket(
      fakeClient({
        search: [
          wire("small", "ARROZ 500 GRS", { price: 1550, unit: "Gr", value: "500" }),
          wire("big", "ARROZ 2000 GRS", { price: 5550, unit: "Gr", value: "2000" }),
        ],
        searchTotal: 40,
      }),
      ["arroz"],
      10_000_000,
    );
    expect(plan.lines[0]?.status).toBe("filled");
    expect(plan.lines[0]?.product?.skuId).toBe("big");
    // Two eligible products, of 40 D1 reported — not "40 compared".
    expect(plan.lines[0]?.compared).toBe(2);
    expect(plan.lines[0]?.matched).toBe(40);
  });

  test("a term D1 answers nothing for is no-match, compared 0", async () => {
    const plan = await buildBasket(fakeClient({ search: [] }), ["unicornio"], 10_000_000);
    expect(plan.lines[0]?.status).toBe("no-match");
    expect(plan.lines[0]?.compared).toBe(0);
  });

  test("an out-of-stock term reaches the substitute lookup at all", async () => {
    // Asserts the REQUEST, not the outcome. The previous version accepted
    // either of the only two statuses its own fixture could produce, so it was
    // a tautology: deleting the entire substitute path left it passing.
    const seen: string[] = [];
    const impl = (async (url: string) => {
      const u = String(url);
      seen.push(u);
      if (u.includes("catalog_system")) {
        return new Response(JSON.stringify(sourceSku("192", "PAN ARTESANAL INTEGRAL")), {
          status: 200,
        });
      }
      return new Response(
        JSON.stringify({
          products: [wire("192", "PAN ARTESANAL INTEGRAL", { available: false, price: 4000 })],
          recordsFiltered: 1,
        }),
        { status: 200 },
      );
    }) as unknown as typeof fetch;

    const plan = await buildBasket(new D1Client({ fetchImpl: impl }), ["pan"], 10_000_000);
    // It asked D1 about the SOURCE SKU — that is the fallback firing.
    expect(seen.some((u) => u.includes("catalog_system") && u.includes("192"))).toBe(true);
    expect(plan.lines[0]?.status).toBe("nothing-in-stock");
    expect(plan.lines[0]?.substituteSweep).toBe(true);
  });

  test("the substitute source is the best MATCH, not the cheapest per unit", async () => {
    // The page used to be re-sorted by unit price before `products[0]` was
    // taken as the source, so a shopper asking for rice whose rice was sold out
    // got replacements swept from the category of whatever was cheapest per
    // kilo — and the line read "replaces SAL REFINADA".
    const asked: string[] = [];
    const impl = (async (url: string) => {
      const u = String(url);
      if (u.includes("catalog_system")) {
        asked.push(u);
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(
        JSON.stringify({
          products: [
            wire("100", "ARROZ ESTÁNDAR 1000 GRS", {
              available: false,
              price: 5000,
              unit: "Gr",
              value: "1000",
            }),
            wire("200", "SAL REFINADA 3000 GRS", {
              available: false,
              price: 2000,
              unit: "Gr",
              value: "3000",
            }),
          ],
          recordsFiltered: 2,
        }),
        { status: 200 },
      );
    }) as unknown as typeof fetch;

    await buildBasket(new D1Client({ fetchImpl: impl }), ["arroz"], 10_000_000);
    // Relevance order puts the rice first; per-unit order would put the salt
    // first at $666/kg against the rice's $5.000/kg.
    expect(asked[0]).toContain("skuId%3A100");
    expect(asked[0]).not.toContain("skuId%3A200");
  });

  test("a replacement lookup that FAILS is unknown, not empty — and exits 1", async () => {
    // The blocker: a bare catch turned a transport failure into a positive
    // claim about the shelf, and exit 3 told an agent never to retry it.
    const plan = await buildBasket(
      fakeClient({
        search: [wire("192", "PAN ARTESANAL", { available: false, price: 4000 })],
        skuThrows: true,
      }),
      ["pan"],
      10_000_000,
    );
    expect(plan.lines[0]?.status).toBe("replacement-unknown");
    expect(basketExit(plan.lines)).toBe(1);
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("unknown, not empty");
    expect(out).not.toContain("had no replacement");
  });

  test("the region reaches the search, or every price is national", async () => {
    const calls: string[] = [];
    const impl = (async (url: string) => {
      calls.push(String(url));
      return new Response(JSON.stringify({ products: [], recordsFiltered: 0 }), { status: 200 });
    }) as unknown as typeof fetch;
    await buildBasket(new D1Client({ fetchImpl: impl }), ["arroz"], 10_000_000, {
      regionId: "v2.ABC",
    });
    expect(calls[0]).toContain("regionId=v2.ABC");
  });

  test("a sizeless winner is flagged, so the output can decline to call it best value", async () => {
    const plan = await buildBasket(
      fakeClient({
        search: [
          wire("a", "ARROZ GRANDE SIN PUM", { price: 20_000 }),
          wire("b", "ARROZ CHICO SIN PUM", { price: 1900 }),
        ],
      }),
      ["arroz"],
      10_000_000,
    );
    expect(plan.lines[0]?.byPackPrice).toBe(true);
    expect(renderBasket(plan, { regionId: "v2.ABC" })).toContain("chosen on pack price");
  });

  test("the budget still binds across several terms", async () => {
    const plan = await buildBasket(
      fakeClient({ search: [wire("x", "COSA", { price: 4000, unit: "Gr", value: "1000" })] }),
      ["a", "b", "c"],
      900_000,
    );
    expect(plan.total).toBeLessThanOrEqual(plan.budget);
    expect(plan.lines.filter((l) => l.status === "filled")).toHaveLength(2);
    expect(plan.lines[2]?.status).toBe("over-budget");
  });
});

describe("buildBasket — the substitute path, exercised end to end", () => {
  const outOfStockTerm = [wire("192", "PAN ARTESANAL INTEGRAL", { available: false, price: 4000 })];

  test("a real replacement fills the line, named and scoped honestly", async () => {
    const plan = await buildBasket(
      fakeClient({
        search: outOfStockTerm,
        searchTotal: 12,
        sku: sourceSku("192", "PAN ARTESANAL INTEGRAL"),
        // One buyable alternative among a pool padded with sold-out products.
        sweep: [
          wire("192", "PAN ARTESANAL INTEGRAL", { available: false, price: 4000 }),
          wire("738", "TOSTADA INTEGRAL", { price: 1950, unit: "Gr", value: "150" }),
          ...Array.from({ length: 20 }, (_, i) =>
            wire(`gone${i}`, `PAN AGOTADO ${i}`, { available: false, price: 3000 }),
          ),
        ],
        sweepTotal: 140,
      }),
      ["pan"],
      10_000_000,
    );
    const l = plan.lines[0];
    expect(l?.status).toBe("filled-by-substitute");
    expect(l?.product?.skuId).toBe("738");
    expect(l?.replaces?.skuId).toBe("192");
    // `rankedCount`, not the 22-product pool: one alternative was rankable.
    expect(l?.compared).toBe(1);
    expect(l?.substituteSweep).toBe(true);

    const out = renderBasket(plan, { regionId: "v2.ABC" });
    // The count came from a CATEGORY sweep, so it must not be compared against
    // `matched`, which counts the term's own search.
    expect(out).toContain("in its category");
    expect(out).not.toContain("D1 matched");
    expect(out).toContain("replaces");
  });

  test("a rankable candidate with no price is not a replacement", async () => {
    // `rankSubstitutes` filters on availability only. VTEX reports Price 0
    // ("no offer in this region") alongside a positive AvailableQuantity, so an
    // unbuyable candidate can rank — and it reached the basket, where the line
    // was downgraded and rendered "its category had no replacement" while still
    // carrying the product it had just found.
    const plan = await buildBasket(
      fakeClient({
        search: outOfStockTerm,
        sku: sourceSku("192", "PAN ARTESANAL INTEGRAL"),
        sweep: [wire("738", "TOSTADA SIN OFERTA", { price: 0 })],
        sweepTotal: 140,
      }),
      ["pan"],
      10_000_000,
    );
    const l = plan.lines[0];
    expect(l?.status).toBe("nothing-in-stock");
    // Critically: it must not claim to have found something it cannot sell.
    expect(l?.status).not.toBe("filled-by-substitute");
    expect(l?.replaces).toBeUndefined();
    expect(plan.total).toBe(0);
  });

  test("a replacement is never described as the best value for the term", async () => {
    // It is not chosen by value and not chosen from the term's own results — it
    // is the closest match in a category. Saying "best value among the products
    // fetched for its term" is false twice, and "chosen on pack price" (an
    // earlier attempt at this) misnames the mechanism a third way: substitutes
    // are ranked by name similarity and price PROXIMITY, never by pack price.
    const plan = await buildBasket(
      fakeClient({
        search: outOfStockTerm,
        sku: sourceSku("192", "PAN ARTESANAL INTEGRAL"),
        sweep: [wire("738", "TOSTADA SIN PUM", { price: 1950 })],
      }),
      ["pan"],
      10_000_000,
    );
    expect(plan.lines[0]?.status).toBe("filled-by-substitute");
    expect(plan.lines[0]?.byPackPrice).toBeUndefined();
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).not.toContain("chosen on pack price");
    expect(out).toContain("closest match from its category");
  });

  test("an empty category is reported as swept, not as a term with no matches", () => {
    // Render-level. Its end-to-end sibling below asserts that production
    // actually COMPUTES the flag and the count this fixture hands it — round 4
    // replaced the end-to-end version with this one and thereby stopped
    // observing the production path entirely.
    const plan = fillToBudget(
      [
        line({
          term: "pan",
          status: "nothing-in-stock",
          product: undefined,
          compared: 39,
          inStock: 39,
          matched: 12,
          substituteSweep: true,
        }),
      ],
      1_000_000,
    );
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("39 in its category");
    expect(out).not.toContain("12");
  });

  test("and production computes that flag and count itself", async () => {
    // The regression this catches: `compared` was briefly `buyable.length`,
    // which is 0 BY CONSTRUCTION on the empty path — so "(4 compared)" became
    // "(0 compared)" for every empty sweep, indistinguishable from an empty
    // category, and the number could no longer vary with the shelf at all.
    const plan = await buildBasket(
      fakeClient({
        search: [wire("192", "PAN ARTESANAL INTEGRAL", { available: false, price: 4000 })],
        searchTotal: 12,
        sku: sourceSku("192", "PAN ARTESANAL INTEGRAL"),
        // In stock, but D1 publishes no offer for any of them here.
        sweep: [
          wire("500", "PAN A", { price: 0 }),
          wire("501", "PAN B", { price: 0 }),
          wire("502", "PAN C", { price: 0 }),
        ],
        sweepTotal: 140,
      }),
      ["pan"],
      10_000_000,
    );
    const l = plan.lines[0];
    expect(l?.status).toBe("nothing-in-stock");
    expect(l?.substituteSweep).toBe(true);
    // Must vary with the shelf, not collapse to zero.
    expect(l?.compared).toBe(3);
    expect(l?.inStock).toBe(3);
    const rendered = renderBasket(plan, { regionId: "v2.ABC" });
    expect(rendered).toContain("3 in its category");
    // The sweep read 3 products of a category D1 says holds 140. `d1
    // substitute` says so on this exact sentence; the basket must too.
    expect(rendered).toContain("only 3 of 140 in that category were searched");
  });

  test("a truly empty category says so, rather than counting nothing", async () => {
    const plan = await buildBasket(
      fakeClient({
        search: [wire("192", "PAN ARTESANAL INTEGRAL", { available: false, price: 4000 })],
        sku: sourceSku("192", "PAN ARTESANAL INTEGRAL"),
        sweep: [wire("x", "TODO AGOTADO", { available: false, price: 3000 })],
      }),
      ["pan"],
      10_000_000,
    );
    expect(plan.lines[0]?.inStock).toBe(0);
    // "nothing in its category" would be a universal over one page of a
    // category that may hold hundreds. It is hedged to what was searched.
    expect(renderBasket(plan, { regionId: "v2.ABC" })).toContain(
      "nothing in the part of its category that was searched is either",
    );
  });

  test("the ranker's order decides which replacement is used", async () => {
    // `buyable[0]` was unpinned: reversing it, or re-sorting by price, both left
    // the suite green because no fixture had two buyable candidates.
    const plan = await buildBasket(
      fakeClient({
        search: [wire("192", "PAN ARTESANAL INTEGRAL", { available: false, price: 4000 })],
        sku: sourceSku("192", "PAN ARTESANAL INTEGRAL"),
        sweep: [
          // Closest by name, and NOT the cheapest — so a price-sorted or
          // reversed pick would choose differently.
          wire("700", "PAN ARTESANAL INTEGRAL GRANDE", { price: 4100 }),
          wire("900", "GALLETA BARATA", { price: 1000 }),
        ],
      }),
      ["pan"],
      10_000_000,
    );
    expect(plan.lines[0]?.status).toBe("filled-by-substitute");
    expect(plan.lines[0]?.product?.skuId).toBe("700");
    expect(plan.lines[0]?.compared).toBe(2);
  });
});

describe("renderBasket defends itself against a hand-built plan", () => {
  test("a filled line with no product is not rendered as a row", () => {
    // `fillToBudget` already downgrades such a line, so this guard is
    // unreachable through the normal path — but `renderBasket` is exported and
    // takes a plan directly, which is exactly how these tests call it. Without
    // the guard the row renders with an empty name and a real price.
    const out = renderBasket(
      {
        budget: 1_000_000,
        lines: [line({ term: "arroz", price: 555_000, product: undefined })],
        total: 555_000,
        remaining: 445_000,
      },
      { regionId: "v2.ABC" },
    );
    expect(out).toContain("could go in the basket");
    expect(out).toContain("0 of 1 lines");
  });
});

describe("a budget must be the number that was typed", () => {
  test("one too large to represent exactly is refused", () => {
    // Past MAX_SAFE_INTEGER/100 the conversion to hundredths loses integer
    // precision, so the ceiling enforced is not the one asked for — silently
    // becoming a different plausible number is what this parser exists to stop.
    expect(parseBudget(90_071_992_547_409)).toBe(9_007_199_254_740_900);
    expect(() => parseBudget(90_071_992_547_410)).toThrow(/too large/);
    expect(() => parseBudget("999.999.999.999.999.999")).toThrow(/too large/);
    // A trillion pesos is still fine — the bound refuses nothing realistic.
    expect(parseBudget(1_000_000_000_000)).toBe(100_000_000_000_000);
  });
});

describe("a replacement is skipped when it cannot be bought", () => {
  test("and the PRICED runner-up is used instead", async () => {
    // `findSubstitutes` slices to `limit` before returning, so asking for one
    // and then skipping unpriced candidates skipped the only candidate there
    // was — the fix was inert and a buyable runner-up was reported as an empty
    // category.
    const plan = await buildBasket(
      fakeClient({
        search: [wire("192", "PAN ARTESANAL INTEGRAL", { available: false, price: 4000 })],
        sku: sourceSku("192", "PAN ARTESANAL INTEGRAL"),
        sweep: [
          // Ranks first, in stock, but D1 publishes no offer for it here.
          wire("500", "PAN INTEGRAL SIN OFERTA", { price: 0, unit: "Gr", value: "500" }),
          wire("738", "TOSTADA INTEGRAL", { price: 1950, unit: "Gr", value: "150" }),
        ],
      }),
      ["pan"],
      10_000_000,
    );
    expect(plan.lines[0]?.status).toBe("filled-by-substitute");
    expect(plan.lines[0]?.product?.skuId).toBe("738");
    expect(plan.total).toBe(195_000);
  });
});

describe("the footer names every mechanism actually in play", () => {
  const valued = line({
    term: "arroz",
    price: 555_000,
    product: product("1075", "ARROZ 2000 GRS", 555_000, { measure: "kg", amount: 2 }),
  });
  const packPriced = line({
    term: "cosa",
    price: 190_000,
    product: product("x", "COSA SIN PUM", 190_000),
    byPackPrice: true,
  });
  const swapped = line({
    term: "pan",
    price: 195_000,
    status: "filled-by-substitute",
    product: product("738", "TOSTADA", 195_000, { measure: "kg", amount: 0.15 }),
    replaces: product("192", "PAN ARTESANAL", 400_000, { available: false }),
    substituteSweep: true,
  });
  const foot = (...ls: BasketLine[]) => {
    const out = renderBasket(fillToBudget(ls, 10_000_000), { regionId: "v2.ABC" });
    return out.slice(
      out.lastIndexOf("Each line") === -1
        ? out.lastIndexOf("Every line")
        : out.lastIndexOf("Each line"),
    );
  };

  test("value only — no pack-price clause, no replacement clause", () => {
    const f = foot(valued);
    expect(f).not.toContain("pack price");
    expect(f).not.toContain("replacement");
  });

  test("a pack-price line adds its clause, and only then", () => {
    // Round 4 proved this clause had zero coverage in EITHER polarity, so it
    // could be deleted, inverted, or replaced with nonsense, all with a green
    // suite — while a code comment justified dropping another disclosure on the
    // grounds that "the footer covers the rest".
    expect(foot(packPriced)).toContain("by pack price where D1 publishes no size");
    expect(foot(valued)).not.toContain("by pack price");
  });

  test("a mixed basket names the replacement as an exception", () => {
    const f = foot(valued, swapped);
    expect(f).toContain("except a replacement");
  });

  test("an all-replacement basket does not call the exception a rule", () => {
    // "Each line is the best among the products fetched for its term … except a
    // replacement" is false for 100% of a basket where every line IS one.
    const f = foot(swapped);
    expect(f).toContain("Every line here is a replacement");
    expect(f).not.toContain("except a replacement");
  });
});

describe("an unanswered lookup outranks an affordability claim", () => {
  test("a mixed empty basket does not blame the budget", () => {
    // The prose and the exit code are two outputs of one invocation. Blaming
    // the budget while exiting 1 ("D1 could not be reached, a retry may help")
    // tells one reader to raise the budget and another to retry.
    const plan = fillToBudget(
      [
        line({ term: "arroz", price: 900_000 }),
        line({ term: "pan", status: "replacement-unknown", product: undefined }),
      ],
      10_000,
    );
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).not.toContain("Nothing fits this budget");
    expect(out).toContain("did not answer");
    expect(basketExit(plan.lines)).toBe(1);
  });

  test("a purely unaffordable basket still says so", () => {
    const plan = fillToBudget([line({ term: "arroz", price: 900_000 })], 10_000);
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("the budget was short");
    expect(out).not.toContain("D1 did not answer");
  });

  test("a mixed basket names BOTH reasons, rather than picking one", () => {
    // Priority-picking made the headline false for whichever lines the losing
    // condition described — "nothing could be checked" printed directly above a
    // line whose price was known and rejected.
    const plan = fillToBudget(
      [
        line({ term: "arroz", price: 900_000 }),
        line({ term: "pan", status: "replacement-unknown", product: undefined }),
      ],
      10_000,
    );
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("D1 did not answer");
    expect(out).toContain("the budget was short");
  });
});

describe("a substitute line counts only what could be bought", () => {
  test("candidates with no price are not part of 'best of N'", async () => {
    // `rankedCount` counts everything past the AVAILABILITY filter, but the
    // price filter rejects more — so the line said "best of 4 in its category"
    // for the only buyable one of four, which is this module's own stated
    // invariant broken on the one path that did not enforce it.
    const plan = await buildBasket(
      fakeClient({
        search: [wire("192", "PAN ARTESANAL INTEGRAL", { available: false, price: 4000 })],
        sku: sourceSku("192", "PAN ARTESANAL INTEGRAL"),
        sweep: [
          wire("500", "PAN ARTESANAL INTEGRAL BIS", { price: 0 }),
          wire("501", "PAN ARTESANAL SIN OFERTA", { price: 0 }),
          wire("738", "TOSTADA INTEGRAL", { price: 1950, unit: "Gr", value: "150" }),
        ],
      }),
      ["pan"],
      10_000_000,
    );
    expect(plan.lines[0]?.status).toBe("filled-by-substitute");
    expect(plan.lines[0]?.product?.skuId).toBe("738");
    // One buyable candidate — not three.
    expect(plan.lines[0]?.compared).toBe(1);
    expect(renderBasket(plan, { regionId: "v2.ABC" })).toContain("best of 1 in its category");
  });
});

describe("the summary bills what the body shows", () => {
  test("a hand-built plan cannot charge for a line it does not render", () => {
    const out = renderBasket(
      {
        budget: 1_000_000,
        lines: [line({ term: "arroz", price: 555_000, product: undefined })],
        total: 555_000,
        remaining: 445_000,
      },
      { regionId: "v2.ABC" },
    );
    expect(out).toContain("0 of 1 lines");
    // The count was fixed in an earlier round; the money was not.
    expect(out).not.toContain("$ 5.550");
    expect(out).toContain("$ 0 of $ 10.000");
  });
});

describe("a categorical claim is only as wide as the sweep behind it", () => {
  const term = [wire("192", "PAN ARTESANAL INTEGRAL", { available: false, price: 4000 })];

  test("a filled replacement discloses how partial the look was", async () => {
    // `scopeOf` printed "best of 2 in its category" with no denominator, while
    // an ordinary line printed "best of 20 compared, of 29 D1 matched". Same
    // command, two standards.
    const plan = await buildBasket(
      fakeClient({
        search: term,
        sku: sourceSku("192", "PAN ARTESANAL INTEGRAL"),
        sweep: [
          wire("738", "TOSTADA INTEGRAL", { price: 1950, unit: "Gr", value: "150" }),
          wire("739", "TOSTADA OTRA", { price: 2500, unit: "Gr", value: "150" }),
        ],
        sweepTotal: 140,
      }),
      ["pan"],
      10_000_000,
    );
    expect(plan.lines[0]?.status).toBe("filled-by-substitute");
    expect(plan.lines[0]?.categoryTotal).toBe(140);
    expect(renderBasket(plan, { regionId: "v2.ABC" })).toContain(
      "only 2 of 140 in that category were searched",
    );
  });

  test("a complete sweep claims no partiality it does not have", async () => {
    // When the page held the whole category there is nothing to disclose, and
    // adding the caveat anyway would be its own false statement.
    const plan = await buildBasket(
      fakeClient({
        search: term,
        sku: sourceSku("192", "PAN ARTESANAL INTEGRAL"),
        sweep: [wire("738", "TOSTADA INTEGRAL", { price: 1950, unit: "Gr", value: "150" })],
        sweepTotal: 1,
      }),
      ["pan"],
      10_000_000,
    );
    expect(renderBasket(plan, { regionId: "v2.ABC" })).not.toContain("were searched");
  });
});
