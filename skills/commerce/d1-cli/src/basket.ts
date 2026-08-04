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
import {
  D1Error,
  DEFAULT_SALES_CHANNEL,
  type PriceHundredths,
  type Product,
  UsageError,
} from "./types.ts";

/** Why a term is not in the basket, or that it is. */
export type LineStatus =
  | "filled"
  | "filled-by-substitute"
  | "over-budget"
  | "nothing-in-stock"
  /** The replacement lookup itself failed, so stock here is UNKNOWN, not empty. */
  | "replacement-unknown"
  /** D1 sells this, but nothing of the requested BRAND — a constraint, not a shortage. */
  | "no-brand-match"
  | "no-match";

/** The two statuses that put a product in the basket and spend money. */
export const FILLED: readonly LineStatus[] = ["filled", "filled-by-substitute"];
export const isFilled = (s: LineStatus) => FILLED.includes(s);

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
  /**
   * How many products this line chose between.
   *
   * Two readings, by path, and `--json` consumers need both stated: on a filled
   * line it is the set actually weighed; on an EMPTY category sweep nothing was
   * weighable, so it reports how wide the look was instead — the alternative
   * was a structural zero that could not vary with the shelf.
   */
  compared: number;
  /** How many D1 reported for the term, which may exceed `compared`. */
  matched: number;
  /** The pick was made on PACK price, because no comparable measure existed. */
  byPackPrice?: boolean;
  /** Whether any candidate published a size — the disclosure must not overclaim. */
  anySized?: boolean;
  /** `compared` counts a category sweep, not the search page for this term. */
  substituteSweep?: boolean;
  /**
   * On an empty sweep: how many products WERE in stock in the category but
   * carry no price here. Separates an empty shelf from an unpriced one.
   */
  inStock?: number;
  /** Distinct products fetched from the category, when one was swept. */
  swept?: number;
  /** Products that category holds. Above `swept` means the look was partial. */
  categoryTotal?: number;
  /**
   * Pack prices of the runners-up this line weighed and did not pick.
   *
   * Input to the disclosure below, and left on the line so a `--json` consumer
   * can reach its own conclusion rather than only ours.
   */
  alternatives?: readonly PriceHundredths[];
  /**
   * How many of those runners-up WOULD have fitted in the money left when this
   * line was refused. Set only on an `over-budget` line, where it is the whole
   * point; meaningless anywhere else, so it is absent there rather than zero.
   *
   * Reported, never acted on — see {@link fillToBudget}.
   */
  affordableAlternatives?: number;
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
export interface Choice {
  product: Product;
  /**
   * How many products this line ACTUALLY chose between — after dropping the
   * unavailable, the unpriced, and everything outside the winning measure.
   * Not the size of the page: reporting that would overstate the look by the
   * out-of-stock count, which is the "3 of 140" defect wearing a new hat.
   */
  compared: number;
  /**
   * True when nothing in the set published a size, so the pick was made on PACK
   * price. The caller must say so — a pack-price winner presented as a value
   * winner is the error unit pricing exists to prevent.
   */
  byPackPrice: boolean;
  /** Whether ANY eligible product published a size, for an honest disclosure. */
  anySized?: boolean;
  /**
   * Pack prices of the products this line weighed and did NOT pick.
   *
   * Carried so that a line which turns out not to fit can say how many of them
   * would have — see {@link fillToBudget}. Exactly the set counted by
   * `compared`, minus the winner, so the two numbers describe one population.
   */
  alternatives: readonly PriceHundredths[];
}

/**
 * Measures, worst-comparable last.
 *
 * `unit` sits last deliberately. A kilogram is a kilogram across products, and
 * a litre is a litre, but one "unit" of an empty bottle and one "unit" of oil
 * are not the same kind of thing — so when two measures are equally common,
 * ranking by `$/unit` is the least defensible of the available answers.
 *
 * Stated precisely, because an earlier version of this comment overclaimed:
 * with today's three measures this table is INTENT, not the operative rule.
 * `"kg" < "L" < "unit"` alphabetically too, so deleting it changes no current
 * outcome and no test can distinguish it from the `localeCompare` fallback
 * below. It earns its place by surviving a fourth measure — add `"m"` and
 * alphabetical order would rank it above `unit`, which is exactly the mistake
 * the table prevents.
 */
