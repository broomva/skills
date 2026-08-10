/**
 * The one property every render in this skill is built around: **no two
 * sentences printed together may contradict each other.**
 *
 * It failed four consecutive review rounds. Each round found one live pair,
 * each fix conditioned one clause on one more piece of state, and the next
 * round found the arm that fix had left open. The defect was never in any
 * particular sentence — it was that the property was only ever checked by
 * example, and an example is one cell of a table nobody had drawn.
 *
 * So this draws the table. It enumerates the reachable render states rather
 * than a few interesting ones, and asserts the property over all of them. A
 * new sentence that contradicts an existing one now fails here without anyone
 * having to think of the case.
 */

import { describe, expect, test } from "bun:test";
import {
  type BasketLine,
  type BasketPlan,
  type CrossBasket,
  type LineStatus,
  crossFromPlans,
  isFilled,
} from "../src/basket.ts";
import { MAX_COUNT } from "../src/catalog.ts";
import { sum } from "../src/money.ts";
import { renderComparison, renderStores } from "../src/present.ts";
import type { StoresResult } from "../src/stores.ts";
import type { Product } from "../src/types.ts";

const BRAND = "LATTI";

const product = (name: string, price: number, brand = "OTRA", unitPrice?: number): Product => ({
  productId: "p",
  skuId: "1",
  name,
  brand,
  // Set, because round 11's new like-for-like rule reads it — and occurred in
  // 0 of 18,816 states while this fixture left it undefined.
  unitPrice,
  size: unitPrice === undefined ? undefined : { measure: "kg", amount: 1 },
  linkText: "",
  categories: [],
  offers: [
    {
      sellerId: "1",
      sellerName: "Tiendas D1",
      price,
      listPrice: price,
      available: true,
      availableQuantity: 5,
    },
  ],
  warnings: [],
});

const ALL_STATUSES: LineStatus[] = [
  "filled",
  "filled-by-substitute",
  "over-budget",
  "nothing-in-stock",
  "replacement-unknown",
  "no-brand-match",
  "no-match",
];

/**
 * One line's worth of DATA — nothing derived.
 *
 * Everything here is a fact a live run could hand back: a status, a page width,
 * a category width, two brand lists. What those facts IMPLY is derived by
 * production, in {@link crossFromPlans}.
 */
interface Shape {
  term: string;
  status: LineStatus;
  /** Brands D1 returned on this term's own search page. */
  pageBrands: string[];
  /** Brands the category sweep returned, when one ran. */
  sweepBrands: string[];
  /** `looked` short of `matched` — the search page was cut by `--count`. */
  partial: boolean;
  /** `swept` short of `categoryTotal` — the sweep read one page of a bigger category. */
  sweepPartial: boolean;
  /** Total D1 matched for the term, so two rows can differ. */
  matched: number;
  /** Measure the pick was ranked on, so a mixed-measure delta is reachable. */
  rankedOn?: string;
  /** Unit price, so the "cheaper pack, dearer per unit" arm is reachable. */
  unitPrice?: number;
  /** Pack price, so a row can have a NEGATIVE delta and not merely a zero one. */
  price?: number;
  /**
   * Whether an `over-budget` line came from the CATEGORY rather than the page.
   *
   * Production produces both — a page hit that does not fit, and a substitute
   * `fillToBudget` downgraded, which keeps its `replaces` — and the render says
   * different things about them. Pinning it either way leaves one arm dead.
   */
  fromCategory?: boolean;
  /** Cheaper things that would have fitted, on an over-budget line. */
  affordable?: number;
}

