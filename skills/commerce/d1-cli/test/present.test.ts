import { describe, expect, test } from "bun:test";
import { addOutcome, parseArgs, parseSpec, quantityFlag } from "../src/cli.ts";
import {
  bestOffer,
  humanEstimate,
  renderCart,
  renderRegion,
  renderSearch,
  renderSubstitutes,
  sanitize,
} from "../src/present.ts";
import type { Candidate, SubstituteResult } from "../src/substitute.ts";
import type { Product, SearchPage } from "../src/types.ts";
import { D1Error, UsageError } from "../src/types.ts";

const product = (over: Partial<Product> = {}): Product => ({
  productId: "262",
  skuId: "262",
  name: "LECHE ENTERA TETRAPAK UHT LATTI 900 ML",
  brand: "LATTI",
  linkText: "leche",
  categories: [],
  warnings: [],
  offers: [
    {
      sellerId: "1",
      sellerName: "Tiendas D1",
      price: 350_000,
      listPrice: 350_000,
      available: true,
      availableQuantity: 10,
    },
  ],
  ...over,
});

describe("bestOffer", () => {
  test("prefers the cheapest available offer", () => {
    const p = product({
      offers: [
        {
          sellerId: "a",
          sellerName: "a",
          price: 400_000,
          listPrice: 400_000,
          available: true,
          availableQuantity: 1,
        },
        {
          sellerId: "b",
          sellerName: "b",
          price: 300_000,
          listPrice: 300_000,
          available: true,
          availableQuantity: 1,
        },
      ],
    });
    expect(bestOffer(p)?.sellerId).toBe("b");
  });

  test("never picks an out-of-stock offer over an available one, even if cheaper", () => {
    const p = product({
      offers: [
        {
          sellerId: "cheap",
          sellerName: "cheap",
          price: 100_000,
          listPrice: 100_000,
          available: false,
          availableQuantity: 0,
        },
        {
          sellerId: "real",
          sellerName: "real",
          price: 300_000,
          listPrice: 300_000,
          available: true,
          availableQuantity: 5,
        },
      ],
    });
    expect(bestOffer(p)?.sellerId).toBe("real");
  });

  test("still reports a price when nothing is in stock", () => {
    const p = product({
      offers: [
        {
          sellerId: "x",
          sellerName: "x",
          price: 100_000,
          listPrice: 100_000,
          available: false,
          availableQuantity: 0,
        },
      ],
    });
    expect(bestOffer(p)?.price).toBe(100_000);
  });
});

