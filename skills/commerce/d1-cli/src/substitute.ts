/**
 * Substitution — what to buy instead, and what you give up by taking it.
 *
 * ## Why this exists
 *
 * Two real sessions stranded on a line D1 could not supply: a mandarin juice
 * that was out of stock at the customer's store while present at the test one,
 * and a `PAN ARTESANAL INTEGRAL` that sold out overnight mid-basket. The CLI
 * could price a basket and refuse to check out a broken one; it could not
 * repair one.
 *
 * ## Propose, never replace
 *
 * Nothing here writes. It returns candidates and the `d1 cart add` you may
 * choose to run, because the customer twice preferred a line REMOVED over a
 * wrong substitute, said so explicitly, and was right both times: a shopper
 * knows things about a swap that a name-and-price ranker cannot see. So the
 * ranking's job is not to decide — it is to make the trade-off legible, which
 * is why every candidate carries what CHANGED rather than just a score.
 */

import {
  bestOffer,
  categoryFacetPath,
  deepestCategory,
  priced,
  productBySku,
  search,
  slugify,
} from "./catalog.ts";
import type { D1Client } from "./client.ts";
import { type UnitSize, formatUnitPrice } from "./measure.ts";
import { formatCOP } from "./money.ts";
import { D1Error, DEFAULT_SALES_CHANNEL, type Product } from "./types.ts";

// ---------------------------------------------------------------------------
// What changed
// ---------------------------------------------------------------------------

export type DeltaKind =
  | "brand"
  | "size"
  | "measure"
  | "unit-price"
  | "price"
  | "warning-added"
  | "warning-removed";

export interface Delta {
  kind: DeltaKind;
  from?: string;
  to?: string;
  /** Signed percentage change, candidate relative to source. Absent when one side is unknown. */
  percent?: number;
  /** One phrase naming the change, for a human. */
  text: string;
}

export interface Candidate {
  product: Product;
  /** 0..1, over name similarity, unit price and pack size. Higher is closer. */
  score: number;
  /**
   * 0 when the candidate is measured in the same unit as the source, 1 when it
   * is not. A hard grouping, never blended into `score` — see {@link scoreCandidate}.
   */
  tier: 0 | 1;
  deltas: Delta[];
}

export interface SubstituteResult {
  /** The product being replaced, priced regionally when it was reachable that way. */
  source: Product;
  /** Whether the source is itself still buyable here — often the reason for asking. */
  sourceAvailable: boolean;
  /**
   * True when the source's own price came from the national catalogue because
   * it was not on the regional page. Never silently mixed with regional prices.
   */
  sourcePricedNationally: boolean;
  /** Category path searched, as D1 names it. */
  categoryPath: string;
  /** Levels of that path actually used — lower than its full depth means widened. */
  searchedDepth: number;
  /** Full depth of the source's category path. */
  categoryDepth: number;
  /** SKUs fetched from that category, including the source and out-of-stock ones. */
  poolSize: number;
  /** Distinct PRODUCTS among them — the unit `poolTotal` is counted in. */
  poolProducts: number;
  /** Products D1 says the category holds. Above `poolProducts` means a partial sweep. */
  poolTotal: number;
  /** How many candidates survived filtering and ranking, before `limit`. */
  rankedCount: number;
  candidates: Candidate[];
  regionId?: string;
}

// ---------------------------------------------------------------------------
// Similarity
// ---------------------------------------------------------------------------

/**
 * Words that carry no product identity: articles, and the unit vocabulary that
 * already lives in `size`.
 *
 * Leaving them in makes packaging look like similarity — `LECHE ENTERA ... 900 ML`
 * and `JUGO DE MANGO ... 900 ML` share two tokens on the strength of the carton
 * alone, and in a mixed category that is enough to outrank a real match.
 */
const NOISE = new Set([
  "de",
  "del",
  "la",
  "el",
  "los",
  "las",
  "y",
  "con",
  "sin",
  "en",
  "para",
  "x",
  "gr",
  "grs",
  "g",
  "kg",
  "kgs",
  "ml",
  "cc",
  "lt",
  "lts",
  "l",
  "un",
  "und",
  "unid",
  "unidad",
  "unidades",
]);

/**
 * The identity-bearing words of a product name, accent-stripped and lowercased.
 *
 * Digits are dropped rather than compared: the quantity they express is already
 * held — correctly, and in a normalized unit — by `size`, whereas as text
 * `900` and `1000` are simply two different tokens no matter how close the
 * products are.
 */