function lineFor(s: Shape): BasketLine {
  const named = s.status !== "no-match";
  // The four statuses production sweeps a category on (`basket.ts`).
  const sweeps =
    s.status === "no-brand-match" ||
    s.status === "filled-by-substitute" ||
    s.status === "nothing-in-stock";
  return {
    term: s.term,
    status: s.status,
    compared: 1,
    // A PARTIAL look is its own axis. `matched > looked` is what makes
    // `partialLook` fire, and before round 8 no state in this file set either
    // field — so `c.partial` was `undefined` in all 98 states and every
    // sentence that has a scoped variant was checked in one polarity only.
    // Round 6's entire fix — a categorical claim never outruns its look — was
    // unprotected by the property test written to protect it.
    // ABSENT on the stock substitute path, because production never sets it
    // there (`buildBasket`'s `filled-by-substitute` push carries no `looked`).
    // `renderBasket`'s footer falls back to `compared` for exactly this case,
    // and the fallback was unexercised while every fixture line had a `looked`.
    looked:
      s.status === "filled-by-substitute"
        ? undefined
        : s.partial
          ? Math.floor(s.matched / 2)
          : s.matched,
    matched: s.matched,
    product: named ? product(`PRODUCTO ${s.term}`, 300_000, "OTRA", s.unitPrice) : undefined,
    price: isFilled(s.status) ? (s.price ?? 300_000) : undefined,
    // FOUR statuses, because production sets it on four (`basket.ts`: both
    // `filled-by-substitute` sites, the empty sweep, and `no-brand-match`).
    // Setting it on one made five production sentences occur in 0 of 4,704
    // states — including round 10's own "replacing … from its category" and the
    // whole replacement arm of `footerFor`, which `renderComparison` had just
    // been taught to call. A fixture that is narrower than production makes the
    // enumeration quietly smaller than it claims to be.
    substituteSweep:
      s.status === "no-brand-match" ||
      s.status === "filled-by-substitute" ||
      s.status === "nothing-in-stock",
    // `fillToBudget` keeps `replaces` when it downgrades a substitute line to
    // `over-budget`, so production carries it on both statuses — and it is the
    // input to "found only in the category around it", which was at 0 states.
    replaces:
      s.status === "filled-by-substitute" || (s.status === "over-budget" && s.fromCategory)
        ? product(`FUENTE ${s.term}`, 300_000, "OTRA")
        : undefined,
    rankedOn: isFilled(s.status) ? s.rankedOn : undefined,
    // The pack-price fallback, which is what an absent `rankedOn` means.
    byPackPrice: isFilled(s.status) && s.rankedOn === undefined,
    // The CATEGORY denominator, which round 9 found had no reader at all. A
    // `no-brand-match` verdict is decided by this sweep and not by the page, so
    // an enumeration that never sets it cannot see a universal asserted over a
    // partial one — and could not, through nine rounds.
    // ...on the lines that ACTUALLY swept, and no others.
    //
    // Every line — both rows, both plans — used to carry these, which made
    // "the alt line swept and the base line did not" unrepresentable. That is
    // what production always produces, and it is why `brandMissFor` reading
    // `row.base` instead of `row.alt` survived the whole suite while printing
    // an unqualified categorical claim over a 10-of-41 sweep.
    swept: sweeps ? (s.sweepPartial ? 10 : 41) : undefined,
    categoryTotal: sweeps ? 41 : undefined,
    // Set only where the line was refused on money, as production does — the
    // input to round 11's "N cheaper matches would have fitted" clause, which
    // occurred in 0 of 18,816 states because this was never set.
    affordableAlternatives: s.status === "over-budget" ? (s.affordable ?? 2) : undefined,
    // Set, because production always sets it and the live defect lived here.
    // Whether the page CARRIED the requested brand is its own axis: D1 returning
    // a COPELIA product at Price 0 and D1 returning no COPELIA at all are
    // different facts that produce different headlines, and an enumeration
    // fixing one of them can never exercise the other.
    pageBrands: named ? s.pageBrands : [],
    // ...and whether the CATEGORY SWEEP carried it is a third. Round 6 added
    // this population to production's returned-brand test and round 7 kept the
    // display list on the page alone — correctly — which made "brand in the
    // sweep but not on the page" a reachable state in which the headline and
    // the list beside it disagreed. No state here could produce it, because
    // this fixture never set the field at all.
    sweepBrands: named ? s.sweepBrands : [],
  };
}

const planOf = (lines: BasketLine[]): BasketPlan => ({
  budget: 10_000_000,
  lines,
  total: sum(lines.filter((l) => isFilled(l.status)).map((l) => l.price ?? 0)),
  remaining: 10_000_000,
});

/**
 * A comparison built the way production builds one.
 *
 * The plans are DATA — a test is entitled to invent what D1 returned. Every
 * conclusion drawn from them comes from `crossFromPlans`, which is the function
 * `compareBaskets` itself calls.
 *
 * This used to hand-assemble the `CrossBasket` literal, and each round found
 * one more field of it drifted from production. Round 4 converted one of two;
 * round 8 converted two of three, in the same commit series that wrote down
 * "convert every derived field". `brandMissed` was the survivor: deleting
 * production's gate for it changed real output and failed nothing here. The
 * class only closes when there is nothing left to mirror.
 *
 * TWO rows, of DIFFERENT widths. One row made three whole families of defect
 * structurally unreachable — per-term-versus-aggregate divergence, mixed
 * buckets, and a denominator summed across terms and printed as one term's own.
 * All three were live at the time the one-row enumeration was passing.
 */
