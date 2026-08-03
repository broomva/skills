import { describe, expect, test } from "bun:test";
import {
  MAX_COUNT,
  MAX_PAGE,
  encodeFacetPath,
  normalizeOffer,
  normalizeProduct,
  productBySku,
  search,
  slugify,
} from "../src/catalog.ts";
import { D1Client } from "../src/client.ts";
import { formatCOP } from "../src/money.ts";

function stub(body: unknown) {
  const calls: string[] = [];
  const impl = (async (url: string) => {
    calls.push(String(url));
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as unknown as typeof fetch;
  return { impl, calls };
}

describe("price unit normalization", () => {
  test("a search price in whole pesos becomes hundredths", () => {
    // The catalogue APIs report SKU 262 as Price 3500 (whole pesos) while the
    // checkout API reports the same product as 350000 (hundredths). Both mean
    // COP 3,500. Everything downstream of this module is hundredths.
    const offer = normalizeOffer({
      sellerId: "1",
      sellerName: "Tiendas D1",
      commertialOffer: { Price: 3500, ListPrice: 3500, AvailableQuantity: 10_000 },
    });
    expect(offer.price).toBe(350_000);
    expect(formatCOP(offer.price)).toBe("$ 3.500");
  });

  test("a search-sourced price renders identically to a checkout-sourced one", () => {
    // This is the invariant the 100x trap would violate. If someone later
    // "simplifies" the toHundredths call away, a COP 3,500 milk turns into
    // COP 35 here and the test fails loudly.
    const fromSearch = normalizeOffer({
      sellerId: "1",
      commertialOffer: { Price: 3500, ListPrice: 3500, AvailableQuantity: 1 },
    }).price;
    const fromCheckout = 350_000; // orderForm.items[0].sellingPrice, observed
    expect(fromSearch).toBe(fromCheckout);
    expect(formatCOP(fromSearch)).toBe(formatCOP(fromCheckout));
  });

  test("availability comes from quantity, since D1 omits IsAvailable", () => {
    const out = normalizeOffer({
      sellerId: "1",
      commertialOffer: { Price: 1000, AvailableQuantity: 0 },
    });
    expect(out.available).toBe(false);

    const inStock = normalizeOffer({
      sellerId: "1",
      commertialOffer: { Price: 1000, AvailableQuantity: 3 },
    });
    expect(inStock.available).toBe(true);
  });

  test("a missing list price falls back to the selling price, not to zero", () => {
    const o = normalizeOffer({ sellerId: "1", commertialOffer: { Price: 2500 } });
    expect(o.listPrice).toBe(250_000);
  });
});

describe("normalizeProduct", () => {
  const wire = {
    productId: "262",
    productName: "LECHE ENTERA TETRAPAK UHT LATTI 900 ML",
    brand: "LATTI",
    linkText: "leche-entera-latti",
    categories: ["/Lacteos y huevos/Leches/", "/Lacteos y huevos/"],
    items: [
      {
        itemId: "262",
        nameComplete: "LECHE ENTERA TETRAPAK UHT LATTI 900 ML",
        sellers: [
          {
            sellerId: "1",
            sellerName: "Tiendas D1",
            commertialOffer: { Price: 3500, ListPrice: 3500, AvailableQuantity: 10_000 },
          },
        ],
      },
    ],
  };

  test("emits one entry per SKU", () => {
    const [p] = normalizeProduct(wire);
    expect(p.skuId).toBe("262");
    expect(p.productId).toBe("262");
    expect(p.offers[0].sellerName).toBe("Tiendas D1");
  });

  test("does not collapse a multi-SKU product to its first variant", () => {
    const multi = {
      ...wire,
      items: [
        { ...wire.items[0], itemId: "262" },
        { ...wire.items[0], itemId: "263", nameComplete: "… 1900 ML" },
      ],
    };
    expect(normalizeProduct(multi).map((p) => p.skuId)).toEqual(["262", "263"]);
  });

  test("strips the slashes VTEX wraps around category paths", () => {
    const [p] = normalizeProduct(wire);
    expect(p.categories).toEqual(["Lacteos y huevos/Leches", "Lacteos y huevos"]);
  });

  test("a product with no items yields nothing rather than a phantom row", () => {
    expect(normalizeProduct({ productId: "9", items: [] })).toEqual([]);
  });
});

describe("search", () => {
  test("clamps page and count to what the API will actually serve", async () => {
    const { impl, calls } = stub({ products: [], recordsFiltered: 0 });
    await search(new D1Client({ fetchImpl: impl }), { page: 999, count: 999 });
    expect(calls[0]).toContain(`page=${MAX_PAGE}`);
    expect(calls[0]).toContain(`count=${MAX_COUNT}`);
  });

  test("flags a result set deeper than pagination can reach", async () => {
    const { impl } = stub({ products: [], recordsFiltered: 5000 });
    const page = await search(new D1Client({ fetchImpl: impl }), { count: 10 });
    // 50 pages x 10 = 500 reachable, of 5000 matches.
    expect(page.truncated).toBe(true);
  });

  test("does not flag a set that fits", async () => {
    const { impl } = stub({ products: [], recordsFiltered: 10 });
    const page = await search(new D1Client({ fetchImpl: impl }), { count: 10 });
    expect(page.truncated).toBe(false);
  });

  test("passes the region id through, since omitting it changes the answer", async () => {
    const { impl, calls } = stub({ products: [], recordsFiltered: 0 });
    await search(new D1Client({ fetchImpl: impl }), { query: "leche", regionId: "v2.ABC" });
    expect(calls[0]).toContain("regionId=v2.ABC");
  });
});

describe("encodeFacetPath", () => {
  test("keeps segment separators intact while escaping segments", () => {
    expect(encodeFacetPath("category-1/lacteos-y-huevos")).toBe("category-1/lacteos-y-huevos");
  });

  test("escapes within a segment but not the separator", () => {
    expect(encodeFacetPath("marca/café con leche")).toBe("marca/caf%C3%A9%20con%20leche");
  });

  test("drops empty segments from sloppy input", () => {
    expect(encodeFacetPath("/a//b/")).toBe("a/b");
  });
});

describe("slugify", () => {
  test("strips Colombian accents the way D1's own slugs do", () => {
    expect(slugify("Panadería y repostería")).toBe("panaderia-y-reposteria");
    expect(slugify("Licor,  vinos y más")).toBe("licor-vinos-y-mas");
  });
});

describe("per-unit sorting groups by measure", () => {
  const mk = (id: string, name: string, price: number, unit?: string, value?: string) => ({
    productId: id,
    productName: name,
    properties: unit
      ? [
          { name: "Unidad De Medida", values: [unit] },
          { name: "Valor de Medida", values: [value] },
        ]
      : [],
    items: [
      {
        itemId: id,
        nameComplete: name,
        sellers: [{ sellerId: "1", commertialOffer: { Price: price, AvailableQuantity: 5 } }],
      },
    ],
  });

  test("a /unit product does not interleave with /L products", async () => {
    // Observed live: searching for oil ranked a $8,900 BOTTLE ("/unit") in
    // among the per-litre figures as though it were a competitive buy. $/kg,
    // $/L and $/unit are not comparable quantities.
    const { impl } = stub({
      products: [
        mk("bottle", "BOTELLA PARA ACEITE", 8990, "Un", "1"),
        mk("oil3l", "ACEITE VEGETAL 3000 ML", 20500, "Ml", "3000"),
        mk("oil900", "ACEITE VEGETAL 900 ML", 6950, "Ml", "900"),
      ],
      recordsFiltered: 3,
    });
    const page = await search(new D1Client({ fetchImpl: impl }), { sort: "per-unit" });
    const order = page.products.map((p) => p.skuId);
    // Litres dominate, so both oils precede the bottle regardless of number.
    expect(order.indexOf("bottle")).toBe(2);
    expect(order.slice(0, 2)).toEqual(["oil3l", "oil900"]);
  });

  test("within the dominant measure, cheapest per unit wins", async () => {
    const { impl } = stub({
      products: [
        mk("small", "ARROZ 500 G", 1550, "Gr", "500"),
        mk("big", "ARROZ 2000 GRS", 5550, "Gr", "2000"),
      ],
      recordsFiltered: 2,
    });
    const page = await search(new D1Client({ fetchImpl: impl }), { sort: "per-unit" });
    // The bigger, more expensive pack is the better value — the whole point.
    expect(page.products[0].skuId).toBe("big");
    expect(page.products[0].unitPrice).toBe(277_500);
    expect(page.products[1].unitPrice).toBe(310_000);
  });

  test("products with no declared size sort last, never dropped", async () => {
    const { impl } = stub({
      products: [
        mk("nosize", "MISTERY ITEM", 1000),
        mk("rice", "ARROZ 1000 G", 3990, "Gr", "1000"),
      ],
      recordsFiltered: 2,
    });
    const page = await search(new D1Client({ fetchImpl: impl }), { sort: "per-unit" });
    expect(page.products.map((p) => p.skuId)).toEqual(["rice", "nosize"]);
    expect(page.products[1].unitPrice).toBeUndefined();
  });

  test("per-unit is never forwarded to D1, which has no such sort", async () => {
    const { impl, calls } = stub({ products: [], recordsFiltered: 0 });
    await search(new D1Client({ fetchImpl: impl }), { sort: "per-unit" });
    expect(calls[0]).not.toContain("per-unit");
  });

  test("warning labels are read only when declared 'si'", async () => {
    const { impl } = stub({
      products: [
        {
          productId: "x",
          properties: [
            { name: "Exceso en Azúcares", values: ["Si"] },
            { name: "Exceso en sodio", values: ["No"] },
          ],
          items: [{ itemId: "x", sellers: [] }],
        },
      ],
    });
    const page = await search(new D1Client({ fetchImpl: impl }));
    expect(page.products[0].warnings).toEqual(["Exceso en Azúcares"]);
  });
});

describe("a multipack whose PUM describes one item", () => {
  // SKU 718, live on 2026-08-03: COP 5,490 for six 200 mL juices. D1 declares
  // `Valor de Medida 200`, so the CLI priced the pack as if it held 200 mL.
  const refrescos = {
    productId: "718",
    productName: "REFRESCOS 6 UN SABORES FRUTA SURT 200 ML",
    brand: "D1",
    linkText: "refrescos-6-un",
    categories: ["/Bebidas/"],
    description: "<ul><li><strong>Contenido Neto:</strong> 6 unidades de 200 mL cada una</li></ul>",
    properties: [
      { name: "Unidad De Medida", values: ["Ml"] },
      { name: "Valor de Medida", values: ["200"] },
    ],
    items: [
      {
        itemId: "718",
        nameComplete: "REFRESCOS 6 UN SABORES FRUTA SURT 200 ML",
        sellers: [
          {
            sellerId: "1",
            commertialOffer: { Price: 5490, ListPrice: 5490, AvailableQuantity: 100 },
          },
        ],
      },
    ],
  };

  test("prices the pack, not one juice box", () => {
    const [p] = normalizeProduct(refrescos);
    expect(p.size).toEqual({ measure: "L", amount: 1.2 });
    expect(p.unitPrice).toBe(457_500); // $ 4.575/L
  });

  test("without the description it falls back to the declared value", () => {
    // Fail-open by design: if D1 stops publishing the prose, the CLI returns to
    // trusting the PUM rather than inventing a pack count from the name.
    const { description: _dropped, ...bare } = refrescos;
    const [p] = normalizeProduct(bare);
    expect(p.size).toEqual({ measure: "L", amount: 0.2 });
  });

  test("the SKU-lookup path corrects it identically to search", () => {
    // `asSearchShape` collects only string[] properties, so `description` has
    // to be forwarded by hand. If that is dropped, this SKU is correct through
    // `d1 search` and wrong through `d1 substitute`, which reads it this way.
    const { impl } = stub([
      {
        ...refrescos,
        "Unidad De Medida": ["Ml"],
        "Valor de Medida": ["200"],
        properties: undefined,
      },
    ]);
    const client = new D1Client({ fetchImpl: impl });
    return productBySku(client, "718").then((p) => {
      expect(p?.size).toEqual({ measure: "L", amount: 1.2 });
      expect(p?.unitPrice).toBe(457_500);
    });
  });
});

describe("a multipack whose PUM already describes the pack", () => {
  // SKU 897 — the product the bug was reported on. Its description mentions a
  // per-unit size but states no count, so there is nothing to multiply by, and
  // the declared 600 mL is already right.
  const leche = {
    productId: "897",
    productName: "LECHE CHOCOLATE TPAK LATTI 3 UN 600 ML",
    brand: "LATTI",
    linkText: "leche-chocolate-latti",
    categories: ["/Lacteos y huevos/"],
    description: "<ul><li><strong>Peso:</strong> 600 mL (200 mL por unidad)</li></ul>",
    properties: [
      { name: "Unidad De Medida", values: ["Ml"] },
      { name: "Valor de Medida", values: ["600"] },
    ],
    items: [
      {
        itemId: "897",
        nameComplete: "LECHE CHOCOLATE TPAK LATTI 3 UN 600 ML",
        sellers: [
          {
            sellerId: "1",
            commertialOffer: { Price: 5150, ListPrice: 5150, AvailableQuantity: 50 },
          },
        ],
      },
    ],
  };

  test("is left exactly as declared", () => {
    const [p] = normalizeProduct(leche);
    expect(p.size).toEqual({ measure: "L", amount: 0.6 });
    expect(p.unitPrice).toBe(858_333); // $ 8.583/L, unchanged
  });
});