describe("renderSearch", () => {
  const page: SearchPage = { products: [product()], total: 1, truncated: false };

  test("shows the price in pesos", () => {
    expect(renderSearch(page, { regionId: "v2.X" })).toContain("$ 3.500");
  });

  test("warns that prices are national when no region was resolved", () => {
    // The most consequential thing this CLI can get wrong is presenting a
    // national catalogue as if it were local stock.
    expect(renderSearch(page)).toContain("national");
    expect(renderSearch(page, { regionId: "v2.X" })).not.toContain("Prices are national");
  });

  test("says so when results run deeper than pagination reaches", () => {
    const deep: SearchPage = { products: [product()], total: 5000, truncated: true };
    expect(renderSearch(deep, { regionId: "v2.X" })).toContain("--facets");
  });

  test("empty results say nothing matched rather than printing a bare header", () => {
    expect(renderSearch({ products: [], total: 0, truncated: false })).toBe("No products matched.");
  });

  test("a product VTEX prices at 0 shows a dash, not `$ 0`", () => {
    // `$ 0` beside a real grocery item reads as free. VTEX reports 0 for a
    // product it has no offer for in this region — observed live on SKU 1687,
    // which rendered as `$ 0   $ 0/kg   out of stock`.
    const unpriced = product({
      offers: [
        {
          sellerId: "1",
          sellerName: "Tiendas D1",
          price: 0,
          listPrice: 0,
          available: false,
          availableQuantity: 0,
        },
      ],
    });
    const out = renderSearch(
      { products: [unpriced], total: 1, truncated: false },
      {
        regionId: "v2.X",
      },
    );
    expect(out).not.toContain("$ 0");
    expect(out).toContain("—");
    expect(out).toContain("out of stock");
  });

  test("no discount is computed from a price it just declined to print", () => {
    // The one-sided-coverage hole: both zero-price fixtures pinned `listPrice:
    // 0` too, so the guard was only ever exercised in the polarity where it
    // could not fail. With a real list price, `{price: 0}` rendered as
    // `—    -100%` — a discount measured from the very non-price the column to
    // its left had refused to show, and a worse lie than the `$ 0` was.
    const unpriced = product({
      offers: [
        {
          sellerId: "1",
          sellerName: "Tiendas D1",
          price: 0,
          listPrice: 930_000,
          available: false,
          availableQuantity: 0,
        },
      ],
    });
    const out = renderSearch(
      { products: [unpriced], total: 1, truncated: false },
      {
        regionId: "v2.X",
      },
    );
    expect(out).not.toContain("-100%");
    expect(out).not.toContain("$ 0");
  });

  test("a genuine discount IS still shown (anti-overshoot control)", () => {
    // Without this the assertion above passes on a renderer that never shows a
    // discount at all.
    const onSale = product({
      offers: [
        {
          sellerId: "1",
          sellerName: "Tiendas D1",
          price: 300_000,
          listPrice: 400_000,
          available: true,
          availableQuantity: 5,
        },
      ],
    });
    expect(
      renderSearch({ products: [onSale], total: 1, truncated: false }, { regionId: "v2.X" }),
    ).toContain("-25%");
  });

  test("an unpriced product is not accused of publishing no pack size", () => {
    // It publishes one perfectly well; it just has no offer here. The count
    // reads `size`, not `unitPrice`, because those stopped being the same
    // question once a zero price stopped yielding a unit price.
    const unpriced = product({
      size: { measure: "L", amount: 0.9 },
      unitPrice: undefined,
      offers: [
        {
          sellerId: "1",
          sellerName: "Tiendas D1",
          price: 0,
          listPrice: 0,
          available: false,
          availableQuantity: 0,
        },
      ],
    });
    expect(
      renderSearch({ products: [unpriced], total: 1, truncated: false }, { regionId: "v2.X" }),
    ).not.toContain("publish no pack size");
  });
});