function crossOf(opts: {
  baseStatus: LineStatus;
  altStatus: LineStatus;
  pageBrands: string[];
  sweepHasBrand: boolean;
  partial: boolean;
  sweepPartial: boolean;
  /** The second row's own (base, alt) pair, or "same" to mirror the first. */
  second: readonly [LineStatus, LineStatus] | "same";
  /**
   * Whether row TWO carries the same brand evidence as row one.
   *
   * The axis that made round 10's blocker invisible. `pageBrands`/`sweepBrands`
   * were spread from one `common` object into both rows of both plans, so every
   * row's brand evidence was identical in all 4,704 states and the state
   * "brand on term A's page, absent from term B's" — the state the headline was
   * false in, live, at ordinary flags — was structurally unreachable. Two rows
   * are not two rows if they are handed the same facts.
   */
  secondHasBrand?: boolean;
  count?: number;
}): CrossBasket {
  const sweep = opts.sweepHasBrand ? [BRAND] : [];
  const [secondBase, secondAlt] =
    opts.second === "same" ? [opts.baseStatus, opts.altStatus] : opts.second;

  // Row two is DELIBERATELY narrower and against a smaller shelf, so any
  // sentence printing an aggregate where a per-term number belongs shows a
  // number no term has.
  const shape = {
    partial: opts.partial,
    sweepPartial: opts.sweepPartial,
  };
  const first = { ...shape, pageBrands: opts.pageBrands, sweepBrands: sweep, fromCategory: true };
  // Row two's evidence is its OWN. With `secondHasBrand: false` it holds no
  // trace of the requested brand in either population, which is exactly the
  // shape `--brand "NATURAL FEELING" leche arroz` produces live.
  const secondPage = opts.secondHasBrand === false ? ["OTRA"] : opts.pageBrands;
  const secondSweep = opts.secondHasBrand === false ? [] : sweep;
  const second = { ...shape, pageBrands: secondPage, sweepBrands: secondSweep };
  const baseLines = [
    lineFor({ ...first, term: "arroz", status: opts.baseStatus, matched: 29, rankedOn: "kg" }),
    lineFor({
      ...second,
      term: "leche",
      status: secondBase,
      matched: 18,
      rankedOn: "kg",
      unitPrice: 500,
    }),
  ];
  const altLines = [
    lineFor({ ...first, term: "arroz", status: opts.altStatus, matched: 29, rankedOn: "L" }),
    lineFor(
      opts.second === "same"
        ? // No comparable measure: `chooseBest`'s pack-price fallback, where
          // `rankedOn` is absent and `byPackPrice` is set. Production never
          // sets both, so neither may the fixture.
          { ...second, term: "leche", status: secondAlt, matched: 18 }
        : // Same axis as the base line, cheaper pack, WORSE unit price — the
          // shape round 11's guard claimed to catch and asserted backwards.
          {
            ...second,
            term: "leche",
            status: secondAlt,
            matched: 18,
            rankedOn: "kg",
            price: 200_000,
            unitPrice: 900,
          },
    ),
  ];

  return crossFromPlans(["arroz", "leche"], planOf(baseLines), planOf(altLines), {
    brand: BRAND,
    count: opts.count,
  });
}

/**
 * Pairs of sentences that cannot both be true.
 *
 * Each entry is the *reason* a pair is contradictory, so a failure names the
 * defect rather than a line number. All four rounds' findings are here.
 */
/** The evidence list's label, either scoping. Both are the PAGE population. */
const LIST_LABEL = `Brands (?:on these terms' own pages|among the \\d+ products looked at across \\d+ terms?)`;
/**
 * The brand as a COMPLETE list item, not a word inside one. `\bLATTI\b` also
 * matched "LATTI FOODS", which is a different brand and precisely the near-miss
 * the hint exists to surface — flagging it would fire on the feature working.
 */
const AS_LIST_ITEM = `(?:[^\\n]*, )?${BRAND}(?:,|\\.)`;

