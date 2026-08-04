import { describe, expect, test } from "bun:test";
import { D1Client } from "../src/client.ts";
import { formatCOP } from "../src/money.ts";
import { listOrders, orderForDisplay, redactOrder, statusLabel } from "../src/orders.ts";
import { D1Error } from "../src/types.ts";

function stub(body: unknown, status = 200) {
  const impl = (async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
  return impl;
}

const authed = (body: unknown, status = 200) =>
  new D1Client({ fetchImpl: stub(body, status), authToken: "tok" });

describe("listOrders", () => {
  test("requires a session rather than returning an empty list", async () => {
    // Anonymous, this endpoint 401s. Answering "no orders" would be a lie that
    // reads like good news.
    const anon = new D1Client({ fetchImpl: stub({}) });
    await expect(listOrders(anon)).rejects.toThrow(/signed-in|d1 login/i);
  });

  test("normalizes an order and labels its status in Spanish", async () => {
    const c = authed({
      list: [
        {
          orderId: "1234567890-01",
          status: "ready-for-handling",
          creationDate: "2026-07-30T14:02:11.000Z",
          totalValue: 8_500_000,
          ItemsQuantity: 12,
        },
      ],
      paging: { total: 1, pages: 1, currentPage: 1 },
    });
    const { orders, total, pages } = await listOrders(c);
    expect(orders).toHaveLength(1);
    expect(orders[0].orderId).toBe("1234567890-01");
    expect(orders[0].statusLabel).toBe("En preparación");
    expect(orders[0].itemCount).toBe(12);
    expect(total).toBe(1);
    expect(pages).toBe(1);
  });

  test("an empty history is reported as empty, not as an error", async () => {
    const c = authed({ list: [], paging: { total: 0, pages: 0 } });
    const { orders, total } = await listOrders(c);
    expect(orders).toEqual([]);
    expect(total).toBe(0);
  });

  test("falls back to counting items when ItemsQuantity is absent", async () => {
    const c = authed({ list: [{ orderId: "x", items: [{}, {}, {}] }] });
    const { orders } = await listOrders(c);
    expect(orders[0].itemCount).toBe(3);
  });

  test("an unknown status passes through rather than becoming blank", () => {
    expect(statusLabel("some-future-status")).toBe("some-future-status");
    expect(statusLabel("invoiced")).toBe("Facturado / enviado");
  });

  test("clamps per_page into the range the API accepts", async () => {
    let seen = "";
    const c = new D1Client({
      authToken: "tok",
      fetchImpl: (async (url: string) => {
        seen = String(url);
        return new Response(JSON.stringify({ list: [] }), { status: 200 });
      }) as unknown as typeof fetch,
    });
    await listOrders(c, { page: 0, perPage: 9999 });
    expect(seen).toContain("page=1");
    expect(seen).toContain("per_page=50");
  });

  test("surfaces an upstream failure instead of swallowing it", async () => {
    await expect(listOrders(authed({}, 500))).rejects.toThrow(D1Error);
  });
});

describe("order totals — the unit this codebase could not verify", () => {
  /**
   * `totalValue` is ASSUMED to be hundredths, by analogy with the rest of the
   * checkout API. Unlike every other price here it was never confirmed against
   * live data: the account this skill was built against has no D1 order
   * history, so there was no real order to check.
   *
   * This test does not prove the assumption — nothing available can. What it
   * does is make the assumption *visible and executable*, so that if someone
   * ever sees a real order render 100x wrong, the fixture states exactly what
   * was believed and where to change it.
   */
  test("pins the assumption: totalValue is treated as hundredths", async () => {
    const c = authed({ list: [{ orderId: "x", totalValue: 8_500_000 }] });
    const { orders } = await listOrders(c);
    expect(orders[0].total).toBe(8_500_000);
    // If D1 in fact returns whole pesos, this renders COP 8.5M as COP 85,000
    // and the line below is the one to change.
    expect(formatCOP(orders[0].total)).toBe("$ 85.000");
  });

  test("a missing total is zero, not NaN", async () => {
    const c = authed({ list: [{ orderId: "x" }] });
    const { orders } = await listOrders(c);
    expect(orders[0].total).toBe(0);
    expect(formatCOP(orders[0].total)).toBe("$ 0");
  });
});

describe("redactOrder", () => {
  /** Shaped like the real VTEX order-detail payload. */
  const ORDER = {
    orderId: "1234567890-01",
    status: "invoiced",
    value: 8_500_000,
    clientProfileData: {
      email: "someone@example.com",
      firstName: "Ada",
      document: "1020304050",
      documentType: "CPF",
      phone: "+573001234567",
    },
    shippingData: {
      address: {
        street: "Calle 72",
        number: "10-34",
        neighborhood: "Chapinero",
        postalCode: "110111",
        city: "Bogotá",
        geoCoordinates: [-74.0628, 4.6486],
      },
    },
    paymentData: {
      transactions: [
        {
          payments: [
            { paymentSystemName: "Visa", firstDigits: "411111", lastDigits: "1234", tid: "abc" },
          ],
        },
      ],
    },
    // TWO items and TWO totals, deliberately. With one element each, a mutation
    // collapsing only index 0 to `[]` left the whole suite green — the claim
    // "`items[].name` matches at ANY index" was asserted nowhere.
    items: [
      { id: "262", name: "LECHE", quantity: 2, sellingPrice: 350_000 },
      { id: "263", name: "ARROZ", quantity: 1, sellingPrice: 555_000 },
    ],
    totals: [
      { id: "Items", name: "Total dos itens", value: 905_000 },
      { id: "Shipping", name: "Total do frete", value: 1_270_000 },
    ],
  };

  // Redaction replaces values with a string, so the redacted object is
  // deliberately NOT `typeof ORDER` — geoCoordinates goes number[] -> string.
  // biome-ignore lint/suspicious/noExplicitAny: assertions below are the schema
  const red = redactOrder(ORDER) as any;

  test("removes the national ID, phone and email", () => {
    // These lived under `clientProfileData`, which is now withheld whole — so
    // the assertion is on the serialized output rather than on each key, which
    // would only prove the key vanished, not that its value did.
    const blob = JSON.stringify(red);
    for (const secret of ["1020304050", "CPF", "+573001234567", "someone@example.com"]) {
      expect(blob).not.toContain(secret);
    }
    expect(red.clientProfileData).toBe("[redacted]");
  });

  test("removes the delivery address and coordinates, nested arbitrarily deep", () => {
    const a = red.shippingData.address;
    expect(a.street).toBe("[redacted]");
    expect(a.postalCode).toBe("[redacted]");
    // Withheld WHOLE, not element-by-element. Redacting each number still
    // published that there were exactly two of them, and the length of a value
    // is part of the value.
    expect(a.geoCoordinates).toBe("[redacted]");
    expect(Array.isArray(a.geoCoordinates)).toBe(false);
  });

  test("an unanticipated key is redacted — the allowlist fails CLOSED", () => {
    // The defect this replaced: `SENSITIVE_KEYS` was a blocklist, so any PII key
    // its author had not thought of printed in full. Nobody has ever seen a real
    // D1 order, so "keys the author thought of" was a guess about an unopened
    // envelope. These are all plausible VTEX fields that the blocklist missed.
    const exotic = redactOrder({
      orderId: "1234567890-01",
      clientProfileData: { stateInscription: "1020304050", tradeName: "Ada Lovelace" },
      giftRegistryData: { recipientEmail: "someone@example.com" },
      marketplacePaymentValue: 8_500_000,
      customData: { customApps: [{ fields: { cedula: "1020304050" } }] },
    }) as Record<string, unknown>;
    const blob = JSON.stringify(exotic);
    for (const secret of ["1020304050", "Ada Lovelace", "someone@example.com"]) {
      expect(blob).not.toContain(secret);
    }
    // ...while the field that IS on the allowlist still prints, so the test
    // cannot pass by redacting everything unconditionally.
    expect(exotic.orderId).toBe("1234567890-01");
  });

  test("removes card digits and the transaction id", () => {
    const p = red.paymentData.transactions[0].payments[0];
    expect(p.firstDigits).toBe("[redacted]");
    expect(p.lastDigits).toBe("[redacted]");
    expect(p.tid).toBe("[redacted]");
  });

  test("keeps everything needed to answer 'where is my order?'", () => {
    expect(red.orderId).toBe("1234567890-01");
    expect(red.status).toBe("invoiced");
    expect(red.value).toBe(8_500_000);
    expect(red.items[0].name).toBe("LECHE");
    expect(red.items[0].quantity).toBe(2);
    // Index 1, which is the point: `[]` is not "the first one".
    expect(red.items[1].name).toBe("ARROZ");
    expect(red.totals[1].value).toBe(1_270_000);
    // Allowlisted neighbours of redacted keys survive, arbitrarily deep.
    expect(red.shippingData.address.city).toBe("Bogotá");
    expect(red.paymentData.transactions[0].payments[0].paymentSystemName).toBe("Visa");
  });

  test("the customer's name no longer survives — clientProfileData is withheld whole", () => {
    // The blocklist printed `firstName` because it was not on the list, and the
    // test asserted that as intended behaviour. It was not intended; it was the
    // blocklist's failure mode written down as a promise. Nothing in
    // `clientProfileData` is needed to answer "where is my order?", so under the
    // allowlist none of it is worth printing by default.
    expect(red.clientProfileData).toBe("[redacted]");
  });

  test("does not mutate the input", () => {
    expect(ORDER.clientProfileData.document).toBe("1020304050");
  });

  test("no redacted value survives anywhere in the serialized output (anti-vacuity)", () => {
    // The per-field assertions above would all pass if `redactOrder` missed a
    // second copy of the same value elsewhere in the tree. Check the whole blob.
    const blob = JSON.stringify(red);
    for (const secret of [
      "1020304050",
      "+573001234567",
      "someone@example.com",
      "411111",
      "Calle 72",
    ]) {
      expect(blob).not.toContain(secret);
    }
  });

  test("a key containing dots or brackets cannot FORGE a printable path", () => {
    // Paths were built by string concatenation, so a key's own characters were
    // indistinguishable from a nesting boundary: a payload whose ROOT key was
    // literally named `shippingData.address.city` matched the allowlist and
    // printed. The allowlist failed open on the one direction it exists to
    // close. Segments are now matched one key at a time.
    const forged = redactOrder({
      "shippingData.address.city": "SECRET_CITY",
      "items[].name": "SECRET_NAME",
      items: [{ "additionalInfo.categories[].name": "SECRET_NESTED" }],
    }) as Record<string, unknown>;
    const blob = JSON.stringify(forged);
    for (const secret of ["SECRET_CITY", "SECRET_NAME", "SECRET_NESTED"]) {
      expect(blob).not.toContain(secret);
    }
  });

  test("a container where a scalar was expected is withheld whole", () => {
    // Every leaf path was also registered as its own ancestor, so a value that
    // arrived as an object or array at an allowlisted LEAF path got walked and
    // published its keys and its length. For a payload nobody has ever
    // observed, "documented as a scalar, actually a container" is a realistic
    // miss rather than a contrived one.
    const odd = redactOrder({
      orderId: ["a", "b", "c", "d", "e"],
      items: [{ seller: { secretA: 1, secretB: 2 } }],
    }) as Record<string, unknown>;
    expect(odd.orderId).toBe("[redacted]");
    expect((odd.items as Array<Record<string, unknown>>)[0]?.seller).toBe("[redacted]");
  });

  test("a key literally named `[]` cannot reach the array-element subtree", () => {
    // The array marker was stored in the same map as real JSON keys, so a
    // payload key named `[]` matched the marker and walked into the element
    // node's printable leaves — `items[].name`, `.ean`, `.id` all printed on the
    // DEFAULT path. The round-1 forgery defect, re-entered one edge over.
    const forged = redactOrder({
      orderId: "1234",
      items: {
        "[]": { name: "CEDULA 1020304050", ean: "Calle 100 #7-33", id: "4111111111111111" },
      },
      shippingData: { logisticsInfo: { "[]": { slas: { "[]": { name: "SECRET_SLA" } } } } },
    }) as Record<string, unknown>;
    const blob = JSON.stringify(forged);
    for (const secret of [
      "CEDULA 1020304050",
      "Calle 100 #7-33",
      "4111111111111111",
      "SECRET_SLA",
    ]) {
      expect(blob).not.toContain(secret);
    }
    // Still prints what it should, so this cannot pass by redacting everything.
    expect(forged.orderId).toBe("1234");
  });

  test("a container of the WRONG KIND is withheld whole, either way round", () => {
    // The scalar-path case was closed; these two were not. An array where an
    // object was expected published its LENGTH, and an object where an array was
    // expected published its KEY NAMES — the exact invariant the fix states.
    expect(
      (redactOrder({ shippingData: [1, 2, 3, 4, 5] }) as Record<string, unknown>).shippingData,
    ).toBe("[redacted]");
    expect(
      (redactOrder({ items: { cedula: "1", telefono: "2" } }) as Record<string, unknown>).items,
    ).toBe("[redacted]");
    // And a real array at a real array path still works.
    const ok = redactOrder({ items: [{ name: "LECHE" }, { name: "ARROZ" }] }) as {
      items: Array<{ name: string }>;
    };
    expect(ok.items.map((i) => i.name)).toEqual(["LECHE", "ARROZ"]);
  });

  test("a `__proto__` key is redacted in place, not silently dropped", () => {
    // Plain assignment set the prototype instead of defining an own property,
    // so the key vanished. No disclosure, but the output stopped being
    // obviously censored and became mysteriously incomplete.
    const out = redactOrder(JSON.parse('{"orderId":"1","__proto__":{"p":"YES"}}')) as Record<
      string,
      unknown
    >;
    expect(Object.hasOwn(out, "__proto__")).toBe(true);
    expect(JSON.stringify(out)).not.toContain("YES");
    expect((out as { polluted?: unknown }).polluted).toBeUndefined();
  });

  test("handles nulls and primitives without crashing, and still fails closed", () => {
    // `null` passes through: it discloses nothing, and turning it into the
    // string "[redacted]" would invent a value where the payload said none.
    expect(redactOrder(null)).toBeNull();
    expect(redactOrder({ document: null })).toEqual({ document: null });
    // A bare scalar or array at the root is not a known printable path, so it is
    // redacted rather than echoed. An order is always an object; anything else
    // arriving here is unrecognised, which is precisely when to say less.
    //
    // The array is withheld WHOLE. Mapping it element-by-element still
    // published how many elements there were, which is the same length leak
    // that `geoCoordinates` taught, on the one path with no allowlist at all.
    expect(redactOrder("plain")).toBe("[redacted]");
    expect(redactOrder([1, 2])).toBe("[redacted]");
  });
});

describe("orderForDisplay — the redaction DEFAULT is bound, not just available", () => {
  const ORDER = { clientProfileData: { document: "1020304050", firstName: "Ada" } };

  test("redacts by default", () => {
    // Replacing this selection with plain `detail` left all 155 tests green
    // while shipping national IDs to stdout — redactOrder was well tested, but
    // nothing bound it to the CLI's default.
    const out = JSON.stringify(orderForDisplay(ORDER, false));
    expect(out).not.toContain("1020304050");
    expect(out).toContain("[redacted]");
    // "Ada" used to survive here. Under the allowlist it does not, and the
    // orderId is what proves this selection is redaction rather than a blanket
    // refusal to print.
    expect(out).not.toContain("Ada");
    expect(JSON.stringify(orderForDisplay({ ...ORDER, orderId: "77-01" }, false))).toContain(
      "77-01",
    );
  });

  test("--raw opts in to the full payload", () => {
    expect(JSON.stringify(orderForDisplay(ORDER, true))).toContain("1020304050");
  });
});
