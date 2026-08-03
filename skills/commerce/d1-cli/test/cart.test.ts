import { describe, expect, test } from "bun:test";
import {
  addItems,
  listAddresses,
  normalizeCart,
  setDeliveryPoint,
  setQuantity,
  simulate,
  undeliverable,
  useSavedAddress,
} from "../src/cart.ts";
import { D1Client } from "../src/client.ts";
import { renderAddresses, renderCart } from "../src/present.ts";
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
    expect(c.messages).toEqual([
      { text: "El precio de un producto cambió.", code: "", status: "info" },
    ]);
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

describe("an undeliverable cart must not read as payable", () => {
  /**
   * VTEX reports `cannotBeDelivered` with `status: "error"` while STILL
   * returning a valid SLA per item and a computed total. Observed live: nine
   * lines, nine errors, and a cart that printed a checkout URL and
   * "$95.930 ready to pay" because the messages rendered BELOW the total.
   */
  const BROKEN = {
    orderFormId: "of1",
    value: 9_593_000,
    items: [{ id: "262", name: "LECHE", quantity: 1, seller: "s", sellingPrice: 350_000 }],
    totalizers: [{ id: "Items", value: 8_323_000 }],
    shippingData: {
      logisticsInfo: [
        { slas: [{ id: "Entrega Programada", price: 1_270_000, shippingEstimate: "1bd" }] },
      ],
    },
    messages: [
      {
        code: "cannotBeDelivered",
        status: "error",
        text: "El ítem LECHE no pudo ser enviado para las coordenadas seleccionadas",
      },
    ],
  };

  test("severity survives normalization — it is not just text", () => {
    const c = normalizeCart(BROKEN);
    expect(c.messages[0].status).toBe("error");
    expect(c.messages[0].code).toBe("cannotBeDelivered");
  });

  test("a STICKY cannotBeDelivered on a line that HAS an SLA does not block", () => {
    // Proven against production: the message survives items/removeAll and a
    // re-add, so a currently-fine line still carries it. The first version of
    // this guard blocked on the message and refused healthy carts.
    expect(undeliverable(normalizeCart(BROKEN))).toEqual([]);
    expect(normalizeCart(BROKEN).items[0].deliverable).toBe(true);
  });

  test("an EMPTY slas array is what actually blocks", () => {
    // The true-negative, measured by moving one cart to an address D1 does not
    // serve: slas went [["Entrega Programada"]] -> [[]].
    const c = normalizeCart({
      ...BROKEN,
      shippingData: { logisticsInfo: [{ itemIndex: 0, slas: [] }] },
    });
    expect(c.items[0].deliverable).toBe(false);
    expect(undeliverable(c)).toHaveLength(1);
  });

  test("a cart with no delivery point yet is not 'refused'", () => {
    // deliverable === undefined means not quoted. Treating that as refused
    // would block every cart before `deliver-to` runs.
    const c = normalizeCart({ orderFormId: "of1", items: [{ id: "262", quantity: 1 }] });
    expect(c.items[0].deliverable).toBeUndefined();
    expect(undeliverable(c)).toEqual([]);
  });

  test("a healthy cart reports nothing blocked (anti-overshoot)", () => {
    const ok = normalizeCart({
      orderFormId: "of1",
      items: [{ id: "262", quantity: 1, sellingPrice: 350_000 }],
      messages: [{ code: "priceChange", status: "warning", text: "El precio cambió." }],
    });
    expect(undeliverable(ok)).toEqual([]);
    expect(ok.messages[0].status).toBe("warning");
  });

  test("severity still survives normalization for display", () => {
    const c = normalizeCart(BROKEN);
    expect(c.messages[0].status).toBe("error");
    expect(c.messages[0].code).toBe("cannotBeDelivered");
  });

  test("a genuinely blocked line renders ABOVE the total", () => {
    // It printed last — after the total and the checkout URL — so an
    // undeliverable cart still read as ready to pay.
    const c = normalizeCart({
      ...BROKEN,
      shippingData: { logisticsInfo: [{ itemIndex: 0, slas: [] }] },
    });
    const out = renderCart(c);
    expect(out).toContain("CANNOT be delivered");
    expect(out.indexOf("CANNOT be delivered")).toBeLessThan(out.indexOf("Total"));
    expect(out).toContain("not safe to check out");
  });

  test("a stale notice is labelled, not presented as a live failure", () => {
    expect(renderCart(normalizeCart(BROKEN))).toContain("stale notice");
  });
});

