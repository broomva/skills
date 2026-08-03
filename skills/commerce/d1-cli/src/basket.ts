/**
 * Building a basket to a spending target.
 *
 * ## The budget is a CEILING, and the output says so
 *
 * `--budget 50000` means "do not spend more than this". A best-effort fit that
 * overshoots by one line is the more useful answer roughly half the time and
 * the wrong answer the other half — and which half you are in is not knowable
 * from here. Overspending someone's grocery budget without being asked is the
 * worse of the two failures, so the ceiling is hard and every basket states
 * that it was.
 *
 * ## What it could not fit is part of the answer, not a footnote
 *
 * A basket that silently drops three of eight lines and reports a total is the
 * same defect as an empty substitute result asserting "nothing is in stock"
 * while concealing that it compared 3 products of 140. Every term that did not
 * make it carries the reason it did not, and every line names how many products
 * it actually chose between.
 *
 * ## Value, not pack price
 *
 * Lines are chosen by unit price within a single measure, because pack price
 * and value routinely disagree — the whole reason `--sort per-unit` exists. A
 * candidate with no published size cannot be compared that way and is not
 * silently ranked as though it could be.
 */

import { pickOffer, priced, search } from "./catalog.ts";
import type { D1Client } from "./client.ts";
import { sum } from "./money.ts";
import { type Candidate, findSubstitutes } from "./substitute.ts";
import { DEFAULT_SALES_CHANNEL, type PriceHundredths, type Product, UsageError } from "./types.ts";

/** Why a term is not in the basket, or that it is. */
export type LineStatus =
  | "filled"
  | "filled-by-substitute"
  | "over-budget"
  | "nothing-in-stock"
  | "no-match";

export interface BasketLine {
  /** The shopping-list term, verbatim. */
  term: string;
  status: LineStatus;
  /** What was chosen, when anything was. */
  product?: Product;
  price?: PriceHundredths;
  /**
   * Set when the term's own best match was unavailable and a replacement from
   * its category was used instead. Named, never applied silently.
   */
  replaces?: Product;
  /** How many products this line actually chose between. */
  compared: number;
  /** How many D1 reported for the term, which may exceed `compared`. */
  matched: number;
}

export interface BasketPlan {
  budget: PriceHundredths;
  lines: BasketLine[];
  /** Sum of the filled lines only. */
  total: PriceHundredths;
  /** `budget - total`. Never negative: the ceiling is hard. */
  remaining: PriceHundredths;
}

/**
 * The best buy among products, by unit price within one measure.
 *
 * Only in-stock, really-priced products are eligible: a `Price: 0` means "no
 * offer at this store", and a basket line built on one would be a claim about
 * a purchase that cannot happen.
 *
 * Measures are not blended. `$/kg`, `$/L` and `$/unit` are not comparable
 * quantities, so the commonest measure among the eligible products wins and the
 * rest are not considered — the same rule `search --sort per-unit` applies, for
 * the same reason. Products with no published size fall back to pack price only
 * when NOTHING in the set publishes one, so a comparable answer is always
 * preferred to an incomparable one.
 */
export function chooseBest(products: readonly Product[]): Product | undefined {
  const eligible = products.filter((p) => {
    const o = pickOffer(p.offers);
    return o?.available === true && priced(o);
  });
  if (!eligible.length) return undefined;

  const byMeasure = new Map<string, number>();
  for (const p of eligible) {
    if (p.size && p.unitPrice !== undefined) {
      byMeasure.set(p.size.measure, (byMeasure.get(p.size.measure) ?? 0) + 1);
    }
  }
  const dominant = [...byMeasure.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];

  if (dominant) {
    const comparable = eligible.filter(
      (p) => p.size?.measure === dominant && p.unitPrice !== undefined,
    );
    return comparable.sort((a, b) => (a.unitPrice ?? 0) - (b.unitPrice ?? 0))[0];
  }
  // Nothing in the set publishes a size. Pack price is the only axis left, and
  // saying so is the caller's job — see `renderBasket`.
  return eligible
    .slice()
    .sort((a, b) => (pickOffer(a.offers)?.price ?? 0) - (pickOffer(b.offers)?.price ?? 0))[0];
}

/** Price of a chosen product, as a basket line costs it. */
export function linePrice(p: Product): PriceHundredths | undefined {
  const o = pickOffer(p.offers);
  return priced(o) ? o.price : undefined;
}

/**
 * Fit chosen lines under the ceiling, in the order the shopper wrote them.
 *
 * Input order is deliberate. A shopping list is already ranked — the person
 * wrote the milk before the biscuits — and reordering by value would spend the
 * budget on whatever happens to be cheapest per kg, which is a different
 * request. A line that does not fit is skipped rather than ending the fill, so
 * a single expensive item cannot strand everything after it.
 */
