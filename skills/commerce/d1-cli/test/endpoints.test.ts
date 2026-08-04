import { describe, expect, test } from "bun:test";
import { encodeFacetPath } from "../src/catalog.ts";
import { D1Client, USER_AGENT } from "../src/client.ts";
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
      "/api/checkout/pub/orderForm/OF1",
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
    // Bumped from 19 to 20 by `catalog_system/pub/products/search` (SKU lookup
    // for `d1 substitute`), and from 20 to 21 by `checkout/pub/pickup-points`
    // (the store locator for `d1 stores near` — a READ of public shop addresses
    // and hours, carrying nothing customer-scoped and settling nothing).
    // The count is here so that widening the CLI's reach upstream cannot happen
    // as a side effect of a feature — it has to be typed out, in a file whose
    // whole subject is the payment boundary.
    expect(ALLOWED_ENDPOINT_SHAPES.length).toBe(21);
    // ...but a COUNT only sees entries appear, never an existing one loosen.
    // Widening `/products/search$/` to `/pub/.*/` is a one-character-class edit
    // that leaves the length at 20 and every shape still matching its own
    // pattern — the whole `catalog_system` surface admitted, invisibly. So the
    // patterns are pinned by source, which is the property actually claimed.
    expect(ALLOWED_ENDPOINT_PATTERNS.map((p) => p.source)).toEqual([
      "^\\/api\\/io\\/_v\\/api\\/intelligent-search\\/product_search(\\/[^/]+)*\\/?$",
      "^\\/api\\/io\\/_v\\/api\\/intelligent-search\\/facets\\/trade-policy\\/[^/]+$",
      "^\\/api\\/io\\/_v\\/api\\/intelligent-search\\/autocomplete_suggestions$",
      "^\\/api\\/io\\/_v\\/api\\/intelligent-search\\/top_searches$",
      "^\\/api\\/catalog_system\\/pub\\/category\\/tree\\/[^/]+$",
      "^\\/api\\/catalog_system\\/pub\\/products\\/search$",
      "^\\/api\\/checkout\\/pub\\/regions$",
      "^\\/api\\/checkout\\/pub\\/pickup-points$",
      "^\\/api\\/checkout\\/pub\\/orderForm$",
      "^\\/api\\/checkout\\/pub\\/orderForm\\/[^/]+$",
      "^\\/api\\/checkout\\/pub\\/orderForm\\/[^/]+\\/items$",
      "^\\/api\\/checkout\\/pub\\/orderForm\\/[^/]+\\/items\\/update$",
      "^\\/api\\/checkout\\/pub\\/orderForm\\/[^/]+\\/items\\/removeAll$",
      "^\\/api\\/checkout\\/pub\\/orderForm\\/[^/]+\\/attachments\\/shippingData$",
      "^\\/api\\/checkout\\/pub\\/orderForms\\/simulation$",
      "^\\/api\\/vtexid\\/pub\\/authentication\\/start$",
      "^\\/api\\/vtexid\\/pub\\/authentication\\/accesskey\\/send$",
      "^\\/api\\/vtexid\\/pub\\/authentication\\/accesskey\\/validate$",
      "^\\/api\\/vtexid\\/pub\\/authenticated\\/user$",
      "^\\/api\\/oms\\/user\\/orders\\/?$",
      "^\\/api\\/oms\\/user\\/orders\\/[^/]+$",
    ]);
    // Bidirectional: a pattern added without a shape would otherwise be
    // invisible to the static source scan.
    expect(ALLOWED_ENDPOINT_PATTERNS.length).toBe(ALLOWED_ENDPOINT_SHAPES.length);
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

