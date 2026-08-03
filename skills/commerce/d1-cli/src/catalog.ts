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
import { parseUnitSize, unitPrice } from "./measure.ts";
import { toHundredths } from "./money.ts";
import {
  type Category,
  DEFAULT_SALES_CHANNEL,
  type Facet,
  type Offer,
  type Product,
  type SearchPage,
  type Suggestion,
  UsageError,
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
interface WireProperty {
  name?: string;
  values?: string[];
}
interface WireProduct {
  productId: string;
  properties?: WireProperty[];
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

/**
 * The same product as `catalog_system` serves it.
 *
 * A third way these two APIs disagree, after the price unit and the missing
 * `IsAvailable` flag: the properties `intelligent-search` nests under
 * `properties[]` are TOP-LEVEL keys here, so `Unidad De Medida` and
 * `Exceso en sodio` arrive as `string[]` values on the product itself.
 */
interface WireCatalogProduct {
  productId: string;
  productName?: string;
  brand?: string;
  linkText?: string;
  categories?: string[];
  items?: WireItem[];
  [property: string]: unknown;
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

  // D1 publishes the legally-required unit-of-measure pair, and Colombia's
  // front-of-pack warning labels, as flat product properties.
  const props = new Map<string, string[]>();
  for (const pr of p.properties ?? []) {
    if (pr.name) props.set(pr.name, pr.values ?? []);
  }
  const size = parseUnitSize(props.get("Unidad De Medida")?.[0], props.get("Valor de Medida")?.[0]);
  const warnings = [...props.entries()]
    .filter(([k, v]) => /^(Exceso|Contiene)/i.test(k) && v[0]?.toLowerCase() === "si")
    .map(([k]) => k);

  return (p.items ?? []).map((item) => {
    const offers = (item.sellers ?? []).map(normalizeOffer);
    // `pickOffer`, not a second inline rule. Two predicates for "which offer
    // represents this product" diverged exactly where it mattered: this one
    // fell back to offers[0] while `bestOffer` fell back to the cheapest, so a
    // product with nothing in stock — the case `substitute` exists for — could
    // print a pack price from one seller beside a $/L derived from another.
    const best = pickOffer(offers);
    return {
      productId: p.productId,
      skuId: item.itemId,
      name: item.nameComplete || item.name || p.productName || "(unnamed)",
      brand: p.brand ?? "",
      linkText: p.linkText ?? "",
      categories: cats,
      offers,
      size,
      // A unit price derived from a non-price is not a unit price. Guarding at
      // the root rather than at each renderer means `$ 0/kg` cannot reappear
      // the next time something reads this field.
      unitPrice: priced(best) ? unitPrice(best.price, size) : undefined,
      warnings,
    };
  });
}

/**
 * The cheapest available offer, or the cheapest offer overall when nothing is
 * in stock — so an out-of-stock product still shows what it would cost.
 *
 * Lives here rather than in `present.ts` (which re-exports it) because picking
 * which of several sellers' offers represents a product is a catalogue
 * decision, not a rendering one: `substitute.ts` compares prices without
 * rendering anything.
 */
export function pickOffer(offers: readonly Offer[]): Offer | undefined {
  const available = offers.filter((o) => o.available);
  const pool = available.length ? available : offers;
  return pool.slice().sort((a, b) => a.price - b.price)[0];
}

export function bestOffer(p: Product): Offer | undefined {
  return pickOffer(p.offers);
}

/**
 * Whether an offer carries a real price.
 *
 * VTEX reports `Price: 0` for a product it has no offer for in this region or
 * channel. That does not mean free — no grocery item is — and treating it as a
 * number produces two distinct lies. Observed live on SKU 1687 (`SALCHICHA
 * PARRILLA MINI VIANDE`, out of stock at the Bogotá region):
 *
 *   d1 search        →  $ 0        $ 0/kg     out of stock
 *   d1 substitute    →  $ 0/kg → $ 40.435/kg      ← a price rise from nothing
 *
 * The second is the worse one: a comparison against a non-price is not a
 * comparison, and it renders as a concrete claim about what a swap costs.
 */
export function priced(o: Offer | undefined): o is Offer {
  return o !== undefined && o.price > 0;
}

/**
 * Reject anything that is not a bare SKU id.
 *
 * `fq` is a query language, not a value slot — `skuId:262 OR productId:1` is a
 * legal filter — so an unconstrained argument does not narrow the catalogue,
 * it rewrites the question, and the answer still arrives as HTTP 200 with
 * plausible products in it. D1 issues decimal integer ids, so requiring one
 * closes the entire grammar without refusing anything real.
 */
export function assertSkuId(skuId: string): void {
  if (!/^\d+$/.test(skuId)) {
    throw new UsageError(
      `SKU must be a number, got "${skuId}". Find one in the first column of \`d1 search\`.`,
    );
  }
}

/**
 * Reshape a `catalog_system` product into the search shape, so both paths go
 * through `normalizeProduct`.
 *
 * A second normalizer would drift, and the drift is silent: a pack size parsed
 * on one path and not the other gives a product that can be compared per-unit
 * through search and cannot through here — which reads as "D1 publishes no
 * size for this one" rather than as a bug.
 */
function asSearchShape(p: WireCatalogProduct): WireProduct {
  const properties: WireProperty[] = [];
  for (const [name, value] of Object.entries(p)) {
    if (Array.isArray(value) && value.every((v) => typeof v === "string")) {
      properties.push({ name, values: value as string[] });
    }
  }
  return {
    productId: p.productId,
    productName: p.productName,
    brand: p.brand,
    linkText: p.linkText,
    categories: p.categories,
    items: p.items,
    properties,
  };
}

/**
 * Find the product carrying a given SKU.
 *
 * This is the only route from a SKU id to its category, and it has to be the
 * legacy catalogue API: `intelligent-search` has no SKU filter at all. Passing
 * it `?fq=skuId:262` returns **the entire catalogue** — 1,600 products, HTTP
 * 200 — because it ignores the parameter rather than rejecting it, and
 * `product_search/skuId/262` as a facet path returns nothing.
 *
 * Prices here are NATIONAL: this endpoint takes no region. Callers that need a
 * regional price re-read the product through {@link search}, which does.
 */
export async function productBySku(
  client: D1Client,
  skuId: string,
  opts: { salesChannel?: string } = {},
): Promise<Product | undefined> {
  assertSkuId(skuId);
  const wire = await client.request<WireCatalogProduct[]>(
    "/api/catalog_system/pub/products/search",
    { query: { fq: `skuId:${skuId}`, sc: opts.salesChannel ?? DEFAULT_SALES_CHANNEL } },
  );

  for (const p of Array.isArray(wire) ? wire : []) {
    // Match the ITEM, never `items[0]`.
    //
    // SKU ids and product ids are different id spaces at D1 and they OVERLAP.
    // SKU 1686 belongs to product 1687; ask for skuId 1687 and you get product
    // 1688 — `SALCHICHA PARRILLA MINI VIANDE`, where you asked about potato
    // crisps. One result, HTTP 200, entirely the wrong grocery item. Only
    // checking the item id makes that visible.
    const match = normalizeProduct(asSearchShape(p)).find((x) => x.skuId === skuId);
    if (match) return match;
  }
  return undefined;
}

/**
 * The deepest of the category paths a product declares.
 *
 * D1 lists every ancestor alongside the leaf — `Lacteos y huevos/Leches/Entera`
 * arrives with `Lacteos y huevos/Leches` and `Lacteos y huevos` — and the leaf
 * is the one that describes the product rather than the aisle.
 */
export function deepestCategory(categories: string[]): string | undefined {
  let best: string | undefined;
  let depth = 0;
  for (const c of categories) {
    const d = c.split("/").filter((s) => s.trim()).length;
    // Ties break on the path itself, not on upstream array order. D1 can
    // publish two equally-deep paths (a merchandising tree and an aisle tree),
    // and nothing documents which comes first — so first-wins would silently
    // change which category gets swept between identical runs.
    if (d > depth || (d === depth && best !== undefined && c < best)) {
      depth = d;
      best = c;
    }
  }
  return best;
}

/**
 * Turn a category NAME path into the SLUG facet path search takes.
 *
 * The two APIs disagree here too: products carry `Lacteos y huevos/Leches/Entera`
 * while search wants `category-1/lacteos-y-huevos/category-2/leches/category-3/entera`.
 * Verified live that the slugified names round-trip, at every depth.
 *
 * A wrong slug fails CLOSED — an unrecognized leaf returns 0 products rather
 * than widening to its parent — which is what lets a caller walk up the path
 * and trust that a level returning nothing really is empty.
 */
export function categoryFacetPath(categoryPath: string, depth?: number): string {
  const names = categoryPath
    .split("/")
    .map((s) => s.trim())
    .filter(Boolean);
  const wanted = depth === undefined ? names.length : Math.max(1, Math.trunc(depth));
  const out: string[] = [];
  for (const name of names.slice(0, wanted)) {
    const slug = slugify(name);
    // Stop rather than emit `category-2/` — an empty segment collapses the path
    // and would silently search a DIFFERENT, broader category than the caller
    // asked for. A shorter honest path is the safe way for this to be wrong.
    if (!slug) break;
    out.push(`category-${out.length + 1}/${slug}`);
  }
  return out.join("/");
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
      // `per-unit` is ours, not D1's — never forward it upstream.
      sort: opts.sort === "per-unit" ? undefined : opts.sort,
      regionId: opts.regionId,
      "trade-policy": channel,
      hideUnavailableItems: opts.onlyAvailable ? "true" : undefined,
    },
  });

  let products = (wire.products ?? []).flatMap(normalizeProduct);
  if (opts.onlyAvailable) {
    products = products.filter((p) => p.offers.some((o) => o.available));
  }

  if (opts.sort === "per-unit") {
    // Sorted here, not upstream: D1's search has no unit-price sort, and the
    // data needed lives in product properties rather than any sortable index.
    // So this orders the page you fetched, NOT the whole result set —
    // `renderSearch` says so, because a "cheapest" claim over a partial set
    // would be false.
    //
    // Grouped by MEASURE first. $/kg, $/L and $/unit are not comparable
    // quantities, and interleaving them produces nonsense: a search for oil
    // ranked a $8,900 *bottle* ("/unit") in among the $/L figures as though it
    // were a competitive buy. Products sharing the measure that dominates the
    // result set come first, in unit-price order; other measures follow in
    // their own order; sizeless products last.
    const counts = new Map<string, number>();
    for (const p of products) {
      if (p.size) counts.set(p.size.measure, (counts.get(p.size.measure) ?? 0) + 1);
    }
    const dominant = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    const rank = (p: Product) =>
      p.unitPrice === undefined ? 2 : p.size?.measure === dominant ? 0 : 1;
    products = products
      .slice()
      .sort((a, b) => rank(a) - rank(b) || (a.unitPrice ?? 0) - (b.unitPrice ?? 0));
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
      throw new UsageError(`Facet path may not contain "${seg}" segments: ${facets}`);
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
  }>(`/api/io/_v/api/intelligent-search/facets/trade-policy/${encodeURIComponent(channel)}`, {
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
