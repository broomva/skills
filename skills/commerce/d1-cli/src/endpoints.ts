/**
 * The single source of truth for which D1 endpoints this CLI may reach.
 *
 * Used twice, deliberately:
 *
 *   - **At runtime**, by `D1Client.request`, against the RESOLVED
 *     `URL.pathname` — after `new URL()` has collapsed any `..` segments.
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

import { D1Error } from "./types.ts";

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
  // location
  /^\/api\/checkout\/pub\/regions$/,
  // cart — builds and prices a basket; none of these settle it
  /^\/api\/checkout\/pub\/orderForm$/,
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
  "/api/checkout/pub/regions",
  "/api/checkout/pub/orderForm",
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

/** Whether a resolved pathname is one this CLI may request. */
export function isAllowedPath(pathname: string): boolean {
  return ALLOWED_ENDPOINT_PATTERNS.some((p) => p.test(pathname));
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
