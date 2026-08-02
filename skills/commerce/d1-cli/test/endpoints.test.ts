import { describe, expect, test } from "bun:test";
import { encodeFacetPath } from "../src/catalog.ts";
import { D1Client } from "../src/client.ts";
import {
  ALLOWED_ENDPOINT_PATTERNS,
  ALLOWED_ENDPOINT_SHAPES,
  isAllowedPath,
} from "../src/endpoints.ts";
import { D1Error } from "../src/types.ts";

describe("the runtime endpoint guard", () => {
  test("admits every endpoint the CLI actually uses", () => {
    for (const p of [
      "/api/io/_v/api/intelligent-search/product_search/",
      "/api/io/_v/api/intelligent-search/product_search/category-1/lacteos",
      "/api/io/_v/api/intelligent-search/facets/trade-policy/1",
      "/api/io/_v/api/intelligent-search/autocomplete_suggestions",
      "/api/io/_v/api/intelligent-search/top_searches",
      "/api/catalog_system/pub/category/tree/3",
      "/api/checkout/pub/regions",
      "/api/checkout/pub/orderForm",
      "/api/checkout/pub/orderForm/OF1/items",
      "/api/checkout/pub/orderForm/OF1/items/update",
      "/api/checkout/pub/orderForm/OF1/items/removeAll",
      "/api/checkout/pub/orderForm/OF1/attachments/shippingData",
      "/api/checkout/pub/orderForms/simulation",
      "/api/vtexid/pub/authentication/start",
      "/api/vtexid/pub/authentication/accesskey/send",
      "/api/vtexid/pub/authentication/accesskey/validate",
      "/api/vtexid/pub/authenticated/user",
      "/api/oms/user/orders",
      "/api/oms/user/orders/123-01",
    ]) {
      expect(isAllowedPath(p)).toBe(true);
    }
  });

  test("refuses the endpoints that move money", () => {
    for (const p of [
      "/api/checkout/pub/orderForm/OF1/transaction",
      "/api/checkout/pub/orderForm/OF1/attachments/paymentData",
      "/api/pub/transactions/OF1/payments",
      "/api/pmt/transaction/T1/payments",
      "/api/checkout/pub/gatewayCallback/OF1",
    ]) {
      expect(isAllowedPath(p)).toBe(false);
    }
  });

  test("no pattern admits a payment path (guards the list itself)", () => {
    // So that adding an entry carelessly trips here rather than shipping.
    for (const p of ALLOWED_ENDPOINT_PATTERNS) {
      expect(p.source).not.toMatch(/payment|transaction|gatewayCallback/i);
    }
  });

  test("the static shapes and the runtime patterns cannot drift apart", () => {
    // Every shape the source scan approves must be admitted by a runtime
    // pattern; otherwise a literal could pass the static check and be refused
    // at runtime, or worse, the reverse.
    for (const shape of ALLOWED_ENDPOINT_SHAPES) {
      expect(isAllowedPath(shape.replace(/\{\}/g, "SEG"))).toBe(true);
    }
    expect(ALLOWED_ENDPOINT_SHAPES.length).toBe(18);
  });
});

describe("path traversal cannot escape an endpoint", () => {
  /** Records the URL a request would have gone to; never actually fetches. */
  function spy() {
    const seen: string[] = [];
    const impl = (async (url: string) => {
      seen.push(new URL(String(url)).pathname);
      return new Response("{}", { status: 200 });
    }) as unknown as typeof fetch;
    return { impl, seen };
  }

  test("a `..` facet path that resolves onto order settlement is REFUSED", async () => {
    // Verified reachable before this guard existed: every string literal in the
    // source was approved, and the request still landed on the endpoint VTEX
    // uses to settle an order.
    const { impl, seen } = spy();
    const client = new D1Client({ fetchImpl: impl, authToken: "tok" });
    const evil =
      "/api/io/_v/api/intelligent-search/product_search/../../../../../../api/checkout/pub/orderForm/OF1/transaction";

    expect(new URL(evil, "https://www.d1.com.co").pathname).toBe(
      "/api/checkout/pub/orderForm/OF1/transaction",
    );
    await expect(client.request(evil)).rejects.toThrow(/not an approved D1 endpoint/);
    expect(seen).toHaveLength(0); // refused BEFORE anything left the process
  });

  test("the refusal names the traversal so it is diagnosable", async () => {
    const { impl } = spy();
    const client = new D1Client({ fetchImpl: impl });
    await expect(
      client.request("/api/oms/user/orders/../../../api/checkout/pub/orderForm/X/transaction"),
    ).rejects.toThrow(/path traversal resolved it elsewhere/);
  });

  test("an approved path still goes through (anti-overshoot control)", async () => {
    // The paired control: a guard that refuses everything would pass the tests
    // above while breaking the CLI.
    const { impl, seen } = spy();
    const client = new D1Client({ fetchImpl: impl });
    await client.request("/api/checkout/pub/regions");
    expect(seen).toEqual(["/api/checkout/pub/regions"]);
  });

  test("encodeFacetPath rejects traversal segments at the argument boundary", () => {
    expect(() => encodeFacetPath("../../etc")).toThrow(D1Error);
    expect(() => encodeFacetPath("a/./b")).toThrow(D1Error);
    // and still does its actual job
    expect(encodeFacetPath("category-1/lacteos-y-huevos")).toBe("category-1/lacteos-y-huevos");
  });
});
