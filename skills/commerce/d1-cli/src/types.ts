/**
 * Domain + wire types for the D1 (Tiendas D1, Colombia) storefront.
 *
 * D1 runs VTEX IO (account `d1tiendas`, workspace `master`), so the wire types
 * here are VTEX's public storefront shapes, narrowed to the fields we consume.
 * They are deliberately partial — VTEX payloads carry ~60 top-level keys and
 * pinning all of them would make every upstream addition a breaking change.
 */

/** VTEX account slug. Everything is scoped to this. */
export const ACCOUNT = "d1tiendas";
export const ORIGIN = "https://www.d1.com.co";

/**
 * Default sales channel (a.k.a. trade policy). D1 serves its public catalogue
 * on channel 1; the checkout API calls it `sc`, search calls it `trade-policy`.
 */
export const DEFAULT_SALES_CHANNEL = "1";

// ---------------------------------------------------------------------------
// Geography / regionalization
// ---------------------------------------------------------------------------

/** A WGS84 point. Note the field order — VTEX serializes lon before lat. */
export interface LatLng {
  lat: number;
  lng: number;
}

/** A physical D1 store that can fulfil orders for a region. */
export interface Seller {
  id: string;
  name: string;
}

/**
 * The result of resolving a delivery point to a fulfilment region.
 *
 * D1 scopes both availability and price by region: a catalogue query without a
 * region reports the national catalogue, which will happily list items that no
 * store near the customer can actually ship. Always resolve first.
 */
export interface Region {
  /** Opaque VTEX region id, e.g. `v2.574CC4356A93931779272F7A26AA8EB6`. */
  id: string;
  /** Physical stores serving the point. Empty means "D1 does not deliver here". */
  sellers: Seller[];
  /** The point this region was resolved from, echoed back for provenance. */
  at: LatLng;
}

// ---------------------------------------------------------------------------
// Catalogue
// ---------------------------------------------------------------------------

/**
 * A price in VTEX's integer representation: hundredths of the store currency.
 * D1 trades in COP, which has no minor unit in practice, so 350000 here is
 * COP 3,500 — not COP 350,000. Mixing the two up is the single easiest way to
 * misreport a basket by 100x, so prices never travel as bare numbers: see
 * `money.ts`.
 */
export type PriceHundredths = number;

export interface Offer {
  sellerId: string;
  sellerName: string;
  /** What the customer pays. */
  price: PriceHundredths;
  /** Pre-discount price. Equal to `price` when nothing is on offer. */
  listPrice: PriceHundredths;
  available: boolean;
  availableQuantity: number;
}

export interface Product {
  productId: string;
  skuId: string;
  name: string;
  brand: string;
  /** Slug used to build the public product URL. */
  linkText: string;
  categories: string[];
  offers: Offer[];
}

export interface SearchPage {
  products: Product[];
  /** Total matches upstream reports, which may exceed what pagination can reach. */
  total: number;
  /** True when `total` exceeded the depth the API will actually paginate. */
  truncated: boolean;
}

export interface FacetValue {
  key: string;
  value: string;
  label: string;
  quantity: number;
}

export interface Facet {
  key: string;
  label: string;
  values: FacetValue[];
}

export interface Category {
  id: string;
  name: string;
  slug: string;
  children: Category[];
}

export interface Suggestion {
  term: string;
  count: number;
}

// ---------------------------------------------------------------------------
// Cart
// ---------------------------------------------------------------------------

export interface CartItem {
  skuId: string;
  name: string;
  quantity: number;
  sellerId: string;
  /** Unit price actually being charged. */
  sellingPrice: PriceHundredths;
  /** `sellingPrice * quantity`, as computed upstream. */
  total: PriceHundredths;
  /**
   * Whether upstream currently offers a way to deliver this line.
   *
   * `undefined` when no delivery point has been set yet, so "not quoted" is
   * distinguishable from "quoted and refused". See `undeliverable()`.
   */
  deliverable?: boolean;
}

export interface ShippingOption {
  id: string;
  name: string;
  price: PriceHundredths;
  /** VTEX shipping estimate, e.g. `1bd` = one business day. */
  estimate: string;
}

export interface CartMessage {
  text: string;
  code: string;
  /** `error` means the cart is NOT safe to check out. */
  status: "error" | "warning" | "info";
}

export interface Cart {
  orderFormId: string;
  loggedIn: boolean;
  items: CartItem[];
  /** Item subtotal, before shipping and discounts. */
  itemsTotal: PriceHundredths;
  /**
   * Promotion total as reported by the `Discounts` totalizer. Negative when a
   * promotion applies (VTEX signs it as a reduction), 0 otherwise.
   */
  discounts: PriceHundredths;
  /** Grand total as computed upstream, including every totalizer. */
  total: PriceHundredths;
  shipping: ShippingOption[];
  /**
   * Notices from upstream. NOT all non-fatal: VTEX reports `cannotBeDelivered`
   * here with `status: "error"` while still returning SLAs and a payable total,
   * so severity has to travel with the text or a broken cart reads as ready.
   */
  messages: CartMessage[];
}

// ---------------------------------------------------------------------------
// Orders
// ---------------------------------------------------------------------------

export interface OrderSummary {
  orderId: string;
  /** VTEX status slug, e.g. `ready-for-handling`, `invoiced`, `canceled`. */
  status: string;
  statusLabel: string;
  creationDate: string;
  total: PriceHundredths;
  itemCount: number;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/** An error carrying enough context to tell a user what to do next. */
export class D1Error extends Error {
  constructor(
    message: string,
    readonly detail?: { status?: number; code?: string; url?: string },
  ) {
    super(message);
    this.name = "D1Error";
  }
}

/**
 * The caller invoked the CLI wrong — bad flags, missing arguments, malformed
 * input. Distinct from `D1Error` so it can exit 2 instead of 1.
 *
 * The distinction matters most to the agents this CLI is built for: exit 1
 * ("D1 said no, or is down") is worth retrying or backing off, while exit 2
 * ("you called this wrong") never is. Collapsing both into 1 leaves a caller
 * unable to tell a transient outage from a bug in its own argument
 * construction, so it retries forever or gives up on a typo.
 */
export class UsageError extends D1Error {
  constructor(message: string) {
    super(message);
    this.name = "UsageError";
  }
}