export function fillToBudget(
  candidates: readonly BasketLine[],
  budget: PriceHundredths,
): BasketPlan {
  const lines: BasketLine[] = [];
  let spent = 0;

  for (const line of candidates) {
    if (line.status === "no-match") {
      lines.push(line);
      continue;
    }
    // A line with no price cannot be a filled line. Letting one through would
    // put it in the basket at `$ 0` and count it toward the total as zero —
    // the "a price of 0 is not free" defect, re-entered from the other side.
    // The only way a chosen product has no price is that it has no offer at
    // this store, which is what `nothing-in-stock` says.
    if (line.price === undefined) {
      lines.push(
        line.status === "filled" || line.status === "filled-by-substitute"
          ? { ...line, status: "nothing-in-stock" }
          : line,
      );
      continue;
    }
    if (spent + line.price > budget) {
      lines.push({ ...line, status: "over-budget" });
      continue;
    }
    spent += line.price;
    lines.push(line);
  }

  const total = sum(
    lines
      .filter((l) => l.status === "filled" || l.status === "filled-by-substitute")
      .map((l) => l.price ?? 0),
  );
  return { budget, lines, total, remaining: budget - total };
}

/**
 * Read `--budget` as whole pesos, strictly.
 *
 * Parsed by an explicit grammar rather than by stripping punctuation and handing
 * the rest to `Number()`. That shortcut accepted three things it should not, and
 * every one of them failed the way this codebase cares about — quietly, with a
 * plausible number:
 *
 *   "50,5"  -> 505      a Colombian DECIMAL comma stripped into a 10x budget
 *   "0x10"  -> 16       Number() reads hex
 *   "1e5"   -> 100000   and scientific notation
 *
 * A dot is a thousands separator here, as Colombians write it. A comma is a
 * decimal separator, and since pesos are not quoted in cents there is no honest
 * reading of one in a budget — so it is refused by name instead of silently
 * becoming a different number.
 */
const BUDGET = /^\$?\s*(\d{1,3}(?:\.\d{3})+|\d+)$/;

export function parseBudget(raw: unknown): PriceHundredths {
  const reject = (why: string): never => {
    throw new UsageError(
      `--budget must be a whole number of pesos, got "${String(raw)}" — ${why}. Example: --budget 50000`,
    );
  };
  if (typeof raw === "number") {
    if (!Number.isFinite(raw) || raw <= 0) reject("it is not a positive amount");
    return Math.round(raw * 100);
  }
  const text = String(raw ?? "").trim();
  if (!text) reject("it is empty");
  if (text.includes(",")) {
    reject("a decimal comma has no meaning in pesos, which are not quoted in cents");
  }
  const m = text.match(BUDGET);
  if (!m) reject("it is not a plain amount like 50000 or 50.000");
  const n = Number((m?.[1] ?? "").replace(/\./g, ""));
  if (!Number.isFinite(n) || n <= 0) reject("it is not a positive amount");
  return Math.round(n * 100);
}

export interface BasketOptions {
  regionId?: string;
  salesChannel?: string;
  /** Products to fetch per term. Capped upstream at 50. */
  count?: number;
}

/**
 * Resolve a shopping list against a store, then fit it under the budget.
 *
 * Each term is searched independently; a term whose matches are all out of
 * stock falls through to `findSubstitutes` on its best match, which is the
 * whole reason this command waited on substitution. The replacement is NAMED in
 * the line rather than swapped in quietly — the CLI proposes and the person
 * decides, here as everywhere else.
 */
export async function buildBasket(
  client: D1Client,
  terms: readonly string[],
  budget: PriceHundredths,
  opts: BasketOptions = {},
): Promise<BasketPlan> {
  const salesChannel = opts.salesChannel ?? DEFAULT_SALES_CHANNEL;
  const chosen: BasketLine[] = [];

  for (const term of terms) {
    const page = await search(client, {
      query: term,
      count: opts.count,
      sort: "per-unit",
      regionId: opts.regionId,
      salesChannel,
    });
    const compared = page.products.length;
    const matched = page.total;

    const best = chooseBest(page.products);
    if (best) {
      chosen.push({
        term,
        status: "filled",
        product: best,
        price: linePrice(best),
        compared,
        matched,
      });
      continue;
    }
    if (!page.products.length) {
      chosen.push({ term, status: "no-match", compared, matched });
      continue;
    }

    // Everything the term found is out of stock. Ask the category what else
    // would do, using the best-matching product as the source.
    const source = page.products[0];
    if (!source) {
      chosen.push({ term, status: "no-match", compared, matched });
      continue;
    }
    const replacement = await bestSubstitute(client, source, opts, salesChannel);
    if (!replacement) {
      chosen.push({ term, status: "nothing-in-stock", product: source, compared, matched });
      continue;
    }
    chosen.push({
      term,
      status: "filled-by-substitute",
      product: replacement.product,
      price: linePrice(replacement.product),
      replaces: source,
      compared: compared + replacement.compared,
      matched,
    });
  }

  return fillToBudget(chosen, budget);
}

/** First ranked in-stock replacement for a product, or undefined. */
async function bestSubstitute(
  client: D1Client,
  source: Product,
  opts: BasketOptions,
  salesChannel: string,
): Promise<{ product: Product; compared: number } | undefined> {
  try {
    const result = await findSubstitutes(client, source.skuId, {
      regionId: opts.regionId,
      salesChannel,
      count: opts.count,
      limit: 1,
    });
    const top: Candidate | undefined = result.candidates[0];
    if (!top) return undefined;
    return { product: top.product, compared: result.poolProducts };
  } catch {
    // A term that cannot be substituted is a line the basket reports as
    // unfilled, not an error that discards the seven lines already resolved.
    return undefined;
  }
}
