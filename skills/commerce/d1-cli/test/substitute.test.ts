import { describe, expect, test } from "bun:test";
import {
  assertSkuId,
  bestOffer,
  categoryFacetPath,
  deepestCategory,
  normalizeProduct,
  priced,
  productBySku,
} from "../src/catalog.ts";
import { countFlag, limitFlag, substituteExit, substituteOptions } from "../src/cli.ts";
import { D1Client } from "../src/client.ts";
import {
  MAX_CATEGORY_DEPTH,
  describeDeltas,
  dice,
  findSubstitutes,
  formatSize,
  proximity,
  rankSubstitutes,
  scoreCandidate,
  tokens,
} from "../src/substitute.ts";
import { D1Error, type Offer, type Product, UsageError } from "../src/types.ts";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function offer(price: number, available = true): Offer {
  return {
    sellerId: "1",
    sellerName: "Tiendas D1",
    price,
    listPrice: price,
    available,
    availableQuantity: available ? 100 : 0,
  };
}

function product(p: Partial<Product> & { skuId: string; name: string }): Product {
  return {
    productId: p.productId ?? p.skuId,
    brand: "LATTI",
    linkText: "",
    categories: ["Lacteos y huevos/Leches/Entera"],
    offers: [offer(350_000)],
    warnings: [],
    ...p,
  };
}

/** A litre-measured product with a derived unit price, like the catalogue emits. */
function litres(
  skuId: string,
  name: string,
  price: number,
  amount: number,
  rest: Partial<Product> = {},
) {
  return product({
    skuId,
    name,
    offers: [offer(price)],
    size: { measure: "L", amount },
    unitPrice: Math.round(price / amount),
    ...rest,
  });
}

/** Did `fn` throw a UsageError? Returned as a boolean so a failure names the input. */
function throws(fn: () => unknown): boolean {
  try {
    fn();
    return false;
  } catch (e) {
    return e instanceof UsageError;
  }
}

// ---------------------------------------------------------------------------
// Tokenization and similarity
// ---------------------------------------------------------------------------

describe("tokens", () => {
  test("drops the pack size, which `size` already holds correctly", () => {
    // As text, "900" and "1000" are simply two different tokens no matter how
    // close the products are — and every carton in the aisle carries one.
    expect(tokens("LECHE ENTERA TETRAPAK UHT LATTI 900 ML")).toEqual([
      "leche",
      "entera",
      "tetrapak",
      "uht",
      "latti",
    ]);
  });

  test("splits a glued alphanumeric to RECOVER the word inside it", () => {
    // Re-fixtured. The original used `X200ML`, which proves nothing: `x` and
    // `ml` are both noise words, so the whole token dies with or without the
    // split and deleting the split entirely kept the suite green.
    //
    // These are the inputs that distinguish the two: without the letter/digit
    // split, `3litros` / `6pack` / `500gramos` each survive slugify as one
    // token containing a digit, and the digit filter then discards the word
    // along with the number.
    expect(tokens("ACEITE GIRASOL 3LITROS")).toEqual(["aceite", "girasol", "litros"]);
    expect(tokens("CERVEZA CLUB 6PACK")).toEqual(["cerveza", "club", "pack"]);
    expect(tokens("HARINA 500GRAMOS PAN")).toEqual(["harina", "gramos", "pan"]);
  });

  test("the pack quantity itself never becomes a token", () => {
    expect(tokens("LECHE CHOCOLATE LATTI BOLSA X200ML")).toEqual([
      "leche",
      "chocolate",
      "latti",
      "bolsa",
    ]);
    expect(tokens("LECHE TPAK LATTI 3 UN 600 ML")).toEqual(["leche", "tpak", "latti"]);
  });

  test("strips accents so the same word matches itself", () => {
    expect(tokens("ARROZ ECONÓMICO")).toEqual(tokens("ARROZ ECONOMICO"));
  });

  test("a name that is nothing but size and noise yields no tokens", () => {
    expect(tokens("900 ML")).toEqual([]);
  });
});

describe("dice", () => {
  test("1 for identical sets, 0 for disjoint ones", () => {
    expect(dice(["a", "b"], ["a", "b"])).toBe(1);
    expect(dice(["a"], ["b"])).toBe(0);
  });

  test("an empty side is 0, not a division by zero", () => {
    expect(dice([], ["a"])).toBe(0);
    expect(dice([], [])).toBe(0);
  });

  test("half-overlap scores between the two", () => {
    expect(dice(["a", "b"], ["b", "c"])).toBeCloseTo(0.5, 5);
  });
});

