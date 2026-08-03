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
    expect(out).not.toContain("Each line is the best value");
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
    expect(out).toContain("Nothing fits this budget.");
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

  test("an out-of-stock term falls through to a substitute, and names it", async () => {
    const plan = await buildBasket(
      fakeClient({
        search: [wire("192", "PAN ARTESANAL", { available: false, price: 4000 })],
        sku: [
          {
            productId: "192",
            productName: "PAN ARTESANAL",
            categories: ["/Panadería/Integral/"],
            items: wire("192", "PAN ARTESANAL", { available: false, price: 4000 }).items,
          },
        ],
      }),
      ["pan"],
      10_000_000,
    );
    // The sweep uses the same stubbed search, which returns the out-of-stock
    // source only, so there is no replacement — but the line must say that
    // truthfully rather than claiming the term matched nothing.
    expect(["nothing-in-stock", "replacement-unknown"]).toContain(plan.lines[0]?.status);
    expect(plan.lines[0]?.status).not.toBe("no-match");
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

  test("a sizeless replacement is not called best value", async () => {
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
    expect(plan.lines[0]?.byPackPrice).toBe(true);
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("chosen on pack price");
    expect(out).not.toContain("Each line is the best value");
  });

  test("an empty category says so without a sweep-vs-search number mix", async () => {
    const plan = await buildBasket(
      fakeClient({
        search: outOfStockTerm,
        searchTotal: 12,
        sku: sourceSku("192", "PAN ARTESANAL INTEGRAL"),
        sweep: [wire("x", "TODO AGOTADO", { available: false, price: 3000 })],
        sweepTotal: 140,
      }),
      ["pan"],
      10_000_000,
    );
    const l = plan.lines[0];
    expect(l?.status).toBe("nothing-in-stock");
    // The count is the sweep's, so it must be labelled as such rather than held
    // against `matched` (12) — which would print a denominator below it.
    expect(l?.substituteSweep).toBe(true);
    expect(renderBasket(plan, { regionId: "v2.ABC" })).not.toContain("of 12 D1 matched");
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
    expect(out).toContain("Nothing fits this budget.");
    expect(out).toContain("0 of 1 lines");
  });
});