describe("renderSubstitutes", () => {
  // The whole human-facing surface of `d1 substitute`. It shipped with no
  // tests at all, and a mutation sweep found that EIGHT independent semantic
  // inversions — including swapping "in stock" with "cannot supply" and
  // recommending the worst-ranked candidate — left the suite at 270 pass.
  const sized = (over: Partial<Product> = {}): Product =>
    product({ size: { measure: "L", amount: 0.9 }, unitPrice: 388_889, ...over });

  const candidate = (
    skuId: string,
    name: string,
    price: number,
    over: Partial<Candidate> = {},
  ): Candidate => ({
    product: product({
      skuId,
      name,
      size: { measure: "L", amount: 0.9 },
      unitPrice: Math.round(price / 0.9),
      offers: [
        {
          sellerId: "1",
          sellerName: "Tiendas D1",
          price,
          listPrice: price,
          available: true,
          availableQuantity: 5,
        },
      ],
    }),
    score: 0.9,
    tier: 0,
    deltas: [],
    ...over,
  });

  const base = (over: Partial<SubstituteResult> = {}): SubstituteResult => ({
    source: sized(),
    sourceAvailable: false,
    sourcePricedNationally: false,
    categoryPath: "Lacteos y huevos/Leches/Entera",
    searchedDepth: 3,
    categoryDepth: 3,
    poolSize: 7,
    poolProducts: 7,
    poolTotal: 7,
    rankedCount: 1,
    candidates: [candidate("892", "LECHE ENTERA BOLSA LATTI 900 ML", 320_000)],
    regionId: "v2.REGION",
    ...over,
  });

  test("says the source is out of stock, and does not say the opposite", () => {
    const out = renderSubstitutes(base({ sourceAvailable: false }));
    expect(out).toContain("cannot supply");
    expect(out).not.toContain("still in stock");
  });

  test("says the source IS in stock when it is — both polarities, so neither can invert", () => {
    const out = renderSubstitutes(base({ sourceAvailable: true }));
    expect(out).toContain("still in stock");
    expect(out).not.toContain("cannot supply");
  });

  test("makes no per-store stock claim when no delivery point is set", () => {
    // Availability is per-store. Saying "still in stock at your store" and then
    // "stock is NATIONAL and may not reflect your store" is self-contradiction.
    const out = renderSubstitutes(base({ regionId: undefined, sourceAvailable: true }));
    expect(out).not.toContain("still in stock at your store");
    expect(out).not.toContain("cannot supply");
    // Said ONCE, in the scope block that prints on both the empty and
    // non-empty paths. It used to be said twice, four lines apart, in two
    // near-identical sentences — which reads as a rendering bug, not emphasis.
    expect(out.match(/No delivery point set/g)).toHaveLength(1);
    expect(out).toContain("NATIONAL");
  });

  test("recommends the FIRST candidate, which is the closest one", () => {
    const out = renderSubstitutes(
      base({
        rankedCount: 2,
        candidates: [
          candidate("892", "LECHE ENTERA BOLSA LATTI 900 ML", 320_000),
          candidate("645", "LECHE DESLACTOSADA LATTI 900 ML", 990_000, { score: 0.2 }),
        ],
      }),
    );
    expect(out).toContain("d1 cart add 892");
    expect(out).not.toContain("d1 cart add 645");
  });

  test("an unpriced source says so instead of printing `$ 0`", () => {
    // The live `$ 0 · $ 0/kg` was observed on THIS surface, and the guard was
    // pinned only on renderSearch.
    const out = renderSubstitutes(
      base({
        source: sized({
          unitPrice: undefined,
          offers: [
            {
              sellerId: "1",
              sellerName: "Tiendas D1",
              price: 0,
              listPrice: 0,
              available: false,
              availableQuantity: 0,
            },
          ],
        }),
      }),
    );
    expect(out).not.toContain("$ 0");
    expect(out).toContain("no price at this store");
  });

  test("separates measure tiers, so incomparable per-unit prices are not read as a ranking", () => {
    const out = renderSubstitutes(
      base({
        rankedCount: 2,
        candidates: [
          candidate("892", "LECHE ENTERA BOLSA LATTI 900 ML", 320_000, { tier: 0 }),
          candidate("900", "LECHE ENTERA LATTI", 350_000, { tier: 1 }),
        ],
      }),
    );
    expect(out).toContain("measured differently");
  });

  test("no separator when every candidate is comparable", () => {
    // The control. Without it the assertion above passes on a renderer that
    // prints the separator unconditionally.
    expect(renderSubstitutes(base())).not.toContain("measured differently");
  });

  test("an empty result still carries every caveat that qualifies it", () => {
    // The defect these tests exist to catch: the empty path used to return
    // early, so the command asserted "nothing in this category is in stock"
    // while suppressing that it compared 3 of 140 products, that it had already
    // widened, and that stock was national. A negative over a partial sweep
    // needs its caveats MORE than a positive does.
    const out = renderSubstitutes(
      base({
        candidates: [],
        rankedCount: 0,
        regionId: undefined,
        poolSize: 3,
        poolProducts: 3,
        poolTotal: 140,
        searchedDepth: 1,
        categoryDepth: 3,
      }),
    );
    expect(out).toContain("Nothing in Lacteos y huevos/Leches/Entera is in stock");
    expect(out).toContain("only 3 were compared");
    expect(out).toContain("widened to level 1 of 3");
    expect(out).toContain("NATIONAL");
  });

  test("reports a partial sweep and a widened search when there ARE candidates too", () => {
    const out = renderSubstitutes(
      base({ poolProducts: 3, poolTotal: 140, searchedDepth: 2, categoryDepth: 3 }),
    );
    expect(out).toContain("only 3 were compared");
    expect(out).toContain("widened to level 2 of 3");
  });

  test("claims neither when the sweep was complete and unwidened", () => {
    // Control for the pair above.
    const out = renderSubstitutes(base());
    expect(out).not.toContain("were compared");
    expect(out).not.toContain("widened");
  });

  test("counts what was ranked, not what was fetched", () => {
    // `poolSize` includes the source itself and every out-of-stock item, so
    // reporting it as the comparison count overstated the work by both.
    const out = renderSubstitutes(base({ poolSize: 7, poolProducts: 7, rankedCount: 1 }));
    expect(out).toContain("1 in-stock alternative");
    expect(out).not.toContain("7 in-stock");
  });

  test("says when the list was truncated by --limit", () => {
    const out = renderSubstitutes(base({ rankedCount: 12 }));
    expect(out).toContain("showing the closest 1");
  });

  test("strips the invisible classes too, not just C0/C1", () => {
    // C0/C1 alone left three classes that defeat the same stated purpose:
    // U+2028/U+2029 break a line in many terminals and log viewers (forging an
    // output line by a different codepoint than the newline the guard names),
    // bidi overrides visually REORDER the line so a price or a warning can read
    // as something it is not, and zero-width characters break the column
    // arithmetic `pad` does on string length.
    for (const [label, ch] of [
      ["U+2028 line separator", "\u2028"],
      ["U+2029 paragraph separator", "\u2029"],
      ["U+202E right-to-left override", "\u202e"],
      ["U+2066 isolate", "\u2066"],
      ["U+200B zero-width space", "\u200b"],
      ["U+FEFF byte-order mark", "\ufeff"],
    ] as const) {
      expect({ label, present: sanitize(`A${ch}B`).includes(ch) }).toEqual({
        label,
        present: false,
      });
    }
    // Anti-overshoot: ordinary Spanish text is untouched.
    expect(sanitize("Panadería y repostería · $ 3.500")).toBe("Panadería y repostería · $ 3.500");
  });

  test("strips terminal control characters out of upstream text", () => {
    // Product names, brands and warning KEY NAMES are all upstream data. An
    // ESC[2J in one clears the screen, erasing the "Nothing was added to your
    // cart" line; in an agent-driven CLI the injected text lands in the
    // transcript verbatim.
    const evil = "LECHE \u001b[2J\u001b]0;pwned\u0007 ENTERA";
    const out = renderSubstitutes(
      base({
        // The SKU ID carries the payload too. It was the one field the earlier
        // fixture left clean, and it was also the one render path that
        // interpolated raw — the closing `d1 cart add <sku>` line. An ESC[2J
        // landing there clears the screen AFTER everything prints, erasing the
        // "Nothing was added to your cart" line itself.
        source: sized({ skuId: `262${evil}`, name: evil, warnings: [evil] }),
        categoryPath: `Lacteos${evil}`,
        candidates: [
          candidate(`892${evil}`, evil, 320_000, { deltas: [{ kind: "brand", text: evil }] }),
        ],
      }),
    );
    // biome-ignore lint/suspicious/noControlCharactersInRegex: asserting their absence is the point
    expect(out).not.toMatch(/[\u0000-\u0009\u000b-\u001f\u007f-\u009f]/);
    expect(out).toContain("LECHE");
  });
});