const MEASURE_RANK: Record<string, number> = { kg: 0, L: 1, unit: 2 };

export function chooseBest(products: readonly Product[], brand?: string): Choice | undefined {
  const want = normalizeBrand(brand);
  const eligible = products.filter((p) => {
    const o = pickOffer(p.offers);
    if (!(o?.available === true && priced(o))) return false;
    // Filtered BEFORE the measure census below, so the dominant measure is
    // decided within the brand. Filtering after would let products the shopper
    // has excluded pick the axis the remaining ones are ranked on.
    return want === undefined || normalizeBrand(p.brand) === want;
  });
  if (!eligible.length) return undefined;

  const byMeasure = new Map<string, number>();
  for (const p of eligible) {
    if (p.size && p.unitPrice !== undefined) {
      byMeasure.set(p.size.measure, (byMeasure.get(p.size.measure) ?? 0) + 1);
    }
  }
  // Commonest measure wins; ties break by MEASURE_RANK, then by name.
  //
  // The tie-break is the whole point. Sorting on count alone left the winner to
  // Map INSERTION ORDER, which is the order `search` happened to return — and
  // that order is computed over out-of-stock products too. So a page listing
  // three sold-out bottles first could make `unit` the dominant measure for a
  // set whose only real contest was one bottle against one oil, and the CLI
  // would put an empty bottle in the basket as the best value. Same set,
  // different array order, different answer.
  const dominant = [...byMeasure.entries()].sort(
    (a, b) =>
      b[1] - a[1] ||
      (MEASURE_RANK[a[0]] ?? 99) - (MEASURE_RANK[b[0]] ?? 99) ||
      a[0].localeCompare(b[0]),
  )[0]?.[0];

  if (dominant) {
    const comparable = eligible.filter(
      (p) => p.size?.measure === dominant && p.unitPrice !== undefined,
    );
    const ranked = comparable
      .slice()
      .sort((a, b) => (a.unitPrice ?? 0) - (b.unitPrice ?? 0) || a.skuId.localeCompare(b.skuId));
    const product = ranked[0];
    if (product) {
      return {
        product,
        compared: comparable.length,
        byPackPrice: false,
        alternatives: packPrices(ranked.slice(1)),
      };
    }
  }
  // No comparable measure. Pack price is the only axis left, and `byPackPrice`
  // makes the caller say so.
  //
  // `sized` is computed separately from the measure census above, which needs
  // BOTH a size and a unit price. Deriving the disclosure from that census
  // would let it print "D1 publishes no size for any of these" about a set
  // where D1 published sizes and only the unit prices were missing — a claim
  // about the data that the data contradicts.
  const ranked = eligible
    .slice()
    .sort(
      (a, b) =>
        (pickOffer(a.offers)?.price ?? 0) - (pickOffer(b.offers)?.price ?? 0) ||
        a.skuId.localeCompare(b.skuId),
    );
  const product = ranked[0];
  const sized = eligible.some((p) => p.size !== undefined);
  return product
    ? {
        product,
        compared: eligible.length,
        byPackPrice: true,
        anySized: sized,
        alternatives: packPrices(ranked.slice(1)),
      }
    : undefined;
}

/**
 * Buyable pack prices of a set of runners-up, in the order they were ranked.
 *
 * The unpriced filter is defence in depth, and deliberately kept even though no
 * current caller can trigger it: all three pre-filter on `priced()`, which is
 * `price > 0`. A mutation removing it therefore survived the whole suite, which
 * is this repo's definition of an unverified claim — so the function is exported
 * and tested directly rather than left as a guard nobody can falsify.
 *
 * It stays because "is buyable" is an invariant the `Product` type does not
 * carry. A future caller handing over an unfiltered list would otherwise promise
 * a fit that cannot be bought — the "a price of 0 is not free" defect, which has
 * now been re-entered from three different directions in this codebase.
 */
/**
 * A brand, comparably.
 *
 * Case and surrounding whitespace are noise — D1 writes `LATTI`, a shopper
 * writes `Latti` — but inner punctuation is not, so nothing else is stripped.
 * A blank yields undefined, so `--brand ""` cannot become a filter that matches
 * only the products whose brand is also blank.
 */
