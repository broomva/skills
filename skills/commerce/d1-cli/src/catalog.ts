/**
 * Catalogue reads: search, facets, suggestions, category tree.
 *
 * ## The unit trap
 *
 * D1's two catalogue APIs and its checkout API do not agree on what a price is.
 * For SKU 262 (Leche Entera Latti 900 ml, COP 3,500 on the shelf):
 *
 *   intelligent-search  Price = 3500      whole pesos
 *   catalog_system      Price = 3500.0    whole pesos
 *   checkout orderForm  sellingPrice = 350000   hundredths
 *
 * Both are "correct" in their own documentation and neither labels its unit.
 * Passing a search price into a checkout comparison — or the reverse — is a
 * silent factor-of-100 error that would still look like a plausible grocery
 * total, which is exactly what makes it dangerous.
 *
 * This module therefore normalizes **at the boundary**: everything it emits is
 * in hundredths, matching checkout, so the rest of the CLI has exactly one
 * unit. `test/catalog.test.ts` pins the invariant by checking a search-sourced
 * price against a cart-sourced price for the same SKU.
 */

import type { D1Client } from "./client.ts";
import { toHundredths } from "./money.ts";
import {
  type Category,
  D1Error,
  DEFAULT_SALES_CHANNEL,
  type Facet,
  type Offer,
  type Product,
  type SearchPage,
  type Suggestion,
} from "./types.ts";

/**
 * Deepest page the search API will serve. Asking for page 51 returns a 400
 * carrying "Page should not exceed 50 pages", so wide result sets have to be
 * narrowed by facet rather than paged through.
 */
export const MAX_PAGE = 50;
/** Largest page size the API accepts. */
export const MAX_COUNT = 50;

// ---------------------------------------------------------------------------
// Wire shapes (partial)
// ---------------------------------------------------------------------------

interface WireOffer {
  Price?: number;
  ListPrice?: number;
  AvailableQuantity?: number;
}
interface WireSeller {
  sellerId: string;
  sellerName?: string;
  commertialOffer?: WireOffer;
}
interface WireItem {
  itemId: string;
  name?: string;
  nameComplete?: string;
  sellers?: WireSeller[];
}
interface WireProduct {
  productId: string;
  productName?: string;
  brand?: string;
  linkText?: string;
  categories?: string[];
  items?: WireItem[];
}
interface WireSearch {
  products?: WireProduct[];
  recordsFiltered?: number;
}

// ---------------------------------------------------------------------------
// Normalization
// ---------------------------------------------------------------------------

/**
 * Convert a catalogue offer into the canonical hundredths representation.
 *
 * Availability is derived from `AvailableQuantity` because the catalogue
 * payload carries no `IsAvailable` flag — VTEX documents one, but D1's
 * responses omit it entirely, so trusting it would mark every product
 * unavailable.
 */
export function normalizeOffer(seller: WireSeller): Offer {
  const o = seller.commertialOffer ?? {};
  const qty = o.AvailableQuantity ?? 0;
  const price = toHundredths(o.Price ?? 0);
  const list = toHundredths(o.ListPrice ?? o.Price ?? 0);
  return {
    sellerId: seller.sellerId,
    sellerName: seller.sellerName || seller.sellerId,
    price,
    listPrice: list,
    available: qty > 0,
    availableQuantity: qty,
  };
}

/**
 * Flatten a VTEX product into one entry per SKU.
 *
 * A VTEX "product" can hold several SKUs (sizes, flavours). A shopper buys a
 * SKU, not a product, so the CLI's unit is the SKU — collapsing to the first
 * one would quietly hide variants.
 */
export function normalizeProduct(p: WireProduct): Product[] {
  const cats = (p.categories ?? []).map((c) => c.replace(/^\/|\/$/g, "")).filter(Boolean);
  return (p.items ?? []).map((item) => ({
    productId: p.productId,
    skuId: item.itemId,
    name: item.nameComplete || item.name || p.productName || "(unnamed)",
    brand: p.brand ?? "",
    linkText: p.linkText ?? "",
    categories: cats,
    offers: (item.sellers ?? []).map(normalizeOffer),
  }));
}

// ---------------------------------------------------------------------------
// Reads
// ---------------------------------------------------------------------------

export interface SearchOptions {
  query?: string;
  /** Facet path, e.g. `category-1/lacteos-y-huevos`. */
  facets?: string;
  /** 1-based. Capped at {@link MAX_PAGE}. */
  page?: number;
  /** Page size. Capped at {@link MAX_COUNT}. */
  count?: number;
  /** VTEX sort key, e.g. `price:asc`, `orders:desc`, `release:desc`. */
  sort?: string;
  /** Region id from `resolveRegion` — omit and prices are national, not local. */
  regionId?: string;
  salesChannel?: string;
  /** Drop products no seller can currently ship. */
  onlyAvailable?: boolean;
}