describe("renderRegion", () => {
  test("states plainly when D1 does not deliver to a point", () => {
    const out = renderRegion({ id: "v2.X", sellers: [], at: { lat: 4.6, lng: -74.1 } });
    expect(out).toContain("does not deliver");
  });

  test("names the fulfilling store when it does", () => {
    const out = renderRegion({
      id: "v2.X",
      sellers: [{ id: "d1bon11808cc", name: "D1 Bogota" }],
      at: { lat: 4.6, lng: -74.1 },
    });
    expect(out).toContain("d1bon11808cc");
  });
});

describe("renderCart", () => {
  test("flags an unpriced delivery instead of implying free shipping", () => {
    const out = renderCart({
      orderFormId: "of1",
      loggedIn: false,
      items: [
        {
          skuId: "262",
          name: "LECHE",
          quantity: 2,
          sellerId: "1",
          sellingPrice: 350_000,
          total: 700_000,
        },
      ],
      itemsTotal: 700_000,
      discounts: 0,
      total: 700_000,
      shipping: [],
      messages: [],
    });
    expect(out).toContain("Shipping not quoted");
    expect(out).toContain("$ 7.000");
  });

  test("an empty cart says so", () => {
    expect(
      renderCart({
        orderFormId: "of1",
        loggedIn: false,
        items: [],
        itemsTotal: 0,
        discounts: 0,
        total: 0,
        shipping: [],
        messages: [],
      }),
    ).toBe("Cart is empty.");
  });
});