export function normalizeBrand(brand?: string): string | undefined {
  if (typeof brand !== "string") return undefined;
  const t = brand.trim().replace(/\s+/g, " ").toUpperCase();
  return t.length ? t : undefined;
}

export function packPrices(products: readonly Product[]): readonly PriceHundredths[] {
  const out: PriceHundredths[] = [];
  for (const p of products) {
    const price = linePrice(p);
    if (price !== undefined && Number.isFinite(price)) out.push(price);
  }
  return out;
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
    // Only a line that is trying to be FILLED can spend money. Any other status
    // is passed through untouched — an earlier version let a priced
    // `nothing-in-stock` line increment `spent` while never counting toward
    // `total`, so the basket refused affordable items while reporting the money
    // as still available.
    if (!isFilled(line.status)) {
      lines.push(line);
      continue;
    }
    // A line with no usable price cannot be a filled line. Letting one through
    // would put it in the basket at `$ 0` and add zero to the total — the
    // "a price of 0 is not free" defect, re-entered from the other side.
    //
    // `Number.isFinite`, not just `!== undefined`: a NaN price defeats the
    // ceiling outright, because `sum()` coerces NaN to 0 while `spent` becomes
    // NaN and every later `spent + price > budget` is then false. That made
    // `remaining` negative on a "hard ceiling" — the one invariant this
    // function exists to hold.
    // A filled line needs BOTH a product and a usable price. Guarding only the
    // price left a line that billed money for a product the output could not
    // name: the body skipped it and the summary still read "1 of 1 lines,
    // $ 5.550". Guard where the money is decided, not where it is printed.
    if (!line.product || line.price === undefined || !Number.isFinite(line.price)) {
      // `alternatives` goes too. A line that reports nothing is in stock must
      // not carry prices of things that were, however unreachable that is from
      // `buildBasket` today — the exported type permits a caller the code does
      // not, and the whole status exists to say the shelf was empty.
      lines.push({
        ...line,
        status: "nothing-in-stock",
        price: undefined,
        alternatives: undefined,
      });
      continue;
    }
    if (spent + line.price > budget) {
      lines.push({ ...line, status: "over-budget" });
      continue;
    }
    spent += line.price;
    lines.push(line);
  }

  const total = sum(lines.filter((l) => isFilled(l.status)).map((l) => l.price ?? 0));
  const remaining = budget - total;

  // Say how many of the runners-up would have fitted — and stop there.
  //
  // Reaching down the ranking to fill the line is the tempting fix and the wrong
  // one. This line's product is the best VALUE of its set, or the closest MATCH
  // from a category; a cheaper one is neither, and swapping it in silently is
  // the auto-substitution BRO-2076 exists to forbid. So the count is disclosed
  // and the choice stays with the person.
  //
  // Settled HERE, against the money finally left, rather than inside the loop
  // against the money left at the moment of refusal. Lines after a refused one
  // keep spending, so the in-loop count could claim "1 cheaper match would fit"
  // directly beneath a footer reading "$ 1.000 left" about an alternative
  // costing $ 3.000 — a claim refuted by the evidence printed next to it.
  //
  // The arithmetic that makes "cheaper" true survives, and tightens: at refusal
  // `spent_t + price > budget`, and `total >= spent_t` because later lines only
  // add, so `remaining = budget - total <= budget - spent_t < price`. Anything
  // fitting in `remaining` is therefore strictly cheaper than what was refused.
  const settled = lines.map((l) =>
    l.status === "over-budget"
      ? {
          ...l,
          affordableAlternatives:
            (l.alternatives ?? []).filter((p) => Number.isFinite(p) && p > 0 && p <= remaining)
              .length || undefined,
        }
      : l,
  );

  return { budget, lines: settled, total, remaining };
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

/**
 * Refuse a budget too large to survive the conversion to hundredths.
 *
 * Past `MAX_SAFE_INTEGER / 100` the multiply loses integer precision, so the
 * ceiling enforced is not the one typed — `999.999.999.999.999.999` came back
 * as 100000000000000000000. Silently becoming a different plausible number is
 * the exact failure this parser exists to prevent, so the bound is stated.
 */
function assertExact(pesos: number, reject: (why: string) => never): void {
  if (pesos * 100 > Number.MAX_SAFE_INTEGER) {
    reject("it is too large to represent exactly, and a budget must be the number you typed");
  }
}

