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
  brandReturnedIn,
  brandsIn,
  isFilled,
  partialLook,
} from "../src/basket.ts";
import { renderComparison, renderStores } from "../src/present.ts";
import type { StoresResult } from "../src/stores.ts";
import type { Product } from "../src/types.ts";

const BRAND = "LATTI";

const product = (name: string, price: number, brand = "OTRA"): Product => ({
  productId: "p",
  skuId: "1",
  name,
  brand,
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

function lineFor(
  term: string,
  status: LineStatus,
  brand: string,
  pageBrands: string[],
  sweepBrands: string[],
  partial: boolean,
): BasketLine {
  const named = status !== "no-match";
  return {
    term,
    status,
    compared: 1,
    // A PARTIAL look is its own axis. `matched > looked` is what makes
    // `partialLook` fire, and before round 8 no state in this file set either
    // field — so `c.partial` was `undefined` in all 98 states and every
    // sentence that has a scoped variant was checked in one polarity only.
    // Round 6's entire fix — a categorical claim never outruns its look — was
    // unprotected by the property test written to protect it.
    looked: partial ? 12 : 29,
    matched: 29,
    product: named ? product(`PRODUCTO ${term}`, 300_000, brand) : undefined,
    price: isFilled(status) ? 300_000 : undefined,
    substituteSweep: status === "no-brand-match",
    // Set, because production always sets it and the live defect lived here.
    // Whether the page CARRIED the requested brand is its own axis: D1 returning
    // a COPELIA product at Price 0 and D1 returning no COPELIA at all are
    // different facts that produce different headlines, and an enumeration
    // fixing one of them can never exercise the other.
    pageBrands: named ? pageBrands : [],
    // ...and whether the CATEGORY SWEEP carried it is a third. Round 6 added
    // this population to production's returned-brand test and round 7 kept the
    // display list on the page alone — correctly — which made "brand in the
    // sweep but not on the page" a reachable state in which the headline and
    // the list beside it disagreed. No state here could produce it, because
    // this fixture never set the field at all.
    sweepBrands: named ? sweepBrands : [],
  };
}

const planOf = (lines: BasketLine[]): BasketPlan => ({
  budget: 10_000_000,
  lines,
  total: 0,
  remaining: 10_000_000,
});

/**
 * Mirrors `compareBaskets`' own bucketing.
 *
 * Deliberately re-derived rather than imported: this file's job is to check the
 * RENDER against the state it is handed, and every state the type permits — not
 * only the ones one production path happens to produce today.
 */
function crossOf(
  baseStatus: LineStatus,
  altStatus: LineStatus,
  brandOnBase: string,
  pageHasBrand = true,
  sweepHasBrand = false,
  partial = false,
): CrossBasket {
  const page = pageHasBrand ? [brandOnBase, BRAND] : [brandOnBase];
  const sweep = sweepHasBrand ? [BRAND] : [];
  // The ALT line's product is the source it REJECTED, not something of the
  // requested brand — that is what `no-brand-match` means. Deriving the page
  // from it pinned the requested brand into every page, so the other headline
  // was never rendered and its rule reported itself dead.
  const base = planOf([lineFor("arroz", baseStatus, brandOnBase, page, sweep, partial)]);
  const alt = planOf([lineFor("arroz", altStatus, brandOnBase, page, sweep, partial)]);
  const bl = base.lines[0] as BasketLine;
  const al = alt.lines[0] as BasketLine;
  const bothFilled = isFilled(bl.status) && isFilled(al.status);
  const filledBase = isFilled(bl.status);

  return {
    brand: BRAND,
    base,
    alt,
    rows: [
      {
        term: "arroz",
        base: bl,
        alt: al,
        delta: bothFilled ? 0 : undefined,
      },
    ],
    comparable: bothFilled
      ? { terms: 1, baseTotal: 300_000, altTotal: 300_000, delta: 0 }
      : { terms: 0, baseTotal: 0, altTotal: 0, delta: 0 },
    onlyBase: filledBase && al.status === "no-brand-match" ? ["arroz"] : [],
    altOverBudget: filledBase && al.status === "over-budget" ? ["arroz"] : [],
    altUnknown: filledBase && al.status === "replacement-unknown" ? ["arroz"] : [],
    altNoMatch:
      filledBase && (al.status === "no-match" || al.status === "nothing-in-stock") ? ["arroz"] : [],
    onlyAlt: isFilled(al.status) && !filledBase ? ["arroz"] : [],
    neither: !filledBase && !isFilled(al.status) ? ["arroz"] : [],
    // PRODUCTION's own `brandsIn`, not a copy of it.
    //
    // This was re-derived inline, and drifted the moment `brandsIn` changed —
    // in the very commit series that wrote this file. The two flagship rules
    // below then became unfalsifiable: side b of the "names the brand it says
    // is absent" rule occurred in 0 of 98 states, because the mirror
    // re-implemented the exclusion the rule exists to check. A mirror of the
    // code under test tests the mirror.
    brandsSeen:
      alt.lines.length && alt.lines.every((l) => l.status === "no-brand-match")
        ? brandsIn([...base.lines, ...alt.lines])
        : undefined,
    // PRODUCTION's own function, for the same reason `brandsIn` is above it.
    //
    // This was the one field still re-derived by hand, and it drifted exactly as
    // round 4 warned: production learned to read `sweepBrands` in round 6 and
    // this copy never did. Every enumerated state therefore had the requested
    // brand either on the page or nowhere — the sweep-only state, where the
    // headline and the evidence list disagree, was unreachable here while being
    // perfectly reachable live. A mirror of the code under test tests the
    // mirror; round 4 found that and fixed one of the two fields.
    brandReturnedIn:
      alt.lines.length && alt.lines.every((l) => l.status === "no-brand-match")
        ? brandReturnedIn([...base.lines, ...alt.lines], BRAND)
        : undefined,
    // Production's, too — same rule.
    partial: partialLook(alt.lines),
  };
}

/**
 * Pairs of sentences that cannot both be true.
 *
 * Each entry is the *reason* a pair is contradictory, so a failure names the
 * defect rather than a line number. All four rounds' findings are here.
 */
/** The evidence list's label, either scoping. Both are the PAGE population. */
const LIST_LABEL = `Brands (?:on these terms' own pages|among the \\d+ looked at)`;
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
    why: "says a term was not counted for two mutually exclusive reasons",
    a: /Not counted — no .* for: arroz\b/,
    b: /Neither basket filled: arroz\b/,
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
function everyState(): Array<{ label: string; out: string }> {
  const states: Array<{ label: string; out: string }> = [];
  for (const baseStatus of ALL_STATUSES) {
    for (const altStatus of ALL_STATUSES) {
      for (const brandOnBase of ["OTRA", BRAND, `${BRAND} FOODS`]) {
        for (const pageHasBrand of [true, false]) {
          for (const sweepHasBrand of [true, false]) {
            for (const partial of [true, false]) {
              states.push({
                label: `${baseStatus} / ${altStatus} / base brand ${brandOnBase} / page ${pageHasBrand} / sweep ${sweepHasBrand} / partial ${partial}`,
                out: renderComparison(
                  crossOf(baseStatus, altStatus, brandOnBase, pageHasBrand, sweepHasBrand, partial),
                ),
              });
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
    const unscoped: string[] = [];
    for (const { label, out } of everyState()) {
      if (!/the look covered \d+ of the \d+ D1 matched/.test(out)) {
        // A complete look needs no qualifier; only scoped states are checked.
        if (!/Raise --count/.test(out)) continue;
      }
      if (/but nothing of it can be bought at this store\./.test(out)) {
        unscoped.push(`${label}: unqualified universal beside a partial look\n${out}\n`);
      }
    }
    expect(unscoped).toEqual([]);
  });

  test("the enumeration is not vacuous — it really does exercise every sentence", () => {
    // A forbidden-pair check passes trivially if no state produces either
    // sentence. This asserts the render surface is actually being covered, so
    // the test above cannot go green by rendering nothing.
    const MARKERS = [
      "BOTH filled:",
      "no price to compare",
      "Not counted — no LATTI for",
      "found but over budget for",
      "lookup did not answer for",
      "D1 returned nothing at all for",
      "only LATTI could fill",
      "Neither basket filled",
      "Nothing D1 returned for these terms",
      "but nothing of it can be bought at this store",
      // Round 8's four. Each names a population or a denominator, and each was
      // unreachable in this enumeration before the sweep and partial axes
      // existed — which is exactly why the defects they describe survived.
      "in the category around these terms",
      "the look covered 12 of the 29 D1 matched",
      "Brands on these terms' own pages",
      "Brands among the 12 looked at",
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