describe("an apartment address survives to the wire", () => {
  test("complement, neighborhood and reference are all sent", async () => {
    // `street` alone strands a parcel at the building gate: couriers and D1's
    // checkout read the unit from `complement`. Before this, the CLI could not
    // express "Torre 1 Apto 2102" at all.
    const { impl, calls } = stub({ orderFormId: "of1" });
    await setDeliveryPoint(
      new D1Client({ fetchImpl: impl }),
      "of1",
      {
        lat: 4.75068,
        lng: -74.03532,
      },
      {
        street: "Cra 13 # 172a-51",
        complement: "Torre 1 Apto 2102",
        neighborhood: "Ciudad La Salle Montpellier",
        reference: "Conjunto Ciudad La Salle Montpellier",
        city: "Bogotá",
        state: "DC",
      },
    );
    const sent = JSON.parse(calls[0].body ?? "{}").selectedAddresses[0];
    expect(sent.complement).toBe("Torre 1 Apto 2102");
    expect(sent.neighborhood).toBe("Ciudad La Salle Montpellier");
    expect(sent.reference).toBe("Conjunto Ciudad La Salle Montpellier");
    expect(sent.street).toBe("Cra 13 # 172a-51");
    // and the coordinate order gotcha still holds
    expect(sent.geoCoordinates).toEqual([-74.03532, 4.75068]);
  });

  test("omitted parts stay omitted rather than becoming empty strings", async () => {
    const { impl, calls } = stub({ orderFormId: "of1" });
    await setDeliveryPoint(new D1Client({ fetchImpl: impl }), "of1", { lat: 4.6, lng: -74.1 });
    const sent = JSON.parse(calls[0].body ?? "{}").selectedAddresses[0];
    expect(sent.complement).toBeUndefined();
    expect(sent.country).toBe("COL");
  });
});

describe("saved addresses — the customer's own, not ours", () => {
  /** Shaped from a real account: 1 canonical record + junk the CLI itself made. */
  const WIRE = {
    orderFormId: "of1",
    shippingData: {
      availableAddresses: [
        {
          addressId: "bc204a4218fcba14c19eaab72c1d0fcf4fcf29f9",
          addressType: "residential",
          street: "KR 15",
          number: "170 - 84",
          complement: "T1-2102 Montpellier Ciudad La Salle",
          neighborhood: "SAN JOSE DE USAQUEN",
          city: "BOGOTÁ, D.C.",
          postalCode: "110141660",
          geoCoordinates: [-74.03525108413305, 4.751136575516661],
        },
        // Nine of these accumulated in a live account, one per deliver-to call.
        {
          addressId: "5dfea8d93a8f",
          street: null,
          city: null,
          geoCoordinates: [-74.03532, 4.75068],
        },
      ],
    },
  };

  test("lists the address book with ids", async () => {
    const { impl } = stub(WIRE);
    const a = await listAddresses(new D1Client({ fetchImpl: impl }), "of1");
    expect(a).toHaveLength(2);
    expect(a[0].addressId).toBe("bc204a4218fcba14c19eaab72c1d0fcf4fcf29f9");
    expect(a[0].postalCode).toBe("110141660");
  });

  test("a record with no street is marked incomplete, not surfaced as an address", () => {
    // These are what the CLI minted from bare coordinates. Presenting them as
    // choosable addresses would be presenting our own litter back to the user.
    const { impl } = stub(WIRE);
    return listAddresses(new D1Client({ fetchImpl: impl }), "of1").then((a) => {
      expect(a[0].complete).toBe(true);
      expect(a[1].complete).toBe(false);
      expect(renderAddresses(a)).toContain("1 incomplete record");
      expect(renderAddresses(a)).not.toContain("5dfea8d93a8f");
    });
  });

  test("nulls do not become the string 'null'", async () => {
    const { impl } = stub(WIRE);
    const a = await listAddresses(new D1Client({ fetchImpl: impl }), "of1");
    expect(a[1].street).toBeUndefined();
    expect(a[1].city).toBeUndefined();
  });

  test("passing an addressId REUSES a record instead of minting one", async () => {
    const { impl, calls } = stub({ orderFormId: "of1" });
    await setDeliveryPoint(
      new D1Client({ fetchImpl: impl }),
      "of1",
      { lat: 4.75, lng: -74.03 },
      {
        addressId: "bc204a4218fcba14c19eaab72c1d0fcf4fcf29f9",
      },
    );
    const sent = JSON.parse(calls[0].body ?? "{}").selectedAddresses[0];
    expect(sent.addressId).toBe("bc204a4218fcba14c19eaab72c1d0fcf4fcf29f9");
  });

  test("omitting it sends no addressId — which is what mints a new record", async () => {
    // Pinned so the behaviour is explicit rather than incidental: the CLI warns
    // at this call site precisely because VTEX will create a record.
    const { impl, calls } = stub({ orderFormId: "of1" });
    await setDeliveryPoint(new D1Client({ fetchImpl: impl }), "of1", { lat: 4.75, lng: -74.03 });
    expect(JSON.parse(calls[0].body ?? "{}").selectedAddresses[0].addressId).toBeUndefined();
  });

  test("an empty book explains how to create one", () => {
    expect(renderAddresses([])).toContain("map picker");
  });
});