export function tokens(name: string): string[] {
  return (
    slugify(name)
      .split("-")
      // `X200ML` and `3UN` arrive glued together. Split at every letter/digit
      // boundary so the numeric half can go without taking the word with it —
      // otherwise `x200ml` survives whole as a token that matches nothing.
      .flatMap((t) => t.split(/(?<=\d)(?=\D)|(?<=\D)(?=\d)/))
      .filter((t) => t.length > 0 && !/\d/.test(t) && !NOISE.has(t))
  );
}

/** Sørensen–Dice overlap of two token sets, 0 (nothing shared) to 1 (identical). */
export function dice(a: string[], b: string[]): number {
  const A = new Set(a);
  const B = new Set(b);
  if (A.size === 0 || B.size === 0) return 0;
  let shared = 0;
  for (const t of A) if (B.has(t)) shared++;
  return (2 * shared) / (A.size + B.size);
}

/**
 * How close two positive quantities are: 1 when equal, falling toward 0 as they
 * diverge.
 *
 * Symmetric on purpose. A substitute at half the price per kilo is exactly as
 * *different* as one at double, and which of those the shopper wants is their
 * call rather than the ranker's — the delta says which direction it went, and
 * that is the part they act on.
 */
export function proximity(a: number, b: number): number {
  if (!(a > 0) || !(b > 0)) return 0;
  return Math.min(a, b) / Math.max(a, b);
}

const WEIGHTS = { name: 0.5, unitPrice: 0.3, size: 0.2 } as const;

/**
 * Score one candidate against the source, and place it in a measure tier.
 *
 * Weight is redistributed over the components that EXIST rather than scoring a
 * missing one as zero. About 5% of D1's catalogue publishes no pack size, and
 * charging those products for the absence buries them for a fact about D1's
 * data rather than about the product — the same reason `parseUnitSize` returns
 * undefined instead of guessing.
 *
 * Measure stays OUT of the score and becomes a hard grouping. $/kg, $/L and
 * $/unit are not comparable quantities, and blending them is what once ranked
 * an $8,900 bottle in among the $/L figures as though it were a competitive
 * buy (see `--sort per-unit` in `catalog.ts`).
 */
export function scoreCandidate(source: Product, cand: Product): { score: number; tier: 0 | 1 } {
  const sameMeasure =
    source.size !== undefined &&
    cand.size !== undefined &&
    source.size.measure === cand.size.measure;

  const parts: Array<[weight: number, value: number]> = [
    [WEIGHTS.name, dice(tokens(source.name), tokens(cand.name))],
  ];
  if (sameMeasure && source.unitPrice !== undefined && cand.unitPrice !== undefined) {
    parts.push([WEIGHTS.unitPrice, proximity(source.unitPrice, cand.unitPrice)]);
  }
  if (sameMeasure && source.size && cand.size) {
    parts.push([WEIGHTS.size, proximity(source.size.amount, cand.size.amount)]);
  }

  const totalWeight = parts.reduce((s, [w]) => s + w, 0);
  const score = totalWeight > 0 ? parts.reduce((s, [w, v]) => s + w * v, 0) / totalWeight : 0;
  // When the source has no size, no candidate can be compared per unit, so
  // there is no meaningful tier to demote anyone into.
  const tier: 0 | 1 = source.size === undefined || sameMeasure ? 0 : 1;
  return { score, tier };
}

// ---------------------------------------------------------------------------
// Differences
// ---------------------------------------------------------------------------

/** Signed percentage change from `from` to `to`. Undefined when `from` is not positive. */
function percentChange(from: number, to: number): number | undefined {
  if (!(from > 0)) return undefined;
  return Math.round(((to - from) / from) * 100);
}

/**
 * `0.9 L`, `2 kg`, `30 unit` — trailing zeroes trimmed.
 *
 * Precision scales with magnitude rather than being fixed at 3 decimals: a
 * 400 mg sachet is 0.0004 kg, which `toFixed(3)` renders as a confident
 * `0 kg`. Showing a real quantity as zero is the same lie as showing an absent
 * price as `$ 0`.
 */
export function formatSize(size: UnitSize): string {
  const places = size.amount >= 1 ? 3 : Math.min(9, 3 + Math.ceil(-Math.log10(size.amount)));
  return `${Number(size.amount.toFixed(places))} ${size.measure}`;
}