export function parseBudget(raw: unknown): PriceHundredths {
  const reject = (why: string): never => {
    throw new UsageError(
      `--budget must be a whole number of pesos, got "${String(raw)}" — ${why}. Example: --budget 50000`,
    );
  };
  // A number argument goes through the SAME rules as a string. Exempting it
  // meant `parseBudget(50.5)` returned half a peso while `parseBudget("50,5")`
  // was refused by name for being fractional, and `parseBudget(0.004)` rounded
  // to a budget of ZERO from a positive input — putting every line over budget.
  if (typeof raw === "number") {
    if (!Number.isFinite(raw) || raw <= 0) reject("it is not a positive amount");
    if (!Number.isInteger(raw)) reject("pesos are not quoted in cents, so it must be whole");
    assertExact(raw, reject);
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
  assertExact(n, reject);
  return Math.round(n * 100);
}

export interface BasketOptions {
  regionId?: string;
  salesChannel?: string;
  /** Products to fetch per term. Capped upstream at 50. */
  count?: number;
  /**
   * Restrict every line to one brand.
   *
   * The constraint is the BRAND rather than availability, which is the only
   * thing separating this from the substitute path — so it reuses the same
   * ranker rather than growing a second one.
   */
  brand?: string;
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
    // Deliberately UNSORTED. `chooseBest` finds the minimum itself, so sorting
    // here bought nothing — and it reordered the page, after which
    // `page.products[0]` was the cheapest-per-unit product rather than the
    // best-matching one. A shopper asking for "arroz" whose rice was sold out
    // then had replacements swept from the category of whatever happened to be
    // cheapest per kilo on the page, and the line read "replaces SAL REFINADA".
    const page = await search(client, {
      query: term,
      count: opts.count,
      regionId: opts.regionId,
      salesChannel,
    });
    const matched = page.total;

    // With a brand constraint, the term's own page is tried first — cheap, and
    // it is where a same-brand product usually is. Only when the page holds
    // none does the category sweep run, which is the ticket's own design: the
    // constraint is the brand rather than availability, so it reuses the
    // ranker rather than growing a second one.
    const best = chooseBest(page.products, opts.brand);
    if (!best && normalizeBrand(opts.brand) !== undefined) {
      const line = await brandLine(client, term, page, matched, opts, salesChannel);
      chosen.push(line);
      continue;
    }
    if (best) {
      chosen.push({
        term,
        status: "filled",
        product: best.product,
        price: linePrice(best.product),
        compared: best.compared,
        matched,
        byPackPrice: best.byPackPrice,
        anySized: best.anySized,
        alternatives: best.alternatives,
      });
      continue;
    }
    // No eligible product. Either D1 returned nothing at all for the term, or
    // everything it returned is out of stock.
    const source = page.products[0];
    if (!source) {
      chosen.push({ term, status: "no-match", compared: 0, matched });
      continue;
    }

    // Ask the category what else would do, using the best-matching product as
    // the source. `compared` stays the SEARCH's own count: the sweep's pool is
    // a different population counted in a different unit (distinct products vs
    // SKUs), and adding them produced a number that could exceed `matched` and
    // silently suppress the denominator.
    const replacement = await bestSubstitute(client, source, opts, salesChannel);
    if (replacement.outcome === "unreachable") {
      chosen.push({
        term,
        status: "replacement-unknown",
        product: source,
        compared: page.products.length,
        matched,
      });
      continue;
    }
    if (replacement.outcome === "none") {
      chosen.push({
        term,
        status: "nothing-in-stock",
        product: source,
        compared: replacement.compared,
        inStock: replacement.inStock,
        swept: replacement.swept,
        categoryTotal: replacement.categoryTotal,
        matched,
        // The count came from the CATEGORY sweep, not this term's own search,
        // so it must be labelled as such here too — `compared` can otherwise
        // exceed `matched`, giving a denominator smaller than its numerator.
        substituteSweep: true,
      });
      continue;
    }
    chosen.push({
      term,
      status: "filled-by-substitute",
      product: replacement.product,
      price: linePrice(replacement.product),
      replaces: source,
      compared: replacement.compared,
      swept: replacement.swept,
      categoryTotal: replacement.categoryTotal,
      matched,
      substituteSweep: true,
      alternatives: replacement.alternatives,
      // `byPackPrice` is deliberately NOT set here. A substitute is ranked by
      // name similarity and price proximity — never by pack price — so the
      // "chosen on pack price" note would misname the mechanism, and its
      // "D1 publishes no size for any of these" reads over a whole set while
      // the predicate looked at one product. The line already says it came from
      // a category sweep and names what it replaces; the footer covers the rest.
    });
  }

  return fillToBudget(chosen, budget);
}