describe("proximity", () => {
  test("1 at equal, and symmetric on either side of it", () => {
    expect(proximity(100, 100)).toBe(1);
    // Half the price per kilo is exactly as DIFFERENT as double it. Which of
    // those the shopper wants is their call; the delta says which way it went.
    expect(proximity(100, 200)).toBe(proximity(200, 100));
  });

  test("falls as the two diverge", () => {
    expect(proximity(100, 200)).toBeCloseTo(0.5, 5);
    expect(proximity(100, 1000)).toBeCloseTo(0.1, 5);
    expect(proximity(100, 200)).toBeGreaterThan(proximity(100, 1000));
  });

  test("a non-positive quantity is 0, never NaN or Infinity", () => {
    expect(proximity(0, 100)).toBe(0);
    expect(proximity(100, 0)).toBe(0);
    expect(proximity(-5, 100)).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Scoring
// ---------------------------------------------------------------------------

describe("scoreCandidate", () => {
  const source = litres("262", "LECHE ENTERA TETRAPAK LATTI 900 ML", 350_000, 0.9);

  test("a perfect match on every axis scores 1", () => {
    const twin = litres("999", "LECHE ENTERA TETRAPAK LATTI 900 ML", 350_000, 0.9);
    expect(scoreCandidate(source, twin).score).toBeCloseTo(1, 5);
  });

  test("a missing pack size REDISTRIBUTES weight instead of scoring zero", () => {
    // ~5% of D1's catalogue publishes no size. Charging those products for the
    // absence buries them for a fact about D1's data, not about the product.
    //
    // Mutation proof: with the same name and no size, the score must equal the
    // name component alone (1.0). If the weight were kept and the component
    // scored 0, this would be 0.5 — the name weight and nothing else.
    const sizeless = product({
      skuId: "998",
      name: "LECHE ENTERA TETRAPAK LATTI 900 ML",
      offers: [offer(350_000)],
    });
    expect(scoreCandidate(source, sizeless).score).toBeCloseTo(1, 5);
  });

  test("...but a sizeless candidate still lands BELOW anything comparable", () => {
    // The redistribution above is why the tier has to be separate: a sizeless
    // product can score 1.0 on name alone, which would otherwise let it head a
    // list of candidates whose value cannot be checked against the source's.
    const sizeless = product({
      skuId: "998",
      name: "LECHE ENTERA TETRAPAK LATTI 900 ML",
      offers: [offer(350_000)],
    });
    expect(scoreCandidate(source, sizeless).tier).toBe(1);
    const comparable = litres("997", "LECHE ENTERA BOLSA LATTI 900 ML", 320_000, 0.9);
    expect(scoreCandidate(source, comparable).tier).toBe(0);
  });

  test("a different measure is a tier, never a score penalty", () => {
    // The regression this prevents is real and already happened once in
    // `--sort per-unit`: an $8,900 bottle ranked in among the $/L figures.
    const byUnit = product({
      skuId: "996",
      name: "LECHE ENTERA TETRAPAK LATTI 900 ML",
      offers: [offer(350_000)],
      size: { measure: "unit", amount: 1 },
      unitPrice: 350_000,
    });
    const { score, tier } = scoreCandidate(source, byUnit);
    expect(tier).toBe(1);
    // The score is untouched — it is the ORDERING that demotes it.
    expect(score).toBeCloseTo(1, 5);
  });

  test("when the SOURCE has no size, nothing is demoted", () => {
    // There is no comparison to be excluded from, so a tier would only be
    // arbitrary.
    const noSize = product({ skuId: "500", name: "PAN ARTESANAL INTEGRAL" });
    const cand = litres("501", "PAN ARTESANAL BLANCO", 300_000, 0.5);
    expect(scoreCandidate(noSize, cand).tier).toBe(0);
  });

  test("a closer unit price outranks a further one at equal names", () => {
    const near = litres("a1", "LECHE ENTERA TETRAPAK LATTI 900 ML", 360_000, 0.9);
    const far = litres("a2", "LECHE ENTERA TETRAPAK LATTI 900 ML", 1_200_000, 0.9);
    expect(scoreCandidate(source, near).score).toBeGreaterThan(scoreCandidate(source, far).score);
  });

  test("a closer PACK SIZE outranks a further one at equal names and equal $/L", () => {
    // The size component was pinned only as "must not be zero" — three separate
    // mutations (weight 0, all weights equal, proximity forced to 1) left the
    // suite green because nothing asked it to DISCRIMINATE. Both candidates
    // here match the name exactly and cost the same per litre, so pack size is
    // the only axis left that can separate them.
    const near = litres("b1", "LECHE ENTERA TETRAPAK LATTI 900 ML", 400_000, 1);
    const far = litres("b2", "LECHE ENTERA TETRAPAK LATTI 900 ML", 2_000_000, 5);
    expect(near.unitPrice).toBe(far.unitPrice);
    expect(scoreCandidate(source, near).score).toBeGreaterThan(scoreCandidate(source, far).score);
    expect(rankSubstitutes(source, [far, near]).map((c) => c.product.skuId)).toEqual(["b1", "b2"]);
  });

  test("nothing in common scores 0 without throwing", () => {
    const alien = product({ skuId: "x", name: "900 ML" });
    expect(scoreCandidate(source, alien).score).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Deltas — the actual product of the command
// ---------------------------------------------------------------------------

describe("describeDeltas", () => {
  const source = litres("262", "LECHE ENTERA LATTI 900 ML", 350_000, 0.9, {
    brand: "LATTI",
    warnings: ["Exceso en sodio"],
  });

  test("names the brand change", () => {
    const cand = litres("892", "LECHE ENTERA ALQUERIA 900 ML", 350_000, 0.9, {
      brand: "ALQUERIA",
    });
    const d = describeDeltas(source, cand).find((x) => x.kind === "brand");
    expect(d?.text).toBe("LATTI → ALQUERIA");
  });

  test("gives the unit-price delta a direction and a percentage", () => {
    // $ 3.889/L → $ 3.556/L is what the shopper acts on; the score is not.
    const cheaper = litres("892", "LECHE ENTERA LATTI 900 ML", 320_000, 0.9, {
      warnings: ["Exceso en sodio"],
    });
    const d = describeDeltas(source, cheaper).find((x) => x.kind === "unit-price");
    expect(d?.percent).toBe(-9);
    expect(d?.text).toContain("(-9%)");
  });

  test("marks a rise with a leading +, so the sign is never ambiguous", () => {
    const dearer = litres("893", "LECHE ENTERA LATTI 900 ML", 700_000, 0.9);
    const d = describeDeltas(source, dearer).find((x) => x.kind === "price");
    expect(d?.percent).toBe(100);
    expect(d?.text).toContain("(+100%)");
  });

  test("reports a size change in normalized units", () => {
    const bigger = litres("894", "LECHE ENTERA LATTI 1000 ML", 380_000, 1);
    const d = describeDeltas(source, bigger).find((x) => x.kind === "size");
    expect(d?.from).toBe("0.9 L");
    expect(d?.to).toBe("1 L");
  });

  test("a warning GAINED is reported — the change most likely to matter", () => {
    const sweet = litres("895", "LECHE ENTERA LATTI 900 ML", 320_000, 0.9, {
      warnings: ["Exceso en sodio", "Exceso en Azúcares"],
    });
    const deltas = describeDeltas(source, sweet);
    expect(deltas.find((d) => d.kind === "warning-added")?.to).toBe("Exceso en Azúcares");
    // And nothing was lost, so no removal is claimed.
    expect(deltas.find((d) => d.kind === "warning-removed")).toBeUndefined();
  });

  test("a warning DROPPED is reported too", () => {
    const clean = litres("896", "LECHE ENTERA LATTI 900 ML", 350_000, 0.9, { warnings: [] });
    expect(describeDeltas(source, clean).find((d) => d.kind === "warning-removed")?.from).toBe(
      "Exceso en sodio",
    );
  });

  test("an incomparable measure says so instead of printing a $/L delta", () => {
    // Printing "$ 3.889/L → $ 2.400/unit  (-38%)" would be a fabricated saving.
    const byUnit = product({
      skuId: "897",
      name: "LECHE ENTERA LATTI",
      offers: [offer(240_000)],
      size: { measure: "unit", amount: 1 },
      unitPrice: 240_000,
    });
    const deltas = describeDeltas(source, byUnit);
    expect(deltas.find((d) => d.kind === "measure")?.text).toContain("cannot be compared per unit");
    expect(deltas.find((d) => d.kind === "unit-price")).toBeUndefined();
  });

  test("a candidate with no size is said to be uncomparable, not given a fake one", () => {
    const sizeless = product({
      skuId: "898",
      name: "LECHE ENTERA LATTI",
      offers: [offer(300_000)],
    });
    const d = describeDeltas(source, sizeless).find((x) => x.kind === "size");
    expect(d?.text).toContain("publishes no pack size");
    expect(d?.to).toBeUndefined();
  });

  test("an identical product produces no deltas at all", () => {
    const twin = litres("999", "LECHE ENTERA LATTI 900 ML", 350_000, 0.9, {
      warnings: ["Exceso en sodio"],
    });
    expect(describeDeltas(source, twin)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// A price of zero is NOT a price
// ---------------------------------------------------------------------------

describe("a zero price is an absent offer, never free", () => {
  test("priced() rejects zero and negatives, accepts a real price", () => {
    expect(priced(offer(0))).toBe(false);
    expect(priced(offer(-1))).toBe(false);
    expect(priced(undefined)).toBe(false);
    expect(priced(offer(350_000))).toBe(true);
  });

  test("the pack price and the unit price come from the SAME offer", () => {
    // Two predicates for "which offer represents this product" diverged exactly
    // where it mattered — `normalizeProduct` fell back to offers[0] while
    // `bestOffer` fell back to the cheapest — so a product with nothing in
    // stock (the case `substitute` exists for) printed a pack price from one
    // seller beside a $/L derived from another. The first seller here is NOT
    // the cheapest, which is what makes the two answers distinguishable.
    const [p] = normalizeProduct({
      productId: "700",
      productName: "ACEITE GIRASOL 900 ML",
      properties: [
        { name: "Unidad De Medida", values: ["Ml"] },
        { name: "Valor de Medida", values: ["900"] },
      ],
      items: [
        {
          itemId: "700",
          sellers: [
            { sellerId: "1", commertialOffer: { Price: 4000, AvailableQuantity: 0 } },
            { sellerId: "store-42", commertialOffer: { Price: 3500, AvailableQuantity: 0 } },
          ],
        },
      ],
    });
    const shown = bestOffer(p);
    expect(shown?.price).toBe(350_000);
    expect(p.unitPrice).toBe(Math.round(350_000 / 0.9));
    // The two numbers on that row must be consistent with one another.
    expect(p.unitPrice).toBe(Math.round((shown as { price: number }).price / 0.9));
  });

  test("a real sub-gram size is not rounded away to zero", () => {
    // `toFixed(3)` rendered a 400 mg sachet as a confident `0 kg`. Showing a
    // real quantity as zero is the same lie as showing an absent price as $ 0.
    expect(formatSize({ measure: "kg", amount: 0.0004 })).toBe("0.0004 kg");
    expect(formatSize({ measure: "kg", amount: 0.5 })).toBe("0.5 kg");
    expect(formatSize({ measure: "L", amount: 1 })).toBe("1 L");
  });

  test("no unit price is derived from a non-price", () => {
    // Root fix. Observed live: SKU 1687 is out of stock in Bogotá and VTEX
    // reports Price 0, which rendered as `$ 0/kg` — a per-kilo figure for a
    // product that has no price at all.
    const [p] = normalizeProduct({
      productId: "1687",
      productName: "SALCHICHA PARRILLA MINI VIANDE 200 G",
      properties: [
        { name: "Unidad De Medida", values: ["Gr"] },
        { name: "Valor de Medida", values: ["200"] },
      ],
      items: [
        {
          itemId: "1687",
          nameComplete: "SALCHICHA PARRILLA MINI VIANDE 200 G",
          sellers: [
            { sellerId: "1", commertialOffer: { Price: 0, ListPrice: 0, AvailableQuantity: 0 } },
          ],
        },
      ],
    });
    // The size is still known — that part of the data is real.
    expect(p.size).toEqual({ measure: "kg", amount: 0.2 });
    expect(p.unitPrice).toBeUndefined();
  });

  test("no price delta is claimed when one side has no price", () => {
    // `$ 0 → $ 9.300` reads as a rise from nothing, and `$ 0/kg → $ 40.435/kg`
    // as a per-kilo comparison against free. Both were printed live before this
    // guard. Saying nothing is the honest output — there is no change to report.
    const unpriced = product({
      skuId: "1687",
      name: "SALCHICHA PARRILLA MINI VIANDE",
      offers: [offer(0, false)],
      size: { measure: "kg", amount: 0.2 },
    });
    const real = product({
      skuId: "117",
      name: "SALCHICHA PARRILLA VIANDE",
      offers: [offer(930_000)],
      size: { measure: "kg", amount: 0.23 },
      unitPrice: 4_043_478,
    });
    const kinds = describeDeltas(unpriced, real).map((d) => d.kind);
    expect(kinds).not.toContain("price");
    expect(kinds).not.toContain("unit-price");
    // The comparisons that ARE sound still happen.
    expect(kinds).toContain("size");
  });
});

// ---------------------------------------------------------------------------
// Ranking
// ---------------------------------------------------------------------------

describe("rankSubstitutes", () => {
  const source = litres("262", "LECHE ENTERA TETRAPAK LATTI 900 ML", 350_000, 0.9);

  test("never proposes the product it was asked to replace", () => {
    const out = rankSubstitutes(source, [
      source,
      litres("892", "LECHE ENTERA BOLSA", 320_000, 0.9),
    ]);
    expect(out.map((c) => c.product.skuId)).not.toContain("262");
    expect(out).toHaveLength(1);
  });

  test("drops out-of-stock candidates — a replacement that is not there replaces nothing", () => {
    const gone = product({
      skuId: "893",
      name: "LECHE ENTERA TETRAPAK LATTI 900 ML",
      offers: [offer(300_000, false)],
      size: { measure: "L", amount: 0.9 },
      unitPrice: 333_333,
    });
    const here = litres("894", "LECHE ENTERA BOLSA LATTI 900 ML", 340_000, 0.9);
    expect(rankSubstitutes(source, [gone, here]).map((c) => c.product.skuId)).toEqual(["894"]);
  });

  test("a same-measure candidate outranks a better-named one in another measure", () => {
    // The `--sort per-unit` regression, in substitution form: the unit-measured
    // product matches the source's name EXACTLY and still must not lead, since
    // its price cannot be checked against the source's at all.
    const perfectNameWrongMeasure = product({
      skuId: "900",
      name: "LECHE ENTERA TETRAPAK LATTI 900 ML",
      offers: [offer(350_000)],
      size: { measure: "unit", amount: 1 },
      unitPrice: 350_000,
    });
    const weakerNameSameMeasure = litres("901", "LECHE DESLACTOSADA BOLSA", 340_000, 0.9);
    const out = rankSubstitutes(source, [perfectNameWrongMeasure, weakerNameSameMeasure]);
    expect(out.map((c) => c.product.skuId)).toEqual(["901", "900"]);
    expect(out[0].tier).toBe(0);
    expect(out[1].tier).toBe(1);
  });

  test("a repeated SKU appears once", () => {
    const dup = litres("892", "LECHE ENTERA BOLSA LATTI 900 ML", 320_000, 0.9);
    expect(rankSubstitutes(source, [dup, { ...dup }])).toHaveLength(1);
  });

  test("ties break deterministically, so two runs agree", () => {
    // Without the skuId tie-break these swap on upstream ordering alone, and a
    // caller diffing two invocations sees a change that did not happen.
    const a = litres("b2", "LECHE ENTERA TETRAPAK LATTI 900 ML", 350_000, 0.9);
    const b = litres("a1", "LECHE ENTERA TETRAPAK LATTI 900 ML", 350_000, 0.9);
    expect(rankSubstitutes(source, [a, b]).map((c) => c.product.skuId)).toEqual(["a1", "b2"]);
    expect(rankSubstitutes(source, [b, a]).map((c) => c.product.skuId)).toEqual(["a1", "b2"]);
  });

  test("honours the limit", () => {
    const pool = Array.from({ length: 12 }, (_, i) =>
      litres(`s${i}`, `LECHE ENTERA ${i}`, 300_000 + i, 0.9),
    );
    expect(rankSubstitutes(source, pool, 3)).toHaveLength(3);
    // Default is 8, not "all" — an unbounded list is not a proposal.
    expect(rankSubstitutes(source, pool)).toHaveLength(8);
  });

  test("an entirely out-of-stock pool yields nothing rather than a bad suggestion", () => {
    const gone = product({
      skuId: "902",
      name: "LECHE ENTERA",
      offers: [offer(300_000, false)],
    });
    expect(rankSubstitutes(source, [gone])).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// SKU lookup — the id-space trap
// ---------------------------------------------------------------------------

/** Routes by URL so one stub can serve the lookup and the category sweep. */
function router(routes: Array<[RegExp, unknown]>) {
  const calls: string[] = [];
  const impl = (async (url: string) => {
    const u = String(url);
    calls.push(u);
    for (const [re, body] of routes) {
      if (re.test(u)) {
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
    }
    return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
  }) as unknown as typeof fetch;
  return { impl, calls };
}

/** The catalog_system shape: properties are TOP-LEVEL, not under `properties[]`. */
function catalogWire(productId: string, itemId: string, name: string, price = 3500) {
  return {
    productId,
    productName: name,
    brand: "LATTI",
    linkText: "x",
    categories: [
      "/Lacteos y huevos/Leches/Entera/",
      "/Lacteos y huevos/Leches/",
      "/Lacteos y huevos/",
    ],
    "Unidad De Medida": ["Ml"],
    "Valor de Medida": ["900"],
    "Exceso en sodio": ["Si"],
    "Exceso en Azúcares": ["No"],
    items: [
      {
        itemId,
        nameComplete: name,
        sellers: [
          {
            sellerId: "1",
            sellerName: "Tiendas D1",
            commertialOffer: { Price: price, ListPrice: price, AvailableQuantity: 100 },
          },
        ],
      },
    ],
  };
}

describe("productBySku", () => {
  test("matches the ITEM id, not the first item of the first product", () => {
    // The trap, observed live: SKU 1686 belongs to product 1687, and asking for
    // skuId 1687 returns product 1688 — `SALCHICHA PARRILLA MINI VIANDE`, where
    // you asked about potato crisps. One result, HTTP 200, wrong groceries.
    //
    // Here the response carries product 1688 whose item is 1687. Taking
    // `items[0]` blindly would be right by luck; the assertion that matters is
    // the NEGATIVE one below.
    const { impl } = router([[/catalog_system/, [catalogWire("1688", "1687", "SALCHICHA")]]]);
    const client = new D1Client({ fetchImpl: impl });
    return productBySku(client, "1687").then((p) => {
      expect(p?.skuId).toBe("1687");
      expect(p?.productId).toBe("1688");
    });
  });

  test("a product whose items do NOT carry the SKU is refused, not returned", async () => {
    // The load-bearing direction. If `items[0]` were taken on faith, this
    // returns a confidently wrong grocery item instead of "not found".
    const { impl } = router([[/catalog_system/, [catalogWire("1687", "1686", "PAPAS EN CASCO")]]]);
    const client = new D1Client({ fetchImpl: impl });
    expect(await productBySku(client, "1687")).toBeUndefined();
  });

  test("reads properties from the TOP LEVEL, where catalog_system puts them", async () => {
    // Proves `asSearchShape`: intelligent-search nests these under
    // `properties[]`, and a normalizer that only knew that shape would report
    // "D1 publishes no pack size" for every product reached this way.
    const { impl } = router([
      [/catalog_system/, [catalogWire("262", "262", "LECHE ENTERA 900 ML")]],
    ]);
    const p = await productBySku(new D1Client({ fetchImpl: impl }), "262");
    expect(p?.size).toEqual({ measure: "L", amount: 0.9 });
    expect(p?.unitPrice).toBe(Math.round(350_000 / 0.9));
    expect(p?.warnings).toEqual(["Exceso en sodio"]);
  });

  test("an empty catalogue answer is undefined, not a throw", async () => {
    const { impl } = router([[/catalog_system/, []]]);
    expect(await productBySku(new D1Client({ fetchImpl: impl }), "404404")).toBeUndefined();
  });

  test("the SKU reaches the wire as a bare fq filter", async () => {
    const { impl, calls } = router([[/catalog_system/, []]]);
    await productBySku(new D1Client({ fetchImpl: impl }), "262", { salesChannel: "1" });
    const u = new URL(calls[0]);
    expect(u.pathname).toBe("/api/catalog_system/pub/products/search");
    expect(u.searchParams.get("fq")).toBe("skuId:262");
    expect(u.searchParams.get("sc")).toBe("1");
  });
});

describe("assertSkuId", () => {
  test("rejects an fq expression wearing a SKU's clothes", () => {
    // `fq` is a query language: this does not narrow the catalogue, it rewrites
    // the question — and still answers 200 with plausible products.
    expect(() => assertSkuId("262 OR productId:1")).toThrow(UsageError);
    expect(() => assertSkuId("262:1")).toThrow(UsageError);
    expect(() => assertSkuId("")).toThrow(UsageError);
    expect(() => assertSkuId("-1")).toThrow(UsageError);
    expect(() => assertSkuId("26 2")).toThrow(UsageError);
  });

  test("accepts a real SKU", () => {
    expect(() => assertSkuId("262")).not.toThrow();
    expect(() => assertSkuId("1686")).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Category paths
// ---------------------------------------------------------------------------

describe("the substitute command's policy, separated so it can be pinned", () => {
  // A network-free suite cannot drive this command's success path — the origin
  // is pinned to d1.com.co by construction, so there is no stub to point a
  // subprocess at. A mutation sweep proved the cost: constant exit code,
  // `--limit` dropped, region never forwarded, all with the suite green.

  test("exit 3 means 'I looked and there is none', never 0 and never 1", () => {
    expect(substituteExit(1)).toBe(0);
    expect(substituteExit(8)).toBe(0);
    // Not 1: that is "D1 refused or was unreachable, a retry may help", and an
    // agent retrying on 1 would loop forever on a legitimately empty category.
    expect(substituteExit(0)).toBe(3);
  });

  test("the region reaches the options, or every shopper silently gets national stock", () => {
    const o = substituteOptions({}, { id: "v2.REGION" }, "1");
    expect(o.regionId).toBe("v2.REGION");
    expect(o.salesChannel).toBe("1");
    expect(substituteOptions({}, undefined, "1").regionId).toBeUndefined();
  });

  test("--limit and --count reach the options", () => {
    const o = substituteOptions({ limit: "3", count: "20" }, undefined, "1");
    expect(o.limit).toBe(3);
    expect(o.count).toBe(20);
    // Absent means "let findSubstitutes default", not 0.
    expect(substituteOptions({}, undefined, "1").limit).toBeUndefined();
    expect(substituteOptions({}, undefined, "1").count).toBeUndefined();
  });

  test("the options builder validates on its own, not only via the command body", () => {
    // `case "substitute"` also calls `limitFlag`/`countFlag` up front, to keep a
    // usage error off the network. That standalone call MASKS this one: swapping
    // `countFlag` back to the unvalidated `num()` in here changed nothing
    // observable, because the earlier call had already thrown. Two guards, and
    // only one of them was pinned — so the inner one could rot silently.
    expect(throws(() => substituteOptions({ count: "0" }, undefined, "1"))).toBe(true);
    expect(throws(() => substituteOptions({ count: "abc" }, undefined, "1"))).toBe(true);
    expect(throws(() => substituteOptions({ limit: "-3" }, undefined, "1"))).toBe(true);
  });

  test("--limit and --count are validated, not clamped", () => {
    // `--limit 0` used to clamp to 1 and exit 0 — answering a question nobody
    // asked. `--qty` has applied the right rule (reject, exit 2) all along.
    //
    // `--count` had the same shape one flag over, and worse: `num()` let 0 and
    // -5 through as real numbers and `search` clamped them to 1, so asking for
    // zero products quietly asked for one, over a live request.
    for (const bad of ["0", "-3", "abc", "2.5", ""]) {
      expect({ flag: "limit", bad, throws: throws(() => limitFlag(bad)) }).toEqual({
        flag: "limit",
        bad,
        throws: true,
      });
      expect({ flag: "count", bad, throws: throws(() => countFlag(bad)) }).toEqual({
        flag: "count",
        bad,
        throws: true,
      });
    }
    expect(limitFlag("5")).toBe(5);
    expect(countFlag("50")).toBe(50);
    expect(limitFlag(undefined)).toBeUndefined();
    expect(countFlag(undefined)).toBeUndefined();
  });

  test("the rejection names the flag the caller actually typed", () => {
    // One shared implementation, two flags: a message hard-coded to "--limit"
    // would send someone hunting the wrong argument.
    expect(() => countFlag("0")).toThrow(/--count/);
    expect(() => limitFlag("0")).toThrow(/--limit/);
  });
});

describe("category paths", () => {
  test("the deepest declared path is the one that describes the product", () => {
    expect(
      deepestCategory([
        "Lacteos y huevos",
        "Lacteos y huevos/Leches/Entera",
        "Lacteos y huevos/Leches",
      ]),
    ).toBe("Lacteos y huevos/Leches/Entera");
    expect(deepestCategory([])).toBeUndefined();
  });

  test("two equally-deep paths resolve the same way whatever order they arrive in", () => {
    // D1 can publish a merchandising tree and an aisle tree at the same depth,
    // and nothing documents which comes first. First-wins would silently change
    // which category got swept between two identical runs.
    const a = "Aseo/Hogar/Pisos";
    const b = "Limpieza/Casa/Pisos";
    expect(deepestCategory([a, b])).toBe(deepestCategory([b, a]));
  });

  test("names become the depth-keyed slug path search actually takes", () => {
    // Verified live: this exact path returns 8 products.
    expect(categoryFacetPath("Lacteos y huevos/Leches/Entera")).toBe(
      "category-1/lacteos-y-huevos/category-2/leches/category-3/entera",
    );
  });

  test("a depth truncates from the left, keeping the numbering contiguous", () => {
    expect(categoryFacetPath("Lacteos y huevos/Leches/Entera", 2)).toBe(
      "category-1/lacteos-y-huevos/category-2/leches",
    );
    expect(categoryFacetPath("Lacteos y huevos/Leches/Entera", 1)).toBe(
      "category-1/lacteos-y-huevos",
    );
  });

  test("a name with no slug STOPS the path instead of emptying a segment", () => {
    // `category-1/a/category-2//category-3/c` collapses on the wire and would
    // silently search a broader category than the caller asked for. A shorter
    // honest path is the safe way for this to be wrong.
    expect(categoryFacetPath("Despensa/!!!/Arroz")).toBe("category-1/despensa");
  });
});

// ---------------------------------------------------------------------------
// End to end, without a network
// ---------------------------------------------------------------------------

/** The intelligent-search shape: properties under `properties[]`. */
function searchWire(skuId: string, name: string, price: number, qty: number, valor = "900") {
  return {
    productId: skuId,
    productName: name,
    brand: "LATTI",
    linkText: "x",
    categories: ["/Lacteos y huevos/Leches/Entera/"],
    properties: [
      { name: "Unidad De Medida", values: ["Ml"] },
      { name: "Valor de Medida", values: [valor] },
    ],
    items: [
      {
        itemId: skuId,
        nameComplete: name,
        sellers: [
          {
            sellerId: "1",
            sellerName: "Tiendas D1",
            commertialOffer: { Price: price, ListPrice: price, AvailableQuantity: qty },
          },
        ],
      },
    ],
  };
}

describe("findSubstitutes", () => {
  test("ranks the leaf category and prices the source regionally", async () => {
    // The two prices differ ON PURPOSE. `catalog_system` takes no region, so it
    // answers nationally (COP 4,000); the regional sweep answers COP 3,500 for
    // the same SKU. Every delta must be measured against the REGIONAL figure —
    // comparing regional candidates to a national baseline reports a saving
    // that is partly just the two catalogues disagreeing.
    const { impl } = router([
      [/catalog_system/, [catalogWire("262", "262", "LECHE ENTERA TETRAPAK LATTI 900 ML", 4000)]],
      [
        /product_search/,
        {
          recordsFiltered: 3,
          products: [
            searchWire("262", "LECHE ENTERA TETRAPAK LATTI 900 ML", 3500, 0),
            searchWire("892", "LECHE ENTERA BOLSA LATTI 900 ML", 3200, 100),
            searchWire("645", "LECHE ENTERA TETRA PAK LATTI 200ML", 1100, 100, "200"),
          ],
        },
      ],
    ]);
    const r = await findSubstitutes(new D1Client({ fetchImpl: impl }), "262", {
      regionId: "v2.REGION",
    });

    expect(r.source.skuId).toBe("262");
    expect(bestOffer(r.source)?.price).toBe(350_000);
    // Regional reading wins: the sweep says quantity 0, the national lookup
    // said 100. Reporting the national one here would tell the shopper the
    // thing they cannot buy is in stock.
    expect(r.sourceAvailable).toBe(false);
    expect(r.sourcePricedNationally).toBe(false);
    expect(r.categoryPath).toBe("Lacteos y huevos/Leches/Entera");
    expect(r.searchedDepth).toBe(3);
    expect(r.candidates.map((c) => c.product.skuId)).toEqual(["892", "645"]);

    // -9% against the regional $ 3.500, not -20% against the national $ 4.000.
    const price = r.candidates[0].deltas.find((d) => d.kind === "price");
    expect(price?.from).toBe("$ 3.500");
    expect(price?.percent).toBe(-9);
  });

  test("every parameter the sweep depends on actually reaches the wire", async () => {
    // Pins the whole query, not one key. Asserting only `hideUnavailableItems`
    // left `regionId`, `count`, `page` and `trade-policy` free: deleting
    // `regionId` from the sweep — so `d1 substitute --lat/--lng` silently
    // returned NATIONAL stock for every shopper — kept the suite green, and the
    // test that claimed to prove regional pricing was matching a stub by URL
    // regex without ever looking at the query string.
    const { impl, calls } = router([
      [/catalog_system/, [catalogWire("262", "262", "LECHE ENTERA LATTI 900 ML")]],
      [
        /product_search/,
        { recordsFiltered: 1, products: [searchWire("892", "LECHE BOLSA", 3200, 5)] },
      ],
    ]);
    await findSubstitutes(new D1Client({ fetchImpl: impl }), "262", {
      regionId: "v2.REGION",
      salesChannel: "2",
      count: 33,
    });

    const sweep = new URL(calls.find((c) => c.includes("product_search")) as string);
    expect(sweep.searchParams.get("regionId")).toBe("v2.REGION");
    expect(sweep.searchParams.get("count")).toBe("33");
    expect(sweep.searchParams.get("page")).toBe("1");
    expect(sweep.searchParams.get("trade-policy")).toBe("2");
    // The source is usually the unavailable one — that is why anyone runs this
    // — and it is needed as the price baseline. Filtering upstream would drop
    // it and silently fall back to a national price.
    expect(sweep.searchParams.get("hideUnavailableItems")).toBeNull();

    // The lookup gets the same channel, or it reads a different catalogue than
    // the one the candidates came from.
    const lookup = new URL(calls.find((c) => c.includes("catalog_system")) as string);
    expect(lookup.searchParams.get("sc")).toBe("2");
  });

  test("the sweep defaults to a full page, not a sample", async () => {
    // `count ?? 50` is what makes the category sweep near-complete; dropping it
    // to 12 (search's own default) silently narrows every comparison.
    const { impl, calls } = router([
      [/catalog_system/, [catalogWire("262", "262", "LECHE ENTERA LATTI 900 ML")]],
      [
        /product_search/,
        { recordsFiltered: 1, products: [searchWire("892", "LECHE BOLSA", 3200, 5)] },
      ],
    ]);
    await findSubstitutes(new D1Client({ fetchImpl: impl }), "262");
    const sweep = new URL(calls.find((c) => c.includes("product_search")) as string);
    expect(sweep.searchParams.get("count")).toBe("50");
  });

  test("--limit is honoured, and rankedCount still reports the true total", async () => {
    const products = Array.from({ length: 6 }, (_, i) =>
      searchWire(`90${i}`, `LECHE ENTERA VARIANTE ${i}`, 3200 + i, 5),
    );
    const { impl } = router([
      [/catalog_system/, [catalogWire("262", "262", "LECHE ENTERA LATTI 900 ML")]],
      [/product_search/, { recordsFiltered: 6, products }],
    ]);
    const r = await findSubstitutes(new D1Client({ fetchImpl: impl }), "262", { limit: 2 });
    expect(r.candidates).toHaveLength(2);
    // "2 of 6" and "2 of 2" are different answers to the shopper.
    expect(r.rankedCount).toBe(6);
  });

  test("widens up the category tree when the leaf has nothing in stock, and SAYS SO", async () => {
    let hit = 0;
    const impl = (async (url: string) => {
      const u = String(url);
      let body: unknown = [];
      if (/catalog_system/.test(u)) {
        body = [catalogWire("262", "262", "LECHE ENTERA LATTI 900 ML")];
      } else if (/product_search/.test(u)) {
        hit++;
        body =
          hit < 3
            ? // Levels 3 and 2: the source, out of stock, and nothing else.
              {
                recordsFiltered: 1,
                products: [searchWire("262", "LECHE ENTERA LATTI 900 ML", 3500, 0)],
              }
            : {
                recordsFiltered: 2,
                products: [searchWire("892", "LECHE BOLSA LATTI 900 ML", 3200, 9)],
              };
      }
      return new Response(JSON.stringify(body), { status: 200 });
    }) as unknown as typeof fetch;

    const r = await findSubstitutes(new D1Client({ fetchImpl: impl }), "262");
    expect(r.searchedDepth).toBe(1);
    expect(r.categoryDepth).toBe(3);
    expect(r.candidates.map((c) => c.product.skuId)).toEqual(["892"]);
    // The source was seen at the DEEPEST level and kept, even though it fell
    // off the widened page — otherwise a known regional price silently reverts.
    expect(r.sourcePricedNationally).toBe(false);
  });

  test("reports a partial sweep rather than implying the whole category", async () => {
    const { impl } = router([
      [/catalog_system/, [catalogWire("262", "262", "LECHE ENTERA LATTI 900 ML")]],
      [
        /product_search/,
        {
          recordsFiltered: 140,
          products: [searchWire("892", "LECHE BOLSA LATTI 900 ML", 3200, 9)],
        },
      ],
    ]);
    const r = await findSubstitutes(new D1Client({ fetchImpl: impl }), "262");
    expect(r.poolSize).toBe(1);
    expect(r.poolTotal).toBe(140);
  });

  test("falls back to the national price only when the source is genuinely absent", async () => {
    const { impl } = router([
      [/catalog_system/, [catalogWire("262", "262", "LECHE ENTERA LATTI 900 ML")]],
      [
        /product_search/,
        { recordsFiltered: 1, products: [searchWire("892", "LECHE BOLSA LATTI 900 ML", 3200, 9)] },
      ],
    ]);
    const r = await findSubstitutes(new D1Client({ fetchImpl: impl }), "262");
    expect(r.sourcePricedNationally).toBe(true);
    // Unknown, never optimistically true — this is what the renderer says out loud.
    expect(r.sourceAvailable).toBe(false);
  });

  test("an unknown SKU fails loudly instead of proposing a category at random", async () => {
    const { impl } = router([[/catalog_system/, []]]);
    // `await` is load-bearing on every one of these. `expect(promise).rejects`
    // returns a promise; dropping it makes the assertion unobservable and the
    // test passes whatever the code does.
    await expect(findSubstitutes(new D1Client({ fetchImpl: impl }), "404404")).rejects.toThrow(
      D1Error,
    );
  });

  test("a product with no category says so rather than searching everything", async () => {
    const bare = { ...catalogWire("262", "262", "LECHE"), categories: [] };
    const { impl } = router([[/catalog_system/, [bare]]]);
    await expect(findSubstitutes(new D1Client({ fetchImpl: impl }), "262")).rejects.toThrow(
      /publishes no category/,
    );
  });

  test("an unsearchable category is an ERROR, not a confident 'nothing here'", async () => {
    // `categoryFacetPath` returns "" when the FIRST name has no slug — `&/Gaseosas`,
    // `本/Arroz`. Breaking out of the loop there left an empty pool and the flat
    // claim "nothing in this category is in stock", asserted from ZERO requests.
    // Sweeping without a facet would be worse still: the whole 1,600-product
    // catalogue, which `productBySku`'s docblock says must never be fetched.
    const bare = { ...catalogWire("262", "262", "LECHE"), categories: ["/&/Gaseosas/"] };
    const { impl, calls } = router([[/catalog_system/, [bare]]]);
    await expect(findSubstitutes(new D1Client({ fetchImpl: impl }), "262")).rejects.toThrow(
      /no searchable form/,
    );
    expect(calls.filter((c) => c.includes("product_search"))).toEqual([]);
  });

  test("the walk widens when the ONLY in-stock item at a level is the source itself", async () => {
    // The `p.skuId !== skuId` half of the break condition. Without it the loop
    // stops at a level whose sole stocked product is the thing being replaced,
    // and returns no candidates while a stocked sibling sits one level up.
    let hit = 0;
    const impl = (async (url: string) => {
      const u = String(url);
      let body: unknown = [];
      if (/catalog_system/.test(u)) {
        body = [catalogWire("262", "262", "LECHE ENTERA LATTI 900 ML")];
      } else if (/product_search/.test(u)) {
        hit++;
        body =
          hit === 1
            ? // The source is here AND in stock — but it is the source.
              {
                recordsFiltered: 1,
                products: [searchWire("262", "LECHE ENTERA LATTI 900 ML", 3500, 9)],
              }
            : {
                recordsFiltered: 2,
                products: [searchWire("892", "LECHE BOLSA LATTI 900 ML", 3200, 9)],
              };
      }
      return new Response(JSON.stringify(body), { status: 200 });
    }) as unknown as typeof fetch;

    const r = await findSubstitutes(new D1Client({ fetchImpl: impl }), "262");
    expect(r.candidates.map((c) => c.product.skuId)).toEqual(["892"]);
    expect(r.searchedDepth).toBeLessThan(r.categoryDepth);
  });

  test("searchedDepth reports the depth SEARCHED, not the depth asked for", async () => {
    // `categoryFacetPath` truncates at a middle name with no slug, so
    // `Bebidas/&/Gaseosas` at depth 3 actually sweeps `category-1/bebidas` —
    // the whole department. Reporting 3 claimed the leaf was swept and
    // suppressed the "widened" notice, which was the reader's only clue.
    const bare = {
      ...catalogWire("262", "262", "GASEOSA"),
      categories: ["/Bebidas/&/Gaseosas/"],
    };
    const { impl, calls } = router([
      [/catalog_system/, [bare]],
      [
        /product_search/,
        { recordsFiltered: 400, products: [searchWire("892", "GASEOSA COLA", 3200, 9)] },
      ],
    ]);
    const r = await findSubstitutes(new D1Client({ fetchImpl: impl }), "262");
    expect(r.categoryDepth).toBe(3);
    expect(r.searchedDepth).toBe(1);
    const sweep = calls.find((c) => c.includes("product_search")) as string;
    expect(decodeURIComponent(new URL(sweep).pathname)).toContain("category-1/bebidas");
    expect(decodeURIComponent(new URL(sweep).pathname)).not.toContain("category-2");
  });

  test("the widening walk is bounded, however deep upstream claims to be", async () => {
    // The depth is upstream-controlled and drives one request per level. A
    // 40-segment category issued 41 requests from a single invocation, against
    // an API whose 429 the client already treats as a live failure.
    const deep = Array.from({ length: 40 }, (_, i) => `L${i}`).join("/");
    const bare = { ...catalogWire("262", "262", "LECHE"), categories: [`/${deep}/`] };
    const { impl, calls } = router([
      [/catalog_system/, [bare]],
      [/product_search/, { recordsFiltered: 0, products: [] }],
    ]);
    const r = await findSubstitutes(new D1Client({ fetchImpl: impl }), "262");
    // The WALK is capped; the reported depth is the real one. Capping both
    // would make the renderer say "level 6 of 6" about a 40-deep path whose
    // leaf it never reached — understating exactly the distance the "widened"
    // notice exists to disclose.
    expect(r.categoryDepth).toBe(40);
    expect(r.searchedDepth).toBeLessThanOrEqual(MAX_CATEGORY_DEPTH);
    expect(calls.filter((c) => c.includes("product_search")).length).toBe(MAX_CATEGORY_DEPTH);
  });

  test("a malformed SKU never reaches the network", async () => {
    const { impl, calls } = router([[/./, []]]);
    await expect(
      findSubstitutes(new D1Client({ fetchImpl: impl }), "262 OR productId:1"),
    ).rejects.toThrow(UsageError);
    // Not just refused — refused BEFORE the request, so a bad argument costs
    // nothing and does not depend on D1 being reachable.
    expect(calls).toEqual([]);
  });
});
