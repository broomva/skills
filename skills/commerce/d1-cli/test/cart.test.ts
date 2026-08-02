import { describe, expect, test } from "bun:test";
import { addItems, normalizeCart, setQuantity, simulate } from "../src/cart.ts";
import { D1Client } from "../src/client.ts";
import { D1Error } from "../src/types.ts";

function stub(body: unknown, status = 200) {
  const calls: Array<{ url: string; body?: string }> = [];
  const impl = (async (url: string, init?: RequestInit) => {
    calls.push({ url: String(url), body: init?.body as string | undefined });
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as unknown as typeof fetch;
  return { impl, calls };
}

const ORDER_FORM = {
  orderFormId: "of1",
  loggedIn: false,
  value: 700_000,
  items: [
    {
      id: "262",
      name: "LECHE ENTERA TETRAPAK UHT LATTI 900 ML",
      quantity: 2,
      seller: "1",
      sellingPrice: 350_000,
      priceDefinition: { total: 700_000 },
    },
  ],
  totalizers: [{ id: "Items", value: 700_000 }],
  messages: [],
};

describe("normalizeCart", () => {
  test("keeps checkout's hundredths and the upstream line total", () => {
    const c = normalizeCart(ORDER_FORM);
    expect(c.items[0].sellingPrice).toBe(350_000);
    expect(c.items[0].total).toBe(700_000);
    expect(c.itemsTotal).toBe(700_000);
    expect(c.total).toBe(700_000);
  });

  test("falls back to quantity x unit price when priceDefinition is absent", () => {
    const c = normalizeCart({
      orderFormId: "of1",
      items: [{ id: "9", quantity: 3, sellingPrice: 100_000 }],
    });
    expect(c.items[0].total).toBe(300_000);
  });

  test("collapses a repeated SLA into ONE row whose price is the whole cost", () => {
    // VTEX repeats logisticsInfo once per line, and each entry's slas[].price
    // is that LINE'S SHARE. Three lines of a flat COP 13,500 delivery arrive as
    // 4,500 each. Showing one row is right; showing 4,500 is not — the previous
    // version did exactly that and under-reported shipping by the line count.
    const share = 450_000; // COP 4,500 in hundredths
    const c = normalizeCart({
      orderFormId: "of1",
      shippingData: {
        logisticsInfo: [
          { slas: [{ id: "Entrega Programada", price: share, shippingEstimate: "1bd" }] },
          { slas: [{ id: "Entrega Programada", price: share, shippingEstimate: "1bd" }] },
          { slas: [{ id: "Entrega Programada", price: share, shippingEstimate: "1bd" }] },
        ],
      },
    });
    expect(c.shipping).toHaveLength(1);
    expect(c.shipping[0].price).toBe(1_350_000); // COP 13,500, the real cost
    expect(c.shipping[0].price).not.toBe(share); // the bug this replaces
  });

  test("a single-line cart is unchanged (the case that hid the bug)", () => {
    // With one line the share IS the total, which is why 1- and 2-line fixtures
    // could not distinguish summing from taking the first.
    const c = normalizeCart({
      orderFormId: "of1",
      shippingData: {
        logisticsInfo: [
          { slas: [{ id: "Entrega Programada", price: 1_350_000, shippingEstimate: "1bd" }] },
        ],
      },
    });
    expect(c.shipping[0].price).toBe(1_350_000);
  });

  test("distinct options stay distinct and are summed independently", () => {
    const c = normalizeCart({
      orderFormId: "of1",
      shippingData: {
        logisticsInfo: [
          {
            slas: [
              { id: "Programada", price: 100_000, shippingEstimate: "1bd" },
              { id: "Express", price: 300_000, shippingEstimate: "4h" },
            ],
          },
          {
            slas: [
              { id: "Programada", price: 100_000, shippingEstimate: "1bd" },
              { id: "Express", price: 300_000, shippingEstimate: "4h" },
            ],
          },
        ],
      },
    });
    expect(c.shipping.map((s) => [s.id, s.price])).toEqual([
      ["Programada", 200_000],
      ["Express", 600_000],
    ]);
  });

  test("an unquoted cart reports no shipping rather than free shipping", () => {
    const c = normalizeCart({ orderFormId: "of1", items: [] });
    expect(c.shipping).toEqual([]);
  });

  test("surfaces upstream messages", () => {
    const c = normalizeCart({
      orderFormId: "of1",
      messages: [{ text: "El precio de un producto cambió." }],
    });
    expect(c.messages).toEqual(["El precio de un producto cambió."]);
  });
});

describe("addItems", () => {
  test("sends the SKU, quantity and fulfilling seller", async () => {
    const { impl, calls } = stub(ORDER_FORM);
    await addItems(new D1Client({ fetchImpl: impl }), "of1", [
      { skuId: "262", quantity: 2, sellerId: "d1bon11808cc" },
    ]);
    const sent = JSON.parse(calls[0].body ?? "{}");
    expect(sent.orderItems).toEqual([{ id: "262", quantity: 2, seller: "d1bon11808cc" }]);
  });

  test("rejects a fractional or zero quantity before calling upstream", async () => {
    const { impl, calls } = stub(ORDER_FORM);
    const client = new D1Client({ fetchImpl: impl });
    await expect(
      addItems(client, "of1", [{ skuId: "1", quantity: 0, sellerId: "1" }]),
    ).rejects.toThrow(D1Error);
    await expect(
      addItems(client, "of1", [{ skuId: "1", quantity: 1.5, sellerId: "1" }]),
    ).rejects.toThrow(/whole number/);
    expect(calls).toHaveLength(0);
  });

  test("rejects an empty add", async () => {
    const { impl } = stub(ORDER_FORM);
    await expect(addItems(new D1Client({ fetchImpl: impl }), "of1", [])).rejects.toThrow(D1Error);
  });
});

describe("setQuantity", () => {
  test("allows zero, which is how VTEX removes a line", async () => {
    const { impl, calls } = stub({ orderFormId: "of1", items: [] });
    await setQuantity(new D1Client({ fetchImpl: impl }), "of1", 0, 0);
    expect(JSON.parse(calls[0].body ?? "{}").orderItems).toEqual([{ index: 0, quantity: 0 }]);
  });

  test("rejects a negative index or quantity", async () => {
    const { impl } = stub({ orderFormId: "of1" });
    const client = new D1Client({ fetchImpl: impl });
    await expect(setQuantity(client, "of1", -1, 1)).rejects.toThrow(/non-negative/);
    await expect(setQuantity(client, "of1", 0, -1)).rejects.toThrow(/zero or a positive/);
  });
});

describe("error translation", () => {
  test("401 tells the user to sign in again", async () => {
    const { impl } = stub({}, 401);
    await expect(
      addItems(new D1Client({ fetchImpl: impl }), "of1", [
        { skuId: "1", quantity: 1, sellerId: "1" },
      ]),
    ).rejects.toThrow(/expired|sign(ed)? in/i);
  });

  test("429 names rate limiting instead of leaking a bare status", async () => {
    const { impl } = stub({}, 429);
    await expect(
      addItems(new D1Client({ fetchImpl: impl }), "of1", [
        { skuId: "1", quantity: 1, sellerId: "1" },
      ]),
    ).rejects.toThrow(/rate-limiting/i);
  });
});

describe("simulate — quantity must survive the quote", () => {
  /**
   * Real payload shape from the simulation endpoint for
   * `262 x2 + 892 x1` delivered to Chapinero. Note `price` is PER UNIT
   * (350000) while the line is 700000: an early version of this CLI summed
   * `price` and quoted a two-litre basket as if it were one, under-reporting
   * by 35%. Dogfooding caught it; this pins it.
   */
  const SIM = {
    items: [
      {
        id: "262",
        quantity: 2,
        availability: "available",
        price: 350_000,
        priceDefinition: { total: 700_000 },
      },
      {
        id: "892",
        quantity: 1,
        availability: "available",
        price: 309_000,
        priceDefinition: { total: 309_000 },
      },
    ],
    totals: [{ id: "Items", value: 1_009_000 }],
    logisticsInfo: [
      { slas: [{ id: "Entrega Programada", price: 900_000, shippingEstimate: "1bd" }] },
    ],
  };

  const AT = { lat: 4.6486, lng: -74.0628 };

  test("a line total reflects quantity, not the unit price", async () => {
    const { impl } = stub(SIM);
    const r = await simulate(
      new D1Client({ fetchImpl: impl }),
      [
        { skuId: "262", quantity: 2, sellerId: "d1bon11808cc" },
        { skuId: "892", quantity: 1, sellerId: "d1bon11808cc" },
      ],
      AT,
    );

    expect(r.items[0].unitPrice).toBe(350_000);
    expect(r.items[0].total).toBe(700_000);
    expect(r.items[0].quantity).toBe(2);
  });

  test("the basket total matches what checkout would charge", async () => {
    const { impl } = stub(SIM);
    const r = await simulate(
      new D1Client({ fetchImpl: impl }),
      [{ skuId: "262", quantity: 2, sellerId: "d1bon11808cc" }],
      AT,
    );
    // COP 10,090 — not the 6,590 a naive sum of unit prices produces.
    expect(r.itemsTotal).toBe(1_009_000);
    expect(r.itemsTotal).not.toBe(659_000);
  });

  test("falls back to unit x quantity when priceDefinition is missing", async () => {
    const { impl } = stub({
      items: [{ id: "5", quantity: 3, availability: "available", price: 100_000 }],
    });
    const r = await simulate(
      new D1Client({ fetchImpl: impl }),
      [{ skuId: "5", quantity: 3, sellerId: "1" }],
      AT,
    );
    expect(r.items[0].total).toBe(300_000);
    expect(r.itemsTotal).toBe(300_000);
  });

  test("an unavailable line is excluded from the fallback total", async () => {
    const { impl } = stub({
      items: [
        { id: "5", quantity: 1, availability: "available", price: 100_000 },
        { id: "6", quantity: 1, availability: "withoutStock", price: 500_000 },
      ],
    });
    const r = await simulate(
      new D1Client({ fetchImpl: impl }),
      [
        { skuId: "5", quantity: 1, sellerId: "1" },
        { skuId: "6", quantity: 1, sellerId: "1" },
      ],
      AT,
    );
    expect(r.items[1].available).toBe(false);
    expect(r.itemsTotal).toBe(100_000);
  });
});

describe("simulate — an unknown SKU must not pass vacuously", () => {
  const AT = { lat: 4.6486, lng: -74.0628 };

  test("a SKU upstream omits entirely is reported as unknown", async () => {
    // D1 answers a bogus SKU with an empty items array rather than an error.
    // Reported naively this becomes "0 items, all available" — and any
    // `every(available)` check passes on the empty list.
    const { impl } = stub({ items: [], totals: [], logisticsInfo: [] });
    const r = await simulate(
      new D1Client({ fetchImpl: impl }),
      [{ skuId: "999999", quantity: 1, sellerId: "1" }],
      AT,
    );

    expect(r.items).toEqual([]);
    expect(r.unknownSkus).toEqual(["999999"]);
    // The trap, stated explicitly: this is TRUE, which is why it cannot be the
    // sole basis for a success verdict.
    expect(r.items.every((i) => i.available)).toBe(true);
  });

  test("distinguishes not-in-catalogue from out-of-stock", async () => {
    const { impl } = stub({
      items: [{ id: "262", quantity: 1, availability: "withoutStock", price: 350_000 }],
    });
    const r = await simulate(
      new D1Client({ fetchImpl: impl }),
      [
        { skuId: "262", quantity: 1, sellerId: "1" },
        { skuId: "999999", quantity: 1, sellerId: "1" },
      ],
      AT,
    );

    expect(r.unknownSkus).toEqual(["999999"]);
    expect(r.items[0].available).toBe(false);
  });

  test("a fully-known basket reports no unknowns", async () => {
    const { impl } = stub({
      items: [{ id: "262", quantity: 1, availability: "available", price: 350_000 }],
    });
    const r = await simulate(
      new D1Client({ fetchImpl: impl }),
      [{ skuId: "262", quantity: 1, sellerId: "1" }],
      AT,
    );
    expect(r.unknownSkus).toEqual([]);
  });
});

describe("promotions are accounted for, not silently dropped", () => {
  test("surfaces the Discounts totalizer", () => {
    const c = normalizeCart({
      orderFormId: "of1",
      value: 1_500_000,
      items: [{ id: "262", quantity: 1, sellingPrice: 2_000_000 }],
      totalizers: [
        { id: "Items", value: 2_000_000 },
        { id: "Discounts", value: -500_000 },
      ],
    });
    // Without this, the cart renders "Items 20.000 / Total 15.000" with a
    // 5.000 gap nothing explains — on the surface where a shopper checks the
    // arithmetic before paying.
    expect(c.itemsTotal).toBe(2_000_000);
    expect(c.discounts).toBe(-500_000);
    expect(c.total).toBe(1_500_000);
    expect(c.itemsTotal + c.discounts).toBe(c.total);
  });

  test("an unpromoted cart reports zero, not undefined", () => {
    const c = normalizeCart({
      orderFormId: "of1",
      totalizers: [{ id: "Items", value: 700_000 }],
    });
    expect(c.discounts).toBe(0);
  });
});

describe("simulate — shipping shares are summed there too", () => {
  const AT = { lat: 4.6486, lng: -74.0628 };

  test("a 3-line simulation reports the whole delivery cost", async () => {
    // The simulation endpoint returns no populated Shipping totalizer, so the
    // per-line sum is the only source of truth on this path.
    const { impl } = stub({
      items: [
        { id: "a", quantity: 1, availability: "available", price: 100_000 },
        { id: "b", quantity: 1, availability: "available", price: 100_000 },
        { id: "c", quantity: 1, availability: "available", price: 100_000 },
      ],
      logisticsInfo: [
        { slas: [{ id: "Entrega Programada", price: 450_000, shippingEstimate: "1bd" }] },
        { slas: [{ id: "Entrega Programada", price: 450_000, shippingEstimate: "1bd" }] },
        { slas: [{ id: "Entrega Programada", price: 450_000, shippingEstimate: "1bd" }] },
      ],
    });
    const r = await simulate(
      new D1Client({ fetchImpl: impl }),
      [
        { skuId: "a", quantity: 1, sellerId: "s" },
        { skuId: "b", quantity: 1, sellerId: "s" },
        { skuId: "c", quantity: 1, sellerId: "s" },
      ],
      AT,
    );
    expect(r.shipping).toHaveLength(1);
    expect(r.shipping[0].price).toBe(1_350_000);
  });
});