type SubstituteOutcome =
  /** `compared` is how many could have been BOUGHT — the real choice. */
  | ({
      outcome: "found";
      product: Product;
      compared: number;
      /** Prices of the other buyable candidates, so an unaffordable pick can say what else was there. */
      alternatives: readonly PriceHundredths[];
    } & SweepScope)
  /**
   * `compared` is how WIDE the look was, not how many were buyable — on this
   * path that is zero by construction, and reporting it deleted the disclosure.
   * `inStock` separates "the category is empty" from "four were in stock and
   * none is priced at your store".
   */
  | ({ outcome: "none"; compared: number; inStock: number } & SweepScope)
  | { outcome: "unreachable" };

/** How partial the category sweep was, carried so the output can disclose it. */
interface SweepScope {
  /** Distinct products actually fetched from the category. */
  swept: number;
  /** Products D1 says that category holds. Above `swept` means a partial look. */
  categoryTotal: number;
}

/**
 * First ranked in-stock replacement for a product.
 *
 * Distinguishes **"the category holds nothing"** from **"the question could not
 * be asked"**, because a bare `catch` collapsing the two turns a failed request
 * into a positive claim about stock. `substitute.ts` already reasons this out
 * for its own sweep — an empty pool asserted from zero successful requests is
 * an error, not an answer — and swallowing here reintroduced it one module
 * over, with the added harm that the basket exits 3 ("never retry") on what may
 * be a transient outage.
 *
 * A failure still does not discard the lines already resolved. It surfaces as
 * `replacement-unknown`, which says what actually happened.
 */
/**
 * A line for a term whose own search page holds nothing of the wanted brand.
 *
 * Falls through to the category sweep and keeps the best-ranked candidate that
 * matches — substitution with a BRAND constraint instead of a stock one, which
 * is exactly what BRO-2079 asked for and why it reuses `findSubstitutes`.
 *
 * A failure to look is reported as `replacement-unknown`, never as "that brand
 * is not sold here": a request that did not answer is a statement about the
 * network, not about the shelf. Same rule as the stock path.
 */
async function brandLine(
  client: D1Client,
  term: string,
  page: { products: readonly Product[] },
  matched: number,
  opts: BasketOptions,
  salesChannel: string,
): Promise<BasketLine> {
  const want = normalizeBrand(opts.brand);
  const source = page.products[0];
  if (!source) {
    return { term, status: "no-match", compared: 0, matched };
  }
  try {
    const result = await findSubstitutes(client, source.skuId, {
      regionId: opts.regionId,
      salesChannel,
      count: opts.count,
      limit: Number.POSITIVE_INFINITY,
    });
    const buyable = result.candidates.filter(
      (c) => linePrice(c.product) !== undefined && normalizeBrand(c.product.brand) === want,
    );
    const top = buyable[0];
    if (!top) {
      return {
        term,
        status: "no-brand-match",
        product: source,
        // How wide the look was. On this path the brand-matching count is zero
        // by construction, so reporting it would be the structural-zero defect
        // the stock path already learned about.
        compared: result.rankedCount,
        swept: result.poolProducts,
        categoryTotal: result.poolTotal,
        matched,
        substituteSweep: true,
      };
    }
    return {
      term,
      status: "filled-by-substitute",
      product: top.product,
      price: linePrice(top.product),
      replaces: source,
      compared: buyable.length,
      swept: result.poolProducts,
      categoryTotal: result.poolTotal,
      matched,
      substituteSweep: true,
      alternatives: packPrices(buyable.slice(1).map((c) => c.product)),
    };
  } catch {
    return { term, status: "replacement-unknown", product: source, compared: 0, matched };
  }
}