describe("humanEstimate", () => {
  test("expands VTEX shorthand", () => {
    expect(humanEstimate("1bd")).toBe("1 business day");
    expect(humanEstimate("3bd")).toBe("3 business days");
    expect(humanEstimate("24h")).toBe("24 hours");
  });

  test("passes through anything it does not recognize", () => {
    expect(humanEstimate("")).toBe("");
    expect(humanEstimate("tomorrow")).toBe("tomorrow");
  });
});

describe("parseArgs", () => {
  test("separates positionals from flags", () => {
    const a = parseArgs(["search", "leche", "entera", "--count", "5", "--json"]);
    expect(a.positional).toEqual(["search", "leche", "entera"]);
    expect(a.flags.count).toBe("5");
    expect(a.flags.json).toBe(true);
  });

  test("supports --key=value", () => {
    expect(parseArgs(["--lat=4.65"]).flags.lat).toBe("4.65");
  });

  test("a negative number is a value, not the next flag", () => {
    // Exercises the LOOKAHEAD branch (space-separated), which is the one the
    // hazard lives in: a parser guarding with startsWith("-") instead of
    // startsWith("--") reads the longitude as a flag and every
    // `--lng -74.06` invocation breaks. The `--lng=-74.06` form takes the
    // `indexOf("=")` branch and would NOT catch that regression, so it is
    // asserted separately below rather than standing in for this.
    const a = parseArgs(["region", "--lat", "4.65", "--lng", "-74.06"]);
    expect(a.flags.lat).toBe("4.65");
    expect(a.flags.lng).toBe("-74.06");
    expect(a.positional).toEqual(["region"]);
  });

  test("the equals form also carries a negative value", () => {
    expect(parseArgs(["--lng=-74.06"]).flags.lng).toBe("-74.06");
  });

  test("a trailing valueless flag stays boolean", () => {
    expect(parseArgs(["cart", "--json"]).flags.json).toBe(true);
  });
});

describe("parseSpec", () => {
  test("a bare SKU means one unit", () => {
    expect(parseSpec("262")).toEqual({ skuId: "262", quantity: 1 });
  });

  test("sku:qty parses", () => {
    expect(parseSpec("262:3")).toEqual({ skuId: "262", quantity: 3 });
  });

  test("a malformed quantity errors instead of silently becoming 1", () => {
    // The failure this replaces: `Number(qty) || 1` turned every unparseable
    // quantity into a single unit, so the caller got a confident total for a
    // basket they did not ask about.
    expect(() => parseSpec("262:abc")).toThrow(/positive whole number/);
    expect(() => parseSpec("262:2 892")).toThrow(/positive whole number/);
    expect(() => parseSpec("262:0")).toThrow(/positive whole number/);
    expect(() => parseSpec("262:-1")).toThrow(/positive whole number/);
    expect(() => parseSpec("262:1.5")).toThrow(/positive whole number/);
  });

  test("rejects extra colons and a missing SKU", () => {
    expect(() => parseSpec("262:2:3")).toThrow(/Malformed/);
    expect(() => parseSpec(":2")).toThrow(/Missing SKU/);
  });
});