describe("useSavedAddress posts the WHOLE record, not just the id", () => {
  const BOOK = {
    orderFormId: "of1",
    shippingData: {
      availableAddresses: [
        {
          addressId: "bc204a4218fcba14c19eaab72c1d0fcf4fcf29f9",
          addressType: "residential",
          street: "KR 15",
          number: "170 - 84",
          complement: "T1-2102 Montpellier Ciudad La Salle",
          neighborhood: "SAN JOSE DE USAQUEN",
          city: "BOGOTÁ, D.C.",
          state: "BOGOTÁ, D.C.",
          postalCode: "110141660",
          geoCoordinates: [-74.03525108413305, 4.751136575516661],
        },
        { addressId: "5dfea8d93a8f", street: null, geoCoordinates: [-74.03532, 4.75068] },
      ],
    },
  };

  test("sends every canonical field back", async () => {
    // Sending the addressId ALONE does not work — verified live: VTEX ignored
    // it and selected a fresh empty address, which is both wrong and yet
    // another junk record.
    const { impl, calls } = stub(BOOK);
    await useSavedAddress(new D1Client({ fetchImpl: impl }), "of1", "bc204a4218fc");
    const sent = JSON.parse(calls[1].body ?? "{}").selectedAddresses[0];
    expect(sent.addressId).toBe("bc204a4218fcba14c19eaab72c1d0fcf4fcf29f9");
    expect(sent.street).toBe("KR 15");
    expect(sent.number).toBe("170 - 84");
    expect(sent.postalCode).toBe("110141660");
    expect(sent.geoCoordinates).toEqual([-74.03525108413305, 4.751136575516661]);
  });

  test("a short id prefix resolves", async () => {
    const { impl } = stub(BOOK);
    await expect(
      useSavedAddress(new D1Client({ fetchImpl: impl }), "of1", "bc204a"),
    ).resolves.toBeDefined();
  });

  test("an unknown id is rejected, not silently ignored", async () => {
    const { impl } = stub(BOOK);
    await expect(
      useSavedAddress(new D1Client({ fetchImpl: impl }), "of1", "deadbeef"),
    ).rejects.toThrow(/No saved address matches/);
  });

  test("an INCOMPLETE record is refused — it is our own litter, not an address", async () => {
    const { impl } = stub(BOOK);
    await expect(
      useSavedAddress(new D1Client({ fetchImpl: impl }), "of1", "5dfea8d93a8f"),
    ).rejects.toThrow(/no street/);
  });
});
