import { describe, expect, test } from "bun:test";
import { D1Client } from "../src/client.ts";
import { formatCOP } from "../src/money.ts";
import { listOrders, redactOrder, statusLabel } from "../src/orders.ts";
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
    items: [{ id: "262", name: "LECHE", quantity: 2, sellingPrice: 350_000 }],
  };

  // Redaction replaces values with a string, so the redacted object is
  // deliberately NOT `typeof ORDER` — geoCoordinates goes number[] -> string.
  // biome-ignore lint/suspicious/noExplicitAny: assertions below are the schema
  const red = redactOrder(ORDER) as any;

  test("removes the national ID, phone and email", () => {
    expect(red.clientProfileData.document).toBe("[redacted]");
    expect(red.clientProfileData.documentType).toBe("[redacted]");
    expect(red.clientProfileData.phone).toBe("[redacted]");
    expect(red.clientProfileData.email).toBe("[redacted]");
  });

  test("removes the delivery address and coordinates, nested arbitrarily deep", () => {
    const a = red.shippingData.address;
    expect(a.street).toBe("[redacted]");
    expect(a.postalCode).toBe("[redacted]");
    expect(a.geoCoordinates).toBe("[redacted]");
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
    // Non-sensitive neighbours of redacted keys survive.
    expect(red.clientProfileData.firstName).toBe("Ada");
    expect(red.shippingData.address.city).toBe("Bogotá");
    expect(red.paymentData.transactions[0].payments[0].paymentSystemName).toBe("Visa");
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

  test("handles nulls and primitives without crashing", () => {
    expect(redactOrder(null)).toBeNull();
    expect(redactOrder({ document: null })).toEqual({ document: null });
    expect(redactOrder("plain")).toBe("plain");
    expect(redactOrder([1, 2])).toEqual([1, 2]);
  });
});
