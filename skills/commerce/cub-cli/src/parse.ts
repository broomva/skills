/**
 * Response → normalized items.
 *
 * The GraphQL responses are deeply nested view-model trees ("viewSection" everywhere),
 * and the same item shape shows up under many different collection wrappers. Rather than
 * encode a path per operation, walk the tree and pick out nodes that look like items.
 */

export type Item = {
  productId: string;
  itemId: string | null;
  name: string;
  size: string | null;
  brand: string | null;
  /** Current shelf price in cents, or null when the response carried no parseable price. */
  priceCents: number | null;
  /** Pre-discount price in cents, when the item is on offer. */
  fullPriceCents: number | null;
  priceLabel: string | null;
  fullPriceLabel: string | null;
  unitPriceLabel: string | null;
  /** e.g. "57% off", "Buy 2 for $6" */
  offerLabel: string | null;
  /** Percent off, derived from prices when both are known. */
  percentOff: number | null;
  url: string | null;
};

/** "$2.99" → 299. Returns null for non-numeric labels like "Buy 2 for $6". */
export function parsePriceCents(label: string | null | undefined): number | null {
  if (!label) return null;
  // Require the price to be the whole label, so multi-buy copy doesn't read as a unit price.
  const m = /^\s*\$?\s*(\d+(?:\.\d{1,2})?)\s*$/.exec(label.replace(/,/g, ""));
  if (!m) return null;
  return Math.round(Number.parseFloat(m[1]) * 100);
}

function isItemNode(o: any): boolean {
  return (
    o &&
    typeof o === "object" &&
    typeof o.name === "string" &&
    typeof o.productId === "string" &&
    "size" in o
  );
}

type PriceBits = {
  priceLabel: string | null;
  fullPriceLabel: string | null;
  unitPriceLabel: string | null;
  offerLabel: string | null;
};

function priceOf(node: any): PriceBits {
  const out: PriceBits = {
    priceLabel: null,
    fullPriceLabel: null,
    unitPriceLabel: null,
    offerLabel: null,
  };
  const walk = (o: any) => {
    if (!o || typeof o !== "object") return;
    if (Array.isArray(o)) {
      for (const v of o) walk(v);
      return;
    }
    if (o.__typename === "ItemsItemPrice") {
      const vs = o.viewSection ?? {};
      out.priceLabel ??= vs.priceString ?? null;
      out.fullPriceLabel ??= vs.fullPriceString ?? null;
      out.unitPriceLabel ??= vs.pricePerUnitString ?? null;
      out.offerLabel ??= vs.badge?.offerLabelString ?? null;
    }
    for (const v of Object.values(o)) walk(v);
  };
  walk(node);
  return out;
}

export function extractItems(data: unknown): Item[] {
  const found: any[] = [];
  const walk = (o: any) => {
    if (!o || typeof o !== "object") return;
    if (Array.isArray(o)) {
      for (const v of o) walk(v);
      return;
    }
    if (isItemNode(o)) found.push(o);
    for (const v of Object.values(o)) walk(v);
  };
  walk(data);

  const byId = new Map<string, Item>();
  for (const node of found) {
    if (byId.has(node.productId)) continue;
    const p = priceOf(node);
    const priceCents = parsePriceCents(p.priceLabel);
    const fullPriceCents = parsePriceCents(p.fullPriceLabel);
    let percentOff: number | null = null;
    if (priceCents !== null && fullPriceCents !== null && fullPriceCents > priceCents) {
      percentOff = Math.round(((fullPriceCents - priceCents) / fullPriceCents) * 100);
    }
    byId.set(node.productId, {
      productId: node.productId,
      itemId: node.id ?? null,
      name: node.name,
      size: node.size ?? null,
      brand: node.brandName ?? null,
      priceCents,
      fullPriceCents,
      priceLabel: p.priceLabel,
      fullPriceLabel: p.fullPriceLabel,
      unitPriceLabel: p.unitPriceLabel,
      offerLabel: p.offerLabel,
      percentOff,
      url: node.evergreenUrl ? `https://www.cub.com/store/cub/products/${node.evergreenUrl}` : null,
    });
  }
  return [...byId.values()];
}
