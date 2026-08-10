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
  /** The replacement lookup itself failed, so stock here is UNKNOWN, not empty. */
  | "replacement-unknown"
  | "no-match";

/**
 * How narrowing the page to products NAMED after the term affected a line.
 *
 * Absent is the third state and the common one: narrowing did not move the
 * answer, so there is nothing to disclose.
 */
export type TermFilter = "none-matched" | "changed-pick";

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
  /**
   * How narrowing the page to products NAMED after the term affected this line.
   *
   * - `"none-matched"` — nothing D1 returned carries the term, so the line was
   *   chosen from the unfiltered set.
   * - `"changed-pick"` — narrowing changed which product fills the line. The
   *   dangerous case: enough products carry the word to keep the pool
   *   non-empty while the ones that ARE the thing asked for do not.
   *
   * Absent means narrowing did not change the answer. It does NOT mean the
   * pick is semantically right, only that the filter did not move it.
   */
  termFilter?: TermFilter;
  /**
   * What the line would have held WITHOUT the name narrowing, when narrowing
   * moved it.
   *
   * Carried so the disclosure can state a fact the reader can act on instead of
   * predicting wrongness. Narrowing changes the pick on every term where it
   * helps as well as every term where it hurts, so a warning phrased as "this
   * may not be what you meant" is false on the majority of the lines it fires
   * on — and a guard that is itself false is the defect it was added to close.
   * Naming the displaced product lets the reader decide in one glance.
   */
  widePick?: Product;
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

/**
 * Accent-stripped, lower-cased text for substring matching.
 *
 * Deliberately NOT `catalog.slugify`, which hyphenates word breaks for URL
 * slugs. Hyphens would break `includes` across the word boundaries this needs
 * to match through, so the two foldings are different functions with different
 * contracts rather than one reused wrongly.
 */
function foldText(s: string): string {
  return s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/**
 * Crudest possible Spanish plural stem, applied to the QUERY token only.
 *
 * A shopper types `huevos`; every product D1 sells is named `Huevo …`. Matching
 * the raw token would find nothing and fall through to the unfiltered set,
 * which is precisely the bug this exists to close — so the plural has to be
 * handled or the filter is decorative on the commonest terms.
 *
 * The length floors stop `gas` → `ga` and `mes` → `m`. This is not a stemmer
 * and is not trying to be: it runs on one or two shopper-typed words, and its
 * failure mode is only ever a WIDER match, never a wrongly-excluded product.
 */
function stemToken(t: string): string {
  if (t.length > 4 && t.endsWith("es")) return t.slice(0, -2);
  if (t.length > 3 && t.endsWith("s")) return t.slice(0, -1);
  return t;
}

/**
 * Does this product's name name the term the shopper typed?
 *
 * Every whitespace-separated token of the term must appear in the product name,
 * accent-folded and plural-stemmed. `leche entera` therefore requires both
 * words, not either.
 *
 * This is a NAME test, not a semantic one. It removes the products that are not
 * plausibly the thing asked for; it cannot rank the ones that remain, and a
 * product whose name merely contains the word still passes.
 */
export function matchesTerm(name: string, term: string): boolean {
  const folded = foldText(name);
  const tokens = foldText(term).split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  return tokens.every((t) => folded.includes(stemToken(t)));
}

export function chooseBest(products: readonly Product[]): Choice | undefined {
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

    // Narrow to the products whose NAME carries the term before anything reads
    // this page.
    //
    // D1's search is loose: `huevos` returns 139 matches including yogurt and
    // mozzarella. `chooseBest` takes a measure census over whatever it is
    // given, so off-term products do not merely compete — they can WIN the
    // census and evict every on-term product from the comparison before
    // ranking starts. Live, `leche` returned bread: the litre-measured milk was
    // never ranked, because kg-measured off-term products outnumbered it.
    //
    // The fallback keeps the old population rather than failing the line, and
    // marks it, so a term D1 answers only with differently-named products still
    // gets an answer and the answer says what it is.
    const onTerm = page.products.filter((p) => matchesTerm(p.name, term));
    const noneMatched = onTerm.length === 0;
    const pool = noneMatched ? page.products : onTerm;

    const best = chooseBest(pool);

    // Disclose whenever the narrowing AFFECTED the answer, not only when it
    // excluded everything.
    //
    // The first version disclosed only the empty case, and that left the one
    // state where narrowing is both wrong and silent: enough products carry the
    // word to keep the pool non-empty, while the products that ARE the thing
    // asked for do not carry it. `pasta` is the live case — D1 names dry pasta
    // by shape (`Spaghetti`, `Fettuccine`), never "pasta", but four kitchen
    // utensils do, so the filter kept a `Pinza para Pasta` and dropped the
    // whole aisle. D1's own top hit for `pasta` is toothpaste, so relevance
    // order cannot rescue it either.
    //
    // Comparing the two picks is the honest test: it asks the only question
    // that matters to a reader — did filtering change what you are being
    // handed? — instead of a proxy for it.
    const wide = noneMatched ? best : chooseBest(page.products);
    const termFilter: TermFilter | undefined = noneMatched
      ? "none-matched"
      : best?.product.skuId !== wide?.product.skuId
        ? "changed-pick"
        : undefined;

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
        termFilter,
        widePick: termFilter === "changed-pick" ? wide?.product : undefined,
        alternatives: best.alternatives,
      });
      continue;
    }
    // No eligible product. Either D1 returned nothing at all for the term, or
    // everything it returned is out of stock.
    //
    // Take the source from `pool`, not `page.products`. Both are in D1's
    // relevance order, so this is still "the best-matching product" — but
    // sweeping the category of an OFF-term product is how a sold-out `arroz`
    // once produced "replaces SAL REFINADA". Filtering first makes the
    // sweep start from something that at least names the term.
    const source = pool[0];
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
        // `pool`, not `page.products`. `product` above is `pool[0]`, so
        // counting the unfiltered page here would report a numerator and a
        // denominator drawn from two different populations.
        compared: pool.length,
        matched,
        termFilter,
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
        termFilter,
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
      // The narrowing decided which product was SWEPT FROM, so it reaches this
      // line too. Computing the flag and attaching it only to the direct-fill
      // push left it set on the object and unprintable — a disclosure that
      // exists and never renders.
      termFilter,
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