function signed(pct: number): string {
  return `${pct > 0 ? "+" : ""}${pct}%`;
}

/**
 * Everything that differs between the source and a candidate.
 *
 * This is the actual product of the command. A score orders the list; the
 * deltas are what a shopper decides on — a 12% saving means one thing when the
 * pack is the same size and the label is the same, and quite another when it
 * comes with `Exceso en Azúcares` attached.
 */
export function describeDeltas(source: Product, cand: Product): Delta[] {
  const out: Delta[] = [];

  if (source.brand && cand.brand && source.brand !== cand.brand) {
    out.push({
      kind: "brand",
      from: source.brand,
      to: cand.brand,
      text: `${source.brand} → ${cand.brand}`,
    });
  }

  if (source.size && cand.size) {
    if (source.size.measure !== cand.size.measure) {
      out.push({
        kind: "measure",
        from: source.size.measure,
        to: cand.size.measure,
        text: `sold by ${cand.size.measure}, not ${source.size.measure} — the two cannot be compared per unit`,
      });
    } else if (source.size.amount !== cand.size.amount) {
      out.push({
        kind: "size",
        from: formatSize(source.size),
        to: formatSize(cand.size),
        percent: percentChange(source.size.amount, cand.size.amount),
        text: `${formatSize(source.size)} → ${formatSize(cand.size)}`,
      });
    }
  } else if (source.size && !cand.size) {
    out.push({
      kind: "size",
      from: formatSize(source.size),
      text: "publishes no pack size, so it cannot be compared per unit",
    });
  } else if (!source.size && cand.size) {
    // The mirror case, and it was silently missing. When the SOURCE publishes
    // no size, nothing can be compared to it per unit — but the candidate rows
    // still carry a $/kg or $/L column, so without this the reader is shown
    // per-unit figures with nothing saying they are incomparable.
    out.push({
      kind: "measure",
      to: cand.size.measure,
      text: `sold by ${cand.size.measure}, but the original publishes no pack size — the two cannot be compared per unit`,
    });
  }

  if (
    source.unitPrice !== undefined &&
    cand.unitPrice !== undefined &&
    source.size &&
    cand.size &&
    source.size.measure === cand.size.measure
  ) {
    const from = formatUnitPrice(formatCOP(source.unitPrice), source.size.measure);
    const to = formatUnitPrice(formatCOP(cand.unitPrice), cand.size.measure);
    const pct = percentChange(source.unitPrice, cand.unitPrice);
    // Compared as RENDERED, not as raw hundredths. 900 mL at COP 3,500 and
    // 1 L at COP 3,889 differ by 11 hundredths per litre — two perfectly
    // ordinary shelf prices that produced `$ 3.889/L → $ 3.889/L  (0%)`, a
    // change reported where the reader can see there is none.
    if (from !== to) {
      out.push({
        kind: "unit-price",
        from,
        to,
        percent: pct,
        text: `${from} → ${to}${pct === undefined ? "" : `  (${signed(pct)})`}`,
      });
    }
  }

  // Both sides must carry a REAL price. VTEX reports 0 for a product it has no
  // offer for here, and `$ 0 → $ 9.300` presents "we have no price for this"
  // as a concrete rise from nothing — observed live on SKU 1687. There is no
  // price change to report when one side has no price; saying nothing is the
  // honest output.
  const so = bestOffer(source);
  const co = bestOffer(cand);
  if (priced(so) && priced(co) && so.price !== co.price) {
    const pct = percentChange(so.price, co.price);
    out.push({
      kind: "price",
      from: formatCOP(so.price),
      to: formatCOP(co.price),
      percent: pct,
      text: `${formatCOP(so.price)} → ${formatCOP(co.price)}${
        pct === undefined ? "" : `  (${signed(pct)})`
      }`,
    });
  }

  // Colombia's Ley 2120 front-of-pack warnings. A swap that quietly adds one is
  // the single change most likely to matter to whoever is eating it, so it is
  // reported in both directions and never folded into the score.
  for (const w of cand.warnings) {
    if (!source.warnings.includes(w)) {
      out.push({ kind: "warning-added", to: w, text: `gains "${w}"` });
    }
  }
  for (const w of source.warnings) {
    if (!cand.warnings.includes(w)) {
      out.push({ kind: "warning-removed", from: w, text: `drops "${w}"` });
    }
  }

  return out;
}