async function bestSubstitute(
  client: D1Client,
  source: Product,
  opts: BasketOptions,
  salesChannel: string,
): Promise<SubstituteOutcome> {
  try {
    const result = await findSubstitutes(client, source.skuId, {
      regionId: opts.regionId,
      salesChannel,
      count: opts.count,
      // Unbounded, NOT 1. `findSubstitutes` slices to `limit` before returning,
      // so asking for one and then skipping unpriced candidates skipped the
      // only candidate there was — the "offer an unbuyable replacement" fix was
      // inert, and a priced runner-up was reported as an empty category.
      limit: Number.POSITIVE_INFINITY,
    });
    // Counts only what could actually be BOUGHT.
    //
    // `poolProducts` is the whole swept category including the out-of-stock
    // source — reporting it claimed a choice between 40 where one alternative
    // existed. `rankedCount` was the next attempt and is still wrong here,
    // because it counts everything that survived the AVAILABILITY filter while
    // the price filter below rejects more: a line could say "best of 4 in its
    // category" for the only buyable one of four, which is this module's own
    // stated invariant ("after dropping the unavailable, the unpriced") broken
    // on the one path that did not enforce it.
    const buyable = result.candidates.filter((c) => linePrice(c.product) !== undefined);
    const compared = buyable.length;
    // The sweep reads ONE page, capped at 50, of a category that may hold
    // hundreds. `d1 substitute` already says so on both its empty and non-empty
    // paths; a basket line making the same categorical claim needs the caveat
    // just as much. SKILL.md states this rule for exactly this sentence.
    const scope: SweepScope = { swept: result.poolProducts, categoryTotal: result.poolTotal };
    // `rankSubstitutes` filters on availability only, never on price. VTEX
    // reports `Price: 0` ("no offer in this region") alongside a positive
    // AvailableQuantity, so a rankable candidate can carry no price at all —
    // and one reached the basket, where it was downgraded and rendered as
    // "its category had no replacement" while the line still carried the
    // product it had just found. A candidate that cannot be bought is not a
    // replacement.
    const top: Candidate | undefined = buyable[0];
    // On the empty path `buyable.length` is 0 BY CONSTRUCTION, so reporting it
    // turned "(4 compared)" into a constant "(0 compared)" — indistinguishable
    // across an empty category, 140 sold-out SKUs, and four in-stock products
    // with no regional offer. A conclusion drawn from a look the sentence says
    // was zero wide also reads as self-refuting.
    if (!top) {
      return {
        outcome: "none",
        compared: result.rankedCount,
        inStock: result.rankedCount,
        ...scope,
      };
    }
    return {
      outcome: "found",
      product: top.product,
      compared,
      // The rest of the buyable sweep, in RANK order — the candidates that were
      // passed over for being less like what was asked for, not for costing
      // more. `buyable` is already filtered to what has a price, so every entry
      // is a real alternative rather than an unpurchasable one.
      alternatives: packPrices(buyable.slice(1).map((c) => c.product)),
      ...scope,
    };
  } catch {
    return { outcome: "unreachable" };
  }
}

/** One term, priced both ways. */
export interface BasketComparison {
  term: string;
  base?: BasketLine;
  alt?: BasketLine;
  /** Set only when BOTH sides filled: `alt.price - base.price`. */
  delta?: PriceHundredths;
}

export interface CrossBasket {
  /** The brand asked for, as typed. */
  brand: string;
  base: BasketPlan;
  alt: BasketPlan;
  rows: BasketComparison[];
  /**
   * The comparison, over the terms BOTH baskets filled — and nothing else.
   *
   * This is the whole reason the type is not two totals side by side. A
   * brand-constrained basket routinely fills fewer lines, and subtracting its
   * total from the unconstrained one then reports the missing lines as a
   * saving: drop the two most expensive terms and the "store brand" looks
   * dramatically cheaper, because it did not buy them.
   */
  comparable: {
    terms: number;
    baseTotal: PriceHundredths;
    altTotal: PriceHundredths;
    delta: PriceHundredths;
  };
  /** Terms where D1 genuinely has nothing of the brand. */
  onlyBase: string[];
  /** Terms where the branded product exists and was priced, but did not fit. */
  altOverBudget: string[];
  /** Terms where the branded lookup never answered — unknown, not empty. */
  altUnknown: string[];
  /** Terms D1 returned nothing for, or nothing in stock, on the branded run. */
  altNoMatch: string[];
  /** Terms the branded basket filled and the base one could not. */
  onlyAlt: string[];
  /** Terms neither basket filled — not a brand difference, and not silent either. */
  neither: string[];
  /**
   * Brands actually seen while searching, when the requested one matched
   * nothing anywhere. A typo is otherwise indistinguishable from a brand D1
   * does not carry, and both render as an empty basket.
   */
  brandsSeen?: string[];
}

