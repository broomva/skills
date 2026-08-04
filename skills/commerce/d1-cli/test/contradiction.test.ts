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
  isFilled,
  normalizeBrand,
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

function lineFor(term: string, status: LineStatus, brand: string): BasketLine {
  const named = status !== "no-match";
  return {
    term,
    status,
    compared: 1,
    matched: 1,
    product: named ? product(`PRODUCTO ${term}`, 300_000, brand) : undefined,
    price: isFilled(status) ? 300_000 : undefined,
    substituteSweep: status === "no-brand-match",
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
function crossOf(baseStatus: LineStatus, altStatus: LineStatus, brandOnBase: string): CrossBasket {
  const base = planOf([lineFor("arroz", baseStatus, brandOnBase)]);
  const alt = planOf([lineFor("arroz", altStatus, BRAND)]);
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
    // Computed EXACTLY as `compareBaskets` does, so every state enumerated here
    // is one the production path can actually produce. A looser rule would
    // report contradictions in states that cannot occur, which is a different
    // and much less useful test.
    brandsSeen:
      al.status === "no-brand-match"
        ? filledBase && normalizeBrand(brandOnBase) !== normalizeBrand(BRAND)
          ? [brandOnBase]
          : []
        : undefined,
  };
}

/**
 * Pairs of sentences that cannot both be true.
 *
 * Each entry is the *reason* a pair is contradictory, so a failure names the
 * defect rather than a line number. All four rounds' findings are here.
 */
const FORBIDDEN: Array<{ why: string; a: RegExp; b: RegExp }> = [
  {
    why: "claims the brand is absent from what D1 returned, while naming it among the brands returned",
    a: new RegExp(`Nothing D1 returned for these terms is ${BRAND}\\.`),
    b: new RegExp(`Brands it did return:[^\\n]*\\b${BRAND}\\b`),
  },
  {
    why: "claims the brand is absent, while a line says the absence is not about the brand",
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
    a: /not an alternative/,
    b: /only .* could fill/,
  },
  {
    why: "claims the brand is no alternative to anything, while a line prices it over budget",
    a: /not an alternative/,
    b: /found but over budget/,
  },
  {
    why: "claims the brand is no alternative to anything, while a lookup never answered so nothing is known",
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

describe("no two sentences the comparison prints can contradict each other", () => {
  test("across every reachable (base, alt) status pair", () => {
    const offenders: string[] = [];
    for (const baseStatus of ALL_STATUSES) {
      for (const altStatus of ALL_STATUSES) {
        for (const brandOnBase of ["OTRA", BRAND]) {
          const out = renderComparison(crossOf(baseStatus, altStatus, brandOnBase));
          for (const { why, a, b } of FORBIDDEN) {
            if (a.test(out) && b.test(out)) {
              offenders.push(
                `${baseStatus} / ${altStatus} / base brand ${brandOnBase}: ${why}\n${out}\n`,
              );
            }
          }
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  test("the enumeration is not vacuous — it really does exercise every sentence", () => {
    // A forbidden-pair check passes trivially if no state produces either
    // sentence. This asserts the render surface is actually being covered, so
    // the test above cannot go green by rendering nothing.
    const seen = new Set<string>();
    for (const baseStatus of ALL_STATUSES) {
      for (const altStatus of ALL_STATUSES) {
        for (const brandOnBase of ["OTRA", BRAND]) {
          const out = renderComparison(crossOf(baseStatus, altStatus, brandOnBase));
          for (const marker of [
            "BOTH filled:",
            "no price to compare",
            "Not counted — no LATTI for",
            "found but over budget for",
            "lookup did not answer for",
            "D1 returned nothing at all for",
            "only LATTI could fill",
            "Neither basket filled",
            "Nothing D1 returned for these terms",
          ]) {
            if (out.includes(marker)) seen.add(marker);
          }
        }
      }
    }
    expect(seen.size).toBe(9);
  });

  test("and a deliberately contradictory render IS caught (control)", () => {
    // Without this the suite cannot distinguish "no contradictions" from "the
    // matcher never matches anything".
    const bad = "Nothing D1 returned for these terms is LATTI.\nBrands it did return: LATTI, OTRA.";
    const hits = FORBIDDEN.filter((f) => f.a.test(bad) && f.b.test(bad));
    expect(hits.length).toBeGreaterThan(0);
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