export async function search(client: D1Client, opts: SearchOptions = {}): Promise<SearchPage> {
  const page = clamp(opts.page ?? 1, 1, MAX_PAGE);
  const count = clamp(opts.count ?? 12, 1, MAX_COUNT);
  const channel = opts.salesChannel ?? DEFAULT_SALES_CHANNEL;
  // Kept on one line with a pre-computed suffix so the endpoint stays a simple
  // literal: `test/safety.test.ts` extracts every `/api/` path from the source
  // and checks it against an allowlist, and an interpolation spanning lines
  // (or containing quotes) would break that extraction into an unrecognizable
  // fragment — a check that silently stops seeing this endpoint.
  const facetPath = opts.facets ? encodeFacetPath(opts.facets) : "";
  const path = `/api/io/_v/api/intelligent-search/product_search/${facetPath}`;

  const wire = await client.request<WireSearch>(path, {
    query: {
      query: opts.query,
      page,
      count,
      sort: opts.sort,
      regionId: opts.regionId,
      "trade-policy": channel,
      hideUnavailableItems: opts.onlyAvailable ? "true" : undefined,
    },
  });

  let products = (wire.products ?? []).flatMap(normalizeProduct);
  if (opts.onlyAvailable) {
    products = products.filter((p) => p.offers.some((o) => o.available));
  }

  const total = wire.recordsFiltered ?? products.length;
  return { products, total, truncated: total > MAX_PAGE * count };
}

/**
 * Facet paths arrive as `key/value` segments and must stay segment-shaped in
 * the URL, so each segment is escaped individually — encoding the whole string
 * would turn the separators into `%2F` and the API would treat it as one
 * literal facet name.
 */
export function encodeFacetPath(facets: string): string {
  const segments = facets.split("/").filter(Boolean);
  // Reject traversal here as well as at the transport. `encodeURIComponent`
  // does NOT escape ".", so ".." survives into the path and `new URL()` then
  // resolves it — a facet argument really could climb out of the search
  // endpoint and land on order settlement. `client.ts` refuses that on the
  // resolved pathname; rejecting it here too means the user hears about the
  // argument they typed rather than about a URL they never saw.
  for (const seg of segments) {
    if (seg === "." || seg === "..") {
      throw new D1Error(`Facet path may not contain "${seg}" segments: ${facets}`);
    }
  }
  return segments.map(encodeURIComponent).join("/");
}

export async function facets(client: D1Client, opts: SearchOptions = {}): Promise<Facet[]> {
  const channel = opts.salesChannel ?? DEFAULT_SALES_CHANNEL;
  const wire = await client.request<{
    facets?: Array<{
      name?: string;
      key?: string;
      values?: Array<{
        key?: string;
        value?: string;
        name?: string;
        quantity?: number;
      }>;
    }>;
  }>(`/api/io/_v/api/intelligent-search/facets/trade-policy/${channel}`, {
    query: { query: opts.query, regionId: opts.regionId },
  });

  return (wire.facets ?? []).map((f) => ({
    key: f.key ?? f.name ?? "",
    label: f.name ?? f.key ?? "",
    values: (f.values ?? []).map((v) => ({
      key: v.key ?? "",
      value: v.value ?? "",
      label: v.name ?? v.value ?? "",
      quantity: v.quantity ?? 0,
    })),
  }));
}

export async function suggest(client: D1Client, query: string): Promise<Suggestion[]> {
  const wire = await client.request<{
    searches?: Array<{ term?: string; count?: number }>;
  }>("/api/io/_v/api/intelligent-search/autocomplete_suggestions", {
    query: { query },
  });
  return (wire.searches ?? []).map((s) => ({
    term: s.term ?? "",
    count: s.count ?? 0,
  }));
}

export async function topSearches(client: D1Client): Promise<Suggestion[]> {
  const wire = await client.request<{
    searches?: Array<{ term?: string; count?: number }>;
  }>("/api/io/_v/api/intelligent-search/top_searches");
  return (wire.searches ?? []).map((s) => ({
    term: s.term ?? "",
    count: s.count ?? 0,
  }));
}

interface WireCategory {
  id: number | string;
  name: string;
  url?: string;
  children?: WireCategory[];
}

export async function categoryTree(client: D1Client, depth = 2): Promise<Category[]> {
  const wire = await client.request<WireCategory[]>(
    `/api/catalog_system/pub/category/tree/${clamp(depth, 1, 5)}`,
  );
  const map = (c: WireCategory): Category => ({
    id: String(c.id),
    name: c.name,
    slug: slugFromUrl(c.url) || slugify(c.name),
    children: (c.children ?? []).map(map),
  });
  return (wire ?? []).map(map);
}

function slugFromUrl(url?: string): string {
  if (!url) return "";
  try {
    return new URL(url).pathname.split("/").filter(Boolean).pop() ?? "";
  } catch {
    return "";
  }
}

/** Accent-stripping slugifier — D1's category slugs are unaccented ASCII. */
export function slugify(s: string): string {
  return s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, Math.trunc(n)));
}