/**
 * The same shopping list, priced twice: as the best value D1 has, and
 * restricted to one brand.
 *
 * Both runs are fit to the same budget, so the comparison is between two
 * baskets a person could actually have bought, not between one real basket and
 * a hypothetical one that overspends.
 */
export async function compareBaskets(
  client: D1Client,
  terms: readonly string[],
  budget: PriceHundredths,
  opts: BasketOptions & { brand: string },
): Promise<CrossBasket> {
  const want = normalizeBrand(opts.brand);
  if (want === undefined) {
    throw new UsageError("--brand needs a brand name, for example --brand LATTI.");
  }
  const base = await buildBasket(client, terms, budget, { ...opts, brand: undefined });
  const alt = await buildBasket(client, terms, budget, opts);

  // Paired by POSITION, not by term.
  //
  // A Map keyed on the term is last-wins, so `d1 basket --brand X leche leche`
  // silently discarded the first line of each basket — including filled,
  // money-spending ones — and the render then reported that nothing was bought
  // and nothing was comparable about a basket that had bought two things. The
  // dropped line was neither named nor netted, which is the one direction the
  // "named, never netted" rule did not anticipate.
  //
  // `buildBasket` emits exactly one line per input term in order, and
  // `fillToBudget` maps them 1:1, so position is the reliable join. Asserted
  // rather than assumed, because a silent length mismatch would reintroduce the
  // same class of defect through a different door.
  const rows = pairRows(terms, base, alt);

  const shared = rows.filter((r) => r.delta !== undefined);
  const baseTotal = sum(shared.map((r) => r.base?.price ?? 0));
  const altTotal = sum(shared.map((r) => r.alt?.price ?? 0));

  const filled = (l: BasketLine | undefined) => l !== undefined && isFilled(l.status);
  return {
    brand: opts.brand,
    base,
    alt,
    rows,
    comparable: {
      terms: shared.length,
      baseTotal,
      altTotal,
      delta: altTotal - baseTotal,
    },
    // Split by WHY, not lumped under one sentence. `over-budget` is a fact
    // about the shopper's wallet and `replacement-unknown` is a fact about the
    // network; reporting either as "no LATTI for this" turns them into facts
    // about D1's shelf.
    onlyBase: rows
      .filter((r) => filled(r.base) && !filled(r.alt) && r.alt?.status === "no-brand-match")
      .map((r) => r.term),
    altOverBudget: rows
      .filter((r) => filled(r.base) && r.alt?.status === "over-budget")
      .map((r) => r.term),
    altUnknown: rows
      .filter((r) => filled(r.base) && r.alt?.status === "replacement-unknown")
      .map((r) => r.term),
    altNoMatch: rows
      .filter(
        (r) =>
          filled(r.base) && (r.alt?.status === "no-match" || r.alt?.status === "nothing-in-stock"),
      )
      .map((r) => r.term),
    onlyAlt: rows.filter((r) => filled(r.alt) && !filled(r.base)).map((r) => r.term),
    // Neither side filled these, so they are not a brand difference at all —
    // but a row of two dashes with no sentence beside it leaves the reader to
    // guess, which is the one thing this output is built not to do.
    neither: rows.filter((r) => !filled(r.base) && !filled(r.alt)).map((r) => r.term),
    // Offered only when NO line ever saw a product of the brand.
    //
    // `!isFilled` was wrong and said so out loud: `over-budget` means the
    // branded product was found and priced and refused on money, and
    // `replacement-unknown` means the lookup never answered. Both rendered
    // "Nothing D1 returned for these terms is LATTI" directly above "Brands it
    // did return: LATTI" — two adjacent sentences in contradiction, and the
    // second one is the true one.
    // Offered only when a line actually LOOKED for the brand and did not find
    // it. `every(no-brand-match || no-match)` was still too wide: `no-match`
    // means D1 returned nothing at all for the term, which is not about the
    // brand, and a single typo'd term then printed "Nothing D1 returned for
    // these terms is LATTI" four lines above "that is not about LATTI". So at
    // least one line must be `no-brand-match` — the only status that means the
    // brand was searched for and missing.
    // EVERY line must have looked for the brand and missed.
    //
    // Three rounds narrowed this and each left one arm open, so it is now the
    // strictest reading there is: `no-match` means D1 returned nothing at all
    // for the term, which says nothing whatever about the brand, and mixing it
    // in let a two-term list print "Nothing D1 returned for these terms is
    // LATTI" about a list where LATTI was never the reason.
    brandsSeen:
      alt.lines.length && alt.lines.every((l) => l.status === "no-brand-match")
        ? brandsIn(base.lines, want).slice(0, 12)
        : undefined,
  };
}