describe("quantityFlag", () => {
  test("absent means one", () => {
    expect(quantityFlag(undefined)).toBe(1);
  });

  test("parses a positive whole number", () => {
    expect(quantityFlag("3")).toBe(3);
  });

  test("rejects an unparseable quantity instead of silently adding one", () => {
    // This governs a MUTATION (`d1 cart add --qty abc`). The read-only
    // `parseSpec` already rejected this class; the write path did not, and
    // silently put 1 unit in a real basket while reporting success.
    expect(() => quantityFlag("abc")).toThrow(/positive whole number/);
    expect(() => quantityFlag("2 892")).toThrow(/positive whole number/);
    expect(() => quantityFlag("0")).toThrow(/positive whole number/);
    expect(() => quantityFlag("-3")).toThrow(/positive whole number/);
    expect(() => quantityFlag("1.5")).toThrow(/positive whole number/);
  });

  test("a valueless --qty is rejected, not read as one", () => {
    // `--qty` with nothing after it parses to boolean true.
    expect(() => quantityFlag(true)).toThrow(/positive whole number/);
    expect(() => quantityFlag("")).toThrow(/positive whole number/);
  });

  test("every rejection is a UsageError, so the CLI exits 2 not 1", () => {
    // An agent must be able to tell "you called this wrong" (never retry) from
    // "D1 is down" (retry). Both were exit 1 before.
    expect(() => quantityFlag("abc")).toThrow(UsageError);
  });
});

describe("usage errors are distinguishable from upstream failures", () => {
  test("UsageError is a D1Error but identifiable", () => {
    const u = new UsageError("Usage: d1 quote <sku>");
    expect(u).toBeInstanceOf(UsageError);
    expect(u).toBeInstanceOf(D1Error);
    expect(u.name).toBe("UsageError");
  });

  test("a plain D1Error is NOT a UsageError", () => {
    // The exit-code split depends on this asymmetry; if D1Error were also a
    // UsageError, every upstream outage would exit 2 and never be retried.
    const e = new D1Error("D1 is rate-limiting this client.");
    expect(e).not.toBeInstanceOf(UsageError);
  });

  test("parseSpec and quantityFlag both raise UsageError", () => {
    expect(() => parseSpec("262:abc")).toThrow(UsageError);
    expect(() => quantityFlag("abc")).toThrow(UsageError);
  });
});

describe("addOutcome — did the add actually land", () => {
  const line = (skuId: string, sellerId: string, quantity: number) => ({
    skuId,
    sellerId,
    quantity,
  });

  test("success when the line reached the requested quantity", () => {
    expect(addOutcome([line("262", "s1", 3)], "262", "s1", 3)).toEqual({ ok: true, got: 3 });
  });

  test("a repeat is not a failure (VTEX SETS the line, it does not add)", () => {
    // `add --qty 2` twice leaves the cart at 2. A delta-based check would call
    // the second one a failure.
    expect(addOutcome([line("262", "s1", 2)], "262", "s1", 2).ok).toBe(true);
  });

  test("short fill is a failure and reports what was actually set", () => {
    expect(addOutcome([line("262", "s1", 1)], "262", "s1", 5)).toEqual({ ok: false, got: 1 });
  });

  test("an absent line is a failure, not a vacuous success", () => {
    expect(addOutcome([], "262", "s1", 1)).toEqual({ ok: false, got: 0 });
  });

  test("the ORIGINAL round-1 bug: present-but-unchanged must not read as success", () => {
    // The old predicate was `items.some(i => i.skuId === sku)` — true here,
    // so asking for 5 more on an existing line of 1 reported success.
    expect(addOutcome([line("262", "s1", 1)], "262", "s1", 5).ok).toBe(false);
  });

  test("a same-SKU line under a DIFFERENT seller must not satisfy the request", () => {
    // Reachable after a region change or an explicit --seller: sellerA holds
    // 10, sellerB was rejected outright. A SKU-only lookup answers "10 >= 3,
    // success" — the exact false success this check exists to prevent.
    const cart = [line("262", "sellerA", 10), line("262", "sellerB", 0)];
    expect(addOutcome(cart, "262", "sellerB", 3)).toEqual({ ok: false, got: 0 });
    expect(addOutcome(cart, "262", "sellerA", 3).ok).toBe(true);
  });
});
