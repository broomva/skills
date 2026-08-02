import { describe, expect, test } from "bun:test";
import {
  MAX_COUNT,
  MAX_PAGE,
  encodeFacetPath,
  normalizeOffer,
  normalizeProduct,
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
