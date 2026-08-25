import { call } from "./client.ts";
import { DEFAULTS } from "./constants.ts";
import { extractItems, type Item } from "./parse.ts";
import { registry } from "./ops.ts";

const shopVars = () => ({
  shopId: DEFAULTS.shopId,
  postalCode: DEFAULTS.postalCode,
  zoneId: DEFAULTS.zoneId,
});

/** A stable id for this client's requests. The API expects one; its value is not meaningful. */
const pageViewId = () => crypto.randomUUID();

/** Items in a named collection (e.g. the on-sale collection behind `deals`). */
export async function collection(slug: string, limit = 30): Promise<Item[]> {
  const data = await call("CollectionProductsWithFeaturedProducts", {
    ...shopVars(),
    slug,
    filters: [],
    pageViewId: pageViewId(),
    itemsDisplayType: "collections_storefront",
    first: limit,
    pageSource: "storefront",
  });
  return extractItems(data);
}

/** Browsable collections from the store's department navigation. */
export async function saleCollections(): Promise<{ slug: string; name: string }[]> {
  const data: any = await call("DepartmentNavCollections", {
    includeSlugs: ["dynamic_collection-sales"],
    shopId: DEFAULTS.shopId,
    postalCode: DEFAULTS.postalCode,
  });
  const out: { slug: string; name: string }[] = [];
  const walk = (o: any) => {
    if (!o || typeof o !== "object") return;
    if (Array.isArray(o)) return o.forEach(walk);
    if (typeof o.slug === "string" && typeof o.name === "string") {
      out.push({ slug: o.slug, name: o.name });
    }
    Object.values(o).forEach(walk);
  };
  walk(data);
  return out.filter((c, i, a) => a.findIndex((x) => x.slug === c.slug) === i);
}

export type DealOptions = { minOff?: number; limit?: number; slug?: string };

export async function deals(opts: DealOptions = {}): Promise<Item[]> {
  const slug = opts.slug ?? "rc-on-sale-recommended-for-you";
  const items = await collection(slug, opts.limit ?? 30);
  const min = opts.minOff ?? 0;
  return items
    .filter((i) => (i.percentOff ?? 0) >= min || (min === 0 && i.offerLabel))
    .sort((a, b) => (b.percentOff ?? 0) - (a.percentOff ?? 0));
}

/**
 * Search.
 *
 * Search results are fetched client-side, so no search operation appears in any SSR
 * payload and its hash cannot ship with this package. Once harvested, it is used here.
 * Until then this falls back to filtering the collections we *can* reach, and says so —
 * a local filter over one collection is not a store-wide search, and pretending otherwise
 * would silently return "no results" for items that are plainly in stock.
 */
export type SearchResult = { items: Item[]; degraded: boolean; searchedCollection?: string };

const SEARCH_OP_CANDIDATES = ["SearchResultsPlacements", "SearchResults", "CrossRetailerSearch"];

export async function search(term: string, limit = 25): Promise<SearchResult> {
  const reg = await registry();
  const opName = SEARCH_OP_CANDIDATES.find((n) => reg[n]);

  if (opName) {
    const data = await call(opName, {
      ...shopVars(),
      query: term,
      first: limit,
      pageViewId: pageViewId(),
    });
    return { items: extractItems(data), degraded: false };
  }

  const slug = "rc-on-sale-recommended-for-you";
  const pool = await collection(slug, 60);
  const t = term.toLowerCase();
  const items = pool
    .filter((i) => i.name.toLowerCase().includes(t) || (i.brand ?? "").toLowerCase().includes(t))
    .slice(0, limit);
  return { items, degraded: true, searchedCollection: slug };
}