const FORBIDDEN: Array<{ why: string; a: RegExp; b: RegExp; regressionOnly?: boolean }> = [
  {
    why: "claims the brand is absent from what D1 returned, while naming it among the brands returned",
    // LIVE again. It was marked a regression guard because production excluded
    // the requested brand from the hint, which made the pair unobservable — the
    // guard was reporting a real defect (the exclusion deleted the evidence and
    // kept the claim) and the exemption silenced it. The claim is conditioned on
    // the evidence now, the list is complete, and this rule can fire.
    a: new RegExp(`Nothing D1 returned for these terms is ${BRAND}\\.`),
    b: new RegExp(`${LIST_LABEL}: ${AS_LIST_ITEM}`),
  },
  {
    why: "says D1 returned the brand ON THE TERM PAGES, while the page list beside it omits it",
    // ROUND 8, live. The mirror image of the rule above, and the one the arc
    // kept walking into from a new direction. Round 5 fixed "claim without the
    // evidence"; round 7 correctly narrowed the list to the page alone; the
    // combination then produced a claim drawn from page-OR-sweep sitting on top
    // of a list drawn from the page. With the brand only in the sweep:
    //
    //   D1 returned LATTI for these terms, but nothing of it can be bought…
    //   Brands it did return: OTRA.
    //
    // Two sentences that read as answers to one question, disagreeing. The fix
    // is that the claim names its own population, so this rule is about the
    // page-scoped wording specifically — the category wording is a different
    // sentence about a different set and cannot contradict this list.
    a: new RegExp(`D1 returned ${BRAND} for these terms`),
    // A list line that does NOT carry the brand as a complete item. The
    // lookahead is what makes this an omission check rather than a presence
    // one; without a list line printed at all there is nothing to contradict,
    // which is why the label is required to match.
    b: new RegExp(`${LIST_LABEL}: (?!${AS_LIST_ITEM})`),
  },
  {
    why: "claims the brand is absent, while a line says the absence is not about the brand",
    regressionOnly: true,
    a: new RegExp(`Nothing D1 returned for these terms is ${BRAND}\\.`),
    // The clause this catches has been removed, so this rule is a REGRESSION
    // guard rather than a live finding. "Neither basket filled: X" alone is not
    // contradictory — both sentences can be true at once, and an earlier draft
    // of this rule wrongly said otherwise.
    b: /that is not about /,
  },
  {
    why: "claims the brand is absent, while a line prices it",
    a: new RegExp(`Nothing D1 returned for these terms is ${BRAND}\\.`),
    b: new RegExp(`found but over budget|only ${BRAND} could fill|BOTH filled`),
  },
  {
    why: "claims the brand is no alternative to anything, while a line says it was the only thing that could fill a term",
    regressionOnly: true,
    a: /not an alternative/,
    b: /only .* could fill/,
  },
  {
    why: "claims the brand is no alternative to anything, while a line prices it over budget",
    regressionOnly: true,
    a: /not an alternative/,
    b: /found but over budget/,
  },
  {
    why: "claims the brand is no alternative to anything, while a lookup never answered so nothing is known",
    regressionOnly: true,
    a: /not an alternative/,
    b: /lookup did not answer/,
  },
  {
    why: "reports a price comparison and simultaneously says there is none to report",
    a: /BOTH filled:/,
    b: /no price to compare|nothing to compare/,
  },
  {
    why: "says D1 returned the brand FOR THESE TERMS, while a per-term line says it returned none for one of them",
    // ROUND 10's blocker, found live by two reviewers independently and
    // invisible to 4,704 enumerated states because every row was handed the
    // same brand evidence. `arroz` is one of "these terms":
    //
    //   D1 returned NATURAL FEELING for these terms, but nothing of it…
    //   Not counted — neither its page nor its category holds any NATURAL FEELING, for: arroz.
    //
    // The universal wording is the only one this rule forbids — "for some of
    // these terms" is the honest form and must coexist with the line below it.
    a: new RegExp(`D1 returned ${BRAND} (?:for|in the category around) these terms`),
    b: new RegExp(`Not counted — neither its page nor its category holds any ${BRAND}`),
  },
  {
    why: "says a term was not counted for two mutually exclusive reasons",
    a: /Not counted — (?:no|D1 returned no) .* for: (?:[^\n]*, )?arroz\b/,
    b: /Neither basket filled: (?:[^\n]*, )?arroz\b/,
  },
];

/**
 * Every reachable render state, as (label, output) pairs.
 *
 * One generator for all four tests below. They had three copies of the same
 * quadruple-nested loop, and round 8 added two axes — a shape where updating
 * three of four call sites leaves a test quietly enumerating less than it
 * claims to, which is this file's own recurring defect wearing a new hat.
 */
/** Page-brand lists: absent, present, and the near-miss that must not be flagged. */
const PAGE_LISTS: string[][] = [["OTRA"], ["OTRA", BRAND], ["OTRA", `${BRAND} FOODS`]];

/**
 * The second row's own status pair.
 *
 * `"same"` keeps the two rows uniform, which is what makes an all-`no-brand-match`
 * basket — and therefore the headline block — reachable for every status. The
 * other three are deliberately MIXED, which is the shape a one-row enumeration
 * could not produce and where the per-term sentences went wrong live.
 */
const SECOND_ROW: Array<readonly [LineStatus, LineStatus] | "same"> = [
  "same",
  ["filled", "filled"],
  ["filled", "no-brand-match"],
  ["no-match", "no-brand-match"],
];