// ---------------------------------------------------------------------------
// Ranking
// ---------------------------------------------------------------------------

export const DEFAULT_LIMIT = 8;

/**
 * Levels of category tree the widening walk will climb, and therefore the most
 * requests one invocation can issue. D1 publishes three; the cap exists because
 * the depth is upstream-controlled and this loop is one request per level.
 */
export const MAX_CATEGORY_DEPTH = 6;

/**
 * Rank a candidate pool against the source.
 *
 * Pure — every input is already fetched. The network lives in
 * {@link findSubstitutes}, so the judgement this command exists to make can be
 * tested without one.
 */
export function rankSubstitutes(
  source: Product,
  pool: Product[],
  limit = DEFAULT_LIMIT,
): Candidate[] {
  const seen = new Set<string>();
  const out: Candidate[] = [];

  // When the SOURCE has no pack size, `scoreCandidate` cannot tier anyone —
  // there is no measure to be same-as. Left there, kg-, L- and unit-measured
  // products interleave in one list under one per-unit column, which is the
  // exact mixed-measure failure `--sort per-unit` was built to avoid, reached
  // by a different route. So group by the candidates' OWN measure, commonest
  // first, exactly as `search` does for the same reason.
  const byMeasure = new Map<string, number>();
  if (source.size === undefined) {
    for (const p of pool) {
      if (p.size) byMeasure.set(p.size.measure, (byMeasure.get(p.size.measure) ?? 0) + 1);
    }
  }
  const dominant = [...byMeasure.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  const group = (p: Product): number => {
    // With a sized source, the only grouping that matters is comparable-to-it.
    if (source.size !== undefined) {
      return p.size !== undefined && p.size.measure === source.size.measure ? 0 : 1;
    }
    // Without one, no candidate is comparable to the source, so group them
    // against EACH OTHER instead: commonest measure first, sizeless last.
    return p.size === undefined ? 2 : p.size.measure === dominant ? 0 : 1;
  };

  for (const p of pool) {
    // Never propose the thing you were asked to replace.
    if (p.skuId === source.skuId) continue;
    // A category page can carry the same SKU under more than one product entry.
    if (seen.has(p.skuId)) continue;
    seen.add(p.skuId);
    // An out-of-stock replacement replaces nothing. This is the whole premise
    // of the command, so it is a hard filter rather than a scoring penalty.
    if (!p.offers.some((o) => o.available)) continue;

    const { score } = scoreCandidate(source, p);
    // The tier a candidate is DISPLAYED in is its comparability group, which
    // `scoreCandidate` can only answer when the source has a size of its own.
    const tier: 0 | 1 = group(p) === 0 ? 0 : 1;
    out.push({ product: p, score, tier, deltas: describeDeltas(source, p) });
  }

  return out
    .sort(
      (a, b) =>
        group(a.product) - group(b.product) ||
        b.score - a.score ||
        // Deterministic last resort. Without it, two equally-scored candidates
        // swap places between runs on nothing but upstream ordering, and a
        // caller diffing two invocations sees a change that did not happen.
        //
        // A plain comparison, not `localeCompare`: collation depends on ICU and
        // `LANG`, and a numeric-collation locale orders "10" before "9" — which
        // would make the "deterministic" tie-break vary by environment.
        (a.product.skuId < b.product.skuId ? -1 : 1),
    )
    .slice(0, limit);
}

// ---------------------------------------------------------------------------
// The command
// ---------------------------------------------------------------------------

export interface SubstituteOptions {
  regionId?: string;
  salesChannel?: string;
  /** Candidates to return. */
  limit?: number;
  /** Products to sweep from the category. Capped upstream at 50 per page. */
  count?: number;
}

/**
 * Find what to buy instead of `skuId`.
 *
 * The sweep deliberately does NOT ask for available items only. The source is
 * usually the unavailable one — that is why anyone runs this — and it is needed
 * as the price baseline, so availability is filtered in the ranker instead.
 */
export async function findSubstitutes(
  client: D1Client,
  skuId: string,
  opts: SubstituteOptions = {},
): Promise<SubstituteResult> {
  const salesChannel = opts.salesChannel ?? DEFAULT_SALES_CHANNEL;
  const national = await productBySku(client, skuId, { salesChannel });
  if (!national) {
    throw new D1Error(
      `SKU ${skuId} is not in D1's catalogue, so there is nothing to find a replacement for. Check the id against the first column of \`d1 search\`.`,
    );
  }

  const categoryPath = deepestCategory(national.categories);
  if (!categoryPath) {
    throw new D1Error(
      `D1 publishes no category for SKU ${skuId}, and the category is what a replacement is searched in. Try \`d1 search\` with part of the product name instead.`,
    );
  }
  // Capped, because the depth comes from upstream and drives one request per
  // level. D1's tree is three deep today and nothing enforces that; a 40-segment
  // category in a malformed response issued 41 requests from one invocation,
  // against an API whose 429 the client already treats as a live failure mode.
  const categoryDepth = Math.min(
    MAX_CATEGORY_DEPTH,
    categoryPath.split("/").filter((s) => s.trim()).length,
  );

  // Walk UP from the leaf, one level at a time.
  //
  // The leaf is the most like-for-like set, but D1's leaves are small — eight
  // products under `Lacteos y huevos/Leches/Entera` — and a leaf whose every
  // member is out of stock has nothing to offer. Widening is REPORTED rather
  // than done quietly: a suggestion from two levels up is a different kind of
  // answer, and the caller should be able to see that it is one.
  let searchedDepth = categoryDepth;
  let pool: Product[] = [];
  let poolTotal = 0;
  let regional: Product | undefined;

  for (let depth = categoryDepth; depth >= 1; depth--) {
    const facets = categoryFacetPath(categoryPath, depth);
    if (!facets) {
      // `categoryFacetPath` returns "" when the FIRST name has no slug — a
      // category like `&/Gaseosas`. Continuing would sweep with no facet at
      // all, which is the whole 1,600-product catalogue. Refusing is right,
      // but it must be an ERROR: breaking here left the caller with an empty
      // pool and the flat claim "nothing in this category is in stock",
      // asserted from zero requests.
      throw new D1Error(
        `D1's category path for SKU ${skuId} ("${categoryPath}") has no searchable form, so a replacement cannot be looked up there. Try \`d1 search\` with part of the product name instead.`,
      );
    }
    const page = await search(client, {
      facets,
      count: opts.count ?? 50,
      page: 1,
      regionId: opts.regionId,
      salesChannel,
    });
    // Derived from the path that was SENT, not from the loop counter.
    // `categoryFacetPath` truncates when a middle name has no slug, so
    // `Bebidas/&/Gaseosas` at depth 3 actually searches `category-1/bebidas` —
    // the whole department — and reporting `3` claimed the leaf was swept and
    // suppressed the "widened" notice that was the reader's only clue.
    searchedDepth = facets.split("/").length / 2;
    pool = page.products;
    poolTotal = page.total;
    // Keep the FIRST (deepest) sighting: the widened pages are larger and the
    // source may fall off the end of one, which would turn a known regional
    // price back into a national one for no reason.
    regional ??= pool.find((p) => p.skuId === skuId);
    if (pool.some((p) => p.skuId !== skuId && p.offers.some((o) => o.available))) break;
  }

  // Prefer the regional reading of the source. Its attributes are identical;
  // its price and availability are the ones that apply where the shopper is,
  // and comparing a national baseline against regional candidates would report
  // a price delta that is partly just the two catalogues disagreeing.
  const source = regional ?? national;
  // Ranked unbounded first, so `rankedCount` reports how many alternatives
  // actually exist rather than how many were asked for — "3 of 27 shown" and
  // "3 of 3" are different answers and the reader needs to tell them apart.
  const eligible = rankSubstitutes(source, pool, Number.POSITIVE_INFINITY);
  const ranked = eligible.slice(0, opts.limit ?? DEFAULT_LIMIT);

  return {
    source,
    sourceAvailable: regional ? regional.offers.some((o) => o.available) : false,
    sourcePricedNationally: regional === undefined,
    categoryPath,
    searchedDepth,
    categoryDepth,
    poolSize: pool.length,
    // Counted in PRODUCTS, to be comparable with `poolTotal`. `pool` holds one
    // entry per SKU and a product can carry several, so `pool.length` could
    // exceed a `recordsFiltered` counting products — and the partial-sweep
    // warning was gated on an inequality between two different units, which
    // suppressed it exactly when the sweep was most partial.
    poolProducts: new Set(pool.map((p) => p.productId)).size,
    poolTotal,
    rankedCount: eligible.length,
    candidates: ranked,
    regionId: opts.regionId,
  };
}