/**
 * Join the two baskets, by POSITION.
 *
 * Exported so the join itself is testable — the length guard below is
 * unreachable from `compareBaskets` today and a mutation deleting it therefore
 * survived the whole suite.
 *
 * A Map keyed on the term is last-wins, so `d1 basket --brand X leche leche`
 * silently discarded the first line of each basket, including filled,
 * money-spending ones. `buildBasket` emits exactly one line per input term in
 * order and `fillToBudget` maps them 1:1, so position is the reliable join —
 * asserted rather than assumed, because a silent length mismatch would
 * reintroduce the same defect through a different door.
 */
/**
 * A term's label in the comparison, disambiguated when the shopper repeated it.
 *
 * The buckets below project rows back to strings. With a bare term, a list
 * containing `aceite` twice — one row filled, one not — printed
 * "no LATTI for: aceite" and "Neither basket filled: aceite" about the same
 * name, which are mutually exclusive claims. A label that is unique per row
 * makes them separate lines about separate rows.
 */
export function rowLabels(terms: readonly string[]): string[] {
  const count = new Map<string, number>();
  for (const t of terms) count.set(t, (count.get(t) ?? 0) + 1);

  const seen = new Map<string, number>();
  const labels = terms.map((term) => {
    if ((count.get(term) ?? 0) < 2) return term;
    const n = (seen.get(term) ?? 0) + 1;
    seen.set(term, n);
    return `${term} (#${n})`;
  });

  // Verified, not assumed. Any suffix scheme that leaves unique terms bare can
  // collide: a list containing both `aceite` (twice) and the literal string
  // `aceite (#1)` produces that label twice, and the two rows then land in two
  // mutually exclusive buckets under one name — the very defect the labels
  // exist to prevent. The row index cannot collide, so falling back to it is
  // the only construction that is right for every input.
  if (new Set(labels).size === labels.length) return labels;
  return terms.map((term, i) => `${i + 1}. ${term}`);
}

export function pairRows(
  terms: readonly string[],
  base: BasketPlan,
  alt: BasketPlan,
): BasketComparison[] {
  if (base.lines.length !== terms.length || alt.lines.length !== terms.length) {
    throw new D1Error(
      `Basket comparison expected one line per term (${terms.length}), got ${base.lines.length} and ${alt.lines.length}. This is a bug in d1-cli.`,
    );
  }
  const labels = rowLabels(terms);
  return terms.map((_term, i) => {
    const term = labels[i] as string;
    const bl = base.lines[i];
    const al = alt.lines[i];
    const both = bl && al && isFilled(bl.status) && isFilled(al.status);
    return {
      term,
      base: bl,
      alt: al,
      delta:
        both && bl.price !== undefined && al.price !== undefined ? al.price - bl.price : undefined,
    };
  });
}

/**
 * Distinct brands among the products a basket actually CHOSE, for a typo hint.
 *
 * Filled lines only. An unfilled line still carries `product: source` — the
 * thing it rejected — so reading every line printed "Brands it did return:
 * LATTI" directly under "Nothing D1 returned for these terms is LATTI",
 * sourcing the contradiction from a product the basket had refused.
 *
 * The requested brand is excluded outright. If it appears in this list the
 * headline above it is false, and no hint is worth printing a lie for.
 */
function brandsIn(lines: readonly BasketLine[], exclude?: string): string[] {
  const seen = new Set<string>();
  for (const l of lines) {
    if (!isFilled(l.status)) continue;
    const b = l.product?.brand?.trim();
    if (b && normalizeBrand(b) !== exclude) seen.add(b);
  }
  return [...seen].sort((x, y) => x.localeCompare(y));
}