function everyState(): Array<{ label: string; out: string; state: CrossBasket }> {
  const states: Array<{ label: string; out: string; state: CrossBasket }> = [];
  for (const baseStatus of ALL_STATUSES) {
    for (const altStatus of ALL_STATUSES) {
      for (const pageBrands of PAGE_LISTS) {
        for (const sweepHasBrand of [true, false]) {
          for (const partial of [true, false]) {
            for (const sweepPartial of [true, false]) {
              for (const second of SECOND_ROW) {
                for (const secondHasBrand of [true, false]) {
                  // At the clamp the advice must change wording, and that arm
                  // was unreachable while `crossOf` accepted a `count` nothing
                  // passed — `c.count` was 12 in every state.
                  for (const count of [12, MAX_COUNT]) {
                    // The NATIONAL disclosure is its own arm and had no
                    // enumerated state — `everyState` hardcoded a region.
                    for (const regionId of ["v2.TEST", undefined]) {
                      const state = crossOf({
                        baseStatus,
                        altStatus,
                        pageBrands,
                        sweepHasBrand,
                        partial,
                        sweepPartial,
                        second,
                        secondHasBrand,
                        count,
                      });
                      states.push({
                        label: `${baseStatus} / ${altStatus} / page [${pageBrands}] / sweep ${sweepHasBrand} / partial ${partial} / sweepPartial ${sweepPartial} / second ${second} / row2brand ${secondHasBrand} / count ${count} / region ${regionId}`,
                        out: renderComparison(state, { regionId }),
                        state,
                      });
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
  return states;
}

describe("no two sentences the comparison prints can contradict each other", () => {
  test("across every reachable (base, alt) status pair", () => {
    const offenders: string[] = [];
    for (const { label, out } of everyState()) {
      for (const { why, a, b } of FORBIDDEN) {
        if (a.test(out) && b.test(out)) offenders.push(`${label}: ${why}\n${out}\n`);
      }
    }
    expect(offenders).toEqual([]);
  });

  test("no categorical brand claim outruns a partial look", () => {
    // Round 6's rule, enforced over the enumeration rather than by example.
    // Round 6 fixed the "Nothing D1 returned…" arm and never touched the
    // "found but unbuyable" one, so with `--count 12` against 29 matches the
    // output still asserted "nothing of it can be bought at this store" — a
    // universal over twelve products. The suite pinned it: the one test
    // covering that state asserted `not.toContain("Nothing among the")` and
    // nothing about the denominator.
    // EVERY unqualified universal this render can print, not just the headline.
    // The first pass of this test checked the headline alone, and a mutation
    // reverting the per-term cause line to `found but not buyable here` — the
    // same universal, four lines lower — survived the whole suite. Six rounds
    // of this arc were spent discovering that fixing one sentence leaves the
    // next one open, so the check is over the set.
    //
    // These are the CURRENT wordings, and the liveness check below is why that
    // sentence needs writing. Round 11 renamed three of the four strings this
    // list watched and did not update it, so the test named after this arc's
    // central invariant became inert: deleting all four patterns left the suite
    // at 595 pass. A check whose subject can be renamed out from under it is
    // not a check, and this file already enforces exactly that rule for
    // `FORBIDDEN` two tests down — it simply did not cover this list.
    const UNSCOPED = [
      /but nothing of it that was searched can be bought here\./,
      /and nothing of it there is buyable, for/,
      /neither its page nor its category holds any LATTI, for/,
      /Nothing D1 returned for these terms is/,
    ];
    // Each pattern must match SOMEWHERE, or it is a rule about a string the
    // render cannot produce. These are the unqualified forms, so they belong in
    // complete-look states and nowhere else — this half proves they exist, the
    // half below proves they never escape into a partial one.
    const everywhere = everyState();
    const dead = UNSCOPED.filter((u) => !everywhere.some((s) => u.test(s.out)));
    expect(dead).toEqual([]);
    const unscoped: string[] = [];
    for (const { label, out, state } of everywhere) {
      // Gated on the STATE, not on the output.
      //
      // The first version of this gate read `/Raise --count/` off the rendered
      // string — a marker the fix under test is itself responsible for
      // emitting. A faithful revert of that fix deletes the marker, the state
      // is skipped, and the test stays green while the defect is back. Proven
      // by a mutation pair differing only in whether the marker survived. A
      // check may never take its precondition from the thing it is checking.
      if (!state.partial && !state.sweepPartial) continue;
      for (const u of UNSCOPED) {
        if (u.test(out)) {
          unscoped.push(`${label}: unqualified universal ${u} beside a partial look\n${out}\n`);
        }
      }
    }
    expect(unscoped).toEqual([]);
  });

  test("no sentence claims a population this CLI never has evidence for", () => {
    // UNCONDITIONAL, and that is the point.
    //
    // Every scope defect from round 5 to round 10 was fixed by hedging one
    // sentence in the states where it was already suspect, and the next round
    // found the state that fix had left. The store-wide claim was the widest
    // instance: "nothing of it can be bought at this store", drawn from two
    // term pages and their two category sweeps, and live-false — the same run
    // denied NATURAL FEELING while `d1 search jabon` returns eight buyable
    // NATURAL FEELING products at that store, with exit 3 beside it.
    //
    // A state-gated check cannot catch that, because the sentence fired
    // precisely where both looks were COMPLETE. The evidence this CLI can hold
    // is bounded by construction — some terms' pages and some categories — so
    // a store-wide claim is wrong in every state, and the check is too.
    const STORE_WIDE = [/at this store/, /in this store/, /D1 does not (?:carry|sell)/, /anywhere/];
    const offenders: string[] = [];
    for (const { label, out } of everyState()) {
      for (const p of STORE_WIDE) {
        if (p.test(out)) offenders.push(`${label}: store-wide claim ${p}\n${out}\n`);
      }
    }
    expect(offenders).toEqual([]);

    // ...and it fires on a real historical output rather than on a literal
    // written to satisfy it: this is round 10's actual headline, which is what
    // the rule exists to keep out. Asserting a regex against a hand-typed
    // string proves only that the regex compiles.
    const roundTen =
      "D1 returned NATURAL FEELING for these terms, but nothing of it can be bought at this store.";
    expect(STORE_WIDE.some((p) => p.test(roundTen))).toBe(true);
    // ...and does not fire on the wording that replaced it.
    const roundEleven =
      "D1 returned NATURAL FEELING for these terms, but nothing of it that was searched can be bought here.";
    expect(STORE_WIDE.some((p) => p.test(roundEleven))).toBe(false);
  });

  test("the not-like-for-like count never outruns the rows it says 'those' about", () => {
    // "N of those rows compare…" — "those" is `comparable.terms`, the rows that
    // produced the delta. Dropping `notLikeForLike`'s `delta === undefined`
    // gate counts a row that was never compared, and the sentence then
    // discounts part of a number that row never contributed to.
    const offenders: string[] = [];
    for (const { label, out, state } of everyState()) {
      expect(state.notLikeForLike.length).toBeLessThanOrEqual(state.comparable.terms);
      const m = out.match(/^(\d+) of those rows? compares?/m);
      if (m && Number(m[1]) > state.comparable.terms) {
        offenders.push(`${label}: claims ${m[1]} of ${state.comparable.terms} compared rows`);
      }
    }
    expect(offenders).toEqual([]);
  });

  test("the prose and the JSON agree about which rows are not like for like", () => {
    // `--json` carried no such field, so a consumer reading identical
    // `rankedOn`, `size.measure` and `size.amount` would correctly conclude the
    // row WAS like for like while the prose said the opposite.
    let checked = 0;
    for (const { label, out, state } of everyState()) {
      for (const nl of state.notLikeForLike) {
        checked += 1;
        expect(`${label}: ${out}`).toContain(`${nl.term}: ${nl.why}`);
      }
    }
    expect(checked).toBeGreaterThan(0);
  });

  test("no per-term sentence prints a number no term actually has", () => {
    // Round 9, found independently by two reviewers. `partialLook` sums across
    // terms and two consumers read the sum as one term's own: with `leche`
    // looking at 12 and `arroz` at 10, the output said "nothing of ALPIN among
    // the 22 looked at, for: leche" and "best among the 22 products fetched for
    // its term". No term fetched 22. A one-row enumeration cannot see this at
    // all, because with one row the sum IS the term's number — which is why
    // this went through 560 green tests.
    const offenders: string[] = [];
    for (const { label, out, state } of everyState()) {
      const perTerm = new Set<number>();
      for (const l of [...state.base.lines, ...state.alt.lines]) {
        if (l.looked !== undefined) perTerm.add(l.looked);
        if (l.swept !== undefined) perTerm.add(l.swept);
      }
      // Every "Not counted" line is ABOUT specific terms, so every count in one
      // must be a count some term really had.
      for (const line of out.split("\n")) {
        if (!line.startsWith("Not counted —")) continue;
        for (const m of line.matchAll(/(\d+) of (\d+) (?:on its page|in its category)/g)) {
          const n = Number(m[1]);
          if (!perTerm.has(n)) offenders.push(`${label}: per-term line cites ${n}\n${line}\n`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  test("a term never appears in two mutually exclusive buckets", () => {
    // Structural, not regex. The buckets project rows back to labels, and a
    // label landing in two of them is two incompatible claims about one row
    // however the sentences happen to be worded — so this reads the buckets
    // rather than the prose, and cannot be defeated by a rewording.
    const offenders: string[] = [];
    for (const { label, state } of everyState()) {
      const buckets: Array<[string, readonly string[]]> = [
        ["onlyBase", state.onlyBase.map((m) => m.term)],
        ["altOverBudget", state.altOverBudget.map((o) => o.term)],
        ["altUnknown", state.altUnknown],
        ["altNoMatch", state.altNoMatch],
        ["altNothingInStock", state.altNothingInStock],
        ["onlyAlt", state.onlyAlt.map((m) => m.term)],
        ["neither", state.neither],
      ];
      const seen = new Map<string, string>();
      for (const [name, terms] of buckets) {
        for (const t of terms) {
          const prior = seen.get(t);
          if (prior) offenders.push(`${label}: "${t}" in both ${prior} and ${name}`);
          else seen.set(t, name);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  test("the enumeration is not vacuous — it really does exercise every sentence", () => {
    // A forbidden-pair check passes trivially if no state produces either
    // sentence. This asserts the render surface is actually being covered, so
    // the test above cannot go green by rendering nothing.
    const MARKERS = [
      "BOTH filled:",
      "no price to compare",
      "neither its page nor its category holds any LATTI, for",
      "found but over budget for",
      "lookup did not answer for",
      "D1 returned nothing at all for",
      "only LATTI could fill",
      "Neither basket filled",
      "Nothing D1 returned for these terms",
      "but nothing of it that was searched can be bought here.",
      // Round 8's four. Each names a population or a denominator, and each was
      // unreachable in this enumeration before the sweep and partial axes
      // existed — which is exactly why the defects they describe survived.
      "in the category around these terms",
      "Brands on these terms' own pages",
      "Brands among the 23 products looked at across 2 terms",
      // Round 10's. The category denominator, the per-term verdicts that replaced
      // one global one, the two disclosures the render never made, and the
      // ceiling-aware advice.
      "in the categories around them",
      "LATTI is on its own page and nothing of it there is buyable, for",
      "LATTI is in the category around it and nothing of it the look reached is buyable",
      "no LATTI in what was searched",
      "What was bought",
      // The five production sentences the fixture could not reach while it set
      // `substituteSweep` on one status where production sets it on four.
      ", replacing ",
      "except a replacement, which is the closest match from its category",
      "Every line here is a replacement",
      "by pack price where D1 publishes no size",
      "--count is already at its ceiling of 50",
      "NOT like for like",
      // Round 11's. The quantifier the headline was assuming, the bucket split
      // out of "returned nothing at all", and the wallet fact that used to read
      // as a shelf fact.
      "for some of these terms",
      "in the category around some of these terms",
      "D1 returned products for this but none of them in LATTI, for",
      "LATTI fitted the budget and the best-value pick did not",
      // Round 12: `baseMissWhy` was split FOUR ways and two arms were never
      // asserted, so replacing either with the default returned "only LATTI
      // could fill" over a failed network lookup — a fact about the network
      // reported as a fact about D1's shelf, the class the split exists for.
      "LATTI filled it and the unconstrained lookup did not answer, for",
      "only LATTI could be bought — D1 returned others and none was buyable, for",
      // ...and the clauses reachable only once the fixture carried the fields
      // production sets, and the enumeration an unregioned state.
      "cheaper matches would have fitted",
      "cheaper pack, dearer per kg",
      "these are NATIONAL prices and stock",
      "found only in the category around it",
      "Raise --count to widen the page look",
      "the category sweep reads one page and --count does not widen it",
    ];
    const seen = new Set<string>();
    for (const { out } of everyState()) {
      for (const marker of MARKERS) if (out.includes(marker)) seen.add(marker);
    }
    // Named, not counted. `toBe(10)` passed just as happily when a marker was
    // replaced as when it was covered, so it could not tell "all ten covered"
    // from "nine covered and one typo'd".
    expect([...seen].sort()).toEqual([...MARKERS].sort());
  });

  test("the enumeration is a table, not one cell repeated", () => {
    // Round 9's measurement, kept as an assertion. Reviewer B instrumented the
    // then-current enumeration and found 1176 iterations collapsing to 40
    // distinct outputs, with three rules structurally unable to fire because
    // `crossOf` built ONE row — so per-term-versus-aggregate divergence, mixed
    // buckets and duplicate terms were all unreachable while being live.
    //
    // Floors, not exact counts: an exact number is a maintenance tax that gets
    // updated to whatever the code now produces, which is how a coverage check
    // stops being one. These are set below what the current axes give and well
    // above what a collapsed enumeration could.
    const states = everyState();
    // Within ~2x of actual, not 5x. At the old floors both axes round 11 added
    // could be deleted and this still passed — every one of eight fixture-axis
    // deletions was caught by the MARKERS check and by nothing here, which is
    // two guards where only one is load-bearing.
    expect(states.length).toBeGreaterThan(18_000);
    expect(new Set(states.map((s) => s.out)).size).toBeGreaterThan(900);
    // The shapes the one-row enumeration could not reach at all.
    const distinctEvidence = (c: CrossBasket) =>
      new Set(c.onlyBase.map((m) => JSON.stringify([m.returnedIn, m.look, m.sweep]))).size;
    expect(states.filter((s) => distinctEvidence(s.state) > 1).length).toBeGreaterThan(0);
    expect(
      states.filter((s) => (s.out.match(/^Not counted —/gm) ?? []).length > 1).length,
    ).toBeGreaterThan(0);
    expect(states.filter((s) => s.state.sweepPartial !== undefined).length).toBeGreaterThan(0);
    expect(states.filter((s) => /NOT like for like/.test(s.out)).length).toBeGreaterThan(0);
  });

  test("every LIVE rule can actually fire — a rule matching nothing proves nothing", () => {
    // Four rules guard sentences this arc DELETED; they are regression guards
    // and are marked as such. Every other rule must have both its sides occur
    // somewhere in the enumeration, or it is a rule about a string the render
    // cannot produce — which passes forever and means nothing. Two of them were
    // exactly that before the mirror stopped re-deriving `brandsIn`.
    const outs = everyState().map((s) => s.out);
    const dead: string[] = [];
    for (const f of FORBIDDEN) {
      if (f.regressionOnly) continue;
      if (!outs.some((o) => f.a.test(o))) dead.push(`side a never occurs: ${f.why}`);
      if (!outs.some((o) => f.b.test(o))) dead.push(`side b never occurs: ${f.why}`);
    }
    expect(dead).toEqual([]);
  });

  test("and a deliberately contradictory render IS caught (control)", () => {
    // Without this the suite cannot distinguish "no contradictions" from "the
    // matcher never matches anything".
    const bad =
      "Nothing D1 returned for these terms is LATTI.\nBrands on these terms' own pages: LATTI, OTRA.";
    const hits = FORBIDDEN.filter((f) => f.a.test(bad) && f.b.test(bad));
    expect(hits.length).toBeGreaterThan(0);

    // ...and so is round 8's, whose control is the OMISSION rather than the
    // presence — a rule with a negative lookahead passes trivially if the
    // lookahead is wrong, and it would never be noticed.
    const badOmission =
      "D1 returned LATTI for these terms, but nothing of it can be bought at this store.\nBrands on these terms' own pages: OTRA.";
    expect(FORBIDDEN.filter((f) => f.a.test(badOmission) && f.b.test(badOmission)).length).toBe(1);
    // The same shape with the brand PRESENT in the list is the feature working,
    // and must not fire — otherwise the rule flags every correct render.
    const good =
      "D1 returned LATTI for these terms, but nothing of it can be bought at this store.\nBrands on these terms' own pages: LATTI, OTRA.";
    expect(FORBIDDEN.filter((f) => f.a.test(good) && f.b.test(good))).toEqual([]);
  });
});

describe("no two sentences the store locator prints can contradict each other", () => {
  const at = { lat: 4.75068, lng: -74.03532 };

  test("across every stop reason and total", () => {
    const stops: Array<StoresResult["stopped"]> = ["registry-empty", "cap", "limit"];
    const totals = [undefined, 0, 1, 29, 115, 299, 300, 301];
    const offenders: string[] = [];

    for (const stopped of stops) {
      for (const registryTotal of totals) {
        for (const swept of [0, 1, 30, 299, 300]) {
          const r: StoresResult = {
            stores: Array.from({ length: Math.min(swept, 2) }, (_, i) => ({
              id: `s${i}`,
              name: "BOG X",
              distanceKm: 1 + i,
              street: "CRA 1",
              neighborhood: "N",
              city: "BOGOTA",
              state: "BOG",
              postalCode: "1",
              hours: [],
              active: true,
            })),
            swept,
            reachedKm: swept ? 2 : undefined,
            registryTotal,
            dropped: 0,
            stopped,
          };
          const out = renderStores(r, at, 1);

          // "every point the registry returns" and "may hold more" are opposite
          // claims about the same set.
          if (/every point the registry returns/.test(out) && /hold more/.test(out)) {
            offenders.push(`${stopped}/${registryTotal}/${swept}: exhausted AND more exist`);
          }
          // An exact remainder must never be negative or zero — that is not a
          // remainder, it is a contradiction of `swept`.
          const m = out.match(/holds (\d+) more further out/);
          if (m && Number(m[1]) <= 0) {
            offenders.push(`${stopped}/${registryTotal}/${swept}: non-positive remainder`);
          }
          // A capped sweep must not also claim to be the complete answer.
          if (/own ceiling of/.test(out) && /every point the registry returns/.test(out)) {
            offenders.push(`${stopped}/${registryTotal}/${swept}: capped AND complete`);
          }
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
