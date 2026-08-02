import { describe, expect, test } from "bun:test";
import { parseArgs, parseSpec } from "../src/cli.ts";
import {
  bestOffer,
  humanEstimate,
  renderCart,
  renderRegion,
  renderSearch,
} from "../src/present.ts";
import type { Product, SearchPage } from "../src/types.ts";

const product = (over: Partial<Product> = {}): Product => ({
  productId: "262",
  skuId: "262",
  name: "LECHE ENTERA TETRAPAK UHT LATTI 900 ML",
  brand: "LATTI",
  linkText: "leche",
  categories: [],
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
    // --lng -74.06 is the single most common invocation, and a naive parser
    // reads the longitude as a flag because it starts with a dash.
    const a = parseArgs(["region", "--lat", "4.65", "--lng=-74.06"]);
    expect(a.flags.lng).toBe("-74.06");
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