describe("a query-language endpoint is constrained by its query, not just its path", () => {
  function spy() {
    const seen: string[] = [];
    const impl = (async (url: string) => {
      seen.push(String(url));
      return new Response("[]", { status: 200 });
    }) as unknown as typeof fetch;
    return { impl, seen };
  }

  const SEARCH = "/api/catalog_system/pub/products/search";

  test("an arbitrary fq is REFUSED, even though the path is approved", async () => {
    // Every allowlist entry before this one carried its risk in the PATH. `fq`
    // is a query language — `C:/1/`, `alternateIds_RefId:x`, `P:[0 TO 9999]`
    // all reach the same approved path — so an approved pathname says nothing
    // about what was asked for. `assertSkuId` guards the one caller that exists
    // today; a second call site would inherit the path and none of the
    // constraint. Proven by planting exactly that caller: it sailed through the
    // static source scan and reached D1 with the session cookie attached.
    const { impl, seen } = spy();
    const client = new D1Client({ fetchImpl: impl, authToken: "tok" });
    for (const fq of [
      "C:/1/",
      "alternateIds_RefId:x",
      "P:[0 TO 9999]",
      "skuId:262 OR productId:1",
    ]) {
      await expect(client.request(SEARCH, { query: { fq } })).rejects.toThrow(/must match/);
    }
    expect(seen).toHaveLength(0);
  });

  test("the whole-catalogue paging levers are refused as UNKNOWN parameters", async () => {
    // `_from`/`_to` are the enumeration levers, and neither would have tripped
    // a check that only validated `fq`. Unknown params fail closed.
    const { impl, seen } = spy();
    const client = new D1Client({ fetchImpl: impl });
    await expect(
      client.request(SEARCH, { query: { fq: "skuId:262", _from: 0, _to: 2500 } }),
    ).rejects.toThrow(/accepts only/);
    expect(seen).toHaveLength(0);
  });

  test("the legitimate SKU lookup still goes through (anti-overshoot control)", async () => {
    // Without this, a guard that refused everything would pass the two above.
    const { impl, seen } = spy();
    const client = new D1Client({ fetchImpl: impl });
    await client.request(SEARCH, { query: { fq: "skuId:262", sc: "1" } });
    expect(seen).toHaveLength(1);
    expect(new URL(seen[0]).searchParams.get("fq")).toBe("skuId:262");
  });

  test("a prototype-chain key raises a D1Error, not an uncaught TypeError", async () => {
    // `guard.params[key]` resolved `constructor` / `toString` / `valueOf` up
    // the prototype chain to functions, which are truthy — so the next line
    // called `.test` on one. Still fail-closed, but through the wrong error
    // class, which means the wrong exit code and a stack trace instead of a
    // sentence.
    const { impl, seen } = spy();
    const client = new D1Client({ fetchImpl: impl });
    for (const key of ["constructor", "toString", "valueOf", "__proto__", "hasOwnProperty"]) {
      await expect(
        client.request(SEARCH, { query: { fq: "skuId:262", [key]: "x" } }),
      ).rejects.toThrow(D1Error);
    }
    expect(seen).toHaveLength(0);
  });

  test("an unguarded endpoint is unconstrained, as before", async () => {
    const { impl, seen } = spy();
    const client = new D1Client({ fetchImpl: impl });
    await client.request("/api/io/_v/api/intelligent-search/autocomplete_suggestions", {
      query: { query: "anything at all" },
    });
    expect(seen).toHaveLength(1);
  });
});

describe("the session cookie cannot leave D1's origin", () => {
  function spy() {
    const seen: string[] = [];
    const impl = (async (url: string) => {
      seen.push(String(url));
      return new Response("{}", { status: 200 });
    }) as unknown as typeof fetch;
    return { impl, seen };
  }

  test("a protocol-relative path keeps an APPROVED pathname but changes host", () => {
    // Why pathname-only checking is insufficient, stated as the premise of the
    // test rather than assumed: this is an approved path on a foreign host.
    const u = new URL("//evil.example/api/checkout/pub/regions", "https://www.d1.com.co");
    expect(u.host).toBe("evil.example");
    expect(isAllowedPath(u.pathname)).toBe(true);
  });

  test("...and is refused before anything is sent", async () => {
    const { impl, seen } = spy();
    const client = new D1Client({ fetchImpl: impl, authToken: "SECRET" });
    await expect(client.request("//evil.example/api/checkout/pub/regions")).rejects.toThrow(
      /only talks to https:\/\/www\.d1\.com\.co/,
    );
    expect(seen).toHaveLength(0);
  });

  test("an absolute foreign URL is refused too", async () => {
    const { impl, seen } = spy();
    const client = new D1Client({ fetchImpl: impl, authToken: "SECRET" });
    await expect(client.request("https://evil.example/api/checkout/pub/regions")).rejects.toThrow(
      /only talks to/,
    );
    expect(seen).toHaveLength(0);
  });

  test("the real origin still goes through (anti-overshoot control)", async () => {
    const { impl, seen } = spy();
    await new D1Client({ fetchImpl: impl }).request("/api/checkout/pub/regions");
    expect(seen[0]).toStartWith("https://www.d1.com.co/api/checkout/pub/regions");
  });
});

describe("the user agent names the version this actually is", () => {
  test("it tracks package.json rather than a literal that drifts", async () => {
    // It was a literal, and it said 0.1.0 while the package said 0.7.0 — seven
    // releases of telling D1 something confident and false. Bound to the
    // manifest here so the next bump cannot silently leave it behind.
    const pkg = (await import("../package.json")) as unknown as { default: { version: string } };
    expect(USER_AGENT).toContain(`d1-cli/${pkg.default.version}`);
    expect(USER_AGENT).not.toContain("0.1.0");
  });

  test("it is the header actually sent, not merely a constant", async () => {
    // The constant being right proves nothing about the request. This is the
    // same lesson `orderForDisplay` taught: a well-tested value that nothing
    // binds to the wire is a value nobody sends.
    let sent = "";
    const c = new D1Client({
      fetchImpl: (async (_u: string, init: RequestInit) => {
        sent = new Headers(init?.headers).get("user-agent") ?? "";
        return new Response("{}", { status: 200 });
      }) as unknown as typeof fetch,
    });
    await c.request("/api/io/_v/api/intelligent-search/product_search", { query: { query: "x" } });
    expect(sent).toBe(USER_AGENT);
  });
});
